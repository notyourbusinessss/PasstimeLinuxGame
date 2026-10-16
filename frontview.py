"""The Milky Way map: pan and zoom from the whole galaxy down to a single star, and look at the fronts.

Zoomed out you see the galaxy (painted from the real shape of the Milky Way), the Sun at the bottom, your territory
glowing blue and the systems your jump drive can reach marked in their faction's colour. Zoomed in, every system is a
star with its name, the lanes between neighbours, the range of your jump drive, and where a lane is a front the two fleets
face each other as ship swarms, with lasers and flashes at the clash point. A mini-map keeps you oriented. The numbers
behind it live in galaxy.py (the stars) and front.py (the fronts).
"""
import math
import threading

import pygame

import director
import front
import generals
import sysview
import galaxy
import gfx
import resources
import worldview
import core
from core import FACTIONS, NSEC, SECTORS, fmt, win_chance
from gfx import glow, lerp_c, scale_c

ADD = pygame.BLEND_RGB_ADD
VIEW = pygame.Rect(8, 72, 640, 412)   # the viewport (the left side of the window, below the HUD)
STAGE_W = 648
BAR = 0
TOP = 72                             # the galaxy screen has only a slim bar of numbers above the map
BAR_H = 84                           # the command bar at the bottom of the wide map
S_MAX = 140.0                        # most zoomed in: pixels per light-year
MAP_R = 58000.0                      # the camera stays within this many light-years of the Galactic Centre
MINE = (120, 190, 255)
LASER_MINE = (150, 225, 255)
SPAN, IMG = gfx.MW_SPAN, 1300        # the painted galaxy: SPAN light-years across, IMG pixels wide
XS, YS = galaxy.XS, galaxy.YS


def set_layout(panel_x, w, h, wide=False):
    """Fit the map to the window: its viewport is everything left of the side panel (all of the window when the panel is
    hidden, "wide") from the slim top bar to the planet strip. In the wide map a command bar sits along the bottom."""
    global VIEW, STAGE_W, BAR
    STAGE_W = panel_x - 12
    BAR = BAR_H if wide else 0
    VIEW = pygame.Rect(8, TOP, STAGE_W - 8, h - TOP - 52)


def hrand(*a):
    """Deterministic pseudo-random number in 0..1 from some integers (so swarms do not jitter between frames)."""
    h = 0
    for i, v in enumerate(a):
        h = (h * 1000003 + int(v) * (2654435761 + i * 97)) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 2246822519) & 0xFFFFFFFF
    h ^= h >> 13
    return (h & 0xFFFF) / 65536.0                 # always below 1, so int(r * n) is a valid index


def fmt_eta(sec):
    sec = int(sec)
    h, m = sec // 3600, sec % 3600 // 60
    return f"{h}h {m:02d}m" if h else f"{m}m {sec % 60:02d}s"


SFAC = [s["faction"] for s in SECTORS]
SNAME = [s["name"] for s in SECTORS]
REAL = [s["real"] for s in SECTORS]
FCOL = {fac: FACTIONS[fac]["col"] for fac in FACTIONS}
FDIM = {fac: scale_c(FACTIONS[fac]["col"], 0.55) for fac in FACTIONS}
GLOW_HELD = {True: scale_c((255, 215, 120), 0.45), False: scale_c((130, 195, 255), 0.45)}


def fame(k):
    """How well known a system is: famous places get their names shown first."""
    s = SECTORS[k]
    if k in (0, galaxy.BOSS) or s["name"] in galaxy.ORIGINAL_LP:
        return 3
    if s["landmark"]:
        return 2
    return 1 if s["real"] else 0


FAME = [fame(_k) for _k in range(NSEC)]


