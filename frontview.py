"""The zoomable galaxy map: pan, zoom and take a close look at the frontlines.

Zoomed out it is the classic map (sectors, lanes, fog). Zoomed in (mouse wheel, + / -, or the FRONT button) the lanes
between your territory and the enemy turn into battle lines: both fleets drawn as ship swarms, lasers and flashes
at the clash point, the front line sitting nearer the weaker side, garrison shields, incoming attacks as moving
fleets, and a mini-map to find your way. The numbers behind it live in front.py.
"""
import math

import pygame

import director
import front
from core import FACTIONS, NSEC, SECTORS, SECTOR_EDGES, SECTOR_LINKS, fmt, win_chance
from gfx import glow, lerp_c, scale_c

ADD = pygame.BLEND_RGB_ADD
GC = (331, 462)                      # screen position of the galaxy centre at zoom 1
MAPW, MAPH = 590, 384                # size of the whole galaxy at zoom 1
VIEW = pygame.Rect(8, 256, 640, 412)  # the viewport (the left side of the window, below the HUD)
STAGE_W = 648
Z_MIN, Z_MAX = 1.0, 4.5
CLOSE = 1.35                         # from this zoom on, fleets and battle lines are drawn
DETAIL = 1.9                         # from this zoom on, sectors get their full labels
MINE = (120, 190, 255)
LASER_MINE = (150, 225, 255)


def set_layout(panel_x, w, h):
    """Re-fit the map to the window: its viewport is everything left of the side panel below the HUD. (At 1280x720 this
    gives the original VIEW, GC and map size.)"""
    global VIEW, GC, MAPW, MAPH, STAGE_W
    STAGE_W = panel_x - 12
    VIEW = pygame.Rect(8, 256, STAGE_W - 8, h - 256 - 52)
    MAPW, MAPH = VIEW.w * 0.9219, VIEW.h * 0.932
    GC = (VIEW.x + VIEW.w * 0.505, VIEW.centery)


def hrand(*a):
    """Deterministic pseudo-random number in 0..1 from some integers (so swarms do not jitter between frames)."""
    h = 0
    for i, v in enumerate(a):
        h = (h * 1000003 + int(v) * (2654435761 + i * 97)) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 2246822519) & 0xFFFFFFFF
    h ^= h >> 13
    return (h & 0xFFFF) / 65536.0                 # always below 1, so int(r * n) is a valid index


