#!/usr/bin/env python3
"""Space Miner - an idle game.  Run:  python3 space_miner.py   (needs: pip install pygame)

Start on Earth and mine the asteroids that orbit it. Every planet has its own ore, fleet and colony.
Unlock the next world with the ores of the ones behind you, travel between them, build megaprojects,
research tech, survive random events, then WARP for permanent Dark Matter.
Autosaves to ~/.space_miner_save.json; your empire keeps working while you're away.
"""
import math
import os
import random
import sys
import time

import pygame

import core
import devtools
import director
import gfx
import sounds
from core import (BMAX, BUILDINGS, NB, NSH, NSITE, PERKS, PROJECTS, SC, SHIPS, SITES, TECHS, TECH_BY_ID,
                  UPGRADES, ACHIEVEMENTS, ACH_BY_ID, ACH_CATS, TIER_BONUS, TIER_NAMES, QUEST_TXT, fmt, geo_cost,
                  SECTORS, NSEC, SECTOR_EDGES, SECTOR_LINKS, FACTIONS, ARMORY, armory_cost, win_chance,
                  STARDUST_PERKS, sd_bonus)
from gfx import glow, scale_c, lerp_c

W, H = 1280, 720
PANEL = pygame.Rect(660, 104, 600, 608)
CX, CY = 325, 392                    # centre of the planet view
PLANET_R = 58
ADD = pygame.BLEND_RGB_ADD
STRIP_Y = H - 30
STRIP_X0, STRIP_DX = 96, 46
BASE_TABS = ["Ships", "Upgrades", "Colony", "Planets", "Galaxy", "Tech", "Quests", "Warp", "Awards"]
T_SHIPS, T_UPG, T_COLONY, T_PLANETS, T_GALAXY, T_TECH, T_QUESTS, T_WARP, T_AWARDS, T_DEV = range(10)
MAP = pygame.Rect(36, 232, 590, 384)          # where the galaxy map is drawn


