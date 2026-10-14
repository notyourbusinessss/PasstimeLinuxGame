"""Procedural ship art: every planet's fleet is drawn in its own design language.

Earth keeps the classic hulls (gfx.make_ship). Every other planet has a family of eight ships (Drone, Rig, Barge, Refinery,
Foundry, Swarm, Tap, Engine) built from its own shapes and its own colours - landers on legs, wheeled rovers, airships,
sun-shields, tumbling rocks, striped storm hulls, ringed discs, crystals, deep-sea creatures, ice sleds, living spores -
so a fleet can be told apart from another planet's at a glance. `beam()` draws each family's mining laser.

Ships point to the right (+x); shapes are described in units of the hull radius, roughly -1..1.
"""
import math
import random

import pygame

from gfx import lerp_c, scale_c

SS = 4                                   # supersampling
HULL = object()                          # "fill with the hull colour" (a fill of None means no fill at all)


class Pen:
    """Draws in hull-radius units onto a supersampled surface."""

    def __init__(self, size, pal, acc):
        self.S = S = size * SS
        self.c = S / 2
        self.R = S * 0.40
        self.surf = pygame.Surface((S, S), pygame.SRCALPHA)
        self.hull, self.mid, self.trim, self.glow = pal
        self.acc = acc                                   # the class colour (a small accent on every hull)
        self.dark = scale_c(pal[1], 0.35)
        self.lw = max(2, SS)

    def p(self, x, y):
        return (self.c + x * self.R, self.c + y * self.R)

    def poly(self, pts, fill=HULL, out=True):
        fill = self.hull if fill is HULL else fill
        q = [self.p(x, y) for x, y in pts]
        if fill:
            pygame.draw.polygon(self.surf, fill, q)
        if out:
            pygame.draw.polygon(self.surf, self.trim if out is True else out, q, self.lw)

    def ellpts(self, cx, cy, rx, ry, rot=0.0, a0=0.0, a1=math.tau, n=40):
        cr, sr = math.cos(rot), math.sin(rot)
        out = []
        for k in range(n + 1):
            a = a0 + (a1 - a0) * k / n
            x, y = math.cos(a) * rx, math.sin(a) * ry
            out.append((cx + x * cr - y * sr, cy + x * sr + y * cr))
        return out

    def ell(self, cx, cy, rx, ry, fill=HULL, out=True, rot=0.0):
        self.poly(self.ellpts(cx, cy, rx, ry, rot), fill, out)

    def circ(self, cx, cy, r, fill=HULL, out=True):
        fill = self.hull if fill is HULL else fill
        c = self.p(cx, cy)
        if fill:
            pygame.draw.circle(self.surf, fill, c, max(1.0, r * self.R))
        if out:
            pygame.draw.circle(self.surf, self.trim if out is True else out, c, max(1.0, r * self.R), self.lw)

    def rect(self, x0, y0, x1, y1, fill=HULL, out=True):
        self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill, out)

    def line(self, a, b, col=None, w=1.0):
        pygame.draw.line(self.surf, self.trim if col is None else col, self.p(*a), self.p(*b), max(1, int(self.lw * w / 2)))

    def lines(self, pts, col=None, w=1.0):
        pygame.draw.lines(self.surf, self.trim if col is None else col, False, [self.p(x, y) for x, y in pts],
                          max(1, int(self.lw * w / 2)))

    def arc(self, cx, cy, rx, ry, a0, a1, col=None, w=1.0, rot=0.0):
        self.lines(self.ellpts(cx, cy, rx, ry, rot, a0, a1, 28), col, w)

    def spot(self, x, y, r=.12, col=None):
        col = self.glow if col is None else col
        self.circ(x, y, r * 1.7, lerp_c(col, (0, 0, 0), .6), None)
        self.circ(x, y, r, col, None)
        self.circ(x, y, r * .45, (255, 255, 255), None)


def _rock(d, cx, cy, r, seed, fill=None, out=True):
    rng = random.Random(seed)
    n = 9
    pts = [(cx + math.cos(k / n * math.tau) * r * (.72 + .28 * rng.random()),
            cy + math.sin(k / n * math.tau) * r * (.72 + .28 * rng.random())) for k in range(n)]
    d.poly(pts, d.hull if fill is None else fill, out)
    for _ in range(2):
        d.circ(cx + rng.uniform(-.4, .4) * r, cy + rng.uniform(-.4, .4) * r, r * .16, d.mid, None)


# ------------------------------------------------------------------ Moon: landers on spindly legs
def lander(d, t):
    def legs(n, body, reach, off=.5):
        for k in range(n):
            a = math.tau * (k + off) / n
            ex, ey = math.cos(a) * reach, math.sin(a) * reach
            d.line((math.cos(a) * body, math.sin(a) * body), (ex, ey), d.trim, 1.7)
            d.circ(ex, ey, .1, d.mid)
    if t == 0:
        legs(4, .3, .85)
        d.circ(0, 0, .5)
        d.circ(.1, 0, .2, d.mid)
        d.spot(.32, 0, .1)
    elif t == 1:
        legs(4, .3, .8)
        d.line((.2, 0), (.85, 0), d.trim, 3)
        d.poly([(.8, -.2), (1.12, 0), (.8, .2)], d.acc)
        d.circ(-.1, 0, .44)
        d.circ(-.15, 0, .18, d.mid)
    elif t == 2:
        legs(4, .4, .95)
        d.rect(-.7, -.42, .62, .42)
        for x in (-.42, 0, .42):
            d.circ(x, 0, .21, d.mid)
        d.spot(.55, 0, .08)
    elif t == 3:
        legs(4, .3, .85)
        d.circ(-.05, 0, .52)
        d.circ(-.05, 0, .3, (255, 150, 60), d.trim)
        d.circ(.5, .3, .12, d.mid)
        d.circ(.5, -.3, .12, d.mid)
    elif t == 4:
        legs(6, .6, 1.02, 0)
        d.circ(0, 0, .8)
        for x, y, r in ((.25, -.2, .3), (-.3, .25, .26), (.3, .42, .14), (-.35, -.4, .12)):
            d.circ(x, y, r, d.mid)
            d.arc(x, y, r, r, 3.5, 5.9, d.trim, 1)
        d.circ(0, 0, .12, d.glow, None)
        for k in range(6):
            d.circ(math.cos(k * math.pi / 3 + .52) * .8, math.sin(k * math.pi / 3 + .52) * .8, .06, d.acc, None)
    elif t == 5:
        for x, y in ((0, 0), (.55, .5), (.55, -.5), (-.5, .52), (-.5, -.52)):
            d.line((x, y), (x + .26, y + .26), d.trim, 1)
            d.line((x, y), (x - .26, y + .26), d.trim, 1)
            d.circ(x, y, .24)
            d.circ(x, y, .09, d.acc, None)
    elif t == 6:
        for a in (2.3, 3.14, 3.98):
            d.line((-.2, 0), (-.2 + math.cos(a) * .7, math.sin(a) * .8), d.trim, 1.6)
        d.line((-.25, 0), (.35, 0), d.trim, 3)
        d.ell(.45, 0, .16, .82, d.mid)
        d.spot(.35, 0, .1)
        d.circ(-.2, 0, .2)
    else:
        d.arc(0, 0, 1.0, .5, 0, math.tau, d.trim, 3)
        d.circ(0, 0, .5, d.dark, d.trim)
        d.circ(0, .88, .15, d.mid)
        d.circ(0, -.88, .15, d.mid)
        d.arc(0, 0, .75, .75, -1.0, 1.0, d.glow, 2)
        d.spot(0, 0, .15)


