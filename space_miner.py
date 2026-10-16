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

import colonies
import core
import galaxy
import gamelog
import resources
import generals
import blackhole
import icons
import shipart
import ships
import sysview
import devtools
import director
import front
import frontview
import gfx
import sounds
import touch
import worlds
import worldview
from version import __version__
from core import (BMAX, BUILDINGS, NB, NSH, NSOL, PERKS, PROJECTS, SHIPS, SITES, TECHS, TECH_BY_ID,
                  UPGRADES, ACHIEVEMENTS, ACH_BY_ID, ACH_CATS, TIER_BONUS, TIER_NAMES, QUEST_TXT, fmt, geo_cost,
                  SECTORS, NSEC, FACTIONS, ARMORY, COMMIT_MODES, armory_cost, win_chance,
                  STARDUST_PERKS, sd_bonus)
from gfx import glow, scale_c, lerp_c

BASE_W, BASE_H = 1280, 720
W, H = BASE_W, BASE_H
PANEL = pygame.Rect(660, 104, 600, 608)
worldview.PANEL = PANEL                         # the same rectangle, resized in place by apply_layout
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
STRIP_X0, STRIP_DX = 142, 42
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
        self.gal_page = 0                    # the Galaxy tab's page: war room / generals / defence
        self.pick = None                     # picking a system on the map for a general's orders: dict(idx, field)
        self._gal_cache = {}
        self.raiders = []
        self.hover_sector = None
        self.warp_view = "warp"
        self.ascend_fx = 0.0
        self.ascend_len, self.ascend_boom = 3.4, False       # how long the Ascension effect lasts, and whether the bomb went off in it
        self.ascend_confirm = 0.0
        self.ascend_cycle = 1
        self.ach_new = False
        self.cl_filter, self.cl_cache, self.cl_ready, self.cl_ready_t = "ready", None, False, -1      # the Colonies page of the Planets tab
        self.strip_off, self.strip_pos, self.strip_cur = 0, {}, None     # the planet strip: first planet shown, x of each, the planet last scrolled to
        self.pl_page, self.wf_group, self.wf_sys = 0, "all", None      # the Planets tab: page, the filter of the worlds page
        self.wsel, self.w_seen, self.w_cache = None, 0, None           # the selected world, how many worlds you have looked at
        self.w_sig, self.w_known, self.w_hab = None, None, False       # the systems held when the discovery toasts last looked; a habitable world found?
        self.awards_cat = "All"
        self.fps = 0.0
        self.can_scale = False               # True when the window is resizable and scales the game to fit
        self.fullscreen = False
        self.test_fault = 0
        self.scr = None
        self.res_override = None            # --resolution WxH from the command line (not saved)
        self.war_confirm = 0.0
        self.war_confirm_k = None
        self.q, self.q_work, self.q_n, self.q_time, self.q_slow, self.q_fast = 0, 0.0, 0, 0.0, 0, 0.0      # fast mode's quality level (0 full ... 3 least) and what decides it
        self.raid_rot = {}
        self.fb, self.fb_key = None, None                              # the baked backdrop of the fast (phone) mode and what it was baked for
        self.pc, self.pc_t, self.pc_dirty, self.pc_key, self.pc_btns = None, -9.0, True, None, []     # the panel, drawn a few times a second (fast mode)
        self.txt_cache, self.ast_rot = {}, {}                          # rendered texts, and asteroids turned to an angle
        self.sys_k, self.sys_sel = None, None                           # the system view: the star shown and the selected body
        self.hud_btns = []
        self.orb_hits, self.orb_btns, self.orb_hover = [], [], None     # ...what was drawn last frame, for the clicks
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
        self.art = {}                        # (what, site id, size) -> picture of a planet, made on first use (see site_sprite)
        for k in range(NSOL):                # the solar planets are painted at start-up, a colony world's picture when it is first drawn
            self.site_sprite(k)
            self.site_icon(k, 32), self.site_icon(k, 50)
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

    def fam(self, p):
        """The ship family of planet p (a solar planet's own, a colony's that of its kind of world)."""
        return self.g.sites[p]["family"]

    def site_sprite(self, p):
        """The picture of planet p as the planet view shows it: a solar planet is painted by gfx.make_planet, a colony world by
        gfx.make_world."""
        s = self.g.sites[p]
        key = ("big", s["id"])
        pic = self.art.get(key)
        if pic is None:
            if s.get("colony"):
                size = 2 * PLANET_R + 2
                pic = gfx.make_world(s["wkind"], s["seed"], round(size / 0.58) if s["ring"] else size, s["ring"])
            else:
                pic = gfx.make_planet(PLANET_R, s["kind"], s["col"], 100 + p * 13)
            self.art[key] = pic
        return pic

    def site_icon(self, p, size):
        """A small picture of planet p (the strip uses 32 pixels, the lists 50)."""
        s = self.g.sites[p]
        key = ("icon", s["id"], size)
        pic = self.art.get(key)
        if pic is None:
            if s.get("colony"):                                       # painted small, not scaled down from the big picture
                pic = gfx.make_world(s["wkind"], s["seed"], size, s["ring"])
            else:
                pic = pygame.transform.smoothscale(self.site_sprite(p), (size, size))
            self.art[key] = pic
        return pic

    def site_dark(self, p, size):
        """The picture of a planet you cannot go to: dark."""
        key = ("dark", self.g.sites[p]["id"], size)
        pic = self.art.get(key)
        if pic is None:
            pic = self.site_icon(p, size).copy()
            pic.fill((24, 28, 46, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.art[key] = pic
        return pic

    def ship_color(self, p, i):
        """The class colour (the accent every hull carries, and the colour of its engine glow and laser). On the planets
        with their own palette it is pulled towards that palette's glow."""
        pal = ships.palette(self.fam(p))
        col = SHIPS[i][3] if pal is None else lerp_c(SHIPS[i][3], pal[3], 0.4)
        return col if p < NSOL else lerp_c(col, self.g.sites[p]["col"], 0.3)         # a colony's fleet takes a hint of its world's colour

    def ship_sprite(self, p, i, icon=False):
        """The sprite of ship class i on planet p (every planet's fleet looks different)."""
        size = 46 if icon else round((26 + i * 2) * (1.3 if i >= gfx.FLEET_TIER else 1.0) * ships.scale(self.fam(p)))
        key = (self.g.sites[p]["id"], i, size)
        spr = self.ship_cache.get(key)
        if spr is None:
            col = SHIPS[i][3] if p < NSOL else lerp_c(SHIPS[i][3], self.g.sites[p]["col"], 0.35)
            spr = self.ship_cache[key] = gfx.make_ship(i, col, size, ships.style(self.fam(p)), ships.palette(self.fam(p)))
        return spr

    def ship_icon(self, p, i):
        return self.ship_sprite(p, i, True)

    def get_ast_sprites(self, p):
        sid = self.g.sites[p]["id"]
        if sid not in self.ast_sprites:
            oc = self.g.sites[p]["ocol"]
            tint = lerp_c((255, 255, 255), oc, 0.45)
            seed = p if p < NSOL else self.g.sites[p]["seed"] % 997
            self.ast_sprites[sid] = [gfx.make_asteroid(sz, seed * 31 + v * 7 + sz, tint) for sz in (34, 44, 56) for v in range(3)]
        return self.ast_sprites[sid]

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
        oc = self.g.sites[g.cur]["ocol"]
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
        self.burst(x, y, self.g.sites[self.g.cur]["ocol"], 22)
        a["dead"] = 3.5
        a["hp"] = 0.0

    def space_click(self):
        if self.view == "galaxy" and self.g.galaxy_open:               # on the map Space launches the best attack
            self.fv.attack_best()
            return
        alive = [a for a in self.asts if a["hp"] > 0]
        if alive:
            a = random.choice(alive)
            x, y, _ = self.ast_pos(a)
            self.mine_at((x, y), a)

    def mouse_down(self, pos, touch=False):
        g = self.g
        self.pc_dirty = True                           # (fast mode: the panel is drawn again at once after a click or a tap)
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
        for rect, fn in self.hud_btns:
            if rect.inflate(grow, grow).collidepoint(pos):
                fn()
                return
        if self.view == "galaxy":
            self.fv.click(pos)
            return
        if self.view == "orbit":
            sysview.click(self, pos, grow)
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

    def strip_entries(self):
        """The planets the strip shows: the solar system, then the colony worlds you have settled."""
        g = self.g
        return list(range(g.nsite))

    def strip_cap(self):
        """How many planets fit in the strip."""
        return max(4, (PANEL.x - 34 - STRIP_X0) // STRIP_DX + 1)

    def strip_click(self, k):
        g = self.g
        if k == -1:                                 # galaxy map button
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
        if k == -4:                                 # the star system button
            sysview.toggle(self)
            return
        if k in (-2, -3):                           # the strip's arrows
            self.strip_off = max(0, self.strip_off + (-4 if k == -2 else 4))
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
        self.pc_dirty = True

    def attack(self, k):
        """ATTACK / DECLARE WAR on the Galaxy tab: invading a faction at peace needs a second click."""
        g = self.g
        if SECTORS[k]["faction"] not in g.war and not (self.war_confirm > 0 and self.war_confirm_k == k):
            self.war_confirm, self.war_confirm_k = 8.0, k
            return
        self.war_confirm = 0.0
        g.start_campaign(k)

    @property
    def fast(self):
        """Fast mode, for slow machines (phones draw in software): the backdrop with its stars, glow, vignette and panel is baked into one
        picture, the panel is drawn a few times a second and the game runs at 30 frames a second. The Stats page chooses: Auto (the
        phone's touch interface), On or Off."""
        mode = self.g.settings.get("perf", "auto")
        return mode == "on" or (mode == "auto" and resources.TOUCH)

    QUALITY_CAP = (99, 99, 3, 1)           # the most ships of a class drawn round the planet at each quality level

    def perf_sample(self, work):
        """The time (seconds) one frame's update and drawing took, from the main loop. In fast mode the game keeps itself smooth: when two
        spells of frames in a row average more than 26 ms (that is under 30 a second with nothing to spare; a spell is 30 frames or 0.8
        seconds of work) it draws less - first no weapon beams, sparkles or long trails, then at most three ships of a class, then one - and
        when frames are quick (under 11 ms) for half a minute it draws more again. The Stats page's Show FPS shows the level (Q0 is
        everything)."""
        if not self.fast:
            self.q = 0
            return
        self.q_work += work
        self.q_n += 1
        self.q_time += self.dt
        if self.q_n < 30 and self.q_work < 0.8:
            return
        avg, span = self.q_work / self.q_n, self.q_time
        self.q_work, self.q_n, self.q_time = 0.0, 0, 0.0
        if avg > 0.026:
            self.q_slow += 1
            self.q_fast = 0.0
            if self.q_slow >= 2 and self.q < 3:
                self.q, self.q_slow = self.q + 1, 0
        elif avg < 0.011 and self.q > 0:
            self.q_fast += span
            self.q_slow = 0
            if self.q_fast >= 30.0:
                self.q, self.q_fast = self.q - 1, 0.0
        else:
            self.q_slow, self.q_fast = 0, 0.0

    def cycle_perf(self):
        st = self.g.settings
        nxt = {"auto": "on", "on": "off", "off": "auto"}[st.get("perf", "auto")]
        st["perf"] = nxt
        self.fb_key = None
        self.pc_dirty = True
        self.g.toast("Fast mode: " + {"auto": "automatic (on for phones)", "on": "always on", "off": "off"}[nxt], 3)

    def fast_backdrop(self):
        """The whole backdrop of the planet and system views in one picture: the sky with its stars and the planet's glow, the vignette and the
        side panel's background. Made once for what is on screen (it takes a few milliseconds) and then drawn with one plain blit."""
        g = self.g
        gal = self.view == "galaxy"
        key = (W, H, id(self.bg), gal, self.panel_visible(), None if gal else g.sites[g.cur]["id"] if self.view == "system" else 0)
        if self.fb is None or self.fb_key != key or self.fb.get_size() != (W, H):
            surf = (self.gal_backdrop if gal else self.bg).copy()
            if not gal:
                for x, y, d, ph, col in self.stars:                         # the stars, still (they do not twinkle in fast mode)
                    if d >= 1.0:
                        r = 4 if d < 1.5 else 6
                        surf.blit(glow(r, scale_c(col, 0.8)), (x - r, y - r), special_flags=ADD)
                    else:
                        v = int(80 + 110 * 0.8 * d)
                        surf.set_at((int(x), int(y)), (v, v, min(255, v + 25)))
                if self.view == "system":
                    surf.blit(glow(280, scale_c(g.sites[g.cur]["col"], 0.22)), (CX - 280, CY - 280), special_flags=ADD)
            surf.blit(self.vig, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            if self.panel_visible():
                surf.blit(self.panel_bg, (PANEL.x - 12, 4))
            self.fb, self.fb_key = surf.convert(), key
        return self.fb

    def draw_panel_fast(self, scr, fonts):
        """The side panel in fast mode: it is drawn on a picture of its own a few times a second (or at once when you touch something or scroll)
        and that picture is what each frame draws; the buttons it made stay as they were."""
        key = (self.tab, self.scroll[self.tab], PANEL.x, PANEL.w, W, H)
        if self.pc is None or self.pc.get_size() != (W, H) or self.pc_dirty or key != self.pc_key or self.t - self.pc_t >= 0.12 or self.t < self.pc_t:
            if self.pc is None or self.pc.get_size() != (W, H):
                self.pc = pygame.Surface((W, H)).convert()
            area = pygame.Rect(PANEL.x - 12, 0, W - (PANEL.x - 12), H)
            self.pc.blit(self.fast_backdrop(), area.topleft, area)
            n0 = len(self.buttons)
            self.draw_panel(self.pc, fonts)
            self.pc_btns = self.buttons[n0:]
            self.pc_t, self.pc_dirty, self.pc_key = self.t, False, key
        else:
            self.buttons.extend(self.pc_btns)
        area = pygame.Rect(PANEL.x - 12, 0, W - (PANEL.x - 12), H)
        scr.blit(self.pc, area.topleft, area)

    def orbit_area(self):
        """The part of the window the system view uses: everything left of the side panel and above the planet strip."""
        return pygame.Rect(0, 0, PANEL.x - 6, STRIP_Y - 30)

    def system_key(self, key):
        """S opens the star system view (or goes back to the planet); in it the arrow keys step through the bodies."""
        if key == pygame.K_s:
            sysview.toggle(self)
            return True
        if self.view == "orbit" and key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            sysview.select_next(self, 1 if key in (pygame.K_RIGHT, pygame.K_DOWN) else -1)
            return True
        return False

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
        if not self.g.event and self.view in ("galaxy", "orbit"):
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
            f"view={self.view} tab={self.tabs[self.tab] if 0 <= self.tab < len(self.tabs) else self.tab} planet={self.g.sites[g.cur]['name']} "
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
        worldview.news_toasts(self)
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
                self.rings.append([CX, CY, 0.0, self.g.sites[data]["col"]])
                self.burst(CX, CY, self.g.sites[data]["col"], 40)
                self.snd.play("unlock")
            elif kind == "bomb":
                self.rings.append([CX, CY, 0.0, (255, 170, 120)])
                self.burst(CX, CY, (255, 170, 120), 40)
                self.snd.play("project")
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
                self.ascend_boom = bool(data.get("boom"))
                self.ascend_len = 5.0 if self.ascend_boom else 3.4
                self.ascend_fx = self.ascend_len
                self.ascend_cycle = data["cycle"]
                self.view = "system"
                self.warp_view = "ascend"
                self.snd.play("ascend")
                self.add_banner(dict(header="ASCENSION", title=f"Cycle {data['cycle']} begins",
                                     sub="The bomb went off: Stardust x%g." % blackhole.SD_MULT if self.ascend_boom else "The universe resets - you keep your Stardust.",
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
    def rendered(self, font, text, col):
        """A text as a picture, kept: drawing the same words again (most of the screen, most frames) costs a blit and no more."""
        key = (id(font), text, col)
        img = self.txt_cache.get(key)
        if img is None:
            if len(self.txt_cache) > 1500:
                self.txt_cache.clear()
            img = self.txt_cache[key] = font.render(text, True, col)
        return img

    def txt(self, surf, font, text, pos, col=(235, 235, 245), anchor="topleft", shadow=False):
        if shadow:
            sh = self.rendered(font, text, (0, 0, 8))
            surf.blit(sh, sh.get_rect(**{anchor: (pos[0] + 2, pos[1] + 2)}))
        img = self.rendered(font, text, col)
        r = img.get_rect(**{anchor: pos})
        surf.blit(img, r)
        return r

    # ---------------- drawing: world -----------------
    def draw(self, scr, fonts):
        g = self.g
        self.buttons = []
        self.modal_buttons = []
        self.hud_btns = []                             # buttons over the scene (not in the panel)
        fast = self.fast
        if fast:                                       # one picture: sky, stars, glow, vignette and the panel's background
            scr.blit(self.fast_backdrop(), (0, 0))
        elif self.view == "galaxy":                    # a different place: the star chart, not the planet's sky
            scr.blit(self.gal_backdrop, (0, 0))
        else:
            scr.blit(self.bg, (0, 0))
            self.draw_stars(scr)
        site = self.g.sites[g.cur]
        if self.view == "system" and not fast:
            scr.blit(glow(280, scale_c(site["col"], 0.22)), (CX - 280, CY - 280), special_flags=ADD)
        if g.buff_mult > 1.5 and self.view == "system":
            k = round(0.6 + 0.4 * math.sin(self.t * 6), 1)
            scr.blit(glow(260, scale_c((140, 100, 20), k)), (CX - 260, CY - 260), special_flags=ADD)
        if self.view == "galaxy":
            self.fv.draw(scr, fonts)
        elif self.view == "orbit":
            sysview.draw(self, scr, fonts)
        else:
            self.draw_scene(scr)
            self.draw_raiders(scr)
            self.draw_crate(scr)
        self.draw_fx(scr, fonts[1])
        if not fast:
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
            if fast:
                self.draw_panel_fast(scr, fonts)
            else:
                self.draw_panel(scr, fonts)
        if g.settings.get("show_fps"):
            self.txt(scr, fonts[3], f"{self.fps:.0f} FPS" + (f"  Q{self.q}" if self.fast else ""), (PANEL.x - 22, H - 66), (255, 220, 140), "topright", True)
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
        site = self.g.sites[p]
        behind, front = [], []
        for a in self.asts:
            if a["hp"] <= 0:
                continue
            x, y, ang = self.ast_pos(a)
            (behind if math.sin(ang) < 0 else front).append(("a", a, x, y))
        for i in range(NSH):
            n = min(ships.shown(self.fam(p), g.owned[p][i]), self.QUALITY_CAP[self.q] if self.fast else 99)
            d = 1 if i % 2 == 0 else -1
            for j in range(n):
                dx, dy, depth = ships.orbit(self.fam(p), i, j, n, self.t, d)
                hd = ships.heading(self.fam(p), i, j, n, self.t, d)
                (behind if depth < 0 else front).append(("s", (i, j, hd, d), CX + dx, CY + dy))
        for item in behind:
            self.draw_item(scr, item)
        spr = self.site_sprite(p)
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
        style = ships.style(self.fam(p))
        for item in (behind + front if not (self.fast and self.q >= 1) else ()):       # (the weapon beams are the first thing to go when frames are slow)
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
            q, zq = (int(a["rot"] / 6) % 60 if self.q < 3 else 0), int(round(sc * 20))     # (turned in steps of 6 degrees and 0.05 of size, kept)
            key = (g.sites[g.cur]["id"], a["spr"], q, zq)
            img = self.ast_rot.get(key)
            if img is None:
                if len(self.ast_rot) > 4000:
                    self.ast_rot.clear()
                img = self.ast_rot[key] = pygame.transform.rotozoom(spr, q * 6, zq / 20)
            scr.blit(img, img.get_rect(center=(x, y)))
            oc = self.g.sites[g.cur]["ocol"]
            for off in ((0.0, 2.4) if not (self.fast and self.q >= 1) else ()):
                ga = math.radians(a["rot"]) + off
                gx = x + math.cos(ga) * spr.get_width() * 0.2 * sc
                gy = y + math.sin(ga) * spr.get_width() * 0.2 * sc
                f = round(0.55 + 0.45 * math.sin(self.t * 4 + a["ph"] + off), 1)         # (a few steps: every glow made is kept, so it must not be a new one every frame)
                scr.blit(glow(7, scale_c(oc, 0.9 * f)), (gx - 7, gy - 7), special_flags=ADD)
            return
        i, j, ta, d = data
        col = self.ship_color(g.cur, i)
        for tc in ((1, 2, 3) if (not self.fast or self.q == 0) else (1,) if self.q == 1 else ()):
            bx = x - math.cos(ta) * tc * 7
            by = y - math.sin(ta) * tc * 7
            scr.blit(glow(7 - tc, scale_c(col, 0.55 / tc)), (bx - (7 - tc), by - (7 - tc)), special_flags=ADD)
        q = int(round(-math.degrees(ta) / 10)) % 36
        key = (g.sites[g.cur]["id"], i, q)
        spr = self.ship_rot.get(key)
        if spr is None:
            spr = self.ship_rot[key] = pygame.transform.rotate(self.ship_sprite(g.cur, i), q * 10)
        scr.blit(spr, spr.get_rect(center=(x, y)))

    def draw_crate(self, scr):
        c = self.g.crate
        if not c:
            return
        x, y = c["x"], c.get("yy", c["y"])
        k = round(0.7 + 0.3 * math.sin(self.t * 8), 1)
        scr.blit(glow(46, scale_c((200, 150, 30), k)), (x - 46, y - 46), special_flags=ADD)
        scr.blit(self.crate_spr, self.crate_spr.get_rect(center=(x, y)))
        c["rect"] = pygame.Rect(0, 0, 58, 58)
        c["rect"].center = (x, y)

    def draw_fx(self, scr, med):
        for r in self.rings:
            t = r[2] / 0.7
            pygame.draw.circle(scr, scale_c(r[3], 1 - t), (int(r[0]), int(r[1])), int(12 + 110 * t), 2)
        for p in (self.parts if not (self.fast and self.q >= 3) else ()):
            k = round(max(0.0, min(1.0, p[4] * 1.6)), 1)                   # (a few steps of brightness: see draw_item)
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
        to = self.g.sites[tr["to"]]
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
        """The planet whose unlock the progress bar in the corner follows: the next solar planet, then the colony world you are
        closest to being able to settle."""
        g = self.g

        def progress(k):
            ores, cr = g.unlock_cost(k)
            fr = [min(1.0, g.ore[p] / amt) for p, amt in ores if amt > 0]
            if cr > 0:
                fr.append(min(1.0, g.credits / cr))
            return min(fr) if fr else 1.0
        k = next((i for i in range(1, NSOL) if not g.unlocked[i]), None)
        if k is not None:
            return k, progress(k)
        return None

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
            self.txt(scr, tiny, f"Campaigns {len(g.campaigns)}  -  defence {g.defence * 100:.0f}%  armies {generals.army_total(g) * 100:.0f}%",
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
        if self.view == "orbit":
            sysview.draw_hud(self, scr, fonts)
            return
        big, med, sm, tiny = fonts
        g = self.g
        p = g.cur
        site = self.g.sites[p]
        oc = site["ocol"]
        if g.cycle > 1:
            self.txt(scr, tiny, f"CYCLE {g.cycle}", (22, 2), (255, 215, 120), shadow=True)
        title = site["name"] if site.get("colony") else site["name"].upper()          # "TRAPPIST-1 e": the planet's letter stays small
        self.txt(scr, med, title, (22, 12), site["col"], shadow=True)
        self.txt(scr, tiny, f"mining {site['ore']}", (22 + med.size(title)[0] + 10, 18), (170, 175, 200), shadow=True)
        sx = 22 + med.size(title)[0] + 10 + tiny.size(f"mining {site['ore']}")[0] + 14
        srect = pygame.Rect(sx, 12, 70, 22)
        hot = srect.collidepoint(self.mouse) and not resources.TOUCH
        pygame.draw.rect(scr, (60, 84, 150) if hot else (24, 32, 66), srect, border_radius=7)
        pygame.draw.rect(scr, (120, 150, 215), srect, 1, border_radius=7)
        self.txt(scr, tiny, "SYSTEM", srect.center, (225, 235, 255), "center")
        self.hud_btns.append((srect, lambda: sysview.open_system(self)))
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
            self.txt(scr, tiny, f"Next {'planet' if k < NSOL else 'colony'}: {self.g.sites[k]['name']}", (22, y + 2), (190, 196, 220), shadow=True)
            pygame.draw.rect(scr, (24, 28, 56), (22, y + 20, 150, 6), border_radius=3)
            pygame.draw.rect(scr, self.g.sites[k]["col"], (22, y + 20, 150 * fr, 6), border_radius=3)
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
                    where = f" -> {SECTORS[inc['target']]['name']}{frontview.colony_tag(g, inc['target'])}" if inc["kind"] == "offensive" else " -> " + ", ".join(
                        self.g.sites[q]["name"] for q in inc["targets"] if q < len(self.g.sites))
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
        x0 = STRIP_X0
        ents, cap = self.strip_entries(), self.strip_cap()
        over = len(ents) > cap
        n_show = cap - 2 if over else len(ents)                   # when it does not all fit, an arrow takes the first and last place
        if over:
            if self.strip_cur != g.cur and g.cur in ents:         # scroll to the planet you travelled to
                i = ents.index(g.cur)
                self.strip_off = max(min(self.strip_off, i), i - n_show + 1)
            self.strip_off = max(0, min(self.strip_off, len(ents) - n_show))
        else:
            self.strip_off = 0
        self.strip_cur = g.cur
        shown = ents[self.strip_off:self.strip_off + n_show]
        slots = len(shown) + (2 if over else 0)
        pygame.draw.line(scr, (34, 40, 78), (x0, STRIP_Y), (x0 + (slots - 1) * STRIP_DX, STRIP_Y), 2)
        nxt = next((i for i in range(1, NSOL) if not g.unlocked[i]), None)
        hover = None
        self.strip_pos = {}
        if over:                                                  # the arrows
            for slot, k, label, ok in ((0, -2, "<", self.strip_off > 0), (slots - 1, -3, ">", self.strip_off + n_show < len(ents))):
                ax = x0 + slot * STRIP_DX
                rect = pygame.Rect(ax - 17, STRIP_Y - 17, 34, 34)
                self.strip_hits.append((rect, k))
                hot = ok and rect.collidepoint(self.mouse) and self.mouse[0] < PANEL.x - 10
                pygame.draw.circle(scr, (40, 50, 96) if hot else (22, 26, 52), (ax, STRIP_Y), 16)
                pygame.draw.circle(scr, (140, 160, 220) if ok else (60, 66, 100), (ax, STRIP_Y), 16, 2)
                self.txt(scr, med, label, (ax, STRIP_Y - 1), (235, 240, 255) if ok else (90, 96, 130), "center")
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
        # the star system button: the solar system, or the system of the planet you are on
        sx = 94
        srect = pygame.Rect(sx - 19, STRIP_Y - 19, 38, 38)
        self.strip_hits.append((srect, -4))
        sact = self.view == "orbit"
        scol = (255, 215, 110) if sact else (130, 170, 255)
        if sact:
            scr.blit(glow(26, scale_c(scol, 0.5)), (sx - 26, STRIP_Y - 26), special_flags=ADD)
        pygame.draw.circle(scr, (14, 18, 40), (sx, STRIP_Y), 19)
        pygame.draw.circle(scr, scol, (sx, STRIP_Y), 19, 2)
        scr.blit(glow(10, (110, 84, 30)), (sx - 10, STRIP_Y - 10), special_flags=ADD)
        pygame.draw.circle(scr, (255, 214, 120), (sx, STRIP_Y), 4)
        for rr, sp, col in ((8, 1.7, (150, 205, 255)), (13, 1.0, (255, 170, 120))):          # two planets on their orbits
            pygame.draw.circle(scr, scale_c(scol, 0.45), (sx, STRIP_Y), rr, 1)
            a = self.t * sp + rr
            pygame.draw.circle(scr, col, (int(sx + rr * math.cos(a)), int(STRIP_Y + rr * math.sin(a))), 2)
        if worldview.colony_ready(self) or any(g.can_unlock(i) for i in range(1, NSOL)):
            pygame.draw.circle(scr, (255, 220, 90), (sx + 14, STRIP_Y - 15), 3)
        if srect.collidepoint(self.mouse) and self.mouse[0] < PANEL.x - 10:
            hover = -4
        for i, k in enumerate(shown):
            x = x0 + (i + (1 if over else 0)) * STRIP_DX
            self.strip_pos[k] = x
            rect = pygame.Rect(x - 19, STRIP_Y - 19, 38, 38)
            self.strip_hits.append((rect, k))
            site = self.g.sites[k]
            if g.unlocked[k]:
                if k == g.cur and self.view == "system":
                    scr.blit(glow(30, scale_c(site["col"], 0.8)), (x - 30, STRIP_Y - 30), special_flags=ADD)
                    pygame.draw.circle(scr, (255, 215, 110), (x, STRIP_Y), 20, 2)
                ic = self.site_icon(k, 32)
                scr.blit(ic, ic.get_rect(center=(x, STRIP_Y)))
                if site["kind"] == "saturn":
                    pygame.draw.ellipse(scr, (214, 194, 150), (x - 22, STRIP_Y - 6, 44, 12), 1)
            else:
                ic = self.site_dark(k, 32)
                scr.blit(ic, ic.get_rect(center=(x, STRIP_Y)))
                if k == nxt:
                    can = g.can_unlock(k)
                    colr = (255, 215, 110) if can else (90, 100, 150)
                    pygame.draw.circle(scr, colr, (x, STRIP_Y), 20, 1)
                    if can:
                        scr.blit(glow(26, scale_c((255, 200, 60), round(0.5 + 0.4 * math.sin(self.t * 5), 1))), (x - 26, STRIP_Y - 26),
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
        if k == -4:
            here = sysview.star_of_site(g.sites[g.cur])
            lines.append((f"Star system: {SECTORS[here]['name']}", (130, 170, 255)))
            lines.append(("Its planets on their orbits", (225, 225, 240)))
            lines.append(("Click to " + ("go back to the planet" if self.view == "orbit" else "open the system view") + "  (S)", (255, 215, 110)))
        elif k < 0:
            if g.galaxy_open:
                lines.append(("Galaxy map", (130, 170, 255)))
                lines.append((f"Fleet power {fmt(g.fleet_power())}   {len(g.conquered) - 1:,} systems held", (225, 225, 240)))
                lines.append(("Click to " + ("return to the solar system" if self.view == "galaxy" else "open the map"),
                              (255, 215, 110)))
            else:
                lines.append(("Galaxy map  (locked)", (120, 128, 170)))
                lines.append(("Unlock Mars to open it", (170, 175, 205)))
        site = self.g.sites[k] if k >= 0 else self.g.sites[0]
        if k < 0:
            pass
        elif g.unlocked[k]:
            lines.append((f"{site['name']}  -  {site['ore']}", site["col"]))
            lines.append((f"{fmt(g.ore[k])} stock   +{fmt(g.s_ops[k])}/s", (225, 225, 240)))
            lines.append((site["perk"], (170, 175, 205)))
            lines.append(("You are here" if k == g.cur else "Click to travel", (255, 215, 110)))
        elif k == next((i for i in range(1, NSOL) if not g.unlocked[i]), None):
            lines.append((f"{site['name']}  -  {site['ore']}   (locked)", site["col"]))
            ores, cr = g.unlock_cost(k)
            for p, amt in ores:
                if amt > 0:
                    ok = g.ore[p] >= amt
                    lines.append((f"{fmt(amt)} {self.g.sites[p]['ore']}  (have {fmt(g.ore[p])})", (130, 255, 150) if ok else (230, 130, 130)))
            if cr > 0:
                lines.append((f"{fmt(cr)} credits  (have {fmt(g.credits)})", (130, 255, 150) if g.credits >= cr else (230, 130, 130)))
            lines.append((site["perk"], (170, 175, 205)))
        else:
            lines.append(("???  (locked)", (140, 146, 180)))
        w = max(sm.size(t)[0] for t, _ in lines) + 24
        h = len(lines) * 20 + 14
        cx = (94 if k == -4 else 44) if k < 0 else self.strip_pos.get(k, STRIP_X0)
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
            return any(g.ore[p] >= u["cost"] * self.g.sc[p] for u in g.avail_upgrades(p))
        if k == T_COLONY:
            return g.can_buy_project(p)
        if k == T_PLANETS:
            return (any(g.can_unlock(i) for i in range(1, NSOL)) or worldview.colony_ready(self)
                    or (self.pl_page != 2 and worldview.has_news(self)))
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

    def tab_summary(self, k):
        """The one-line summary on the right of a tab's header: (text, colour) or None."""
        g = self.g
        if k == T_PLANETS:
            return f"{sum(1 for p in range(NSOL) if g.unlocked[p])} solar planets  -  {g.n_colonies:,} colonies", (150, 200, 225)
        if k == T_GALAXY:
            return (f"{len(g.conquered) - 1:,} systems  -  fleet {fmt(g.fleet_power())}", (180, 160, 235)) if g.galaxy_open else None
        if k == T_TECH:
            return f"{len(g.techs)}/{len(TECHS)} researched  -  {fmt(g.science)} science", (120, 225, 215)
        if k == T_QUESTS:
            return f"{g.quests_done} completed", (240, 190, 130)
        if k == T_WARP:
            return f"{g.dm_avail()} Dark Matter" + (f"  -  {g.stardust} Stardust" if g.sd_total else ""), (240, 150, 200)
        if k == T_AWARDS:
            return f"{len(g.ach)}/{len(ACHIEVEMENTS)}  -  +{g.ach_bonus * 100:.1f}% production", (240, 205, 100)
        return None

    def draw_panel(self, scr, fonts):
        big, med, sm, tiny = fonts
        g = self.g
        if not self.fast:                              # (fast mode has the background in its baked picture)
            scr.blit(self.panel_bg, (PANEL.x - 12, 4))
        tw = PANEL.w // len(self.tabs)
        for k, n in enumerate(self.tabs):                       # the tabs: an icon over the name, the number of the key in the corner
            r = pygame.Rect(PANEL.x + k * tw, 10, tw - 4, 44)
            on = self.tab == k
            accent = icons.TAB_ACCENT[n]
            self.button(scr, r, "", tiny, (lambda k=k: self.set_tab(k)), col=(66, 88, 160) if on else (30, 38, 70),
                        dot=not on and self.tab_alert(k), selected=on, danger=(n == "Dev"))
            ic = icons.tab_icon(n, 20, accent if on else scale_c(accent, 0.8))
            scr.blit(ic, ic.get_rect(center=(r.centerx, r.y + 15)))
            self.txt(scr, tiny, n, (r.centerx, r.y + 34), (255, 255, 255) if on else (170, 180, 215), "center")
            if k < 9:
                self.txt(scr, tiny, str((k + 1) % 10), (r.x + 5, r.y + 2), (110, 120, 160) if not on else (170, 190, 235))
            if on:
                pygame.draw.rect(scr, accent, (r.x + 8, r.bottom - 3, r.w - 16, 3), border_radius=2)
        accent = icons.TAB_ACCENT[self.tabs[self.tab]]
        self.txt(scr, med, self.tabs[self.tab].upper(), (PANEL.x + 2, 62), accent)
        if self.tab in (T_SHIPS, T_COLONY):
            for k, (lab, m) in enumerate([("x1", 1), ("x10", 10), ("x100", 100), ("Max", 0)]):
                r = pygame.Rect(PANEL.right - 4 * 54 + k * 54 + 2, 62, 50, 26)
                self.button(scr, r, lab, sm, (lambda m=m: setattr(g, "buy_mode", m)),
                            col=(66, 128, 92) if g.buy_mode == m else (34, 42, 74))
        site = self.g.sites[g.cur]
        summary = self.tab_summary(self.tab)
        if summary:
            self.txt(scr, tiny, summary[0], (PANEL.right - 2, 69), summary[1], "topright")
        if self.tab in (T_SHIPS, T_UPG, T_COLONY):
            right = PANEL.right - (4 * 54 + 8 if self.tab != T_UPG else 0)
            self.txt(scr, tiny, f"{site['name']}  -  paid in {site['ore']}", (right, 69), site["col"], "topright")
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
            per = rate * self.g.sc[p] * g.s_gm[p][i] * g.G
            self.row(scr, fonts, r, ships.name(self.fam(p), i), f"{fmt(per, 2)} {self.g.sites[p]['ore']}/s each  -  {ships.blurb(self.fam(p), i)}", None, None, ok,
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
        affordable = sum(1 for u in ups if g.ore[p] >= u["cost"] * self.g.sc[p])
        if r.colliderect(PANEL):
            self.button(scr, r, f"Buy everything affordable  ({affordable})", sm,
                        (lambda: g.buy_all_upgrades(p)), enabled=affordable > 0, panel=True, col=(70, 110, 90))
        y += 42
        if not ups:
            self.txt(scr, sm, "No upgrades yet - buy more ships!", (PANEL.x + 10, y + 6), (150, 155, 180))
            return y + 40
        self.txt(scr, tiny, f"{len(g.ups[p])}/{len(UPGRADES)} bought on {self.g.sites[p]['name']} this run", (PANEL.x + 4, y),
                 (150, 155, 180))
        y += 20
        glyphs = {"click": "C", "clickops": "R", "global": "*"}
        for u in ups:
            r = pygame.Rect(PANEL.x, y, PANEL.w, 62)
            y += 68
            cost = u["cost"] * self.g.sc[p]
            ok = g.ore[p] >= cost
            kw = dict(icon=self.ship_icon(p, u["arg"][0])) if u["kind"] == "gen" else dict(glyph=glyphs[u["kind"]])
            uname, udesc = core.upgrade_text(u, self.fam(p))
            self.row(scr, fonts, r, uname, udesc, fmt(cost), None, ok, (200, 160, 255),
                     lambda uid=u["id"]: g.buy_upgrade(p, uid), **kw)
        return y

    def draw_colony(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        p = g.cur
        bonus = self.g.sites[p]["bonus"]
        bn = "all buildings x1.5" if bonus == -1 else f"{BUILDINGS[bonus][0]} x2"
        self.txt(scr, tiny, f"{self.g.sites[p]['name']} colony  -  planet bonus: {bn}", (PANEL.x + 4, y), self.g.sites[p]["col"])
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
            unit = self.g.sites[p]["ore"] if res == "ore" else res
            self.row(scr, fonts, r, f"{name}  Lv {L}", f"{desc}  {self.bld_output(p, b, L, f)}",
                     f"x{n}: {fmt(cost)} {unit}", None, ok, bcol, (lambda b=b: g.buy_building(p, b)), glyph=name[0])
        y += 10
        if p >= NSOL:                                       # only the solar planets have a megaproject
            self.txt(scr, tiny, "Colony worlds have no megaproject: the wonders are the solar system's.", (PANEL.x + 4, y), (150, 160, 190))
            return y + 24
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
            lines = [(f"{fmt(ore)} {self.g.sites[p]['ore']}  (have {fmt(g.ore[p])})", good if ok_o else bad),
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
            return f"(now {fmt(0.5 * L * f * self.g.csc[p] * (core.colonies.YIELD if p >= NSOL else 1.0) * E['cred'])}/s)"
        if b == 2:
            return f"(now {fmt(0.15 * L * f * self.g.csc[p] * (core.colonies.YIELD if p >= NSOL else 1.0) * E['sci'])}/s)"
        if b == 3:
            return f"(now -{0.6 * L * f:.1f}%)"
        if b == 4:
            return f"(now +{2.5 * L * f:.1f}%)"
        return f"(now +{4 * L * f:.0f}%)"

    def draw_planets(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        if self.pl_page == 1:
            return worldview.draw_colonies(self, scr, fonts, y)
        if self.pl_page == 2:
            return worldview.draw_page(self, scr, fonts, y)
        y = worldview.draw_toggle(self, scr, fonts, y)
        nxt = next((i for i in range(1, NSOL) if not g.unlocked[i]), None)
        for i, line in enumerate(["Unlock planets with the ores of the worlds behind you. Every planet has its",
                                  "own ore, fleet, colony and a bonus. Travel by clicking a planet below or at the bottom."]):
            self.txt(scr, tiny, line, (PANEL.x + 4, y + i * 15), (150, 160, 190))
        y += 38
        good, bad = (130, 255, 150), (230, 130, 130)
        for k, site in enumerate(SITES[:NSOL]):
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
                         icon=self.site_icon(k, 50), lines=lines)
            elif k == nxt:
                ores, cr = g.unlock_cost(k)
                lines = []
                for pp, amt in ores:
                    if amt > 0:
                        lines.append((f"{fmt(amt)} {self.g.sites[pp]['ore']}   (have {fmt(g.ore[pp])})", good if g.ore[pp] >= amt else bad))
                if cr > 0:
                    lines.append((f"{fmt(cr)} credits   (have {fmt(g.credits)})", good if g.credits >= cr else bad))
                r = pygame.Rect(PANEL.x, y, PANEL.w, 62 + 15 * len(lines))
                y += r.h + 6
                self.row(scr, fonts, r, f"{site['name']}  -  {site['ore']}", site["perk"], "UNLOCK", None,
                         g.can_unlock(k), site["col"], (lambda k=k: g.unlock_planet(k)), icon=self.site_icon(k, 50),
                         lines=lines)
            else:
                r = pygame.Rect(PANEL.x, y, PANEL.w, 62)
                y += 68
                self.row(scr, fonts, r, "???", "Unlock the planets before it first", None, None, False, (62, 66, 92),
                         None, dim=True, icon=self.site_dark(k, 50))
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
            site = self.g.sites[q.get("site", 0) if q.get("site", 0) < self.g.nsite else 0]
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
            rk = (r["fac"], int(round(ang / 6.0)) % 60)                      # (turned in steps of 6 degrees, kept)
            img = self.raid_rot.get(rk)
            if img is None:
                img = self.raid_rot[rk] = pygame.transform.rotate(self.enemy_big[r["fac"]], rk[1] * 6.0)
            scr.blit(img, img.get_rect(center=(r["x"], r["y"])))
            d = math.hypot(dx, dy) or 1.0
            if d < 300 and math.sin(self.t * 16 + idx * 1.7) > 0.2:      # your defences open fire
                ox, oy = CX - dx / d * 95, CY - dy / d * 95
                pygame.draw.line(scr, (255, 120, 90), (ox, oy), (r["x"], r["y"]), 3)
                pygame.draw.line(scr, (255, 245, 220), (ox, oy), (r["x"], r["y"]), 1)
        if any(not r["win"] for r in self.raiders):
            scr.blit(glow(80, (90, 20, 10)), (CX - 80, CY - 80), special_flags=ADD)

    GAL_PAGES = ["War room", "Generals", "Defence"]

    # ---------------- generals, wardens and the defence: the war's standing orders -----------------
    def begin_pick(self, idx, field):
        self.pick = dict(idx=idx, field=field)
        self.view = "galaxy"
        what = {"heading": "the direction to go", "goal": "the place to go toward", "region": "the region to clear"}[field]
        self.g.toast(f"Click a system on the map: {what} for {generals.COMMANDERS[idx][2]}  (Esc cancels)", 6)

    def apply_pick(self, k):
        """A system was clicked while picking orders for a general. Returns True if the click was used."""
        g, pk = self.g, self.pick
        if not pk or pk["idx"] not in g.cmd:
            self.pick = None
            return False
        st, f = g.cmd[pk["idx"]], pk["field"]
        name = generals.COMMANDERS[pk["idx"]][2]
        if f == "goal":
            if k in g.conquered:
                g.toast("Pick a system you do not hold yet.", 3)
                return True
            generals.set_orders(st, mode="toward", goal=k)
            g.toast(f"{name}: toward {SECTORS[k]['name']}", 4)
        elif f == "region":
            generals.set_orders(st, mode="region", region=generals.region_of(k))
            g.toast(f"{name}: clear the {generals.region_of(k)}", 4)
        else:
            generals.set_orders(st, mode="heading", angle=generals.heading_from(g, k) % math.tau)
            g.toast(f"{name}: heading {generals.compass(st['angle'])}", 4)
        self.pick = None
        return True

    def set_general_mode(self, idx, st, m):
        generals.set_orders(st, mode=m)
        if m == "heading" and st.get("angle") is None:
            st["angle"] = 0.0
        if m == "toward" and st["goal"] is None:
            self.begin_pick(idx, "goal")
        elif m == "region" and st["region"] is None:
            self.begin_pick(idx, "region")

    def toggle_commander(self, st):
        st["on"] = not st["on"]
        if st["on"] and "army" in st:
            generals.set_army(self.g, next(i for i, v in self.g.cmd.items() if v is st), st["army"])

    def commander_frame(self, scr, r, col, on=True):
        pygame.draw.rect(scr, (36, 44, 62) if on else (28, 31, 48), r, border_radius=9)
        pygame.draw.rect(scr, scale_c((36, 44, 62), 1.35), (r.x + 3, r.y + 1, r.w - 6, 2), border_radius=1)
        pygame.draw.rect(scr, col if on else (62, 66, 92), r, 1, border_radius=9)
        pygame.draw.rect(scr, col if on else (62, 66, 92), (r.x, r.y + 8, 4, r.h - 16), border_radius=2)

    def draw_locked_commanders(self, scr, fonts, y, ids, label):
        big, med, sm, tiny = fonts
        g = self.g
        locked = [i for i in ids if i not in g.cmd]
        if not locked:
            return y
        self.txt(scr, med, label, (PANEL.x + 4, y), (255, 225, 140))
        y += 28
        for i in locked:
            sysname, role, name, tr, blurb = generals.COMMANDERS[i]
            k = generals.SYSTEM_OF[i]
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 50)
            near = k in g.targets_set()
            self.row(scr, fonts, rr, f"{name}  -  {generals.TRAITS[tr][0]}",
                     f"Liberate {sysname} ({galaxy.fmt_ly(SECTORS[k]['d'])} from the Sun)" + ("  -  in range" if near else ""), None, None,
                     near, (255, 190, 150) if role == generals.GENERAL else (120, 190, 255), (lambda k=k: self.select_sector(k)), glyph="G" if role == generals.GENERAL else "W")
            y += 56
        return y

    def draw_generals_page(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        gens = generals.commanders(g, generals.GENERAL)
        self.txt(scr, med, f"Generals  {len(gens)}/{len(generals.GENERAL_IDS)}", (PANEL.x + 4, y), (255, 190, 150))
        self.txt(scr, tiny, f"armies {generals.army_total(g) * 100:.0f}%  -  defence {g.defence * 100:.0f}%  -  manual {g.manual_cap() * 100:.0f}% of the fleet",
                 (PANEL.right - 4, y + 7), (150, 158, 190), "topright")
        y += 26
        self.txt(scr, tiny, "Give a general orders once: it picks its targets and runs its own campaigns, offline too.", (PANEL.x + 4, y),
                 (140, 148, 180))
        y += 22
        if self.pick:
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 34)
            pygame.draw.rect(scr, (70, 56, 24), rr, border_radius=7)
            pygame.draw.rect(scr, (255, 215, 110), rr, 1, border_radius=7)
            self.txt(scr, sm, "Click a system on the map...", (rr.x + 12, rr.centery), (255, 235, 170), "midleft")
            self.button(scr, pygame.Rect(rr.right - 92, rr.y + 4, 84, 26), "Cancel", tiny, lambda: setattr(self, "pick", None), panel=True)
            y += 42
        if not gens:
            self.txt(scr, sm, "No general yet. Liberate Alpha Centauri (4.4 light years away) to earn the first.", (PANEL.x + 4, y),
                     (200, 205, 225))
            y += 30
        for idx, st in gens:
            y = self.general_card(scr, fonts, y, idx, st)
        return self.draw_locked_commanders(scr, fonts, y, generals.GENERAL_IDS, "Still to earn") + 8

    def general_card(self, scr, fonts, y, idx, st):
        big, med, sm, tiny = fonts
        g = self.g
        sysname, _, name, tr, blurb = generals.COMMANDERS[idx]
        r = pygame.Rect(PANEL.x, y, PANEL.w, 190)
        if r.colliderect(PANEL):
            self.commander_frame(scr, r, (255, 190, 150), st["on"])
            rk = generals.rank(st)
            self.txt(scr, med, name, (r.x + 14, r.y + 6), (245, 245, 250) if st["on"] else (125, 130, 156))
            self.txt(scr, tiny, f"{generals.TRAITS[tr][0]}: {generals.TRAITS[tr][1]}  -  {generals.RANK_NAMES[rk]}  -  from {sysname}",
                     (r.x + 14, r.y + 30), (156, 166, 196))
            self.button(scr, pygame.Rect(r.right - 78, r.y + 8, 66, 26), "ON" if st["on"] else "OFF", sm,
                        lambda st=st: self.toggle_commander(st), panel=True, col=(40, 110, 70) if st["on"] else (70, 50, 56))
            n_c = sum(1 for c in g.campaigns if c.get("by") == generals.key(idx))
            status = "Paused after defeats" if st["paused"] else (st["status"] or "Waiting for orders to take effect")
            self.txt(scr, tiny, f"{status}   ({n_c}/{generals.slots(idx, st)} campaigns)", (r.x + 14, r.y + 48),
                     (255, 190, 130) if st["paused"] else (130, 220, 160))
            # --- where to go
            bw = (r.w - 28 - 3 * 6) // 4
            for j, m in enumerate(generals.MODES):
                self.button(scr, pygame.Rect(r.x + 14 + j * (bw + 6), r.y + 70, bw, 26), generals.MODE_NAMES[m], tiny,
                            (lambda m=m, idx=idx, st=st: self.set_general_mode(idx, st, m)), panel=True, selected=st["mode"] == m,
                            col=(70, 100, 170) if st["mode"] == m else (36, 44, 76))
            self.txt(scr, sm, generals.describe_orders(st), (r.x + 14, r.y + 106), (235, 238, 250))
            field = {"heading": "heading", "toward": "goal", "region": "region"}.get(st["mode"])
            if field:
                self.button(scr, pygame.Rect(r.right - 142, r.y + 100, 128, 26), "Pick on map", tiny,
                            (lambda idx=idx, f=field: self.begin_pick(idx, f)), panel=True, col=(90, 80, 40))
            # --- under what circumstances
            cw = (r.w - 28 - 3 * 6) // 4
            conds = [(f"Odds {st['odds'] * 100:.0f}%+", lambda st=st: generals.cycle_odds(st)),
                     (generals.WAR_NAMES[st["war"]], lambda st=st: generals.cycle_war(st)),
                     (generals.PREFER_NAMES[st["prefer"]], lambda st=st: generals.cycle_prefer(st)),
                     ("Stop: " + (f"after {st['limit']}" if st["limit"] else "never"), lambda st=st: generals.cycle_limit(st))]
            for j, (label, fn) in enumerate(conds):
                self.button(scr, pygame.Rect(r.x + 14 + j * (cw + 6), r.y + 134, cw, 26), label, tiny, fn, panel=True, col=(54, 62, 96))
            # --- the army and the record
            self.txt(scr, tiny, f"Army {st['army'] * 100:.0f}% of the fleet", (r.x + 14, r.y + 170), (200, 205, 225), "midleft")
            self.button(scr, pygame.Rect(r.x + 160, r.y + 162, 28, 22), "-", tiny, (lambda idx=idx: generals.set_army(g, idx, g.cmd[idx]["army"] - 0.02)),
                        panel=True)
            self.button(scr, pygame.Rect(r.x + 192, r.y + 162, 28, 22), "+", tiny, (lambda idx=idx: generals.set_army(g, idx, g.cmd[idx]["army"] + 0.02)),
                        panel=True)
            self.txt(scr, tiny, f"took {st['took']}  -  lost {st['lost']}", (r.right - 14 - (96 if st["paused"] else 0), r.y + 170), (170, 176, 205), "midright")
            if st["paused"]:
                self.button(scr, pygame.Rect(r.right - 92, r.y + 160, 80, 24), "Resume", tiny, lambda st=st: generals.resume(st), panel=True,
                            col=(40, 110, 70))
        return y + 198

    def draw_defence_page(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        self.txt(scr, med, f"Defence  {g.defence * 100:.0f}% of the fleet", (PANEL.x + 4, y), (140, 200, 255))
        self.button(scr, pygame.Rect(PANEL.right - 132, y - 2, 60, 26), "-5%", tiny, lambda: generals.set_defence(g, g.defence - 0.05), panel=True)
        self.button(scr, pygame.Rect(PANEL.right - 66, y - 2, 60, 26), "+5%", tiny, lambda: generals.set_defence(g, g.defence + 0.05), panel=True)
        y += 32
        bar = pygame.Rect(PANEL.x + 4, y, PANEL.w - 8, 16)
        pygame.draw.rect(scr, (16, 18, 32), bar, border_radius=4)
        x = bar.x
        for share, col in ((g.defence, (90, 160, 255)), (generals.army_total(g), (255, 160, 110)), (g.manual_cap(), (120, 210, 150))):
            w = int(bar.w * share)
            if w > 0:
                pygame.draw.rect(scr, col, (x, bar.y, w, bar.h), border_radius=3)
                x += w
        y += 22
        self.txt(scr, tiny, f"defence {g.defence * 100:.0f}%   armies {generals.army_total(g) * 100:.0f}%   manual {g.manual_cap() * 100:.0f}%", (PANEL.x + 4, y), (170, 176, 205))
        y += 20
        self.txt(scr, tiny, "Armies on campaign defend nothing. The defence never leaves home.",
                 (PANEL.x + 4, y), (140, 148, 180))
        y += 26
        # --- the regions: a posture for each
        self.txt(scr, med, "Regions", (PANEL.x + 4, y), (255, 225, 140))
        y += 28
        counts, held, dmap = generals.exposed_counts(g), generals.held_regions(g), generals.defence_map(g)
        regions = sorted(held, key=lambda r: (-counts.get(r, 0), r))
        if not regions:
            self.txt(scr, sm, "You hold no system yet.", (PANEL.x + 4, y), (200, 205, 225))
            y += 28
        for reg in regions:
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 54)
            exp = counts.get(reg, 0)
            self.commander_frame(scr, rr, (140, 200, 255) if exp else (90, 96, 130))
            self.txt(scr, sm, reg, (rr.x + 14, rr.y + 6), (245, 245, 250))
            sub = (f"{held[reg]:,} held  -  {exp} on the front  -  defended by {fmt(dmap.get(reg, 0.0))}" if exp
                   else f"{held[reg]:,} held  -  no enemy at war reaches it")
            self.txt(scr, tiny, sub, (rr.x + 14, rr.y + 30), (156, 166, 196))
            pst = g.posture.get(reg, "balanced")
            bw = 76
            for j, ps in enumerate(generals.POSTURES):
                self.button(scr, pygame.Rect(rr.right - 12 - (3 - j) * (bw + 4) + 4, rr.y + 12, bw, 28), generals.POSTURE_NAMES[ps], tiny,
                            (lambda reg=reg, ps=ps: g.posture.__setitem__(reg, ps)), panel=True, selected=pst == ps,
                            col=(70, 100, 170) if pst == ps else (36, 44, 76))
            y += 60
        y += 6
        # --- the wardens
        wards = generals.commanders(g, generals.WARDEN)
        self.txt(scr, med, f"Wardens  {len(wards)}/{len(generals.WARDEN_IDS)}", (PANEL.x + 4, y), (255, 225, 140))
        y += 28
        if not wards:
            self.txt(scr, sm, "No warden yet. Liberate Barnard's Star (6 light years away) to earn the first.", (PANEL.x + 4, y), (200, 205, 225))
            y += 28
        for idx, st in wards:
            sysname, _, name, tr, blurb = generals.COMMANDERS[idx]
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 100)
            if rr.colliderect(PANEL):
                self.commander_frame(scr, rr, (140, 200, 255), st["on"])
                self.txt(scr, med, name, (rr.x + 14, rr.y + 6), (245, 245, 250) if st["on"] else (125, 130, 156))
                self.txt(scr, tiny, f"{generals.TRAITS[tr][0]}: {generals.TRAITS[tr][1]}  -  from {sysname}", (rr.x + 14, rr.y + 30), (156, 166, 196))
                self.button(scr, pygame.Rect(rr.right - 78, rr.y + 8, 66, 26), "ON" if st["on"] else "OFF", sm,
                            lambda st=st: st.__setitem__("on", not st["on"]), panel=True, col=(40, 110, 70) if st["on"] else (70, 50, 56))
                self.button(scr, pygame.Rect(rr.x + 14, rr.y + 64, 250, 26), f"Region: {st['region'] or '-'}", tiny,
                            lambda st=st: generals.cycle_region(g, st), panel=True, col=(54, 62, 96))
                self.button(scr, pygame.Rect(rr.x + 272, rr.y + 64, 150, 26), "Retake: " + ("on" if st["retake"] else "off"), tiny,
                            lambda st=st: st.__setitem__("retake", not st["retake"]), panel=True, col=(54, 62, 96))
                self.txt(scr, tiny, st["status"] or "Holding its region", (rr.x + 14, rr.y + 48), (130, 220, 160))
                self.txt(scr, tiny, f"retaken {st.get('retaken', 0)}", (rr.right - 14, rr.y + 90), (170, 176, 205), "midright")
            y += 108
        return self.draw_locked_commanders(scr, fonts, y, generals.WARDEN_IDS, "Still to earn") + 8

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
        quarter = (PANEL.w - 24) // 4
        sk = self.sel_sector if sysview.can_open(g, self.sel_sector) else None
        for i, (label, fn, col, ok) in enumerate((("Close look", self.close_look, (150, 74, 74), True), ("Home", self.go_home, (50, 100, 110), True),
                                                  ("Whole galaxy", self.zoom_out, (50, 70, 110), True),
                                                  ("Open system", (lambda: sysview.open_system(self, sk)), (46, 110, 84), sk is not None))):
            self.button(scr, pygame.Rect(PANEL.x + i * (quarter + 8), y, quarter, 30), label, sm if len(label) < 12 else tiny, fn, panel=True,
                        col=col, enabled=ok)
        y += 40
        pw = (PANEL.w - 16) // 3
        for i, label in enumerate(self.GAL_PAGES):
            self.button(scr, pygame.Rect(PANEL.x + i * (pw + 8), y, pw, 30), label, sm, (lambda i=i: setattr(self, "gal_page", i)),
                        panel=True, selected=self.gal_page == i, col=(70, 100, 170) if self.gal_page == i else (36, 44, 76))
        y += 38
        if self.gal_page == 1:
            return self.draw_generals_page(scr, fonts, y)
        if self.gal_page == 2:
            return self.draw_defence_page(scr, fonts, y)
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
        # ---- the campaigns: everything in the field, and how much of the fleet a manual attack sends
        self.txt(scr, med, f"Campaigns  {len(g.campaigns)}", (PANEL.x + 4, y), (255, 190, 150))
        self.txt(scr, tiny, f"defence {g.defence * 100:.0f}%  -  armies {generals.army_total(g) * 100:.0f}%  -  manual {g.manual_cap() * 100:.0f}%"
                 " of the fleet", (PANEL.right - 4, y + 7), (150, 158, 190), "topright")
        y += 28
        bw = (PANEL.w - 52 - 6 * len(COMMIT_MODES)) // len(COMMIT_MODES)
        self.txt(scr, tiny, "Send:", (PANEL.x + 4, y + 9), (170, 176, 205))
        for i, (label, _) in enumerate(COMMIT_MODES):
            self.button(scr, pygame.Rect(PANEL.x + 52 + i * (bw + 6), y, bw, 28), label, sm, (lambda i=i: setattr(g, "commit", i)),
                        panel=True, selected=g.commit == i, col=(60, 74, 120))
        y += 34
        self.txt(scr, tiny, f"Manual strikes {g.manual_count()}/{g.max_fronts()} (Command track).  Generals launch their own: see the Generals page.",
                 (PANEL.x + 4, y), (140, 148, 180))
        y += 20
        for c in sorted(g.campaigns, key=lambda c: c["dur"] - c["t"]):
            sec = SECTORS[c["k"]]
            who = generals.COMMANDERS[generals.index_of(c["by"])][2] if c.get("by") else "Manual"
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 58)
            self.row(scr, fonts, rr, f"{sec['name']}", f"{who}  -  {fmt_time(max(0, c['dur'] - c['t']))} left   -   "
                     f"{c['chance'] * 100:.0f}% to win   -   {c['share'] * 100:.0f}% of the fleet", None, None, True,
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
        text, armed = blackhole.status(g.bomb)
        if g.bomb or core.BOSS in g.conquered:
            for l in wrap(tiny, text, PANEL.w - 24):
                self.txt(scr, tiny, l, (x, y), (255, 150, 130) if armed else (190, 170, 150))
                y += 16
            y += 6
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
        prog = self.ascend_fx / self.ascend_len        # 1 -> 0
        grow = 1 - prog
        if self.ascend_boom:                           # the bomb: shock waves that sweep the screen, red then white
            for i in range(3):
                rad = (grow * 1.3 - i * 0.16) * W * 0.9
                if rad > 0:
                    pygame.draw.circle(scr, lerp_c((255, 110, 80), (255, 245, 225), i / 2), (CX, CY), int(rad), max(2, int(26 * prog)))
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
            img2 = fonts[1].render("THE BOMB GOES OFF" if self.ascend_boom else "NEW GAME+", True, (255, 170, 130) if self.ascend_boom else (255, 215, 120))
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
            ("Planets unlocked", f"{g.n_sol}/{NSOL}"),
            ("Colony worlds settled", f"{g.n_colonies:,} of {len(worlds.found(g.conquered)):,} found"),
            ("Planets visited", f"{len(g.visited)}/{g.nsite}"),
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
            ("Megaprojects", f"{len(g.projects)}/{NSOL}"),
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
        mode = st.get("perf", "auto")
        self.button(scr, pygame.Rect(PANEL.x, y, 180, 36), f"Fast mode: {mode.upper()}", sm, self.cycle_perf, panel=True,
                    col=(60, 120, 90) if self.fast else (50, 70, 110))
        self.txt(scr, tiny, "For slow phones and computers: a lighter picture, 30 frames a second. Auto = on for phones.", (PANEL.x + 192, y + 4), (150, 158, 190))
        self.txt(scr, tiny, f"Now {'ON' if self.fast else 'OFF'}.", (PANEL.x + 192, y + 19), (150, 158, 190))
        y += 48
        self.button(scr, pygame.Rect(PANEL.x, y, 180, 36), f"Show FPS: {'ON' if st.get('show_fps') else 'OFF'}", sm,
                    lambda: st.__setitem__("show_fps", not st.get("show_fps")), panel=True,
                    col=(60, 120, 90) if st.get("show_fps") else (50, 70, 110))
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
    """A canvas with the shape of the phone's screen (so it fills it without black bars) and 1280 pixels along its long side: the phone
    draws in software, so every pixel saved is time saved (1280x576 on a 20:9 screen is a third fewer pixels than 1600x720)."""
    aspect = max(dw, dh) / max(1, min(dw, dh))
    return 1280, max(540, round(1280 / aspect))


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
                raw = clock.tick(30 if app.fast else 60) / 1000.0
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
                            if app.pick:
                                app.pick = None                        # (cancels picking a system for a general's orders)
                            elif app.fullscreen and not resources.ANDROID:
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
                        elif not g.event and app.system_key(e.key):
                            pass
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
                work0 = time.perf_counter()
                app.touch.update(dt)
                app.update(dt)
                app.draw(app.scr, fonts)
                if not selftest:
                    app.perf_sample(time.perf_counter() - work0)
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
                    gamelog.LOG.info("alive: %.0f fps average, slowest frame %.0f ms, fast mode %s | %s", beat_frames / secs, slowest * 1000, "on" if app.fast else "off",
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
    for p in range(NSOL):
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
        assert len({seen[(p, i)] for p in range(NSOL)}) == NSOL, f"class {i} has identical sprites on two solar planets"

    canvas = pygame.Surface((300, 300))
    for style in {ships.style(p) for p in range(NSOL)}:   # every laser style draws
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
    names = {r["names"][i] for r in ships.ROSTERS[:NSOL] for i in (8, 9)}
    assert len(names) == 2 * NSOL, "the big classes need a name of their own on every solar planet"
    assert len(ships.ROSTERS) == NSOL and set(colonies.FAMILY.values()) | {7} <= set(range(NSOL))
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
    last = SITES[NSOL - 1]
    assert last["name"] == "Kuiper Belt" and last["kind"] == "kuiper" and not any("Proxima" in s["name"] for s in SITES[:NSOL])
    assert ships.style(NSOL - 1) == "comet" and "comet" in shipart.FAMILIES and ships.motion(NSOL - 1) == "sweep"
    for i in range(NSH):                                       # the comet orbit stays on screen for every class and ship
        for j in range(4):
            for tt in (0.0, 3.3, 9.9, 21.0):
                x, y, depth = ships.orbit(NSOL - 1, i, j, 4, tt, 1)
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


def check_colonies():
    """Every world of every star you hold can be settled and played: tiers from the strength of the star, prices in the ore of the tiers
    before, a bonus per kind of world, saves, Warp and Ascension."""
    t1, pr, boss = galaxy.BY_NAME["TRAPPIST-1"], galaxy.BY_NAME["Proxima Centauri"], galaxy.BOSS
    assert colonies.tier_of(t1) == 5 and colonies.tier_of(pr) == 3 and colonies.tier_of(boss) == 10
    tiers = [colonies.tier_of(k) for k in range(1, galaxy.N)]
    assert 1 <= min(tiers) and max(tiers) == colonies.TIER_CAP and len(set(tiers)) >= 9
    for k in range(1, galaxy.N, 7):                                            # a world is a site like the planets of the solar system
        for i in range(worlds.count_of(k)):
            c = colonies.site_of(k, i)
            assert c is colonies.site_of(k, i) and c["colony"] and 1 <= c["tier"] <= colonies.TIER_CAP and c["fx"] and c["perk"], c["name"]
            assert 0 <= c["family"] < NSOL and c["id"] == ("c", k, i) and c["name"] == worlds.planets_of(k)[i]["name"]
    assert set(colonies.FAMILY) == set(worlds.KINDS) == set(colonies.PERK) == set(colonies.ORE) == set(colonies.BONUS)
    g = core.Game(load=False, sim=True)
    assert g.nsite == NSOL and g.n_colonies == 0 and g.sites[:NSOL] == SITES and g.tier == list(range(NSOL)) and g.sc[11] == 1e11
    te = (t1, 3)                                                              # TRAPPIST-1 e, a temperate world of tier 5
    assert not g.can_settle(*te), "the star must be liberated first"
    g.conquered.add(t1)
    assert g.settle_state(*te) == "waiting" and not g.can_settle(*te), "and a planet of the tier before its own reached"
    for k in range(1, 5):
        g.unlocked[k] = True
    assert g.settle_state(*te) == "ready" and not g.can_settle(*te), "ready, but you have nothing to pay with yet"
    g.credits = 1e60
    for q in range(5):
        g.ore[q] = 1e60
    assert g.can_settle(*te)
    pays, cr = g.settle_cost(*te)
    a, b, cr0 = SITES[5]["unlock"]
    assert [p for p, _ in pays] == [4, 3] and abs(pays[0][1] - a * 0.4 * core.SCALE ** 4) < 1e-6 * pays[0][1], pays
    assert abs(cr - cr0 * 0.4 ** 0.6) < 1e-6 * cr0
    g.recalc()
    e0, G0 = g.E["cred"], g.G
    g.ore[4], g.ore[3] = 5 * pays[0][1], 5 * pays[1][1]
    g.credits = 5 * cr
    p = g.settle(*te)
    assert p == NSOL and g.nsite == NSOL + 1 and g.n_colonies == 1 and g.sites[p]["name"] == "TRAPPIST-1 e" and g.unlocked[p]
    assert len(g.ore) == len(g.owned) == len(g.ups) == len(g.bld) == len(g.unlocked) == len(g.sc) == g.nsite
    assert abs(g.ore[4] - 4 * pays[0][1]) < 1e-6 * pays[0][1] and abs(g.credits - 4 * cr) < 1e-6 * cr, "paid in the ore of the planets before its tier"
    g.credits = 1e60
    assert g.sc[p] == 1e5 and g.csc[p] == 5.0 ** 5 and g.colony_planet[te] == p and g.settle_state(*te) == "settled"
    assert g.can_settle(*te) is False and g.settle(*te) is None
    assert abs(g.E["cred"] / e0 - 1.1) < 1e-9 and g.G > G0, "the first temperate world brings the bonus of its kind, and every colony some production"
    assert "Settler" in {x["id"] for x in g.check_achievements()}
    pays2 = g.settle_cost(t1, 2)[0]
    assert abs(pays2[0][1] / pays[0][1] - 1.06) < 1e-9, "dearer for every colony you hold"
    g.ore[3] = 1e61
    assert g.settle(t1, 2) is not None and abs(g.E["cred"] / e0 - 1.1) < 1e-9, "a second world of a kind brings no second bonus"
    assert g.kind_first == {"temperate": te}
    assert g.settle(t1, 1) is not None and g.n_colonies == 3                    # a desert world: its own bonus
    # the richest planet of a tier pays
    g.ore[4] = 1e9
    rich = g.settle_cost(t1, 4)[0][0][0]
    assert rich == 4
    # a colony is a planet: it mines, fights, has buildings and no megaproject
    g.owned[p][0] = 5
    g.recalc()
    assert g.s_ops[p] > 0 and g.planet_power(p) > 0 and g.fleet_power() >= g.planet_power(p)
    assert not g.can_buy_project(p) and p not in g.projects
    assert g.start_travel(p) and g.cur == p and p in g.visited
    g.step(1.0)
    # the worlds you hold, and the ones you could settle
    assert len(g.world_options()) == sum(worlds.count_of(k) for k in g.conquered if k) - 3
    assert all(g.can_settle(*w) for w in g.colony_options(3)) and len(g.colony_options(2)) <= 2
    assert worlds.sig(g.conquered) and not g.valid_world((0, 0)) and not g.valid_world((t1, 99)) and g.valid_world((t1, 6))
    # the Colonial Office tech settles worlds by itself, one every few seconds, when you switch it on
    for q in range(g.nsite):
        g.ore[q] = 1e70
    g.credits = 1e70
    g.techs.add("t32")
    g.recalc()
    n = g.n_colonies
    g.step(6.0)
    assert g.n_colonies == n, "it is off until you switch it on"
    g.auto_settle = True
    g.step(6.0)
    assert g.n_colonies == n + 1, "it settles the nearest world you can pay for"
    g.auto_settle = False
    g.techs.discard("t32")
    g.recalc()
    # saves: colonies are kept in order with their ships, bad entries are dropped, and a save with twelve planets loads
    old_save = core.SAVE
    d = tempfile.mkdtemp(prefix="space_miner_colonies_")
    try:
        core.SAVE = os.path.join(d, "save.json")
        g.projects = {0, 1}
        g.save()
        h = core.Game(load=True, sim=True)
        assert h.colonies == g.colonies and h.nsite == g.nsite and h.owned[p][0] == 5 and h.cur == p and h.n_colonies == len(g.colonies) == 4
        assert [s["name"] for s in h.sites[NSOL:]] == [s["name"] for s in g.sites[NSOL:]] and h.kind_first == g.kind_first
        with open(core.SAVE) as f:
            data = json.load(f)
        data["colonies"] = data["colonies"][:2] + [[0, 0], [t1, 99], "x", [5.5, 1]]
        for key in ("ore", "run_ore", "all_ore", "owned", "ups", "unlocked", "bld"):
            data[key] = data[key][:NSOL + 2]
        data["visited"] = [0, 12, 13, 99]
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        h = core.Game(load=True, sim=True)
        assert h.colonies == g.colonies[:2] + [(5, 1)] if galaxy.STARS[5] and worlds.count_of(5) > 1 else h.colonies == g.colonies[:2]
        assert len(h.ore) == len(h.unlocked) == h.nsite and h.visited <= set(range(h.nsite))
        h.step(1.0)
        with open(core.SAVE) as f:
            data = json.load(f)
        del data["colonies"]
        for key in ("ore", "run_ore", "all_ore", "owned", "ups", "unlocked", "bld"):
            data[key] = data[key][:NSOL]                                       # what a 1.x save holds
        data["projects"] = [0, 1, 40]
        data["cur"] = 0
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        h = core.Game(load=True, sim=True)
        assert h.nsite == NSOL and h.n_colonies == 0 and h.n_sol == g.n_sol and h.projects == {0, 1}
        h.step(1.0)
    finally:
        core.SAVE = old_save
        shutil.rmtree(d, ignore_errors=True)
    # a Warp keeps your colonies, an Ascension takes them (like the planets)
    n = g.nsite
    g.dm = 1e12
    g.do_warp(force=True)
    assert g.nsite == n and g.unlocked[p] and g.owned[p][0] == 0 and len(g.owned) == n
    g.conquered |= {boss}
    g.ascend(force=True)
    assert g.nsite == NSOL and g.n_colonies == 0 and g.colonies == [] and len(g.ore) == NSOL and g.unlocked[0] and not g.unlocked[1]
    assert g.kind_first == {} and g.colony_planet == {}
    g.step(1.0)
    # more achievements, and colonies of every tier and kind draw their sprites
    assert {"Settler", "Colonist", "Colonial Empire", "Worlds Without End", "A Home on Every Star"} <= set(core.ACH_BY_ID)


def check_worlds():
    """The planets of the other systems: the same every time, sane numbers, real planets for the real stars, the facts you find."""
    total = 0
    kinds = set()
    for k in range(galaxy.N):
        ws = worlds.planets_of(k)
        assert ws is worlds.planets_of(k)
        total += len(ws)
        for i, w in enumerate(ws):
            assert w["sys"] == k and w["idx"] == i and w["kind"] in worlds.KINDS and w["name"] and w["seed"] >= 0, (k, w)
            assert 0.2 <= w["r"] <= 16.0 and w["m"] > 0 and w["t"] > 0 and w["per"] > 0 and w["a"] > 0, (k, w)
            assert w["ring"] <= (w["kind"] == "gas")
            kinds.add(w["kind"])
        assert [w["a"] for w in ws] == sorted(w["a"] for w in ws)
    assert not worlds.planets_of(0) and kinds == set(worlds.KINDS) and total > 10000, (total, kinds)
    first = worlds.planets_of(40)
    worlds._CACHE.clear()
    again = worlds.planets_of(40)
    assert first == again and first is not again, "the worlds of a system must not change"
    for k in range(galaxy.N):                                                # places that are not a star have no planets
        if galaxy.STARS[k]["kind"] in ("Nebula", "Star cluster", "Black hole", "Globular cluster", "Supernova remnant"):
            assert not worlds.planets_of(k), galaxy.STARS[k]
    t1 = worlds.planets_of(galaxy.BY_NAME["TRAPPIST-1"])
    assert [w["name"] for w in t1] == [f"TRAPPIST-1 {c}" for c in "bcdefgh"] and all(w["real"] for w in t1)
    assert t1[3]["kind"] == "temperate" and t1[3]["year"] == 2017 and worlds.origin(t1[3]).startswith("Confirmed exoplanet")
    prox = [w["name"] for w in worlds.planets_of(galaxy.BY_NAME["Proxima Centauri"])]
    assert "Proxima Centauri b" in prox and not any("Proxima" in w["name"] for w in worlds.planets_of(galaxy.BY_NAME["Alpha Centauri"]))
    assert all(not w["real"] and w["name"].split()[-1] in worlds.ROMAN for w in worlds.planets_of(galaxy.BY_NAME["Sirius"]))
    assert len(worlds.REAL) == 31 and sum(len(v) for v in worlds.REAL.values()) == 89
    for r, t, roll, kind in ((11.0, 150, 0.5, "gas"), (4.0, 100, 0.5, "ice_giant"), (2.2, 300, 0.5, "mini"), (0.3, 300, 0.5, "dwarf"),
                             (1.0, 1500, 0.5, "lava"), (0.9, 500, 0.5, "desert"), (1.0, 288, 0.9, "temperate"), (1.0, 288, 0.1, "ocean"),
                             (1.0, 150, 0.2, "ice"), (0.5, 288, 0.5, "rocky")):
        assert worlds.classify(r, t, roll) == kind, (r, t, roll, kind)
    for m in (0.1, 1.0, 5.0, 17.0, 318.0):                                     # mass and radius agree both ways
        assert abs(worlds.mass_from_radius(worlds.radius_from_mass(m)) / m - 1) < 0.2, m
    assert worlds.year_text(1.0) == "24 hours" and worlds.year_text(400) == "400 days" and worlds.year_text(600) == "1.6 years" and "K" in worlds.temp_text(288)
    # what you find follows what you hold
    g = core.Game(load=False, sim=True)
    assert worlds.stats(g.conquered)["total"] == 0 and worlds.found(g.conquered) == [] and worlds.news(0) is None
    k = galaxy.BY_NAME["TRAPPIST-1"]
    g.conquered.add(k)
    st = worlds.stats(g.conquered)
    assert st["total"] == 7 and st["systems"] == 1 and st["real"] == 7 and st["habitable"] == 3 and st["by_kind"]["desert"] == 2
    assert [w["name"] for w in worlds.found(g.conquered, "habitable")] == ["TRAPPIST-1 d", "TRAPPIST-1 e", "TRAPPIST-1 f"]
    assert len(worlds.found(g.conquered, "all", k)) == 7 and worlds.found(g.conquered, "all", 5) == []
    assert "7 worlds" in worlds.news(k) and "3 habitable" in worlds.news(k)
    new = {a["id"] for a in g.check_achievements()}
    assert {"First Light", "Goldilocks", "Seven Sisters"} <= new and not ({"Survey Team", "Known Worlds"} & new), new
    assert len(core.ACHIEVEMENTS) == len({a["id"] for a in core.ACHIEVEMENTS}), "two achievements with the same name"
    assert worldview.summary(k) == "7 worlds: 3 habitable, 4 rocky" and worldview.summary(0) is None
    assert len(worlds.found(set(range(galaxy.N)))) == total


def check_attack_ui(app):
    """Attacking from the map: a drag from a system you hold to a star launches the campaign, Space launches the recommended one,
    a faction at peace asks first, and the dock, the aim arrow and the best-target ring draw at every size, with the panel and wide."""
    fonts = app_fonts()
    VIEW = frontview.VIEW
    g0, view0, tab0, wide0 = app.g, app.view, app.tab, app.gal_wide
    try:
        g = core.Game(load=False, sim=True)
        g.unlocked[2] = True
        g.owned = [[200000 >> i for i in range(NSH)] for _ in range(NSOL)]
        g.armory[core.JUMP] = 8
        g.armory[core.COMMAND] = 2
        g.defence = 0.0
        g.recalc()
        app.g, app.view, app.tab = g, "galaxy", T_GALAXY
        fv = app.fv
        app.war_confirm, app.war_confirm_k = 0.0, None
        fv.best_t = -9.0

        def show(k):
            sx, sy = galaxy.STARS[0]["x"], galaxy.STARS[0]["y"]
            tx, ty = galaxy.STARS[k]["x"], galaxy.STARS[k]["y"]
            fv.look_at((sx + tx) / 2, (sy + ty) / 2, min(14.0, 360.0 / max(1.0, math.hypot(sx - tx, sy - ty))), snap=True)
            app.update(0.016)
            app.draw(app.scr, fonts)
            return {k: (x, y) for x, y, k in fv.pts}
        b = fv.best_target()
        assert b is not None and fv.best == b
        pos = show(b[0])
        assert 0 in pos and b[0] in pos
        # a drag from the home system to the target aims, draws and (the faction being at peace) asks before the war
        fv.down(pos[0])
        assert fv.drag["aim"] == 0
        fv.move(pos[0]); assert fv.aim is None, "a press is not an aim until the pointer moves"
        mid = ((pos[0][0] + pos[b[0]][0]) // 2, (pos[0][1] + pos[b[0]][1]) // 2)
        fv.move(mid); assert fv.aim and fv.aim["src"] == 0
        fv.move(pos[b[0]]); assert fv.aim["hover"] == b[0]
        app.mouse = pos[b[0]]
        app.draw(app.scr, fonts)
        fv.up(pos[b[0]])
        assert fv.aim is None and fv.drag is None
        if b[2]:
            assert not g.campaigns and app.war_confirm > 0 and app.war_confirm_k == b[0], "a peaceful faction asks first"
            app.update(0.016)
            app.draw(app.scr, fonts)                                   # the prompt
            app.attack(b[0])
        assert len(g.campaigns) == 1 and g.campaigns[0]["k"] == b[0] and SECTORS[b[0]]["faction"] in g.war and app.war_confirm == 0
        app.draw(app.scr, fonts)                                       # the dock now lists it
        # a drag from empty space still pans, and a drag from a held star dropped on nothing does nothing
        c0 = (fv.tcx, fv.tcy)
        empty = (VIEW.x + 40, VIEW.centery)
        assert fv.system_at(empty) is None
        fv.down(empty); fv.move((empty[0] + 60, empty[1] + 30)); fv.up((empty[0] + 60, empty[1] + 30))
        assert (fv.tcx, fv.tcy) != c0 and fv.aim is None
        n = len(g.campaigns)
        fv.down(pos[0]); fv.move((pos[0][0] + 8, pos[0][1] + 8)); fv.up((VIEW.x + 12, VIEW.centery))
        assert len(g.campaigns) == n
        # a drop on a system that cannot be attacked says why instead
        fv.down(pos[0]); fv.move(pos[b[0]]); fv.up(pos[b[0]])
        assert len(g.campaigns) == n and any("Cannot attack" in t[0] for t in g.toasts), "the system is already under attack"
        # the campaign arrives, then Space launches the next recommended attack (it asks first about a faction at peace)
        base = dict(g.campaigns[0])
        g.campaigns[0]["chance"], g.campaigns[0]["t"] = 1.0, g.campaigns[0]["dur"]
        g.step(0.01)
        assert b[0] in g.conquered and not g.campaigns
        g.toasts.clear()
        fv.best_t = -9.0
        nb = fv.best_target()
        assert nb is not None and nb[0] != b[0] and nb[0] in g.targets()
        assert fv.key(pygame.K_SPACE)
        if app.war_confirm > 0:
            assert nb[2] and app.war_confirm_k == nb[0] and not g.campaigns
            app.attack(nb[0])
        assert len(g.campaigns) == 1 and g.campaigns[0]["k"] == nb[0]
        g.armory[core.COMMAND] = 0                                     # one front only, and it is used
        g.toasts.clear()
        fv.best_t = -9.0
        assert fv.best_target() is None and fv.key(pygame.K_SPACE) and "fronts" in g.toasts[-1][0].lower() and len(g.campaigns) == 1
        g.armory[core.COMMAND] = 2
        # every size, with the panel and wide, with no campaigns, three and six rows (one by a general), and with the war prompt up
        for res in ("1920x1080", "1600x720", "2560x1440", "1280x720"):
            app.set_resolution_choice(res)
            for wide in (False, True):
                app.gal_wide = wide
                for ncamp in (0, 3, 6):
                    g.campaigns = [dict(base, k=g.targets()[i], t=1.0 + i, dur=60.0, by="g0" if i == 5 else None) for i in range(ncamp)]
                    g.incoming = []
                    app.war_confirm, app.war_confirm_k = (5.0, g.targets()[0]) if ncamp == 3 else (0.0, None)
                    fv.best_t = -9.0
                    app.update(0.016)
                    app.draw(app.scr, fonts)
                    fv.down((VIEW.x + 200, VIEW.y + 200)); fv.move((VIEW.x + 260, VIEW.y + 240)); fv.up((VIEW.x + 260, VIEW.y + 240))
        app.set_resolution_choice("auto")
    finally:
        app.g, app.view, app.tab, app.gal_wide = g0, view0, tab0, wide0
        app.war_confirm, app.war_confirm_k = 0.0, None
        app.fv.best_t = -9.0
        app.fv.aim = app.fv.drag = None
        app.set_resolution_choice("auto")


def check_sysview():
    """The layout of a star's worlds: every star that has worlds gets a sane, deterministic set of orbits."""
    sol = sysview.bodies(0)
    assert len(sol) == NSOL and [b["name"] for b in sol if b["parent"] is None][:3] == ["Mercury", "Venus", "Earth"], "the planets are in order from the Sun"
    assert [b["name"] for b in sol if b["parent"] is not None] == ["Moon"] and sol[-1]["parent"] == ("s", 0), "the Moon orbits the Earth"
    assert sorted(b["p"] for b in sol) == list(range(NSOL)) and sysview.bodies(0) is sol, "every solar planet once, cached"
    planets = [b for b in sol if b["parent"] is None]
    assert all(0 <= b["u"] <= 1 for b in planets) and [b["u"] for b in planets] == sorted(b["u"] for b in planets)
    assert sysview.can_open(core.Game(load=False, sim=True), 0)
    t1 = galaxy.BY_NAME["TRAPPIST-1"]
    tb = sysview.bodies(t1)
    assert len(tb) == 7 and [b["name"][-1] for b in tb] == list("bcdefgh") and all(0 <= b["u"] <= 1 for b in tb)
    n = 0
    for k in range(1, galaxy.N):
        ws = worlds.count_of(k)
        if not ws:
            assert sysview.bodies(k) == []
            continue
        bs = sysview.bodies(k)
        assert len(bs) == ws and len({b["key"] for b in bs}) == ws, k
        assert all(0 <= b["u"] <= 1 and b["size"] >= 16 and 0 < b["w"] <= 0.6 for b in bs), k
        assert all(sysview.STAR_LOOK.get(galaxy.STARS[k]["kind"]) for _ in (0,)), galaxy.STARS[k]["kind"]
        n += 1
    assert n > 3000
    g = core.Game(load=False, sim=True)
    assert not sysview.can_open(g, t1) and not sysview.can_open(g, galaxy.BY_NAME["Nebula 1"] if "Nebula 1" in galaxy.BY_NAME else 1)
    g.conquered.add(t1)
    assert sysview.can_open(g, t1)
    assert sysview.state_of(g, sol[2]) == "here" and sysview.state_of(g, sysview.body_of(0, ("s", 5))) in ("next", "locked")
    assert sysview.state_of(g, sysview.body_of(0, ("s", 1))) == "next"                      # the Moon is the next planet
    g.ore[0] = 1e30
    g.credits = 1e30
    assert sysview.state_of(g, sysview.body_of(0, ("s", 1))) == "ready"
    assert sysview.primary(type("A", (), dict(g=g))(), sysview.body_of(0, ("s", 1)))[0] == "UNLOCK"


def check_sysview_ui(app):
    """The system view draws at every canvas size for the Sun and for a star with worlds, answers clicks on the worlds, the star, the
    buttons and the keys, and the strip's button, S and the Android back button move between the three levels."""
    fonts = app_fonts()
    g0, view0, tab0 = app.g, app.view, app.tab
    sel0, skey0 = app.sel_sector, (app.sys_k, app.sys_sel)
    try:
        g = core.Game(load=False, sim=True)
        app.g = g
        app.rebuild_view()
        t1 = galaxy.BY_NAME["TRAPPIST-1"]
        g.credits = 1e80
        g.conquered.add(t1)
        for k in range(1, 4):
            g.unlocked[k] = True
        for q in range(NSOL):
            g.ore[q] = 1e70
        g.galaxy_open or g.recalc()
        app.view, app.tab = "system", T_PLANETS
        # the three levels: planet -> system (button, S key, strip) -> back
        app.update(0.016)
        app.draw(app.scr, fonts)
        assert app.system_key(pygame.K_s) and app.view == "orbit" and sysview.current_star(app) == 0
        app.update(0.016)
        app.draw(app.scr, fonts)
        assert app.system_key(pygame.K_s) and app.view == "system"
        app.strip_click(-4)
        assert app.view == "orbit"
        app.back_pressed()
        assert app.view == "system"
        assert any(k == -4 for _, k in app.strip_hits), "the strip has the star system button"
        app.update(0.016)
        app.draw(app.scr, fonts)
        for r, fn in app.hud_btns:                                        # the SYSTEM chip of the planet view
            fn()
        assert app.view == "orbit"
        # the Sun: click on a planet selects it, a second click on one you hold goes there
        for res in ("1920x1080", "1280x720", "1600x720", "2560x1440"):
            app.set_resolution_choice(res)
            for k in (0, t1):
                app.sys_k, app.sys_sel = k, None
                app.view = "orbit"
                for tab in (T_PLANETS, T_SHIPS):
                    app.tab = tab
                    app.update(0.016)
                    app.draw(app.scr, fonts)
        app.set_resolution_choice("1280x720")
        app.sys_k, app.sys_sel, app.view = 0, None, "orbit"
        app.update(0.016)
        app.draw(app.scr, fonts)
        hits = {key: (x, y) for x, y, r, key in app.orb_hits}
        assert ("s", 2) in hits and "star" in hits and len(app.orb_hits) == NSOL + 1
        x, y = hits[("s", 2)]
        app.mouse_down((int(x), int(y)))
        assert app.sys_sel == ("s", 2)
        app.draw(app.scr, fonts)
        assert app.orb_btns, "the card has buttons"
        x, y = hits["star"]
        app.mouse_down((int(x), int(y)))
        assert app.sys_sel is None
        app.draw(app.scr, fonts)
        app.sys_sel = ("s", 1)
        for _ in range(3):
            sysview.select_next(app, 1)
        assert app.sys_sel not in (None, ("s", 1))
        app.system_key(pygame.K_LEFT)
        # the planets you hold: go there; the card unlocks the next planet
        g.cur = 0
        app.sys_sel = ("s", 3)
        app.update(0.016)
        app.draw(app.scr, fonts)
        label, fn, ok = sysview.primary(app, sysview.body_of(0, ("s", 3)))
        assert label == "TRAVEL HERE" and ok
        fn()
        assert app.view == "system" and g.cur == 3                          # (a sim game travels at once)
        app.sys_sel, app.view = ("s", 4), "orbit"
        app.update(0.016)
        app.draw(app.scr, fonts)
        label, fn, ok = sysview.primary(app, sysview.body_of(0, ("s", 4)))
        assert label == "UNLOCK" and ok
        fn()
        assert g.unlocked[4]
        # a star with worlds: settle one from the card, then it is lit
        app.sys_k, app.view, app.sys_sel = t1, "orbit", ("w", t1, 3)
        app.update(0.016)
        app.draw(app.scr, fonts)
        n0 = g.n_colonies
        label, fn, ok = sysview.primary(app, sysview.body_of(t1, ("w", t1, 3)))
        assert label == "SETTLE" and ok, label
        pressed = [f for r, f in app.orb_btns if r.collidepoint((app.orbit_area().right - 90, card_y(app) + 30))]
        assert pressed, "the card's main button is on screen"
        pressed[0]()
        assert g.n_colonies == n0 + 1 and sysview.state_of(g, sysview.body_of(t1, ("w", t1, 3))) == "owned"
        assert any("settled by you" in t for t, _ in app.fv.system_lines(t1)[4]), "the system's card says that its colonies are lost with it"
        app.update(0.016)
        app.draw(app.scr, fonts)
        label, fn, ok = sysview.primary(app, sysview.body_of(t1, ("w", t1, 3)))
        assert label == "TRAVEL HERE"
        fn()
        assert g.cur == g.colony_planet[(t1, 3)] and app.view == "system"
        # a star you do not hold has no system view; the galaxy view's buttons reach it for ones you do
        far = next(k for k in range(1, galaxy.N) if k not in g.conquered and worlds.count_of(k))
        g.toasts.clear()
        assert not sysview.open_system(app, far) and g.toasts and app.view == "system"
        app.view, app.sel_sector = "galaxy", t1
        app.gal_wide = True
        app.update(0.016)
        app.fv.focus(t1, snap=True)
        app.draw(app.scr, fonts)
        assert sysview.can_open(g, t1)
        app.view, app.sys_k = "system", None
        # the Galaxy tab's "Open system" button and every tab of the panel (the new header) draw in the system view
        app.tab = T_GALAXY
        app.view = "orbit"
        for tab in range(len(app.tabs)):
            app.tab = tab
            app.update(0.016)
            app.draw(app.scr, fonts)
        app.view, app.tab = "orbit", T_GALAXY
        app.sys_k = 0
        sysview._to_galaxy(app, t1)
        assert app.view == "galaxy" and app.sel_sector == t1
    finally:
        app.g, app.view, app.tab = g0, view0, tab0
        app.sel_sector, (app.sys_k, app.sys_sel) = sel0, skey0
        app.set_resolution_choice("auto")
        app.rebuild_view()


def card_y(app):
    return sysview.card_rect(app).y


def check_blackhole():
    """The Black Hole Bomb: five stages paid in the ore of a tier-11 planet, credits and science once you hold the Void Throne;
    a finished one doubles the Stardust of the Ascension it goes off in and is used up; saves, Warp and Ascension."""
    g = core.Game(load=False, sim=True)
    assert g.bomb == 0 and g.bombs == 0 and not g.bomb_armed() and not g.can_build_bomb()
    costs = [g.bomb_cost(i) for i in range(blackhole.N)]
    base = g.project_cost(NSOL - 1)
    assert all(abs(costs[i][j] / (base[j] * blackhole.STAGES[i]["mult"]) - 1) < 1e-9 for i in range(blackhole.N) for j in range(3))
    assert all(costs[i + 1][0] > costs[i][0] for i in range(blackhole.N - 1)), "every stage costs more than the one before"
    g.credits, g.science = 3 * sum(c[1] for c in costs), 3 * sum(c[2] for c in costs)      # (stocks of the same size as the prices: floats keep the differences)
    g.ore = [3 * sum(c[0] for c in costs)] * g.nsite
    assert not g.can_build_bomb() and not g.build_bomb(), "the Void Throne must be yours first"
    g.conquered.add(core.BOSS)
    assert g.bomb_planet() is None and not g.can_build_bomb(), "the Kuiper Belt (tier 11) pays for it: it must be unlocked"
    g.unlocked[NSOL - 1] = True
    assert g.bomb_planet() == NSOL - 1 and g.can_build_bomb()
    sci = g.science
    g.science = costs[0][2] * 0.5
    assert not g.can_build_bomb(), "science is needed too"
    g.science = sci
    unarmed = None
    for st in range(blackhole.N):
        ore0, cr0, sci0 = g.ore[NSOL - 1], g.credits, g.science
        if st == blackhole.N - 1:
            unarmed = g.sd_gain()
        assert g.build_bomb() and g.bomb == st + 1
        assert abs((ore0 - g.ore[NSOL - 1]) / costs[st][0] - 1) < 1e-6 and abs((cr0 - g.credits) / costs[st][1] - 1) < 1e-6
    assert g.bomb_armed() and not g.can_build_bomb() and not g.build_bomb() and g.bomb == blackhole.N
    assert g.sd_gain() >= 2 * unarmed - 1 and g.sd_gain() > unarmed, "an armed bomb doubles the Stardust"
    assert "Bomb Maker" in {a["id"] for a in core.ACHIEVEMENTS} and core.ACH_BY_ID["Bomb Maker"]["cond"](g)
    assert not core.ACH_BY_ID["Big Bang"]["cond"](g)
    # Warp keeps the bomb; it is part of the galaxy you hold
    assert g.do_warp(force=True) and g.bomb == blackhole.N
    # saves: it comes back, and a save from before there was a bomb loads with none
    old_save = core.SAVE
    d = tempfile.mkdtemp(prefix="space_miner_bomb_")
    try:
        core.SAVE = os.path.join(d, "save.json")
        g.bombs = 2
        g.save()
        h = core.Game(load=True, sim=True)
        assert h.bomb == blackhole.N and h.bombs == 2
        with open(core.SAVE) as f:
            data = json.load(f)
        data.pop("bomb"), data.pop("bombs")
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        h = core.Game(load=True, sim=True)
        assert h.bomb == 0 and h.bombs == 0
        data["bomb"] = 99
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        assert core.Game(load=True, sim=True).bomb == blackhole.N, "a damaged save cannot build a sixth stage"
    finally:
        core.SAVE = old_save
        shutil.rmtree(d, ignore_errors=True)
    # Ascension: the armed bomb goes off (Stardust x2, used up); a half-built one is lost
    g.bombs = 0
    gain, sd0 = g.sd_gain(), g.stardust
    g.toasts.clear()
    assert g.ascend(force=True) and g.stardust == sd0 + max(1, gain) and g.bomb == 0 and g.bombs == 1
    assert any("bomb went off" in t[0] for t in g.toasts)
    assert core.ACH_BY_ID["Big Bang"]["cond"](g) and core.ACH_BY_ID["Bomb Maker"]["cond"](g)
    g.conquered.add(core.BOSS)
    g.bomb = 3
    g.toasts.clear()
    assert g.ascend(force=True) and g.bomb == 0 and g.bombs == 1
    assert not any("bomb went off" in t[0] for t in g.toasts), "an unfinished bomb does not go off"
    text, armed = blackhole.status(blackhole.N)
    assert armed and "Stardust x2" in text and not blackhole.status(2)[1] and "lost" in blackhole.status(2)[0]


def check_hole_ui(app):
    """The Void Throne opens as a black hole in the system view, at every size and at every stage of the bomb; the card builds the
    stages; the Ascension screen and the detonation draw."""
    fonts = app_fonts()
    g0, view0, tab0, wv0 = app.g, app.view, app.tab, app.warp_view
    skey0 = (app.sys_k, app.sys_sel)
    try:
        g = core.Game(load=False, sim=True)
        app.g = g
        app.rebuild_view()
        assert not sysview.can_open(g, core.BOSS) and not sysview.open_system(app, core.BOSS)
        g.conquered.add(core.BOSS)
        for q in range(NSOL):
            g.unlocked[q] = True
            g.ore[q] = 1e300
        g.credits = g.science = 1e300
        assert sysview.can_open(g, core.BOSS) and sysview.open_system(app, core.BOSS) and app.view == "orbit"
        for res in ("1920x1080", "1280x720", "1600x720", "2560x1440"):
            app.set_resolution_choice(res)
            for stage in range(blackhole.N + 1):
                g.bomb = stage
                app.update(0.016)
                app.draw(app.scr, fonts)
        app.set_resolution_choice("1280x720")
        g.bomb = 0
        app.update(0.016)
        app.draw(app.scr, fonts)
        assert not app.orb_hits and app.orb_btns, "nothing to click but the card's button"
        fn = [f for r, f in app.orb_btns if r.collidepoint((sysview.card_rect(app).right - 60, sysview.card_rect(app).y + 26))]
        assert fn, "the BUILD button is on the card"
        for stage in range(blackhole.N):
            app.update(0.016)
            app.draw(app.scr, fonts)
            fn = [f for r, f in app.orb_btns if r.collidepoint((sysview.card_rect(app).right - 60, sysview.card_rect(app).y + 26))]
            assert fn, stage
            fn[0]()
            assert g.bomb == stage + 1
        app.update(0.016)
        app.draw(app.scr, fonts)
        assert not [1 for r, f in app.orb_btns if r.collidepoint((sysview.card_rect(app).right - 60, sysview.card_rect(app).y + 26))], \
            "an armed bomb has nothing left to build"
        app.mouse_down((app.orbit_area().centerx, 200))                          # a click on the black hole does nothing
        app.view, app.sel_sector = "galaxy", core.BOSS                           # the map's command bar offers to open it
        app.update(0.016)
        app.draw(app.scr, fonts)
        # the Ascension screen says what the bomb will do, and the detonation draws
        app.view, app.tab, app.warp_view = "system", T_WARP, "ascend"
        app.update(0.016)
        app.draw(app.scr, fonts)
        g.sim = False                                                            # (the effects are only made for a game that is played)
        for _ in range(2):
            app.do_ascend()
        app.update(0.016)
        assert app.ascend_boom and app.ascend_len > 3.4 and g.bombs == 1 and g.bomb == 0
        for _ in range(8):
            app.update(0.4)
            app.draw(app.scr, fonts)
        g.conquered.add(core.BOSS)
        g.bomb = 2
        app.update(0.016)
        app.draw(app.scr, fonts)                                                 # an unfinished bomb: the warning on the Ascension screen
    finally:
        app.g, app.view, app.tab, app.warp_view = g0, view0, tab0, wv0
        app.sys_k, app.sys_sel = skey0
        app.ascend_boom, app.ascend_len, app.ascend_fx = False, 3.4, 0.0
        app.set_resolution_choice("auto")
        app.rebuild_view()


def check_fast_mode(app):
    """Fast mode (the phone's): the canvas of a phone, a backdrop baked once, a panel drawn a few times a second whose buttons keep
    working, cached texts and asteroids; every view draws the same in both modes."""
    fonts = app_fonts()
    assert android_canvas(2400, 1080) == (1280, 576) and android_canvas(1920, 1080) == (1280, 720) and android_canvas(1080, 2400) == (1280, 576)
    assert android_canvas(2340, 1080)[0] == 1280 and 540 <= android_canvas(3200, 1080)[1] <= 600
    g0, view0, tab0, touch0 = app.g, app.view, app.tab, resources.TOUCH
    try:
        g = core.Game(load=False, sim=True)
        app.g = g
        app.rebuild_view()
        for touch, want in ((False, False), (True, True)):
            resources.TOUCH = touch
            g.settings["perf"] = "auto"
            assert app.fast is want
        g.settings["perf"] = "on"
        assert app.fast
        g.settings["perf"] = "off"
        resources.TOUCH = True
        assert not app.fast
        g.settings["perf"] = "auto"
        app.cycle_perf(); assert g.settings["perf"] == "on" and app.fast
        app.cycle_perf(); assert g.settings["perf"] == "off" and not app.fast
        app.cycle_perf(); assert g.settings["perf"] == "auto"
        resources.TOUCH = False
        g.credits = 1e30
        for k in range(1, 4):
            g.unlocked[k] = True
        for q in range(NSOL):
            g.ore[q] = 1e30
        for mode in ("on", "off"):
            g.settings["perf"] = mode
            for res in ("1280x576", "1280x720", "1920x1080", "1600x720"):
                app.set_resolution_choice(res)
                for view in ("system", "orbit", "galaxy"):
                    for tab in range(len(app.tabs)):
                        app.view, app.tab = view, tab
                        app.sys_k = 0
                        app.update(0.016)
                        app.draw(app.scr, fonts)
        app.set_resolution_choice("1280x576")
        assert (W, H) == (1280, 576) and PANEL.right <= W and PANEL.bottom <= H
        # the panel is drawn a few times a second: the frames in between keep its buttons, and a tap shows its result at once
        g.settings["perf"] = "on"
        app.view, app.tab, app.gal_wide = "system", T_SHIPS, False
        app.update(0.016); app.draw(app.scr, fonts)
        n = len(app.buttons)
        assert n > 10 and app.pc is not None and app.pc_key[0] == T_SHIPS
        t0 = app.pc_t
        app.update(0.016); app.draw(app.scr, fonts)
        assert app.pc_t == t0 and len(app.buttons) == n, "the panel is not drawn again every frame"
        tab_btn = next(r for r, fn in app.buttons if r.y < 60 and r.x > PANEL.x + 3 * (PANEL.w // len(app.tabs)))     # a tab to the right
        app.mouse_down(tab_btn.center)
        assert app.tab != T_SHIPS and app.pc_dirty
        app.update(0.016); app.draw(app.scr, fonts)
        assert app.pc_key[0] == app.tab and not app.pc_dirty
        app.scroll[app.tab] += 40
        app.update(0.016); app.draw(app.scr, fonts)
        assert app.pc_key[1] == app.scroll[app.tab], "scrolling draws the panel again at once"
        for _ in range(10):                                   # and it is drawn again a few times a second all the same
            app.update(0.05); app.draw(app.scr, fonts)
        assert app.t - app.pc_t < 0.2
        # the baked backdrop follows what is shown
        fb = app.fb
        app.view = "galaxy"; app.draw(app.scr, fonts)
        assert app.fb is not fb
        app.view = "system"; app.draw(app.scr, fonts)
        # cached texts and turned asteroids
        f = fonts[3]
        assert app.rendered(f, "cache me", (1, 2, 3)) is app.rendered(f, "cache me", (1, 2, 3))
        assert app.ast_rot and len(app.ast_rot) < 4001
        # the Stats page has the switches
        app.tab = T_AWARDS
        app.awards_cat = "Stats"
        g.settings["show_fps"] = True
        app.update(0.016); app.draw(app.scr, fonts)
        g.settings["show_fps"] = False
    finally:
        resources.TOUCH = touch0
        app.g, app.view, app.tab = g0, view0, tab0
        app.awards_cat = "All"
        app.set_resolution_choice("auto")
        app.rebuild_view()
        app.fb, app.pc_dirty = None, True


def check_quality(app):
    """The quality levels of fast mode: slow frames lower them (and quick ones raise them again, slowly), every level draws every view, and
    the shipped Milky Way is the picture the map would paint."""
    fonts = app_fonts()
    g0, view0, tab0 = app.g, app.view, app.tab
    q0 = app.q
    try:
        g = core.Game(load=False, sim=True)
        app.g = g
        app.rebuild_view()
        g.settings["perf"] = "on"
        for k in range(1, 4):
            g.unlocked[k] = True
        g.owned = [[30 - 3 * i for i in range(NSH)] for _ in range(NSOL)]
        g.recalc()
        app.q, app.dt = 0, 0.033
        for _ in range(20):                                                      # a spell of 40 ms frames is too slow; two of them lower the level
            app.perf_sample(0.040)
        assert app.q == 0
        for _ in range(20):
            app.perf_sample(0.040)
        assert app.q == 1, app.q
        for _ in range(400):
            app.perf_sample(0.040)
        assert app.q == 3, "it goes down to the lowest level and no further"
        for _ in range(600):
            app.perf_sample(0.020)                                               # in between: nothing changes
        assert app.q == 3
        for _ in range(2000):                                                    # quick frames bring it back, a level every half minute
            app.perf_sample(0.006)
        assert app.q == 1, app.q
        app.q = 3
        g.settings["perf"] = "off"
        app.perf_sample(0.2)
        assert app.q == 0, "outside fast mode the game always draws everything"
        g.settings["perf"] = "on"
        for q in range(4):
            app.q = q
            app.view, app.tab = "system", T_SHIPS
            app.parts.append([CX, CY, 10.0, 10.0, 0.5, (255, 200, 100)])
            app.spawn_raid(dict(tier=0, faction="pirates", win=False, lost=[]))
            for _ in range(3):
                app.update(0.016)
                app.draw(app.scr, fonts)
        app.raiders.clear()
        assert app.raid_rot, "the turned raiders are kept"
    finally:
        app.q = q0
        app.g, app.view, app.tab = g0, view0, tab0
        app.rebuild_view()
    # the shipped Milky Way is what gfx would paint (and has the size the map expects)
    shipped = pygame.image.load(resources.resource("assets/milky_way.png"))
    assert shipped.get_size() == (frontview.IMG, frontview.IMG), "run tools/make_milky_way.py"
    assert frontview.milky_way_picture().get_size() == (frontview.IMG, frontview.IMG)
    painted = gfx.make_milky_way(frontview.IMG)
    for x, y in ((650, 650), (300, 700), (900, 400), (100, 100), (1200, 1250), (640, 500), (700, 820)):
        assert tuple(shipped.get_at((x, y)))[:3] == tuple(painted.get_at((x, y)))[:3], ("assets/milky_way.png is out of date: run tools/make_milky_way.py", x, y)


def check_worlds_ui(app):
    """The Other systems page draws and answers clicks with nothing found, a few worlds and every world of the galaxy."""
    fonts = app_fonts()
    g0, view0, tab0, page0 = app.g, app.view, app.tab, app.pl_page
    try:
        g = core.Game(load=False, sim=True)
        app.g = g
        app.view, app.tab, app.pl_page = "system", T_PLANETS, 2
        app.w_known = app.w_sig = app.w_cache = app.wsel = None
        for held in (None, {0, 1, 2}, set(range(galaxy.N))):
            g.unlocked[core.GALAXY_UNLOCK_PLANET] = held is not None
            if held:
                g.conquered = set(held)
            for scroll in (0, 700, 10 ** 6):
                app.scroll[T_PLANETS] = scroll
                app.update(0.016)
                app.draw(app.scr, fonts)
        k = galaxy.BY_NAME["TRAPPIST-1"]
        g.conquered = {0, k}
        g.unlocked[core.GALAXY_UNLOCK_PLANET] = True
        app.scroll[T_PLANETS] = 0
        for res in ("1920x1080", "2560x1440", "1600x720", "1280x720"):      # the page follows the side panel on every canvas
            app.set_resolution_choice(res)
            assert worldview.PANEL == PANEL, res
            app.buttons.clear()
            app.draw(app.scr, fonts)
            inside = [r for r, _ in app.buttons if r.y > PANEL.y and r.y < PANEL.y + 80 and PANEL.contains(r)]
            assert len(inside) >= 2, (res, "the Other systems page is not drawn inside the side panel", PANEL, inside)
        g.conquered = {0}
        app.w_known = app.w_sig = None
        g.toasts.clear()
        app.update(0.016)                                                      # the first look only learns what you hold
        assert not g.toasts
        g.conquered = {0, k}
        app.update(0.016)
        assert any("7 worlds" in t[0] for t in g.toasts), "liberating a star with real planets should be announced"
        app.draw(app.scr, fonts)
        w = worlds.planets_of(k)[3]
        worldview.select(app, w)
        assert worldview.selected(app) is w
        for grp, _ in worlds.GROUPS:
            worldview.set_filter(app, grp, None)
            app.draw(app.scr, fonts)
            assert len(worldview.world_list(app, None)) == len(worlds.found(g.conquered, grp))
        worldview.set_filter(app, "all", k)
        app.sel_sector = k
        app.draw(app.scr, fonts)
        assert len(worldview.world_list(app, k)) == 7
        worldview.show_on_map(app, k)
        assert app.view == "galaxy" and app.sel_sector == k
        app.pl_page = 0
        app.draw(app.scr, fonts)
        worldview.set_page(app, 2)
        assert app.pl_page == 2 and app.scroll[app.tab] == 0
        g.conquered = {0}                                                      # a selected world that is no longer yours
        assert worldview.selected(app) is None
        app.draw(app.scr, fonts)
    finally:
        app.g, app.view, app.tab, app.pl_page = g0, view0, tab0, page0
        app.w_known = app.w_sig = app.w_cache = app.wsel = None
        app.scroll[T_PLANETS] = 0


def check_colonies_ui(app):
    """The Colonies page, the strip and every tab draw for colony worlds, at every canvas size, and a click settles a world."""
    fonts = app_fonts()
    g0, view0, tab0, page0 = app.g, app.view, app.tab, app.pl_page
    sel0 = app.sel_sector
    try:
        g = core.Game(load=False, sim=True)
        app.g = g
        app.rebuild_view()
        t1, pr = galaxy.BY_NAME["TRAPPIST-1"], galaxy.BY_NAME["Proxima Centauri"]
        g.credits = 1e80
        g.conquered |= {t1, pr, galaxy.BY_NAME["Tau Ceti"], galaxy.BY_NAME["Kepler-186"]}
        for k in range(1, 7):
            g.unlocked[k] = True
        for q in range(NSOL):
            g.ore[q] = 1e70
        app.view, app.tab, app.pl_page = "system", T_PLANETS, 1
        app.sel_sector = t1
        app.cl_cache, app.cl_ready_t = None, -1
        lists = worldview.colony_lists(app)
        assert (t1, 3) in lists["ready"] and not lists["settled"] and worldview.colony_ready(app)
        for res in ("1920x1080", "1280x720", "1600x720"):
            app.set_resolution_choice(res)
            for flt in ("ready", "settled", "waiting", "star"):
                worldview.set_cl_filter(app, flt)
                for scroll in (0, 900, 10 ** 6):
                    app.scroll[T_PLANETS] = scroll
                    app.buttons.clear()
                    app.update(0.016)
                    app.draw(app.scr, fonts)
        app.set_resolution_choice("1280x720")
        worldview.set_cl_filter(app, "ready")
        app.scroll[T_PLANETS] = 0
        app.buttons.clear()
        app.draw(app.scr, fonts)
        n0 = g.n_colonies
        rows = [fn for r, fn in app.buttons if r.y > PANEL.y + 120 and PANEL.contains(r)]
        assert rows, "the ready worlds have SETTLE buttons"
        rows[0]()
        assert g.n_colonies == n0 + 1, "clicking a world settles it"
        app.draw(app.scr, fonts)
        assert worldview.colony_lists(app)["settled"] == [g.colonies[-1]]
        worldview.settle_all(app)
        assert g.n_colonies > n0 + 1, "settle all settles every world you can pay for"
        # a lot of colonies: the strip shows them after the solar planets and scrolls
        g.conquered |= set(range(1, 150))
        g.credits = 1e300
        for q in range(NSOL):
            g.ore[q] = 1e90
        for k, i in g.world_options()[:60]:
            g.settle(k, i)
        assert g.nsite >= NSOL + 30
        for q in range(g.nsite):
            g.ore[q] = 1e90
        ents = app.strip_entries()
        assert ents == list(range(g.nsite)) and app.strip_cap() < len(ents)
        app.view = "system"
        app.draw(app.scr, fonts)
        hits = [k for _, k in app.strip_hits]
        assert -3 in hits and -2 in hits
        off = app.strip_off
        app.strip_click(-3)
        assert app.strip_off == off + 4
        for _ in range(g.nsite):
            app.strip_click(-2)
        assert app.strip_off == 0
        last = g.nsite - 1
        g.cur = last                                                           # travelling to a far colony scrolls the strip to it
        app.draw(app.scr, fonts)
        assert app.strip_off > 0 and last in app.strip_pos
        seen_kinds = set()
        for p in range(NSOL, g.nsite):                                         # every tab draws for every kind of world
            kind = g.sites[p]["wkind"]
            if kind in seen_kinds and p != last:
                continue
            seen_kinds.add(kind)
            g.cur = p
            g.owned[p] = [40, 30, 20, 10, 5, 2, 1, 1, 0, 0]                    # ships to list upgrades for and to draw
            g.ore[p] = 1e90
            g.recalc()
            app.rebuild_view()
            for tab in range(len(app.tabs)):
                app.tab = tab
                app.update(0.016)
                app.draw(app.scr, fonts)
            app.mouse = (app.strip_pos.get(p, STRIP_X0), STRIP_Y)
            app.draw(app.scr, fonts)
            for i in range(NSH):
                assert app.ship_sprite(p, i).get_width() > 8
        app.tab = T_AWARDS
        app.awards_cat = "Stats"
        app.draw(app.scr, fonts)
        app.awards_cat = "All"
    finally:
        app.g, app.view, app.tab, app.pl_page = g0, view0, tab0, page0
        app.sel_sector = sel0
        app.rebuild_view()
        app.set_resolution_choice("1280x720")
        app.strip_off, app.strip_cur = 0, None
        app.scroll[T_PLANETS] = 0
        app.cl_cache, app.cl_ready_t = None, -1
        app.mouse = (20, 20)


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
    g.owned = [[200000 >> i for i in range(NSH)] for _ in range(NSOL)]
    g.armory[core.JUMP] = 4
    g.defence = 0.0                                                      # (the whole fleet is free for manual campaigns here)
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


def check_attack_flow():
    """The recommended attack (Space / the dock's button): the strongest system the free fleet beats with 90% odds, at war first."""
    g = core.Game(load=False, sim=True)
    assert front.best_target(g) is None and "not open" in front.why_no_best(g)
    g.unlocked[2] = True
    g.owned = [[20000000 >> i for i in range(NSH)] for _ in range(NSOL)]
    g.armory[core.JUMP] = 14
    g.armory[core.COMMAND] = 2
    g.defence = 0.0
    g.recalc()
    assert g.galaxy_open
    ok = [k for k in g.targets() if not g.attack_block(k) and win_chance(g.free_power(), g.sector_power(k)) >= front.BEST_ODDS]
    assert len(ok) >= 5, len(ok)
    b = front.best_target(g)
    assert b is not None and b[0] in ok and b[1] >= front.BEST_ODDS - 1e-9 and b[1] == g.attack_chance(b[0])
    top = max(SECTORS[k]["lp"] for k in ok)
    assert SECTORS[b[0]]["lp"] == top, "the best attack is the strongest one that is safe"
    assert b[2] == (SECTORS[b[0]]["faction"] not in g.war), "it says whether it declares war"
    # a faction you are at war with comes first, even when a stronger system of another one is in reach
    foes = {SECTORS[k]["faction"] for k in ok}
    assert len(foes) >= 2, foes
    weak = min(ok, key=lambda k: SECTORS[k]["lp"])
    director.declare_war(g, SECTORS[weak]["faction"], "player")
    b = front.best_target(g)
    assert SECTORS[b[0]]["faction"] in g.war and not b[2], "systems of factions at war come first"
    # nothing to launch: no fleet to spare, no front left, and a fleet too weak for anything in reach
    assert g.start_campaign(b[0])
    assert front.best_target(g) is None or front.best_target(g)[0] != b[0], "never the system already under attack"
    g.campaigns = []
    g.commit = 3
    assert g.start_campaign(b[0]) and front.best_target(g) is None and "No fleet" in front.why_no_best(g)
    g.campaigns, g.commit = [], 1
    g.armory[core.COMMAND] = 0
    assert g.start_campaign(ok[0]) and front.best_target(g) is None and "fronts" in front.why_no_best(g)
    g.campaigns = []
    g.owned = [[1] + [0] * (NSH - 1) for _ in range(NSOL)]
    g.recalc()
    assert front.best_target(g) is None and "90%" in front.why_no_best(g)


def check_lose_colonies():
    """Losing a system takes the worlds settled in it: their planets leave every table and the planets after them move up, with every
    planet number the game holds (the planet you are on, a journey, visited places, quests, raids on their way)."""
    g = core.Game(load=False, sim=True)
    A, B = galaxy.BY_NAME["TRAPPIST-1"], galaxy.BY_NAME["Proxima Centauri"]
    g.conquered |= {A, B}
    g.credits = 1e80
    for k in range(1, 7):
        g.unlocked[k] = True
    for q in range(NSOL):
        g.ore[q] = 1e70
    order = [(A, 0), (B, 0), (A, 1), (B, 1), (A, 2)]                       # the planets of the two stars alternate: 12 A, 13 B, 14 A, 15 B, 16 A
    for k, i in order:
        assert g.settle(k, i) is not None
    assert g.nsite == NSOL + 5 and [g.colony_planet[c] for c in order] == [12, 13, 14, 15, 16]
    uids = list(core.UPG_BY_ID)
    for p in range(NSOL, g.nsite):                                         # every planet has its own ore, ships, upgrades and buildings
        g.ore[p], g.owned[p][0], g.bld[p][0] = 1000.0 + p, p, p
        g.ups[p] = {uids[p]}
    g.recalc()
    fleet = g.total_ships()
    assert g.lose_colonies(galaxy.BY_NAME["Tau Ceti"]) == [] and g.nsite == NSOL + 5, "a system with none of your worlds loses nothing"
    g.cur = 15
    g.visited |= {12, 13, 14, 15, 16}
    g.quests = [dict(k="clicks", tgt=10, base=0, r="ore", amt=5.0, site=16), dict(k="clicks", tgt=10, base=0, r="ore", amt=5.0, site=13)]
    g.incoming = [dict(id=1, kind="raid", tier=0, fac="pirates", src=A, targets=[12, 13, 16], t=0.0, eta=60.0, fort=[16, 13], power=1.0),
                  dict(id=2, kind="raid", tier=0, fac="pirates", src=A, targets=[14], t=0.0, eta=60.0, fort=[], power=1.0),
                  dict(id=3, kind="offensive", tier=-1, fac="pirates", src=A, target=A, targets=[], t=0.0, eta=60.0, fort=[A], power=1.0)]
    g.travel = dict(to=13, t=0.0, dur=3.0, swapped=False)
    names = g.lose_colonies(A)
    assert len(names) == 3 and all(n.startswith("TRAPPIST-1") for n in names)
    assert g.nsite == NSOL + 2 and g.colonies == [(B, 0), (B, 1)] and g.colony_set == {(B, 0), (B, 1)}
    assert [g.colony_planet[c] for c in g.colonies] == [12, 13] and [s["name"] for s in g.sites[NSOL:]] == [worlds.planets_of(B)[i]["name"] for i in (0, 1)]
    assert len({len(x) for x in (g.ore, g.run_ore, g.all_ore, g.owned, g.ups, g.unlocked, g.bld, g.sites, g.tier, g.sc, g.csc, g.s_ops)}) == 1
    assert g.ore[12] == 1013.0 and g.ore[13] == 1015.0 and g.owned[12][0] == 13 and g.owned[13][0] == 15 and g.bld[13][0] == 15
    assert g.ups[12] == {uids[13]} and g.ups[13] == {uids[15]}, "a planet keeps its own upgrades"
    assert g.total_ships() == fleet - (12 + 14 + 16), "the ships of the lost planets are gone"
    assert g.cur == 13 and g.travel["to"] == 12, (g.cur, g.travel)
    assert {0, 12, 13} <= g.visited and not g.visited & {14, 15, 16}, g.visited
    assert [q["site"] for q in g.quests] == [0, 12], "a quest on a lost planet pays on Earth"
    assert [(i["id"], i["targets"], i["fort"]) for i in g.incoming] == [(1, [12], [12]), (3, [], [A])], "a raid on lost planets is dropped, the others follow their planets"
    assert all(g.kind_first[w] in g.colony_set for w in g.kind_first), "the planet bonuses come from worlds you still hold"
    assert g.fleet_power() > 0 and g.G > 0
    # on a lost planet: back to Earth, and a journey there is cancelled
    g2 = core.Game(load=False, sim=True)
    g2.conquered.add(A)
    g2.credits = 1e80
    for k in range(1, 7):
        g2.unlocked[k] = True
    for q in range(NSOL):
        g2.ore[q] = 1e70
    assert g2.settle(A, 0) == 12 and g2.settle(A, 1) == 13
    g2.cur = 13
    g2.travel = dict(to=12, t=0.0, dur=3.0, swapped=False)
    assert len(g2.lose_colonies(A)) == 2 and g2.cur == 0 and g2.travel is None and g2.nsite == NSOL
    assert g2.colonies == [] and g2.kind_first == {}
    # the director's counter-offensive does it when it takes the system, and it is saved and loaded as it is
    g3 = core.Game(load=False, sim=True)
    g3.conquered.add(A)
    g3.credits = 1e80
    for k in range(1, 7):
        g3.unlocked[k] = True
    for q in range(NSOL):
        g3.ore[q] = 1e70
    for i in range(3):
        assert g3.settle(A, i) is not None
    inc = dict(id=9, kind="offensive", tier=-1, fac="pirates", src=A, target=A, targets=[], t=0.0, eta=0.0, fort=[], power=1e300)
    g3.toasts.clear()
    director.resolve_offensive(g3, inc)
    assert A not in g3.conquered and A in g3.lost_sectors and g3.nsite == NSOL and not g3.colonies
    assert any("lost with it" in t[0] for t in g3.toasts) and any("3 colonies" in e[1] for e in g3.director_log)
    old_save = core.SAVE
    d = tempfile.mkdtemp(prefix="space_miner_lose_")
    try:
        core.SAVE = os.path.join(d, "save.json")
        g.save()
        h = core.Game(load=True, sim=True)
        assert h.colonies == [(B, 0), (B, 1)] and h.nsite == NSOL + 2 and h.cur == 13, (h.colonies, h.nsite, h.cur)
        assert h.owned[12][0] == 13 and h.owned[13][0] == 15 and h.ups[13] == {uids[15]}, "the planets come back with what they had"
    finally:
        core.SAVE = old_save
        shutil.rmtree(d, ignore_errors=True)


def check_generals():
    """Generals and wardens: earned from command systems, orders (heading / toward / region / anywhere + conditions), their
    own armies, tallies and pauses, the defence pool with postures and wardens, the war while you are away, and saves."""
    assert len(generals.GENERAL_IDS) == 8 and len(generals.WARDEN_IDS) == 4 and len(set(generals.SYSTEM_OF)) == 12
    assert all(c[3] in generals.TRAITS and c[0] in galaxy.BY_NAME for c in generals.COMMANDERS)

    def fresh():
        g = core.Game(load=False, sim=True)
        g.unlocked[2] = True
        g.owned = [[200000 >> i for i in range(NSH)] for _ in range(NSOL)]
        g.armory[core.JUMP] = 6
        g.recalc()
        g.grace = 0.0
        return g
    g = fresh()
    ac, bs = galaxy.BY_NAME["Alpha Centauri"], galaxy.BY_NAME["Barnard's Star"]
    assert not g.cmd
    g.conquered.add(ac)
    assert generals.ensure(g) == [0] and g.cmd[0]["army"] == generals.ARMY_DEFAULT and generals.ensure(g) == [], "earned once"
    g.conquered.add(bs)
    assert generals.ensure(g) == [1] and g.cmd[1]["region"] == SECTORS[bs]["region"] and "retake" in g.cmd[1]
    # ---- the pools: defence, armies and manual campaigns are separate shares of the fleet
    assert abs(g.manual_cap() - (1 - g.defence - 0.1)) < 1e-9 and abs(g.free_share("g0") - 0.1) < 1e-9
    generals.set_defence(g, 0.8)
    assert generals.army_total(g) <= 0.2 + 1e-9, "the army must shrink to fit beside the defence"
    generals.set_defence(g, 0.35)
    generals.set_army(g, 0, 5.0)
    assert abs(g.cmd[0]["army"] - 0.65) < 1e-9
    generals.set_army(g, 0, 0.1)
    # ---- orders
    st = g.cmd[0]
    generals.set_orders(st, mode="heading", angle=0.0, war="any", odds=0.9, prefer="nearest")
    k = generals.choose(g, 0, st)
    assert k is not None and galaxy.XS[k] >= galaxy.XS[g.source_of(k)[0]] - 1e-9, "heading east must go east"
    generals.set_orders(st, angle=math.pi)
    k = generals.choose(g, 0, st)
    assert k is not None and galaxy.XS[k] <= galaxy.XS[g.source_of(k)[0]] + 1e-9, "heading west must go west"
    generals.set_orders(st, mode="any", war="declared")
    assert generals.choose(g, 0, st) is None, "a general that may only fight factions at war does not start a war"
    goal = max(g.targets(), key=lambda q: galaxy.dist(0, q))
    generals.set_orders(st, mode="toward", goal=goal, war="any")
    k = generals.choose(g, 0, st)
    assert k is not None and galaxy.dist(k, goal) < galaxy.dist(g.source_of(k)[0], goal), "toward a place must close in on it"
    generals.set_orders(st, mode="region", region="Perseus Arm")
    assert generals.choose(g, 0, st) is None and st["status"], "no target in a region that is out of reach"
    generals.set_orders(st, mode="any", war="any", odds=0.9, prefer="strongest")
    strongest = generals.choose(g, 0, st)
    generals.set_orders(st, prefer="weakest")
    weakest = generals.choose(g, 0, st)
    assert SECTORS[weakest]["lp"] <= SECTORS[strongest]["lp"]
    generals.set_orders(st, prefer="nearest", odds=0.99)
    assert generals.choose(g, 0, st) is not None and generals.slots(0, st) == 1
    # ---- an army launches its own campaigns, from its own share, and the manual pool stays free
    generals.step(g, 3.0)
    assert len(g.campaigns) == 1 and g.campaigns[0]["by"] == "g0" and g.campaigns[0]["share"] <= st["army"] + 1e-9
    assert abs(g.free_share() - g.manual_cap()) < 1e-9 and g.free_fronts() == g.max_fronts()
    generals.step(g, 3.0)
    assert len(g.campaigns) == 1, "one slot: it does not launch a second campaign"
    c = g.campaigns[0]
    c["chance"], c["t"] = 1.0, c["dur"]
    g.war_step(0.01)
    assert st["took"] == 1 and st["run"] == 1 and c["k"] in g.conquered and c not in g.campaigns   # (it may have sent the next at once)
    g.campaigns = []
    # ---- defeats pause a general until you resume it; the stop-after limit counts the run
    for _ in range(generals.STOP_DEFEATS):
        st["idle"] = 0.0
        generals.step(g, 3.0)
        assert g.campaigns, "the general should have launched"
        g.campaigns[0]["chance"], g.campaigns[0]["t"] = 0.0, g.campaigns[0]["dur"]
        g.war_step(0.01)
    assert st["paused"] and st["lost"] == generals.STOP_DEFEATS
    generals.step(g, 30.0)
    assert not g.campaigns, "a paused general stays put"
    generals.resume(st)
    assert not st["paused"] and st["streak"] == generals.STOP_DEFEATS
    generals.set_orders(st, limit=3, odds=0.99)
    st["run"] = 3
    assert generals.choose(g, 0, st) is None and st["status"] == "Limit reached"
    generals.set_orders(st, limit=0)
    # ---- the defence: postures share the pool between regions, wardens strengthen one
    pool = generals.defence_pool(g)
    assert pool == g.fleet_power() * g.defence
    reg = SECTORS[ac]["region"]
    other = next(r for r in generals.REGIONS if r != reg)
    both = generals.defence_map(g, (other,))
    assert abs(sum(both.values()) - pool * generals.warden_mult(g, reg) - 0.0) < pool * 0.5 + 1, "(the warden adds to its region)"
    g.cmd[1]["on"] = False
    both = generals.defence_map(g, (other,))
    assert abs(both[reg] + both[other] - pool) < 1e-6 * pool, "the regions share the whole pool"
    g.posture[reg], g.posture[other] = "fortress", "skeleton"
    both = generals.defence_map(g, (other,))
    assert abs(both[reg] / both[other] - generals.POSTURE_W["fortress"] / generals.POSTURE_W["skeleton"]) < 1e-9
    g.posture.clear()
    g.cmd[1]["on"], g.cmd[1]["region"] = True, reg
    assert generals.warden_mult(g, reg) == generals.WARDEN_BONUS["bastion"] and generals.warden_mult(g, other) == 1.0
    # a warden retakes a system lost in its region (and only one at war with you)
    t = next(q for q in g.targets() if SECTORS[q]["region"] == reg)
    director.declare_war(g, SECTORS[t]["faction"], "enemy")
    g.incoming = []
    g.lost_sectors.add(t)
    g.campaigns = []
    g.cmd[0]["on"] = False                                                 # (so the general does not take it first)
    g.cmd[1]["idle"] = 0.0
    generals.step(g, 3.0)
    assert any(c.get("by") == "w1" and c["k"] == t for c in g.campaigns), "the warden should retake the lost system"
    assert generals.defence_pool(g) < pool, "the retaking force is not defending meanwhile"
    # ---- the war goes on while you are away, by the same rules, and a reload cannot reroll it
    old_save = core.SAVE
    d = tempfile.mkdtemp(prefix="space_miner_generals_")
    try:
        core.SAVE = os.path.join(d, "save.json")
        g = fresh()
        g.conquered.add(ac)
        generals.ensure(g)
        generals.set_orders(g.cmd[0], mode="any", war="any", prefer="nearest", odds=0.7)
        g.defence = 0.3
        g.posture["Orion Spur"] = "fortress"
        k0 = g.targets()[0]
        assert g.start_campaign(k0, by="g0", pmult=1.0)
        g.campaigns[0]["chance"] = 0.5
        g.save()
        with open(core.SAVE) as f:
            data = json.load(f)
        assert data["cmd"]["0"]["army"] == g.cmd[0]["army"] and data["posture"] == {"Orion Spur": "fortress"} and data["defence"] == 0.3
        data["time"] = time.time() - 3 * 3600
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        a, b = core.Game(load=True), core.Game(load=True)
        assert a.conquered == b.conquered and a.battles_won == b.battles_won and a.battles_lost == b.battles_lost, "reloading rerolled the war"
        assert len(a.conquered) > 2 or a.battles_lost > 0, "three hours away: the campaign must have been fought"
        assert a.cmd[0]["army"] == g.cmd[0]["army"] and a.defence == 0.3 and a.posture == {"Orion Spur": "fortress"}
        assert 0 in a.cmd and a.cmd[0]["took"] + a.cmd[0]["lost"] >= 1, "the general should have fought while you were away"
        # a save from before commanders: no defence, no commanders, campaigns without a tag, no dice
        for key in ("cmd", "defence", "posture", "rng"):
            data.pop(key)
        data["time"] = time.time()
        for c in data["campaigns"]:
            c.pop("by", None)
        with open(core.SAVE, "w") as f:
            json.dump(data, f)
        h = core.Game(load=True)
        assert h.defence == core.DEFENCE_DEFAULT and h.posture == {} and 0 in h.cmd, "(Alpha Centauri is held: its general is earned)"
        assert all(c.get("by") is None for c in h.campaigns)
    finally:
        core.SAVE = old_save
        shutil.rmtree(d, ignore_errors=True)


def check_counter_offensives():
    """Enemies take systems back: the defence pool of the region defends them, armies on campaign do not, and several enemy
    fronts strike at once and share the pool."""
    def setup():
        g = core.Game(load=False, sim=True)
        g.unlocked[2] = True
        g.owned = [[200000 >> i for i in range(NSH)] for _ in range(NSOL)]
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
    pool = generals.defence_pool(g)
    assert pool == g.fleet_power() * g.defence and director.sector_defense(g, k, strikes=2) <= director.sector_defense(g, k) + 1e-9
    assert generals.defence_power(g, k) == pool * generals.warden_mult(g, generals.region_of(k))   # (one exposed region: all of it)
    inc = director.schedule_offensive(g, target=k, lead=0)                 # lead 0: it hits at once
    assert inc and k in g.conquered and g.offensives_repelled == 1, "the defence pool should hold the system"
    g.commit = 3                                                           # armies and campaigns away defend nothing...
    far = next(q for q in sorted(g.targets(), key=lambda q: SECTORS[q]["lp"]) if q != k and q not in g.conquered)
    a0 = director.aggression(g)
    assert g.start_campaign(far) and generals.defence_pool(g) == pool, "a campaign must not weaken the defence"
    assert director.aggression(g) > a0, "the enemy grows bolder while the armies are away"
    generals.set_defence(g, 0.0)                                           # ...and with nothing set aside a thin garrison falls
    assert generals.defence_pool(g) == 0.0
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
        check_colonies()
        check_worlds()
        check_fronts()
        check_attack_flow()
        check_sysview()
        check_blackhole()
        check_generals()
        check_counter_offensives()
        check_lose_colonies()
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
        g.ore = [1e15 * g.sc[i] for i in range(NSOL)]
        g.run_ore = list(g.ore); g.all_norm = g.run_norm = 1e20
        g.credits = 1e15; g.science = 1e12
        for k in range(NSOL):
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
        for p in range(NSOL):
            g.buy_project(p)
        g.buy_mode = 0
        for p in range(NSOL):
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
        g.owned = [[40 + k, 30, 20, 10, 5, 2, 1, 0, 0, 0] for k in range(NSOL)]
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
    if frames == 70:                                 # the generals and defence pages draw, and picking orders on the map works
        g.conquered.update(generals.SYSTEM_OF)
        generals.ensure(g)
        app.view, app.tab = "galaxy", T_GALAXY
        for page in (1, 2, 0):
            app.gal_page = page
            for _ in range(2):
                app.update(0.016)
                app.draw(app_scr(), app_fonts())
        st0 = g.cmd[0]
        far = next(k for k in sorted(range(1, NSEC), key=lambda q: -SECTORS[q]["d"]) if k not in g.conquered)
        for field, mode in (("goal", "toward"), ("heading", "heading"), ("region", "region")):
            app.begin_pick(0, field)
            assert app.pick and app.apply_pick(far) and app.pick is None and st0["mode"] == mode, field
        near = g.targets()[0]
        app.begin_pick(0, "goal")
        app.fv.focus(near, snap=True)
        app.draw(app_scr(), app_fonts())
        app.fv.click(app.fv.pos(near))               # a click on the map while picking is used up by the pick
        assert app.pick is None and st0["mode"] == "toward" and st0["goal"] == near
        app.gal_page = 1
        app.draw(app_scr(), app_fonts())
        app.gal_page = 0
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
    if frames == 78:
        check_worlds_ui(app)
        check_colonies_ui(app)
    if frames == 81:
        check_attack_ui(app)
        check_sysview_ui(app)
        check_hole_ui(app)
        check_fast_mode(app)
        check_quality(app)
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
