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
import gfx
from core import (BMAX, BUILDINGS, NB, NSH, NSITE, PERKS, PROJECTS, SC, SHIPS, SITES, TECHS, TECH_BY_ID,
                  UPGRADES, ACHIEVEMENTS, ACH_BONUS, QUEST_TXT, fmt, geo_cost)
from gfx import glow, scale_c, lerp_c

W, H = 1280, 720
PANEL = pygame.Rect(660, 104, 600, 608)
CX, CY = 325, 392                    # centre of the planet view
PLANET_R = 58
ADD = pygame.BLEND_RGB_ADD
STRIP_Y = H - 30
TABS = ["Ships", "Upgrades", "Colony", "Planets", "Tech", "Quests", "Warp", "Trophies"]


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
    def __init__(self):
        self.g = core.Game()
        self.t = 0.0
        self.dt = 0.016
        self.mouse = (0, 0)
        self.tab = 0
        self.scroll = [0] * len(TABS)
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

    def strip_click(self, k):
        g = self.g
        if g.unlocked[k]:
            if k != g.cur:
                g.start_travel(k)
            else:
                self.tab = 3
        else:
            self.tab = 3

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

    def hard_reset(self):
        if self.reset_confirm <= 0:
            self.reset_confirm = 4.0
            return
        self.reset_confirm = 0
        self.g.hard_reset()

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
        self.warp_confirm = max(0, self.warp_confirm - dt)
        self.reset_confirm = max(0, self.reset_confirm - dt)
        for kind, data in g.fx_events:
            if kind == "warp":
                self.warp_fx = 1.8
            elif kind == "unlock":
                self.rings.append([CX, CY, 0.0, SITES[data]["col"]])
                self.burst(CX, CY, SITES[data]["col"], 40)
            elif kind == "project":
                self.rings.append([CX, CY, 0.0, (255, 220, 120)])
                self.burst(CX, CY, (255, 220, 120), 50)
            elif kind == "crate":
                c = data
                self.burst(c["x"], c.get("yy", c["y"]), (255, 215, 80), 30)
                self.rings.append([c["x"], c.get("yy", c["y"]), 0.0, (255, 215, 80)])
            elif kind == "buy":
                self.burst(CX, CY, SHIPS[data[1]][3], 8)
        g.fx_events.clear()
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
        scr.blit(glow(280, scale_c(site["col"], 0.22)), (CX - 280, CY - 280), special_flags=ADD)
        if g.buff_mult > 1.5:
            k = 0.6 + 0.4 * math.sin(self.t * 6)
            scr.blit(glow(260, scale_c((140, 100, 20), k)), (CX - 260, CY - 260), special_flags=ADD)
        self.draw_scene(scr)
        self.draw_crate(scr)
        self.draw_fx(scr, fonts[1])
        scr.blit(self.vig, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        self.draw_hud(scr, fonts)
        self.draw_strip(scr, fonts)
        self.draw_panel(scr, fonts)
        self.draw_toasts(scr, fonts[2])
        if g.event:
            self.draw_event(scr, fonts)
        if g.travel:
            self.draw_travel(scr, fonts)
        if self.warp_fx > 0:
            self.draw_warp_fx(scr)

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
        for msg, secs in reversed(self.g.toasts):
            img = sm.render(msg, True, (255, 245, 210))
            r = img.get_rect(midbottom=(CX, y)).inflate(28, 12)
            r.width = min(r.width, 650)
            r.centerx = CX
            bg = pygame.Surface(r.size, pygame.SRCALPHA)
            a = int(min(1, secs) * 225)
            pygame.draw.rect(bg, (16, 18, 38, a), bg.get_rect(), border_radius=10)
            pygame.draw.rect(bg, (255, 215, 110, a), bg.get_rect(), 1, border_radius=10)
            scr.blit(bg, r)
            img.set_alpha(int(min(1, secs) * 255))
            scr.blit(img, img.get_rect(center=r.center), area=pygame.Rect(0, 0, r.w - 20, img.get_height()))
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
        self.txt(scr, med, f"{site['name'].upper()}", (22, 12), site["col"], shadow=True)
        self.txt(scr, tiny, f"mining {site['ore']}", (22 + med.size(site['name'].upper())[0] + 10, 18), (170, 175, 200), shadow=True)
        self.txt(scr, big, fmt(g.ore[p], 2), (20, 32), (255, 255, 255), shadow=True)
        self.txt(scr, med, f"{fmt(g.s_ops[p], 2)} {site['ore']}/s", (22, 74), lerp_c(oc, (255, 255, 255), 0.35), shadow=True)
        self.txt(scr, sm, f"Click: +{fmt(g.s_click[p])}", (22, 100), (205, 205, 220), shadow=True)
        extra = f"Bonus x{g.G:.2f}"
        if g.dm:
            extra += f"   Dark Matter: {g.dm_avail()}/{g.dm}"
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
        yb = 16
        for b in g.buffs:
            self.txt(scr, sm, f"{b['name']} x{b['mult']:g}  {b['t']:.0f}s", (640, yb), (255, 222, 90), "topright", True)
            frac = b["t"] / b["dur"]
            pygame.draw.rect(scr, (40, 34, 12), (490, yb + 21, 150, 5), border_radius=2)
            pygame.draw.rect(scr, (255, 200, 60), (640 - 150 * frac, yb + 21, 150 * frac, 5), border_radius=2)
            yb += 34

    def draw_strip(self, scr, fonts):
        big, med, sm, tiny = fonts
        g = self.g
        self.strip_hits = []
        n = NSITE
        x0 = CX - (n - 1) * 25
        pygame.draw.line(scr, (34, 40, 78), (x0, STRIP_Y), (x0 + (n - 1) * 50, STRIP_Y), 2)
        nxt = next((i for i in range(1, NSITE) if not g.unlocked[i]), None)
        hover = None
        for k in range(n):
            x = x0 + k * 50
            rect = pygame.Rect(x - 19, STRIP_Y - 19, 38, 38)
            self.strip_hits.append((rect, k))
            site = SITES[k]
            if g.unlocked[k]:
                if k == g.cur:
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
                    col = (255, 215, 110) if can else (90, 100, 150)
                    pygame.draw.circle(scr, col, (x, STRIP_Y), 20, 1)
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
        site = SITES[k]
        lines = []
        if g.unlocked[k]:
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
        x = max(8, min(CX - w // 2 + (k - 5.5) * 38, PANEL.x - 20 - w))
        r = pygame.Rect(x, STRIP_Y - 44 - h, w, h)
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (14, 16, 36, 235), bg.get_rect(), border_radius=8)
        pygame.draw.rect(bg, (110, 130, 195, 255), bg.get_rect(), 1, border_radius=8)
        scr.blit(bg, r)
        for i, (t, col) in enumerate(lines):
            self.txt(scr, sm, t, (r.x + 12, r.y + 8 + i * 20), col)

    # ---------------- panel -----------------
    def button(self, scr, rect, label, font, fn, enabled=True, col=(50, 70, 110), modal=False, dot=False,
               panel=False, selected=False):
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
        if k == 1:
            return any(g.ore[p] >= u["cost"] * SC[p] for u in g.avail_upgrades(p))
        if k == 2:
            return g.can_buy_project(p)
        if k == 3:
            return any(g.can_unlock(i) for i in range(1, NSITE))
        if k == 4:
            return any(t[0] not in g.techs and all(q in g.techs for q in t[3]) and g.science >= t[2] for t in TECHS)
        if k == 5:
            return any(g.quest_prog(q) >= q["tgt"] for q in g.quests)
        if k == 6:
            return g.warp_gain() >= 1 or any(pk[0] not in g.perks and g.dm_avail() >= pk[2] for pk in PERKS)
        return False

    def draw_panel(self, scr, fonts):
        big, med, sm, tiny = fonts
        g = self.g
        scr.blit(self.panel_bg, (PANEL.x - 12, 4))
        tw = PANEL.w // len(TABS)
        for k, n in enumerate(TABS):
            r = pygame.Rect(PANEL.x + k * tw, 14, tw - 4, 30)
            self.button(scr, r, n, tiny if sm.size(n)[0] > tw - 10 else sm, (lambda k=k: self.set_tab(k)),
                        col=(78, 100, 176) if self.tab == k else (34, 42, 74), dot=self.tab != k and self.tab_alert(k),
                        selected=self.tab == k)
        if self.tab in (0, 2):
            self.txt(scr, tiny, "Buy:", (PANEL.x + 2, 70), (170, 175, 200))
            for k, (lab, m) in enumerate([("x1", 1), ("x10", 10), ("x100", 100), ("Max", 0)]):
                r = pygame.Rect(PANEL.x + 40 + k * 62, 58, 56, 26)
                self.button(scr, r, lab, sm, (lambda m=m: setattr(g, "buy_mode", m)),
                            col=(66, 128, 92) if g.buy_mode == m else (34, 42, 74))
        site = SITES[g.cur]
        if self.tab in (0, 1, 2):
            self.txt(scr, tiny, f"{site['name']}  -  paid in {site['ore']}", (PANEL.right, 70), site["col"], "topright")
        pygame.draw.line(scr, (50, 58, 100), (PANEL.x, PANEL.y - 7), (PANEL.right, PANEL.y - 7))
        scr.set_clip(PANEL)
        sy = PANEL.y - self.scroll[self.tab]
        end = [self.draw_ships, self.draw_upgrades, self.draw_colony, self.draw_planets, self.draw_tech,
               self.draw_quests, self.draw_warp, self.draw_trophies][self.tab](scr, fonts, sy)
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
            ore, cr, sci = core.project_cost(p)
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
                 f"Science: {fmt(g.science)}  (+{fmt(g.sci_ops)}/s)", (PANEL.x + 4, y), (150, 160, 190))
        y += 20
        order = sorted(TECHS, key=lambda t: (t[0] in g.techs, not all(q in g.techs for q in t[3]), t[2]))
        for t in order:
            tid, name, cost, pre, desc, _ = t
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
        x = PANEL.x + 8
        self.txt(scr, big, "Warp Drive", (x, y))
        lines = ["Warp resets ore, ships and upgrades on EVERY planet. You keep your",
                 "unlocked planets, colonies, megaprojects, tech, credits, science",
                 "and Dark Matter. Dark Matter total = (lifetime ore / 1B) ^ 0.25.",
                 "Dark Matter gives a permanent production bonus (1 + 0.4 x sqrt(DM)) and can be",
                 "spent on perks below."]
        for k, l in enumerate(lines):
            self.txt(scr, tiny, l, (x, y + 42 + k * 17), (175, 180, 205))
        y += 134
        gain = g.warp_gain()
        self.txt(scr, med, f"Dark Matter: {g.dm_avail()} to spend ({g.dm} total, bonus x{core.dm_bonus(g.dm, g.E['dmbase']):.2f})",
                 (x, y), (210, 170, 255))
        self.txt(scr, med, f"Lifetime ore (Earth-equivalent): {fmt(g.all_norm)}", (x, y + 26))
        self.txt(scr, med, f"Warp now for: +{gain} DM", (x, y + 52), (130, 255, 150) if gain else (180, 120, 120))
        need = ((g.dm + gain + 1) / g.E["dm"]) ** (1 / core.DM_POW) * core.DM_DIV
        self.txt(scr, tiny, f"Next Dark Matter at lifetime ore {fmt(need)}   -   warps so far: {g.warps}", (x, y + 80), (150, 155, 180))
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

    def draw_trophies(self, scr, fonts, y):
        big, med, sm, tiny = fonts
        g = self.g
        self.txt(scr, med, f"{len(g.ach)}/{len(ACHIEVEMENTS)} trophies  (+{int(len(g.ach) * ACH_BONUS * 100)}% production)",
                 (PANEL.x + 4, y), (255, 225, 140))
        y += 36
        for name, desc, _ in ACHIEVEMENTS:
            got = name in g.ach
            r = pygame.Rect(PANEL.x, y, PANEL.w, 44)
            y += 50
            if not r.colliderect(PANEL):
                continue
            pygame.draw.rect(scr, (56, 48, 28) if got else (22, 24, 40), r, border_radius=8)
            if got:
                pygame.draw.rect(scr, (255, 215, 110), r, 1, border_radius=8)
                scr.blit(glow(20, (110, 84, 20)), (r.right - 40, r.centery - 20), special_flags=ADD)
                pygame.draw.circle(scr, (255, 215, 110), (r.right - 20, r.centery), 7)
            self.txt(scr, sm, name if got else "???", (r.x + 12, r.y + 4), (255, 230, 150) if got else (90, 95, 120))
            self.txt(scr, tiny, desc, (r.x + 12, r.y + 25), (170, 175, 200) if got else (80, 85, 110))
        y += 10
        b1 = pygame.Rect(PANEL.x, y, 200, 40)
        b2 = pygame.Rect(PANEL.x + 220, y, 280, 40)
        self.button(scr, b1, "Save now", sm, lambda: (g.save(), g.toast("Game saved.", 2)), panel=True)
        self.button(scr, b2, "CLICK AGAIN: WIPE SAVE" if self.reset_confirm > 0 else "Hard reset (wipe save)", sm,
                    self.hard_reset, panel=True, col=(150, 60, 70) if self.reset_confirm > 0 else (70, 40, 50))
        return y + 60

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


def main():
    selftest = "--selftest" in sys.argv
    if selftest:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("Space Miner")
    scr = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()

    def font(size, bold=False):
        return pygame.font.SysFont("dejavusans,liberationsans,arial,freesans", size, bold=bold)

    fonts = (font(30, True), font(18, True), font(15), font(12))
    t0 = time.time()
    app = App()
    g = app.g
    if selftest:
        print(f"startup {time.time() - t0:.2f}s")
    here = os.path.dirname(os.path.abspath(__file__))
    running = True
    frames = 0

    def shot(n):
        pygame.image.save(scr, os.path.join(here, f"shot_{n}.png"))

    while running:
        dt = min(clock.tick(60) / 1000.0, 0.25)
        if selftest:
            dt = 0.05
        app.mouse = (480, 330) if selftest else pygame.mouse.get_pos()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_SPACE and not g.event:
                    app.space_click()
                elif pygame.K_1 <= e.key <= pygame.K_8:
                    app.set_tab(e.key - pygame.K_1)
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
            if frames >= 80:
                running = False
    g.save()
    pygame.quit()


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
        app.tab = 0
    if frames == 44:
        shot("saturn_ships")
        app.tab = 3
    if frames == 46:
        shot("planets")
        app.tab = 2
    if frames == 48:
        shot("colony")
        app.tab = 4
    if frames == 50:
        shot("tech")
        app.tab = 1
    if frames == 52:
        shot("upgrades")
        app.tab = 6
        g.event = g.pick_event(); g.event["left"] = 60
    if frames == 54:
        shot("event")
        g.resolve_event(g.event["opts"][0][1])
        app.scroll[6] = 300
    if frames == 56:
        shot("warp")
        app.scroll[6] = 0
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
    if frames == 70:
        g.hard_reset()


if __name__ == "__main__":
    main()