# ------------------------------------------------------------------ Mars: wheeled rovers
def rover(d, t):
    tire = (48, 38, 42)

    def wheel(x, y, w=.27, h=.14):
        d.rect(x - w, y - h, x + w, y + h, tire, d.mid)
    if t == 0:
        for x in (-.4, .4):
            for y in (-.5, .5):
                wheel(x, y, .24, .13)
        d.rect(-.6, -.34, .6, .34)
        d.rect(-.3, -.2, .25, .2, d.mid, None)
        d.line((-.4, -.3), (-.6, -.8), d.trim, 1)
        d.spot(.52, 0, .09)
    elif t == 1:
        for x in (-.4, .4):
            for y in (-.54, .54):
                wheel(x, y)
        d.rect(-.65, -.36, .5, .36)
        d.line((.4, -.2), (.82, -.28), d.trim, 2)
        d.line((.4, .2), (.82, .28), d.trim, 2)
        d.poly([(.8, -.42), (1.12, -.28), (.8, -.14)], d.acc)
        d.poly([(.8, .42), (1.12, .28), (.8, .14)], d.acc)
        d.circ(-.2, 0, .18, d.mid)
    elif t == 2:
        for x in (-.7, 0, .7):
            for y in (-.62, .62):
                wheel(x, y)
        d.rect(-.95, -.46, .95, .46)
        for x in (-.7, -.2, .3):
            d.rect(x, -.32, x + .38, .32, d.mid)
        d.spot(.84, 0, .07)
    elif t == 3:
        for x in (-.5, 0, .5):
            for y in (-.64, .64):
                wheel(x, y, .24, .13)
        d.rect(-.8, -.44, .8, .44)
        d.circ(-.1, 0, .36, d.mid)
        d.circ(-.1, 0, .2, (255, 140, 50), None)
        d.circ(.5, 0, .1, d.glow, None)
        for k, x in enumerate((-.68, -.9)):
            d.circ(x, .08 * (-1) ** k, .08 + .02 * k, scale_c(d.hull, .6), None)
    elif t == 4:
        for x in (-.64, .64):
            for y in (-.64, .64):
                d.rect(x - .32, y - .22, x + .32, y + .22, tire, d.mid)
        d.rect(-.78, -.78, .78, .78)
        d.poly([(math.cos(k * math.pi / 3) * .5, math.sin(k * math.pi / 3) * .5) for k in range(6)], d.mid)
        d.circ(0, 0, .22, (255, 140, 50), d.trim)
        d.circ(0, 0, .08, (255, 255, 255), None)
    elif t == 5:
        for x, y in ((0, 0), (.6, .52), (.6, -.52), (-.55, .52), (-.55, -.52)):
            d.rect(x - .3, y - .06, x + .3, y + .06, tire, None)
            d.rect(x - .24, y - .2, x + .24, y + .2)
            d.circ(x + .1, y, .06, d.acc, None)
        d.arc(0, 0, .95, .8, .3, 1.2, d.glow, 1)
        d.arc(0, 0, .95, .8, 3.4, 4.3, d.glow, 1)
    elif t == 6:
        for x, y in ((-.6, -.8), (-.6, .8), (.6, -.8), (.6, .8)):
            d.line((0, 0), (x, y), d.trim, 2.4)
            d.rect(x - .2, y - .08, x + .2, y + .08, tire, d.mid)
        d.poly([(.55, 0), (-.4, -.35), (-.4, .35)], d.mid)
        d.line((.1, 0), (.95, 0), d.trim, 3)
        d.poly([(.9, -.12), (1.15, 0), (.9, .12)], d.acc)
        d.circ(-.1, 0, .3)
        d.circ(-.1, 0, .12, d.glow, None)
    else:
        for x in (-.6, .6):
            for y in (-.74, .74):
                d.rect(x - .3, y - .17, x + .3, y + .17, tire, d.mid)
        d.rect(-.84, -.62, .84, .62)
        d.circ(0, 0, .5, d.dark, d.trim)
        d.arc(0, 0, .36, .36, .5, 5.8, d.glow, 3)
        d.spot(0, 0, .13)
        d.line((.5, 0), (.84, 0), d.trim, 2)


