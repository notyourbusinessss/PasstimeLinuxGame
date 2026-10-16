"""Procedural graphics for Space Miner: every sprite is generated at start-up (no asset files)."""
import math
import random
from functools import lru_cache

import pygame

ADD = pygame.BLEND_RGB_ADD
SUB = pygame.BLEND_RGB_SUB
MULT = pygame.BLEND_RGB_MULT


def lerp_c(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def scale_c(c, k):
    return (max(0, min(255, int(c[0] * k))), max(0, min(255, int(c[1] * k))), max(0, min(255, int(c[2] * k))))


@lru_cache(maxsize=1500)
def glow(r, color):
    """Soft radial light, meant for additive blitting (BLEND_RGB_ADD)."""
    r = max(2, int(r))
    s = pygame.Surface((2 * r, 2 * r))
    s.fill((0, 0, 0))
    for i in range(r, 0, -1):
        t = 1 - i / r
        pygame.draw.circle(s, scale_c(color, t * t), (r, r), i)
    return s


def noise_gray(w, h, octaves=4, seed=0, base=3, stretch=True):
    """Smooth fractal value-noise as a grayscale surface (built from tiny random grids + smoothscale)."""
    rng = random.Random(seed)
    acc = pygame.Surface((w, h))
    acc.fill((0, 0, 0))
    weights = [0.55 ** i for i in range(octaves)]
    tot = sum(weights)
    for i, wt in enumerate(weights):
        n = base * 2 ** i + 1
        small = pygame.Surface((n, n))
        for x in range(n):
            for y in range(n):
                v = rng.randint(0, 255)
                small.set_at((x, y), (v, v, v))
        big = pygame.transform.smoothscale(small, (w, h))
        k = int(255 * wt / tot)
        big.fill((k, k, k), special_flags=MULT)
        acc.blit(big, (0, 0), special_flags=ADD)
    if stretch:
        acc.fill((70, 70, 70), special_flags=SUB)
        acc.blit(acc.copy(), (0, 0), special_flags=ADD)
    return acc


def sphere_shade(S, r, light=(-0.5, -0.55), ambient=(46, 48, 82), lit=(255, 244, 225)):
    """RGB lighting map; multiply it onto a texture to get a lit sphere."""
    s = pygame.Surface((S, S))
    s.fill(ambient)
    c = S / 2
    steps = max(8, int(r))
    for i in range(steps, 0, -1):
        t = i / steps
        k = min(1.0, (1 - t) * 1.25)
        col = lerp_c(ambient, lit, k ** 0.9)
        pygame.draw.circle(s, col, (int(c + light[0] * r * 0.62 * (1 - t)), int(c + light[1] * r * 0.62 * (1 - t))),
                           max(1, int(r * t)))
    return s


# ------------------------------------------------------------------ asteroid
ROCK_S = 270


def make_rock(seed=7):
    S = ROCK_S
    c = S // 2
    rr = 102
    rng = random.Random(seed)
    N = 26
    pts = []
    for i in range(N):
        a = i / N * math.tau
        m = 0.84 + 0.16 * rng.random()
        pts.append((c + math.cos(a) * rr * m, c + math.sin(a) * rr * m))
    big = pygame.Surface((S * 2, S * 2), pygame.SRCALPHA)
    pygame.draw.polygon(big, (255, 255, 255, 255), [(x * 2, y * 2) for x, y in pts])
    mask = pygame.transform.smoothscale(big, (S, S))

    tex = noise_gray(S, S, 5, seed, 4)
    tex.fill((140, 140, 140), special_flags=MULT)
    tex.fill((115, 115, 115), special_flags=ADD)
    tex.fill((196, 170, 148), special_flags=MULT)
    mineral = noise_gray(S, S, 3, seed + 5, 2)
    mineral.fill((55, 38, 22), special_flags=MULT)
    tex.blit(mineral, (0, 0), special_flags=ADD)
    for _ in range(11):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0.05, 0.72) * rr
        rad = int(rng.uniform(0.07, 0.17) * rr)
        x, y = int(c + math.cos(a) * d), int(c + math.sin(a) * d)
        pygame.draw.circle(tex, (62, 54, 50), (x, y), rad)
        pygame.draw.circle(tex, (82, 72, 64), (x + max(1, rad // 8), y + max(1, rad // 8)), int(rad * 0.82))
        rect = pygame.Rect(x - rad, y - rad, rad * 2, rad * 2)
        pygame.draw.arc(tex, (178, 160, 140), rect, -1.5, 0.1, 3)
        pygame.draw.arc(tex, (30, 26, 26), rect, 1.7, 3.1, 3)
    tex = tex.convert_alpha()
    tex.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    shade = sphere_shade(S, rr * 1.15, ambient=(70, 68, 98))
    return tex, shade


# ------------------------------------------------------------------ planets
def _planet_color(kind, v, v2, x, y, S, base):
    lat = abs(y / S - 0.5) * 2                     # 0 at equator, 1 at poles
    if kind == "earth":
        if v > 0.52:
            c = lerp_c((40, 120, 56), (150, 140, 84), (v2 - 0.3) * 1.6)
        else:
            c = lerp_c((14, 52, 150), (42, 112, 210), v / 0.52)
        if lat > 0.9:
            c = lerp_c(c, (245, 250, 255), 0.85)
        return lerp_c(c, (255, 255, 255), max(0.0, (v2 - 0.6) * 2.4))
    if kind == "moon":
        c = lerp_c((92, 92, 98), (205, 205, 210), v)
        return lerp_c(c, (40, 40, 46), max(0.0, (0.3 - v2) * 2.2))
    if kind == "mars":
        c = lerp_c((120, 50, 30), (216, 124, 72), v)
        c = lerp_c(c, (62, 30, 26), max(0.0, (0.36 - v2) * 2.4))
        return lerp_c(c, (250, 245, 240), max(0.0, (lat - 0.88) * 7))
    if kind == "venus":
        band = 0.5 + 0.5 * math.sin(y / S * 22 + v * 7)
        return lerp_c((200, 150, 70), (252, 232, 170), band)
    if kind == "mercury":
        c = lerp_c((66, 60, 56), (170, 158, 146), v)
        return lerp_c(c, (30, 28, 28), max(0.0, (0.28 - v2) * 2.5))
    if kind == "ceres":
        c = lerp_c((48, 46, 50), (126, 124, 130), v)
        return lerp_c(c, (250, 250, 255), max(0.0, (v2 - 0.93) * 14))
    if kind == "jupiter":
        band = 0.5 + 0.5 * math.sin(y / S * math.tau * 6 + v * 3)
        c = lerp_c((150, 86, 48), (244, 222, 190), band)
        dx, dy = (x - 0.64 * S) / (0.13 * S), (y - 0.63 * S) / (0.075 * S)
        if dx * dx + dy * dy < 1:
            c = lerp_c(c, (204, 70, 48), 0.9 - 0.6 * (dx * dx + dy * dy))
        return c
    if kind == "saturn":
        band = 0.5 + 0.5 * math.sin(y / S * math.tau * 4 + v * 2)
        return lerp_c((186, 160, 108), (246, 232, 192), band)
    if kind == "uranus":
        band = 0.5 + 0.5 * math.sin(y / S * math.tau * 2 + v * 1.5)
        return lerp_c((112, 196, 212), (196, 244, 248), band)
    if kind == "neptune":
        band = 0.5 + 0.5 * math.sin(y / S * math.tau * 3 + v * 2)
        c = lerp_c((22, 44, 170), (76, 120, 238), band)
        dx, dy = (x - 0.4 * S) / (0.1 * S), (y - 0.55 * S) / (0.06 * S)
        if dx * dx + dy * dy < 1:
            c = lerp_c(c, (10, 20, 90), 0.8)
        return c
    if kind == "pluto":
        c = lerp_c((142, 112, 92), (236, 222, 208), v)
        dx, dy = (x - 0.5 * S) / (0.3 * S), (y - 0.6 * S) / (0.22 * S)
        if dx * dx + dy * dy < 1:
            c = lerp_c(c, (250, 244, 238), 0.75)
        return c
    if kind == "kuiper":                  # a dwarf world of ice with dark red-brown patches of tholin and a few bright craters
        c = lerp_c((164, 176, 204), (244, 247, 255), min(1.0, v * 1.6))
        if v2 > 0.4:
            c = lerp_c(c, lerp_c((98, 56, 68), (178, 112, 112), min(1.0, v2 * 1.3)), min(0.9, (v2 - 0.4) * 3.4))
        for cx, cy, cr in ((0.30, 0.34, 0.07), (0.64, 0.58, 0.10), (0.42, 0.72, 0.05), (0.7, 0.28, 0.045)):
            dx, dy = (x - cx * S) / (cr * S), (y - cy * S) / (cr * S)
            q = dx * dx + dy * dy
            if q < 1:
                c = lerp_c(c, (250, 252, 255), 0.6 * (1 - q))
        return c
    return lerp_c((90, 90, 90), (200, 200, 200), v)


def make_planet(r, kind, base, seed):
    S = 2 * r + 2
    n1 = noise_gray(S, S, 4, seed, 3)
    n2 = noise_gray(S, S, 3, seed + 99, 3)
    tex = pygame.Surface((S, S))
    for x in range(S):
        for y in range(S):
            tex.set_at((x, y), _planet_color(kind, n1.get_at((x, y))[0] / 255, n2.get_at((x, y))[0] / 255,
                                             x, y, S, base))
    big = pygame.Surface((S * 4, S * 4), pygame.SRCALPHA)
    pygame.draw.circle(big, (255, 255, 255, 255), (S * 2, S * 2), r * 4)
    mask = pygame.transform.smoothscale(big, (S, S))
    shade = sphere_shade(S, r)
    tex.blit(shade, (0, 0), special_flags=MULT)
    tex = tex.convert_alpha()
    tex.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return tex


# ------------------------------------------------------------------ worlds of other systems
WORLD_RES = 56                    # a big picture of a world is painted at this radius and scaled up


def _world_pal(kind, rng):
    """The colours of one world of a kind: a few palettes and a few random knobs, so no two worlds look the same."""
    if kind == "temperate":
        land = rng.choice([((40, 118, 52), (156, 144, 84)), ((70, 112, 44), (176, 150, 96)), ((34, 96, 84), (130, 150, 110))])
        return dict(land=land, sea=((12, 48, 140), (40, 108, 206)), cut=rng.uniform(0.42, 0.58), cloud=rng.uniform(0.55, 0.7))
    if kind == "ocean":
        return dict(sea=rng.choice([((8, 40, 128), (30, 120, 214)), ((6, 56, 112), (40, 150, 190)), ((20, 40, 120), (70, 110, 220))]),
                    cloud=rng.uniform(0.5, 0.65))
    if kind == "rocky":
        return dict(cols=rng.choice([((92, 86, 80), (190, 176, 160)), ((84, 78, 90), (176, 170, 186)), ((100, 82, 70), (200, 170, 140))]))
    if kind == "desert":
        return dict(cols=rng.choice([((150, 96, 52), (236, 196, 128)), ((170, 110, 60), (240, 210, 150)), ((130, 80, 60), (214, 164, 120))]),
                    ripple=rng.uniform(10, 26))
    if kind == "ice":
        return dict(cols=rng.choice([((176, 200, 226), (250, 252, 255)), ((190, 214, 220), (246, 252, 252)), ((170, 180, 220), (240, 244, 255))]))
    if kind == "lava":
        return dict(glow=rng.choice([((255, 110, 30), (255, 220, 120)), ((255, 70, 40), (255, 190, 90))]), width=rng.uniform(9, 16))
    if kind == "dwarf":
        return dict(cols=rng.choice([((116, 100, 92), (214, 200, 190)), ((84, 84, 92), (190, 190, 200)), ((140, 110, 96), (232, 214, 200))]))
    if kind == "mini":
        return dict(cols=rng.choice([((140, 184, 206), (214, 236, 244)), ((186, 164, 208), (236, 224, 246)), ((196, 196, 150), (246, 244, 214))]),
                    bands=rng.uniform(3, 7))
    if kind == "ice_giant":
        return dict(cols=rng.choice([((104, 190, 208), (196, 244, 248)), ((22, 44, 170), (80, 124, 240)), ((60, 150, 150), (170, 228, 214))]),
                    bands=rng.uniform(2, 5))
    return dict(cols=rng.choice([((150, 86, 48), (244, 222, 190)), ((186, 160, 108), (246, 232, 192)), ((120, 90, 60), (230, 200, 160)),
                                 ((90, 110, 150), (200, 215, 235)), ((160, 70, 60), (240, 190, 170))]),
                bands=rng.uniform(4, 9), storm=(rng.uniform(0.2, 0.8), rng.uniform(0.35, 0.65)))


def _world_color(kind, pal, v, v2, x, y, S):
    lat = abs(y / S - 0.5) * 2
    if kind == "temperate" or kind == "ocean":
        if kind == "temperate" and v > pal["cut"]:
            c = lerp_c(pal["land"][0], pal["land"][1], min(1.0, max(0.0, (v2 - 0.3) * 1.6)))
        else:
            c = lerp_c(pal["sea"][0], pal["sea"][1], v / max(0.2, pal.get("cut", 0.8)))
        if lat > 0.9:
            c = lerp_c(c, (245, 250, 255), 0.85)
        return lerp_c(c, (255, 255, 255), max(0.0, (v2 - pal["cloud"]) * 2.6))
    if kind in ("rocky", "dwarf"):
        c = lerp_c(pal["cols"][0], pal["cols"][1], v)
        return lerp_c(c, (36, 34, 38), max(0.0, (0.3 - v2) * 2.2))
    if kind == "desert":
        c = lerp_c(pal["cols"][0], pal["cols"][1], v)
        return lerp_c(c, pal["cols"][0], 0.5 + 0.5 * math.sin(y / S * pal["ripple"] + v * 6) * 0.5)
    if kind == "ice":
        c = lerp_c(pal["cols"][0], pal["cols"][1], v)
        return lerp_c(c, (90, 120, 170), max(0.0, 1 - abs(v2 - 0.5) * 22) * 0.7)
    if kind == "lava":
        crust = lerp_c((26, 22, 24), (74, 52, 46), v)
        k = max(0.0, 1 - abs(v - 0.5) * pal["width"] * 0.35) ** 2
        k = max(k, max(0.0, 1 - abs(v2 - 0.45) * pal["width"] * 0.3) ** 3)
        return lerp_c(crust, lerp_c(pal["glow"][0], pal["glow"][1], k), min(1.0, k * 1.2))
    band = 0.5 + 0.5 * math.sin(y / S * math.tau * pal["bands"] + v * (3 if kind == "gas" else 1.6))
    c = lerp_c(pal["cols"][0], pal["cols"][1], band)
    if kind == "gas":
        sx, sy = pal["storm"]
        dx, dy = (x - sx * S) / (0.12 * S), (y - sy * S) / (0.07 * S)
        if dx * dx + dy * dy < 1:
            c = lerp_c(c, (204, 80, 56), 0.9 - 0.6 * (dx * dx + dy * dy))
    return c


@lru_cache(maxsize=160)
def make_world(kind, seed, size, ring=False):
    """A picture of a world of another system, size x size pixels, lit from the upper left; a ringed giant is drawn smaller, inside
    its rings. Pictures are cached, so never draw on one."""
    rng = random.Random(seed)
    pal = _world_pal(kind, rng)
    diam = int(size * 0.58) if ring else size
    tr = max(8, min(diam // 2, WORLD_RES))
    S = 2 * tr + 2
    n1 = noise_gray(S, S, 4, seed, 3)
    n2 = noise_gray(S, S, 3, seed + 99, 3)
    tex = pygame.Surface((S, S))
    for x in range(S):
        for y in range(S):
            tex.set_at((x, y), _world_color(kind, pal, n1.get_at((x, y))[0] / 255, n2.get_at((x, y))[0] / 255, x, y, S))
    big = pygame.Surface((S * 4, S * 4), pygame.SRCALPHA)
    pygame.draw.circle(big, (255, 255, 255, 255), (S * 2, S * 2), tr * 4)
    mask = pygame.transform.smoothscale(big, (S, S))
    tex.blit(sphere_shade(S, tr), (0, 0), special_flags=MULT)
    tex = tex.convert_alpha()
    tex.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if S != diam + 2:
        tex = pygame.transform.smoothscale(tex, (diam + 2, diam + 2))
    out = pygame.Surface((size, size), pygame.SRCALPHA)
    if not ring:
        out.blit(tex, tex.get_rect(center=(size // 2, size // 2)))
        return out
    cx, cy = size // 2, size // 2
    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    rx, ry = size * 0.48, size * 0.13
    for i, (k, a) in enumerate(((1.0, 150), (0.9, 210), (0.8, 120), (0.74, 190), (0.68, 100))):
        col = lerp_c((236, 214, 170), (160, 140, 110), i / 4)
        pygame.draw.ellipse(layer, (*col, a), (cx - rx * k, cy - ry * k, 2 * rx * k, 2 * ry * k), max(2, size // 40))
    back = layer.copy()
    back.fill((255, 255, 255, 0), (0, cy, size, size - cy), special_flags=pygame.BLEND_RGBA_MULT)
    layer.fill((255, 255, 255, 0), (0, 0, size, cy), special_flags=pygame.BLEND_RGBA_MULT)
    out.blit(back, (0, 0))
    out.blit(tex, tex.get_rect(center=(cx, cy)))
    out.blit(layer, (0, 0))
    return out


def make_asteroid(size, seed, tint=(255, 255, 255)):
    """Small lit rock sprite (lighting baked in)."""
    S = size
    c = S / 2
    rr = S * 0.42
    rng = random.Random(seed)
    N = 14
    pts = []
    for i in range(N):
        a = i / N * math.tau
        m = 0.72 + 0.28 * rng.random()
        pts.append((c + math.cos(a) * rr * m, c + math.sin(a) * rr * m))
    big = pygame.Surface((S * 3, S * 3), pygame.SRCALPHA)
    pygame.draw.polygon(big, (255, 255, 255, 255), [(x * 3, y * 3) for x, y in pts])
    mask = pygame.transform.smoothscale(big, (S, S))
    tex = noise_gray(S, S, 3, seed, 3)
    tex.fill((150, 150, 150), special_flags=MULT)
    tex.fill((95, 95, 95), special_flags=ADD)
    tex.fill(tuple(int(120 + 0.55 * (t - 120)) if t < 255 else 255 for t in tint), special_flags=MULT) if False else None
    tex.fill((int(170 * tint[0] / 255 + 40), int(160 * tint[1] / 255 + 36), int(150 * tint[2] / 255 + 32)), special_flags=MULT)
    for _ in range(3):
        cx, cy = rng.uniform(0.3, 0.7) * S, rng.uniform(0.3, 0.7) * S
        rad = max(2, int(S * rng.uniform(0.06, 0.12)))
        pygame.draw.circle(tex, (50, 46, 46), (cx, cy), rad)
        pygame.draw.arc(tex, (170, 160, 150), (cx - rad, cy - rad, 2 * rad, 2 * rad), -1.5, 0.1, 1)
    tex.blit(sphere_shade(S, rr * 1.25, ambient=(58, 58, 84)), (0, 0), special_flags=MULT)
    tex = tex.convert_alpha()
    tex.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return tex


# ------------------------------------------------------------------ ships
FLEET_TIER = 8       # the classes from here up are formations of the planet's own hulls


def make_fleet(tier, color, size, style, pal):
    """The two biggest classes. Citadel (tier 8): a flagship with its escorts under a halo. Ark (tier 9): a line of three
    flagships with escorts between them, inside a double halo. Every hull is the planet's own, so the fleet still looks like
    its planet's; drawn at twice the size and scaled down once, so the small hulls stay sharp."""
    S = size * 2
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    halo = lerp_c(color, (255, 255, 255), 0.2)
    c = S / 2

    def ring(r, a, w):
        layer = pygame.Surface((S, S), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*halo, a), (c, c), r, w)
        surf.blit(layer, (0, 0))

    def put(t, fx, fy, frac):
        spr = make_ship(t, color, max(8, int(S * frac)), style, pal)
        surf.blit(spr, spr.get_rect(center=(S * fx, S * fy)))

    surf.blit(glow(int(S * 0.5), scale_c(color, 0.35)), (0, 0), special_flags=ADD)
    if tier == FLEET_TIER:
        ring(S * 0.43, 140, max(2, S // 44))
        for fx, fy in ((0.18, 0.27), (0.18, 0.73), (0.62, 0.13), (0.62, 0.87)):
            put(1, fx, fy, 0.25)
        put(7, 0.54, 0.5, 0.66)
    else:
        ring(S * 0.45, 130, max(2, S // 50))
        for fx, fy in ((0.11, 0.5), (0.5, 0.1), (0.5, 0.9)):
            put(3, fx, fy, 0.2)
        for fx, fy in ((0.7, 0.5), (0.31, 0.27), (0.31, 0.73)):
            put(7, fx, fy, 0.37)
    return pygame.transform.smoothscale(surf, (size, size))


def make_ship(tier, color, size=40, style="classic", pal=None):
    """Ship class `tier` in `color`; Earth's classic hulls are drawn here, every other planet's in shipart.py."""
    if tier >= FLEET_TIER:
        return make_fleet(tier, color, size, style, pal)
    if style != "classic":
        import shipart
        return shipart.make(style, tier, color, size, pal)
    ss = 4
    S = size * ss
    c = S / 2
    R = S * 0.42
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    hull = lerp_c((28, 32, 46), color, 0.30)
    mid = lerp_c((52, 58, 80), color, 0.55)
    edge = lerp_c(color, (255, 255, 255), 0.35)
    hot = lerp_c(color, (255, 255, 255), 0.85)
    lw = max(2, ss)

    def P(pts):
        return [(c + x * R, c + y * R) for x, y in pts]

    def poly(pts, fill, out=edge):
        pygame.draw.polygon(surf, fill, P(pts))
        if out:
            pygame.draw.polygon(surf, out, P(pts), lw)

    def dot(x, y, rad, col):
        pygame.draw.circle(surf, col, (c + x * R, c + y * R), max(1, rad * R))

    def rect(x0, y0, x1, y1, fill, out=edge):
        poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill, out)

    if tier == 0:
        poly([(1, 0), (.1, .55), (-.7, .35), (-.45, 0), (-.7, -.35), (.1, -.55)], hull)
        poly([(.7, 0), (.1, .25), (-.2, 0), (.1, -.25)], mid, None)
        dot(.35, 0, .17, hot)
    elif tier == 1:
        rect(-.3, .6, .95, .85, mid)
        rect(-.3, -.85, .95, -.6, mid)
        poly([(.9, 0), (-.5, .5), (-.3, 0), (-.5, -.5)], hull)
        dot(.95, .72, .12, hot)
        dot(.95, -.72, .12, hot)
        dot(.2, 0, .15, hot)
    elif tier == 2:
        poly([(1, 0), (.55, .45), (-.9, .5), (-.9, -.5), (.55, -.45)], hull)
        for x in (-.75, -.4, -.05):
            rect(x, -.32, x + .28, .32, mid)
        dot(.68, 0, .13, hot)
    elif tier == 3:
        pygame.draw.ellipse(surf, hull, (c - .95 * R, c - .45 * R, 1.9 * R, .9 * R))
        pygame.draw.ellipse(surf, edge, (c - .95 * R, c - .45 * R, 1.9 * R, .9 * R), lw)
        rect(-.5, -.8, -.25, -.35, mid)
        rect(0, -.8, .25, -.35, mid)
        dot(-.38, -.85, .1, hot)
        dot(.12, -.85, .1, hot)
        dot(.55, 0, .16, hot)
    elif tier == 4:
        hexa = [(math.cos(i * math.pi / 3) * .92, math.sin(i * math.pi / 3) * .92) for i in range(6)]
        poly(hexa, hull)
        poly([(x * .6, y * .6) for x, y in hexa], mid)
        dot(0, 0, .26, hot)
    elif tier == 5:
        pygame.draw.circle(surf, edge, (c, c), .88 * R, lw * 2)
        pygame.draw.circle(surf, hull, (c, c), .78 * R, lw)
        for i in range(6):
            a = i * math.pi / 3
            pygame.draw.line(surf, mid, (c, c), (c + math.cos(a) * .85 * R, c + math.sin(a) * .85 * R), lw)
        dot(0, 0, .3, hot)
    elif tier == 6:
        poly([(1, 0), (-.3, .18), (-.8, .5), (-.55, 0), (-.8, -.5), (-.3, -.18)], hull)
        for x in (-.15, .3):
            pygame.draw.ellipse(surf, edge, (c + (x - .08) * R, c - .55 * R, .16 * R, 1.1 * R), lw)
        dot(.9, 0, .1, hot)
    elif tier == 7:
        pygame.draw.ellipse(surf, hot, (c - 1.0 * R, c - .38 * R, 2.0 * R, .76 * R), lw * 2)
        dot(0, 0, .62, (6, 6, 12))
        pygame.draw.circle(surf, edge, (c, c), .62 * R, lw)
        pygame.draw.arc(surf, hot, (c - 1.0 * R, c - .38 * R, 2.0 * R, .76 * R), 3.4, 6.0, lw * 2)
    elif tier == 8:
        star = []
        for i in range(16):
            a = i * math.pi / 8
            rad = 1.0 if i % 2 == 0 else .45
            star.append((math.cos(a) * rad, math.sin(a) * rad))
        poly(star, mid)
        dot(0, 0, .3, hot)
    elif tier == 9:
        for k, (a0, a1, rad) in enumerate([(.4, 4.6, .9), (1.2, 5.4, .62), (2.0, 6.2, .36)]):
            pygame.draw.arc(surf, edge if k % 2 == 0 else mid, (c - rad * R, c - rad * R, 2 * rad * R, 2 * rad * R),
                            a0, a1, lw * 2)
        dot(0, 0, .12, hot)
    elif tier == 10:
        for arm in range(3):
            for t in range(46):
                a = t * .22 + arm * math.tau / 3
                rad = .08 + t * .02
                dot(math.cos(a) * rad, math.sin(a) * rad, .075 + (46 - t) * .0015, lerp_c(hot, color, t / 46))
        dot(0, 0, .2, (255, 255, 255))
    else:
        poly([(1, 0), (0, .72), (-1, 0), (0, -.72)], hull)
        poly([(.55, 0), (0, .4), (-.55, 0), (0, -.4)], mid, hot)
        pygame.draw.line(surf, edge, P([(1, 0)])[0], P([(-1, 0)])[0], lw)
        pygame.draw.line(surf, edge, P([(0, .72)])[0], P([(0, -.72)])[0], lw)
        dot(0, 0, .2, (255, 255, 255))
    return pygame.transform.smoothscale(surf, (size, size))


def make_galaxy_backdrop(W, H):
    """The backdrop of the galaxy map: a deep-space star chart (dark blue-black, dense coloured stars, distant galaxies, a
    faint grid of rings and bearings) - clearly a different place from the starfield around a planet."""
    s = pygame.Surface((W, H))
    for y in range(H):
        k = y / H
        pygame.draw.line(s, (int(2 + 4 * k), int(5 + 8 * k), int(14 + 16 * k)), (0, y), (W, y))
    rng = random.Random(21)
    for _ in range(9):                                            # soft cold nebulae for depth
        x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.18, 0.4) * max(W, H)
        s.blit(glow(int(r), rng.choice([(10, 22, 44), (8, 26, 40), (18, 16, 44), (10, 30, 34)])), (x - r, y - r), special_flags=ADD)
    tints = [(255, 255, 255), (190, 210, 255), (255, 240, 200), (255, 200, 170), (170, 230, 255)]
    for _ in range(W * H // 700):                                 # a dense field of faint stars
        x, y = rng.randrange(W), rng.randrange(H)
        v = rng.choice((60, 90, 130, 180))
        t = rng.choice(tints)
        s.set_at((x, y), (v * t[0] // 255, v * t[1] // 255, v * t[2] // 255))
    for _ in range(W * H // 18000):                               # and some bright ones
        x, y = rng.randrange(W), rng.randrange(H)
        t = rng.choice(tints)
        s.blit(glow(rng.choice((4, 6, 9)), (t[0] // 2, t[1] // 2, t[2] // 2)), (x - 9, y - 9), special_flags=ADD)
        pygame.draw.circle(s, t, (x, y), 1)
    for _ in range(7):                                            # distant galaxies
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.randrange(14, 34)
        blob = glow(r, rng.choice([(60, 70, 110), (90, 70, 60), (60, 90, 100)]))
        blob = pygame.transform.rotate(pygame.transform.smoothscale(blob, (2 * r, r)), rng.uniform(0, 180))
        s.blit(blob, blob.get_rect(center=(x, y)), special_flags=ADD)
    grid = pygame.Surface((W, H), pygame.SRCALPHA)                # the star chart: rings and bearings around the galactic centre
    cx, cy = W * 0.46, H * 0.52
    for i in range(1, 9):
        rad = i * max(W, H) * 0.115
        pygame.draw.circle(grid, (70, 110, 180, 34), (cx, cy), rad, 1)
    for i in range(12):
        a = i * math.pi / 6
        pygame.draw.line(grid, (70, 110, 180, 26), (cx, cy), (cx + math.cos(a) * W, cy + math.sin(a) * W), 1)
    for x in range(0, W, 80):
        pygame.draw.line(grid, (90, 130, 200, 40), (x, 0), (x, 8), 1)
        pygame.draw.line(grid, (90, 130, 200, 40), (x, H - 8), (x, H), 1)
    for y in range(0, H, 80):
        pygame.draw.line(grid, (90, 130, 200, 40), (0, y), (8, y), 1)
        pygame.draw.line(grid, (90, 130, 200, 40), (W - 8, y), (W, y), 1)
    s.blit(grid, (0, 0))
    return s


def make_crate(size=34):
    ss = 4
    S = size * ss
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    r = pygame.Rect(S * .12, S * .22, S * .76, S * .6)
    pygame.draw.rect(s, (255, 200, 60), r, border_radius=S // 12)
    pygame.draw.rect(s, (255, 236, 150), (r.x, r.y, r.w, r.h // 3), border_radius=S // 12)
    pygame.draw.rect(s, (140, 92, 20), r, S // 22, border_radius=S // 12)
    pygame.draw.line(s, (140, 92, 20), (r.centerx, r.top), (r.centerx, r.bottom), S // 22)
    pygame.draw.line(s, (140, 92, 20), (r.left, r.centery), (r.right, r.centery), S // 22)
    pygame.draw.circle(s, (255, 255, 255), (r.centerx, r.centery), S // 16)
    return pygame.transform.smoothscale(s, (size, size))


# ------------------------------------------------------------------ backdrops
def make_background(W, H):
    s = pygame.Surface((W, H))
    for y in range(H):
        k = y / H
        pygame.draw.line(s, (int(5 + 8 * k), int(5 + 5 * k), int(16 + 20 * k)), (0, y), (W, y))
    for seed, col, wt in [(11, (130, 55, 200), 1.0), (23, (40, 120, 235), 0.9), (37, (210, 60, 120), 0.7)]:
        n = noise_gray(W // 8, H // 8, 5, seed, 2)
        n.fill((60, 60, 60), special_flags=SUB)
        n.blit(n.copy(), (0, 0), special_flags=ADD)
        n = pygame.transform.smoothscale(n, (W, H))
        n.fill(scale_c(col, wt * 0.42), special_flags=MULT)
        s.blit(n, (0, 0), special_flags=ADD)
    return s


def make_vignette(W, H):
    s = pygame.Surface((W, H))
    base = (72, 72, 90)
    s.fill(base)
    steps = 48
    for i in range(steps, 0, -1):
        t = i / steps
        col = lerp_c(base, (255, 255, 255), (1 - t) * 1.9)
        rect = pygame.Rect(0, 0, int(W * 1.55 * t), int(H * 1.55 * t))
        rect.center = (W // 2, H // 2)
        pygame.draw.ellipse(s, col, rect)
    return s


def make_panel_bg(w, h):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        k = y / h
        pygame.draw.line(s, (int(16 - 6 * k), int(18 - 6 * k), int(40 - 14 * k), 232), (0, y), (w, y))
    pygame.draw.rect(s, (70, 80, 140, 255), (0, 0, w, h), 2, border_radius=14)
    pygame.draw.rect(s, (30, 34, 66, 255), (3, 3, w - 6, h - 6), 1, border_radius=12)
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    m = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(m, (255, 255, 255, 255), (0, 0, w, h), border_radius=14)
    out.blit(s, (0, 0))
    out.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


def make_enemy(faction, size=26):
    """Hostile ship sprite for each enemy faction (pointing right, like the player's ships)."""
    ss = 4
    S = size * ss
    c = S / 2
    R = S * 0.42
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    cols = {"pirates": (235, 90, 80), "hive": (130, 220, 90), "crystal": (110, 220, 255),
            "iron": (225, 150, 80), "void": (175, 110, 255), "devourer": (255, 80, 200)}
    col = cols.get(faction, (230, 90, 90))
    dark = lerp_c((14, 12, 20), col, 0.28)
    edge = lerp_c(col, (255, 255, 255), 0.3)
    hot = lerp_c(col, (255, 255, 255), 0.85)
    lw = max(2, ss)

    def P(pts):
        return [(c + x * R, c + y * R) for x, y in pts]

    def poly(pts, fill, out=edge):
        pygame.draw.polygon(surf, fill, P(pts))
        if out:
            pygame.draw.polygon(surf, out, P(pts), lw)

    def dot(x, y, rad, color):
        pygame.draw.circle(surf, color, (c + x * R, c + y * R), max(1, rad * R))

    if faction == "pirates":        # jagged dart with side spikes
        poly([(1, 0), (.2, .35), (-.2, .9), (-.35, .3), (-.8, .2), (-.8, -.2), (-.35, -.3), (-.2, -.9), (.2, -.35)], dark)
        dot(.35, 0, .13, hot)
    elif faction == "hive":         # bug: round body, mandibles
        pygame.draw.ellipse(surf, dark, (c - .75 * R, c - .45 * R, 1.3 * R, .9 * R))
        pygame.draw.ellipse(surf, edge, (c - .75 * R, c - .45 * R, 1.3 * R, .9 * R), lw)
        poly([(.55, .15), (1, .5), (.8, .05)], dark)
        poly([(.55, -.15), (1, -.5), (.8, -.05)], dark)
        for dy in (-.5, .5):
            pygame.draw.line(surf, edge, (c - .1 * R, c + dy * .45 * R), (c - .35 * R, c + dy * R), lw)
        dot(.3, 0, .12, hot)
    elif faction == "crystal":      # shard cluster
        poly([(1, 0), (0, .5), (-.6, .2), (-.9, 0), (-.6, -.2), (0, -.5)], dark)
        poly([(.2, .3), (.1, .95), (-.3, .4)], dark)
        poly([(.2, -.3), (.1, -.95), (-.3, -.4)], dark)
        dot(.1, 0, .12, hot)
    elif faction == "iron":         # blocky battleship
        poly([(1, 0), (.5, .35), (-.9, .45), (-.9, -.45), (.5, -.35)], dark)
        for x in (-.55, -.1, .35):
            pygame.draw.rect(surf, edge, (c + x * R, c - .12 * R, .24 * R, .24 * R))
        dot(.8, 0, .1, hot)
    elif faction == "void":         # swirling crescent
        pygame.draw.arc(surf, edge, (c - R, c - R, 2 * R, 2 * R), 1.0, 5.3, lw * 2)
        pygame.draw.arc(surf, dark, (c - .65 * R, c - .65 * R, 1.3 * R, 1.3 * R), 0.5, 5.8, lw * 2)
        dot(0, 0, .22, hot)
    else:                           # devourer: a maw
        pygame.draw.circle(surf, dark, (c, c), .85 * R)
        pygame.draw.circle(surf, edge, (c, c), .85 * R, lw)
        for i in range(8):
            a = i * math.tau / 8
            x1, y1 = c + math.cos(a) * .85 * R, c + math.sin(a) * .85 * R
            x2, y2 = c + math.cos(a + .2) * .45 * R, c + math.sin(a + .2) * .45 * R
            x3, y3 = c + math.cos(a + .4) * .85 * R, c + math.sin(a + .4) * .85 * R
            pygame.draw.polygon(surf, hot, [(x1, y1), (x2, y2), (x3, y3)])
        dot(0, 0, .2, (10, 0, 12))
    return pygame.transform.smoothscale(surf, (size, size))


# ------------------------------------------------------------------ the Milky Way seen from above
MW_SPAN = 124000.0                   # light-years across the picture (the galaxy's disc is about 105,000 across)


def make_milky_way(size=1300, grid=200):
    """The galaxy painted from milkyway.density(): a bright warm bulge and bar, blue-white spiral arms with pink star-forming
    knots, dark lanes and thousands of faint stars. Meant to be blitted additively onto a dark background; one pixel is
    MW_SPAN / size light-years."""
    import milkyway
    rng = random.Random(5)
    small = pygame.Surface((grid, grid))
    dens = []
    for j in range(grid):
        row = []
        for i in range(grid):
            x = ((i + 0.5) / grid - 0.5) * MW_SPAN
            y = ((j + 0.5) / grid - 0.5) * MW_SPAN
            d = milkyway.density(x, y)
            arm, _ = milkyway.arm_strength(x, y)
            row.append((d, arm))
            R = math.hypot(x, y)
            v = 1.0 - math.exp(-1.15 * d)
            bulge = math.exp(-(R / 3800.0) ** 2)
            col = lerp_c((4, 6, 16), (96, 124, 214), min(1.0, v * 1.15))
            col = lerp_c(col, (255, 222, 160), min(1.0, bulge * 1.05 + 0.25 * milkyway.bar_strength(x, y)))
            if arm > 0.55 and R > 4000:
                col = lerp_c(col, (210, 120, 200), 0.18 * (arm - 0.55) / 0.45 * min(1.0, v * 3))
            small.set_at((i, j), col)
        dens.append(row)
    img = pygame.transform.smoothscale(small, (size, size))
    dust = noise_gray(size // 5, size // 5, 5, 77, 4)
    dust = pygame.transform.smoothscale(dust, (size, size))
    dust.fill((165, 165, 165), special_flags=MULT)               # 0..165, then +90: arms get dark lanes and bright clumps
    dust.fill((90, 90, 90), special_flags=ADD)
    img.blit(dust, (0, 0), special_flags=MULT)
    img.fill((255, 255, 255), special_flags=MULT)
    boost = pygame.Surface((size, size))
    boost.fill((70, 70, 70))
    img.blit(img.copy(), (0, 0), special_flags=ADD)              # brighten the arms (the black background stays black)
    for _ in range(26000):                                      # faint stars, thickest where the galaxy is
        i, j = rng.randrange(size), rng.randrange(size)
        d = dens[min(grid - 1, j * grid // size)][min(grid - 1, i * grid // size)][0]
        if rng.random() < min(1.0, d * 0.9) ** 1.3:
            b = rng.randint(70, 200)
            c = img.get_at((i, j))
            img.set_at((i, j), (min(255, c[0] + b), min(255, c[1] + b), min(255, c[2] + b)))
    fade = pygame.Surface((64, 64))                              # a round fade-out so the picture has no visible edge
    for j in range(64):
        for i in range(64):
            r = math.hypot(i - 31.5, j - 31.5) / 31.5
            v = 1.0 if r < 0.78 else max(0.0, 1.0 - (r - 0.78) / 0.2)
            fade.set_at((i, j), (int(255 * v),) * 3)
    img.blit(pygame.transform.smoothscale(fade, (size, size)), (0, 0), special_flags=MULT)
    return img