class FrontView:
    def __init__(self, app, tab_galaxy):
        self.app = app
        self.tab_galaxy = tab_galaxy        # index of the Galaxy tab in the side panel
        self.cx = self.tcx = 0.0
        self.cy = self.tcy = 0.0
        self.s = self.ts = 0.005
        self.fit_s = 0.005
        self.mc = (0, 0)
        self.drag = None
        self.hits = []                  # clickable rects of the toolbar and the mini-map: (rect, fn)
        self.marks = []                 # clash markers of this frame: (x, y, enemy system)
        self.pts = []                   # this frame's systems on screen: (x, y, id)
        self.rot_cache = {}
        self.hover = None
        self.last_click = (-9.0, None)
        self.bg = None                  # the painted galaxy (made in the background, see prebuild)
        self._building = None
        self._made = None
        self.first_open = True
        self.bg_view = None             # its cached, scaled piece for the current camera
        self.terr = None                # territory layer: a glow for every system you hold, in the painted galaxy's pixels
        self.terr_held = set()
        self._pcache = {}               # the last scaled piece of each painted layer (see _piece)
        self.terr_range = -1.0
        self.mini = None
        self.known = []
        self.known_set = set()
        self.terr_info = (0.0, 26670.0, 1.0)
        self.known_key = None
        self.held_edges = []
        self.dots = None
        self.dots_key = None
        self.dots_hits, self.dots_labels = [], []
        self.aim = None                 # an attack being aimed by dragging from a system you hold: dict(src, pos, hover)
        self.best, self.best_t = None, -9.0
        self.relayout()
        self.fit(snap=True)

    def relayout(self):
        side = 128
        self.minimap = pygame.Rect(VIEW.x + 8, VIEW.bottom - BAR - side - 8, side, side)
        self.mc = (VIEW.centerx, VIEW.y + (VIEW.h - BAR) / 2)
        self.fit_s = min(VIEW.w, VIEW.h - BAR) * 0.94 / (2 * 56000.0)
        self.bg_view = None
        self.clamp(snap=True)

    # ------------------------------------------------------------------ camera
    @property
    def z(self):
        return self.s / self.fit_s

    @property
    def zt(self):
        return self.ts / self.fit_s

    def pt(self, x, y):
        return self.mc[0] + (x - self.cx) * self.s, self.mc[1] + (y - self.cy) * self.s

    def pos(self, k):
        return self.mc[0] + (XS[k] - self.cx) * self.s, self.mc[1] + (YS[k] - self.cy) * self.s

    def world(self, px, py, target=False):
        s, cx, cy = (self.ts, self.tcx, self.tcy) if target else (self.s, self.cx, self.cy)
        return cx + (px - self.mc[0]) / s, cy + (py - self.mc[1]) / s

    def clamp(self, snap=False):
        self.ts = max(self.fit_s, min(S_MAX, self.ts))
        u = min(1.0, (self.ts / self.fit_s - 1.0) / 1.5)
        lim = MAP_R * u
        self.tcx = max(-lim, min(lim, self.tcx))
        self.tcy = max(-lim, min(lim, self.tcy))
        if snap:
            self.s, self.cx, self.cy = self.ts, self.tcx, self.tcy

    def update(self, dt):
        k = 1.0 - math.exp(-dt * 9.0)
        self.s *= (self.ts / self.s) ** k
        if abs(self.ts / self.s - 1.0) < 0.002:
            self.s = self.ts
        self.cx += (self.tcx - self.cx) * k
        self.cy += (self.tcy - self.cy) * k

    def zoom_at(self, pos, factor):
        wx, wy = self.world(pos[0], pos[1], target=True)
        self.ts = max(self.fit_s, min(S_MAX, self.ts * factor))
        self.tcx = wx - (pos[0] - self.mc[0]) / self.ts
        self.tcy = wy - (pos[1] - self.mc[1]) / self.ts
        self.clamp()
        if self.zt >= 40:
            self.app.g.flags.add("closeup")

    def pan_px(self, dx, dy):
        """Drag the map by dx, dy screen pixels."""
        self.tcx -= dx / self.ts
        self.tcy -= dy / self.ts
        self.clamp()
        self.cx, self.cy = self.tcx, self.tcy

    def fit(self, snap=False):
        self.ts, self.tcx, self.tcy = self.fit_s, 0.0, 0.0
        self.clamp(snap)

    def look_at(self, x, y, scale, snap=False):
        self.ts, self.tcx, self.tcy = scale, x, y
        self.clamp(snap)

    def home(self, snap=False):
        """Frame all your territory."""
        held = self.app.g.conquered
        xs = [XS[k] for k in held]
        ys = [YS[k] for k in held]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pad = max(self.app.g.jump_range() * 1.2, 8.0)
        w, h = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
        self.look_at((x0 + x1) / 2, (y0 + y1) / 2, min(VIEW.w / w, (VIEW.h - BAR) / h), snap)

    def focus(self, k, snap=False):
        """Zoom in on system k: for an enemy system you can attack, the lane the attack would fly; otherwise its neighbourhood."""
        g = self.app.g
        px, py = XS[k], YS[k]
        src = front.source_sector(g, k) if k not in g.conquered else None
        if src is not None and galaxy.dist(src, k) < 3 * g.jump_range() + 1:
            sx, sy = XS[src], YS[src]
            t = front.front_pos(g, k)
            lane = math.hypot(px - sx, py - sy) or 1.0
            self.look_at(sx + (px - sx) * t, sy + (py - sy) * t, min(60.0, max(self.fit_s * 3, 0.62 * VIEW.w / lane)), snap)
        else:
            rng = max(g.jump_range(), 3.0)
            self.look_at(px, py, min(60.0, max(self.fit_s * 3, 0.32 * (VIEW.h - BAR) / rng)), snap)
        g.flags.add("closeup")

    def focus_selected(self):
        g = self.app.g
        k = self.app.sel_sector
        if k not in g.conquered and k not in g.targets_set():
            c = g.campaigns[0] if g.campaigns else None
            k = c["k"] if c else (min(g.targets(), key=lambda q: SECTORS[q]["lp"]) if g.targets() else 0)
        self.focus(k)

    def toggle(self):
        if self.zt > 12:
            self.fit()
        else:
            self.focus_selected()

    # ------------------------------------------------------------------ input
    def inside(self, pos):
        return VIEW.collidepoint(pos)

    def aim_source(self, pos):
        """The system you hold under the pointer when you press on it: a drag from there aims an attack (a drag from empty space pans)."""
        app, g = self.app, self.app.g
        if app.pick is not None or not g.galaxy_open:
            return None
        k = self.system_at(pos)
        return k if k is not None and k in g.conquered else None

    def target_at(self, pos):
        """The system you do not hold nearest to the pointer, within reach, to drop an attack on."""
        best, bd = None, 28.0 * (1.8 if resources.TOUCH else 1.0)
        for x, y, k in self.pts:
            d = math.hypot(pos[0] - x, pos[1] - y)
            if d < bd and k not in self.app.g.conquered:
                best, bd = k, d
        return best

    def down(self, pos):
        if not self.inside(pos):
            return False
        self.drag = dict(start=pos, last=pos, moved=False, aim=self.aim_source(pos))
        return True

    def move(self, pos):
        d = self.drag
        if not d:
            return
        if not d["moved"] and math.hypot(pos[0] - d["start"][0], pos[1] - d["start"][1]) > 5:
            d["moved"] = True
        if d.get("aim") is not None:                       # aiming an attack: the map stays where it is
            if d["moved"]:
                self.aim = dict(src=d["aim"], pos=pos, hover=self.target_at(pos))
        elif d["moved"]:
            self.pan_px(pos[0] - d["last"][0], pos[1] - d["last"][1])
        d["last"] = pos

    def up(self, pos):
        d, self.drag = self.drag, None
        self.aim = None
        if not d:
            return
        if d.get("aim") is not None and d["moved"]:        # dropped on a star: attack it
            k = self.target_at(pos)
            if k is not None:
                self.launch(k)
        elif not d["moved"]:
            self.click(pos)

    def launch(self, k):
        """Attack system k now (a faction at peace first asks to be declared war on): from a drag, the best-target key or a button."""
        app, g = self.app, self.app.g
        app.sel_sector = k
        app.tab = self.tab_galaxy
        why = g.attack_block(k)
        if why:
            g.toast(f"Cannot attack {SECTORS[k]['name']}: {why.lower()}", 3)
            return
        app.attack(k)

    def best_target(self):
        """The attack worth launching (see front.best_target), looked at twice a second."""
        app = self.app
        if app.t - self.best_t > 0.5 or app.t < self.best_t:
            self.best_t = app.t
            self.best = front.best_target(app.g)
        return self.best

    def attack_best(self):
        """Space on the map: launch the best attack, or say why there is none."""
        g = self.app.g
        self.best_t = -9.0
        b = self.best_target()
        if b is None:
            g.toast(front.why_no_best(g), 3)
            return
        self.launch(b[0])

    def wheel(self, pos, dy):
        if self.inside(pos) and dy:
            self.zoom_at(pos, 1.25 ** dy)

    def key(self, key):
        """Keyboard shortcuts of the galaxy view; True if the key was used."""
        if key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.zoom_at(self.mc, 1.5)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.zoom_at(self.mc, 1 / 1.5)
        elif key == pygame.K_z:
            self.toggle()
        elif key == pygame.K_SPACE:
            self.attack_best()
        elif key in (pygame.K_h, pygame.K_HOME):
            self.home()
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            dx = (key == pygame.K_RIGHT) - (key == pygame.K_LEFT)
            dy = (key == pygame.K_DOWN) - (key == pygame.K_UP)
            self.tcx += dx * 90 / self.ts
            self.tcy += dy * 90 / self.ts
            self.clamp()
        else:
            return False
        return True

    def system_at(self, pos):
        best, bd = None, 1e9
        reach = 15 * (1.8 if resources.TOUCH else 1.0)
        for x, y, k in self.pts:
            d = math.hypot(pos[0] - x, pos[1] - y)
            if d < reach and (d < bd or (abs(d - bd) < 2 and fame(k) > fame(best))):
                best, bd = k, d
        return best

    sector_at = system_at

    def click(self, pos):
        app = self.app
        for rect, fn in self.hits:
            if rect.collidepoint(pos):
                fn()
                return
        k = self.system_at(pos)
        if k is None:
            for x, y, enemy in self.marks:
                if math.hypot(pos[0] - x, pos[1] - y) < 16:
                    k = enemy
                    break
        if k is None:
            return
        if app.pick is not None and app.apply_pick(k):                 # picking a system for a general's orders
            return
        again = self.last_click[1] == k and app.t - self.last_click[0] < 0.45
        self.last_click = (app.t, k)
        app.sel_sector = k
        app.tab = self.tab_galaxy
        if again:
            self.focus(k)

    # ------------------------------------------------------------------ painted layers
    def prebuild(self):
        """Paint the Milky Way in a background thread (about a third of a second of work) so opening the map never stalls."""
        if self.bg is not None or self._building is not None:
            return

        def work():
            try:
                self._made = gfx.make_milky_way(IMG)
            except Exception:                     # (the map then paints it itself when it is first drawn)
                self._made = None
        self._building = threading.Thread(target=work, daemon=True)
        self._building.start()

    def ensure_bg(self):
        if self.bg is None:
            if self._building is not None:
                self._building.join()
                self._building = None
                self.bg = self._made
            if self.bg is None:
                self.bg = gfx.make_milky_way(IMG)
        return self.bg

    def opened(self):
        """The map has just been opened: the first time, show the neighbourhood of your territory rather than the whole galaxy."""
        if self.first_open:
            self.first_open = False
            self.home(snap=True)

    def _piece(self, layer, key, smooth_ok=True, fade=1.0, stamp=0):
        """The part of a world-sized layer the camera sees, scaled to the screen (None if nothing is on screen), dimmed by fade. The last
        one made for each layer is kept: while the camera does not move (most of the time) it costs nothing, where scaling a big picture
        to the screen every frame is the most expensive thing the map does. stamp says whether the layer itself has changed."""
        half = SPAN / 2
        vx0, vy0, vx1, vy1 = VIEW.x, VIEW.y, VIEW.right, VIEW.bottom - BAR
        wx0, wx1 = self.cx + (vx0 - self.mc[0]) / self.s, self.cx + (vx1 - self.mc[0]) / self.s
        wy0, wy1 = self.cy + (vy0 - self.mc[1]) / self.s, self.cy + (vy1 - self.mc[1]) / self.s
        u0, u1 = max(0.0, (wx0 + half) / SPAN * IMG), min(float(IMG), (wx1 + half) / SPAN * IMG)
        v0, v1 = max(0.0, (wy0 + half) / SPAN * IMG), min(float(IMG), (wy1 + half) / SPAN * IMG)
        if u1 - u0 < 1 or v1 - v0 < 1:
            return None
        src = pygame.Rect(int(u0), int(v0), max(1, int(math.ceil(u1)) - int(u0)), max(1, int(math.ceil(v1)) - int(v0)))
        src.clamp_ip(pygame.Rect(0, 0, IMG, IMG))
        # where that rectangle lands on the screen
        dx0 = self.mc[0] + (src.x / IMG * SPAN - half - self.cx) * self.s
        dy0 = self.mc[1] + (src.y / IMG * SPAN - half - self.cy) * self.s
        dw = max(1, int(round(src.w / IMG * SPAN * self.s)))
        dh = max(1, int(round(src.h / IMG * SPAN * self.s)))
        if dw > 6000 or dh > 6000:                      # absurdly magnified: skip
            return None
        at = (int(round(dx0)), int(round(dy0)))
        ck = (id(layer), stamp, tuple(src), dw, dh, at, smooth_ok, round(fade, 2))
        hit = self._pcache.get(key)
        if hit is not None and hit[0] == ck:
            return hit[1], at
        sub = layer.subsurface(src)
        img = pygame.transform.smoothscale(sub, (dw, dh)) if (smooth_ok and dw < src.w) else pygame.transform.scale(sub, (dw, dh))
        if fade < 1.0:
            img.fill((int(255 * fade),) * 3, special_flags=pygame.BLEND_RGB_MULT)
        self._pcache[key] = (ck, img)
        return img, at

    def draw_backdrop(self, scr):
        m = self.s * SPAN / IMG                          # screen pixels per pixel of the painted galaxy
        if m > 14:
            return
        fade = max(0.0, 1.0 - (m - 3) / 11.0) if m > 3 else 1.0        # too magnified to look good: fade it out
        piece = self._piece(self.ensure_bg(), "bg", fade=fade)
        if piece:
            img, at = piece
            scr.blit(img, at, special_flags=ADD)

    def update_territory(self, g):
        """Paint a soft glow for each system you hold into the territory layer (only the new ones when nothing was lost)."""
        held = g.conquered
        rng_px = 1.0
        redo = self.terr is None or bool(self.terr_held - held)
        if self.terr is None:
            self.terr = pygame.Surface((IMG, IMG))
        if redo:
            self.terr.fill((0, 0, 0))
            self.terr_held = set()
        for k in held - self.terr_held:
            u = (XS[k] + SPAN / 2) / SPAN * IMG
            v = (YS[k] + SPAN / 2) / SPAN * IMG
            for r, col in ((7.0, (8, 18, 38)), (4.0, (16, 36, 76)), (2.0, (40, 84, 150))):
                pygame.draw.circle(self.terr, col, (u, v), r)
            for n in galaxy.LINKS[k]:
                if n in self.terr_held or n in held and n < k:
                    pygame.draw.line(self.terr, (70, 130, 220), (u, v), ((XS[n] + SPAN / 2) / SPAN * IMG,
                                                                       (YS[n] + SPAN / 2) / SPAN * IMG), 1)
        self.terr_held = set(held)

    def draw_territory(self, scr, g):
        m = self.s * SPAN / IMG
        if m > 9:
            return
        self.update_territory(g)
        fade = max(0.0, 1.0 - (m - 2.5) / 6.5) if m > 2.5 else 1.0
        piece = self._piece(self.terr, "terr", fade=fade, stamp=(len(self.terr_held), sum(self.terr_held)))
        if piece:
            img, at = piece
            scr.blit(img, at, special_flags=ADD)

    def refresh_known(self, g):
        """The systems that are on the map: yours, the ones on your sensors, and the famous places."""
        r = g.sync_reach()
        key = (r.version, len(g.conquered), sum(g.conquered))
        if key == self.known_key:
            return
        held, scan = g.conquered, r.scan
        self.known = [k for k in range(NSEC) if k in held or scan[k] or SECTORS[k]["real"]]
        self.known_set = set(self.known)
        self.held_edges = [(a, b) for a in held for b in galaxy.LINKS[a] if b in held and a < b]
        hx = sum(XS[k] for k in held) / len(held)
        hy = sum(YS[k] for k in held) / len(held)
        self.terr_info = (hx, hy, max(math.hypot(XS[k] - hx, YS[k] - hy) for k in held))
        self.known_key = key

    # ------------------------------------------------------------------ small drawing helpers
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
        return VIEW.x - m < x < VIEW.right + m and VIEW.y - m < y < VIEW.bottom - BAR + m

    def lane_visible(self, pa, pb):
        r = pygame.Rect(min(pa[0], pb[0]), min(pa[1], pb[1]), abs(pa[0] - pb[0]) + 1, abs(pa[1] - pb[1]) + 1)
        return r.colliderect(VIEW.inflate(120, 120))

    def dashed(self, scr, col, p1, p2, width=2, offset=0.0):
        self.app.dashed(scr, col, p1, p2, width, offset=offset)

    def star_radius(self):
        return 1.0 + 1.55 * math.log10(max(self.s, 0.006) / 0.006)

    # ------------------------------------------------------------------ the battle line of one lane
    def draw_front_lane(self, scr, fonts, mine, enemy, main=True):
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        pm, po = self.pos(mine), self.pos(enemy)
        if not self.lane_visible(pm, po):
            return
        L = math.hypot(po[0] - pm[0], po[1] - pm[1]) or 1.0
        if L < 14:
            return
        z = max(1.0, min(3.4, L / 150.0))               # how big to draw things: bigger when the lane is long on screen
        close = L >= 190 and main
        fac = SECTORS[enemy]["faction"]
        ecol = FACTIONS[fac]["col"]
        st = director.stance(g, fac)
        fighting = st == "war" or g.attacking(enemy) is not None      # at peace the fleets only face each other
        tension = g.tension.get(fac, 0.0)
        t = front.front_pos(g, enemy)
        F = (pm[0] + (po[0] - pm[0]) * t, pm[1] + (po[1] - pm[1]) * t)
        w = 2 + int(z // 2)
        pygame.draw.line(scr, (36, 66, 112), pm, F, w + 4)
        pygame.draw.line(scr, MINE, pm, F, w)
        self.dashed(scr, scale_c(ecol, 0.85), F, po, w, offset=app.t * 22)
        ux, uy = (po[0] - pm[0]) / L, (po[1] - pm[1]) / L
        nx, ny = -uy, ux
        now = app.t
        COLS = 5
        S = 14 + 4 * min(z, 3.4)             # drawn size of a ship in pixels
        gap = S + 3
        lat = S + 2
        arriving = director.intel(g) >= 1 and any(i["kind"] == "offensive" and i["src"] == enemy and i["target"] == mine
                                                  for i in g.incoming)
        if close and mine == front.source_sector(g, enemy):      # the fleets gather on the main lane
            body = 16 * (0.85 + 0.15 * min(z, 3))
            roster = front.fleet_roster(g)
            camp = g.attacking(enemy)                            # the fleet in the field there, or else your whole fleet
            fp, ep = (camp["fp"] if camp else g.fleet_power()), g.sector_power(enemy)
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
                    s_, e_ = (a, b) if mine_fire else (b, a)
                    col = LASER_MINE if mine_fire else ecol
                    pygame.draw.line(scr, scale_c(col, 0.6), s_, e_, 3)
                    pygame.draw.line(scr, lerp_c(col, (255, 255, 255), 0.45), s_, e_, 1)
                    self.spark(scr, e_[0], e_[1], 7, (255, 200, 120))
        # the battle line: your front and theirs, with the contested ground between
        half = 2 * lat + 10 if close else 9      # how wide the battle line is
        for side_, col_ in ((-1, MINE if fighting else (120, 150, 190)), (1, ecol if fighting else (150, 140, 170))):
            ox_, oy_ = ux * 9 * side_, uy * 9 * side_
            a_ = (F[0] + ox_ - nx * half, F[1] + oy_ - ny * half)
            b_ = (F[0] + ox_ + nx * half, F[1] + oy_ + ny * half)
            self.dashed(scr, col_, a_, b_, 2, offset=now * 18 * side_ if fighting else 0.0)
        # the clash itself (or, at peace, a calm marker whose ring fills with the faction's tension)
        if fighting:
            pulse = 0.6 + 0.4 * math.sin(now * 7 + mine * 3 + enemy)
            self.spark(scr, F[0], F[1], 12 + 8 * min(z, 3) * pulse, (255, 170, 90), 0.5 + 0.5 * pulse)
            if close:
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
        if close and L >= 260:                    # power split pill
            camp = g.attacking(enemy)
            ch = camp["chance"] if camp else win_chance(g.fleet_power(), g.sector_power(enemy))
            pw, ph = 70, 6
            bx, by = F[0] + nx * (half + 14) - pw / 2, F[1] + ny * (half + 14)
            shr = front.share(g, enemy)
            pygame.draw.rect(scr, (10, 12, 28), (bx - 2, by - 2, pw + 4, ph + 4), border_radius=4)
            pygame.draw.rect(scr, ecol, (bx, by, pw, ph), border_radius=3)
            pygame.draw.rect(scr, MINE, (bx, by, max(2, int(pw * shr)), ph), border_radius=3)
            tag = {"war": "  WAR", "truce": "  TRUCE", "peace": f"  peace {tension * 100:.0f}%"}[st]
            app.txt(scr, tiny, f"{ch * 100:.0f}%{tag}", (bx + pw / 2, by + ph + 3), app.chance_color(ch), "midtop", True)

    def render_stars(self, tgt, ox, oy, g, R, now, sel, camps, app):
        """Draw every system on the map onto tgt (whose top-left is at screen position ox, oy). Returns the systems drawn,
        as (screen x, screen y, id), and the name labels wanted, as (priority, x, y, name, colour)."""
        s, mx, my, cx, cy = self.s, self.mc[0], self.mc[1], self.cx, self.cy
        vx0, vx1, vy0, vy1 = VIEW.x - 40, VIEW.right + 40, VIEW.y - 40, VIEW.bottom - BAR + 40
        conq = g.conquered
        tset = g.targets_set()
        labels, hits = [], []
        big_s = s >= 0.6
        set_at = tgt.set_at
        scan = g.reach.scan
        pulse_t = now * 3
        sel_k = sel
        for k in self.known:
            x = mx + (XS[k] - cx) * s
            y = my + (YS[k] - cy) * s
            if x < vx0 or x > vx1 or y < vy0 or y > vy1:
                continue
            fac = SFAC[k]
            held = k in conq
            tgtd = k in tset
            if not (held or tgtd or scan[k] or REAL[k]):
                continue
            hits.append((x, y, k))
            dx, dy = x - ox, y - oy
            if held:
                col = (255, 215, 120) if k == 0 else (130, 195, 255)
                r = max(2.4, R * (1.3 if k == 0 else 1.1))
                gr = int(r * 5) // 4 * 4 + 4
                tgt.blit(glow(gr, GLOW_HELD[k == 0]), (dx - gr, dy - gr), special_flags=ADD)
                if r >= 3.5:
                    pygame.draw.circle(tgt, (20, 36, 72), (dx, dy), r)
                    pygame.draw.circle(tgt, col, (dx, dy), r, 2)
                    pygame.draw.circle(tgt, col, (dx, dy), max(1, int(r * 0.4)))
                else:
                    pygame.draw.circle(tgt, (225, 240, 255), (dx, dy), max(1.5, r * 0.7))
            elif tgtd:
                fcol = FCOL[fac]
                r = max(1.6, R)
                if r >= 3.5:
                    pulse = 0.55 + 0.45 * math.sin(pulse_t + k)
                    gr = int(r * 5) // 4 * 4 + 4
                    tgt.blit(glow(gr, scale_c(fcol, 0.25 + 0.2 * pulse)), (dx - gr, dy - gr), special_flags=ADD)
                    pygame.draw.circle(tgt, scale_c(fcol, 0.22), (dx, dy), r)
                    pygame.draw.circle(tgt, fcol, (dx, dy), r, 2)
                    if big_s and s > 4:                       # enemy ships circling the system
                        spr = app.enemy_small[fac]
                        orbit = r + 14
                        for j in range(3):
                            a = now * 0.9 + j * math.tau / 3 + k
                            ex, ey = dx + math.cos(a) * orbit, dy + math.sin(a) * orbit * 0.72
                            img = self.rot(spr, -math.degrees(a + math.pi / 2), 16)
                            tgt.blit(img, img.get_rect(center=(ex, ey)))
                    if k in camps:                            # siege ring: campaign progress
                        camp = camps[k]
                        prog = max(0.0, min(1.0, camp["t"] / max(1.0, camp["dur"])))
                        rr = pygame.Rect(0, 0, 2 * (r + 8), 2 * (r + 8))
                        rr.center = (dx, dy)
                        pygame.draw.arc(tgt, (130, 220, 255), rr, math.pi / 2, math.pi / 2 + math.tau * prog, 3)
                elif r >= 2.2:
                    pygame.draw.circle(tgt, fcol, (dx, dy), r)
                else:
                    set_at((int(dx), int(dy)), fcol)
            elif scan[k]:
                if R >= 2.2:
                    pygame.draw.circle(tgt, FDIM[fac], (dx, dy), max(1.0, R * 0.7))
                else:
                    set_at((int(dx), int(dy)), FDIM[fac])
            else:                                             # a famous place beyond your sensors
                if R >= 2.2:
                    pygame.draw.circle(tgt, (150, 156, 190), (dx, dy), max(1.0, R * 0.8))
                else:
                    set_at((int(dx), int(dy)), (170, 176, 210))
            # name labels (only for the few systems that can have one at this zoom)
            f = FAME[k]
            if sel_k == k:
                pr = 100
            elif k in camps:
                pr = 90
            elif f >= 3:
                pr = 60 + (10 if held else 0)
            elif f or held or s >= 0.5:
                pr = None
                if s >= 0.5 or (f >= 1 and s >= 0.06) or (f >= 2 and s >= 0.02) or (held and f >= 1):
                    pr = 20 * f + (10 if tgtd else 0) + (8 if held else 0)
                    if f == 0 and s < 2.5:
                        pr = None
            else:
                pr = None
            if pr is not None:
                fcol = FCOL[fac]
                lc = (235, 238, 250) if held else lerp_c(fcol, (255, 255, 255), 0.45) if tgtd else (190, 196, 220)
                labels.append((pr, x, y, SNAME[k], lerp_c(lc, (255, 255, 255), 0.5) if pr >= 90 else lc))
        return hits, labels

    # ------------------------------------------------------------------ the whole view
    def draw(self, scr, fonts):
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        s = self.s
        now = app.t
        conq = g.conquered
        tset = g.targets_set()
        fp = g.fleet_power()
        self.hits, self.marks, self.pts = [], [], []
        mouse = app.mouse
        if self.first_open:
            self.opened()
        self.refresh_known(g)
        stage = pygame.Rect(0, 0, STAGE_W, scr.get_height())
        scr.set_clip(stage)
        scr.set_clip(VIEW.clip(pygame.Rect(0, 0, STAGE_W, VIEW.bottom - BAR)))
        self.draw_backdrop(scr)
        self.draw_territory(scr, g)
        mx, my, cx, cy = self.mc[0], self.mc[1], self.cx, self.cy
        vx0, vx1, vy0, vy1 = VIEW.x - 40, VIEW.right + 40, VIEW.y - 40, VIEW.bottom - BAR + 40
        sel = app.sel_sector
        camps = {c["k"]: c for c in g.campaigns}
        R = self.star_radius()
        rng_ly = g.jump_range()

        # zoomed far out your territory is a speck: ring it so you can find it
        if R < 2.2 and len(conq) > 1:
            hx, hy, hr = self.terr_info
            px, py = self.pt(hx, hy)
            pr = max(15.0, hr * s + 8.0)
            a0 = now * 0.4
            for q in range(16):
                pygame.draw.arc(scr, (130, 190, 255), (px - pr, py - pr, 2 * pr, 2 * pr), a0 + q * math.tau / 16,
                                a0 + q * math.tau / 16 + 0.26, 2)
            app.txt(scr, fonts[3], "Your territory", (px, py - pr - 4), (170, 210, 255), "midbottom", True)

        # jump range around the selected system (if you hold it) or around the system an attack on it would start from
        src_ring = None
        if sel in conq:
            src_ring = sel
        elif sel in tset or sel in camps:
            src_ring = front.source_sector(g, sel)
        if src_ring is not None and s * rng_ly > 4:
            x, y = self.pos(src_ring)
            rr = rng_ly * s
            if rr < 8000:
                pygame.draw.circle(scr, (96, 150, 235), (x, y), rr, 1)
                pygame.draw.circle(scr, (46, 76, 130), (x, y), rr + 2, 1)

        # lanes between systems you hold (and, zoomed in, between neighbours you can see)
        if s >= 0.12:
            for a, b in self.held_edges:
                xa, ya = mx + (XS[a] - cx) * s, my + (YS[a] - cy) * s
                xb, yb = mx + (XS[b] - cx) * s, my + (YS[b] - cy) * s
                if (xa < vx0 and xb < vx0) or (xa > vx1 and xb > vx1) or (ya < vy0 and yb < vy0) or (ya > vy1 and yb > vy1):
                    continue
                pygame.draw.line(scr, (34, 66, 112), (xa, ya), (xb, yb), 2)
                pygame.draw.line(scr, (120, 180, 245), (xa, ya), (xb, yb), 1)
        if s >= 1.0:
            known = self.known_set
            for k in self.known:
                x, y = mx + (XS[k] - cx) * s, my + (YS[k] - cy) * s
                if not (vx0 < x < vx1 and vy0 < y < vy1) or k in conq:
                    continue
                for n in galaxy.LINKS[k]:
                    if n > k and n in known and n not in conq:
                        xb, yb = mx + (XS[n] - cx) * s, my + (YS[n] - cy) * s
                        pygame.draw.line(scr, (30, 34, 62), (x, y), (xb, yb), 1)

        # the systems: zoomed far out they are tiny dots, painted once into a cache while the camera stands still
        if R < 2.2:
            key = (round(cx, 1), round(cy, 1), round(s, 9), self.known_key, sel, tuple(sorted(camps)), VIEW.size, BAR)
            if key != self.dots_key:
                self.dots = pygame.Surface(VIEW.size)
                self.dots_hits, self.dots_labels = self.render_stars(self.dots, VIEW.x, VIEW.y, g, R, now, sel, camps, app)
                self.dots_key = key
            scr.blit(self.dots, VIEW.topleft, special_flags=ADD)
            hits, labels = self.dots_hits, list(self.dots_labels)
            self.pts = hits
        else:
            hits, labels = self.render_stars(scr, 0, 0, g, R, now, sel, camps, app)
            self.pts = hits
        hover, hd = None, 18.0
        mxm, mym = mouse
        if VIEW.collidepoint(mouse):
            for x, y, k in hits:
                if abs(mxm - x) < hd and abs(mym - y) < hd:
                    d = math.hypot(mxm - x, mym - y)
                    if d < hd:
                        hover, hd = k, d
        if sel is not None:
            for x, y, k in hits:
                if k == sel:
                    rad = max(R, 3) + 8
                    for q in range(12):
                        a0 = now * 1.5 + q * math.tau / 12
                        pygame.draw.arc(scr, (255, 255, 255), (x - rad, y - rad, 2 * rad, 2 * rad), a0, a0 + 0.3, 2)
                    break

        # fronts: the lane of an attack you are flying or considering, and the borders at war you can see
        lanes = []
        for camp in camps.values():
            lanes.append((camp.get("src", 0), camp["k"]))
        if sel in tset:
            sp = front.source_sector(g, sel)
            if sp is not None and (sp, sel) not in lanes:
                lanes.append((sp, sel))
        n_main = len(lanes)                          # only these get the ship swarms
        if s >= 0.05:
            cand = []
            for m_, e_ in front.lanes(g):
                if (m_, e_) in lanes or not (e_ in tset or SECTORS[e_]["faction"] in g.war):
                    continue
                x, y = mx + (XS[e_] - cx) * s, my + (YS[e_] - cy) * s
                if vx0 < x < vx1 and vy0 < y < vy1:
                    cand.append(((x - mx) ** 2 + (y - my) ** 2, m_, e_))
            cand.sort()
            lanes += [(m_, e_) for _, m_, e_ in cand[:9]]
        for i, (m_, e_) in enumerate(lanes[:12]):
            self.draw_front_lane(scr, fonts, m_, e_, main=i < n_main)

        # enemy fleets on their way
        ilv = director.intel(g)
        if ilv >= 1:
            for inc in g.incoming:
                sx, sy = self.pos(inc["src"])
                tx, ty = self.pos(inc["target"]) if inc["kind"] == "offensive" else self.pos(0)
                f = max(0.0, min(1.0, inc["t"] / max(0.1, inc["eta"])))
                self.dashed(scr, (255, 90, 80), (sx, sy), (tx, ty), 2, offset=-now * 30)
                px, py = sx + (tx - sx) * f, sy + (ty - sy) * f
                scr.blit(glow(18, (150, 40, 30)), (px - 18, py - 18), special_flags=ADD)
                fac = inc["fac"] if ilv >= 2 and inc["fac"] else "pirates"
                ang = -math.degrees(math.atan2(ty - sy, tx - sx))
                img = self.rot(app.enemy_small[fac], ang)
                scr.blit(img, img.get_rect(center=(px, py)))
                app.txt(scr, tiny, fmt_eta(max(0, inc["eta"] - inc["t"])), (px, py + 16), (255, 150, 140), "midtop", True)
                if inc["kind"] == "offensive":
                    labels.append((95, tx, ty, SECTORS[inc["target"]]["name"], (255, 150, 140)))
        # your fleets on their way (zoomed far out: close up they are the swarm on the lane)
        for camp in camps.values():
            k = camp["k"]
            sxy, txy = self.pos(camp.get("src", 0)), self.pos(k)
            if math.hypot(txy[0] - sxy[0], txy[1] - sxy[1]) < 190:
                f = max(0.0, min(1.0, camp["t"] / camp["dur"]))
                fx_, fy_ = sxy[0] + (txy[0] - sxy[0]) * f, sxy[1] + (txy[1] - sxy[1]) * f
                self.dashed(scr, (120, 190, 255), sxy, txy, 1, offset=-now * 20)
                ang = math.atan2(txy[1] - sxy[1], txy[0] - sxy[0])
                for tc in range(1, 5):
                    scr.blit(glow(10 - tc, scale_c((130, 200, 255), 0.6 / tc)),
                             (fx_ - math.cos(ang) * tc * 9 - (10 - tc), fy_ - math.sin(ang) * tc * 9 - (10 - tc)), special_flags=ADD)
                spr = self.rot(app.ship_sprite(*front.fleet_roster(g)[0]), -math.degrees(ang))
                scr.blit(spr, spr.get_rect(center=(fx_, fy_)))
                if len(camps) > 1 or g.max_fronts() > 1:                  # how much of the fleet this front is
                    app.txt(scr, tiny, f"{camp['share'] * 100:.0f}%", (fx_, fy_ - 14), (170, 215, 255), "midbottom", True)
        self.draw_commanders(scr, fonts, labels)
        # name labels, the most important first, none on top of another
        labels.sort(key=lambda t: -t[0])
        placed = []
        for pr, x, y, name, col in labels[:90]:
            font = sm if pr >= 90 else tiny
            w, h = font.size(name)[0], 14
            r = pygame.Rect(0, 0, w + 4, h)
            r.midtop = (x, y + max(R, 3) + 5)
            if pr >= 90:                                   # the important ones always show: move them down until they fit
                for _ in range(4):
                    if not any(r.colliderect(p) for p in placed):
                        break
                    r.y += 16
            elif any(r.colliderect(p) for p in placed):
                continue
            placed.append(r)
            app.txt(scr, font, name, r.midtop, col, "midtop", True)
        self.draw_best(scr, fonts, R)
        self.draw_aim(scr, fonts)
        # distance rings when zoomed far in on the Sun's neighbourhood
        scr.set_clip(None)
        self.hover = hover
        app.hover_sector = hover

    def draw_best(self, scr, fonts, R):
        """A gold ring that pulses round the best attack to launch now (Space launches it)."""
        app = self.app
        b = self.best_target()
        if b is None or b[0] == app.sel_sector and app.g.attacking(b[0]):
            return
        x, y = self.pos(b[0])
        if not VIEW.collidepoint(x, y):
            return
        pulse = 0.5 + 0.5 * math.sin(app.t * 4.0)
        rad = max(R, 3) + 11 + 4 * pulse
        scr.blit(glow(int(rad + 8), (120, 90, 20)), (x - rad - 8, y - rad - 8), special_flags=ADD)
        pygame.draw.circle(scr, (255, 215, 110), (x, y), rad, 2)
        app.txt(scr, fonts[3], "BEST" + ("  (declares war)" if b[2] else ""), (x, y - rad - 4), (255, 225, 140), "midbottom", True)

    def draw_aim(self, scr, fonts):
        """The arrow of an attack being aimed: from the system you hold to the pointer, snapping to the star under it with its odds."""
        app, g = self.app, self.app.g
        a = self.aim
        if not a:
            return
        big, med, sm, tiny = fonts
        sx, sy = self.pos(a["src"])
        tgt = a["hover"]
        ex, ey = self.pos(tgt) if tgt is not None else a["pos"]
        why = g.attack_block(tgt) if tgt is not None else None
        col = (150, 190, 255) if tgt is None else ((255, 110, 100) if why else (255, 215, 110))
        self.dashed(scr, col, (sx, sy), (ex, ey), 3, offset=-app.t * 40)
        ang = math.atan2(ey - sy, ex - sx)
        tip = (ex - math.cos(ang) * 4, ey - math.sin(ang) * 4)
        pygame.draw.polygon(scr, col, [tip, (tip[0] - math.cos(ang - 0.45) * 16, tip[1] - math.sin(ang - 0.45) * 16),
                                       (tip[0] - math.cos(ang + 0.45) * 16, tip[1] - math.sin(ang + 0.45) * 16)])
        pygame.draw.circle(scr, col, (sx, sy), 9, 2)
        if tgt is None:
            text, tcol = "Drop on a star to attack it", (190, 215, 255)
        elif why:
            text, tcol = f"{SECTORS[tgt]['name']}: {why.lower()}", (255, 140, 130)
        else:
            ch = g.attack_chance(tgt)
            text = f"{SECTORS[tgt]['name']}   {ch * 100:.0f}% to win" + ("   - declares war" if SECTORS[tgt]["faction"] not in g.war else "")
            tcol = app.chance_color(ch)
        w = sm.size(text)[0] + 20
        r = pygame.Rect(0, 0, w, 26)
        r.midbottom = (ex, ey - 22)
        r.clamp_ip(VIEW.inflate(-12, -12))
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (10, 13, 32, 235), bg.get_rect(), border_radius=8)
        pygame.draw.rect(bg, (*col, 255), bg.get_rect(), 1, border_radius=8)
        scr.blit(bg, r)
        app.txt(scr, sm, text, r.center, tcol, "center")

    def draw_dock(self, scr, fonts):
        """The campaigns you are running, always in the corner of the map, and the button for the best attack."""
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        if not g.galaxy_open:
            return VIEW.y + 34
        camps = sorted(g.campaigns, key=lambda c: c["dur"] - c["t"])
        rows = camps[:4]
        r = pygame.Rect(VIEW.x + 10, VIEW.y + 36, 304, 40 + 31 * len(rows) + (16 if len(camps) > 4 else 0))
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (10, 13, 32, 210), bg.get_rect(), border_radius=9)
        pygame.draw.rect(bg, (90, 115, 185, 255), bg.get_rect(), 1, border_radius=9)
        scr.blit(bg, r)
        free = g.free_fronts()
        app.txt(scr, tiny, "CAMPAIGNS", (r.x + 10, r.y + 6), (200, 215, 255))
        app.txt(scr, tiny, f"{g.manual_count()}/{g.max_fronts()} fronts" + (f"  -  {len(g.campaigns) - g.manual_count()} by generals" if len(g.campaigns) > g.manual_count() else ""),
                (r.x + 10, r.y + 22), (150, 165, 205))
        b = self.best_target()
        label = "ATTACK BEST" if b else "NO TARGET"
        self.button(scr, pygame.Rect(r.right - 118, r.y + 6, 108, 26 if not resources.TOUCH else 34), label, self.attack_best, tiny, enabled=b is not None,
                    col=(110, 40, 46), accent=(255, 130, 110))
        y = r.y + 42
        for c in rows:
            k = c["k"]
            row = pygame.Rect(r.x + 4, y - 2, r.w - 8, 30)
            self.hits.append((row, lambda k=k: self.focus(k)))
            if row.collidepoint(app.mouse):
                pygame.draw.rect(scr, (30, 40, 80), row, border_radius=6)
            mark = "" if not c.get("by") else "  [general]"
            app.txt(scr, tiny, f"{SECTORS[k]['name']}{mark}", (r.x + 10, y), (255, 205, 190))
            app.txt(scr, tiny, f"{c['chance'] * 100:.0f}%  {fmt_eta(max(0, c['dur'] - c['t']))}", (r.right - 10, y), (255, 175, 150), "topright")
            pygame.draw.rect(scr, (40, 24, 28), (r.x + 10, y + 17, r.w - 20, 5), border_radius=3)
            pygame.draw.rect(scr, (255, 120, 100), (r.x + 10, y + 17, (r.w - 20) * c["t"] / c["dur"], 5), border_radius=3)
            y += 31
        if len(camps) > 4:
            app.txt(scr, tiny, f"+{len(camps) - 4} more", (r.x + 10, y), (255, 175, 150))
        return r.bottom + 8

    def draw_war_prompt(self, scr, fonts):
        """Dropping an attack on a faction at peace asks first, here, in plain words."""
        app, g = self.app, self.app.g
        if app.war_confirm <= 0 or app.war_confirm_k is None:
            return
        big, med, sm, tiny = fonts
        k = app.war_confirm_k
        fac = FACTIONS[SECTORS[k]["faction"]]["name"]
        l1, l2 = f"Declare war on the {fac}?", f"{SECTORS[k]['name']} is theirs: attacking it starts a war."
        w = min(VIEW.w - 20, max(sm.size(l1)[0], tiny.size(l2)[0]) + 14 + 24 + 232)
        r = pygame.Rect(0, 0, w, 64)
        r.midbottom = (VIEW.centerx, VIEW.bottom - BAR - 16)
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (30, 12, 16, 240), bg.get_rect(), border_radius=10)
        pygame.draw.rect(bg, (255, 120, 100, 255), bg.get_rect(), 2, border_radius=10)
        scr.blit(bg, r)
        app.txt(scr, sm, l1, (r.x + 14, r.y + 8), (255, 190, 170))
        app.txt(scr, tiny, l2, (r.x + 14, r.y + 34), (210, 170, 160))
        self.button(scr, pygame.Rect(r.right - 232, r.y + 14, 130, 36), "ATTACK", lambda k=k: app.attack(k), sm, col=(130, 40, 46), accent=(255, 130, 110))
        self.button(scr, pygame.Rect(r.right - 94, r.y + 14, 82, 36), "CANCEL", lambda: setattr(app, "war_confirm", 0.0), sm)

    def draw_commanders(self, scr, fonts, labels):
        """The command systems (a ring: gold for a general, blue for a warden) and the orders of your generals: an arrow for a
        heading, a dashed line toward a place."""
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        now = app.t
        for idx, k in enumerate(generals.SYSTEM_OF):
            x, y = self.pos(k)
            if not (VIEW.x - 20 < x < VIEW.right + 20 and VIEW.y - 20 < y < VIEW.bottom - BAR + 20):
                continue
            have = idx in g.cmd
            col = generals.colour(idx)
            r = max(self.star_radius(), 3) + 7
            pygame.draw.circle(scr, col if have else scale_c(col, 0.55), (x, y), r, 2 if have else 1)
            if generals.COMMANDERS[idx][1] == generals.WARDEN:
                pygame.draw.polygon(scr, col if have else scale_c(col, 0.55), [(x, y - r - 5), (x + 4, y - r - 1), (x - 4, y - r - 1)])
            else:
                pygame.draw.circle(scr, col if have else scale_c(col, 0.55), (x, y - r - 3), 2)
            if self.s >= 0.04 or have:
                labels.append((88 if have else 74, x, y, SNAME[k], lerp_c(col, (255, 255, 255), 0.4)))
        for idx, st in g.cmd.items():
            if generals.COMMANDERS[idx][1] != generals.GENERAL or not st["on"]:
                continue
            col = generals.colour(idx)
            name = generals.COMMANDERS[idx][2].split()[-1]
            if st["mode"] == "heading":
                tx, ty = self.pos(generals.tip(g, st["angle"]))
                ang = st["angle"]
                ex, ey = tx + math.cos(ang) * 110, ty + math.sin(ang) * 110
                self.dashed(scr, col, (tx, ty), (ex, ey), 2, offset=-now * 30)
                for da in (-2.5, 2.5):
                    pygame.draw.line(scr, col, (ex, ey), (ex + math.cos(ang + da) * 10, ey + math.sin(ang + da) * 10), 2)
                app.txt(scr, tiny, name, (ex, ey), col, "center", True)
            elif st["mode"] == "toward" and st["goal"] is not None and st["goal"] not in g.conquered:
                sx, sy = self.pos(g.source_of(st["goal"])[0])
                gx, gy = self.pos(st["goal"])
                self.dashed(scr, col, (sx, sy), (gx, gy), 2, offset=-now * 30)
                pygame.draw.circle(scr, col, (gx, gy), max(self.star_radius(), 3) + 10, 1)
                app.txt(scr, tiny, name, (gx, gy - 16), col, "midbottom", True)

    def draw_overlay(self, scr, fonts):
        """The frame, toolbar, command bar, alerts, mini-map and tooltip: drawn after the vignette so they are not dimmed."""
        app = self.app
        stage = pygame.Rect(0, 0, STAGE_W + 12, scr.get_height())
        scr.set_clip(stage)
        self.draw_frame(scr, fonts)
        if self.hover is not None and not self.aim:
            self.draw_tooltip(scr, fonts, self.hover, app.g.fleet_power())
        if app.pick is not None and app.pick["idx"] in app.g.cmd:
            what = {"heading": "a direction to go", "goal": "a place to go toward", "region": "a region to clear"}[app.pick["field"]]
            txt = f"Click a system: {what}  -  {generals.COMMANDERS[app.pick['idx']][2]}  (Esc cancels)"
            w = fonts[2].size(txt)[0] + 28
            r = pygame.Rect(0, 0, w, 32)
            r.midtop = (VIEW.centerx, VIEW.y + 8)
            pygame.draw.rect(scr, (60, 48, 20), r, border_radius=8)
            pygame.draw.rect(scr, (255, 215, 110), r, 2, border_radius=8)
            app.txt(scr, fonts[2], txt, r.center, (255, 238, 180), "center")
        scr.set_clip(None)

    # ------------------------------------------------------------------ frame, toolbar, mini-map, tooltip
    def draw_frame(self, scr, fonts):
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        r = pygame.Rect(VIEW.x, VIEW.y, VIEW.w, VIEW.h - BAR)
        pygame.draw.rect(scr, (64, 84, 140), r, 1, border_radius=6)
        for cx, cy, sx, sy in ((r.x, r.y, 1, 1), (r.right - 1, r.y, -1, 1), (r.x, r.bottom - 1, 1, -1), (r.right - 1, r.bottom - 1, -1, -1)):
            pygame.draw.line(scr, (150, 190, 255), (cx, cy), (cx + 16 * sx, cy), 2)
            pygame.draw.line(scr, (150, 190, 255), (cx, cy), (cx, cy + 16 * sy), 2)
        # toolbar (top right)
        x = VIEW.right - 8
        y = VIEW.y + 8
        bh = 40 if resources.TOUCH else 26
        tw = 1.35 if resources.TOUCH else 1.0
        panel_label = "PANEL" if app.gal_wide else "WIDE"
        buttons = [("BACK", 50, app.leave_galaxy), (panel_label, 58, app.toggle_gal_wide), ("HOME", 52, self.home),
                   ("FRONT", 52, self.focus_selected), ("FIT", 38, self.fit),
                   ("-", 28, lambda: self.zoom_at(self.mc, 1 / 1.5)), ("+", 28, lambda: self.zoom_at(self.mc, 1.5))]
        for label, w, fn in buttons:
            w = int(w * tw)
            rect = pygame.Rect(x - w, y, w, bh)
            x -= w + 6
            self.button(scr, rect, label, fn, med if len(label) == 1 else sm)
        app.txt(scr, tiny, self.scale_text(), (x - 2, y + bh // 2), (170, 185, 225), "midright")
        hint = ("Drag from your stars to attack   Pinch: zoom   Double-tap: close look" if resources.TOUCH else
                "Drag from your stars to attack   Space: best attack   Wheel: zoom   Drag: pan   H: home")
        if x - (VIEW.x + 12) > tiny.size(hint)[0] + 30:                  # only when there is room next to the buttons
            pill = pygame.Rect(VIEW.x + 8, VIEW.y + 6, tiny.size(hint)[0] + 16, 22)
            bg = pygame.Surface(pill.size, pygame.SRCALPHA)
            pygame.draw.rect(bg, (10, 13, 32, 170), bg.get_rect(), border_radius=8)
            scr.blit(bg, pill)
            app.txt(scr, tiny, hint, (pill.x + 8, pill.y + 4), (150, 162, 205))
        self.draw_alerts(scr, fonts, self.draw_dock(scr, fonts))
        self.draw_war_prompt(scr, fonts)
        if BAR:
            self.draw_command_bar(scr, fonts)
        self.draw_scale_bar(scr, fonts)
        self.draw_minimap(scr, fonts)

    def scale_text(self):
        """How much light-years one hundred pixels are, e.g. '100 px = 12 ly'."""
        ly = 100.0 / self.s
        return f"100 px = {galaxy.fmt_ly(ly)}" if ly >= 1 else f"100 px = {ly:.2f} ly"

    def draw_scale_bar(self, scr, fonts):
        """A ruler along the bottom edge of the map with a round number of light-years."""
        app = self.app
        tiny = fonts[3]
        target = 120 / self.s                                  # light-years that would be about 120 px
        mag = 10 ** math.floor(math.log10(target))
        ly = mag * (5 if target / mag >= 5 else 2 if target / mag >= 2 else 1)
        px = ly * self.s
        x0 = self.minimap.right + 18
        y0 = VIEW.bottom - BAR - 16
        pygame.draw.line(scr, (170, 185, 225), (x0, y0), (x0 + px, y0), 2)
        pygame.draw.line(scr, (170, 185, 225), (x0, y0 - 4), (x0, y0 + 4), 2)
        pygame.draw.line(scr, (170, 185, 225), (x0 + px, y0 - 4), (x0 + px, y0 + 4), 2)
        app.txt(scr, tiny, galaxy.fmt_ly(ly), (x0 + px / 2, y0 - 6), (190, 200, 235), "midbottom", True)

    def draw_minimap(self, scr, fonts):
        app, g = self.app, self.app.g
        m = self.minimap
        if self.mini is None or self.mini.get_width() != m.w - 2:
            self.mini = pygame.transform.smoothscale(self.ensure_bg(), (m.w - 2, m.h - 2))
            self.mini.fill((170, 170, 170), special_flags=pygame.BLEND_RGB_MULT)
        pygame.draw.rect(scr, (8, 10, 26), m, border_radius=6)
        scr.blit(self.mini, (m.x + 1, m.y + 1), special_flags=ADD)
        pygame.draw.rect(scr, (80, 100, 160), m, 1, border_radius=6)

        def mp(x, y):
            return m.x + 1 + (x + SPAN / 2) / SPAN * (m.w - 2), m.y + 1 + (y + SPAN / 2) / SPAN * (m.h - 2)
        held = g.conquered
        step = max(1, len(held) // 600)
        for i, k in enumerate(held):
            if i % step == 0:
                scr.set_at(tuple(int(v) for v in mp(XS[k], YS[k])), (140, 200, 255))
        for k in g.targets()[:0]:
            pass
        sx, sy = mp(XS[0], YS[0])
        pygame.draw.circle(scr, (255, 215, 120), (sx, sy), 2)
        hw, hh = VIEW.w / 2 / self.s, (VIEW.h - BAR) / 2 / self.s
        x0, y0 = mp(self.cx - hw, self.cy - hh)
        x1, y1 = mp(self.cx + hw, self.cy + hh)
        vr = pygame.Rect(x0, y0, x1 - x0, y1 - y0).clip(m.inflate(-2, -2))
        pygame.draw.rect(scr, (255, 255, 255), vr, 1)

        def recenter(m=m):
            px = ((app.mouse[0] - m.x - 1) / (m.w - 2) - 0.5) * SPAN
            py = ((app.mouse[1] - m.y - 1) / (m.h - 2) - 0.5) * SPAN
            self.tcx, self.tcy = px, py
            self.clamp()
        self.hits.append((m, recenter))

    def button(self, scr, rect, label, fn, font, enabled=True, col=(26, 34, 70), accent=(120, 150, 215)):
        """A button of the map overlay; clickable through self.hits."""
        app = self.app
        hot = enabled and rect.collidepoint(app.mouse) and not resources.TOUCH
        c = (60, 84, 150) if hot else col
        pygame.draw.rect(scr, c if enabled else (30, 32, 44), rect, border_radius=6)
        pygame.draw.rect(scr, accent if enabled else (60, 62, 80), rect, 1, border_radius=6)
        app.txt(scr, font, label, rect.center, (235, 240, 255) if enabled else (120, 122, 140), "center")
        if enabled:
            self.hits.append((rect, fn))

    def draw_alerts(self, scr, fonts, y=None):
        """Incoming enemy attacks (with Intel), with a Fortify button, under the toolbar."""
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        ilv = director.intel(g)
        if ilv < 1 or not g.incoming or app.panel_visible():       # (with the panel open its cards show the same)
            return
        y = VIEW.y + 34 if y is None else y
        for inc in g.incoming[:3]:
            left = max(0, inc["eta"] - inc["t"])
            name = "Counter-offensive" if inc["kind"] == "offensive" else director.TIERS[inc["tier"]]["name"]
            where = ""
            if ilv >= 2:
                where = (" -> " + SECTORS[inc["target"]]["name"]) if inc["kind"] == "offensive" else " -> " + ", ".join(
                    g.sites[q]["name"] for q in inc["targets"] if q < g.nsite)
            text = f"INCOMING: {name}{where}  ({fmt_eta(left)})"
            pill = pygame.Rect(VIEW.x + 10, y, min(VIEW.w - 20, tiny.size(text)[0] + 150), 28)
            bg = pygame.Surface(pill.size, pygame.SRCALPHA)
            pygame.draw.rect(bg, (40, 12, 16, 225), bg.get_rect(), border_radius=8)
            pygame.draw.rect(bg, (255, 100, 90, 255), bg.get_rect(), 1, border_radius=8)
            scr.blit(bg, pill)
            blink = 0.65 + 0.35 * math.sin(app.t * 6)
            app.txt(scr, tiny, text, (pill.x + 10, pill.centery), scale_c((255, 140, 130), blink), "midleft")
            if ilv >= 2:
                cost = director.fortify_cost(g, inc)
                done = bool(inc["fort"]) if inc["kind"] == "offensive" else len(inc["fort"]) >= len(inc["targets"])
                can = not done and g.credits >= cost
                label = "FORTIFIED" if done else f"FORTIFY {fmt(cost)}"
                b = pygame.Rect(pill.right - 140, pill.y + 3, 134, 22)
                self.button(scr, b, label, (lambda i=inc["id"]: director.fortify(g, i)), tiny, enabled=can, col=(70, 30, 36),
                            accent=(255, 130, 110))
            y += 34

    def system_lines(self, k):
        """(title, subtitle colour, lines) describing a system for the command bar and the tooltip."""
        app, g = self.app, self.app.g
        sec = SECTORS[k]
        fp = g.fleet_power()
        where = f"{galaxy.fmt_ly(sec['d'])} from the Sun  -  {sec['region']}, {sec['con']}"
        if k in g.conquered:
            lines = [(sec["desc"], (130, 255, 150))] if k else [("Your home system", (255, 215, 120))]
            if k:
                foes, hold = front.exposure(g, k)
                if hold is not None:
                    label, rc = front.risk(hold)
                    lines.append((f"Garrison {fmt(director.sector_defense(g, k))}  -  {label}: {hold * 100:.0f}% to hold", rc))
                else:
                    lines.append(("Rear system: nothing can reach it", (130, 230, 150)))
                w = worldview.summary(k)
                if w:
                    lines.append((w, (200, 190, 255)))
            return sec["name"], (140, 205, 255), f"{sec['kind']}  -  yours", where, lines
        fac = sec["faction"]
        fcol = FACTIONS[fac]["col"]
        if not (g.scanned(k)):
            return sec["name"], (190, 196, 220), f"{sec['kind']}", where, [
                ("Out of sensor range: extend your territory or your Jump Drive to learn more.", (170, 176, 205))]
        ep = g.sector_power(k)
        ch = win_chance(fp, ep)
        label, sc_ = front.status(g, k)
        lines = [(f"Enemy power {fmt(ep)}   your fleet {fmt(fp)}", (210, 215, 235)),
                 (f"Win chance {ch * 100:.0f}%  -  {label}", app.chance_color(ch)),
                 (f"Reward: {sec['desc']}", (150, 158, 190))]
        if k not in g.targets_set():
            _, d = g.source_of(k)
            lines.insert(0, (f"Out of range: {galaxy.fmt_ly(d)} from your nearest system, "
                             f"your jump drive reaches {galaxy.fmt_ly(g.jump_range())}", (255, 190, 120)))
        return sec["name"], fcol, f"{sec['kind']}  -  {FACTIONS[fac]['name']}", where, lines

    def draw_command_bar(self, scr, fonts):
        """The wide map's bottom bar: the selected system, what an attack would be like, and the actions."""
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        r = pygame.Rect(VIEW.x + 6, VIEW.bottom - BAR + 4, VIEW.w - 12, BAR - 10)
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (10, 13, 32, 236), bg.get_rect(), border_radius=10)
        pygame.draw.rect(bg, (90, 115, 185, 255), bg.get_rect(), 1, border_radius=10)
        scr.blit(bg, r)
        k = app.sel_sector
        sec = SECTORS[k]
        fp = g.fleet_power()
        name, col, sub, where, lines = self.system_lines(k)
        x = r.x + 14
        held = k in g.conquered
        if held:
            pygame.draw.circle(scr, (20, 36, 72), (x + 20, r.centery), 20)
            pygame.draw.circle(scr, col, (x + 20, r.centery), 20, 2)
        else:
            icon = app.enemy_big[sec["faction"]]
            scr.blit(icon, icon.get_rect(center=(x + 20, r.centery)))
        app.txt(scr, med, name, (x + 52, r.y + 8), col if not held else (225, 235, 255))
        app.txt(scr, tiny, sub, (x + 52, r.y + 32), col)
        app.txt(scr, tiny, where, (x + 52, r.y + 48), (140, 150, 185))
        tx = x + 52 + 270
        for i, (t, c) in enumerate(lines[:3]):
            app.txt(scr, tiny, t, (tx, r.y + 8 + i * 17), c)
        # actions, right-aligned
        bx = r.right - 12
        by = r.y + 12
        bh = 44 if resources.TOUCH else 32
        fac = None if held else sec["faction"]
        if fac is not None and g.scanned(k):
            can = g.can_attack(k) and fp > 0
            at_war = fac in g.war
            block = g.attack_block(k)
            if block:
                label = block
            elif at_war:
                label = "ATTACK"
            else:
                label = "CONFIRM WAR!" if app.war_confirm > 0 and app.war_confirm_k == k else "DECLARE WAR"
            rect = pygame.Rect(bx - 168, by, 168, bh)
            self.button(scr, rect, label, (lambda k=k: app.attack(k)), sm, enabled=can, col=(110, 40, 46), accent=(255, 130, 110))
            bx -= 176
            if at_war:
                ok, why = director.can_sue(g, fac)
                rect = pygame.Rect(bx - 148, by, 148, bh)
                label = "SUE FOR PEACE" if ok else (why if len(why) < 18 else "SUE FOR PEACE")
                self.button(scr, rect, label, (lambda f=fac: director.sue_for_peace(g, f)), tiny if not ok else sm, enabled=ok,
                            col=(30, 70, 60), accent=(110, 230, 190))
                bx -= 156
        rect = pygame.Rect(bx - 120, by, 120, bh)
        self.button(scr, rect, "CLOSE LOOK", (lambda k=k: self.focus(k)), sm)
        if held and sysview.can_open(g, k):
            bx -= 128
            rect = pygame.Rect(bx - 132, by, 132, bh)
            self.button(scr, rect, "OPEN SYSTEM", (lambda k=k: sysview.open_system(app, k)), sm, col=(30, 70, 60), accent=(110, 230, 190))

    def draw_tooltip(self, scr, fonts, k, fp):
        app, g = self.app, self.app.g
        big, med, sm, tiny = fonts
        name, col, sub, where, lines = self.system_lines(k)
        rows = [(name, col), (sub, (180, 188, 215))] + lines[:3]
        w = max(sm.size(t)[0] for t, _ in rows) + 24
        h = len(rows) * 20 + 14
        x, y = self.pos(k)
        r = pygame.Rect(0, 0, w, h)
        r.midbottom = (x, y - 24)
        r.clamp_ip(pygame.Rect(6, 6, STAGE_W - 12, scr.get_height() - 12))
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (14, 16, 36, 240), bg.get_rect(), border_radius=8)
        pygame.draw.rect(bg, (110, 130, 195, 255), bg.get_rect(), 1, border_radius=8)
        scr.blit(bg, r)
        for i, (t, c) in enumerate(rows):
            app.txt(scr, sm, t, (r.x + 12, r.y + 8 + i * 20), c)