# ------------------------------------------------------------------ Venus: airships and balloons
def airship(d, t):
    def fins(x, s=1.0):
        d.poly([(x, 0), (x - .3 * s, -.5 * s), (x - .05 * s, 0)], d.mid)
        d.poly([(x, 0), (x - .3 * s, .5 * s), (x - .05 * s, 0)], d.mid)

    def envelope(cx, cy, rx, ry, seams=3):
        d.ell(cx, cy, rx, ry, d.hull)
        for k in range(1, seams + 1):
            xx = cx - rx + 2 * rx * k / (seams + 1)
            hy = ry * math.sqrt(max(0.0, 1 - ((xx - cx) / rx) ** 2))
            d.line((xx, cy - hy), (xx, cy + hy), d.mid, 1)
    if t == 0:
        fins(-.65)
        envelope(.05, 0, .85, .42)
        d.rect(-.05, -.1, .3, .1, d.dark, d.trim)
    elif t == 1:
        fins(-.6)
        envelope(-.1, 0, .72, .38)
        d.line((.55, 0), (1.05, 0), d.trim, 3)
        d.spot(1.05, 0, .09)
        d.rect(-.3, -.08, .05, .08, d.dark, d.trim)
    elif t == 2:
        for k, x in enumerate((-.52, 0, .52)):
            envelope(x, 0, .5, .42, 2)
        d.rect(-.72, -.12, .72, .12, d.dark, d.trim)
        fins(-.95, .8)
    elif t == 3:
        fins(-.7)
        envelope(0, 0, .88, .5)
        for x in (-.3, .15):
            d.rect(x, -.5, x + .16, -.9, d.mid)
            d.circ(x + .08, -.98, .1, scale_c(d.hull, .7), None)
        d.circ(.45, 0, .16, (255, 150, 60), None)
    elif t == 4:
        d.circ(0, 0, 1.0)
        d.arc(0, 0, 1.0, .38, 0, math.tau, d.mid, 1.4)
        d.arc(0, 0, .38, 1.0, 0, math.tau, d.mid, 1.4)
        d.circ(0, 0, .42, d.dark, d.trim)
        d.circ(0, 0, .16, d.glow, None)
    elif t == 5:
        for x, y, r in ((0, 0, .36), (.5, .52, .3), (.5, -.52, .3), (-.5, .55, .28), (-.5, -.55, .28)):
            d.line((x, y), (0, 0) if r < .36 else (x - .1, y), d.mid, 1)
            d.ell(x, y, r * 1.2, r)
            d.circ(x + .05, y, .06, d.acc, None)
    elif t == 6:
        d.ell(-.15, 0, .85, .26)
        d.line((.3, 0), (.95, 0), d.trim, 1.5)
        d.circ(1.0, 0, .12, d.mid)
        d.spot(1.0, 0, .08)
        d.line((-.45, -.2), (-.45, .2), d.mid, 1)
        d.line((0, -.24), (0, .24), d.mid, 1)
        fins(-.85, .8)
    else:
        d.circ(0, 0, .95, d.hull)
        for k in range(8):
            a = k * math.tau / 8
            d.line((math.cos(a) * .55, math.sin(a) * .55), (math.cos(a) * .95, math.sin(a) * .95), d.mid, 2.5)
        d.circ(0, 0, .6, d.dark, d.trim)
        d.circ(0, 0, .3, d.mid, d.glow)
        d.spot(0, 0, .12)


