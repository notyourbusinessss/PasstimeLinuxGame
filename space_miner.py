#!/usr/bin/env python3
"""Space Miner - an idle game.  Run:  python3 space_miner.py   (needs: pip install pygame)

Start on Earth and mine the asteroids that orbit it. Every planet has its own ore, fleet and colony.
Unlock the next world with the ores of the ones behind you, travel between them, build megaprojects,
research tech, survive random events, then WARP for permanent Dark Matter.
Autosaves to ~/.space_miner_save.json; your empire keeps working while you're away.
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")       # no pygame banner in the terminal
import pygame

import core
import galaxy
import gamelog
import resources
import shipart
import ships
import devtools
import director
import front
import frontview
import gfx
import sounds
import touch
from version import __version__
from core import (BMAX, BUILDINGS, NB, NSH, NSITE, PERKS, PROJECTS, SC, SHIPS, SITES, TECHS, TECH_BY_ID,
                  UPGRADES, ACHIEVEMENTS, ACH_BY_ID, ACH_CATS, TIER_BONUS, TIER_NAMES, QUEST_TXT, fmt, geo_cost,
                  SECTORS, NSEC, FACTIONS, ARMORY, COMMIT_MODES, armory_cost, win_chance,
                  STARDUST_PERKS, sd_bonus)
from gfx import glow, scale_c, lerp_c

BASE_W, BASE_H = 1280, 720
W, H = BASE_W, BASE_H
PANEL = pygame.Rect(660, 104, 600, 608)
CX, CY = 325, 392                    # centre of the planet view
PLANET_R = 58
RESOLUTIONS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]      # the choices in the settings ("auto" picks one)


def apply_layout(w, h):
    """Lay the window out for a w x h canvas: the side panel sits on the right (a little wider on big canvases and as tall
    as the window), the planet / galaxy view takes the rest. 1280x720 is exactly the original layout."""
    global W, H, CX, CY, STRIP_Y
    W, H = int(w), int(h)
    pw = 600 + min(120, max(0, (W - BASE_W) // 8))
    PANEL.update(W - pw - 20, 104, pw, H - 112)
    CX, CY = (PANEL.x - 12) // 2 + 1, round(H * 0.5444)
    STRIP_Y = H - 30
    frontview.set_layout(PANEL.x, W, H)
ADD = pygame.BLEND_RGB_ADD
STRIP_Y = H - 30
STRIP_X0, STRIP_DX = 96, 46
BASE_TABS = ["Ships", "Upgrades", "Colony", "Planets", "Galaxy", "Tech", "Quests", "Warp", "Awards"]
T_SHIPS, T_UPG, T_COLONY, T_PLANETS, T_GALAXY, T_TECH, T_QUESTS, T_WARP, T_AWARDS, T_DEV = range(10)

MEDAL = {"bronze": (205, 127, 50), "silver": (205, 210, 222), "gold": (255, 208, 70), "platinum": (140, 230, 255)}
AWARD_CHIPS = ["All"] + ACH_CATS + ["Stats"]


def fmt_time(sec):
    sec = int(sec)
    h, m = sec // 3600, sec % 3600 // 60
    return f"{h}h {m:02d}m" if h else f"{m}m {sec % 60:02d}s"


def wrap(font, text, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if font.size(t)[0] > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


class App:
    def __init__(self, dev=False):
        self.g = core.Game()
        self.dev = dev                       # developer mode: only ever enabled by the --dev command-line flag
        self.dev_state = devtools.DevState()
        self.tabs = BASE_TABS + (["Dev"] if dev else [])
        self.banners = []
        self.view = "system"
        self.sel_sector = 1
        self.gal_mode = 0                    # which list the Galaxy tab's target browser shows
        self._gal_cache = {}
        self.raiders = []
        self.hover_sector = None
        self.warp_view = "warp"
        self.ascend_fx = 0.0
        self.ascend_confirm = 0.0
        self.ascend_cycle = 1
        self.ach_new = False
        self.awards_cat = "All"
        self.fps = 0.0
        self.can_scale = False               # True when the window is resizable and scales the game to fit
        self.fullscreen = False
        self.test_fault = 0
        self.scr = None
        self.res_override = None            # --resolution WxH from the command line (not saved)
        self.war_confirm = 0.0
        self.war_confirm_k = None
        self.g.stage_w, self.g.stage_h = PANEL.x - 12, H
        self.touch = touch.Touch(self, PANEL, lambda: (W, H))
        self.bg_since = None
        self.gal_wide = bool(self.g.settings.get("galaxy_wide", True))     # the galaxy map fills the window (the panel is hidden)
        self.wide_applied = None
        self.view_t = 9.0
        self.last_view = self.view
        self.had_event = False
        self.snd = sounds.Sounds(self.g.settings)
        self.t = 0.0
        self.dt = 0.016
        self.mouse = (0, 0)
        self.tab = 0
        self.scroll = [0] * len(self.tabs)
        self.buttons = []
        self.modal_buttons = []
        self.strip_hits = []
        self.floats, self.parts, self.rings, self.shooting = [], [], [], []
        self.pulse = self.shake = self.warp_fx = 0.0
        self.warp_confirm = self.reset_confirm = 0.0
        self.view_site = None
        self.asts = []
        self.content_h = 0
        self.fv = frontview.FrontView(self, T_GALAXY)
        self.load_assets()
        self.rebuild_view()

    # ---------------- assets -----------------
    def load_assets(self):
        self.site_sprites = [gfx.make_planet(PLANET_R, s["kind"], s["col"], 100 + i * 13) for i, s in enumerate(SITES)]
        self.strip_icons = [pygame.transform.smoothscale(sp, (32, 32)) for sp in self.site_sprites]
        self.strip_dark = []
        for ic in self.strip_icons:
            d = ic.copy()
            d.fill((24, 28, 46, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.strip_dark.append(d)
        self.planet_icons = [pygame.transform.smoothscale(sp, (50, 50)) for sp in self.site_sprites]
        self.planet_dark = []
        for ic in self.planet_icons:
            d = ic.copy()
            d.fill((24, 28, 46, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.planet_dark.append(d)
        self.ship_cache = {}                 # (planet, class, size) -> sprite, made on first use
        self.ship_rot = {}
        self.ast_sprites = {}
        self.crate_spr = gfx.make_crate()
        self.enemy_small = {f: gfx.make_enemy(f, 24) for f in FACTIONS}
        self.enemy_big = {f: gfx.make_enemy(f, 40) for f in FACTIONS}
        self.layout_cache = {}
        self.build_layout_assets()
        self.modal_bg = gfx.make_panel_bg(560, 290)
        rng = random.Random(6)
        self.streaks = [(rng.uniform(0, math.tau), rng.uniform(0.5, 1.4)) for _ in range(110)]

    def build_layout_assets(self):
        """Backdrops, vignette, side panel, galaxy nebula and stars for the current canvas size (cached per size)."""
        key = (W, H, PANEL.w)
        cached = self.layout_cache.get(key)
        if cached is None:
            sc = min((PANEL.x - 12) / 648, H / 720)
            gb = pygame.Surface((int(PANEL.x + 560), int(H + 280)))                  # the nebula behind the galaxy map
            gb.fill((0, 0, 0))
            bx, by = gb.get_width() / 2, gb.get_height() / 2
            for arm in range(2):
                for i in range(90):
                    t = i / 90
                    ang = arm * math.pi + t * 4.4
                    rad = (24 + t * 340) * sc
                    x, y = bx + math.cos(ang) * rad, by + math.sin(ang) * rad * 0.55
                    r = int((16 + int(t * 22)) * sc)
                    gb.blit(glow(r, (10, 28, 62)), (x - r, y - r), special_flags=ADD)
            gb.blit(glow(int(170 * sc), (86, 66, 36)), (bx - 170 * sc, by - 170 * sc), special_flags=ADD)
            rng = random.Random(5)
            stars = [[rng.uniform(0, W), rng.uniform(0, H), rng.choice([0.4, 0.7, 1.0, 1.6]),
                      rng.uniform(0, math.tau), rng.choice([(150, 170, 255), (255, 235, 200), (200, 220, 255)])]
                     for _ in range(int(190 * W * H / (BASE_W * BASE_H)))]
            cached = self.layout_cache[key] = (gfx.make_background(W, H), gfx.make_vignette(W, H),
                                               gfx.make_panel_bg(PANEL.w + 24, H - 8), gb, stars, gfx.make_galaxy_backdrop(W, H))
            if len(self.layout_cache) > 3:
                self.layout_cache.pop(next(iter(self.layout_cache)))
        self.bg, self.vig, self.panel_bg, self.galaxy_bg, self.stars, self.gal_backdrop = cached

    def set_resolution(self, w, h):
        """Switch the canvas to w x h (the window is recreated by the caller): re-lay out everything."""
        apply_layout(w, h)
        self.g.stage_w, self.g.stage_h = PANEL.x - 12, H
        self.build_layout_assets()
        self.wide_applied = None
        self.update_galaxy_layout()
        self.rebuild_view()
        self.touch.gesture = None
        self.raiders = []
        self.floats, self.parts, self.rings, self.shooting = [], [], [], []

    def ship_color(self, p, i):
        """The class colour (the accent every hull carries, and the colour of its engine glow and laser). On the planets
        with their own palette it is pulled towards that palette's glow."""
        pal = ships.palette(p)
        return SHIPS[i][3] if pal is None else lerp_c(SHIPS[i][3], pal[3], 0.4)

    def ship_sprite(self, p, i, icon=False):
        """The sprite of ship class i on planet p (every planet's fleet looks different)."""
        size = 46 if icon else round((26 + i * 2) * (1.3 if i >= gfx.FLEET_TIER else 1.0) * ships.scale(p))
        key = (p, i, size)
        spr = self.ship_cache.get(key)
        if spr is None:
            spr = self.ship_cache[key] = gfx.make_ship(i, SHIPS[i][3], size, ships.style(p), ships.palette(p))
        return spr

    def ship_icon(self, p, i):
        return self.ship_sprite(p, i, True)

    def get_ast_sprites(self, p):
        if p not in self.ast_sprites:
            oc = SITES[p]["ocol"]
            tint = lerp_c((255, 255, 255), oc, 0.45)
            self.ast_sprites[p] = [gfx.make_asteroid(sz, p * 31 + v * 7 + sz, tint)
                                   for sz in (34, 44, 56) for v in range(3)]
        return self.ast_sprites[p]

    def rebuild_view(self):
        p = self.g.cur
        self.view_site = p
        rng = random.Random(p * 977 + 3)
        self.asts = []
        rings = [(176, 5, 0.11), (218, 6, -0.085), (258, 7, 0.065)]
        rmax = min((PANEL.x - 12) / 2 - 30, (CY - 150) / 0.84)              # a bigger canvas gets more rings of asteroids
        r = 308
        while r <= rmax:
            rings.append((r, int(r / 42), (0.055 - 0.004 * len(rings)) * (1 if len(rings) % 2 else -1)))
            r += 50
        for ring, (r, n, spd) in enumerate(rings):
            for k in range(n):
                self.asts.append(dict(r=r + rng.uniform(-8, 8), a0=k / n * math.tau + rng.uniform(-0.2, 0.2),
                                      spd=spd * rng.uniform(0.85, 1.15), spr=rng.randrange(9),
                                      spin=rng.uniform(-1.2, 1.2), ph=rng.uniform(0, 6), hp=1.0, dead=0.0,
                                      rot=rng.uniform(0, 360)))

    def ast_pos(self, a):
        ang = a["a0"] + a["spd"] * self.t
        return CX + math.cos(ang) * a["r"], CY + math.sin(ang) * a["r"] * 0.84, ang

    # ---------------- input / actions -----------------
    def burst(self, x, y, col, n):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            s = random.uniform(40, 230)
            self.parts.append([x, y, math.cos(a) * s, math.sin(a) * s, random.uniform(0.35, 0.9), col])

    def mine_at(self, pos, asteroid=None):
        g = self.g
        if g.travel:
            return
        x = g.click(pos)
        self.snd.play("click")
        oc = SITES[g.cur]["ocol"]
        self.pulse = 1.0
        self.shake = 0.25
        self.floats.append([pos[0] + random.uniform(-14, 14), pos[1] - 12, f"+{fmt(x)}", 1.0, lerp_c(oc, (255, 255, 255), 0.4)])
        self.burst(pos[0], pos[1], oc, 7)
        self.rings.append([pos[0], pos[1], 0.0, lerp_c(oc, (255, 255, 255), 0.3)])
        self.rings = self.rings[-8:]
        if asteroid is not None:
            asteroid["hp"] -= 0.16
            if asteroid["hp"] <= 0:
                self.break_asteroid(asteroid)

    def break_asteroid(self, a):
        x, y, _ = self.ast_pos(a)
        self.burst(x, y, SITES[self.g.cur]["ocol"], 22)
        a["dead"] = 3.5
        a["hp"] = 0.0

    def space_click(self):
        alive = [a for a in self.asts if a["hp"] > 0]
        if alive:
            a = random.choice(alive)
            x, y, _ = self.ast_pos(a)
            self.mine_at((x, y), a)

    def mouse_down(self, pos, touch=False):
        g = self.g
        grow = 8 if touch else 0                       # fingers are fatter than a mouse pointer
        if g.event:
            for rect, fn in reversed(self.modal_buttons):
                if rect.collidepoint(pos):
                    fn()
                    return
            return
        c = g.crate
        if c and c.get("rect") and c["rect"].collidepoint(pos):
            g.grab_crate()
            return
        if self.panel_visible() and pos[0] >= PANEL.x - 10:
            for rect, fn in reversed(self.buttons):
                if rect.inflate(0, grow).collidepoint(pos):
                    fn()
                    return
            return
        for rect, k in self.strip_hits:
            if rect.inflate(grow, grow).collidepoint(pos):
                self.strip_click(k)
                return
        if self.view == "galaxy":
            self.fv.click(pos)
            return
        best, bd = None, 1e9
        for a in self.asts:
            if a["hp"] <= 0:
                continue
            x, y, _ = self.ast_pos(a)
            d = math.hypot(pos[0] - x, pos[1] - y)
            if d < bd:
                best, bd = a, d
        if best is not None and (bd < 38 or touch):                  # a tap anywhere mines the nearest asteroid
            x, y, _ = self.ast_pos(best)
            self.mine_at((x, y) if bd > 14 else pos, best)

    def sector_known(self, k):
        g = self.g
        return k in g.conquered or g.scanned(k) or SECTORS[k]["real"]

    def strip_click(self, k):
        g = self.g
        if k < 0:                                   # galaxy map button
            if not g.galaxy_open:
                g.toast("Unlock Mars to open the galaxy map.", 3)
                return
            self.view = "system" if self.view == "galaxy" else "galaxy"
            if self.view == "galaxy":
                w = g.weakest_target()
                if self.sel_sector in g.conquered and w is not None:
                    self.sel_sector = w
                self.tab = T_GALAXY
                self.fv.opened()
                if "gal_hint" not in g.flags:
                    g.flags.add("gal_hint")
                    g.toast("The Milky Way: attack any system within your jump range of one you hold. "
                            "Upgrade the Jump Drive in the Galaxy tab to reach further.", 9)
            return
        self.view = "system"
        if g.unlocked[k]:
            if k != g.cur:
                g.start_travel(k)
            else:
                self.tab = T_PLANETS
        else:
            self.tab = T_PLANETS

    def set_tab(self, k):
        self.tab = k

    def attack(self, k):
        """ATTACK / DECLARE WAR on the Galaxy tab: invading a faction at peace needs a second click."""
        g = self.g
        if SECTORS[k]["faction"] not in g.war and not (self.war_confirm > 0 and self.war_confirm_k == k):
            self.war_confirm, self.war_confirm_k = 4.0, k
            return
        self.war_confirm = 0.0
        g.start_campaign(k)

    def panel_visible(self):
        """The side panel is hidden while the galaxy map is shown wide."""
        return not (self.view == "galaxy" and self.gal_wide)

    def toggle_gal_wide(self):
        self.gal_wide = not self.gal_wide
        self.g.settings["galaxy_wide"] = self.gal_wide

    def leave_galaxy(self):
        self.view = "system"

    def update_galaxy_layout(self):
        """Wide map: the viewport takes the whole window; otherwise it stops at the side panel."""
        want = not self.panel_visible()
        if want != self.wide_applied:
            frontview.set_layout(W + 12 if want else PANEL.x, W, H, wide=want)
            self.fv.relayout()
            self.wide_applied = want

    def back_pressed(self):
        """The Android back button: leave the galaxy view; never quits (use Home)."""
        if not self.g.event and self.view == "galaxy":
            self.view = "system"

    def went_to_background(self):
        self.g.save()
        self.bg_since = time.time()
        gamelog.LOG.info("App went to the background; saved")

    def came_back(self):
        """Back from the background: the process may have been paused for hours; reloading the save pays the offline progress."""
        away = time.time() - self.bg_since if self.bg_since else 0.0
        self.bg_since = None
        gamelog.LOG.info("App came back after %.0f s", away)
        if away > 20:
            self.g.load()
            self.g.recalc()
            self.rebuild_view()

    def describe(self):
        """A few lines about the game state, added to error reports."""
        g = self.g
        try:
            win = pygame.display.get_window_size()
        except pygame.error:
            win = "?"
        return "\n".join([
            f"view={self.view} tab={self.tabs[self.tab] if 0 <= self.tab < len(self.tabs) else self.tab} planet={SITES[g.cur]['name']} "
            f"fps={self.fps:.0f} window={win} fullscreen={self.fullscreen} dev={self.dev}",
            f"play_time={g.play_time:.0f}s cycle={g.cycle} warps={g.warps} unlocked={g.n_unlocked} sectors={len(g.conquered) - 1} "
            f"fronts={len(g.campaigns)}/{g.max_fronts()} incoming={len(g.incoming)} event={'yes' if g.event else 'no'} "
            f"travel={'yes' if g.travel else 'no'} cheated={'cheated' in g.flags}",
            f"galaxy camera: scale={self.fv.s:.4f} px/ly centre=({self.fv.cx:.0f},{self.fv.cy:.0f}) selected system={self.sel_sector}",
        ])

    def open_log_folder(self):
        d = gamelog.log_dir()
        for cmd in (["xdg-open", d], ["open", d]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except OSError as e:
                    gamelog.LOG.warning("Could not open the log folder: %s", e)
        if hasattr(os, "startfile"):
            os.startfile(d)                              # Windows
            return
        self.g.toast(f"Log folder: {d}", 8)

    def display_setting(self):
        return self.res_override or self.g.settings.get("resolution", "auto")

    def apply_display(self, fullscreen=None):
        """(Re)create the window for the current fullscreen / resolution settings and re-lay out the game. Returns True
        if it worked."""
        g = self.g
        want_fs = self.fullscreen if fullscreen is None else fullscreen
        w, h = choose_resolution(self.display_setting(), want_fs)
        if (w, h) == (W, H) and self.can_scale and want_fs != self.fullscreen:      # same canvas: only toggle fullscreen
            try:
                pygame.display.toggle_fullscreen()
                self.fullscreen = pygame.display.is_fullscreen() if hasattr(pygame.display, "is_fullscreen") else want_fs
                return True
            except (pygame.error, NotImplementedError):
                pass                                                                  # fall through: recreate the window
        if (w, h) == (W, H) and want_fs == self.fullscreen and self.scr is not None:
            return True
        self.scr, self.can_scale, self.fullscreen = open_window(w, h, want_fs)
        self.set_resolution(w, h)
        gamelog.LOG.info("Display: %dx%d, fullscreen %s, window %s", w, h, self.fullscreen, pygame.display.get_window_size())
        return True

    def toggle_fullscreen(self):
        """F11 / Alt+Enter / the Stats page button. The canvas is scaled to fit the screen (black bars if the aspect
        ratio differs); with the automatic resolution a fullscreen game uses the whole desktop's resolution."""
        g = self.g
        if not self.can_scale:
            g.toast("Fullscreen is not available on this display.", 3)
            return False
        before = self.fullscreen
        try:
            self.apply_display(fullscreen=not self.fullscreen)
        except (pygame.error, NotImplementedError) as e:
            gamelog.LOG.warning("Could not switch fullscreen: %s", e)
        if self.fullscreen == before:
            g.toast("Fullscreen is not supported by this display.", 3)
            return False
        g.settings["fullscreen"] = self.fullscreen
        gamelog.LOG.info("Fullscreen %s", "on" if self.fullscreen else "off")
        g.toast("Fullscreen on - press F11 or Esc to leave it." if self.fullscreen else "Back to the window.", 3)
        return True

    def set_resolution_choice(self, value):
        """Settings button: 'auto' or 'WxH'."""
        self.g.settings["resolution"] = value
        self.res_override = None
        self.apply_display()
        w, h = choose_resolution(value, self.fullscreen)
        self.g.toast(f"Resolution: {w}x{h}" + (" (auto)" if value == "auto" else ""), 3)

    def select_sector(self, k):
        """Select a sector (from the Galaxy tab); if the map is zoomed in, the camera follows."""
        self.sel_sector = k
        if self.view == "galaxy":
            self.fv.focus(k)

    def close_look(self):
        """Open the galaxy map zoomed in on the selected front."""
        g = self.g
        if not g.galaxy_open:
            g.toast("Unlock Mars to open the galaxy map.", 3)
            return
        self.view = "galaxy"
        self.tab = T_GALAXY
        self.fv.focus_selected()

    def zoom_out(self):
        if not self.g.galaxy_open:
            return
        self.view = "galaxy"
        self.fv.fit()

    def go_home(self):
        """Show all your territory on the galaxy map."""
        if not self.g.galaxy_open:
            return
        self.view = "galaxy"
        self.fv.home()

    def toggle_auto(self):
        self.g.auto_war = not self.g.auto_war

    def galaxy_key(self, key):
        """Z opens (or leaves) the front close-up; in the galaxy view the zoom and pan keys work too."""
        if not self.g.galaxy_open:
            return False
        if key == pygame.K_z and self.view != "galaxy":
            self.close_look()
            return True
        return self.view == "galaxy" and self.fv.key(key)

    def do_warp(self):
        g = self.g
        if g.warp_gain() < 1:
            return
        if self.warp_confirm <= 0:
            self.warp_confirm = 4.0
            return
        self.warp_confirm = 0
        g.do_warp()

    def do_ascend(self):
        g = self.g
        if not g.can_ascend():
            return
        if self.ascend_confirm <= 0:
            self.ascend_confirm = 4.0
            return
        self.ascend_confirm = 0
        g.ascend()

    def hard_reset(self):
        if self.reset_confirm <= 0:
            self.reset_confirm = 4.0
            return
        self.reset_confirm = 0
        self.g.hard_reset()

    def add_banner(self, b):
        b.setdefault("dur", 3.6)
        b["t"] = 0.0
        if len(self.banners) < 8:
            self.banners.append(b)

    def spawn_raid(self, data):
        base = director.TIERS[data.get("tier", 0)]["count"]
        n = random.randint(base - 2, base + 2)
        for i in range(n):
            a = random.uniform(0, math.tau)
            d = random.uniform(330, 420)
            self.raiders.append(dict(x=CX + math.cos(a) * d, y=CY + math.sin(a) * d * 0.8, fac=data["faction"],
                                     win=data["win"], stop=random.uniform(115, 190) if data["win"] else 62,
                                     spd=random.uniform(70, 110), hp=1.0, lost=data["lost"], first=(i == 0)))

    def update_raiders(self, dt):
        keep = []
        for r in self.raiders:
            dx, dy = CX - r["x"], CY - r["y"]
            d = math.hypot(dx, dy) or 1.0
            if d > r["stop"]:
                r["x"] += dx / d * r["spd"] * dt
                r["y"] += dy / d * r["spd"] * dt
                keep.append(r)
                continue
            col = FACTIONS[r["fac"]]["col"]
            if r["win"]:
                self.burst(r["x"], r["y"], col, 14)
                self.rings.append([r["x"], r["y"], 0.3, col])
            else:
                self.burst(r["x"], r["y"], (255, 120, 80), 10)
                self.shake = 0.5
                if r["first"]:
                    self.floats.append([CX, CY - 80, f"RAID!  -{fmt(r['lost'])}", 1.2, (255, 120, 100)])
        self.raiders = keep

    # ---------------- update -----------------
    def update(self, dt):
        g = self.g
        if self.test_fault > 0:                      # developer test: exercise the error log (Dev tab -> Game)
            self.test_fault -= 1
            raise RuntimeError("Test error raised from the Dev tab")
        self.dt = dt
        self.t += dt
        g.step(dt)
        if self.view != self.last_view:
            self.last_view, self.view_t = self.view, 0.0
        self.view_t += dt
        self.update_galaxy_layout()
        self.fv.update(dt)
        if self.g.galaxy_open:
            self.fv.prebuild()                # the painted Milky Way is made in the background once the map is open to you
        if self.view_site != g.cur:
            self.rebuild_view()
        self.pulse = max(0, self.pulse - dt * 4)
        self.shake = max(0, self.shake - dt * 3)
        self.warp_fx = max(0, self.warp_fx - dt)
        self.ascend_fx = max(0, self.ascend_fx - dt)
        self.ascend_confirm = max(0, self.ascend_confirm - dt)
        self.warp_confirm = max(0, self.warp_confirm - dt)
        self.war_confirm = max(0, self.war_confirm - dt)
        self.reset_confirm = max(0, self.reset_confirm - dt)
        for kind, data in g.fx_events:
            if kind == "warp":
                self.warp_fx = 1.8
                self.snd.play("warp")
            elif kind == "unlock":
                self.rings.append([CX, CY, 0.0, SITES[data]["col"]])
                self.burst(CX, CY, SITES[data]["col"], 40)
                self.snd.play("unlock")
            elif kind == "project":
                self.rings.append([CX, CY, 0.0, (255, 220, 120)])
                self.burst(CX, CY, (255, 220, 120), 50)
                self.snd.play("project")
            elif kind == "crate":
                c = data
                self.burst(c["x"], c.get("yy", c["y"]), (255, 215, 80), 30)
                self.rings.append([c["x"], c.get("yy", c["y"]), 0.0, (255, 215, 80)])
                self.snd.play("crate")
            elif kind == "buy":
                self.burst(CX, CY, SHIPS[data[1]][3], 8)
                self.snd.play("buy")
            elif kind == "travel":
                self.snd.play("travel")
            elif kind == "ach":
                self.ach_new = True
                a = ACH_BY_ID.get(data)
                if a:
                    self.add_banner(dict(header="ACHIEVEMENT UNLOCKED", title=a["name"], sub=a["desc"],
                                         right=f"+{TIER_BONUS[a['tier']] * 100:g}%", tier=a["tier"], sound="ach",
                                         col=MEDAL[a["tier"]]))
            elif kind == "ascend":
                self.ascend_fx = 3.4
                self.ascend_cycle = data["cycle"]
                self.view = "system"
                self.warp_view = "ascend"
                self.snd.play("ascend")
                self.add_banner(dict(header="ASCENSION", title=f"Cycle {data['cycle']} begins", sub="The universe resets - you keep your Stardust.",
                                     right=f"+{data['gain']}", sound=None, col=(255, 215, 120), glyph="*", dur=5.0))
            elif kind == "campaign":
                self.snd.play("buy")
            elif kind == "conquer":
                sec = SECTORS[data]
                col = FACTIONS[sec["faction"]]["col"]
                self.add_banner(dict(header="SECTOR LIBERATED", title=sec["name"], sub=sec["desc"], right="",
                                     sound="win", col=col, glyph="!", dur=5.0))
                x, y = self.fv.pos(data)
                self.burst(x, y, col, 50)
                self.rings.append([x, y, 0.0, col])
            elif kind == "defeat":
                sec = SECTORS[data]
                self.add_banner(dict(header="DEFEAT", title=sec["name"], sub="Your fleet was beaten back and lost ships.",
                                     right="", sound="lose", col=(255, 110, 100), glyph="x", dur=4.5))
            elif kind == "raid":
                self.snd.play("raid")
                if data["p"] == g.cur and self.view == "system":
                    self.spawn_raid(data)
            elif kind == "warning":
                if data["kind"] == "offensive" or data["tier"] >= 1:
                    name = "Enemy counter-offensive" if data["kind"] == "offensive" else director.TIERS[data["tier"]]["name"]
                    self.add_banner(dict(header="INCOMING ATTACK", title=name, sub=data["text"][:60], right=f"{int(data['eta'])}s",
                                         sound="raid", col=(255, 110, 100), glyph="!", dur=5.0))
                else:
                    self.snd.play("raid")
            elif kind == "war":
                name = FACTIONS[data["fac"]]["name"]
                if data["by"] == "player":
                    self.add_banner(dict(header="WAR DECLARED", title=name, sub="You invade. Their fleets will strike back.",
                                         right="", sound="raid", col=FACTIONS[data["fac"]]["col"], glyph="!", dur=5.0))
                else:
                    self.add_banner(dict(header="INVASION!", title=name, sub="They declare war on you. Defend your worlds!",
                                         right="", sound="lose", col=(255, 90, 90), glyph="!", dur=6.0))
            elif kind == "peace":
                self.add_banner(dict(header="PEACE", title=f"Truce with the {FACTIONS[data['fac']]['name']}",
                                     sub="They stand down for a while.", right="", sound="win", col=(130, 220, 255), glyph="v", dur=4.5))
            elif kind == "sector_lost":
                sec = SECTORS[data]
                self.add_banner(dict(header="SECTOR LOST", title=sec["name"], sub="Liberate it again to get its bonus back.",
                                     right="", sound="lose", col=(255, 90, 90), glyph="x", dur=6.0))
                x, y = self.fv.pos(data)
                self.burst(x, y, (255, 90, 90), 40)
            elif kind == "held":
                sec = SECTORS[data]
                self.add_banner(dict(header="COUNTER-OFFENSIVE REPELLED", title=sec["name"], sub="Your garrison held the line.",
                                     right="", sound="buy", col=(130, 220, 255), glyph="v", dur=4.0))
        g.fx_events.clear()
        if self.banners:
            b = self.banners[0]
            if b["t"] == 0.0 and b.get("sound", "ach"):
                self.snd.play(b.get("sound", "ach"))
            b["t"] += dt
            if len(self.banners) > 3:
                b["dur"] = min(b["dur"], 1.6)
            if b["t"] >= b["dur"]:
                self.banners.pop(0)
        self.update_raiders(dt)
        if g.event and not self.had_event:
            self.snd.play("event")
        self.had_event = bool(g.event)
        if self.dev:
            devtools.tick(self, dt)
        shown = sum(min(o, 4) for o in g.owned[g.cur])
        alive = [a for a in self.asts if a["hp"] > 0]
        for a in self.asts:
            a["rot"] += a["spin"] * 20 * dt
            if a["hp"] <= 0:
                a["dead"] -= dt
                if a["dead"] <= 0:
                    a["hp"] = 1.0
            elif a["hp"] < 1:
                a["hp"] = min(1.0, a["hp"] + 0.02 * dt)
        if alive and shown:
            tgt = random.choice(alive)
            tgt["hp"] -= shown * 0.012 * dt * len(alive) / 3
            if tgt["hp"] <= 0:
                self.break_asteroid(tgt)
        for f in self.floats:
            f[1] -= 40 * dt
            f[3] -= dt * 0.9
        self.floats = [f for f in self.floats if f[3] > 0]
        for p in self.parts:
            p[0] += p[2] * dt; p[1] += p[3] * dt
            p[2] *= 0.97; p[3] *= 0.97
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0][-300:]
        for r in self.rings:
            r[2] += dt
        self.rings = [r for r in self.rings if r[2] < 0.7]
        for s in self.stars:
            s[0] -= s[2] * 7 * dt
            if s[0] < 0:
                s[0] = W; s[1] = random.uniform(0, H)
        if random.random() < dt * 0.15:
            self.shooting.append([random.uniform(0, PANEL.x - 90), random.uniform(0, 250), 0.0])
        for s in self.shooting:
            s[2] += dt
        self.shooting = [s for s in self.shooting if s[2] < 0.7]

    # ---------------- text helpers -----------------
    def txt(self, surf, font, text, pos, col=(235, 235, 245), anchor="topleft", shadow=False):
        if shadow:
            sh = font.render(text, True, (0, 0, 8))
            surf.blit(sh, sh.get_rect(**{anchor: (pos[0] + 2, pos[1] + 2)}))
        img = font.render(text, True, col)
        r = img.get_rect(**{anchor: pos})
        surf.blit(img, r)
        return r

    # ---------------- drawing: world -----------------
    def draw(self, scr, fonts):
        g = self.g
        self.buttons = []
        self.modal_buttons = []
        if self.view == "galaxy":                      # a different place: the star chart, not the planet's sky
            scr.blit(self.gal_backdrop, (0, 0))
        else:
            scr.blit(self.bg, (0, 0))
            self.draw_stars(scr)
        site = SITES[g.cur]
        if self.view == "system":
            scr.blit(glow(280, scale_c(site["col"], 0.22)), (CX - 280, CY - 280), special_flags=ADD)
        if g.buff_mult > 1.5 and self.view == "system":
            k = 0.6 + 0.4 * math.sin(self.t * 6)
            scr.blit(glow(260, scale_c((140, 100, 20), k)), (CX - 260, CY - 260), special_flags=ADD)
        if self.view == "galaxy":
            self.fv.draw(scr, fonts)
        else:
            self.draw_scene(scr)
            self.draw_raiders(scr)
            self.draw_crate(scr)
        self.draw_fx(scr, fonts[1])
        scr.blit(self.vig, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        if self.view == "galaxy":
            self.fv.draw_overlay(scr, fonts)
        if self.view_t < 0.45:                         # fade in when the view changes
            ov = pygame.Surface((W, H))
            ov.set_alpha(int(255 * (1 - self.view_t / 0.45) ** 2))
            scr.blit(ov, (0, 0))
        self.draw_hud(scr, fonts)
        if self.dev:
            self.draw_dev_badge(scr, fonts)
        self.draw_strip(scr, fonts)
        if self.panel_visible():
            self.draw_panel(scr, fonts)
        self.draw_toasts(scr, fonts[2])
        self.draw_banner(scr, fonts)
        if g.event:
            self.draw_event(scr, fonts)
        if g.travel:
            self.draw_travel(scr, fonts)
        if self.warp_fx > 0:
            self.draw_warp_fx(scr)
        if self.ascend_fx > 0:
            self.draw_ascend_fx(scr, fonts)

    def draw_stars(self, scr):
        for x, y, d, ph, col in self.stars:
            b = 0.55 + 0.45 * math.sin(self.t * 1.7 + ph)
            if d >= 1.0:
                r = 4 if d < 1.5 else 6
                scr.blit(glow(r, scale_c(col, b)), (x - r, y - r), special_flags=ADD)
            else:
                v = int(80 + 110 * b * d)
                scr.set_at((int(x), int(y)), (v, v, min(255, v + 25)))
        for sx, sy, t in self.shooting:
            k = 1 - t / 0.7
            x0, y0 = sx + t * 500, sy + t * 260
            pygame.draw.line(scr, scale_c((200, 220, 255), k), (x0, y0), (x0 - 70 * k, y0 - 36 * k), 2)

    def draw_rings(self, scr, cx, cy, r, front):
        for k, (f, col) in enumerate([(1.5, (170, 150, 110)), (1.68, (214, 194, 150)), (1.85, (190, 170, 130)),
                                      (2.05, (130, 116, 90))]):
            rx, ry = r * f, r * f * 0.27
            rect = pygame.Rect(cx - rx, cy - ry, 2 * rx, 2 * ry)
            pygame.draw.arc(scr, col, rect, math.pi if front else 0, math.tau if front else math.pi, 3)

    def draw_scene(self, scr):
        g = self.g
        p = g.cur
        site = SITES[p]
        behind, front = [], []
        for a in self.asts:
            if a["hp"] <= 0:
                continue
            x, y, ang = self.ast_pos(a)
            (behind if math.sin(ang) < 0 else front).append(("a", a, x, y))
        for i in range(NSH):
            n = ships.shown(p, g.owned[p][i])
            d = 1 if i % 2 == 0 else -1
            for j in range(n):
                dx, dy, depth = ships.orbit(p, i, j, n, self.t, d)
                hd = ships.heading(p, i, j, n, self.t, d)
                (behind if depth < 0 else front).append(("s", (i, j, hd, d), CX + dx, CY + dy))
        for item in behind:
            self.draw_item(scr, item)
        spr = self.site_sprites[p]
        ox = random.uniform(-2, 2) * self.shake
        scr.blit(glow(int(PLANET_R * 2.3), scale_c(site["col"], 0.35)), (CX - PLANET_R * 2.3, CY - PLANET_R * 2.3),
                 special_flags=ADD)
        if site["kind"] == "saturn":
            self.draw_rings(scr, CX, CY, PLANET_R, False)
        scr.blit(spr, spr.get_rect(center=(CX + ox, CY)))
        if site["kind"] in ("earth", "venus"):
            pygame.draw.circle(scr, scale_c(site["col"], 0.5), (CX, CY), PLANET_R + 1, 2)
        if site["kind"] == "saturn":
            self.draw_rings(scr, CX, CY, PLANET_R, True)
        for item in front:
            self.draw_item(scr, item)
        style = ships.style(p)
        for item in behind + front:
            if item[0] == "s":
                i, j, hd, d = item[1]
                if math.sin(self.t * 5 + j * 2 + i) > 0.9:
                    tgt, td = None, 1e9
                    for a in self.asts:
                        if a["hp"] > 0:
                            ax, ay, _ = self.ast_pos(a)
                            dd = (ax - item[2]) ** 2 + (ay - item[3]) ** 2
                            if dd < td:
                                tgt, td = a, dd
                    if tgt is not None and td < 130 ** 2:
                        tx, ty, _ = self.ast_pos(tgt)
                        col = self.ship_color(p, i)
                        shipart.beam(scr, style, (item[2], item[3]), (tx, ty), col, self.t, i * 7 + j)
                        scr.blit(glow(16, scale_c(col, 0.8)), (tx - 16, ty - 16), special_flags=ADD)

    def draw_item(self, scr, item):
        g = self.g
        kind, data, x, y = item
        if kind == "a":
            a = data
            sprs = self.get_ast_sprites(g.cur)
            spr = sprs[a["spr"]]
            sc = 0.55 + 0.45 * a["hp"]
            img = pygame.transform.rotozoom(spr, a["rot"], sc)
            scr.blit(img, img.get_rect(center=(x, y)))
            oc = SITES[g.cur]["ocol"]
            for off in (0.0, 2.4):
                ga = math.radians(a["rot"]) + off
                gx = x + math.cos(ga) * spr.get_width() * 0.2 * sc
                gy = y + math.sin(ga) * spr.get_width() * 0.2 * sc
                f = 0.55 + 0.45 * math.sin(self.t * 4 + a["ph"] + off)
                scr.blit(glow(7, scale_c(oc, 0.9 * f)), (gx - 7, gy - 7), special_flags=ADD)
            return
        i, j, ta, d = data
        col = self.ship_color(g.cur, i)
        for tc in (1, 2, 3):
            bx = x - math.cos(ta) * tc * 7
            by = y - math.sin(ta) * tc * 7
            scr.blit(glow(7 - tc, scale_c(col, 0.55 / tc)), (bx - (7 - tc), by - (7 - tc)), special_flags=ADD)
        q = int(round(-math.degrees(ta) / 10)) % 36
        key = (g.cur, i, q)
        spr = self.ship_rot.get(key)
        if spr is None:
            spr = self.ship_rot[key] = pygame.transform.rotate(self.ship_sprite(g.cur, i), q * 10)
        scr.blit(spr, spr.get_rect(center=(x, y)))

    def draw_crate(self, scr):
        c = self.g.crate
        if not c:
            return
        x, y = c["x"], c.get("yy", c["y"])
        k = 0.7 + 0.3 * math.sin(self.t * 8)
        scr.blit(glow(46, scale_c((200, 150, 30), k)), (x - 46, y - 46), special_flags=ADD)
        scr.blit(self.crate_spr, self.crate_spr.get_rect(center=(x, y)))
        c["rect"] = pygame.Rect(0, 0, 58, 58)
        c["rect"].center = (x, y)

    def draw_fx(self, scr, med):
        for r in self.rings:
            t = r[2] / 0.7
            pygame.draw.circle(scr, scale_c(r[3], 1 - t), (int(r[0]), int(r[1])), int(12 + 110 * t), 2)
        for p in self.parts:
            k = max(0.0, min(1.0, p[4] * 1.6))
            rad = 5 if k > 0.5 else 3
            scr.blit(glow(rad, scale_c(p[5], k)), (p[0] - rad, p[1] - rad), special_flags=ADD)
        for x, y, text, life, col in self.floats:
            sh = med.render(text, True, (0, 0, 0))
            img = med.render(text, True, col)
            a = max(0, min(255, int(life * 320)))
            sh.set_alpha(a); img.set_alpha(a)
            scr.blit(sh, sh.get_rect(center=(x + 2, y + 2)))
            scr.blit(img, img.get_rect(center=(x, y)))

    def draw_warp_fx(self, scr):
        prog = self.warp_fx / 1.8
        grow = 1 - prog
        for a, sp in self.streaks:
            d0 = grow * sp * 700
            d1 = d0 + 40 + grow * 260 * sp
            v = int(255 * min(1, prog * 1.6))
            pygame.draw.line(scr, (v // 2 + 40, v // 2 + 60, v), (CX + math.cos(a) * d0, CY + math.sin(a) * d0),
                             (CX + math.cos(a) * d1, CY + math.sin(a) * d1), 2)
        if prog > 0.65:
            fx = pygame.Surface((W, H), pygame.SRCALPHA)
            fx.fill((220, 230, 255, int((prog - 0.65) / 0.35 * 235)))
            scr.blit(fx, (0, 0))

    def draw_travel(self, scr, fonts):
        tr = self.g.travel
        prog = tr["t"] / tr["dur"]
        k = math.sin(math.pi * min(1, prog))
        to = SITES[tr["to"]]
        scr.set_clip(pygame.Rect(0, 0, PANEL.x - 14, H))
        for a, sp in self.streaks:
            d0 = 40 + k * sp * 380
            d1 = d0 + 20 + k * 220 * sp
            v = int(230 * k)
            pygame.draw.line(scr, (v // 2 + 20, v // 2 + 40, v), (CX + math.cos(a) * d0, CY + math.sin(a) * d0),
                             (CX + math.cos(a) * d1, CY + math.sin(a) * d1), 2)
        fx = pygame.Surface((PANEL.x, H), pygame.SRCALPHA)
        fx.fill((190, 210, 255, int(k * 70)))
        scr.blit(fx, (0, 0))
        self.txt(scr, fonts[0], f"Travelling to {to['name']}", (CX, CY - 130), (255, 255, 255), "midtop", True)
        pygame.draw.rect(scr, (30, 36, 70), (CX - 130, CY - 86, 260, 6), border_radius=3)
        pygame.draw.rect(scr, to["col"], (CX - 130, CY - 86, 260 * prog, 6), border_radius=3)
        scr.set_clip(None)

    def draw_toasts(self, scr, sm):
        y = H - 62 - (frontview.BAR if self.view == "galaxy" else 0)
        maxw = 610
        for msg, secs in reversed(self.g.toasts):
            if sm.size(msg)[0] > maxw:                      # fit long messages with an ellipsis
                while msg and sm.size(msg + "...")[0] > maxw:
                    msg = msg[:-1]
                msg = msg.rstrip() + "..."
            img = sm.render(msg, True, (255, 245, 210))
            r = img.get_rect(midbottom=(CX, y)).inflate(28, 12)
            bg = pygame.Surface(r.size, pygame.SRCALPHA)
            a = int(min(1, secs) * 225)
            pygame.draw.rect(bg, (16, 18, 38, a), bg.get_rect(), border_radius=10)
            pygame.draw.rect(bg, (255, 215, 110, a), bg.get_rect(), 1, border_radius=10)
            scr.blit(bg, r)
            img.set_alpha(int(min(1, secs) * 255))
            scr.blit(img, img.get_rect(center=r.center))
            y -= 38

    # ---------------- HUD & strip -----------------
    def next_goal(self):
        g = self.g
        k = next((i for i in range(1, NSITE) if not g.unlocked[i]), None)
        if k is None:
            return None
        ores, cr = g.unlock_cost(k)
        fr = [min(1.0, g.ore[p] / amt) for p, amt in ores if amt > 0]
        if cr > 0:
            fr.append(min(1.0, g.credits / cr))
        return k, (min(fr) if fr else 1.0)

    def draw_hud_galaxy(self, scr, fonts):
        """The galaxy screen keeps only a slim bar of numbers, so the map can use the rest of the window."""
        big, med, sm, tiny = fonts
        g = self.g
        self.txt(scr, med, "GALAXY MAP", (22, 10), (200, 215, 255), shadow=True)
        x = 22 + med.size("GALAXY MAP")[0] + 28
        t = f"{fmt(g.credits)} credits (+{fmt(g.cred_ops)}/s)"
        self.txt(scr, sm, t, (x, 13), (255, 218, 120), shadow=True)
        x += sm.size(t)[0] + 24
        self.txt(scr, sm, f"{fmt(g.science)} science (+{fmt(g.sci_ops)}/s)", (x, 13), (125, 238, 255), shadow=True)
        wars = len(g.war)
        self.txt(scr, tiny, f"Fleet power {fmt(g.fleet_power())}   -   {len(g.conquered) - 1:,} systems held   -   range {galaxy.fmt_ly(g.jump_range())}   -   "
                 + ("at peace" if not wars else f"at war with {wars} faction{'s' if wars > 1 else ''}"),
                 (22, 40), (170, 180, 215), shadow=True)
        if g.campaigns and not self.panel_visible():        # (with the panel open its Fronts card shows the same)
            right = frontview.VIEW.right
            self.txt(scr, tiny, f"Fronts {len(g.campaigns)}/{g.max_fronts()}  -  {g.free_share() * 100:.0f}% of the fleet at home",
                     (right, 8), (255, 175, 150), "topright", True)
            shown = sorted(g.campaigns, key=lambda c: c["dur"] - c["t"])[:3]
            bw = 142
            for i, c in enumerate(shown):                   # the next three to arrive
                x = right - (len(shown) - i) * (bw + 16) + 16
                self.txt(scr, tiny, f"{SECTORS[c['k']]['name']} {c['chance'] * 100:.0f}% {fmt_time(max(0, c['dur'] - c['t']))}",
                         (x, 26), (255, 205, 190), shadow=True)
                pygame.draw.rect(scr, (40, 24, 28), (x, 44, bw, 5), border_radius=3)
                pygame.draw.rect(scr, (255, 120, 100), (x, 44, bw * c["t"] / c["dur"], 5), border_radius=3)

    def draw_hud(self, scr, fonts):
        if self.view == "galaxy":
            self.draw_hud_galaxy(scr, fonts)
            return
        big, med, sm, tiny = fonts
        g = self.g
        p = g.cur
        site = SITES[p]
        oc = site["ocol"]
        if g.cycle > 1:
            self.txt(scr, tiny, f"CYCLE {g.cycle}", (22, 2), (255, 215, 120), shadow=True)
        self.txt(scr, med, f"{site['name'].upper()}", (22, 12), site["col"], shadow=True)
        self.txt(scr, tiny, f"mining {site['ore']}", (22 + med.size(site['name'].upper())[0] + 10, 18), (170, 175, 200), shadow=True)
        self.txt(scr, big, fmt(g.ore[p], 2), (20, 32), (255, 255, 255), shadow=True)
        self.txt(scr, med, f"{fmt(g.s_ops[p], 2)} {site['ore']}/s", (22, 74), lerp_c(oc, (255, 255, 255), 0.35), shadow=True)
        self.txt(scr, sm, f"Click: +{fmt(g.s_click[p])}", (22, 100), (205, 205, 220), shadow=True)
        extra = f"Bonus x{g.G:.2f}" if g.G < 1e4 else f"Bonus x{fmt(g.G, 2)}"
        if g.dm:
            extra += f"   Dark Matter: {g.dm_avail()}/{g.dm}"
        if g.sd_total:
            extra += f"   Stardust: {g.stardust}"
        self.txt(scr, sm, extra, (22, 120), (215, 175, 255), shadow=True)
        y = 144
        if g.cred_ops > 0 or g.credits > 0:
            self.txt(scr, med, f"{fmt(g.credits)} credits  (+{fmt(g.cred_ops)}/s)", (22, y), (255, 218, 120), shadow=True)
            y += 24
        if g.sci_ops > 0 or g.science > 0:
            self.txt(scr, med, f"{fmt(g.science)} science  (+{fmt(g.sci_ops)}/s)", (22, y), (125, 238, 255), shadow=True)
            y += 24
        goal = self.next_goal()
        if goal:
            k, fr = goal
            self.txt(scr, tiny, f"Next planet: {SITES[k]['name']}", (22, y + 2), (190, 196, 220), shadow=True)
            pygame.draw.rect(scr, (24, 28, 56), (22, y + 20, 150, 6), border_radius=3)
            pygame.draw.rect(scr, SITES[k]["col"], (22, y + 20, 150 * fr, 6), border_radius=3)
            y += 34
        for c in sorted(g.campaigns, key=lambda c: c["dur"] - c["t"])[:2]:
            self.txt(scr, tiny, f"Campaign: {SECTORS[c['k']]['name']}  {c['chance'] * 100:.0f}%  "
                     f"({fmt_time(max(0, c['dur'] - c['t']))} left)", (22, y + 2), (255, 175, 150), shadow=True)
            pygame.draw.rect(scr, (40, 24, 28), (22, y + 20, 150, 6), border_radius=3)
            pygame.draw.rect(scr, (255, 120, 100), (22, y + 20, 150 * c["t"] / c["dur"], 6), border_radius=3)
            y += 34
        if len(g.campaigns) > 2:
            self.txt(scr, tiny, f"+{len(g.campaigns) - 2} more fronts", (22, y + 2), (255, 175, 150), shadow=True)
            y += 20
        if director.intel(g) >= 1 and self.view != "galaxy":       # the galaxy view shows incoming fleets itself
            for inc in g.incoming[:2]:
                left = max(0, inc["eta"] - inc["t"])
                blink = 0.6 + 0.4 * math.sin(self.t * 6)
                name = "Counter-offensive" if inc["kind"] == "offensive" else director.TIERS[inc["tier"]]["name"]
                where = ""
                if director.intel(g) >= 2:
                    where = f" -> {SECTORS[inc['target']]['name']}" if inc["kind"] == "offensive" else " -> " + ", ".join(
                        SITES[q]["name"] for q in inc["targets"])
                self.txt(scr, tiny, f"INCOMING: {name}{where}  ({fmt_time(left)})", (22, y + 2), scale_c((255, 120, 110), blink),
                         shadow=True)
                y += 18
        yb = 84
        for b in g.buffs:
            self.txt(scr, sm, f"{b['name']} x{b['mult']:g}  {b['t']:.0f}s", (PANEL.x - 20, yb), (255, 222, 90), "topright", True)
            frac = b["t"] / b["dur"]
            pygame.draw.rect(scr, (40, 34, 12), (PANEL.x - 170, yb + 21, 150, 5), border_radius=2)
            pygame.draw.rect(scr, (255, 200, 60), (PANEL.x - 20 - 150 * frac, yb + 21, 150 * frac, 5), border_radius=2)
            yb += 34

    def draw_dev_badge(self, scr, fonts):
        tiny = fonts[3]
        d = self.dev_state
        self.txt(scr, tiny, "DEV MODE", (PANEL.x - 22, 3), (255, 110, 110), "topright", True)
        if d.fps:
            self.txt(scr, tiny, f"{self.fps:.0f} FPS", (PANEL.x - 22, 18), (255, 220, 140), "topright", True)
        if d.speed != 1:
            self.txt(scr, tiny, f"speed x{d.speed}", (PANEL.x - 22, 33), (255, 220, 140), "topright", True)
        if d.god:
            self.txt(scr, tiny, "GOD MODE", (PANEL.x - 22, 48), (255, 140, 140), "topright", True)
        if d.infinite:
            self.txt(scr, tiny, "INFINITE RESOURCES", (PANEL.x - 22, 63), (255, 140, 140), "topright", True)

    def draw_strip(self, scr, fonts):
        big, med, sm, tiny = fonts
        g = self.g
        self.strip_hits = []
        n = NSITE
        x0 = STRIP_X0
        pygame.draw.line(scr, (34, 40, 78), (x0, STRIP_Y), (x0 + (n - 1) * STRIP_DX, STRIP_Y), 2)
        nxt = next((i for i in range(1, NSITE) if not g.unlocked[i]), None)
        hover = None
        # galaxy map button
        gx = 44
        grect = pygame.Rect(gx - 19, STRIP_Y - 19, 38, 38)
        self.strip_hits.append((grect, -1))
        opened = g.galaxy_open
        active = self.view == "galaxy"
        col = (255, 215, 110) if active else ((130, 170, 255) if opened else (70, 76, 110))
        if opened:
            scr.blit(glow(26, scale_c(col, 0.5 if active else 0.3)), (gx - 26, STRIP_Y - 26), special_flags=ADD)
        pygame.draw.circle(scr, (14, 18, 40), (gx, STRIP_Y), 19)
        pygame.draw.circle(scr, col, (gx, STRIP_Y), 19, 2)
        for arm in range(2):
            pts = []
            for i in range(14):
                t = i / 13
                ang = arm * math.pi + t * 3.6 + (self.t * 0.6 if opened else 0)
                pts.append((gx + math.cos(ang) * (2 + 13 * t), STRIP_Y + math.sin(ang) * (2 + 13 * t)))
            pygame.draw.lines(scr, col, False, pts, 2)
        if opened and g.attack_ready():
            scr.blit(glow(8, (255, 200, 60)), (gx + 8, STRIP_Y - 24), special_flags=ADD)
            pygame.draw.circle(scr, (255, 220, 90), (gx + 15, STRIP_Y - 15), 3)
        if grect.collidepoint(self.mouse) and self.mouse[0] < PANEL.x - 10:
            hover = -1
        for k in range(n):
            x = x0 + k * STRIP_DX
            rect = pygame.Rect(x - 19, STRIP_Y - 19, 38, 38)
            self.strip_hits.append((rect, k))
            site = SITES[k]
            if g.unlocked[k]:
                if k == g.cur and self.view == "system":
                    scr.blit(glow(30, scale_c(site["col"], 0.8)), (x - 30, STRIP_Y - 30), special_flags=ADD)
                    pygame.draw.circle(scr, (255, 215, 110), (x, STRIP_Y), 20, 2)
                ic = self.strip_icons[k]
                scr.blit(ic, ic.get_rect(center=(x, STRIP_Y)))
                if site["kind"] == "saturn":
                    pygame.draw.ellipse(scr, (214, 194, 150), (x - 22, STRIP_Y - 6, 44, 12), 1)
            else:
                ic = self.strip_dark[k]
                scr.blit(ic, ic.get_rect(center=(x, STRIP_Y)))
                if k == nxt:
                    can = g.can_unlock(k)
                    colr = (255, 215, 110) if can else (90, 100, 150)
                    pygame.draw.circle(scr, colr, (x, STRIP_Y), 20, 1)
                    if can:
                        scr.blit(glow(26, scale_c((255, 200, 60), 0.5 + 0.4 * math.sin(self.t * 5))), (x - 26, STRIP_Y - 26),
                                 special_flags=ADD)
                    self.txt(scr, tiny, "?", (x, STRIP_Y), (160, 168, 210), "center")
            if rect.collidepoint(self.mouse) and self.mouse[0] < PANEL.x - 10:
                hover = k
        if hover is not None:
            self.draw_tooltip(scr, fonts, hover)

    def draw_tooltip(self, scr, fonts, k):
        big, med, sm, tiny = fonts
        g = self.g
        lines = []
        if k < 0:
            if g.galaxy_open:
                lines.append(("Galaxy map", (130, 170, 255)))
                lines.append((f"Fleet power {fmt(g.fleet_power())}   {len(g.conquered) - 1:,} systems held", (225, 225, 240)))
                lines.append(("Click to " + ("return to the solar system" if self.view == "galaxy" else "open the map"),
                              (255, 215, 110)))
            else:
                lines.append(("Galaxy map  (locked)", (120, 128, 170)))
                lines.append(("Unlock Mars to open it", (170, 175, 205)))
        site = SITES[k] if k >= 0 else SITES[0]
        if k < 0:
            pass
        elif g.unlocked[k]:
            lines.append((f"{site['name']}  -  {site['ore']}", site["col"]))
            lines.append((f"{fmt(g.ore[k])} stock   +{fmt(g.s_ops[k])}/s", (225, 225, 240)))
            lines.append((site["perk"], (170, 175, 205)))
            lines.append(("You are here" if k == g.cur else "Click to travel", (255, 215, 110)))
        elif k == next((i for i in range(1, NSITE) if not g.unlocked[i]), None):
            lines.append((f"{site['name']}  -  {site['ore']}   (locked)", site["col"]))
            ores, cr = g.unlock_cost(k)
            for p, amt in ores:
                if amt > 0:
                    ok = g.ore[p] >= amt
                    lines.append((f"{fmt(amt)} {SITES[p]['ore']}  (have {fmt(g.ore[p])})", (130, 255, 150) if ok else (230, 130, 130)))
            if cr > 0:
                lines.append((f"{fmt(cr)} credits  (have {fmt(g.credits)})", (130, 255, 150) if g.credits >= cr else (230, 130, 130)))
            lines.append((site["perk"], (170, 175, 205)))
        else:
            lines.append(("???  (locked)", (140, 146, 180)))
        w = max(sm.size(t)[0] for t, _ in lines) + 24
        h = len(lines) * 20 + 14
        cx = 44 if k < 0 else STRIP_X0 + k * STRIP_DX
        x = max(8, min(cx - w // 2, PANEL.x - 20 - w))
        r = pygame.Rect(x, STRIP_Y - 44 - h, w, h)
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (14, 16, 36, 235), bg.get_rect(), border_radius=8)
        pygame.draw.rect(bg, (110, 130, 195, 255), bg.get_rect(), 1, border_radius=8)
        scr.blit(bg, r)
        for i, (t, col) in enumerate(lines):
            self.txt(scr, sm, t, (r.x + 12, r.y + 8 + i * 20), col)

    # ---------------- panel -----------------
    def button(self, scr, rect, label, font, fn, enabled=True, col=(50, 70, 110), modal=False, dot=False,
               panel=False, selected=False, danger=False):
        if danger and not selected:
            col = (110, 40, 50)
        hot = enabled and rect.collidepoint(self.mouse) and (not panel or PANEL.collidepoint(self.mouse))
        c = tuple(min(255, v + 28) for v in col) if hot else col
        if not enabled:
            c = (38, 40, 52)
        pygame.draw.rect(scr, c, rect, border_radius=7)
        pygame.draw.rect(scr, scale_c(c, 1.5), (rect.x + 2, rect.y + 1, rect.w - 4, 2), border_radius=1)
        pygame.draw.rect(scr, (120, 140, 195) if enabled else (62, 64, 80), rect, 1, border_radius=7)
        if selected:
            pygame.draw.rect(scr, (255, 215, 110), (rect.x + 6, rect.bottom - 3, rect.w - 12, 2))
        self.txt(scr, font, label, rect.center, (242, 242, 252) if enabled else (120, 120, 135), "center")
        if dot:
            scr.blit(glow(8, (255, 200, 60)), (rect.right - 15, rect.y - 1), special_flags=ADD)
            pygame.draw.circle(scr, (255, 220, 90), (rect.right - 7, rect.y + 7), 3)
        if enabled and fn:
            if panel:
                self.add_btn(rect, fn)
            else:
                (self.modal_buttons if modal else self.buttons).append((rect, fn))

    def add_btn(self, rect, fn):
        r = rect.clip(PANEL)
        if r.w > 0 and r.h > 0:
            self.buttons.append((r, fn))

    def row(self, scr, fonts, rect, title, sub, rt, rb, ok, col, fn, frac=None, tcol=(245, 245, 250),
            dim=False, icon=None, glyph=None, lines=None):
        big, med, sm, tiny = fonts
        if not rect.colliderect(PANEL):
            return
        hover = fn is not None and rect.collidepoint(self.mouse) and PANEL.collidepoint(self.mouse)
        bg = (40, 56, 74) if ok else (28, 31, 52)
        if hover:
            bg = tuple(min(255, v + 14) for v in bg)
        pygame.draw.rect(scr, bg, rect, border_radius=9)
        pygame.draw.rect(scr, scale_c(bg, 1.35), (rect.x + 3, rect.y + 1, rect.w - 6, 2), border_radius=1)
        pygame.draw.rect(scr, col if ok else (62, 66, 92), rect, 1, border_radius=9)
        pygame.draw.rect(scr, col if ok else (62, 66, 92), (rect.x, rect.y + 8, 4, rect.h - 16), border_radius=2)
        tx = rect.x + 14
        cy = rect.centery - (3 if frac is not None else 0)
        if icon is not None:
            scr.blit(icon, icon.get_rect(center=(rect.x + 36, cy)))
            tx = rect.x + 66
        elif glyph is not None:
            gc = col if ok else (80, 84, 112)
            scr.blit(glow(22, scale_c(gc, 0.45)), (rect.x + 14, cy - 22), special_flags=ADD)
            pygame.draw.circle(scr, scale_c(gc, 0.35), (rect.x + 36, cy), 16)
            pygame.draw.circle(scr, gc, (rect.x + 36, cy), 16, 2)
            self.txt(scr, med, glyph, (rect.x + 36, cy), (255, 255, 255) if ok else (130, 134, 160), "center")
            tx = rect.x + 66
        self.txt(scr, med, title, (tx, rect.y + 6), (125, 130, 156) if dim else tcol)
        if sub:
            self.txt(scr, tiny, sub, (tx, rect.y + 30), (92, 98, 124) if dim else (156, 166, 196))
        if lines:
            for i, (t, c) in enumerate(lines):
                self.txt(scr, tiny, t, (tx, rect.y + (48 if sub else 30) + i * 15), c)
        if rt:
            self.txt(scr, sm, rt, (rect.right - 12, rect.y + 8), (130, 255, 150) if ok else (205, 120, 120), "topright")
        if rb:
            self.txt(scr, tiny, rb, (rect.right - 12, rect.bottom - 8), (175, 180, 205), "bottomright")
        if frac is not None:
            bar = pygame.Rect(tx, rect.bottom - 11, rect.right - 12 - tx, 5)
            pygame.draw.rect(scr, (16, 18, 32), bar, border_radius=2)
            w = max(0, int(bar.w * min(1, frac)))
            if w:
                pygame.draw.rect(scr, col, (bar.x, bar.y, w, bar.h), border_radius=2)
        if fn:
            self.add_btn(rect, fn)

    def tab_alert(self, k):
        g = self.g
        p = g.cur
        if k == T_UPG:
            return any(g.ore[p] >= u["cost"] * SC[p] for u in g.avail_upgrades(p))
        if k == T_COLONY:
            return g.can_buy_project(p)
        if k == T_PLANETS:
            return any(g.can_unlock(i) for i in range(1, NSITE))
        if k == T_GALAXY:
            return g.attack_ready()
        if k == T_TECH:
            return any(t[0] not in g.techs and all(q in g.techs for q in t[3]) and g.science >= g.tech_cost(t[0]) for t in TECHS)
        if k == T_QUESTS:
            return any(g.quest_prog(q) >= q["tgt"] for q in g.quests)
        if k == T_WARP:
            return (g.warp_gain() >= 1 or any(pk[0] not in g.perks and g.dm_avail() >= pk[2] for pk in PERKS)
                    or g.can_ascend() or any(pk[0] not in g.sd_perks and g.stardust >= pk[2] for pk in STARDUST_PERKS))
        if k == T_AWARDS:
            return self.ach_new
        return False

    def draw_panel(self, scr, fonts):
        big, med, sm, tiny = fonts
        g = self.g
        scr.blit(self.panel_bg, (PANEL.x - 12, 4))
        tw = PANEL.w // len(self.tabs)
        for k, n in enumerate(self.tabs):
            r = pygame.Rect(PANEL.x + k * tw, 14, tw - 4, 30)
            self.button(scr, r, n, tiny if sm.size(n)[0] > tw - 10 else sm, (lambda k=k: self.set_tab(k)),
                        col=(78, 100, 176) if self.tab == k else (34, 42, 74), dot=self.tab != k and self.tab_alert(k),
                        selected=self.tab == k, danger=(n == "Dev"))
        if self.tab in (T_SHIPS, T_COLONY):
            self.txt(scr, tiny, "Buy:", (PANEL.x + 2, 70), (170, 175, 200))
            for k, (lab, m) in enumerate([("x1", 1), ("x10", 10), ("x100", 100), ("Max", 0)]):
                r = pygame.Rect(PANEL.x + 40 + k * 62, 58, 56, 26)
                self.button(scr, r, lab, sm, (lambda m=m: setattr(g, "buy_mode", m)),
                            col=(66, 128, 92) if g.buy_mode == m else (34, 42, 74))
        site = SITES[g.cur]
        if self.tab in (T_SHIPS, T_UPG, T_COLONY):
            self.txt(scr, tiny, f"{site['name']}  -  paid in {site['ore']}", (PANEL.right, 70), site["col"], "topright")
        pygame.draw.line(scr, (50, 58, 100), (PANEL.x, PANEL.y - 7), (PANEL.right, PANEL.y - 7))
        if self.tab == T_AWARDS:
            self.ach_new = False
        scr.set_clip(PANEL)
        sy = PANEL.y - self.scroll[self.tab]
        end = [self.draw_ships, self.draw_upgrades, self.draw_colony, self.draw_planets, self.draw_galaxy_tab,
               self.draw_tech, self.draw_quests, self.draw_warp, self.draw_awards, self.draw_dev][self.tab](scr, fonts, sy)
        scr.set_clip(None)
        self.content_h = end - sy
        maxs = max(0, self.content_h - PANEL.h)
        self.scroll[self.tab] = max(0, min(maxs, self.scroll[self.tab]))
        if maxs > 0:
            frac = PANEL.h / self.content_h
            top = PANEL.y + (PANEL.h - PANEL.h * frac) * (self.scroll[self.tab] / maxs)
            pygame.draw.rect(scr, (90, 104, 170), (PANEL.right + 3, top, 4, PANEL.h * frac), border_radius=2)

    def draw_ships(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        p = g.cur
        shown = max([i for i, o in enumerate(g.owned[p]) if o > 0], default=-1) + 2
        for i, (name, base, rate, col) in enumerate(SHIPS):
            r = pygame.Rect(PANEL.x, y, PANEL.w, 62)
            y += 68
            if i >= shown:
                if i == shown and r.colliderect(PANEL):
                    pygame.draw.rect(scr, (22, 24, 42), r, border_radius=9)
                    dark = self.ship_icon(p, i).copy()
                    dark.fill((22, 26, 40, 255), special_flags=pygame.BLEND_RGBA_MULT)
                    scr.blit(dark, dark.get_rect(center=(r.x + 36, r.centery)))
                    self.txt(scr, med, "???", (r.x + 66, r.y + 18), (90, 95, 120))
                continue
            n = g.ship_count(p, i)
            cost = g.ship_cost(p, i, n)
            ok = g.ore[p] >= cost
            per = rate * SC[p] * g.s_gm[p][i] * g.G
            self.row(scr, fonts, r, ships.name(p, i), f"{fmt(per, 2)} {SITES[p]['ore']}/s each  -  {ships.blurb(p, i)}", None, None, ok,
                     col, lambda i=i: g.buy_ship(p, i), icon=self.ship_icon(p, i))
            if r.colliderect(PANEL):
                self.txt(scr, big, str(g.owned[p][i]), (r.right - 12, r.y + 0), (255, 255, 255), "topright")
                self.txt(scr, sm, f"x{n}: {fmt(cost)}", (r.right - 12, r.bottom - 8),
                         (130, 255, 150) if ok else (205, 120, 120), "bottomright")
        return y

    def draw_upgrades(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        p = g.cur
        ups = g.avail_upgrades(p)
        r = pygame.Rect(PANEL.x, y, PANEL.w, 34)
        affordable = sum(1 for u in ups if g.ore[p] >= u["cost"] * SC[p])
        if r.colliderect(PANEL):
            self.button(scr, r, f"Buy everything affordable  ({affordable})", sm,
                        (lambda: g.buy_all_upgrades(p)), enabled=affordable > 0, panel=True, col=(70, 110, 90))
        y += 42
        if not ups:
            self.txt(scr, sm, "No upgrades yet - buy more ships!", (PANEL.x + 10, y + 6), (150, 155, 180))
            return y + 40
        self.txt(scr, tiny, f"{len(g.ups[p])}/{len(UPGRADES)} bought on {SITES[p]['name']} this run", (PANEL.x + 4, y),
                 (150, 155, 180))
        y += 20
        glyphs = {"click": "C", "clickops": "R", "global": "*"}
        for u in ups:
            r = pygame.Rect(PANEL.x, y, PANEL.w, 62)
            y += 68
            cost = u["cost"] * SC[p]
            ok = g.ore[p] >= cost
            kw = dict(icon=self.ship_icon(p, u["arg"][0])) if u["kind"] == "gen" else dict(glyph=glyphs[u["kind"]])
            uname, udesc = core.upgrade_text(u, p)
            self.row(scr, fonts, r, uname, udesc, fmt(cost), None, ok, (200, 160, 255),
                     lambda uid=u["id"]: g.buy_upgrade(p, uid), **kw)
        return y

    def draw_colony(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        p = g.cur
        bonus = SITES[p]["bonus"]
        bn = "all buildings x1.5" if bonus == -1 else f"{BUILDINGS[bonus][0]} x2"
        self.txt(scr, tiny, f"{SITES[p]['name']} colony  -  planet bonus: {bn}", (PANEL.x + 4, y), SITES[p]["col"])
        y += 22
        for b, (name, res, base, desc, bcol) in enumerate(BUILDINGS):
            r = pygame.Rect(PANEL.x, y, PANEL.w, 58)
            y += 64
            L = g.bld[p][b]
            f = 2.0 if bonus == b else (1.5 if bonus == -1 else 1.0)
            if L >= BMAX:
                self.row(scr, fonts, r, f"{name}  Lv {L} (MAX)", desc, None, None, True, (255, 220, 100), None, glyph=name[0])
                continue
            n = g.bld_count(p, b)
            cost = g.bld_total_cost(p, b, n)
            ok = g.have_for(p, b) >= cost
            unit = SITES[p]["ore"] if res == "ore" else res
            self.row(scr, fonts, r, f"{name}  Lv {L}", f"{desc}  {self.bld_output(p, b, L, f)}",
                     f"x{n}: {fmt(cost)} {unit}", None, ok, bcol, (lambda b=b: g.buy_building(p, b)), glyph=name[0])
        y += 10
        self.txt(scr, med, "Megaproject", (PANEL.x + 4, y), (255, 225, 140))
        y += 28
        name, desc, _ = PROJECTS[p]
        r = pygame.Rect(PANEL.x, y, PANEL.w, 104)
        y += 112
        if p in g.projects:
            self.row(scr, fonts, r, name, desc, "BUILT", None, True, (255, 220, 100), None, tcol=(255, 225, 140), glyph="W")
        else:
            ore, cr, sci = g.project_cost(p)
            ok_o, ok_c, ok_s = g.ore[p] >= ore, g.credits >= cr, g.science >= sci
            good, bad = (130, 255, 150), (230, 130, 130)
            lines = [(f"{fmt(ore)} {SITES[p]['ore']}  (have {fmt(g.ore[p])})", good if ok_o else bad),
                     (f"{fmt(cr)} credits  (have {fmt(g.credits)})", good if ok_c else bad),
                     (f"{fmt(sci)} science  (have {fmt(g.science)})", good if ok_s else bad)]
            self.row(scr, fonts, r, name, desc, "BUILD", None, ok_o and ok_c and ok_s, (255, 215, 90),
                     (lambda: g.buy_project(p)), glyph="W", lines=lines)
        return y

    def bld_output(self, p, b, L, f):
        E = self.g.E
        if b == 0:
            return f"(now +{L * 3 * f * E['minebonus']:.0f}%)"
        if b == 1:
            return f"(now {fmt(0.5 * L * f * core.CSC[p] * E['cred'])}/s)"
        if b == 2:
            return f"(now {fmt(0.15 * L * f * core.CSC[p] * E['sci'])}/s)"
        if b == 3:
            return f"(now -{0.6 * L * f:.1f}%)"
        if b == 4:
            return f"(now +{2.5 * L * f:.1f}%)"
        return f"(now +{4 * L * f:.0f}%)"

    def draw_planets(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        nxt = next((i for i in range(1, NSITE) if not g.unlocked[i]), None)
        for i, line in enumerate(["Unlock planets with the ores of the worlds behind you. Every planet has its",
                                  "own ore, fleet, colony and a bonus. Travel by clicking a planet below or at the bottom."]):
            self.txt(scr, tiny, line, (PANEL.x + 4, y + i * 15), (150, 160, 190))
        y += 38
        good, bad = (130, 255, 150), (230, 130, 130)
        for k, site in enumerate(SITES):
            if g.unlocked[k]:
                r = pygame.Rect(PANEL.x, y, PANEL.w, 96)
                y += 102
                here = k == g.cur
                lines = [(f"{fmt(g.ore[k])} {site['ore']} stored   (+{fmt(g.s_ops[k])}/s)", (205, 210, 230)),
                         (f"Colony levels: {sum(g.bld[k])}   Megaproject: {'built' if k in g.projects else 'not built'}",
                          (160, 168, 198))]
                self.row(scr, fonts, r, f"{site['name']}  -  {site['ore']}", site["perk"],
                         "YOU ARE HERE" if here else "TRAVEL", None, True, site["col"],
                         None if here else (lambda k=k: g.start_travel(k)), tcol=site["col"],
                         icon=self.planet_icons[k], lines=lines)
            elif k == nxt:
                ores, cr = g.unlock_cost(k)
                lines = []
                for pp, amt in ores:
                    if amt > 0:
                        lines.append((f"{fmt(amt)} {SITES[pp]['ore']}   (have {fmt(g.ore[pp])})", good if g.ore[pp] >= amt else bad))
                if cr > 0:
                    lines.append((f"{fmt(cr)} credits   (have {fmt(g.credits)})", good if g.credits >= cr else bad))
                r = pygame.Rect(PANEL.x, y, PANEL.w, 62 + 15 * len(lines))
                y += r.h + 6
                self.row(scr, fonts, r, f"{site['name']}  -  {site['ore']}", site["perk"], "UNLOCK", None,
                         g.can_unlock(k), site["col"], (lambda k=k: g.unlock_planet(k)), icon=self.planet_icons[k],
                         lines=lines)
            else:
                r = pygame.Rect(PANEL.x, y, PANEL.w, 62)
                y += 68
                self.row(scr, fonts, r, "???", "Unlock the planets before it first", None, None, False, (62, 66, 92),
                         None, dim=True, icon=self.planet_dark[k])
        return y

    def draw_tech(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        self.txt(scr, tiny, f"{len(g.techs)}/{len(TECHS)} researched (techs persist through Warp)  -  "
                 f"Science: {fmt(g.science)}  (+{fmt(g.sci_ops)}/s)" + (f"  -  tech costs x{g.E['techcost']:.2f}" if g.E['techcost'] < 1 else ""),
                 (PANEL.x + 4, y), (150, 160, 190))
        y += 20
        order = sorted(TECHS, key=lambda t: (t[0] in g.techs, not all(q in g.techs for q in t[3]), t[2]))
        for t in order:
            tid, name, _, pre, desc, _fx = t
            cost = g.tech_cost(tid)
            r = pygame.Rect(PANEL.x, y, PANEL.w, 64)
            y += 70
            if tid in g.techs:
                self.row(scr, fonts, r, name, desc, "DONE", None, True, (255, 220, 100), None, tcol=(255, 225, 140), glyph="v")
                continue
            unlocked = all(q in g.techs for q in pre)
            ok = unlocked and g.science >= cost
            sub = desc if unlocked else "Requires: " + ", ".join(TECH_BY_ID[q][1] for q in pre if q not in g.techs)
            self.row(scr, fonts, r, name, sub, fmt(cost) + " sci", None, ok, (120, 235, 255),
                     (lambda tid=tid: g.research(tid)) if unlocked else None, dim=not unlocked,
                     frac=(g.science / cost) if unlocked else None, glyph="T" if unlocked else "#")
        return y

    def draw_quests(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        self.txt(scr, tiny, f"Quests completed: {g.quests_done}   -   claim rewards when the bar is full",
                 (PANEL.x + 4, y), (150, 160, 190))
        y += 22
        for idx, q in enumerate(g.quests):
            r = pygame.Rect(PANEL.x, y, PANEL.w, 84)
            y += 92
            prog = g.quest_prog(q)
            done = prog >= q["tgt"]
            title = QUEST_TXT[q["k"]].format(fmt(q["tgt"]))
            site = SITES[q.get("site", 0)]
            if q["r"] == "ore":
                rew = f"{fmt(q['amt'])} {site['ore']}"
            elif q["r"] == "frenzy":
                rew = f"{q['amt']:.0f}s Mining Frenzy"
            else:
                rew = f"{fmt(q['amt'])} {q['r']}"
            self.row(scr, fonts, r, title, f"Reward: {rew}", "CLAIM!" if done else f"{fmt(prog)}/{fmt(q['tgt'])}",
                     None, done, (255, 215, 90), (lambda idx=idx: g.claim_quest(idx)) if done else None,
                     frac=prog / q["tgt"], glyph="!")
        return y

    def draw_warp(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        self.button(scr, pygame.Rect(PANEL.x, y, 292, 32), "Warp & Dark Matter", sm,
                    lambda: setattr(self, "warp_view", "warp"), panel=True,
                    col=(78, 100, 176) if self.warp_view == "warp" else (34, 42, 74), selected=self.warp_view == "warp")
        self.button(scr, pygame.Rect(PANEL.x + 302, y, 292, 32), "Ascension (New Game+)", sm,
                    lambda: setattr(self, "warp_view", "ascend"), panel=True,
                    col=(150, 110, 40) if self.warp_view == "ascend" else (60, 46, 30),
                    selected=self.warp_view == "ascend", dot=g.can_ascend() and self.warp_view != "ascend")
        y += 44
        if self.warp_view == "ascend":
            return self.draw_ascension(scr, fonts, y)
        x = PANEL.x + 8
        self.txt(scr, big, "Warp Drive", (x, y))
        lines = ["Warp resets ore, ships and upgrades on EVERY planet. You keep your",
                 "unlocked planets, colonies, megaprojects, tech, credits, science",
                 "and Dark Matter. Dark Matter total = (ore mined this cycle / 1B) ^ 0.25.",
                 "Dark Matter gives a permanent production bonus (1 + 0.4 x sqrt(DM)) and can be",
                 "spent on perks below."]
        for k, l in enumerate(lines):
            self.txt(scr, tiny, l, (x, y + 42 + k * 17), (175, 180, 205))
        y += 134
        gain = g.warp_gain()
        self.txt(scr, med, f"Dark Matter: {g.dm_avail()} to spend ({g.dm} total, bonus x{core.dm_bonus(g.dm, g.E['dmbase']):.2f})",
                 (x, y), (210, 170, 255))
        self.txt(scr, med, f"Ore mined this cycle (Earth-equiv.): {fmt(g.cyc_norm)}", (x, y + 26))
        self.txt(scr, med, f"Warp now for: +{gain} DM", (x, y + 52), (130, 255, 150) if gain else (180, 120, 120))
        need = ((g.dm + gain + 1) / g.E["dm"]) ** (1 / core.DM_POW) * core.DM_DIV
        self.txt(scr, tiny, f"Next Dark Matter at {fmt(need)} ore   -   warps so far: {g.warps}", (x, y + 80), (150, 155, 180))
        r = pygame.Rect(x, y + 102, PANEL.w - 16, 50)
        label = "CLICK AGAIN TO CONFIRM WARP" if self.warp_confirm > 0 else "WARP!"
        self.button(scr, r, label, med, self.do_warp, enabled=gain >= 1, panel=True,
                    col=(150, 60, 70) if self.warp_confirm > 0 else (70, 80, 170))
        y += 170
        self.txt(scr, med, "Dark Matter Perks", (x, y), (230, 200, 255))
        y += 30
        for pk in PERKS:
            pid, name, cost, desc, _ = pk
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 58)
            y += 64
            if pid in g.perks:
                self.row(scr, fonts, rr, name, desc, "OWNED", None, True, (255, 220, 100), None, tcol=(255, 225, 140), glyph="D")
            else:
                self.row(scr, fonts, rr, name, desc, f"{fmt(cost)} DM", None, g.dm_avail() >= cost, (210, 170, 255),
                         lambda pid=pid: g.buy_perk(pid), glyph="D")
        return y

    # ---------------- galaxy -----------------
    def sector_color(self, k):
        fac = SECTORS[k]["faction"]
        return FACTIONS[fac]["col"] if fac else (255, 210, 120)

    def dashed(self, scr, col, p1, p2, width=2, dash=9, gap=7, offset=0.0):
        x1, y1 = p1
        x2, y2 = p2
        dist = math.hypot(x2 - x1, y2 - y1) or 1.0
        ux, uy = (x2 - x1) / dist, (y2 - y1) / dist
        d = -(offset % (dash + gap))
        while d < dist:
            a, b = max(0.0, d), min(dist, d + dash)
            if b > a:
                pygame.draw.line(scr, col, (x1 + ux * a, y1 + uy * a), (x1 + ux * b, y1 + uy * b), width)
            d += dash + gap

    def chance_color(self, ch):
        return (120, 255, 150) if ch >= 0.7 else ((255, 220, 110) if ch >= 0.4 else (255, 120, 110))

    def draw_raiders(self, scr):
        if not self.raiders:
            return
        for idx, r in enumerate(self.raiders):
            dx, dy = CX - r["x"], CY - r["y"]
            ang = math.degrees(math.atan2(-dy, dx))
            col = FACTIONS[r["fac"]]["col"]
            scr.blit(glow(12, scale_c(col, 0.5)), (r["x"] - 12, r["y"] - 12), special_flags=ADD)
            img = pygame.transform.rotate(self.enemy_big[r["fac"]], ang)
            scr.blit(img, img.get_rect(center=(r["x"], r["y"])))
            d = math.hypot(dx, dy) or 1.0
            if d < 300 and math.sin(self.t * 16 + idx * 1.7) > 0.2:      # your defences open fire
                ox, oy = CX - dx / d * 95, CY - dy / d * 95
                pygame.draw.line(scr, (255, 120, 90), (ox, oy), (r["x"], r["y"]), 3)
                pygame.draw.line(scr, (255, 245, 220), (ox, oy), (r["x"], r["y"]), 1)
        if any(not r["win"] for r in self.raiders):
            scr.blit(glow(80, (90, 20, 10)), (CX - 80, CY - 80), special_flags=ADD)

    GAL_MODES = ["Strongest you can beat", "Easiest", "Famous places"]

    def gal_list(self, mode):
        """Up to ten systems for the target browser of the Galaxy tab, by mode (cached for half a second)."""
        g = self.g
        key = (mode, g._targets_key, round(math.log10(max(g.fleet_power(), 1.0)) * 8))
        if self._gal_cache.get("key") == key and self.t - self._gal_cache["t"] < 0.5:
            return self._gal_cache["rows"]
        fp = g.fleet_power()
        tg = g.targets()
        if mode == 0:
            ok = [k for k in tg if win_chance(fp, g.sector_power(k)) >= 0.5]
            rows = sorted(ok, key=lambda k: -SECTORS[k]["lp"])[:10]
        elif mode == 1:
            rows = sorted(tg, key=lambda k: SECTORS[k]["lp"])[:10]
        else:
            rows = [k for k in galaxy.LANDMARK_IDS if k not in g.conquered][:10]
            rows = sorted(rows, key=lambda k: (k not in g.targets_set(), SECTORS[k]["d"]))[:10]
        self._gal_cache = dict(key=key, t=self.t, rows=rows)
        return rows

    def draw_galaxy_tab(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        if not g.galaxy_open:
            self.txt(scr, big, "The galaxy awaits", (PANEL.x + 8, y))
            for i, line in enumerate(["Unlock Mars to open the galaxy map: the real Milky Way, with thousands of star",
                                      "systems held by hostile factions. Liberate them with your fleet - you can jump",
                                      "to any system within range of one you hold - and claim permanent bonuses."]):
                self.txt(scr, sm, line, (PANEL.x + 8, y + 46 + i * 22), (170, 176, 205))
            return y + 140
        fp = g.fleet_power()
        self.txt(scr, med, f"Fleet power  {fmt(fp)}", (PANEL.x + 4, y), (255, 215, 140))
        self.txt(scr, sm, f"{len(g.conquered) - 1:,} systems held", (PANEL.right - 4, y + 2), (130, 255, 150), "topright")
        y += 26
        self.txt(scr, tiny, f"Battles {g.battles_won:,} won / {g.battles_lost:,} lost   -   Raids {g.raids_repelled} repelled / "
                 f"{g.raids_lost} lost   -   Press G to toggle the map", (PANEL.x + 4, y), (150, 158, 190))
        y += 20
        r = pygame.Rect(PANEL.x, y, PANEL.w, 32)
        self.button(scr, r, "Back to the solar system" if self.view == "galaxy" else "Open the galaxy map", sm,
                    lambda: self.strip_click(-1), panel=True, col=(60, 84, 150))
        y += 38
        third = (PANEL.w - 16) // 3
        self.button(scr, pygame.Rect(PANEL.x, y, third, 30), "Close look", sm, self.close_look, panel=True, col=(150, 74, 74))
        self.button(scr, pygame.Rect(PANEL.x + third + 8, y, third, 30), "Home", sm, self.go_home, panel=True, col=(50, 100, 110))
        self.button(scr, pygame.Rect(PANEL.x + 2 * (third + 8), y, third, 30), "Whole galaxy", sm, self.zoom_out, panel=True,
                    col=(50, 70, 110))
        y += 40
        # ---- the jump drive: how far you can reach
        L, mx = g.armory[core.JUMP], ARMORY[core.JUMP][3]
        rr = pygame.Rect(PANEL.x, y, PANEL.w, 62)
        if L >= mx:
            self.row(scr, fonts, rr, f"Jump range  {galaxy.fmt_ly(g.jump_range())}", "Jump Drive at its maximum: you can reach any system",
                     "MAX", None, True, (255, 220, 100), None, glyph="J")
        else:
            cr, sci = armory_cost(core.JUMP, L)
            ok = g.credits >= cr and g.science >= sci
            self.row(scr, fonts, rr, f"Jump range  {galaxy.fmt_ly(g.jump_range())}",
                     f"Attack anything in range. The next level reaches {galaxy.fmt_ly(galaxy.jump_range(L + 1))}.",
                     f"Lv {L}/{mx}", f"{fmt(cr)} cr + {fmt(sci)} sci", ok, (120, 190, 255),
                     (lambda: g.buy_armory(core.JUMP)) if ok else None, glyph="J")
        y += 70
        # ---- the fronts: how many fleets are out, how much of the fleet each attack sends
        n_f, mx_f = len(g.campaigns), g.max_fronts()
        self.txt(scr, med, f"Fronts  {n_f}/{mx_f}", (PANEL.x + 4, y), (255, 190, 150))
        self.txt(scr, tiny, f"{g.free_share() * 100:.0f}% of the fleet at home", (PANEL.right - 4, y + 7), (150, 158, 190), "topright")
        y += 28
        bw = (PANEL.w - 52 - 6 * len(COMMIT_MODES)) // len(COMMIT_MODES)
        self.txt(scr, tiny, "Send:", (PANEL.x + 4, y + 9), (170, 176, 205))
        for i, (label, _) in enumerate(COMMIT_MODES):
            self.button(scr, pygame.Rect(PANEL.x + 52 + i * (bw + 6), y, bw, 28), label, sm, (lambda i=i: setattr(g, "commit", i)),
                        panel=True, selected=g.commit == i, col=(60, 74, 120))
        y += 34
        if not g.campaigns:
            self.txt(scr, tiny, "No fleet in the field." + (" Upgrade Command in the armory to attack several systems at once." if mx_f == 1 else ""),
                     (PANEL.x + 4, y), (140, 148, 180))
            y += 20
        for c in sorted(g.campaigns, key=lambda c: c["dur"] - c["t"]):
            sec = SECTORS[c["k"]]
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 58)
            self.row(scr, fonts, rr, f"{sec['name']}", f"{fmt_time(max(0, c['dur'] - c['t']))} left   -   "
                     f"{c['chance'] * 100:.0f}% to win   -   {c['share'] * 100:.0f}% of the fleet ({fmt(c['fp'])})", None, None, True,
                     FACTIONS[sec["faction"]]["col"], (lambda k=c["k"]: self.select_sector(k)), frac=c["t"] / c["dur"],
                     icon=self.enemy_small[sec["faction"]])
            y += 64
        if g.E["autowar"]:
            on = g.auto_war
            rr = pygame.Rect(PANEL.x, y, PANEL.w - 150, 52)
            self.row(scr, fonts, rr, "Fleet Admiral: " + ("ON" if on else "OFF"),
                     f"Attacks enemies at war with you by itself ({g.auto_odds * 100:.0f}%+ win chance)",
                     None, None, True, (130, 220, 160) if on else (120, 130, 160), self.toggle_auto, glyph="A")
            odds = {0.7: 0.85, 0.85: 0.95, 0.95: 0.7}.get(round(g.auto_odds, 2), 0.85)
            self.button(scr, pygame.Rect(PANEL.right - 142, y, 142, 52), f"Odds {g.auto_odds * 100:.0f}%+", sm,
                        lambda o=odds: setattr(g, "auto_odds", o), panel=True, col=(50, 70, 110))
            y += 60
        # ---- Threat Director
        lvl = director.level(g)
        agg = director.aggression(g)
        at_peace = not director.war_fronts(g)
        tcol = (120, 220, 140) if at_peace else [(120, 220, 140), (190, 230, 120), (255, 215, 100), (255, 150, 90), (255, 90, 90)][lvl]
        tlines = []
        if not g.border():
            tlines.append(("No enemy territory borders yours.", (170, 176, 205)))
        elif at_peace:
            tlines.append(("Nobody is at war with you. Invade a faction - or wait: tension builds on your borders.", (170, 176, 205)))
        elif g.grace > 0:
            tlines.append((f"Enemy fleets are regrouping - quiet for {fmt_time(g.grace)}", (170, 176, 205)))
        else:
            tlines.append(("Raids and counter-offensives come more often when your fleet or planets look weak.", (170, 176, 205)))
        rr = pygame.Rect(PANEL.x, y, PANEL.w, 84)
        self.row(scr, fonts, rr, "Peace" if at_peace and g.border() else f"Threat level: {director.LEVELS[lvl]}",
                 "No faction is at war with you" if at_peace and g.border() else "Enemy aggression", None, None, True, tcol, None,
                 frac=None if at_peace else agg, glyph="!", lines=tlines)
        y += 92
        ilv = director.intel(g)
        if not g.incoming:
            msg = ("No enemy fleets detected." if ilv >= 1 else
                   "Buy the Intel upgrade in the Armory to get early warnings of enemy attacks.")
            self.txt(scr, tiny, msg, (PANEL.x + 8, y), (150, 158, 190))
            y += 22
        for inc in g.incoming:
            if ilv < 1:
                continue
            left = max(0.0, inc["eta"] - inc["t"])
            name = "Enemy counter-offensive" if inc["kind"] == "offensive" else director.TIERS[inc["tier"]]["name"]
            cost = director.fortify_cost(g, inc)
            if inc["kind"] == "offensive":
                done = bool(inc["fort"])
                label = "FORTIFIED" if done else f"FORTIFY  {fmt(cost)} cr"
                can = ilv >= 2 and not done and g.credits >= cost
            else:
                done_n = len(inc["fort"])
                label = (f"FORTIFIED {done_n}/{len(inc['targets'])}" if done_n == len(inc["targets"]) else
                         f"FORTIFY  {fmt(cost)} cr  ({done_n}/{len(inc['targets'])})")
                can = ilv >= 2 and done_n < len(inc["targets"]) and g.credits >= cost
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 76)
            self.row(scr, fonts, rr, f"Incoming: {name}", director.describe(g, inc), fmt_time(left), label if ilv >= 2 else None,
                     can, (255, 110, 100), (lambda i=inc["id"]: director.fortify(g, i)) if can else None,
                     frac=inc["t"] / max(0.1, inc["eta"]), glyph="!")
            y += 84
        # ---- factions: war, truce or peace (tension)
        facs = [f for f in FACTIONS if g.faction_left(f) > 0 and (f in g.war or g.truce.get(f, 0.0) > 0 or director.borders(g, f))]
        if facs:
            self.txt(scr, med, "Factions", (PANEL.x + 4, y), (255, 225, 140))
            y += 28
        for f in facs:
            fcol = FACTIONS[f]["col"]
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 62)
            y += 68
            st = director.stance(g, f)
            if st == "war":
                ok, why = director.can_sue(g, f)
                by = "invaded you" if g.war[f]["by"] == "enemy" else "you invaded them"
                self.row(scr, fonts, rr, f"{FACTIONS[f]['name']}  -  AT WAR",
                         f"{fmt_time(director.war_age(g, f))} ({by}). Their attacks hit x{director.hostility_mult(g, f):.2f}",
                         "SUE FOR PEACE", f"{fmt(director.peace_cost(g, f))} cr" if ok or why == "Not enough credits" else why,
                         ok, (255, 110, 100), (lambda f=f: director.sue_for_peace(g, f)) if ok else None,
                         icon=self.enemy_small[f], tcol=fcol)
            elif st == "truce":
                left = g.truce[f]
                self.row(scr, fonts, rr, f"{FACTIONS[f]['name']}  -  TRUCE", f"Peace holds for {fmt_time(left)}", None, None, True,
                         (130, 220, 255), None, frac=left / director.TRUCE_TIME, icon=self.enemy_small[f], tcol=fcol)
            else:
                t = g.tension.get(f, 0.0)
                tc = (120, 220, 140) if t < 0.5 else ((255, 215, 100) if t < 0.8 else (255, 110, 100))
                sub = ("They are about to declare war!" if t >= 0.8 else
                       "Tension rises while you border them; at 100% they invade you.")
                self.row(scr, fonts, rr, f"{FACTIONS[f]['name']}  -  PEACE", sub, f"tension {t * 100:.0f}%", None, True, tc, None,
                         frac=t, icon=self.enemy_small[f], tcol=fcol)
        if g.director_log:
            ll = [(f"{fmt_time(max(0, g.play_time - t))} ago  -  {text}"[:78], (190, 196, 220)) for t, text in reversed(g.director_log[-5:])]
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 36 + 15 * len(ll))
            self.row(scr, fonts, rr, "Recent enemy activity", "", None, None, True, (150, 160, 200), None, glyph="L", lines=ll)
            y += rr.h + 8
        # ---- the selected system
        k = self.sel_sector
        if k not in g.conquered and not self.sector_known(k):
            k = g.weakest_target() or 1
        sec = SECTORS[k]
        fac = FACTIONS[sec["faction"]]
        ep = g.sector_power(k)
        block = g.attack_block(k)
        share = 1.0 if block else g.launch_share(k)               # what an attack would send (the whole fleet while none can go)
        ch = g.attack_chance(k, share)
        rr = pygame.Rect(PANEL.x, y, PANEL.w, 126)
        y += 134
        loc = f"{galaxy.fmt_ly(sec['d'])} from the Sun  -  {sec['region']}, {sec['con']}"
        if k in g.conquered:
            self.row(scr, fonts, rr, f"{sec['name']}  -  {fac['name']}", f"Reward: {sec['desc']}", "LIBERATED", None, True,
                     fac["col"], (lambda k=k: self.fv.focus(k)), icon=self.enemy_big[sec["faction"]],
                     lines=[(f"{sec['kind']}  -  this system is yours", (140, 205, 255)), (loc, (150, 158, 190))])
        elif not g.scanned(k):
            self.row(scr, fonts, rr, sec["name"], f"{sec['kind']}  -  {loc}", None, None, False,
                     (62, 66, 92), (lambda k=k: self.fv.focus(k)), dim=True, icon=self.enemy_big[sec["faction"]],
                     lines=[("Out of sensor range: hold a system closer, or upgrade the Jump Drive.", (150, 158, 190)),
                            (f"Reward: {sec['desc']}", (120, 128, 160))])
        else:
            tgt = k in g.targets_set()
            can = g.can_attack(k) and fp > 0
            lines = [(f"{sec['kind']}  -  {loc}", (150, 158, 190)),
                     (f"Enemy power {fmt(ep)}    your fleet {fmt(fp)}", (205, 210, 230)),
                     (f"Win chance {ch * 100:.0f}%" + (f" sending {share * 100:.0f}% of the fleet" if not block else "")
                      + f"    campaign time {fmt_time(g.campaign_duration(k))}", self.chance_color(ch))]
            if not tgt:
                _, d = g.source_of(k)
                lines.insert(0, (f"Out of range: {galaxy.fmt_ly(d)} from your nearest system (range {galaxy.fmt_ly(g.jump_range())})",
                                 (255, 190, 120)))
            elif sec["faction"] not in g.war:
                lines.append(("Invading starts a WAR: their fleets will raid you and counter-attack.", (255, 170, 130)))
            rr.h = 48 + 15 * len(lines) + 8
            y += rr.h - 126
            at_war = sec["faction"] in g.war
            if block:
                label = block
            elif at_war:
                label = "ATTACK"
            else:
                label = "CONFIRM WAR!" if self.war_confirm > 0 and self.war_confirm_k == k else "DECLARE WAR"
            self.row(scr, fonts, rr, f"{sec['name']}  -  {fac['name']}", f"Reward: {sec['desc']}", label, None,
                     can, fac["col"], (lambda k=k: self.attack(k)) if can else None,
                     icon=self.enemy_big[sec["faction"]], lines=lines)
        rl, shr = front.report(g, k)
        rr = pygame.Rect(PANEL.x, y, PANEL.w, 56 + 15 * len(rl) + (8 if shr is not None else 0))
        self.row(scr, fonts, rr, f"Front report: {sec['name']}", "Where the battle line sits and how safe the system is",
                 None, None, True, (120, 190, 255), lambda k=k: (setattr(self, "sel_sector", k), self.close_look()),
                 frac=shr, glyph="F", lines=rl)
        y += rr.h + 8
        # ---- armory
        self.txt(scr, med, "Armory", (PANEL.x + 4, y), (255, 225, 140))
        y += 28
        for i, (key, name, desc, mx, base) in enumerate(ARMORY):
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 58)
            y += 64
            L = g.armory[i]
            if L >= mx:
                self.row(scr, fonts, rr, f"{name}  Lv {L} (MAX)", desc, None, None, True, (255, 220, 100), None, glyph=name[0])
                continue
            cr, sci = armory_cost(i, L)
            ok = g.credits >= cr and g.science >= sci
            self.row(scr, fonts, rr, f"{name}  Lv {L}/{mx}", desc, f"{fmt(cr)} cr + {fmt(sci)} sci", None, ok,
                     (230, 150, 110), (lambda i=i: g.buy_armory(i)), glyph=name[0])
        y += 6
        # ---- the systems you can attack
        self.txt(scr, med, "Targets", (PANEL.x + 4, y), (255, 225, 140))
        n_t = len(g.targets())
        self.txt(scr, tiny, f"{n_t:,} in range   -   {len(g.conquered) - 1:,} held   -   {NSEC - 1:,} in the galaxy",
                 (PANEL.right - 4, y + 8), (150, 158, 190), "topright")
        y += 30
        qw = (PANEL.w - 16) // len(self.GAL_MODES)
        for i, label in enumerate(self.GAL_MODES):
            self.button(scr, pygame.Rect(PANEL.x + i * (qw + 8), y, qw, 28), label, tiny,
                        (lambda i=i: setattr(self, "gal_mode", i)), panel=True,
                        col=(70, 100, 170) if i == self.gal_mode else (36, 44, 76))
        y += 36
        rows = self.gal_list(self.gal_mode)
        if not rows:
            self.txt(scr, sm, "Nothing here yet: upgrade the Jump Drive or liberate more systems.", (PANEL.x + 8, y), (150, 158, 190))
            y += 30
        for k in rows:
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 52)
            y += 58
            sec = SECTORS[k]
            fac = FACTIONS[sec["faction"]]
            if k in g.targets_set() or g.scanned(k):
                c2 = win_chance(fp, g.sector_power(k))
                ok = k in g.targets_set()
                _, d = g.source_of(k)
                self.row(scr, fonts, rr, sec["name"], f"{sec['kind']}  -  {fac['name']}  -  {galaxy.fmt_ly(d)} away  -  {sec['desc']}"[:80],
                         f"{c2 * 100:.0f}%", None, ok, fac["col"], (lambda k=k: self.select_sector(k)),
                         icon=self.enemy_small[sec["faction"]])
            else:
                self.row(scr, fonts, rr, sec["name"], f"{sec['kind']}  -  {galaxy.fmt_ly(sec['d'])} from the Sun  -  out of range",
                         None, None, False, (62, 66, 92), (lambda k=k: self.select_sector(k)), dim=True,
                         icon=self.enemy_small[sec["faction"]])
        return y

    # ---------------- ascension -----------------
    def draw_ascension(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        x = PANEL.x + 8
        gold = (255, 215, 120)
        self.txt(scr, big, "Ascension", (x, y), gold)
        self.txt(scr, med, f"New Game+  -  you are in cycle {g.cycle}", (PANEL.right - 8, y + 8), (200, 190, 150), "topright")
        y += 44
        lines = ["Defeat The Devourer on the Void Throne, then Ascend: the whole universe resets and",
                 "a new cycle begins. You keep your achievements and earn Stardust, which gives a",
                 "permanent production bonus and buys powerful perks that make every cycle faster."]
        for i, l in enumerate(lines):
            self.txt(scr, tiny, l, (x, y + i * 17), (175, 180, 205))
        y += 62
        can = g.can_ascend()
        boss = SECTORS[core.BOSS]
        done = core.BOSS in g.conquered
        rr = pygame.Rect(PANEL.x, y, PANEL.w, 62)
        self.row(scr, fonts, rr, "The Devourer  -  The Void Throne",
                 "Defeated! You may Ascend whenever you like." if done else
                 f"It sits at the Galactic Centre, {galaxy.fmt_ly(boss['d'])} from the Sun. Fight your way there.",
                 "DEFEATED" if done else f"{len(g.conquered) - 1:,} systems held", None, done, FACTIONS["devourer"]["col"],
                 None, icon=self.enemy_big["devourer"])
        y += 72
        self.txt(scr, med, f"Stardust: {g.stardust:,} to spend", (x, y), gold)
        self.txt(scr, sm, f"{g.sd_total:,} earned   -   production bonus x{sd_bonus(g.sd_total):.2f}", (PANEL.right - 8, y + 2),
                 (210, 190, 140), "topright")
        y += 28
        gain = max(1, g.sd_gain())
        self.txt(scr, med, f"Ascend now for: +{gain} Stardust", (x, y), (130, 255, 150) if can else (180, 120, 120))
        y += 28
        m = 1 + core.TUNE["cdiff"] * g.cycle
        self.txt(scr, tiny, f"Next cycle: planets and megaprojects cost x{m:.0f}, enemy fleets x{core.TUNE['cpow'] ** g.cycle:.1f} stronger.",
                 (x, y), (190, 160, 130))
        y += 22
        keeps = [("KEPT: achievements, Stardust and its perks, your statistics.", (150, 220, 160)),
                 ("RESET: planets, ships, colonies, tech, credits, science, Dark Matter, armory, liberated sectors "
                  "and megaprojects - some of these can be kept with the Stardust perks below.", (210, 150, 140))]
        for text, col in keeps:
            for l in wrap(tiny, text, PANEL.w - 24):
                self.txt(scr, tiny, l, (x, y), col)
                y += 16
        y += 8
        label = "CLICK AGAIN TO CONFIRM ASCENSION" if self.ascend_confirm > 0 else "ASCEND"
        self.button(scr, pygame.Rect(x, y, PANEL.w - 16, 52), label, med, self.do_ascend, enabled=can, panel=True,
                    col=(170, 70, 60) if self.ascend_confirm > 0 else (150, 110, 40))
        y += 70
        self.txt(scr, med, "Stardust Perks", (x, y), gold)
        y += 30
        for pk in STARDUST_PERKS:
            pid, name, cost, desc, _ = pk
            r = pygame.Rect(PANEL.x, y, PANEL.w, 58)
            y += 64
            if pid in g.sd_perks:
                self.row(scr, fonts, r, name, desc, "OWNED", None, True, (255, 220, 100), None, tcol=(255, 225, 140), glyph="*")
            else:
                self.row(scr, fonts, r, name, desc, f"{fmt(cost)} SD", None, g.stardust >= cost, (255, 200, 110),
                         lambda pid=pid: g.buy_sd_perk(pid), glyph="*")
        return y

    def draw_ascend_fx(self, scr, fonts):
        prog = self.ascend_fx / 3.4                    # 1 -> 0
        grow = 1 - prog
        for a, sp in self.streaks:
            d0 = 20 + grow * sp * 520
            d1 = d0 + 30 + grow * 300 * sp
            v = min(1.0, prog * 1.8)
            pygame.draw.line(scr, (int(255 * v), int(205 * v), int(110 * v)), (CX + math.cos(a) * d0, CY + math.sin(a) * d0),
                             (CX + math.cos(a) * d1, CY + math.sin(a) * d1), 3)
        fx = pygame.Surface((W, H), pygame.SRCALPHA)
        a = int(max(0.0, min(1.0, (prog - 0.35) / 0.65)) * 245) if prog > 0.35 else int(max(0.0, prog / 0.35) * 160)
        fx.fill((255, 240, 205, a))
        scr.blit(fx, (0, 0))
        if prog < 0.8:
            k = min(1.0, (0.8 - prog) / 0.25) * min(1.0, prog / 0.25)
            img = fonts[0].render(f"CYCLE {self.ascend_cycle}", True, (255, 245, 215))
            img.set_alpha(int(255 * k))
            scr.blit(img, img.get_rect(center=(CX, CY - 30)))
            img2 = fonts[1].render("NEW GAME+", True, (255, 215, 120))
            img2.set_alpha(int(255 * k))
            scr.blit(img2, img2.get_rect(center=(CX, CY + 10)))

    # ---------------- achievements, stats, dev -----------------
    def ach_progress(self, a):
        if not a["prog"]:
            return None
        cur, tgt = a["prog"](self.g)
        if tgt <= 0:
            return None
        if tgt >= 1e5:
            f = math.log10(max(cur, 0) + 1) / math.log10(tgt + 1)
        else:
            f = cur / tgt
        return max(0.0, min(1.0, f)), cur, tgt

    def draw_star(self, scr, cx, cy, r, col):
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.42
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        pygame.draw.polygon(scr, col, pts)

    def draw_medal(self, scr, cx, cy, tier, got):
        col = MEDAL[tier]
        if got:
            scr.blit(glow(26, scale_c(col, 0.55)), (cx - 26, cy - 26), special_flags=ADD)
        pygame.draw.circle(scr, scale_c(col, 0.28 if got else 0.12), (cx, cy), 19)
        pygame.draw.circle(scr, col if got else scale_c(col, 0.35), (cx, cy), 19, 2)
        self.draw_star(scr, cx, cy, 11, col if got else scale_c(col, 0.35))

    def draw_awards(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        total = len(ACHIEVEMENTS)
        self.txt(scr, med, f"{len(g.ach)}/{total} achievements", (PANEL.x + 4, y), (255, 225, 140))
        self.txt(scr, sm, f"+{g.ach_bonus * 100:.1f}% production", (PANEL.right - 4, y + 2), (130, 255, 150), "topright")
        y += 26
        x = PANEL.x + 4
        for t in TIER_NAMES:
            n = sum(1 for a in ACHIEVEMENTS if a["tier"] == t)
            e = sum(1 for a in ACHIEVEMENTS if a["tier"] == t and a["id"] in g.ach)
            label = f"{t.title()} {e}/{n} (+{TIER_BONUS[t] * 100:g}%)"
            self.txt(scr, tiny, label, (x, y), MEDAL[t])
            x += tiny.size(label)[0] + 16
        y += 22
        for i, c in enumerate(AWARD_CHIPS):
            r = pygame.Rect(PANEL.x + (i % 8) * 74, y + (i // 8) * 28, 70, 24)
            self.button(scr, r, c, tiny, (lambda c=c: setattr(self, "awards_cat", c)), panel=True,
                        col=(78, 100, 176) if self.awards_cat == c else (34, 42, 74))
        y += 62
        if self.awards_cat == "Stats":
            return self.draw_stats(scr, fonts, y)
        items = [a for a in ACHIEVEMENTS if self.awards_cat in ("All", a["cat"])]

        def sort_key(a):
            pr = self.ach_progress(a)
            return (a["id"] in g.ach, -(pr[0] if pr else 0.0))
        items.sort(key=sort_key)
        for a in items:
            r = pygame.Rect(PANEL.x, y, PANEL.w, 62)
            y += 68
            if not r.colliderect(PANEL):
                continue
            got = a["id"] in g.ach
            col = MEDAL[a["tier"]]
            hidden = a["secret"] and not got
            pygame.draw.rect(scr, (52, 46, 28) if got else (22, 24, 42), r, border_radius=9)
            pygame.draw.rect(scr, col if got else (52, 56, 84), r, 1, border_radius=9)
            self.draw_medal(scr, r.x + 34, r.centery, a["tier"], got)
            self.txt(scr, med, "???" if hidden else a["name"], (r.x + 66, r.y + 6), (255, 235, 170) if got else (150, 155, 180))
            desc = "Secret achievement - keep playing to find it!" if hidden else a["desc"]
            self.txt(scr, tiny, desc, (r.x + 66, r.y + 30), (180, 184, 205) if got else (110, 116, 142))
            self.txt(scr, sm, f"+{TIER_BONUS[a['tier']] * 100:g}%", (r.right - 12, r.y + 8), col if got else scale_c(col, 0.5), "topright")
            if got:
                self.txt(scr, tiny, "EARNED", (r.right - 12, r.bottom - 10), (255, 215, 110), "bottomright")
            else:
                pr = self.ach_progress(a)
                if pr:
                    f, cur, tgt = pr
                    bar = pygame.Rect(r.x + 66, r.bottom - 12, r.w - 200, 5)
                    pygame.draw.rect(scr, (16, 18, 32), bar, border_radius=2)
                    if f > 0:
                        pygame.draw.rect(scr, scale_c(col, 0.8), (bar.x, bar.y, int(bar.w * f), bar.h), border_radius=2)
                    self.txt(scr, tiny, f"{fmt(cur)} / {fmt(tgt)}", (r.right - 12, r.bottom - 10), (150, 156, 184), "bottomright")
        return y

    def draw_stats(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        rows = [
            ("Play time", fmt_time(g.play_time)),
            ("Asteroid clicks", f"{g.clicks:,}"),
            ("Best click burst (10 s)", str(g.best_burst)),
            ("Ore mined (Earth-equivalent)", fmt(g.all_norm)),
            ("Credits earned", fmt(g.all_cred)),
            ("Science produced", fmt(g.all_sci)),
            ("Ships owned", f"{g.total_ships():,}"),
            ("Ships bought", f"{g.bought:,}"),
            ("Upgrades bought", f"{g.ups_bought:,}"),
            ("Planets unlocked", f"{g.n_unlocked}/{NSITE}"),
            ("Planets visited", f"{len(g.visited)}/{NSITE}"),
            ("Trips between planets", f"{g.travels:,}"),
            ("Systems held", f"{len(g.conquered) - 1:,} of {NSEC - 1:,}"),
            ("Jump range", galaxy.fmt_ly(g.jump_range())),
            ("Battles won / lost", f"{g.battles_won:,} / {g.battles_lost:,}"),
            ("Raids repelled / lost", f"{g.raids_repelled:,} / {g.raids_lost:,}"),
            ("Big raids repelled (regional / system)", f"{g.tier_wins[1]:,} / {g.tier_wins[2]:,}"),
            ("Counter-offensives held", f"{g.offensives_repelled:,}"),
            ("Wars declared / suffered / peace treaties", f"{g.wars_declared} / {g.wars_suffered} / {g.peaces_made}"),
            ("Systems lost / retaken", f"{g.sectors_lost:,} / {g.sectors_retaken:,}"),
            ("Fleet power", fmt(g.fleet_power())),
            ("Colony levels built", f"{g.bldg:,}"),
            ("Megaprojects", f"{len(g.projects)}/{NSITE}"),
            ("Techs researched", f"{len(g.techs)}/{len(TECHS)}"),
            ("Quests completed", f"{g.quests_done:,}"),
            ("Events resolved", f"{g.events_done:,}"),
            ("Supply crates grabbed", f"{g.crates:,}"),
            ("Mining frenzies", f"{g.frenzies:,}"),
            ("Warps", f"{g.warps:,}"),
            ("Cycle (New Game+)", f"{g.cycle}   ({g.ascensions} ascension{'s' if g.ascensions != 1 else ''})"),
            ("Time in this cycle", fmt_time(g.play_time - g.cycle_start)),
            ("Stardust", f"{g.stardust:,} to spend, {g.sd_total:,} earned"),
            ("Dark Matter", f"{g.dm:,} total, {g.dm_avail():,} to spend"),
            ("Dark Matter perks", f"{len(g.perks)}/{len(PERKS)}"),
            ("Achievements", f"{len(g.ach)}/{len(ACHIEVEMENTS)}  (+{g.ach_bonus * 100:.1f}%)"),
        ]
        self.txt(scr, med, "Statistics", (PANEL.x + 4, y), (230, 200, 255))
        y += 28
        for i, (label, val) in enumerate(rows):
            r = pygame.Rect(PANEL.x, y, PANEL.w, 24)
            y += 26
            if i % 2 == 0 and r.colliderect(PANEL):
                pygame.draw.rect(scr, (24, 28, 52), r, border_radius=5)
            self.txt(scr, sm, label, (r.x + 10, r.y + 3), (170, 176, 205))
            self.txt(scr, sm, val, (r.right - 10, r.y + 3), (240, 240, 250), "topright")
        if "cheated" in g.flags:
            self.txt(scr, sm, "This save has used developer cheats.", (PANEL.x + 10, y + 4), (255, 120, 120))
            y += 24
        y += 14
        self.txt(scr, med, "Settings", (PANEL.x + 4, y), (230, 200, 255))
        y += 30
        st = g.settings

        def toggle_sound():
            st["sound"] = not st.get("sound", True)
            self.snd.play("buy")

        def vol(d):
            def run():
                st["volume"] = max(0.0, min(1.0, round(st.get("volume", 0.6) + d, 2)))
                self.snd.play("buy")
            return run
        self.button(scr, pygame.Rect(PANEL.x, y, 180, 36), f"Sound: {'ON' if st.get('sound', True) else 'OFF'}", sm,
                    toggle_sound, panel=True, col=(60, 120, 90) if st.get("sound", True) else (90, 50, 60))
        self.button(scr, pygame.Rect(PANEL.x + 190, y, 50, 36), "-", med, vol(-0.1), panel=True)
        self.txt(scr, sm, f"Volume {int(st.get('volume', 0.6) * 100)}%", (PANEL.x + 300, y + 9), (200, 205, 225), "midtop")
        self.button(scr, pygame.Rect(PANEL.x + 360, y, 50, 36), "+", med, vol(0.1), panel=True)
        if not self.snd.ok:
            self.txt(scr, tiny, "(no audio device found)", (PANEL.x + 420, y + 12), (160, 120, 120))
        y += 48
        if not resources.TOUCH:                      # (not on a phone: the game always fills the screen)
            self.button(scr, pygame.Rect(PANEL.x, y, 180, 36), f"Fullscreen: {'ON' if self.fullscreen else 'OFF'}", sm,
                        self.toggle_fullscreen, enabled=self.can_scale, panel=True,
                        col=(60, 120, 90) if self.fullscreen else (50, 70, 110))
            self.txt(scr, tiny, "F11 or Alt+Enter. You can also resize or maximise the window.", (PANEL.x + 192, y + 11), (150, 158, 190))
            y += 48
            opts = ["auto"] + [f"{w}x{h}" for w, h in RESOLUTIONS]
            cur = st.get("resolution", "auto")
            nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else "auto"
            shown = "Auto" if cur == "auto" else cur
            self.button(scr, pygame.Rect(PANEL.x, y, 180, 36), f"Size: {shown}", sm, lambda nxt=nxt: self.set_resolution_choice(nxt),
                        enabled=self.can_scale, panel=True, col=(50, 70, 110))
            self.txt(scr, tiny, f"Now {W}x{H}. Bigger = sharper and roomier, but needs a faster computer.", (PANEL.x + 192, y + 11), (150, 158, 190))
            y += 48
        self.button(scr, pygame.Rect(PANEL.x, y, 200, 40), "Save now", sm,
                    lambda: (g.save(), g.toast("Game saved.", 2)), panel=True)
        self.button(scr, pygame.Rect(PANEL.x + 220, y, 280, 40),
                    "CLICK AGAIN: WIPE SAVE" if self.reset_confirm > 0 else "Hard reset (wipe save)", sm,
                    self.hard_reset, panel=True, col=(150, 60, 70) if self.reset_confirm > 0 else (70, 40, 50))
        y += 52
        if not resources.TOUCH:
            can_open = not resources.ANDROID and gamelog.enabled()
            self.button(scr, pygame.Rect(PANEL.x, y, 200, 34), "Open log folder", sm, self.open_log_folder, enabled=can_open, panel=True)
            shown = gamelog.log_dir()
            if len(shown) > 52:
                shown = "..." + shown[-49:]
            self.txt(scr, tiny, shown, (PANEL.x + 212, y + 4), (150, 158, 190))
            n = gamelog.error_count()
            self.txt(scr, tiny, (f"{n} error(s) logged this session - see the log" if n else "No errors this session"),
                     (PANEL.x + 212, y + 19), (255, 150, 130) if n else (120, 160, 130))
        self.txt(scr, tiny, f"Space Miner {__version__}", (PANEL.x + 4, y + 44), (120, 128, 160))
        return y + 70

    def draw_dev(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        self.txt(scr, med, "DEVELOPER MODE", (PANEL.x + 4, y), (255, 120, 120))
        y += 26
        self.txt(scr, tiny, "Started with --dev. Using a cheat marks the save as cheated (secret achievement).",
                 (PANEL.x + 4, y), (170, 150, 150))
        y += 12
        half = PANEL.w // 2
        for title, items in devtools.sections(self):
            y += 18
            self.txt(scr, med, title, (PANEL.x + 4, y), (255, 215, 140))
            y += 28
            for k, (label, fn, active) in enumerate(items):
                r = pygame.Rect(PANEL.x + (k % 2) * half, y, half - 6, 34)
                if r.colliderect(PANEL):
                    f = sm if sm.size(label)[0] < half - 24 else tiny
                    self.button(scr, r, label, f, (lambda fn=fn, label=label: (gamelog.LOG.info("Developer cheat: %s", label), fn())),
                                panel=True, col=(150, 70, 70) if active else (52, 64, 108))
                if k % 2 == 1 or k == len(items) - 1:
                    y += 40
        return y + 20

    def draw_banner(self, scr, fonts):
        if not self.banners:
            return
        big, med, sm, tiny = fonts
        bn = self.banners[0]
        t, dur = bn["t"], bn["dur"]
        k = max(0.0, min(1.0, t / 0.35, (dur - t) / 0.35))
        ease = 1 - (1 - k) ** 3
        w, h = 430, 68
        x = PANEL.x - 5 - w if self.panel_visible() else (W - w) // 2
        y = -h + (h + 12) * ease
        col = bn["col"]
        scr.blit(glow(150, scale_c(col, 0.18)), (x + w // 2 - 150, y + h // 2 - 150), special_flags=ADD)
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (14, 16, 38, 238), bg.get_rect(), border_radius=12)
        pygame.draw.rect(bg, (*col, 255), bg.get_rect(), 2, border_radius=12)
        scr.blit(bg, (x, y))
        if bn.get("tier"):
            self.draw_medal(scr, int(x + 36), int(y + h // 2), bn["tier"], True)
        else:
            cx, cy = int(x + 36), int(y + h // 2)
            scr.blit(glow(26, scale_c(col, 0.55)), (cx - 26, cy - 26), special_flags=ADD)
            pygame.draw.circle(scr, scale_c(col, 0.3), (cx, cy), 19)
            pygame.draw.circle(scr, col, (cx, cy), 19, 2)
            self.txt(scr, med, bn.get("glyph", "!"), (cx, cy), (255, 255, 255), "center")
        self.txt(scr, tiny, bn["header"], (x + 70, y + 8), col)
        self.txt(scr, med, bn["title"], (x + 70, y + 24), (255, 245, 215))
        self.txt(scr, tiny, bn["sub"][:62], (x + 70, y + 48), (175, 180, 205))
        if bn.get("right"):
            self.txt(scr, sm, bn["right"], (x + w - 14, y + 10), (130, 255, 150), "topright")

    def draw_event(self, scr, fonts):
        big, med, sm, tiny = fonts
        ev = self.g.event
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 10, 150))
        scr.blit(dim, (0, 0))
        box = pygame.Rect(0, 0, 560, 290)
        box.center = (CX, int(H * 0.458))
        scr.blit(glow(330, (24, 20, 6)), (box.centerx - 330, box.centery - 330), special_flags=ADD)
        scr.blit(self.modal_bg, box)
        pygame.draw.rect(scr, (255, 215, 110), box, 2, border_radius=14)
        self.txt(scr, big if big.size(ev["title"])[0] < 520 else med, ev["title"], (box.centerx, box.y + 18),
                 (255, 225, 140), "midtop", True)
        for i, line in enumerate(wrap(sm, ev["text"], box.w - 50)):
            self.txt(scr, sm, line, (box.x + 25, box.y + 72 + i * 22))
        for i, (label, fn) in enumerate(ev["opts"]):
            r = pygame.Rect(box.x + 25, box.y + 160 + i * 56, box.w - 50, 46)
            self.button(scr, r, label, med, (lambda fn=fn: self.g.resolve_event(fn)), col=(60, 80, 150), modal=True)
        self.txt(scr, tiny, f"Decide in {ev['left']:.0f}s", (box.centerx, box.bottom - 6), (150, 155, 180), "midbottom")


USAGE = """Space Miner

usage: space-miner [--new-game [--yes]] [--fullscreen] [--resolution WxH] [--touch] [--debug] [--dev] [--selftest] [--version]

  --new-game   erase your save and start over (asks first; --yes skips the question). A copy of the old save is kept
               next to it as .space_miner_save.json.before-reset-DATE
  --fullscreen start in fullscreen (F11 toggles it any time; the window can also be resized or maximised)
  --resolution WxH   canvas size for this run, e.g. 1920x1080 (the Stats page saves a choice; the default is automatic)
  --touch      the touch-screen interface (tap, drag to scroll, bigger buttons), to try it with a mouse
  --debug      verbose log (also printed in the terminal)
  --dev        developer mode: adds a Dev tab with cheats (F1 jumps to it). Terminal only.
  --selftest   run headless for a few seconds and exercise the game (used for testing)
  --version    print the version and exit
"""


def open_window(w, h, fullscreen=False):
    """Open the game window as a w x h canvas: resizable (so it can be maximised or dragged bigger) and scaled to fit,
    with black bars if the shape differs. Returns (surface, can_scale, fullscreen); without a scaling renderer it is a
    plain fixed-size window."""
    os.environ.setdefault("SDL_HINT_RENDER_SCALE_QUALITY", "linear")          # smooth scaling when the window is not w x h
    if pygame.display.get_driver() == "dummy":                                  # the headless test driver has no renderer
        return pygame.display.set_mode((w, h)), True, False
    if resources.ANDROID:                                                       # always fullscreen, scaled to the screen
        try:
            return pygame.display.set_mode((w, h), pygame.SCALED | pygame.FULLSCREEN), True, True
        except pygame.error as e:
            gamelog.LOG.warning("Scaled fullscreen failed on Android (%s); trying a plain fullscreen.", e)
            return pygame.display.set_mode((w, h), pygame.FULLSCREEN), False, True
    flags = pygame.SCALED | pygame.RESIZABLE
    if fullscreen:
        try:
            return pygame.display.set_mode((w, h), flags | pygame.FULLSCREEN), True, True
        except pygame.error as e:
            gamelog.LOG.warning("Fullscreen is not available (%s); using a window.", e)
    try:
        scr = pygame.display.set_mode((w, h), flags)
        try:                                                                   # the window can keep an older, bigger size
            from pygame._sdl2 import video
            video.Window.from_display_module().size = (w, h)
        except Exception:
            pass
        return scr, True, False
    except pygame.error as e:
        gamelog.LOG.warning("No scaling window (%s); using a fixed-size window.", e)
        return pygame.display.set_mode((w, h)), False, False


def android_canvas(dw, dh):
    """A canvas with the shape of the phone's screen (so it fills it without black bars), at least 1280x720."""
    aspect = max(dw, dh) / max(1, min(dw, dh))
    if aspect >= 16 / 9:
        return round(720 * aspect), 720
    return 1280, round(1280 / aspect)


def choose_resolution(setting, fullscreen):
    """The canvas size to use: the one picked in the settings, or ("auto") the biggest preset that suits the screen -
    the whole desktop when fullscreen, otherwise what fits in a window."""
    if setting and setting != "auto":
        try:
            w, h = (int(v) for v in str(setting).lower().split("x"))
            if 640 <= w <= 7680 and 360 <= h <= 4320:
                return w, h
        except ValueError:
            pass
    try:
        dw, dh = pygame.display.get_desktop_sizes()[0]
    except (pygame.error, IndexError):
        dw, dh = 1920, 1080
    if resources.ANDROID:
        return android_canvas(dw, dh)
    lim = (dw, dh) if fullscreen else (dw * 0.92, dh * 0.85)
    best = RESOLUTIONS[0]
    for r in RESOLUTIONS:
        if r[0] <= lim[0] and r[1] <= lim[1]:
            best = r
    return best


def new_game_reset(save, yes=False, ask=input, say=print):
    """--new-game: erase the save (and its backup) so the next start is a brand-new game. The old save is not thrown away: it is
    renamed to <save>.before-reset-<date>. Returns "none" if there was no save, "reset" when it was erased and "declined" when the
    answer was not yes (or there was nobody to ask)."""
    if not os.path.exists(save) and not os.path.exists(save + ".bak"):
        say("There is no save to erase: a new game starts.")
        return "none"
    if not yes:
        try:
            answer = ask(f"This erases your save ({save}). A copy is kept next to it. Start over? Type yes to confirm: ")
        except EOFError:                              # not a terminal: never wipe without an answer
            say("Not erasing anything: there was nobody to ask. Add --yes to skip the question.")
            return "declined"
        if answer.strip().lower() not in ("y", "yes"):
            say("Nothing was erased.")
            return "declined"
    kept = f"{save}.before-reset-{time.strftime('%Y%m%d-%H%M%S')}"
    for path in (save, save + ".bak", save + ".tmp"):
        if os.path.exists(path):
            if path == save:
                shutil.move(path, kept)
            else:
                os.remove(path)
    say(f"Save erased. The old one was kept as {kept}  (delete that file if you do not want it).")
    return "reset"


def check_new_game_reset():
    """--new-game: asks, keeps a copy of the old save, removes the backup, and never wipes without a yes."""
    d = tempfile.mkdtemp(prefix="space_miner_reset_")
    save = os.path.join(d, "save.json")
    quiet = lambda *a: None
    try:
        assert new_game_reset(save, yes=True, say=quiet) == "none"
        for p in (save, save + ".bak"):
            with open(p, "w") as f:
                f.write("{}")
        assert new_game_reset(save, ask=lambda q: "no", say=quiet) == "declined" and os.path.exists(save)
        assert new_game_reset(save, ask=lambda q: (_ for _ in ()).throw(EOFError), say=quiet) == "declined" and os.path.exists(save)
        assert new_game_reset(save, ask=lambda q: " Yes ", say=quiet) == "reset"
        assert not os.path.exists(save) and not os.path.exists(save + ".bak"), "the save and its backup must be gone"
        assert [n for n in os.listdir(d) if ".before-reset-" in n], "a copy of the old save must be kept"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(USAGE)
        return
    if "--version" in sys.argv:
        print(f"Space Miner {__version__}")
        return
    selftest = "--selftest" in sys.argv
    if ("--new-game" in sys.argv or "--reset" in sys.argv) and not selftest:
        if new_game_reset(core.SAVE, yes="--yes" in sys.argv) == "declined":
            return
    dev = "--dev" in sys.argv
    if "--touch" in sys.argv:
        resources.TOUCH = True                      # the touch-screen interface, for trying it with a mouse
    test_dir = None
    if selftest:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        test_dir = tempfile.mkdtemp(prefix="space_miner_selftest_")
        core.SAVE = os.path.join(test_dir, "save.json")              # the self-test never touches your real save
    gamelog.setup(debug="--debug" in sys.argv, directory=test_dir)   # the self-test logs into its temporary folder too
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("Space Miner")
    try:
        pygame.display.set_icon(pygame.image.load(resources.resource("assets/icon.png")))
    except (FileNotFoundError, pygame.error) as e:
        gamelog.LOG.warning("Could not load the window icon: %s", e)
    saved = core.peek_settings()
    cli_res = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--resolution=")), None)
    if cli_res is None and "--resolution" in sys.argv and sys.argv.index("--resolution") + 1 < len(sys.argv):
        cli_res = sys.argv[sys.argv.index("--resolution") + 1]
    want_fs = resources.ANDROID or ((not selftest) and ("--fullscreen" in sys.argv or bool(saved.get("fullscreen"))))
    start_w, start_h = choose_resolution(cli_res or saved.get("resolution", "auto"), want_fs)
    apply_layout(start_w, start_h)
    scr, can_scale, is_fs = open_window(start_w, start_h, want_fs)
    if not can_scale:
        gamelog.LOG.warning("No scaling renderer: using a fixed-size window (no resizing or fullscreen).")
    gamelog.log_session()
    clock = pygame.time.Clock()

    def font(size, bold=False):                      # the bundled DejaVu Sans, so it looks the same everywhere
        try:
            return pygame.font.Font(resources.resource("assets/fonts/DejaVuSans-Bold.ttf" if bold else "assets/fonts/DejaVuSans.ttf"), size)
        except (FileNotFoundError, pygame.error) as e:
            gamelog.LOG.warning("Bundled font not found (%s); using a system font.", e)
            return pygame.font.SysFont("dejavusans,liberationsans,arial,freesans", size, bold=bold)

    fonts = (font(30, True), font(18, True), font(15), font(12))
    t0 = time.time()
    app = App(dev=dev)
    g = app.g
    gamelog.set_context(app.describe)
    app.scr, app.can_scale, app.fullscreen = scr, can_scale, is_fs
    app.res_override = cli_res
    gamelog.LOG.info("Display: %dx%d, fullscreen %s", start_w, start_h, is_fs)
    if dev:
        print("Developer mode ON (cheats are in the Dev tab; F1 jumps to it).")
        gamelog.LOG.info("Developer mode is ON")
    if selftest:
        print(f"startup {time.time() - t0:.2f}s")
    gamelog.LOG.info("Ready in %.2f s", time.time() - t0)
    _SCR.update(scr=scr, fonts=fonts)
    here = os.path.dirname(os.path.abspath(__file__))
    running = True
    frames = 0
    fail_streak = 0
    crashed = False
    started = last_beat = time.monotonic()
    beat_frames = 0
    slowest = 0.0

    def shot(n):
        pygame.image.save(app.scr, os.path.join(here, f"shot_{n}.png"))

    try:
        while running:
            try:
                raw = clock.tick(60) / 1000.0
                dt = min(raw, 0.25)
                if selftest:
                    dt = 0.05
                if raw > 2.0 and not selftest:
                    gamelog.LOG.info("The game was paused for %.1f s (computer asleep, or the window was being dragged).", raw)
                else:
                    slowest = max(slowest, raw)
                app.fps = clock.get_fps()
                if dev and not selftest:
                    dt = min(dt * app.dev_state.speed, 30.0)
                app.mouse = (480, 330) if selftest else pygame.mouse.get_pos()
                for e in pygame.event.get():
                    if e.type == pygame.QUIT:
                        running = False
                    elif e.type == pygame.KEYDOWN:
                        if e.key == getattr(pygame, "K_AC_BACK", -1):
                            app.back_pressed()
                        elif e.key == pygame.K_ESCAPE:
                            if app.fullscreen and not resources.ANDROID:
                                app.toggle_fullscreen()
                            else:
                                running = False
                        elif e.key == pygame.K_F11 or (e.key == pygame.K_RETURN and e.mod & pygame.KMOD_ALT):
                            app.toggle_fullscreen()
                        elif e.key == pygame.K_SPACE and not g.event:
                            app.space_click()
                        elif pygame.K_1 <= e.key <= pygame.K_9 and e.key - pygame.K_1 < len(app.tabs):
                            app.set_tab(e.key - pygame.K_1)
                        elif e.key == pygame.K_0 and len(app.tabs) >= 10:
                            app.set_tab(9)
                        elif e.key == pygame.K_g:
                            app.strip_click(-1)
                        elif app.galaxy_key(e.key):
                            pass
                        elif e.key == pygame.K_F1 and dev:
                            app.set_tab(len(app.tabs) - 1 if app.tab != len(app.tabs) - 1 else 0)
                    elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                        if getattr(e, "touch", False) or resources.TOUCH:
                            app.touch.down(e.pos)
                        elif not (app.view == "galaxy" and not g.event and app.fv.down(e.pos)):
                            app.mouse_down(e.pos)
                    elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                        if getattr(e, "touch", False) or resources.TOUCH:
                            app.touch.up(e.pos)
                        else:
                            app.fv.up(e.pos)
                    elif e.type == pygame.MOUSEMOTION:
                        if getattr(e, "touch", False) or resources.TOUCH:
                            app.touch.move(e.pos)
                        else:
                            if app.fv.drag and not e.buttons[0]:
                                app.fv.drag = None
                            app.fv.move(e.pos)
                    elif e.type in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
                        kind = {pygame.FINGERDOWN: "down", pygame.FINGERUP: "up", pygame.FINGERMOTION: "motion"}[e.type]
                        app.touch.finger(kind, e.finger_id, e.x, e.y, pygame.display.get_window_size())
                    elif e.type == pygame.MOUSEWHEEL:
                        if app.panel_visible() and PANEL.collidepoint(app.mouse):
                            app.scroll[app.tab] -= e.y * 50
                        elif app.view == "galaxy" and not g.event:
                            app.fv.wheel(app.mouse, e.y)
                    elif e.type in LIFECYCLE_BACKGROUND:
                        app.went_to_background()
                    elif e.type in LIFECYCLE_FOREGROUND:
                        app.came_back()
                app.touch.update(dt)
                app.update(dt)
                app.draw(app.scr, fonts)
                pygame.display.flip()
                frames += 1
                beat_frames += 1
                fail_streak = 0
                if selftest:
                    selftest_step(app, g, frames, shot)
                    if frames >= (100 if dev else 95):
                        running = False
                elif time.monotonic() - last_beat >= 300:                       # a line every 5 minutes: what was going on
                    secs = time.monotonic() - last_beat
                    gamelog.LOG.info("alive: %.0f fps average, slowest frame %.0f ms | %s", beat_frames / secs, slowest * 1000,
                                     app.describe().splitlines()[0])
                    last_beat, beat_frames, slowest = time.monotonic(), 0, 0.0
            except Exception:
                if selftest:
                    raise                                    # the self-test must fail loudly
                app.scr.set_clip(None)                       # a half-finished frame can leave a clip rectangle behind
                fail_streak += 1
                if gamelog.report("the game loop"):
                    try:
                        g.toast("Something went wrong - it was written to the log. The game keeps running.", 8)
                    except Exception:
                        pass
                if fail_streak >= 30:                        # every frame fails: stop cleanly instead of freezing
                    path = gamelog.write_crash_report(sys.exc_info(), "The game stopped: 30 frames in a row raised an error.")
                    print(f"Space Miner stopped because of an error. Crash report: {path or gamelog.log_path()}", file=sys.stderr)
                    crashed = True
                    running = False
    except KeyboardInterrupt:
        gamelog.LOG.info("Interrupted from the terminal")
    if not crashed:
        g.save()                                             # (after a crash the last autosave is kept as it is)
    gamelog.LOG.info("Exit %s after %.0f s, %d frames, %d error(s)", "after a crash" if crashed else "normally",
                     time.monotonic() - started, frames, gamelog.error_count())
    pygame.quit()
    if test_dir:
        shutil.rmtree(test_dir, ignore_errors=True)
    if crashed:
        sys.exit(1)


_SCR = {}
LIFECYCLE_BACKGROUND = {getattr(pygame, n) for n in ("APP_WILLENTERBACKGROUND", "APP_TERMINATING") if hasattr(pygame, n)}
LIFECYCLE_FOREGROUND = {getattr(pygame, n) for n in ("APP_DIDENTERFOREGROUND",) if hasattr(pygame, n)}


def app_scr():
    return pygame.display.get_surface()


def app_fonts():
    return _SCR["fonts"]


def check_ship_art(app):
    """Every planet's ships draw, are not all alike, and fly sensible paths."""
    seen = {}
    for p in range(NSITE):
        for i in range(NSH):
            spr = app.ship_sprite(p, i)
            assert spr.get_width() > 8 and pygame.mask.from_surface(spr).count() > 20, (p, i)
            assert app.ship_icon(p, i).get_width() == 46
            seen[(p, i)] = pygame.image.tostring(spr, "RGBA")
        n = ships.shown(p, 4)
        assert 1 <= n <= 4
        for i in range(NSH):
            for j in range(n):
                for t in (0.0, 7.3, 1234.5):
                    x, y, depth = ships.orbit(p, i, j, n, t, 1 if i % 2 == 0 else -1)
                    assert abs(x) < 300 and abs(y) < 300 and -1.001 <= depth <= 1.001, (p, i, j, t, x, y, depth)
                    assert -math.pi <= ships.heading(p, i, j, n, t, 1) <= math.pi
    for i in range(NSH):                           # the same class must look different on different planets
        assert len({seen[(p, i)] for p in range(NSITE)}) == NSITE, f"class {i} has identical sprites on two planets"
    canvas = pygame.Surface((300, 300))
    for style in {ships.style(p) for p in range(NSITE)}:   # every laser style draws
        shipart.beam(canvas, style, (100, 100), (180, 150), (255, 200, 120), 1.5, 3)


def check_more_ships():
    """Ten classes everywhere: the tables agree, the new classes are priced and powered on the same ladder, and a save from
    the time of eight classes still loads."""
    from core import SHIP_POWER, UPG_BY_ID
    assert NSH == 10 == len(ships.CLASSES) == len(SHIP_POWER) == len(SHIPS)
    assert all(len(r["names"]) == NSH and len(r["blurbs"]) == NSH for r in ships.ROSTERS), "a roster misses a class"
    assert [n for n, *_ in SHIPS] == ships.ROSTERS[0]["names"], "Earth's roster must use the ships' own names"
    assert all(SHIPS[i + 1][1] > SHIPS[i][1] and SHIPS[i + 1][2] > SHIPS[i][2] and SHIP_POWER[i + 1] > SHIP_POWER[i]
               for i in range(NSH - 1)), "each class must cost, produce and fight more than the one before"
    assert all(f"g{i}_{k}" in UPG_BY_ID for i in range(NSH) for k in range(5)), "every class has its upgrades"
    names = {r["names"][i] for r in ships.ROSTERS for i in (8, 9)}
    assert len(names) == 2 * len(ships.ROSTERS), "the big classes need a name of their own on every planet"
    old_save = core.SAVE
    d = tempfile.mkdtemp(prefix="space_miner_ships_")
    try:
        core.SAVE = os.path.join(d, "save.json")
        g = core.Game(load=False, sim=True)
        g.owned[0][0], g.owned[0][7] = 5, 3
        g.save()
        with open(core.SAVE) as f:
            data = json.load(f)
        data["owned"] = [row[:8] for row in data["owned"]]                    # what a save with eight classes holds
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        h = core.Game(load=True, sim=True)
        assert all(len(row) == NSH for row in h.owned) and h.owned[0][0] == 5 and h.owned[0][7] == 3 and h.owned[0][9] == 0
    finally:
        core.SAVE = old_save
        shutil.rmtree(d, ignore_errors=True)


def check_kuiper_belt():
    """The solar system ends at the Kuiper Belt (not at another star's planet), and a save that earned the old achievement
    for the last planet keeps it under its new name."""
    last = SITES[NSITE - 1]
    assert last["name"] == "Kuiper Belt" and last["kind"] == "kuiper" and not any("Proxima" in s["name"] for s in SITES)
    assert ships.style(NSITE - 1) == "comet" and "comet" in shipart.FAMILIES and ships.motion(NSITE - 1) == "sweep"
    for i in range(NSH):                                       # the comet orbit stays on screen for every class and ship
        for j in range(4):
            for tt in (0.0, 3.3, 9.9, 21.0):
                x, y, depth = ships.orbit(NSITE - 1, i, j, 4, tt, 1)
                assert abs(x) < 300 and abs(y) < 250 and abs(depth) <= 1.0, (i, j, tt, x, y)
    assert "Last Frontier" in core.ACH_BY_ID and "Interstellar" not in core.ACH_BY_ID
    old_save = core.SAVE
    d = tempfile.mkdtemp(prefix="space_miner_kuiper_")
    try:
        core.SAVE = os.path.join(d, "save.json")
        g = core.Game(load=False, sim=True)
        g.save()
        with open(core.SAVE) as f:
            data = json.load(f)
        data["ach"] = ["Interstellar", "Small Fleet"]
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        h = core.Game(load=True, sim=True)
        assert "Last Frontier" in h.ach and "Interstellar" not in h.ach and "Small Fleet" in h.ach
    finally:
        core.SAVE = old_save
        shutil.rmtree(d, ignore_errors=True)


def check_galaxy():
    """The Milky Way's data and the reach map agree with a brute-force check."""
    N = galaxy.N
    held = {0, 3, 5, 9, 14}
    inc = galaxy.Reach()
    inc.set({0}, 9.0)
    for k in (3, 5, 9, 14):
        inc.add(k)
    full = galaxy.Reach()
    full.set(held, 9.0)
    assert bytes(inc.reach) == bytes(full.reach) and bytes(inc.scan) == bytes(full.scan), "incremental reach differs"
    brute = {i for i in range(N) if any(galaxy.dist(h, i) <= 9.0 for h in held)}
    assert {i for i in range(N) if full.reach[i]} == brute, "reach differs from brute force"
    assert abs(SECTORS[galaxy.BY_NAME["Alpha Centauri"]]["d"] - 4.4) < 0.3 and abs(SECTORS[galaxy.BY_NAME["Sirius"]]["d"] - 8.6) < 0.3
    assert 450 < SECTORS[galaxy.BY_NAME["Betelgeuse"]]["d"] < 650                  # real distances are kept
    assert SECTORS[galaxy.BOSS]["name"] == "The Void Throne" and abs(SECTORS[galaxy.BOSS]["d"] - galaxy.GC_DIST) < 1
    assert N > 5000 and len({s["name"] for s in SECTORS}) == N, "system names are not unique"
    assert all(s["faction"] in FACTIONS and s["fx"] is not None and 2 < s["lp"] < 15 for s in SECTORS)
    assert all(0 <= n < N and n != k for k in range(N) for n in galaxy.LINKS[k]), "bad lane"
    assert all(SECTORS[galaxy.BY_NAME[nm]]["lp"] == galaxy.ORIGINAL_LP[nm] for nm in galaxy.ORIGINAL_LP)
    for r in range(23):                                                              # every jump drive level has targets from Sol
        assert core.ARMORY[core.JUMP][3] == 22
    assert galaxy.jump_range(22) > galaxy.GC_DIST + 5000, "the last jump drive level must cross the galaxy"
    # the game's own view of it: a campaign needs the target in range of a held system
    g = core.Game(load=False, sim=True)
    assert g.targets() and all(galaxy.dist(0, k) <= g.jump_range() + 1e-6 for k in g.targets())
    far = galaxy.BY_NAME["Betelgeuse"]
    assert not g.can_attack(far), "Betelgeuse should be out of range at jump level 0"
    g.armory[core.JUMP] = 15
    assert far in g.targets_set() and 0 in g.sync_reach().held


def check_fronts():
    """Several fleets at once: slots from the Command track, the fleet split between fronts, losses by share, the Fleet Admiral
    filling free fronts, and saves (including a save from before there could be several fronts)."""
    for c in (0.2, 0.5, 0.85, 0.95):
        assert abs(win_chance(core.power_for(1000.0, c), 1000.0) - c) < 1e-6, "power_for is not the inverse of win_chance"
    g = core.Game(load=False, sim=True)
    g.unlocked[2] = True
    g.owned = [[200000 >> i for i in range(NSH)] for _ in range(NSITE)]
    g.armory[core.JUMP] = 4
    g.recalc()
    fp = g.fleet_power()
    tg = sorted(g.targets(), key=lambda k: SECTORS[k]["lp"])
    assert g.max_fronts() == 1 and len(tg) >= 6 and g.galaxy_open
    assert all(g.sector_power(k) * 3 < fp for k in tg[:4]), "the test fleet should beat the weakest systems easily"
    assert g.attack_block(tg[0]) == "" and g.launch_share(tg[0]) < 0.5, "'Enough' should send only part of the fleet"
    assert g.start_campaign(tg[0]) and len(g.campaigns) == 1
    c = g.campaigns[0]
    assert abs(c["share"] - (1 - g.free_share())) < 1e-9 and abs(c["fp"] - fp * c["share"]) < 1e-6 * fp and c["chance"] >= core.COMMIT_ODDS - 1e-6
    assert g.attack_block(tg[1]) == "FRONTS FULL" and not g.start_campaign(tg[1]), "one front only without Command"
    assert g.attack_block(tg[0]) == "ATTACKING" and g.weakest_target() == tg[1]
    g.armory[core.COMMAND] = 2                                           # three fronts
    assert g.max_fronts() == 3 and g.free_fronts() == 2
    assert g.start_campaign(tg[1]) and g.start_campaign(tg[2]) and not g.start_campaign(tg[3])
    assert len(g.campaigns) == 3 and g.peak_fronts == 3 and g.free_fronts() == 0
    assert abs(g.free_share() - (1 - sum(c["share"] for c in g.campaigns))) < 1e-9 and 0 <= g.free_share() < 1
    # the whole fleet on one front leaves nothing for a second
    g.campaigns = []
    g.commit = 3
    assert g.start_campaign(tg[0]) and g.campaigns[0]["share"] == 1.0 and g.attack_block(tg[1]) == "NO FLEET FREE"
    g.campaigns, g.commit = [], 1                                        # 25% each: four fronts at most
    g.armory[core.COMMAND] = 7
    n = 0
    while g.start_campaign(tg[n]):
        n += 1
    assert n == 4 and abs(g.free_share()) < 1e-9, n
    # a campaign that arrives frees its front; losses scale with the share it carried
    g.commit = 0
    g.campaigns = []
    before = [sum(o) for o in g.owned]
    assert g.start_campaign(tg[0])
    c = g.campaigns[0]
    c["chance"] = 0.0
    c["t"] = c["dur"]
    g.step(0.01)
    assert not g.campaigns and tg[0] not in g.conquered and g.battles_lost == 1
    lost = 1 - sum(sum(o) for o in g.owned) / sum(before)
    assert 0 < lost < core.LOSE_LOSSES * c["share"] * 1.5 + 0.01, lost
    assert g.start_campaign(tg[0])
    g.campaigns[0]["chance"] = 1.0
    g.campaigns[0]["t"] = g.campaigns[0]["dur"]
    g.step(0.01)
    assert tg[0] in g.conquered and not g.campaigns and g.battles_won == 1
    # the Fleet Admiral fills every free front by itself
    g.techs.add("t31")
    g.recalc()
    g.auto_war, g.auto_odds = True, 0.85
    director.declare_war(g, SECTORS[tg[1]]["faction"], "player")
    war_t = [k for k in g.targets() if SECTORS[k]["faction"] in g.war]
    assert len(war_t) >= 3
    for _ in range(3):                                                   # one launch every few seconds
        g.step(3.2)
    assert len(g.campaigns) >= 2 and all(SECTORS[c["k"]]["faction"] in g.war and c["chance"] >= 0.84 for c in g.campaigns)
    assert len({c["k"] for c in g.campaigns}) == len(g.campaigns), "two fleets on one system"
    assert not director.can_sue(g, SECTORS[g.campaigns[0]["k"]]["faction"])[0]
    # saves: the fronts survive, and an old save with one campaign becomes one front with the whole fleet
    old_save = core.SAVE
    d = tempfile.mkdtemp(prefix="space_miner_fronts_")
    try:
        core.SAVE = os.path.join(d, "save.json")
        g.commit = 2
        g.save()
        h = core.Game(load=True, sim=True)
        assert [(c["k"], round(c["share"], 6)) for c in h.campaigns] == [(c["k"], round(c["share"], 6)) for c in g.campaigns]
        assert h.commit == 2 and h.peak_fronts == g.peak_fronts and h.armory[core.COMMAND] == 7
        with open(core.SAVE) as f:
            data = json.load(f)
        data.pop("campaigns")
        data.pop("commit")
        data["campaign"] = dict(k=tg[5], t=3.0, dur=50.0, fp=123.0, chance=0.8, src=0)
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        h = core.Game(load=True, sim=True)
        assert len(h.campaigns) == 1 and h.campaigns[0]["k"] == tg[5] and h.campaigns[0]["share"] == 1.0 and h.free_share() == 0.0
        data["armory"] = data["armory"][:core.COMMAND]                    # ...and a save from before the Command track exists
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        assert core.Game(load=True, sim=True).max_fronts() == 1
    finally:
        core.SAVE = old_save
        shutil.rmtree(d, ignore_errors=True)


def check_counter_offensives():
    """Enemies take systems back: a fleet at home defends them, fleets in the field do not, and several enemy fronts strike
    at once and share your fleet at home."""
    def setup():
        g = core.Game(load=False, sim=True)
        g.unlocked[2] = True
        g.owned = [[200000 >> i for i in range(NSH)] for _ in range(NSITE)]
        g.armory[core.JUMP] = 4
        g.armory[core.COMMAND] = 2
        g.recalc()
        g.grace = 0.0
        return g
    g = setup()
    tg = sorted(g.targets(), key=lambda k: SECTORS[k]["lp"])[:6]
    k = tg[2]
    g.conquered.add(k)
    foes = [n for n in galaxy.LINKS[k] if n not in g.conquered]
    assert foes, "the test system should border enemy systems"
    fac = SECTORS[foes[0]]["faction"]
    director.declare_war(g, fac, "enemy")
    g.incoming = []
    assert k in director.exposed_systems(g) and k in director.exposed_systems(g, fac) and 0 not in director.exposed_systems(g)
    tp = g.sector_power(k)
    for n in foes:                                                         # the strength of an offensive follows the system it starts from
        p = director.offensive_power(g, k, n, SECTORS[n]["faction"])
        assert director.OFFENSIVE_MIN * tp - 1e-9 <= p <= director.OFFENSIVE_MAX * tp * director.hostility_mult(g, SECTORS[n]["faction"]) + 1e-9
    g.garrison[k] = 0.5 * tp                                               # a thin garrison
    full = director.home_guard(g)
    assert full == director.HOME_GUARD * g.fleet_power() and director.home_guard(g, 2) == full / 2
    inc = director.schedule_offensive(g, target=k, lead=0)                 # lead 0: it hits at once
    assert inc and k in g.conquered and g.offensives_repelled == 1, "the fleet at home should hold the system"
    g.commit = 3                                                           # ...but with the whole fleet away on a campaign
    far = next(q for q in sorted(g.targets(), key=lambda q: SECTORS[q]["lp"]) if q != k and q not in g.conquered)
    assert g.start_campaign(far) and g.free_share() == 0.0 and director.home_guard(g) == 0.0
    assert director.aggression(g) >= 0.25
    inc = director.schedule_offensive(g, target=k, lead=0)
    assert inc and k not in g.conquered and k in g.lost_sectors and g.sectors_lost == 1, "an undefended system should fall"
    assert k in g.targets_set() or g.attack_block(k) in ("FRONTS FULL", "NO FLEET FREE"), "a lost system can be attacked again"
    # a wave: one offensive from each enemy faction that touches you, sharing the fleet at home
    g = setup()
    facs = set()
    for k in sorted(range(1, NSEC), key=lambda q: SECTORS[q]["d"]):         # grow a territory outwards until it touches 3 factions
        g.conquered.add(k)
        facs = {SECTORS[n]["faction"] for q in g.conquered for n in galaxy.LINKS[q] if n not in g.conquered}
        if len(facs) >= 3:
            break
    assert len(facs) >= 3, "the test territory should touch several factions"
    g.armory[director.INTEL] = 6                                           # attacks are announced, so they stay in flight
    for f in facs:
        director.declare_war(g, f, "enemy")
    g.incoming = []
    reachable = {f for f in facs if director.exposed_systems(g, f)}        # (Sol itself cannot be taken)
    n = director.schedule_strikes(g)
    offs = [i for i in g.incoming if i["kind"] == "offensive"]
    assert len(reachable) >= 2 and 2 <= n <= min(director.MAX_STRIKES, len(reachable)) and n == len(offs), (n, reachable)
    assert len({i["fac"] for i in offs}) == n                              # (a system two factions touch is attacked by only one)
    assert len({i["target"] for i in offs}) == n, "two offensives on one system"
    if n > 1:
        one = director.sector_defense(g, offs[0]["target"], strikes=1)
        assert director.sector_defense(g, offs[0]["target"], strikes=director.strikes_with(g, offs[0])) <= one


def selftest_step(app, g, frames, shot):
    if frames == 1:
        check_ship_art(app)
        check_galaxy()
        check_more_ships()
        check_kuiper_belt()
        check_fronts()
        check_counter_offensives()
        check_new_game_reset()
    if frames == 3:
        for _ in range(25):
            app.space_click()
        g.ore[0] = 1e4
    if frames == 6:
        shot("start")
        g.buy_mode = 1
        for i in range(3):
            g.buy_ship(0, i)
        g.ore[0] = 1e6
        g.credits = 1e6
        g.science = 1e3
        g.buy_building(0, 1); g.buy_building(0, 2)
        g.unlock_planet(1)
        assert g.unlocked[1]
        g.start_travel(1)
    if frames == 14:
        shot("travel")
    if frames == 16:
        app.toggle_fullscreen()                      # the dummy video driver refuses; that must not crash
        assert not app.fullscreen
        app.tab = T_AWARDS
        app.awards_cat = "Stats"                     # draw the settings page once
    if frames == 18:
        app.awards_cat = "All"
        app.tab = T_SHIPS
    if frames == 20:                                 # other canvas sizes: re-layout and draw every view
        for res in ("1920x1080", "1600x720", "2560x1440", "1280x720"):
            app.set_resolution_choice(res)
            assert (W, H) == tuple(int(v) for v in res.split("x")) and app.scr.get_size() == (W, H), res
            assert PANEL.right <= W and PANEL.bottom <= H and 0 < CX < PANEL.x and 0 < CY < H
            for view in ("system", "galaxy"):
                for tab in range(len(app.tabs)):
                    app.view, app.tab = view, tab
                    app.update(0.016)
                    app.draw(app.scr, app_fonts())
        app.view, app.tab = "system", T_SHIPS
        app.set_resolution_choice("auto")
        assert (W, H) == choose_resolution("auto", False)
    if frames == 40:
        g.ore = [1e15 * SC[i] for i in range(NSITE)]
        g.run_ore = list(g.ore); g.all_norm = g.run_norm = 1e20
        g.credits = 1e15; g.science = 1e12
        for k in range(NSITE):
            g.unlocked[k] = True
            g.owned[k] = [12 + k, 11, 10, 9, 8, 7, 6, 5, 4, 3]
            g.bld[k] = [5 + k, 6, 7, 3, 4, 2]
        g.projects = {0, 1, 2}
        g.recalc()
        g.cur = 7
        for t in TECHS[:12]:
            g.research(t[0])
        app.tab = T_SHIPS
    if frames == 44:
        shot("saturn_ships")
        app.tab = T_PLANETS
    if frames == 46:
        shot("planets")
        app.tab = T_COLONY
    if frames == 48:
        shot("colony")
        app.tab = T_TECH
    if frames == 50:
        shot("tech")
        app.tab = T_UPG
    if frames == 52:
        shot("upgrades")
        app.tab = T_WARP
        g.event = g.pick_event(); g.event["left"] = 60
    if frames == 54:
        shot("event")
        g.resolve_event(g.event["opts"][0][1])
        app.scroll[T_WARP] = 300
    if frames == 56:
        shot("warp")
        app.scroll[T_WARP] = 0
        for q in g.quests:
            q["base"] = -1e30
        for _ in range(3):
            g.claim_quest(0)
        for _ in range(80):
            g.event = g.pick_event()
            for _, fn in g.event["opts"]:
                g.resolve_event(fn)
        for p in range(NSITE):
            g.buy_project(p)
        g.buy_mode = 0
        for p in range(NSITE):
            for b in range(NB):
                g.buy_building(p, b)
            g.buy_ship(p, 3)
            g.buy_all_upgrades(p)
        assert g.warp_gain() > 0
        app.do_warp(); app.do_warp()
        assert g.warps == 1 and sum(g.owned[3]) == 0 and g.unlocked[11], "warp failed"
    if frames == 60:
        shot("warpfx")
    if frames == 62:
        # galaxy: campaign, map view, raid
        g.owned = [[40 + k, 30, 20, 10, 5, 2, 1, 0, 0, 0] for k in range(NSITE)]
        g.conquered = {0, 1, 2}
        g.recalc()
        app.tab = T_GALAXY
        app.view = "galaxy"
        app.sel_sector = 3
        assert g.start_campaign(3), "campaign failed to start"
        assert "pirates" in g.war and g.wars_declared == 1, "invading did not declare war"
    if frames == 64:
        g.armory[director.INTEL] = 6
        g.credits = 1e15
        director.schedule_raid(g, tier=1, lead=60.0)
        director.schedule_raid(g, tier=2, lead=90.0)
        director.schedule_offensive(g, lead=70.0)
        assert len(g.incoming) == 3
        for inc in g.incoming:
            assert director.fortify(g, inc["id"]) or director.intel(g) < 2
    if frames == 66:
        shot("galaxy_map")
    if frames == 66:
        g.war["pirates"]["since"] = g.play_time - 700                 # old enough to sue for peace
        assert director.can_sue(g, "pirates")[0] is False             # ...but the campaign against them is still running
        g.armory[core.JUMP] = 14                                      # a range of ~1,100 ly reaches other factions' systems
        other = next(k for k in g.targets() if SECTORS[k]["faction"] not in g.war)
        app.attack(other)                                             # the first click only asks for confirmation
        assert SECTORS[other]["faction"] not in g.war and app.war_confirm > 0
    if frames == 67:
        fv = app.fv                                  # zoom, pan and click the galaxy view
        fv.focus(3, snap=True)
        assert fv.zt >= 2.0 and "closeup" in g.flags and fv.s > fv.fit_s
        fv.zoom_at((300, 450), 1.2)
        fv.down((300, 450)); fv.move((330, 470)); fv.up((330, 470))
        for key in (pygame.K_LEFT, pygame.K_PLUS, pygame.K_MINUS):
            assert fv.key(key)
        fv.focus(3, snap=True)
        app.draw(app_scr(), app_fonts())                              # (clicks use where the systems were drawn)
        fv.click(fv.pos(3))
        assert app.sel_sector == 3, app.sel_sector
        assert all(frontview.hrand(i, 7, 3) < 1.0 for i in range(300000))    # it once returned exactly 1.0 and crashed the close-up
    if frames == 68:
        shot("front")
        app.fv.fit()
        assert app.galaxy_key(pygame.K_z) and app.fv.zt > 1.3
        app.view = "system"
        g.raid(g.cur, force=True)
    if frames == 72:
        shot("raid")
    if frames == 74:
        for c in g.campaigns:
            c["t"] = c["dur"]
        for inc in list(g.incoming):
            inc["t"] = inc["eta"] - 0.1
    if frames == 76 and app.dev:
        app.tab = T_DEV
        app.draw(app_scr(), app_fonts())
        shot("dev")
        for title, items in devtools.sections(app):
            for label, fn, active in items:
                if "Wipe" in label or "Lock ALL" in label or "Relock" in label or "Reset galaxy" in label or label.startswith("Test:"):
                    continue
                fn()
        g.event = None
        app.dev_state.infinite = False
        devtools.tick(app, 0.05)
    if frames == 78:
        g.conquered = set(range(NSEC))
        g.recalc()
        app.tab = T_WARP
        app.warp_view = "ascend"
        assert g.can_ascend()
    if frames == 79:
        shot("ascension")
    if frames == 80:
        c0 = g.cycle
        app.do_ascend(); app.do_ascend()
        assert g.cycle == c0 + 1 and g.stardust > 0 and 0 in g.conquered and sum(g.owned[3]) == 0, "ascension failed"
    if frames == 83:
        shot("ascend_fx")
        before = g.stardust
        for pk in core.STARDUST_PERKS:
            if g.buy_sd_perk(pk[0]):
                break
    if frames == 90:
        g.hard_reset()


if __name__ == "__main__":
    main()
