"""The Void Throne on screen: Sagittarius A*, one big black hole, and the Black Hole Bomb being built round it.

The system view (sysview.py) hands over to this file for the black hole at the middle of the galaxy: it has no worlds, so all you see
is the hole with its glowing disk, the light bent over and under it, and - one stage at a time - the bomb. The logic of the bomb is
blackhole.py and core.Game.build_bomb; this file draws the hole and the card with the build button.
"""
import math
import random

import pygame

import blackhole
import core
from core import fmt
from gfx import glow, lerp_c, scale_c

ADD = pygame.BLEND_RGB_ADD
DISK_IN, DISK_OUT = 1.25, 3.3          # the bright disk, in horizon radii
SHELL = 3.15                           # the mirror shell round everything


# ------------------------------------------------------------------ pictures (made once per size)
# The light is built on black and added to the picture (BLEND_ADD): it glows over the sky and over the hole's black disk alike.
def _disk_color(t):
    """The colour of the disk at t (0 at the inner edge, 1 at the outer): white-hot, yellow, orange, deep red."""
    stops = [(0.0, (255, 250, 228)), (0.2, (255, 224, 128)), (0.55, (255, 140, 40)), (1.0, (170, 40, 18))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if t <= b:
            return lerp_c(ca, cb, (t - a) / (b - a))
    return stops[-1][1]


def disk_picture(R):
    """The accretion disk seen from above: a ring of hot gas, white at its inner edge and red at its outer one, with darker streaks
    in it, brighter on the side that turns towards us."""
    D = int(2 * DISK_OUT * R)
    pic = pygame.Surface((D, D))
    c = D // 2
    r_in, r_out = DISK_IN * R, DISK_OUT * R
    steps = int(r_out - r_in)
    for i in range(steps, 0, -1):
        t = i / steps
        k = min(1.0, t * 30) * (1 - t) ** 0.85
        pygame.draw.circle(pic, scale_c(_disk_color(t), k), (c, c), int(r_in + i), 2)
    rng = random.Random(77)
    mod = pygame.Surface((D, D))
    mod.fill((255, 255, 255))
    for _ in range(260):                                      # streaks of thinner gas, blurred so they are soft
        r = r_in + rng.random() ** 1.3 * (r_out - r_in)
        a0 = rng.random() * math.tau
        v = rng.randint(185, 235)
        pygame.draw.arc(mod, (v, v, v), (c - r, c - r, 2 * r, 2 * r), a0, a0 + rng.uniform(0.2, 1.0), rng.choice((2, 3, 4)))
    mod = pygame.transform.smoothscale(pygame.transform.smoothscale(mod, (D // 5, D // 5)), (D, D))
    pic.blit(mod, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    for x in range(D):                                        # the side moving towards us is brighter
        v = int(175 + 80 * (x / D))
        pic.fill((v, v, v), (x, 0, 1, D), special_flags=pygame.BLEND_RGB_MULT)
    return pic


def arc_picture(R, r0, r1, upper):
    """The light of the far side of the disk bent over the hole (upper) or under it: half a thin ring hugging the edge, white at the
    hole and red further out, fading away towards the line it is cut at."""
    D = int(2 * r1 * R) + 4
    pic = pygame.Surface((D, D))
    c = D // 2
    n = int((r1 - r0) * R)
    for i in range(n, 0, -1):
        t = i / n
        k = 0.7 * min(1.0, t * 14) * (1 - t) ** 1.7
        pygame.draw.circle(pic, scale_c(_disk_color(0.5 * t), k), (c, c), int(r0 * R + i), 2)
    cut = pygame.Surface((D, D))
    ramp = max(8, int(0.8 * R))                                 # it fades out towards the cut: it does not end in a block
    for dy in range(c):
        v = int(255 * min(1.0, dy / ramp) ** 1.5)
        pygame.draw.line(cut, (v, v, v), (0, c - 1 - dy if upper else c + dy), (D, c - 1 - dy if upper else c + dy))
    pic.blit(cut, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    return pic


def ring_picture(R):
    """The thin ring of light at the very edge of the hole, with a soft glow outside it."""
    S = int(3.4 * R)
    pic = pygame.Surface((S, S))
    c = S // 2
    reach = int(0.4 * R)
    for dr in range(reach, -1, -1):
        k = (1 - dr / reach) ** 3.2
        pygame.draw.circle(pic, scale_c((255, 222, 165), 0.62 * k), (c, c), R + dr, 2)
    return pic


def pictures(app, R):
    key = ("hole", R)
    got = app.art.get(key)
    if got is None:
        got = app.art[key] = dict(disk=disk_picture(R), top=arc_picture(R, 1.0, 1.7, True), bottom=arc_picture(R, 1.0, 1.32, False),
                                  ring=ring_picture(R))
    return got


# ------------------------------------------------------------------ the world layer
def hole_radius(geo):
    cx, cy, rx, ry, sr = geo
    return max(40, int(min(rx / (DISK_OUT + 0.15), ry / 0.85 / 1.2)))


def draw(app, scr, geo):
    """The black hole in the middle of the system view, and every stage of the bomb that is built."""
    g = app.g
    cx, cy, rx, ry, _ = geo
    R = hole_radius(geo)
    pics = pictures(app, R)
    t = app.t
    stage = g.bomb
    spin = 0.12 + 0.05 * stage + (0.5 if stage >= 4 else 0)
    pulse = 0.5 + 0.5 * math.sin(t * (2.2 if stage < blackhole.N else 5.0))
    # the sky is darker round the hole, so the light of the disk stands out; and a faint glow round it
    gr = int(R * 4.6)
    scr.blit(glow(gr, (120, 120, 128)), (cx - gr, cy - gr), special_flags=pygame.BLEND_RGB_SUB)
    gr = int(R * 2.6)
    scr.blit(glow(gr, scale_c((255, 130, 50), 0.22 + 0.03 * round(pulse, 1))), (cx - gr, cy - gr), special_flags=ADD)
    # the disk turns: its far half, then the bent light and the hole, then its near half
    disk = pygame.transform.rotate(pics["disk"], -math.degrees(t * spin) % 360)
    side = pics["disk"].get_width()
    crop = disk.subsurface(((disk.get_width() - side) // 2, (disk.get_height() - side) // 2, side, side))
    flat = pygame.transform.smoothscale(crop, (side, int(side * 0.3)))
    fh = flat.get_height()
    back = pygame.Rect(0, 0, side, fh // 2)
    front = pygame.Rect(0, fh // 2, side, fh - fh // 2)
    scr.blit(flat, (cx - side // 2, cy - fh // 2), back, special_flags=ADD)
    top = pics["top"]
    scr.blit(top, (cx - top.get_width() // 2, cy - top.get_height() // 2 - int(R * 0.06)), special_flags=ADD)
    bomb(app, scr, geo, R, t, stage, pulse, front=False)
    pygame.draw.circle(scr, (0, 0, 0), (cx, cy), R)
    ring = pics["ring"]
    scr.blit(ring, (cx - ring.get_width() // 2, cy - ring.get_height() // 2), special_flags=ADD)
    bottom = pics["bottom"]
    scr.blit(bottom, (cx - bottom.get_width() // 2, cy - bottom.get_height() // 2 + int(R * 0.06)), special_flags=ADD)
    scr.blit(flat, (cx - side // 2, cy), front, special_flags=ADD)
    boost = pics.get(("boost", fh))                              # the near side of the disk is the bright one (it turns towards us):
    if boost is None:                                            # more light, from nothing at the middle line to a lot at the front
        ramp = pygame.Surface((side, fh))
        for y in range(fh):
            v = int(255 * max(0.0, (y - fh / 2) / (fh / 2)) ** 0.9)
            pygame.draw.line(ramp, (v, v, v), (0, y), (side, y))
        pics[("boost", fh)] = boost = ramp
    extra = flat.copy()
    extra.blit(boost, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    scr.blit(extra, (cx - side // 2, cy - fh // 2), special_flags=ADD)
    bomb(app, scr, geo, R, t, stage, pulse)


def _shell_point(cx, cy, R, ang, k=SHELL, flat=0.8):
    return cx + math.cos(ang) * R * k, cy + math.sin(ang) * R * k * flat


def bomb(app, scr, geo, R, t, stage, pulse, front=True):
    """The stages built so far, round the hole. Called twice: first (front False) for the far halves of the rings that go round the hole,
    which the hole hides, then (front True) for everything else and the near halves."""
    cx, cy = geo[0], geo[1]
    armed = stage >= blackhole.N
    tone = lerp_c((190, 215, 255), (255, 120, 100), pulse) if armed else (190, 215, 255)
    half = (math.pi, math.tau) if front else (0.0, math.pi)          # pygame's arcs run anticlockwise on the screen: 0..pi is the top
    if stage >= 5 and not front:                                     # the armed bomb glows red behind the hole
        gr = int(R * (2.7 + 0.4 * pulse))
        scr.blit(glow(gr, scale_c((255, 70, 60), 0.3)), (cx - gr, cy - gr), special_flags=ADD)
    if stage >= 1 and front:                                    # the mirror shell: a circle of panels
        sr = R * SHELL
        pygame.draw.ellipse(scr, scale_c(tone, 0.42), (cx - sr, cy - sr * 0.8, 2 * sr, 2 * sr * 0.8), 1)
        n = 44
        for i in range(n):
            a = i * math.tau / n + t * 0.05
            x, y = _shell_point(cx, cy, R, a)
            glint = 0.5 + 0.5 * math.sin(t * 2.0 + i * 1.7)
            pts = [(x, y - 5), (x + 4, y), (x, y + 5), (x - 4, y)]
            pygame.draw.polygon(scr, scale_c(tone, 0.55 + 0.45 * glint), pts)
    if stage >= 2:                                              # the superradiant core: a tight ring of light and the lasers on it
        rr = R * 1.55
        pygame.draw.arc(scr, scale_c((140, 255, 245), 0.8), (cx - rr, cy - rr * 0.3, 2 * rr, 2 * rr * 0.3), half[0], half[1], 2)
        for i in range(6):
            a = t * 1.4 + i * math.tau / 6
            if (math.sin(a) > 0) == front:
                x, y = cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.3
                scr.blit(glow(10, (90, 220, 210)), (x - 10, y - 10), special_flags=ADD)
    if stage >= 3 and front:                                    # the containment lattice: pylons from the shell to a hexagon
        hexp = []
        for i in range(6):
            a = i * math.tau / 6 + 0.3
            hexp.append(_shell_point(cx, cy, R, a, 2.25))
            pygame.draw.line(scr, scale_c(tone, 0.55), _shell_point(cx, cy, R, a, SHELL), hexp[-1], 2)
        pygame.draw.polygon(scr, scale_c(tone, 0.5), hexp, 1)
    if stage >= 4:                                              # the spin-up rings and the jets they throw out of the poles
        for k, rr in enumerate((R * 2.65, R * 2.0)):
            pygame.draw.arc(scr, (255, 200, 120), (cx - rr, cy - rr * 0.22, 2 * rr, 2 * rr * 0.22), half[0], half[1], 2)
            for i in range(10):
                a = (t * (0.9 + 0.4 * k)) * (1 if k == 0 else -1) + i * math.tau / 10
                if (math.sin(a) > 0) == front:
                    x, y = cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.22
                    pygame.draw.circle(scr, (255, 235, 190), (int(x), int(y)), 2)
        if front:
            for sign in (-1, 1):
                tipy = cy + sign * R * 2.7
                for w, col in ((6, (90, 60, 30)), (3, (200, 170, 120)), (1, (255, 250, 235))):
                    pygame.draw.polygon(scr, col, [(cx - w, cy + sign * R * 1.02), (cx + w, cy + sign * R * 1.02), (cx, tipy)])
    if stage >= 5 and front:                                    # the trigger array: eight satellites aimed at the middle
        for i in range(8):
            a = i * math.tau / 8 + t * 0.12
            x, y = _shell_point(cx, cy, R, a, SHELL + 0.25)
            d = math.hypot(x - cx, y - cy) or 1.0
            end = (cx + (x - cx) / d * R * 1.04, cy + (y - cy) / d * R * 1.04)             # the beams stop at the edge of the hole
            pygame.draw.line(scr, scale_c((255, 90, 80), 0.3 + 0.7 * pulse), (x, y), end, 1)
            pygame.draw.rect(scr, (255, 240, 235), (int(x) - 4, int(y) - 4, 8, 8))
            pygame.draw.rect(scr, (255, 100, 90), (int(x) - 4, int(y) - 4, 8, 8), 1)


# ------------------------------------------------------------------ the card
def card_lines(app):
    """What the card says: (title, stage text, cost lines [(text, colour)], button label, button function or None)."""
    g = app.g
    st = g.bomb
    if st >= blackhole.N:
        return (f"{blackhole.NAME}: ARMED", f"Ascend and it goes off: the Stardust of the Ascension is x{blackhole.SD_MULT:g}.",
                [(f"Built {st} of {blackhole.N}; a bomb is used up when it goes off.", (255, 170, 150))], "ARMED", None)
    ore, cr, sci = g.bomb_cost(st)
    p = g.bomb_planet()
    ok = g.can_build_bomb()
    have_ore = g.ore[p] if p is not None else 0.0
    ore_name = g.sites[p]["ore"] if p is not None else "tier 11 ore"
    good, bad = (130, 255, 150), (230, 130, 130)
    lines = [(f"{fmt(ore)} {ore_name}  (have {fmt(have_ore)})", good if have_ore >= ore else bad),
             (f"{fmt(cr)} credits  (have {fmt(g.credits)})   {fmt(sci)} science  (have {fmt(g.science)})",
              good if g.credits >= cr and g.science >= sci else bad)]
    return (f"{blackhole.stage_name(st)}  -  stage {st + 1} of {blackhole.N}", blackhole.STAGES[st]["text"], lines,
            "BUILD", (lambda: g.build_bomb()) if ok else None)


def draw_card(app, scr, fonts, r):
    """The bomb's card, in the place of a world's card: the stage to build, what it costs and the button."""
    import sysview
    big, med, sm, tiny = fonts
    g = app.g
    title, text, lines, label, fn = card_lines(app)
    armed = g.bomb >= blackhole.N
    col = (255, 130, 110) if armed else (255, 200, 130)
    x = r.x + 14
    for i in range(blackhole.N):                                  # five pips: built, the next one, not yet
        c = (r.x + 24 + i * 22, r.y + 22)
        if i < g.bomb:
            pygame.draw.circle(scr, col, c, 8)
        else:
            pygame.draw.circle(scr, (255, 235, 190) if i == g.bomb else (70, 74, 100), c, 8, 2)
    x = r.x + 14 + 5 * 22 + 12
    room = r.w - 130 - (x - r.x)
    font = med if med.size(title)[0] < room else sm
    app.txt(scr, font, title, (x, r.y + 8 if font is med else r.y + 12), col)
    app.txt(scr, tiny, text, (r.x + 14, r.y + 44), (190, 198, 225))
    for i, (t, c) in enumerate(lines[:2]):
        app.txt(scr, tiny, t, (r.x + 14, r.y + 64 + i * 18), c)
    rect = pygame.Rect(r.right - 120, r.y + 8, 108, 38)
    enabled = fn is not None
    hot = enabled and rect.collidepoint(app.mouse) and not sysview._touch()
    c = (130, 70, 50) if enabled else (38, 40, 52)
    pygame.draw.rect(scr, tuple(min(255, v + 25) for v in c) if hot else c, rect, border_radius=8)
    pygame.draw.rect(scr, (255, 180, 130) if enabled else (62, 64, 80), rect, 1, border_radius=8)
    app.txt(scr, sm, label, rect.center, (255, 240, 225) if enabled else (130, 132, 150), "center")
    if enabled:
        app.orb_btns.append((rect, fn))