# ------------------------------------------------------------------ Mercury: sun-shields and solar wings
def solar(d, t):
    gold = d.trim
    panel = (34, 54, 120)

    def wing(x0, x1, y0, y1):
        d.rect(x0, y0, x1, y1, panel, gold)
        d.line((x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2), gold, .8)
        d.line(((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1), gold, .8)
    if t == 0:
        d.ell(-.1, 0, .6, .22, d.hull)
        d.poly(d.ellpts(.45, 0, .28, .8, 0, -math.pi / 2, math.pi / 2, 20), d.mid, gold)
        d.spot(-.5, 0, .09)
    elif t == 1:
        wing(-.45, .15, -1.05, -.2)
        wing(-.45, .15, .2, 1.05)
        d.ell(.1, 0, .72, .2, d.hull)
        d.line((.6, 0), (1.1, 0), gold, 2.5)
        d.spot(1.05, 0, .08)
    elif t == 2:
        d.line((-1, 0), (1, 0), d.hull, 3)
        for x in (-.7, 0, .7):
            wing(x - .3, x + .3, -.72, .72)
        d.circ(0, 0, .15, d.dark, gold)
    elif t == 3:
        for k in range(10):
            a = k * math.tau / 10
            d.poly([(math.cos(a - .12) * .62, math.sin(a - .12) * .62), (math.cos(a) * 1.05, math.sin(a) * 1.05),
                    (math.cos(a + .12) * .62, math.sin(a + .12) * .62)], d.mid, gold)
        d.circ(0, 0, .6, (255, 214, 120), gold)
        d.circ(0, 0, .34, (255, 250, 220), None)
    elif t == 4:
        d.circ(0, 0, 1.0, d.dark, gold)
        for r in (.78, .56):
            d.circ(0, 0, r, None, gold)
        for k in range(8):
            a = k * math.tau / 8
            d.line((math.cos(a) * .3, math.sin(a) * .3), (math.cos(a) * .95, math.sin(a) * .95), gold, 1)
        d.circ(0, 0, .3, (255, 214, 120), gold)
        d.spot(0, 0, .15, (255, 245, 200))
    elif t == 5:
        d.circ(0, 0, .16, (255, 245, 200), None)
        for k in range(7):
            a = k * math.tau / 7 + .3
            r = .62 + .34 * (k % 2)
            x, y = math.cos(a) * r, math.sin(a) * r * .9
            d.poly([(x + .22, y), (x, y + .13), (x - .22, y), (x, y - .13)], panel, gold)
    elif t == 6:
        d.poly([(1.1, 0), (-.5, -.16), (-.9, 0), (-.5, .16)], d.hull)
        d.arc(-.15, -.5, .5, .5, 3.4, 6.1, gold, 2)
        d.arc(-.15, .5, .5, .5, .3, 3.0, gold, 2)
        d.arc(.45, -.35, .35, .35, 3.4, 6.1, gold, 1.5)
        d.arc(.45, .35, .35, .35, .3, 3.0, gold, 1.5)
        d.spot(1.0, 0, .08)
    else:
        for k in range(16):
            a = k * math.tau / 16
            r1 = 1.1 if k % 2 == 0 else .85
            d.line((math.cos(a) * .6, math.sin(a) * .6), (math.cos(a) * r1, math.sin(a) * r1), (255, 190, 70), 1.3)
        d.circ(0, 0, .62, (255, 230, 150), gold)
        d.circ(0, 0, .45, d.dark, None)
        d.spot(0, 0, .13, (255, 245, 200))


# ------------------------------------------------------------------ Ceres: tumbling rocks with claws and drills
def rock(d, t):
    ice = d.glow
    if t == 0:
        d.poly([(.5, -.45), (1.1, -.2), (.7, -.05)], d.mid)
        d.poly([(.5, .45), (1.1, .2), (.7, .05)], d.mid)
        _rock(d, -.1, 0, .72, 3)
        d.spot(-.7, .1, .08, ice)
    elif t == 1:
        _rock(d, -.2, 0, .7, 5)
        d.poly([(.45, -.2), (1.15, 0), (.45, .2)], ice)
        d.line((.45, 0), (1.1, 0), (255, 255, 255), .8)
        d.spot(-.7, -.1, .07)
    elif t == 2:
        d.line((-.8, 0), (.8, 0), d.trim, 1)
        _rock(d, -.62, 0, .45, 11)
        _rock(d, -.0, .04, .38, 12)
        _rock(d, .58, 0, .28, 13)
        d.poly([(.8, -.12), (1.12, 0), (.8, .12)], d.acc)
    elif t == 3:
        _rock(d, 0, 0, .9, 21)
        d.line((-.4, .3), (.45, -.2), (255, 140, 50), 2.5)
        for x, y in ((-.3, -.62), (.2, -.7)):
            d.rect(x - .09, y - .3, x + .09, y + .08, d.mid)
            d.circ(x, y - .4, .1, scale_c(d.hull, .7), None)
        d.spot(.65, .2, .09)
    elif t == 4:
        _rock(d, 0, 0, 1.0, 31)
        d.circ(0, 0, .55, d.dark, d.trim)
        for k in range(6):
            a = k * math.tau / 6
            d.circ(math.cos(a) * .72, math.sin(a) * .72, .07, d.acc, None)
        d.circ(0, 0, .22, d.glow, None)
    elif t == 5:
        for k, (x, y, r) in enumerate(((.0, .0, .2), (.6, .4, .17), (.7, -.35, .15), (-.55, .45, .18), (-.6, -.4, .16),
                                       (.15, .75, .12), (.1, -.78, .13))):
            _rock(d, x, y, r * 1.35, 40 + k)
        d.spot(0, 0, .07)
    elif t == 6:
        for k, a in enumerate((.6, 2.5, 3.8, 5.6)):
            x, y = math.cos(a) * .88, math.sin(a) * .88
            d.line((0, 0), (x, y), d.trim, 1.2)
            _rock(d, x, y, .2, 50 + k)
        _rock(d, 0, 0, .45, 60)
        d.spot(0, 0, .13, ice)
    else:
        for k in range(7):
            a = k * math.tau / 7
            _rock(d, math.cos(a) * .82, math.sin(a) * .82, .17, 70 + k)
        d.circ(0, 0, .52, (4, 4, 10), d.glow)
        d.arc(0, 0, .52, .52, 3.4, 5.9, (255, 255, 255), 2)


# ------------------------------------------------------------------ Jupiter: striped storm hulls
def storm(d, t):
    dark, cream, rust = d.mid, d.trim, (196, 98, 60)

    def band(cx, cy, rx, ry, y0, y1, col):
        def half(y):
            return rx * math.sqrt(max(0.0, 1 - ((y - cy) / ry) ** 2))
        ys = [y0 + (y1 - y0) * k / 5 for k in range(6)]
        d.poly([(cx - half(y), y) for y in ys] + [(cx + half(y), y) for y in reversed(ys)], col, None)

    def banded(cx, cy, rx, ry, bands=3):
        d.ell(cx, cy, rx, ry, cream, None)
        for k in range(bands):
            y0 = cy - ry + 2 * ry * (k + .25) / bands
            y1 = cy - ry + 2 * ry * (k + .75) / bands
            band(cx, cy, rx, ry, y0, y1, dark if k % 2 == 0 else rust)
        d.ell(cx, cy, rx, ry, None, d.trim)

    def swirl(cx, cy, r, col=None):
        for k in range(3):
            d.arc(cx, cy, r * (1 - .27 * k), r * (1 - .27 * k) * .8, .5 + k, 4.9 + k, col or d.glow, 1.8)
    if t == 0:
        banded(0, 0, .85, .45, 3)
        d.ell(.35, .1, .16, .1, (232, 70, 50), (255, 200, 160))
    elif t == 1:
        banded(-.15, 0, .75, .45, 3)
        d.lines([(.55, -.15), (.75, 0), (.65, .05), (.95, .22), (.8, .2), (1.1, .38)], (255, 240, 150), 2.4)
        d.lines([(.55, .15), (.75, 0), (.65, -.05), (.95, -.22), (.8, -.2), (1.1, -.38)], (255, 240, 150), 2.4)
    elif t == 2:
        banded(0, 0, .95, .6, 5)
        for y in (-.78, .78):
            banded(.1, y, .5, .18, 1)
    elif t == 3:
        banded(0, 0, .9, .55, 3)
        d.ell(.18, 0, .46, .36, (232, 70, 50), (255, 200, 160))
        swirl(.18, 0, .3, (255, 240, 200))
    elif t == 4:
        d.circ(0, 0, .98, cream, None)
        for k in range(4):
            band(0, 0, .98, .98, -.92 + k * .46, -.92 + k * .46 + .32, dark if k % 2 == 0 else rust)
        d.circ(0, 0, .98, None, d.trim)
        d.ell(.18, .28, .44, .27, (226, 66, 46), (255, 210, 170))
        swirl(.18, .28, .3, (255, 235, 200))
    elif t == 5:
        banded(0, 0, .34, .34, 3)
        for x, y, r in ((.75, .1, .16), (.38, .62, .12), (-.5, .62, .2), (-.75, -.15, .14), (.1, -.75, .15)):
            d.circ(x, y, r, rust)
            d.circ(x - r * .25, y - r * .25, r * .3, cream, None)
        d.arc(0, 0, .8, .8, 0, math.tau, d.glow, .7)
    elif t == 6:
        banded(0, 0, .3, .3, 3)
        for k in (1, 2, 3):
            d.arc(-.1 + k * .05, 0, .3 + .26 * k, .5 + .22 * k, -math.pi / 2, math.pi / 2, d.glow, 1.8)
            d.arc(.1 - k * .05, 0, .3 + .26 * k, .5 + .22 * k, math.pi / 2, 3 * math.pi / 2, d.glow, 1.8)
        d.spot(0, 0, .1)
    else:
        d.circ(0, 0, .78, cream, None)
        for k in range(5):
            band(0, 0, .78, .78, -.74 + k * .3, -.74 + k * .3 + .2, dark if k % 2 == 0 else rust)
        d.circ(0, 0, .78, None, d.trim)
        d.arc(0, 0, 1.0, 1.0, 0, math.tau, (255, 130, 60), 3)
        d.arc(0, 0, .9, .9, 0, math.tau, (255, 210, 120), 1)
        d.spot(0, 0, .14)


# ------------------------------------------------------------------ Saturn: discs and tilted rings
def ringed(d, t):
    tilt = -.3

    def ring(cx, cy, rx, ry, w=1.4, col=None, front=True):
        d.arc(cx, cy, rx, ry, math.pi if front is False else 0, math.tau if front is False else math.pi, col or d.trim, w, tilt)
    if t == 0:
        ring(0, 0, 1.0, .36, 2, d.mid, False)
        d.circ(0, 0, .42)
        ring(0, 0, 1.0, .36, 2, d.trim)
    elif t == 1:
        ring(-.1, 0, .9, .3, 2, d.mid, False)
        d.circ(-.1, 0, .38)
        ring(-.1, 0, .9, .3, 2, d.trim)
        d.line((.2, 0), (1.0, 0), d.glow, 1.4)
        d.spot(1.05, 0, .08)
    elif t == 2:
        for x in (-.55, 0, .55):
            d.circ(x, 0, .32 - abs(x) * .1)
        ring(0, 0, 1.12, .3, 2.4, d.trim)
        d.line((.7, 0), (1.05, 0), d.acc, 2)
    elif t == 3:
        ring(0, 0, 1.05, .38, 2, d.mid, False)
        d.circ(0, 0, .5, d.hull)
        d.arc(0, 0, .5, .5, 0, math.tau, d.mid, 1)
        ring(0, 0, 1.05, .38, 2, d.trim)
        for x, y in ((.6, -.5), (-.55, .5), (.8, .4), (-.75, -.45)):
            d.poly([(x, y - .14), (x + .09, y), (x, y + .14), (x - .09, y)], (255, 255, 255), None)
    elif t == 4:
        for k, r in enumerate((1.1, .85, .6)):
            ring(0, 0, r, r * .38, 2, d.mid, False)
        d.circ(0, 0, .42, d.hull)
        for k, r in enumerate((1.1, .85, .6)):
            ring(0, 0, r, r * .38, 2)
        d.spot(0, 0, .12)
    elif t == 5:
        d.arc(0, 0, 1.0, .36, 0, math.tau, d.mid, .8, tilt)
        for k in range(9):
            a = k * math.tau / 9
            x, y = math.cos(a) * 1.0, math.sin(a) * .36
            cr, sr = math.cos(tilt), math.sin(tilt)
            d.circ(x * cr - y * sr, x * sr + y * cr, .1, d.hull if k % 2 else d.glow)
    elif t == 6:
        ring(0, 0, 1.0, .34, 1.6, d.mid, False)
        d.circ(0, 0, .45, (236, 160, 80))
        d.arc(0, 0, .45, .45, 3.7, 5.7, (255, 210, 140), 2)
        ring(0, 0, 1.0, .34, 1.6)
        d.line((.2, .1), (.2, .85), d.trim, 1.4)
        d.circ(.2, .9, .1, d.mid)
    else:
        ring(0, 0, 1.12, .4, 2, d.mid, False)
        d.poly([(math.cos(k * math.pi / 3) * .6, math.sin(k * math.pi / 3) * .6) for k in range(6)], d.mid)
        d.poly([(math.cos(k * math.pi / 3) * .38, math.sin(k * math.pi / 3) * .38) for k in range(6)], d.hull)
        d.spot(0, 0, .12)
        ring(0, 0, 1.12, .4, 2.4)


# ------------------------------------------------------------------ Uranus: crystals
def crystal(d, t):
    def shard(cx, cy, length, width, rot=0.0, facets=True):
        pts = [(-length, 0), (-length * .45, width), (length * .5, width), (length, 0), (length * .5, -width),
               (-length * .45, -width)]
        cr, sr = math.cos(rot), math.sin(rot)
        pts = [(cx + x * cr - y * sr, cy + x * sr + y * cr) for x, y in pts]
        d.poly(pts, d.hull)
        if facets:
            a, b = pts[1], pts[2]
            d.poly([pts[0], pts[1], pts[2], pts[3]], d.mid, None)
            d.line(pts[0], pts[3], d.trim, .7)
            d.line(pts[1], pts[2], d.trim, .7)
            d.poly(pts, None, d.trim)
    if t == 0:
        shard(0, 0, .95, .26)
        d.spot(.4, 0, .07, (255, 255, 255))
    elif t == 1:
        shard(-.1, 0, .85, .26)
        shard(.3, -.5, .45, .13, -.5)
        shard(.3, .5, .45, .13, .5)
    elif t == 2:
        shard(.1, 0, 1.0, .22)
        shard(-.1, -.45, .8, .16)
        shard(-.1, .45, .8, .16)
        d.line((-.8, -.3), (-.8, .3), d.mid, 1)
    elif t == 3:
        for k in range(5):
            shard(math.cos(k * math.tau / 5) * .18, math.sin(k * math.tau / 5) * .18, .85, .2, k * math.tau / 5)
        d.spot(0, 0, .12, (255, 255, 255))
    elif t == 4:
        for k in range(6):
            a = k * math.pi / 3
            d.poly([(math.cos(a - .18) * .7, math.sin(a - .18) * .7), (math.cos(a) * 1.08, math.sin(a) * 1.08),
                    (math.cos(a + .18) * .7, math.sin(a + .18) * .7)], d.mid)
        d.poly([(math.cos(k * math.pi / 3) * .78, math.sin(k * math.pi / 3) * .78) for k in range(6)])
        d.poly([(math.cos(k * math.pi / 3) * .45, math.sin(k * math.pi / 3) * .45) for k in range(6)], d.mid)
        d.spot(0, 0, .13, (255, 255, 255))
    elif t == 5:
        for k, (x, y, s) in enumerate(((0, 0, .3), (.2, .6, .22), (.2, -.6, .22), (-.4, .45, .2), (-.4, -.45, .2),
                                       (.6, .25, .17), (.6, -.25, .17), (-.7, 0, .17))):
            shard(x, y, s, s * .42, math.pi / 2, False)
    elif t == 6:
        shard(0, 0, 1.0, .18, -.7)
        d.arc(-.1, .1, .5, .22, 0, math.tau, d.glow, 1.4, -.7 + math.pi / 2)
        d.spot(.7, -.6, .08, (255, 255, 255))
        d.line((-.3, .35), (-.55, .55), d.trim, 1)
    else:
        shard(0, 0, 1.08, .4, .78)
        shard(0, 0, 1.08, .4, -.78)
        d.circ(0, 0, .3, (255, 255, 255), d.glow)
        d.spot(0, 0, .12, (255, 255, 255))


# ------------------------------------------------------------------ Neptune: deep-sea creatures
def deep(d, t):
    glow = d.glow

    def fish(cx, cy, s, eye=True):
        d.poly([(cx + s, cy), (cx + .55 * s, cy - .42 * s), (cx - .4 * s, cy - .34 * s), (cx - .6 * s, cy),
                (cx - .4 * s, cy + .34 * s), (cx + .55 * s, cy + .42 * s)], d.hull)
        d.poly([(cx - .5 * s, cy), (cx - 1.1 * s, cy - .42 * s), (cx - .95 * s, cy), (cx - 1.1 * s, cy + .42 * s)], d.mid)
        d.poly([(cx + .1 * s, cy - .36 * s), (cx - .2 * s, cy - .75 * s), (cx - .35 * s, cy - .32 * s)], d.mid)
        if eye:
            d.circ(cx + .55 * s, cy - .08 * s, .08 * s + .02, glow, None)
    if t == 0:
        fish(.15, 0, .75)
    elif t == 1:
        fish(-.2, 0, .6)
        d.lines([(.4, -.1), (.7, -.4), (1.0, -.25)], d.trim, 1.4)
        d.spot(1.0, -.25, .09)
    elif t == 2:
        d.poly([(.9, 0), (.2, -.95), (-.3, -.7), (-.35, -.2), (-.95, 0), (-.35, .2), (-.3, .7), (.2, .95)], d.hull)
        d.line((.85, 0), (-.9, 0), d.mid, 1.5)
        d.lines([(.2, -.9), (-.05, -.4)], d.mid, 1)
        d.lines([(.2, .9), (-.05, .4)], d.mid, 1)
        d.circ(.55, -.14, .06, glow, None)
        d.circ(.55, .14, .06, glow, None)
    elif t == 3:
        d.circ(0, 0, .85, d.hull)
        d.circ(0, 0, .85, None, d.trim)
        for x, y, r in ((0, 0, .3), (.45, -.3, .17), (-.4, .35, .2), (.4, .4, .13), (-.45, -.38, .12)):
            d.poly([(x + r * 1.3, y), (x, y + r), (x - r * 1.3, y), (x, y - r)], (150, 210, 255), d.trim)
    elif t == 4:
        d.circ(-.4, 0, .5)
        d.rect(-.05, -.07, .6, .07, d.mid)
        for y in (-.62, 0, .62):
            d.line((.55, y), (1.1, y), d.trim, 2.2)
            d.poly([(1.05, y - .1), (1.25, y), (1.05, y + .1)], d.acc)
        d.line((.55, -.62), (.55, .62), d.trim, 2.2)
        d.circ(-.4, 0, .2, d.dark, glow)
        d.spot(-.4, 0, .1)
    elif t == 5:
        for x, y, s in ((.2, 0, .3), (-.3, .45, .26), (-.3, -.45, .26), (.35, .6, .2), (.35, -.6, .2), (-.75, 0, .22)):
            fish(x, y, s, False)
    elif t == 6:
        for k in range(6):
            y = -.5 + k * .2
            d.lines([(-.2, y * .6), (-.55, y), (-.8, y * 1.25 + .15 * math.sin(k)), (-1.05, y * 1.4)], d.mid, 2)
        d.poly([(.95, 0), (.3, -.42), (-.4, -.32), (-.4, .32), (.3, .42)], d.hull)
        d.circ(.45, -.16, .07, glow, None)
        d.circ(.45, .16, .07, glow, None)
        d.line((.1, 0), (-.3, 0), d.mid, 1)
    else:
        d.circ(0, 0, .95, (4, 6, 22), d.trim)
        d.circ(0, 0, .75, None, d.mid)
        for k, (x, y) in enumerate(((.3, -.4), (-.4, -.3), (.1, .5), (-.2, .1), (.5, .2), (-.55, .45))):
            d.circ(x, y, .05, glow, None)
        d.arc(0, 0, 1.12, .4, .3, math.tau - .3, glow, 1.6, .5)
        d.spot(0, 0, .12, (160, 200, 255))


# ------------------------------------------------------------------ Pluto: ice sleds and snow
def sled(d, t):
    def runners(x0, x1, y):
        for s in (-1, 1):
            d.lines([(x0, s * y), (x1 - .15, s * y), (x1, s * (y - .14))], d.trim, 2)

    def heart(cx, cy, s, fill, out=True):
        pts = []
        for k in range(40):
            a = k / 40 * math.tau
            hx = 16 * math.sin(a) ** 3
            hy = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)
            pts.append((cx - hy / 17 * s, cy + hx / 17 * s))
        d.poly(pts, fill, out)

    def flake(x, y, r):
        for k in range(3):
            a = k * math.pi / 3
            d.line((x - math.cos(a) * r, y - math.sin(a) * r), (x + math.cos(a) * r, y + math.sin(a) * r), d.trim, 1)
    if t == 0:
        runners(-.7, .8, .42)
        d.circ(0, 0, .5)
        d.circ(.2, -.12, .07, d.dark, None)
        d.circ(.2, .12, .07, d.dark, None)
    elif t == 1:
        heart(-.05, 0, 1.0, d.hull)
        d.line((.4, 0), (1.1, 0), d.glow, 1.4)
        d.poly([(1.05, -.1), (1.2, 0), (1.05, .1)], d.acc)
    elif t == 2:
        runners(-.95, .95, .64)
        for x in (-.55, -.05, .45):
            d.rect(x - .22, -.4, x + .3, .4, d.hull)
            d.line((x - .22, -.18), (x + .3, -.18), d.mid, 1)
        d.line((.8, -.64), (.8, .64), d.trim, 1.6)
    elif t == 3:
        for x, r in ((-.55, .45), (.1, .38), (.65, .28)):
            d.circ(x, 0, r)
            d.circ(x, 0, r * .4, d.mid, None)
        d.circ(.7, 0, .1, (255, 140, 60), None)
    elif t == 4:
        d.circ(-.35, 0, .62)
        d.circ(.7, .18, .27, d.mid)
        d.arc(.1, .1, .62, .5, -.6, 1.2, d.glow, 1)
        d.spot(.13, .1, .06)
        d.circ(-.5, -.1, .15, d.mid, None)
        d.circ(-.2, .25, .1, d.mid, None)
    elif t == 5:
        for x, y, r in ((0, 0, .32), (.55, .5, .24), (.55, -.5, .24), (-.45, .52, .22), (-.45, -.52, .22),
                        (.95, 0, .16), (-.9, 0, .16)):
            d.circ(x, y, r * .8, None, d.trim)
            flake(x, y, r)
    elif t == 6:
        for k in range(6):
            a = k * math.pi / 3
            d.line((0, 0), (math.cos(a) * 1.0, math.sin(a) * 1.0), d.trim, 1.5)
            d.circ(math.cos(a) * 1.0, math.sin(a) * 1.0, .08, d.glow, None)
        d.circ(0, 0, .35)
        d.circ(0, 0, .15, d.mid, None)
        d.spot(0, 0, .08)
    else:
        heart(0, 0, 1.2, d.dark, d.glow)
        heart(0, 0, .8, d.mid, d.trim)
        d.spot(0, 0, .15, (255, 200, 230))


