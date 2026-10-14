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


@lru_cache(maxsize=None)
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
    if kind == "proxima":
        if v > 0.5:
            return lerp_c((100, 26, 18), (210, 84, 40), v2)
        return lerp_c((16, 100, 116), (60, 190, 170), v2)
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
def make_ship(tier, color, size=40):
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