class FrontView:
    def __init__(self, app, tab_galaxy):
        self.app = app
        self.tab_galaxy = tab_galaxy        # index of the Galaxy tab in the side panel
        self.z = self.zt = 1.0
        self.x = self.xt = 0.5
        self.y = self.yt = 0.5
        self.drag = None
        self.hits = []                  # clickable rects of the toolbar and the mini-map: (rect, fn)
        self.marks = []                 # clash markers of this frame: (x, y, enemy sector)
        self.rot_cache = {}
        self.hover = None
        self.last_click = (-9.0, None)
        self.relayout()

    def relayout(self):
        self.minimap = pygame.Rect(VIEW.x + 8, VIEW.bottom - 86, 132, 78)
        self.clamp(snap=True)

    # ------------------------------------------------------------------ camera
    def pt(self, px, py):
        return GC[0] + (px - self.x) * MAPW * self.z, GC[1] + (py - self.y) * MAPH * self.z

    def pos(self, k):
        return self.pt(*SECTORS[k]["pos"])

    def limits(self):
        u = min(1.0, (self.zt - 1.0) / 0.6)
        return (0.5 - 0.42 * u, 0.5 + 0.47 * u), (0.5 - 0.34 * u, 0.5 + 0.38 * u)

    def clamp(self, snap=False):
        self.zt = max(Z_MIN, min(Z_MAX, self.zt))
        (x0, x1), (y0, y1) = self.limits()
        self.xt = max(x0, min(x1, self.xt))
        self.yt = max(y0, min(y1, self.yt))
        if snap:
            self.z, self.x, self.y = self.zt, self.xt, self.yt

    def update(self, dt):
        k = 1.0 - math.exp(-dt * 9.0)
        self.z += (self.zt - self.z) * k
        self.x += (self.xt - self.x) * k
        self.y += (self.yt - self.y) * k
        if abs(self.zt - self.z) < 0.002:
            self.z = self.zt

    def zoom_at(self, pos, factor):
        old = self.zt
        new = max(Z_MIN, min(Z_MAX, old * factor))
        self.xt += (pos[0] - GC[0]) / MAPW * (1 / old - 1 / new)
        self.yt += (pos[1] - GC[1]) / MAPH * (1 / old - 1 / new)
        self.zt = new
        self.clamp()
        if self.zt >= DETAIL:
            self.app.g.flags.add("closeup")

    def fit(self, snap=False):
        self.zt, self.xt, self.yt = 1.0, 0.5, 0.5
        self.clamp(snap)

    def focus(self, k, snap=False):
        """Zoom in on the front at sector k (an enemy sector you border, or one of yours)."""
        g = self.app.g
        px, py = SECTORS[k]["pos"]
        if k not in g.conquered:
            src = front.source_sector(g, k)
            if src is not None:
                sx, sy = SECTORS[src]["pos"]
                t = front.front_pos(g, k)
                cx, cy = sx + (px - sx) * t, sy + (py - sy) * t
                lane = math.hypot((px - sx) * MAPW, (py - sy) * MAPH)
                self.zt = max(2.2, min(3.4, 0.62 * VIEW.w / max(lane, 1.0)))
                self.xt, self.yt = cx, cy
            else:
                self.zt, self.xt, self.yt = 2.6, px, py
        else:
            self.zt, self.xt, self.yt = 2.6, px, py
        self.clamp(snap)
        g.flags.add("closeup")

    def focus_selected(self):
        g = self.app.g
        k = self.app.sel_sector
        if k not in g.conquered and k not in g.frontier():
            fr = g.frontier()
            k = min(fr) if fr else 0
        self.focus(k)

    def toggle(self):
        if self.zt > 1.3:
            self.fit()
        else:
            self.focus_selected()

    # ------------------------------------------------------------------ input
    def inside(self, pos):
        return VIEW.collidepoint(pos)

    def down(self, pos):
        if not self.inside(pos):
            return False
        self.drag = dict(start=pos, last=pos, moved=False)
        return True

    def move(self, pos):
        d = self.drag
        if not d:
            return
        if not d["moved"] and math.hypot(pos[0] - d["start"][0], pos[1] - d["start"][1]) > 5:
            d["moved"] = True
        if d["moved"] and self.zt > 1.0:
            self.xt -= (pos[0] - d["last"][0]) / (MAPW * self.z)
            self.yt -= (pos[1] - d["last"][1]) / (MAPH * self.z)
            self.clamp()
            self.x, self.y = self.xt, self.yt
        d["last"] = pos

    def up(self, pos):
        d, self.drag = self.drag, None
        if d and not d["moved"]:
            self.click(pos)

    def wheel(self, pos, dy):
        if self.inside(pos) and dy:
            self.zoom_at(pos, 1.2 ** dy)

    def key(self, key):
        """Keyboard shortcuts of the galaxy view; True if the key was used."""
        if key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.zoom_at(GC, 1.35)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.zoom_at(GC, 1 / 1.35)
        elif key == pygame.K_z:
            self.toggle()
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            dx = (key == pygame.K_RIGHT) - (key == pygame.K_LEFT)
            dy = (key == pygame.K_DOWN) - (key == pygame.K_UP)
            self.xt += dx * 80 / (MAPW * self.zt)
            self.yt += dy * 80 / (MAPH * self.zt)
            self.clamp()
        else:
            return False
        return True

    def sector_at(self, pos):
        best, bd = None, 1e9
        reach = 20 + 3 * min(self.z, 3)
        for k in range(1, NSEC):
            if not self.app.sector_known(k):
                continue
            x, y = self.pos(k)
            d = math.hypot(pos[0] - x, pos[1] - y)
            if d < reach and d < bd:
                best, bd = k, d
        return best

    def click(self, pos):
        app = self.app
        for rect, fn in self.hits:
            if rect.collidepoint(pos):
                fn()
                return
        k = self.sector_at(pos)
        if k is None:
            for x, y, enemy in self.marks:
                if math.hypot(pos[0] - x, pos[1] - y) < 16:
                    k = enemy
                    break
        if k is None:
            return
        again = self.last_click[1] == k and app.t - self.last_click[0] < 0.45
        self.last_click = (app.t, k)
        app.sel_sector = k
        app.tab = self.tab_galaxy
        if again:
            self.focus(k)

    # ------------------------------------------------------------------ drawing helpers
    def rot(self, spr, ang_deg, size=None):
        """The sprite turned to ang_deg and scaled to `size` pixels wide (cached)."""
        size = int(round(size if size else spr.get_width()))
        key = (id(spr), int(round(ang_deg / 6.0)) % 60, size)
        img = self.rot_cache.get(key)
        if img is None:
            if len(self.rot_cache) > 900:
                self.rot_cache.clear()
            img = pygame.transform.rotozoom(spr, key[1] * 6, size / spr.get_width())
            self.rot_cache[key] = img
        return img

    def spark(self, scr, x, y, r, col, k=1.0):
        r = max(4, int(r / 2) * 2)
        k = max(1, min(4, round(k * 4))) / 4.0
        scr.blit(glow(r, scale_c(col, 0.8 * k)), (x - r, y - r), special_flags=ADD)

    def visible(self, x, y, m=60):
        return VIEW.x - m < x < VIEW.right + m and VIEW.y - m < y < VIEW.bottom + m

    def lane_visible(self, pa, pb):
        r = pygame.Rect(min(pa[0], pb[0]), min(pa[1], pb[1]), abs(pa[0] - pb[0]) + 1, abs(pa[1] - pb[1]) + 1)
        return r.colliderect(VIEW.inflate(120, 120))

    def dashed(self, scr, col, p1, p2, width=2, offset=0.0):
        self.app.dashed(scr, col, p1, p2, width, offset=offset)

    # ------------------------------------------------------------------ the battle line of one lane
    def draw_front_lane(self, scr, fonts, mine, enemy):
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        pm, po = self.pos(mine), self.pos(enemy)
        if not self.lane_visible(pm, po):
            return
        fac = SECTORS[enemy]["faction"]
        ecol = FACTIONS[fac]["col"]
        st = director.stance(g, fac)
        fighting = st == "war" or bool(g.campaign and g.campaign["k"] == enemy)      # at peace the fleets only face each other
        tension = g.tension.get(fac, 0.0)
        t = front.front_pos(g, enemy)
        F = (pm[0] + (po[0] - pm[0]) * t, pm[1] + (po[1] - pm[1]) * t)
        z = self.z
        w = 2 + int(z // 2)
        pygame.draw.line(scr, (36, 66, 112), pm, F, w + 4)
        pygame.draw.line(scr, MINE, pm, F, w)
        self.dashed(scr, scale_c(ecol, 0.85), F, po, w, offset=app.t * 22)
        L = math.hypot(po[0] - pm[0], po[1] - pm[1]) or 1.0
        ux, uy = (po[0] - pm[0]) / L, (po[1] - pm[1]) / L
        nx, ny = -uy, ux
        now = app.t
        COLS = 5
        S = 14 + 4 * min(z, 3.4)             # drawn size of a ship in pixels
        gap = S + 3
        lat = S + 2
        arriving = director.intel(g) >= 1 and any(i["kind"] == "offensive" and i["src"] == enemy and i["target"] == mine
                                                  for i in g.incoming)
        if z >= CLOSE and mine == front.source_sector(g, enemy):      # the fleets gather on the main lane
            body = 16 * (0.85 + 0.15 * min(z, 3))
            roster = front.fleet_roster(g)
            fp, ep = g.fleet_power(), g.sector_power(enemy)
            rows_m = max(1, int(max(0.0, t * L - body - 8) / gap))
            rows_e = max(1, int(max(0.0, (1 - t) * L - body - 8) / gap))
            n_m = min(front.ships_for(fp, 20), COLS * rows_m)
            n_e = 0 if arriving else min(front.ships_for(ep, 20), COLS * rows_e)
            mine_pts, enemy_pts = [], []
            ang_m = -math.degrees(math.atan2(uy, ux))
            ang_e = -math.degrees(math.atan2(-uy, -ux))
            for i in range(n_m):
                r, c = divmod(i, COLS)
                c -= COLS // 2
                back = 12 + r * gap + abs(c) * 0.3 * gap + 3 * math.sin(now * 1.3 + i * 1.7)
                side = c * lat + 2.5 * math.sin(now * 1.1 + i * 2.3)
                x, y = F[0] - ux * back + nx * side, F[1] - uy * back + ny * side
                mine_pts.append((x, y))
                self.spark(scr, x, y, S * 0.8, MINE, 0.35)
                img = self.rot(app.ship_sprite(*roster[i % len(roster)]), ang_m, S)
                scr.blit(img, img.get_rect(center=(x, y)))
            espr = app.enemy_small[fac]
            for j in range(n_e):
                r, c = divmod(j, COLS)
                c -= COLS // 2
                back = 12 + r * gap + abs(c) * 0.3 * gap + 3 * math.sin(now * 1.2 + j * 1.9)
                side = c * lat + 2.5 * math.sin(now * 1.0 + j * 2.1)
                x, y = F[0] + ux * back + nx * side, F[1] + uy * back + ny * side
                enemy_pts.append((x, y))
                self.spark(scr, x, y, S * 0.8, ecol, 0.35)
                img = self.rot(espr, ang_e, S)
                scr.blit(img, img.get_rect(center=(x, y)))
            # lasers, in short bursts
            slot = int(now * 6)
            lit = (now * 6) % 1.0 < 0.65
            if lit and fighting and mine_pts and enemy_pts:
                for q in range(min(4, 2 + len(mine_pts) // 6)):
                    a = mine_pts[min(len(mine_pts) - 1, int(hrand(mine, enemy, slot, q) * len(mine_pts)))]
                    b = enemy_pts[min(len(enemy_pts) - 1, int(hrand(enemy, mine, slot, q + 9) * len(enemy_pts)))]
                    mine_fire = hrand(slot, q, mine) < 0.5
                    s, e = (a, b) if mine_fire else (b, a)
                    col = LASER_MINE if mine_fire else ecol
                    pygame.draw.line(scr, scale_c(col, 0.6), s, e, 3)
                    pygame.draw.line(scr, lerp_c(col, (255, 255, 255), 0.45), s, e, 1)
                    self.spark(scr, e[0], e[1], 7, (255, 200, 120))
        # the battle line: your front and theirs, with the contested ground between
        half = 2 * lat + 10 if z >= CLOSE else 9      # how wide the battle line is
        for side_, col_ in ((-1, MINE if fighting else (120, 150, 190)), (1, ecol if fighting else (150, 140, 170))):
            ox_, oy_ = ux * 9 * side_, uy * 9 * side_
            a_ = (F[0] + ox_ - nx * half, F[1] + oy_ - ny * half)
            b_ = (F[0] + ox_ + nx * half, F[1] + oy_ + ny * half)
            self.dashed(scr, col_, a_, b_, 2, offset=now * 18 * side_ if fighting else 0.0)
        # the clash itself (or, at peace, a calm marker whose ring fills with the faction's tension)
        if fighting:
            pulse = 0.6 + 0.4 * math.sin(now * 7 + mine * 3 + enemy)
            self.spark(scr, F[0], F[1], 12 + 8 * min(z, 3) * pulse, (255, 170, 90), 0.5 + 0.5 * pulse)
            if z >= CLOSE:
                for q in range(3):
                    ph = (now * 2.0 + q * 0.34 + hrand(enemy, q)) % 1.0
                    off = (hrand(mine, enemy, q, int(now * 2.0 + q * 0.34)) - 0.5) * 36 * min(z, 3) / 2
                    self.spark(scr, F[0] + nx * off, F[1] + ny * off, 5 + 12 * ph, (255, 220, 160), 1 - ph)
            for a in range(4):
                ang = now * 2.2 + a * math.pi / 2
                pygame.draw.line(scr, (255, 235, 190), (F[0] + math.cos(ang) * 4, F[1] + math.sin(ang) * 4),
                                 (F[0] + math.cos(ang) * 10, F[1] + math.sin(ang) * 10), 2)
        else:
            tc = (120, 220, 140) if tension < 0.5 else ((255, 215, 100) if tension < 0.8 else (255, 110, 100))
            if st == "truce":
                tc = (130, 220, 255)
            rr = pygame.Rect(0, 0, 22, 22)
            rr.center = (F[0], F[1])
            pygame.draw.circle(scr, (14, 18, 36), rr.center, 11)
            pygame.draw.circle(scr, scale_c(tc, 0.45), rr.center, 11, 2)
            if tension > 0.02 and st != "truce":
                pygame.draw.arc(scr, tc, rr, math.pi / 2, math.pi / 2 + math.tau * tension, 3)
            pygame.draw.circle(scr, tc, rr.center, 3)
        self.marks.append((F[0], F[1], enemy))
        if z >= DETAIL:                    # power split pill
            ch = win_chance(g.fleet_power(), g.sector_power(enemy))
            pw, ph = 70, 6
            bx, by = F[0] + nx * (half + 14) - pw / 2, F[1] + ny * (half + 14)
            shr = front.share(g, enemy)
            pygame.draw.rect(scr, (10, 12, 28), (bx - 2, by - 2, pw + 4, ph + 4), border_radius=4)
            pygame.draw.rect(scr, ecol, (bx, by, pw, ph), border_radius=3)
            pygame.draw.rect(scr, MINE, (bx, by, max(2, int(pw * shr)), ph), border_radius=3)
            tag = {"war": "  WAR", "truce": "  TRUCE", "peace": f"  peace {tension * 100:.0f}%"}[st]
            app.txt(scr, tiny, f"{ch * 100:.0f}%{tag}", (bx + pw / 2, by + ph + 3), app.chance_color(ch), "midtop", True)

    # ------------------------------------------------------------------ the whole view
    def draw(self, scr, fonts):
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        z = self.z
        now = app.t
        conq = g.conquered
        fr = set(g.frontier())
        fp = g.fleet_power()
        self.hits, self.marks = [], []
        mouse = app.mouse
        stage = pygame.Rect(0, 0, STAGE_W, scr.get_height())
        scr.set_clip(stage)
        ox = max(-150, min(150, -(self.x - 0.5) * MAPW * z * 0.14))
        oy = max(-90, min(90, -(self.y - 0.5) * MAPH * z * 0.14))
        gbw, gbh = app.galaxy_bg.get_size()
        scr.blit(app.galaxy_bg, (STAGE_W * 0.586 - gbw / 2 + ox, scr.get_height() * 0.528 - gbh / 2 + oy), special_flags=ADD)
        app.txt(scr, med, "GALAXY MAP", (VIEW.right, 104), (190, 200, 235), "topright", True)
        app.txt(scr, tiny, "Liberate sectors to claim their bonuses", (VIEW.right, 126), (140, 150, 185), "topright")
        scr.set_clip(VIEW)
        # territory
        for k in range(NSEC):
            if k not in conq and k not in fr:
                continue
            x, y = self.pos(k)
            if not self.visible(x, y, 140):
                continue
            col = (70, 120, 210) if k in conq else FACTIONS[SECTORS[k]["faction"]]["col"]
            r = int((52 + 34 * min(z, 3)) / 4) * 4
            scr.blit(glow(r, scale_c(col, 0.32 if k in conq else 0.26)), (x - r, y - r), special_flags=ADD)
        # lanes
        for a, b in SECTOR_EDGES:
            pa, pb = self.pos(a), self.pos(b)
            if not self.lane_visible(pa, pb):
                continue
            ac, bc = a in conq, b in conq
            if ac and bc:
                pygame.draw.line(scr, (40, 80, 130), pa, pb, 5 + int(z))
                pygame.draw.line(scr, (140, 200, 255), pa, pb, 2)
            elif ac or bc:
                pass                        # frontlines are drawn below
            elif a in fr or b in fr:
                pygame.draw.line(scr, (38, 44, 78), pa, pb, 1)
        for mine, enemy in front.lanes(g):
            self.draw_front_lane(scr, fonts, mine, enemy)
        # sectors
        sel = app.sel_sector
        hover = None
        camp = g.campaign
        for k in range(NSEC):
            x, y = self.pos(k)
            if not self.visible(x, y, 80):
                continue
            zz = min(z, 3.0)
            R = int(14 * (0.85 + 0.15 * zz))
            if k in conq:
                col = app.sector_color(k)
                big_r = int(R * 1.35) if k == 0 else R
                gr = int(34 * (0.9 + 0.2 * zz)) // 4 * 4
                scr.blit(glow(gr, scale_c((130, 190, 255) if k else (255, 190, 90), 0.5)), (x - gr, y - gr), special_flags=ADD)
                pygame.draw.circle(scr, (20, 36, 72), (x, y), big_r)
                pygame.draw.circle(scr, (140, 205, 255) if k else (255, 215, 120), (x, y), big_r, 2)
                pygame.draw.circle(scr, col if k else (255, 230, 160), (x, y), int(big_r * (0.36 if k else 0.5)))
                ly = y + big_r + 5
                app.txt(scr, tiny, SECTORS[k]["name"], (x, ly), (190, 215, 245), "midtop", True)
                ly += 14
                exposed = None
                if k:
                    foes, hold = front.exposure(g, k)
                    exposed = hold
                    if hold is not None and z >= CLOSE:      # garrison shield
                        label, rc = front.risk(hold)
                        for q in range(3):
                            a0 = now * 0.6 + q * math.tau / 3
                            pygame.draw.arc(scr, rc, (x - big_r - 7, y - big_r - 7, 2 * big_r + 14, 2 * big_r + 14),
                                            a0, a0 + 1.5, 2)
                if z >= DETAIL and k:
                    app.txt(scr, tiny, SECTORS[k]["desc"], (x, ly), (130, 255, 150), "midtop", True)
                    ly += 14
                    if exposed is not None:
                        label, rc = front.risk(exposed)
                        app.txt(scr, tiny, f"Garrison {fmt(director.sector_defense(g, k))}  -  {label} {exposed * 100:.0f}%",
                                (x, ly), rc, "midtop", True)
                for inc in g.incoming:
                    if inc["kind"] == "offensive" and inc["target"] == k and inc["fort"]:
                        pygame.draw.circle(scr, (255, 215, 90), (x, y), big_r + 10, 2)
            elif k in fr:
                fac = SECTORS[k]["faction"]
                col = FACTIONS[fac]["col"]
                pulse = round((0.55 + 0.45 * math.sin(now * 3 + k)) * 6) / 6
                gr = int(36 * (0.9 + 0.2 * zz)) // 4 * 4
                scr.blit(glow(gr, scale_c(col, 0.4 * pulse + 0.2)), (x - gr, y - gr), special_flags=ADD)
                pygame.draw.circle(scr, scale_c(col, 0.22), (x, y), R)
                pygame.draw.circle(scr, col, (x, y), R, 2)
                spr = app.enemy_small[fac]
                orbit = 25 + 8 * (zz - 1)
                for j in range(3 if z < CLOSE else 5):
                    a = now * 0.9 + j * math.tau / (3 if z < CLOSE else 5) + k
                    ex, ey = x + math.cos(a) * orbit, y + math.sin(a) * orbit * 0.72
                    img = self.rot(spr, -math.degrees(a + math.pi / 2), 18 + 2 * zz)
                    scr.blit(img, img.get_rect(center=(ex, ey)))
                if camp and camp["k"] == k:                   # siege ring: campaign progress
                    prog = max(0.0, min(1.0, camp["t"] / max(1.0, camp["dur"])))
                    rr = pygame.Rect(0, 0, 2 * (R + 9), 2 * (R + 9))
                    rr.center = (x, y)
                    pygame.draw.arc(scr, (130, 220, 255), rr, math.pi / 2, math.pi / 2 + math.tau * prog, 3)
                ch = win_chance(fp, g.sector_power(k))
                ly = y + R + 17
                app.txt(scr, tiny, SECTORS[k]["name"], (x, ly), (235, 225, 225), "midtop", True)
                ly += 14
                app.txt(scr, tiny, f"{ch * 100:.0f}%", (x, ly), app.chance_color(ch), "midtop", True)
                ly += 14
                if z >= DETAIL:
                    label, sc_ = front.status(g, k)
                    app.txt(scr, tiny, f"{FACTIONS[fac]['name']}  -  power {fmt(g.sector_power(k))}", (x, ly), col, "midtop", True)
                    ly += 14
                    app.txt(scr, tiny, label, (x, ly), sc_, "midtop", True)
            else:
                pygame.draw.circle(scr, (52, 58, 96), (x, y), 4)
            if k and app.sector_known(k):
                if sel == k:
                    rad = R + 9
                    for q in range(12):
                        a0 = now * 1.5 + q * math.tau / 12
                        pygame.draw.arc(scr, (255, 255, 255), (x - rad, y - rad, 2 * rad, 2 * rad), a0, a0 + 0.3, 2)
                if math.hypot(mouse[0] - x, mouse[1] - y) < 20 + 3 * zz and VIEW.collidepoint(mouse):
                    hover = k
        # enemy fleets on their way
        ilv = director.intel(g)
        if ilv >= 1:
            for inc in g.incoming:
                sx, sy = self.pos(inc["src"])
                tx, ty = self.pos(inc["target"]) if inc["kind"] == "offensive" else self.pos(0)
                f = max(0.0, min(1.0, inc["t"] / max(0.1, inc["eta"])))
                self.dashed(scr, (255, 90, 80), (sx, sy), (tx, ty), 2, offset=-now * 30)
                mx, my = sx + (tx - sx) * f, sy + (ty - sy) * f
                scr.blit(glow(18, (150, 40, 30)), (mx - 18, my - 18), special_flags=ADD)
                fac = inc["fac"] if ilv >= 2 and inc["fac"] else "pirates"
                ang = -math.degrees(math.atan2(ty - sy, tx - sx))
                if z >= CLOSE:
                    L = math.hypot(tx - sx, ty - sy) or 1.0
                    ux, uy = (tx - sx) / L, (ty - sy) / L
                    n = front.ships_for(inc["power"], 12) if ilv >= 3 else 6
                    S = 14 + 4 * min(z, 3.4)
                    for i in range(n):
                        r, c = divmod(i, 3)
                        px = mx - ux * (r * (S + 3)) - uy * (c - 1) * (S + 2)
                        py = my - uy * (r * (S + 3)) + ux * (c - 1) * (S + 2)
                        img = self.rot(app.enemy_small[fac], ang, S)
                        scr.blit(img, img.get_rect(center=(px, py)))
                else:
                    img = self.rot(app.enemy_small[fac], ang)
                    scr.blit(img, img.get_rect(center=(mx, my)))
                app.txt(scr, tiny, fmt_eta(max(0, inc["eta"] - inc["t"])), (mx, my + 16), (255, 150, 140), "midtop", True)
        # your fleet on its way (zoomed out only: zoomed in it is the swarm on the lane)
        if camp and z < CLOSE:
            k = camp["k"]
            tx, ty = self.pos(k)
            srcs = [n for n in SECTOR_LINKS[k] if n in conq]
            sx, sy = min((self.pos(n) for n in srcs), key=lambda q: math.hypot(q[0] - tx, q[1] - ty)) if srcs else (tx, ty)
            f = max(0.0, min(1.0, camp["t"] / camp["dur"]))
            fx_, fy_ = sx + (tx - sx) * f, sy + (ty - sy) * f
            ang = math.atan2(ty - sy, tx - sx)
            for tc in range(1, 5):
                scr.blit(glow(10 - tc, scale_c((130, 200, 255), 0.6 / tc)),
                         (fx_ - math.cos(ang) * tc * 9 - (10 - tc), fy_ - math.sin(ang) * tc * 9 - (10 - tc)), special_flags=ADD)
            spr = self.rot(app.ship_sprite(*front.fleet_roster(g)[0]), -math.degrees(ang))
            scr.blit(spr, spr.get_rect(center=(fx_, fy_)))
        scr.set_clip(stage)
        self.draw_frame(scr, fonts)
        self.hover = hover
        app.hover_sector = hover
        if hover is not None:
            self.draw_tooltip(scr, fonts, hover, fp)
        scr.set_clip(None)

    # ------------------------------------------------------------------ frame, toolbar, mini-map, tooltip
    def draw_frame(self, scr, fonts):
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        r = VIEW
        pygame.draw.rect(scr, (64, 84, 140), r, 1, border_radius=6)
        for cx, cy, sx, sy in ((r.x, r.y, 1, 1), (r.right - 1, r.y, -1, 1), (r.x, r.bottom - 1, 1, -1), (r.right - 1, r.bottom - 1, -1, -1)):
            pygame.draw.line(scr, (150, 190, 255), (cx, cy), (cx + 16 * sx, cy), 2)
            pygame.draw.line(scr, (150, 190, 255), (cx, cy), (cx, cy + 16 * sy), 2)
        # toolbar (top right)
        mouse = app.mouse
        x = r.right - 8
        y = r.y + 8
        buttons = [("FRONT", 52, self.focus_selected), ("FIT", 38, self.fit), ("-", 28, lambda: self.zoom_at(GC, 1 / 1.35)),
                   ("+", 28, lambda: self.zoom_at(GC, 1.35))]
        for label, w, fn in buttons:
            rect = pygame.Rect(x - w, y, w, 26)
            x -= w + 6
            hot = rect.collidepoint(mouse)
            pygame.draw.rect(scr, (60, 84, 150) if hot else (26, 34, 70), rect, border_radius=6)
            pygame.draw.rect(scr, (120, 150, 215), rect, 1, border_radius=6)
            app.txt(scr, sm if len(label) > 1 else med, label, rect.center, (235, 240, 255), "center")
            self.hits.append((rect, fn))
        app.txt(scr, tiny, f"x{self.z:.1f}", (x - 2, y + 13), (170, 185, 225), "midright")
        app.txt(scr, tiny, "Wheel: zoom   Drag: pan   Double-click: close look   Z: front view",
                (r.x + 12, r.y + 10), (120, 132, 175))
        # mini-map
        if self.z > 1.05:
            m = self.minimap
            bg = pygame.Surface(m.size, pygame.SRCALPHA)
            pygame.draw.rect(bg, (8, 10, 26, 215), bg.get_rect(), border_radius=6)
            scr.blit(bg, m)
            pygame.draw.rect(scr, (80, 100, 160), m, 1, border_radius=6)

            def mp(px, py):
                return m.x + 6 + px * (m.w - 12), m.y + 6 + py * (m.h - 12)
            for a, b in SECTOR_EDGES:
                both = a in g.conquered and b in g.conquered
                pygame.draw.line(scr, (70, 120, 190) if both else (36, 42, 70), mp(*SECTORS[a]["pos"]), mp(*SECTORS[b]["pos"]), 1)
            fr = set(g.frontier())
            for k in range(NSEC):
                px, py = mp(*SECTORS[k]["pos"])
                if k in g.conquered:
                    pygame.draw.circle(scr, MINE, (px, py), 3)
                elif k in fr:
                    pygame.draw.circle(scr, FACTIONS[SECTORS[k]["faction"]]["col"], (px, py), 3)
                else:
                    pygame.draw.circle(scr, (60, 66, 100), (px, py), 1)
            hw, hh = VIEW.w / (2 * MAPW * self.z), VIEW.h / (2 * MAPH * self.z)
            x0, y0 = mp(self.x - hw, self.y - hh)
            x1, y1 = mp(self.x + hw, self.y + hh)
            vr = pygame.Rect(x0, y0, x1 - x0, y1 - y0).clip(m.inflate(-2, -2))
            pygame.draw.rect(scr, (255, 255, 255), vr, 1)

            def recenter(m=m):
                px = (app.mouse[0] - m.x - 6) / (m.w - 12)
                py = (app.mouse[1] - m.y - 6) / (m.h - 12)
                self.xt, self.yt = px, py
                self.clamp()
            self.hits.append((m, recenter))

    def draw_tooltip(self, scr, fonts, k, fp):
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        sec = SECTORS[k]
        lines = []
        if k in g.conquered:
            lines.append((f"{sec['name']}  (liberated)", (140, 205, 255)))
            lines.append((sec["desc"], (130, 255, 150)))
            foes, hold = front.exposure(g, k)
            if hold is not None:
                label, rc = front.risk(hold)
                lines.append((f"Garrison {fmt(director.sector_defense(g, k))}  -  {label}: {hold * 100:.0f}% to hold", rc))
        else:
            fac = FACTIONS[sec["faction"]]
            ep = g.sector_power(k)
            ch = win_chance(fp, ep)
            label, sc_ = front.status(g, k)
            lines.append((f"{sec['name']}  -  {fac['name']}", fac["col"]))
            lines.append((f"Enemy power {fmt(ep)}   yours {fmt(fp)}", (225, 225, 240)))
            lines.append((f"Win chance {ch * 100:.0f}%  -  {label}", app.chance_color(ch)))
            lines.append(front.stance_line(g, sec["faction"]))
            lines.append((f"Reward: {sec['desc']}", (170, 175, 205)))
        w = max(sm.size(t)[0] for t, _ in lines) + 24
        h = len(lines) * 20 + 14
        x, y = self.pos(k)
        r = pygame.Rect(0, 0, w, h)
        r.midbottom = (x, y - 30)
        r.clamp_ip(pygame.Rect(6, 6, STAGE_W - 12, scr.get_height() - 12))
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (14, 16, 36, 240), bg.get_rect(), border_radius=8)
        pygame.draw.rect(bg, (110, 130, 195, 255), bg.get_rect(), 1, border_radius=8)
        scr.blit(bg, r)
        for i, (t, col) in enumerate(lines):
            app.txt(scr, sm, t, (r.x + 12, r.y + 8 + i * 20), col)


def fmt_eta(sec):
    sec = int(sec)
    h, m = sec // 3600, sec % 3600 // 60
    return f"{h}h {m:02d}m" if h else f"{m}m {sec % 60:02d}s"