# ------------------------------------------------------------------ Proxima b: living spores
def spore(d, t):
    def blob(cx, cy, r, fill=HULL):
        rng = random.Random(int(cx * 17 + cy * 31 + r * 7))
        pts = [(cx + math.cos(k / 14 * math.tau) * r * (.88 + .24 * rng.random()),
                cy + math.sin(k / 14 * math.tau) * r * (.88 + .24 * rng.random())) for k in range(14)]
        d.poly(pts, fill)

    def tail(x, y, n=7, sway=.12, length=.7, col=None):
        d.lines([(x - length * k / n, y + sway * math.sin(k * .9 + x * 5)) for k in range(n + 1)],
                col or d.mid, 1.7)
    if t == 0:
        tail(-.4, -.2)
        tail(-.4, .2)
        blob(.1, 0, .55)
        for x, y in ((.2, -.2), (.3, .2), (-.1, .05)):
            d.circ(x, y, .08, d.glow, None)
    elif t == 1:
        for k in range(5):
            a = k * math.tau / 5
            d.ell(math.cos(a) * .5, math.sin(a) * .5, .46, .2, d.hull, True, a)
        d.circ(0, 0, .22, d.mid)
        d.poly([(.1, -.1), (1.05, 0), (.1, .1)], d.glow, None)
        d.spot(0, 0, .1)
    elif t == 2:
        cells = ((0, 0), (.62, 0), (.31, .54), (.31, -.54), (-.31, .54), (-.31, -.54))
        for x, y in cells[:5]:
            d.poly([(x + math.cos(k * math.pi / 3) * .36, y + math.sin(k * math.pi / 3) * .36) for k in range(6)],
                   d.hull if (x + y) > 0 else d.mid)
        d.line((.6, -.1), (1.05, -.4), d.trim, 1)
        d.line((.6, .1), (1.05, .4), d.trim, 1)
        d.spot(0, 0, .1)
    elif t == 3:
        for k, r in enumerate((1.0, .78, .56, .34)):
            d.circ(0, 0, r, None, d.glow if k % 2 == 0 else d.mid)
        d.circ(0, 0, .2, d.hull)
        d.spot(0, 0, .11, (255, 150, 220))
    elif t == 4:
        for x, y, r in ((0, 0, .45), (.5, .5, .3), (.55, -.45, .28), (-.5, .5, .26), (-.5, -.5, .3), (-.95, 0, .15),
                        (.95, 0, .17)):
            d.circ(x, y, r, lerp_c(d.hull, (0, 0, 0), .35), d.trim)
            d.circ(x - r * .3, y - r * .3, r * .22, (255, 255, 255), None)
        d.spot(0, 0, .12)
    elif t == 5:
        for x, y in ((0, 0), (.55, .55), (.55, -.55), (-.5, .55), (-.5, -.55)):
            d.ell(x, y - .2, .1, .24, d.hull, True, .5)
            d.ell(x, y + .2, .1, .24, d.hull, True, -.5)
            d.circ(x, y, .08, d.glow, None)
    elif t == 6:
        for k in range(7):
            y = -.42 + k * .14
            tail(-.35, y, 6, .1, .7)
        d.ell(.15, 0, .7, .5)
        d.circ(.3, 0, .3, d.dark, d.trim)
        d.spot(.3, 0, .15, (255, 90, 170))
    else:
        pts = []
        for k in range(150):
            a = k * .22
            r = .06 + k * .0065
            pts.append((math.cos(a) * r, math.sin(a) * r))
        for arm in range(2):
            ang = arm * math.pi
            cr, sr = math.cos(ang), math.sin(ang)
            d.lines([(x * cr - y * sr, x * sr + y * cr) for x, y in pts], d.glow if arm else d.trim, 3.4)
        d.circ(0, 0, .2, d.dark, d.glow)
        d.spot(0, 0, .12, (255, 150, 220))