def sec_pos(k):
    px, py = SECTORS[k]["pos"]
    return MAP.x + px * MAP.w, MAP.y + py * MAP.h
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
        self.raiders = []
        self.hover_sector = None
        self.warp_view = "warp"
        self.ascend_fx = 0.0
        self.ascend_confirm = 0.0
        self.ascend_cycle = 1
        self.ach_new = False
        self.awards_cat = "All"
        self.fps = 0.0
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
        self.ship_sprites = [gfx.make_ship(i, SHIPS[i][3], 26 + i * 2) for i in range(NSH)]
        self.ship_icons = [gfx.make_ship(i, SHIPS[i][3], 46) for i in range(NSH)]
        self.ship_rot = {}
        self.ast_sprites = {}
        self.crate_spr = gfx.make_crate()
        self.enemy_small = {f: gfx.make_enemy(f, 24) for f in FACTIONS}
        self.enemy_big = {f: gfx.make_enemy(f, 40) for f in FACTIONS}
        self.galaxy_bg = pygame.Surface((660, H))
        self.galaxy_bg.fill((0, 0, 0))
        for arm in range(2):
            for i in range(90):
                t = i / 90
                ang = arm * math.pi + t * 4.4
                rad = 24 + t * 340
                x, y = 380 + math.cos(ang) * rad, 380 + math.sin(ang) * rad * 0.55
                r = 16 + int(t * 22)
                self.galaxy_bg.blit(glow(r, (16, 20, 46)), (x - r, y - r), special_flags=ADD)
        self.galaxy_bg.blit(glow(170, (70, 52, 34)), (380 - 170, 380 - 170), special_flags=ADD)
        self.bg = gfx.make_background(W, H)
        self.vig = gfx.make_vignette(W, H)
        self.panel_bg = gfx.make_panel_bg(PANEL.w + 24, H - 8)
        self.modal_bg = gfx.make_panel_bg(560, 290)
        rng = random.Random(5)
        self.stars = [[rng.uniform(0, W), rng.uniform(0, H), rng.choice([0.4, 0.7, 1.0, 1.6]),
                       rng.uniform(0, math.tau), rng.choice([(150, 170, 255), (255, 235, 200), (200, 220, 255)])]
                      for _ in range(190)]
        self.streaks = [(rng.uniform(0, math.tau), rng.uniform(0.5, 1.4)) for _ in range(110)]

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
        for ring, (r, n, spd) in enumerate([(176, 5, 0.11), (218, 6, -0.085), (258, 7, 0.065)]):
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

    def mouse_down(self, pos):
        g = self.g
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
        if pos[0] >= PANEL.x - 10:
            for rect, fn in reversed(self.buttons):
                if rect.collidepoint(pos):
                    fn()
                    return
            return
        for rect, k in self.strip_hits:
            if rect.collidepoint(pos):
                self.strip_click(k)
                return
        if self.view == "galaxy":
            for k in range(1, NSEC):
                x, y = sec_pos(k)
                if math.hypot(pos[0] - x, pos[1] - y) < 20 and self.sector_known(k):
                    self.sel_sector = k
                    self.tab = T_GALAXY
                    return
            return
        best, bd = None, 1e9
        for a in self.asts:
            if a["hp"] <= 0:
                continue
            x, y, _ = self.ast_pos(a)
            d = math.hypot(pos[0] - x, pos[1] - y)
            if d < bd:
                best, bd = a, d
        if best is not None and bd < 38:
            x, y, _ = self.ast_pos(best)
            self.mine_at((x, y) if bd > 14 else pos, best)

    def sector_known(self, k):
        g = self.g
        return k in g.conquered or k in g.frontier()

    def strip_click(self, k):
        g = self.g
        if k < 0:                                   # galaxy map button
            if not g.galaxy_open:
                g.toast("Unlock Mars to open the galaxy map.", 3)
                return
            self.view = "system" if self.view == "galaxy" else "galaxy"
            if self.view == "galaxy":
                fr = g.frontier()
                if self.sel_sector in g.conquered and fr:
                    self.sel_sector = min(fr)
                self.tab = T_GALAXY
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
        self.dt = dt
        self.t += dt
        g.step(dt)
        if self.view_site != g.cur:
            self.rebuild_view()
        self.pulse = max(0, self.pulse - dt * 4)
        self.shake = max(0, self.shake - dt * 3)
        self.warp_fx = max(0, self.warp_fx - dt)
        self.ascend_fx = max(0, self.ascend_fx - dt)
        self.ascend_confirm = max(0, self.ascend_confirm - dt)
        self.warp_confirm = max(0, self.warp_confirm - dt)
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
                x, y = sec_pos(data)
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
            elif kind == "sector_lost":
                sec = SECTORS[data]
                self.add_banner(dict(header="SECTOR LOST", title=sec["name"], sub="Liberate it again to get its bonus back.",
                                     right="", sound="lose", col=(255, 90, 90), glyph="x", dur=6.0))
                x, y = sec_pos(data)
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
            self.shooting.append([random.uniform(0, 560), random.uniform(0, 250), 0.0])
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
        scr.blit(self.bg, (0, 0))
        self.draw_stars(scr)
        site = SITES[g.cur]
        if self.view == "system":
            scr.blit(glow(280, scale_c(site["col"], 0.22)), (CX - 280, CY - 280), special_flags=ADD)
        if g.buff_mult > 1.5 and self.view == "system":
            k = 0.6 + 0.4 * math.sin(self.t * 6)
            scr.blit(glow(260, scale_c((140, 100, 20), k)), (CX - 260, CY - 260), special_flags=ADD)
        if self.view == "galaxy":
            self.draw_galaxy_view(scr, fonts)
        else:
            self.draw_scene(scr)
            self.draw_raiders(scr)
            self.draw_crate(scr)
        self.draw_fx(scr, fonts[1])
        scr.blit(self.vig, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        self.draw_hud(scr, fonts)
        if self.dev:
            self.draw_dev_badge(scr, fonts)
        self.draw_strip(scr, fonts)
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
            n = min(g.owned[p][i], 4)
            rad = 82 + i * 7
            spd = 0.65 - i * 0.04
            d = 1 if i % 2 == 0 else -1
            for j in range(n):
                ang = self.t * spd * d + j * math.tau / n + i
                x = CX + math.cos(ang) * rad
                y = CY + math.sin(ang) * rad * 0.7
                (behind if math.sin(ang) < 0 else front).append(("s", (i, j, ang, d), x, y))
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
        for item in behind + front:
            if item[0] == "s":
                i, j, ang, d = item[1]
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
                        col = SHIPS[i][3]
                        pygame.draw.line(scr, scale_c(col, 0.45), (item[2], item[3]), (tx, ty), 4)
                        pygame.draw.line(scr, lerp_c(col, (255, 255, 255), 0.7), (item[2], item[3]), (tx, ty), 1)
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
        i, j, ang, d = data
        col = SHIPS[i][3]
        ta = ang + d * math.pi / 2
        for tc in (1, 2, 3):
            bx = x - math.cos(ta) * tc * 7
            by = y - math.sin(ta) * tc * 7
            scr.blit(glow(7 - tc, scale_c(col, 0.55 / tc)), (bx - (7 - tc), by - (7 - tc)), special_flags=ADD)
        q = int(round(-math.degrees(ta) / 10)) % 36
        key = (i, q)
        spr = self.ship_rot.get(key)
        if spr is None:
            spr = self.ship_rot[key] = pygame.transform.rotate(self.ship_sprites[i], q * 10)
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
        fx = pygame.Surface((660, H), pygame.SRCALPHA)
        fx.fill((190, 210, 255, int(k * 70)))
        scr.blit(fx, (0, 0))
        self.txt(scr, fonts[0], f"Travelling to {to['name']}", (CX, 262), (255, 255, 255), "midtop", True)
        pygame.draw.rect(scr, (30, 36, 70), (CX - 130, 306, 260, 6), border_radius=3)
        pygame.draw.rect(scr, to["col"], (CX - 130, 306, 260 * prog, 6), border_radius=3)
        scr.set_clip(None)

    def draw_toasts(self, scr, sm):
        y = H - 62
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

    def draw_hud(self, scr, fonts):
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
        if g.campaign:
            c = g.campaign
            self.txt(scr, tiny, f"Campaign: {SECTORS[c['k']]['name']}  {c['chance'] * 100:.0f}%  "
                     f"({fmt_time(max(0, c['dur'] - c['t']))} left)", (22, y + 2), (255, 175, 150), shadow=True)
            pygame.draw.rect(scr, (40, 24, 28), (22, y + 20, 150, 6), border_radius=3)
            pygame.draw.rect(scr, (255, 120, 100), (22, y + 20, 150 * c["t"] / c["dur"], 6), border_radius=3)
            y += 34
        if director.intel(g) >= 1:
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
            self.txt(scr, sm, f"{b['name']} x{b['mult']:g}  {b['t']:.0f}s", (640, yb), (255, 222, 90), "topright", True)
            frac = b["t"] / b["dur"]
            pygame.draw.rect(scr, (40, 34, 12), (490, yb + 21, 150, 5), border_radius=2)
            pygame.draw.rect(scr, (255, 200, 60), (640 - 150 * frac, yb + 21, 150 * frac, 5), border_radius=2)
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
        if opened and g.campaign is None and any(g.can_attack(k) and win_chance(g.fleet_power(), g.sector_power(k)) >= 0.8
                                                  for k in g.frontier()):
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
                lines.append((f"Fleet power {fmt(g.fleet_power())}   {len(g.conquered) - 1}/{NSEC - 1} sectors", (225, 225, 240)))
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
                self.txt(scr, tiny, t, (tx, rect.y + 48 + i * 15), c)
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
            fp = g.fleet_power()
            return g.galaxy_open and g.campaign is None and any(
                win_chance(fp, g.sector_power(c)) >= 0.8 for c in g.frontier())
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
                    dark = self.ship_icons[i].copy()
                    dark.fill((22, 26, 40, 255), special_flags=pygame.BLEND_RGBA_MULT)
                    scr.blit(dark, dark.get_rect(center=(r.x + 36, r.centery)))
                    self.txt(scr, med, "???", (r.x + 66, r.y + 18), (90, 95, 120))
                continue
            n = g.ship_count(p, i)
            cost = g.ship_cost(p, i, n)
            ok = g.ore[p] >= cost
            per = rate * SC[p] * g.s_gm[p][i] * g.G
            self.row(scr, fonts, r, name, f"{fmt(per, 2)} {SITES[p]['ore']}/s each", None, None, ok, col,
                     lambda i=i: g.buy_ship(p, i), icon=self.ship_icons[i])
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
            kw = dict(icon=self.ship_icons[u["arg"][0]]) if u["kind"] == "gen" else dict(glyph=glyphs[u["kind"]])
            self.row(scr, fonts, r, u["name"], u["desc"], fmt(cost), None, ok, (200, 160, 255),
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

    def draw_galaxy_view(self, scr, fonts):
        big, med, sm, tiny = fonts
        g = self.g
        scr.blit(self.galaxy_bg, (0, 0), special_flags=ADD)
        self.txt(scr, med, "GALAXY MAP", (MAP.right, 104), (190, 200, 235), "topright", True)
        self.txt(scr, tiny, "Liberate sectors to claim their bonuses", (MAP.right, 126), (140, 150, 185), "topright")
        conq = g.conquered
        front = set(g.frontier())
        fp = g.fleet_power()
        for a, b in SECTOR_EDGES:
            pa, pb = sec_pos(a), sec_pos(b)
            if a in conq and b in conq:
                pygame.draw.line(scr, (40, 80, 130), pa, pb, 6)
                pygame.draw.line(scr, (140, 200, 255), pa, pb, 2)
            elif a in conq or b in conq:
                other = b if a in conq else a
                if other in front:
                    self.dashed(scr, scale_c(self.sector_color(other), 0.85), pa, pb, 2, offset=self.t * 22)
            elif a in front or b in front:
                pygame.draw.line(scr, (38, 44, 78), pa, pb, 1)
        camp = g.campaign
        mouse = self.mouse
        hover = None
        for k in range(NSEC):
            x, y = sec_pos(k)
            if k in conq:
                col = self.sector_color(k)
                scr.blit(glow(34 if k else 46, scale_c((130, 190, 255) if k else (255, 190, 90), 0.55)),
                         (x - (34 if k else 46), y - (34 if k else 46)), special_flags=ADD)
                pygame.draw.circle(scr, (20, 36, 72), (x, y), 14 if k else 19)
                pygame.draw.circle(scr, (140, 205, 255) if k else (255, 215, 120), (x, y), 14 if k else 19, 2)
                if k:
                    pygame.draw.circle(scr, col, (x, y), 5)
                else:
                    pygame.draw.circle(scr, (255, 230, 160), (x, y), 9)
                self.txt(scr, tiny, SECTORS[k]["name"], (x, y + (19 if k else 24)), (190, 215, 245), "midtop", True)
            elif k in front:
                fac = SECTORS[k]["faction"]
                col = FACTIONS[fac]["col"]
                pulse = 0.55 + 0.45 * math.sin(self.t * 3 + k)
                scr.blit(glow(36, scale_c(col, 0.4 * pulse + 0.2)), (x - 36, y - 36), special_flags=ADD)
                pygame.draw.circle(scr, scale_c(col, 0.22), (x, y), 14)
                pygame.draw.circle(scr, col, (x, y), 14, 2)
                spr = self.enemy_small[fac]
                for j in range(3):
                    a = self.t * 0.9 + j * math.tau / 3 + k
                    ex, ey = x + math.cos(a) * 25, y + math.sin(a) * 18
                    ang = -math.degrees(a + math.pi / 2)
                    img = pygame.transform.rotate(spr, ang)
                    scr.blit(img, img.get_rect(center=(ex, ey)))
                ch = win_chance(fp, g.sector_power(k))
                self.txt(scr, tiny, SECTORS[k]["name"], (x, y + 31), (235, 225, 225), "midtop", True)
                self.txt(scr, tiny, f"{ch * 100:.0f}%", (x, y + 45), self.chance_color(ch), "midtop", True)
            else:
                pygame.draw.circle(scr, (52, 58, 96), (x, y), 4)
            if k and self.sector_known(k):
                if self.sel_sector == k:
                    for q in range(12):
                        a0 = self.t * 1.5 + q * math.tau / 12
                        pygame.draw.arc(scr, (255, 255, 255), (x - 23, y - 23, 46, 46), a0, a0 + 0.3, 2)
                if math.hypot(mouse[0] - x, mouse[1] - y) < 20 and mouse[0] < PANEL.x - 10:
                    hover = k
        if director.intel(g) >= 1:                 # enemy fleets on their way
            for inc in g.incoming:
                sx, sy = sec_pos(inc["src"])
                tx, ty = sec_pos(inc["target"]) if inc["kind"] == "offensive" else sec_pos(0)
                f = max(0.0, min(1.0, inc["t"] / max(0.1, inc["eta"])))
                self.dashed(scr, (255, 90, 80), (sx, sy), (tx, ty), 2, offset=-self.t * 30)
                mx, my = sx + (tx - sx) * f, sy + (ty - sy) * f
                scr.blit(glow(18, (150, 40, 30)), (mx - 18, my - 18), special_flags=ADD)
                fac = inc["fac"] if director.intel(g) >= 2 else "pirates"
                ang = -math.degrees(math.atan2(ty - sy, tx - sx))
                img = pygame.transform.rotate(self.enemy_small[fac], ang)
                scr.blit(img, img.get_rect(center=(mx, my)))
                label = fmt_time(max(0, inc["eta"] - inc["t"])) if director.intel(g) < 2 else (
                    f"{fmt_time(max(0, inc['eta'] - inc['t']))}")
                self.txt(scr, tiny, label, (mx, my + 14), (255, 150, 140), "midtop", True)
        if camp:                                   # your fleet travelling to the target
            k = camp["k"]
            tx, ty = sec_pos(k)
            srcs = [n for n in SECTOR_LINKS[k] if n in conq]
            sx, sy = min((sec_pos(n) for n in srcs), key=lambda q: math.hypot(q[0] - tx, q[1] - ty)) if srcs else (tx, ty)
            f = max(0.0, min(1.0, camp["t"] / camp["dur"]))
            fx_, fy_ = sx + (tx - sx) * f, sy + (ty - sy) * f
            col = FACTIONS[SECTORS[k]["faction"]]["col"]
            r = 20 + 6 * math.sin(self.t * 6)
            pygame.draw.circle(scr, scale_c(col, 0.9), (tx, ty), int(r), 2)
            ang = math.atan2(ty - sy, tx - sx)
            for tc in range(1, 5):
                scr.blit(glow(10 - tc, scale_c((130, 200, 255), 0.6 / tc)),
                         (fx_ - math.cos(ang) * tc * 9 - (10 - tc), fy_ - math.sin(ang) * tc * 9 - (10 - tc)), special_flags=ADD)
            spr = pygame.transform.rotate(self.ship_sprites[5], -math.degrees(ang))
            scr.blit(spr, spr.get_rect(center=(fx_, fy_)))
        self.hover_sector = hover
        if hover is not None:
            self.draw_sector_tooltip(scr, fonts, hover, fp)

    def draw_sector_tooltip(self, scr, fonts, k, fp):
        big, med, sm, tiny = fonts
        g = self.g
        sec = SECTORS[k]
        lines = []
        if k in g.conquered:
            lines.append((f"{sec['name']}  (liberated)", (140, 205, 255)))
            lines.append((sec["desc"], (130, 255, 150)))
        else:
            fac = FACTIONS[sec["faction"]]
            ep = g.sector_power(k)
            ch = win_chance(fp, ep)
            lines.append((f"{sec['name']}  -  {fac['name']}", fac["col"]))
            lines.append((f"Enemy power {fmt(ep)}   yours {fmt(fp)}", (225, 225, 240)))
            lines.append((f"Win chance {ch * 100:.0f}%", self.chance_color(ch)))
            lines.append((f"Reward: {sec['desc']}", (170, 175, 205)))
        w = max(sm.size(t)[0] for t, _ in lines) + 24
        h = len(lines) * 20 + 14
        x, y = sec_pos(k)
        r = pygame.Rect(0, 0, w, h)
        r.midbottom = (x, y - 28)
        r.clamp_ip(pygame.Rect(6, 6, PANEL.x - 24, H - 12))
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (14, 16, 36, 240), bg.get_rect(), border_radius=8)
        pygame.draw.rect(bg, (110, 130, 195, 255), bg.get_rect(), 1, border_radius=8)
        scr.blit(bg, r)
        for i, (t, col) in enumerate(lines):
            self.txt(scr, sm, t, (r.x + 12, r.y + 8 + i * 20), col)

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

    def draw_galaxy_tab(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        if not g.galaxy_open:
            self.txt(scr, big, "The galaxy awaits", (PANEL.x + 8, y))
            for i, line in enumerate(["Unlock Mars to open the galaxy map. Beyond the solar system lie",
                                      "15 sectors held by hostile factions. Liberate them with your fleet",
                                      "to claim permanent bonuses - but watch out for enemy raids."]):
                self.txt(scr, sm, line, (PANEL.x + 8, y + 46 + i * 22), (170, 176, 205))
            return y + 140
        fp = g.fleet_power()
        self.txt(scr, med, f"Fleet power  {fmt(fp)}", (PANEL.x + 4, y), (255, 215, 140))
        self.txt(scr, sm, f"{len(g.conquered) - 1}/{NSEC - 1} sectors liberated", (PANEL.right - 4, y + 2), (130, 255, 150), "topright")
        y += 26
        self.txt(scr, tiny, f"Battles {g.battles_won} won / {g.battles_lost} lost   -   Raids {g.raids_repelled} repelled / "
                 f"{g.raids_lost} lost   -   Press G to toggle the map", (PANEL.x + 4, y), (150, 158, 190))
        y += 20
        r = pygame.Rect(PANEL.x, y, PANEL.w, 32)
        self.button(scr, r, "Back to the solar system" if self.view == "galaxy" else "Open the galaxy map", sm,
                    lambda: self.strip_click(-1), panel=True, col=(60, 84, 150))
        y += 42
        if g.campaign:
            c = g.campaign
            sec = SECTORS[c["k"]]
            fr = c["t"] / c["dur"]
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 66)
            self.row(scr, fonts, rr, f"Campaign: {sec['name']}", f"{fmt_time(max(0, c['dur'] - c['t']))} left   -   "
                     f"{c['chance'] * 100:.0f}% to win   -   committed power {fmt(c['fp'])}", None, None, True,
                     FACTIONS[sec["faction"]]["col"], None, frac=fr, icon=self.enemy_big[sec["faction"]])
            y += 74
        # ---- Threat Director
        lvl = director.level(g)
        agg = director.aggression(g)
        tcol = [(120, 220, 140), (190, 230, 120), (255, 215, 100), (255, 150, 90), (255, 90, 90)][lvl]
        tlines = []
        if g.grace > 0:
            tlines.append((f"Enemy fleets are regrouping - quiet for {fmt_time(g.grace)}", (170, 176, 205)))
        elif not g.frontier():
            tlines.append(("No enemy territory borders yours.", (170, 176, 205)))
        else:
            tlines.append(("Raids and counter-offensives come more often when your fleet or planets look weak.", (170, 176, 205)))
        rr = pygame.Rect(PANEL.x, y, PANEL.w, 84)
        self.row(scr, fonts, rr, f"Threat level: {director.LEVELS[lvl]}", "Enemy aggression", None, None, True, tcol, None,
                 frac=agg, glyph="!", lines=tlines)
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
        # ---- faction hostility
        facs = [f for f in FACTIONS if any(SECTORS[k]["faction"] == f and k not in g.conquered for k in range(1, NSEC))]
        if facs:
            hl = [(f"{FACTIONS[f]['name']}:  attack power x{director.hostility_mult(g, f):.2f}   "
                   f"(hostility {g.hostility.get(f, 0.0):.1f})", FACTIONS[f]["col"]) for f in facs]
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 50 + 15 * len(hl))
            self.row(scr, fonts, rr, "Faction hostility", "Every campaign against a faction makes its attacks stronger for a while.",
                     None, None, True, (255, 150, 110), None, glyph="H", lines=hl)
            y += rr.h + 8
        if g.director_log:
            ll = [(f"{fmt_time(max(0, g.play_time - t))} ago  -  {text}"[:78], (190, 196, 220)) for t, text in reversed(g.director_log[-5:])]
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 50 + 15 * len(ll))
            self.row(scr, fonts, rr, "Recent enemy activity", "", None, None, True, (150, 160, 200), None, glyph="L", lines=ll)
            y += rr.h + 8
        fr_list = g.frontier()
        sel = self.sel_sector
        if sel not in fr_list and sel not in g.conquered:
            sel = min(fr_list) if fr_list else 1
        k = sel
        sec = SECTORS[k]
        fac = FACTIONS[sec["faction"]]
        ep = g.sector_power(k)
        ch = win_chance(fp, ep)
        good, bad = (130, 255, 150), (230, 130, 130)
        rr = pygame.Rect(PANEL.x, y, PANEL.w, 126)
        y += 134
        if k in g.conquered:
            self.row(scr, fonts, rr, f"{sec['name']}  -  {fac['name']}", f"Reward: {sec['desc']}", "LIBERATED", None, True,
                     fac["col"], None, icon=self.enemy_big[sec["faction"]],
                     lines=[("This sector is yours.", (140, 205, 255))])
        elif k not in fr_list:
            self.row(scr, fonts, rr, "Unscouted sector", "Liberate a neighbouring sector first.", None, None, False,
                     (62, 66, 92), None, dim=True, icon=self.enemy_big[sec["faction"]])
        else:
            can = g.can_attack(k) and fp > 0
            lines = [(f"Enemy power {fmt(ep)}    your fleet {fmt(fp)}", (205, 210, 230)),
                     (f"Win chance {ch * 100:.0f}%    campaign time {fmt_time(g.campaign_duration(k))}", self.chance_color(ch)),
                     (f"Losses: victory {g.loss_fraction(core.WIN_LOSSES) * 100:.1f}% of ships, defeat "
                      f"{g.loss_fraction(core.LOSE_LOSSES) * 100:.1f}%", (170, 176, 205))]
            label = "ATTACK" if g.campaign is None else "BUSY"
            self.row(scr, fonts, rr, f"{sec['name']}  -  {fac['name']}", f"Reward: {sec['desc']}", label, None,
                     can, fac["col"], (lambda k=k: g.start_campaign(k)) if can else None,
                     icon=self.enemy_big[sec["faction"]], lines=lines)
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
        self.txt(scr, med, "Sectors", (PANEL.x + 4, y), (255, 225, 140))
        y += 28
        for k in range(1, NSEC):
            rr = pygame.Rect(PANEL.x, y, PANEL.w, 52)
            y += 58
            sec = SECTORS[k]
            fac = FACTIONS[sec["faction"]]
            if k in g.conquered:
                self.row(scr, fonts, rr, sec["name"], sec["desc"], "LIBERATED", None, True, (120, 190, 255),
                         (lambda k=k: setattr(self, "sel_sector", k)), icon=self.enemy_small[sec["faction"]])
            elif k in fr_list:
                c2 = win_chance(fp, g.sector_power(k))
                self.row(scr, fonts, rr, sec["name"], f"{fac['name']}  -  reward: {sec['desc']}", f"{c2 * 100:.0f}%", None,
                         True, fac["col"], (lambda k=k: setattr(self, "sel_sector", k)), icon=self.enemy_small[sec["faction"]])
            else:
                self.row(scr, fonts, rr, "???", "Not scouted yet", None, None, False, (62, 66, 92), None, dim=True)
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
        boss = SECTORS[NSEC - 1]
        done = NSEC - 1 in g.conquered
        rr = pygame.Rect(PANEL.x, y, PANEL.w, 62)
        self.row(scr, fonts, rr, "The Devourer  -  The Void Throne",
                 "Defeated! You may Ascend whenever you like." if done else "Liberate sectors until the Void Throne is yours.",
                 "DEFEATED" if done else f"{len(g.conquered) - 1}/{NSEC - 1} sectors", None, done, FACTIONS["devourer"]["col"],
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
            ("Sectors liberated", f"{len(g.conquered) - 1}/{NSEC - 1}"),
            ("Battles won / lost", f"{g.battles_won:,} / {g.battles_lost:,}"),
            ("Raids repelled / lost", f"{g.raids_repelled:,} / {g.raids_lost:,}"),
            ("Big raids repelled (regional / system)", f"{g.tier_wins[1]:,} / {g.tier_wins[2]:,}"),
            ("Counter-offensives held", f"{g.offensives_repelled:,}"),
            ("Sectors lost / retaken", f"{g.sectors_lost:,} / {g.sectors_retaken:,}"),
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
        self.button(scr, pygame.Rect(PANEL.x, y, 200, 40), "Save now", sm,
                    lambda: (g.save(), g.toast("Game saved.", 2)), panel=True)
        self.button(scr, pygame.Rect(PANEL.x + 220, y, 280, 40),
                    "CLICK AGAIN: WIPE SAVE" if self.reset_confirm > 0 else "Hard reset (wipe save)", sm,
                    self.hard_reset, panel=True, col=(150, 60, 70) if self.reset_confirm > 0 else (70, 40, 50))
        return y + 60

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
                    self.button(scr, r, label, f, fn, panel=True, col=(150, 70, 70) if active else (52, 64, 108))
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
        x = 225
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
        box.center = (CX, 330)
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

usage: python3 space_miner.py [--dev] [--selftest]

  --dev        developer mode: adds a Dev tab with cheats (F1 jumps to it). Terminal only.
  --selftest   run headless for a few seconds and exercise the game (used for testing)
"""


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(USAGE)
        return
    selftest = "--selftest" in sys.argv
    dev = "--dev" in sys.argv
    if selftest:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("Space Miner")
    scr = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()

    def font(size, bold=False):
        return pygame.font.SysFont("dejavusans,liberationsans,arial,freesans", size, bold=bold)

    fonts = (font(30, True), font(18, True), font(15), font(12))
    t0 = time.time()
    app = App(dev=dev)
    g = app.g
    if dev:
        print("Developer mode ON (cheats are in the Dev tab; F1 jumps to it).")
    if selftest:
        print(f"startup {time.time() - t0:.2f}s")
    _SCR.update(scr=scr, fonts=fonts)
    here = os.path.dirname(os.path.abspath(__file__))
    running = True
    frames = 0

    def shot(n):
        pygame.image.save(scr, os.path.join(here, f"shot_{n}.png"))

    while running:
        dt = min(clock.tick(60) / 1000.0, 0.25)
        if selftest:
            dt = 0.05
        app.fps = clock.get_fps()
        if dev and not selftest:
            dt = min(dt * app.dev_state.speed, 30.0)
        app.mouse = (480, 330) if selftest else pygame.mouse.get_pos()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_SPACE and not g.event:
                    app.space_click()
                elif pygame.K_1 <= e.key <= pygame.K_9 and e.key - pygame.K_1 < len(app.tabs):
                    app.set_tab(e.key - pygame.K_1)
                elif e.key == pygame.K_0 and len(app.tabs) >= 10:
                    app.set_tab(9)
                elif e.key == pygame.K_g:
                    app.strip_click(-1)
                elif e.key == pygame.K_F1 and dev:
                    app.set_tab(len(app.tabs) - 1 if app.tab != len(app.tabs) - 1 else 0)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                app.mouse_down(e.pos)
            elif e.type == pygame.MOUSEWHEEL and PANEL.collidepoint(app.mouse):
                app.scroll[app.tab] -= e.y * 50
        app.update(dt)
        app.draw(scr, fonts)
        pygame.display.flip()
        frames += 1
        if selftest:
            selftest_step(app, g, frames, shot)
            if frames >= (100 if dev else 95):
                running = False
    g.save()
    pygame.quit()


_SCR = {}


def app_scr():
    return _SCR["scr"]


def app_fonts():
    return _SCR["fonts"]


def selftest_step(app, g, frames, shot):
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
    if frames == 40:
        g.ore = [1e15 * SC[i] for i in range(NSITE)]
        g.run_ore = list(g.ore); g.all_norm = g.run_norm = 1e20
        g.credits = 1e15; g.science = 1e12
        for k in range(NSITE):
            g.unlocked[k] = True
            g.owned[k] = [12 + k, 11, 10, 9, 8, 7, 6, 5]
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
        g.owned = [[40 + k, 30, 20, 10, 5, 2, 1, 0] for k in range(NSITE)]
        g.conquered = {0, 1, 2}
        g.recalc()
        app.tab = T_GALAXY
        app.view = "galaxy"
        app.sel_sector = 3
        assert g.start_campaign(3), "campaign failed to start"
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
    if frames == 68:
        app.view = "system"
        g.raid(g.cur, force=True)
    if frames == 72:
        shot("raid")
    if frames == 74:
        g.campaign["t"] = g.campaign["dur"]
        for inc in list(g.incoming):
            inc["t"] = inc["eta"] - 0.1
    if frames == 76 and app.dev:
        app.tab = T_DEV
        app.draw(app_scr(), app_fonts())
        shot("dev")
        for title, items in devtools.sections(app):
            for label, fn, active in items:
                if "Wipe" in label or "Lock ALL" in label or "Relock" in label or "Reset galaxy" in label:
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