FAMILIES = dict(lander=lander, rover=rover, airship=airship, solar=solar, rock=rock, storm=storm, ringed=ringed,
                crystal=crystal, deep=deep, sled=sled, spore=spore)
STYLES = ["classic"] + list(FAMILIES)


def make(style, tier, acc, size, pal):
    """The sprite of class `tier` for the hull family `style` (a size x size surface, nose to the right)."""
    d = Pen(size, pal, acc)
    FAMILIES[style](d, tier)
    return pygame.transform.smoothscale(d.surf, (size, size))


# ------------------------------------------------------------------ mining lasers, one look per family
def beam(scr, style, a, b, col, t, seed=0):
    """Draw the mining beam from a (the ship) to b (the asteroid) in the family's own style."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ln = math.hypot(dx, dy) or 1.0
    ux, uy = dx / ln, dy / ln
    nx, ny = -uy, ux
    white = lerp_c(col, (255, 255, 255), .7)
    dim = scale_c(col, .45)

    def at(k, off=0.0):
        return (ax + dx * k + nx * off, ay + dy * k + ny * off)
    if style == "lander":                                   # a stream of shots
        for k in range(7):
            f = ((k / 7) + t * 1.8) % 1.0
            pygame.draw.circle(scr, white, at(f), 3)
            pygame.draw.circle(scr, dim, at(f), 5, 1)
    elif style == "rover":                                  # a thick, jolting drill beam with sparks
        o = 2.5 * math.sin(t * 40 + seed)
        pygame.draw.line(scr, dim, a, at(1, o), 6)
        pygame.draw.line(scr, col, a, at(1, -o), 3)
        for k in range(3):
            pygame.draw.circle(scr, (255, 220, 150), (bx + random.uniform(-6, 6), by + random.uniform(-6, 6)), 2)
    elif style == "airship":                                # a wide soft beam
        pygame.draw.line(scr, scale_c(col, .22), a, b, 9)
        pygame.draw.line(scr, scale_c(col, .55), a, b, 5)
        pygame.draw.line(scr, white, a, b, 1)
    elif style == "solar":                                  # a white-hot lens beam with a flare
        pygame.draw.line(scr, dim, a, b, 7)
        pygame.draw.line(scr, (255, 250, 220), a, b, 3)
        for s in (-1, 1):
            pygame.draw.line(scr, (255, 240, 200), (bx - 9 * s, by), (bx + 9 * s, by), 1)
            pygame.draw.line(scr, (255, 240, 200), (bx, by - 9 * s), (bx, by + 9 * s), 1)
    elif style == "rock":                                   # a ragged, flickering charge
        rng = random.Random(int(t * 14) + seed)
        pts = [a] + [at(k / 6, rng.uniform(-6, 6)) for k in range(1, 6)] + [b]
        pygame.draw.lines(scr, dim, False, pts, 4)
        pygame.draw.lines(scr, white, False, pts, 1)
    elif style == "storm":                                  # lightning
        rng = random.Random(int(t * 18) + seed)
        pts = [a] + [at(k / 7, rng.uniform(-9, 9)) for k in range(1, 7)] + [b]
        pygame.draw.lines(scr, dim, False, pts, 5)
        pygame.draw.lines(scr, (255, 245, 200), False, pts, 2)
    elif style == "ringed":                                 # two parallel beams
        for off in (-4, 4):
            pygame.draw.line(scr, dim, at(0, off), at(1, off), 3)
            pygame.draw.line(scr, white, at(0, off), at(1, off), 1)
    elif style == "crystal":                                # a beam that splits into a fan at the target
        mid = at(.7)
        pygame.draw.line(scr, white, a, mid, 2)
        for off in (-9, 0, 9):
            pygame.draw.line(scr, dim, mid, at(1, off), 2)
            pygame.draw.line(scr, white, mid, at(1, off * .4), 1)
    elif style == "deep":                                   # a wavy beam
        pts = [at(k / 14, math.sin(k * .9 - t * 12) * 5 * math.sin(k / 14 * math.pi)) for k in range(15)]
        pygame.draw.lines(scr, dim, False, pts, 5)
        pygame.draw.lines(scr, white, False, pts, 2)
    elif style == "sled":                                   # slow ice shards
        for k in range(5):
            f = ((k / 5) + t * .9) % 1.0
            x, y = at(f)
            pygame.draw.polygon(scr, white, [(x + ux * 5, y + uy * 5), (x + nx * 3, y + ny * 3), (x - ux * 5, y - uy * 5),
                                             (x - nx * 3, y - ny * 3)])
        pygame.draw.line(scr, scale_c(col, .25), a, b, 2)
    elif style == "spore":                                  # a living tendril
        pts = [at(k / 14, math.sin(k * .7 + t * 6) * 8 * math.sin(k / 14 * math.pi)) for k in range(15)]
        pygame.draw.lines(scr, dim, False, pts, 6)
        pygame.draw.lines(scr, col, False, pts, 3)
        pygame.draw.circle(scr, (255, 255, 255), pts[-1], 3)
    else:                                                   # the classic laser
        pygame.draw.line(scr, dim, a, b, 4)
        pygame.draw.line(scr, white, a, b, 1)
