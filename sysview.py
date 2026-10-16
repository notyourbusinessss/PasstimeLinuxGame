"""The star system view: a star in the middle and its worlds on their orbits.

The middle level of the map: the galaxy shows the stars, this shows what orbits one you hold (the twelve planets of the solar system,
or the worlds of worlds.py) and a click opens a world as the planet view you mine in. Worlds you hold are lit, the ones you can settle
pulse, the rest are dimmed; the card at the bottom says what the selected one is and what you can do with it.

The layout (bodies, orbit sizes, speeds) is pure data and cached per star; the functions that draw and click take the App, like
frontview and worldview do.
"""
import math
import zlib

import pygame

import colonies
import core
import galaxy
import gfx
import holeview
import worlds
from core import fmt
from gfx import glow, lerp_c, scale_c

ADD = pygame.BLEND_RGB_ADD
TILT = 0.7                                  # how flat the orbits are drawn (height / width)
CARD_H = 112
TOP = 70                                    # the navigation bar and the star's line sit above this
# the real distance from the Sun of the planets of the solar system, in AU (the Moon orbits the Earth)
SOL_AU = {"Mercury": 0.387, "Venus": 0.723, "Earth": 1.0, "Mars": 1.524, "Ceres": 2.77, "Jupiter": 5.2, "Saturn": 9.58, "Uranus": 19.2,
          "Neptune": 30.07, "Pluto": 39.5, "Kuiper Belt": 46.0}
SOL_SIZE = {"Mercury": 15, "Venus": 21, "Earth": 22, "Moon": 11, "Mars": 18, "Ceres": 13, "Jupiter": 38, "Saturn": 32, "Uranus": 26,
            "Neptune": 26, "Pluto": 12, "Kuiper Belt": 16}
BELTS = ("Ceres", "Kuiper Belt")            # these two are belts: a ring of rocks goes round their orbit
# star kind -> (colour, radius in pixels). Kinds that are not a star (a nebula, a black hole) have no worlds and are not shown here.
STAR_LOOK = {"Red dwarf": ((255, 120, 80), 17), "Orange dwarf": ((255, 170, 90), 21), "Yellow dwarf": ((255, 224, 130), 25),
             "White star": ((225, 235, 255), 25), "Binary system": ((255, 205, 130), 19), "Brown dwarf": ((190, 90, 120), 14),
             "White dwarf": ((215, 230, 255), 11), "Red giant": ((255, 110, 70), 44), "Blue giant": ((140, 180, 255), 36),
             "Supergiant": ((255, 150, 110), 54), "Neutron star": ((190, 220, 255), 8), "Pulsar": ((190, 220, 255), 8)}
DEFAULT_LOOK = ((255, 224, 130), 22)
KIND_COL = dict(temperate=(120, 230, 140), ocean=(110, 170, 255), rocky=(190, 180, 170), desert=(235, 190, 120), ice=(190, 220, 255),
                lava=(255, 140, 80), dwarf=(190, 175, 165), mini=(190, 215, 230), ice_giant=(120, 215, 230), gas=(235, 180, 130))
GOOD, BAD, GOLD = (130, 255, 150), (230, 130, 130), (255, 215, 110)


# ------------------------------------------------------------------ the layout of a star (pure data)
_CACHE = {}


def star_of_site(site):
    """The star a planet (a site of core.SITES or a colony's) orbits: the Sun for the solar planets."""
    return site.get("sys", 0)


def bodies(k):
    """The bodies of star k, the planets nearest first and a moon after its planet: dicts with key, name, a (AU), size, u (0 inner ... 1
    outer orbit), phase, w (angular speed in rad/s), parent (a key or None) and either p (a solar planet) or world."""
    got = _CACHE.get(k)
    if got is None:
        got = _CACHE[k] = _make(k)
    return got


def _phase(key):
    return (zlib.crc32(repr(key).encode()) % 6283) / 1000.0


def _world_size(w):
    return int(max(16, min(48, 1.3 * (12 + 7 * math.log2(1 + w["r"])))))


def _make(k):
    out = []
    if k == 0:
        for p, s in enumerate(core.SITES):
            nm = s["name"]
            b = dict(key=("s", p), name=nm, size=round(SOL_SIZE[nm] * 1.3), p=p, ring=nm == "Saturn", belt=nm in BELTS, parent=None,
                     a=SOL_AU.get(nm, 1.0))
            if nm == "Moon":
                b["parent"] = ("s", 0)
            out.append(b)
    else:
        for i, w in enumerate(worlds.planets_of(k)):
            out.append(dict(key=("w", k, i), name=w["name"], size=_world_size(w), world=w, ring=w["ring"], belt=False, parent=None,
                            a=max(1e-4, w["a"])))
    planets = sorted((b for b in out if b["parent"] is None), key=lambda b: b["a"])
    n = len(planets)
    logs = [math.log(b["a"]) for b in planets]
    lo, hi = (min(logs), max(logs)) if logs else (0, 1)
    for j, b in enumerate(planets):
        rank = j / (n - 1) if n > 1 else 0.5
        spread = (logs[j] - lo) / (hi - lo) if hi > lo + 1e-9 else rank
        b["u"] = 0.5 * rank + 0.5 * spread                    # an even spacing, bent towards the real one
        b["w"] = min(0.6, 0.16 / (0.25 + b["u"]) ** 1.2)
    for b in out:
        b["phase"] = _phase(b["key"])
        if b["parent"] is not None:                          # a moon: it goes round its planet
            b["u"], b["w"] = 0.0, 1.5
    out.sort(key=lambda b: (b["parent"] is not None, b["a"]))
    return out


def body_of(k, key):
    for b in bodies(k):
        if b["key"] == key:
            return b
    return None


def current_star(app):
    """The star the system view shows."""
    g = app.g
    k = app.sys_k
    if k is None or (k and k not in g.conquered):
        k = star_of_site(g.sites[g.cur])
    return k if k == 0 or k in g.conquered else 0


def can_open(g, k):
    """A system you can open: the Sun, a star you hold that has worlds, and the Void Throne (the black hole with the bomb)."""
    return k == 0 or (k in g.conquered and (bool(worlds.count_of(k)) or k == core.BOSS))


# ------------------------------------------------------------------ states
def state_of(g, b):
    """What a body is to you: here (the planet you are on), owned (you can travel there), ready (you can settle or unlock it with
    what you have), next (the next solar planet), settled-not (a world you could settle later) or locked."""
    if "p" in b:
        p = b["p"]
        if g.unlocked[p]:
            return "here" if p == g.cur else "owned"
        if g.can_unlock(p):
            return "ready"
        return "next" if p > 0 and g.unlocked[p - 1] else "locked"
    k, i = b["key"][1], b["key"][2]
    st = g.settle_state(k, i)
    if st == "settled":
        return "here" if g.colony_planet[(k, i)] == g.cur else "owned"
    return "ready" if st == "ready" and g.can_settle(k, i) else ("next" if st == "ready" else "locked")


def planet_of(g, b):
    """The planet number of a body you hold, or None."""
    if "p" in b:
        return b["p"] if g.unlocked[b["p"]] else None
    return g.colony_planet.get((b["key"][1], b["key"][2]))


# ------------------------------------------------------------------ opening and leaving
def open_system(app, k=None, sel=None):
    """Show star k (default: the star of the planet you are on) in the system view."""
    g = app.g
    if k is None:
        k = star_of_site(g.sites[g.cur])
    if not can_open(g, k):
        g.toast("That star has no worlds to show." if k in g.conquered else "Liberate a star to see its worlds.", 3)
        return False
    app.sys_k = k
    app.sys_sel = sel
    app.view = "orbit"
    return True


def toggle(app):
    """The strip's star button and the S key: the system view of the planet you are on, or back to the planet."""
    if app.view == "orbit":
        leave(app)
    else:
        open_system(app)


def leave(app):
    app.view = "system"


def go_to(app, b):
    """The primary action on a body you hold: travel there (or open it when you are there) and show the planet view."""
    g = app.g
    p = planet_of(g, b)
    if p is None:
        return
    if p == g.cur:
        app.view = "system"
    else:
        app.strip_click(p)


def primary(app, b):
    """(label, function, enabled) of the main button for body b."""
    g = app.g
    st = state_of(g, b)
    if st in ("here", "owned"):
        return ("OPEN PLANET" if st == "here" else "TRAVEL HERE"), (lambda: go_to(app, b)), True
    if "p" in b:
        if st == "ready":
            return "UNLOCK", (lambda p=b["p"]: g.unlock_planet(p)), True
        return "LOCKED", None, False
    k, i = b["key"][1], b["key"][2]
    if st == "ready":
        return "SETTLE", (lambda: g.settle(k, i)), True
    if st == "next":
        return "SETTLE", (lambda: g.settle(k, i)), False
    return "WAITING", None, False


# ------------------------------------------------------------------ pictures
def star_sprite(app, kind):
    look = STAR_LOOK.get(kind, DEFAULT_LOOK)
    key = ("orbstar", kind)
    pic = app.art.get(key)
    if pic is None:
        col, r = look
        S = r * 6
        pic = pygame.Surface((S, S), pygame.SRCALPHA)
        c = S // 2
        pic.blit(glow(r * 3, scale_c(col, 0.55)), (c - r * 3, c - r * 3), special_flags=ADD)
        pic.blit(glow(int(r * 1.9), scale_c(col, 0.8)), (c - int(r * 1.9), c - int(r * 1.9)), special_flags=ADD)
        for i in range(r, 0, -1):                               # a disc, darker at the rim
            t = i / r
            pygame.draw.circle(pic, lerp_c((255, 255, 255), col, t ** 1.6), (c, c), i)
        pygame.draw.circle(pic, scale_c(col, 0.85), (c, c), r, 2)
        app.art[key] = pic
    return pic


def body_pic(app, b, level=0):
    """The picture of a body: a solar planet's own icon, a world painted by gfx.make_world; level 1 dims it (a world you have not settled
    yet) and level 2 makes it a dark shape (a planet you have not found)."""
    size = b["size"]
    key = ("orbbody", b["key"], level)
    pic = app.art.get(key)
    if pic is None:
        if "p" in b:
            pic = pygame.transform.smoothscale(app.site_icon(b["p"], 48), (size, size))
        else:
            w = b["world"]
            pic = gfx.make_world(w["kind"], w["seed"], round(size / 0.58) if w["ring"] else size, w["ring"])
        if level:
            pic = pic.copy()
            pic.fill((120, 124, 150, 255) if level == 1 else (24, 28, 46, 255), special_flags=pygame.BLEND_RGBA_MULT)
        app.art[key] = pic
    return pic


# ------------------------------------------------------------------ geometry
def area(app):
    return app.orbit_area()


def geometry(app, k):
    """(centre x, centre y, rx, ry, star radius) of the system on screen."""
    A = area(app)
    look = STAR_LOOK.get(galaxy.STARS[k]["kind"], DEFAULT_LOOK)
    bottom = A.bottom - CARD_H - 14
    cy = (TOP + bottom) // 2 + 6
    ry = max(60, (bottom - TOP) // 2 - 26)
    rx = max(120, A.w // 2 - 36)
    ry = min(ry, int(rx * TILT))
    return A.centerx, cy, rx, ry, look[1]


def body_pos(app, k, b, geo, t, cache):
    """Where body b is at time t on screen (x, y), and how far it is round its orbit (for the draw order)."""
    cx, cy, rx, ry, sr = geo
    if b["parent"] is not None:
        px, py = cache[b["parent"]][:2]
        ang = b["phase"] + b["w"] * t
        pr = (body_of(k, b["parent"])["size"] // 2) + 12 + b["size"] // 2
        return px + math.cos(ang) * pr, py + math.sin(ang) * pr * 0.6, math.sin(ang)
    r = orbit_radius(geo, b)
    ang = b["phase"] + b["w"] * t
    return cx + math.cos(ang) * r, cy + math.sin(ang) * r * (ry / rx), math.sin(ang)


def orbit_radius(geo, b):
    cx, cy, rx, ry, sr = geo
    inner = sr + 26
    return inner + (rx - inner) * b["u"]


# ------------------------------------------------------------------ drawing
def draw(app, scr, fonts):
    """The world layer: orbits, the star, the bodies (the ones behind the star first). Fills app.orb_hits for the clicks."""
    g = app.g
    k = current_star(app)
    geo = geometry(app, k)
    cx, cy, rx, ry, sr = geo
    t = app.t
    bs = bodies(k)
    star = galaxy.STARS[k]
    sel = app.sys_sel
    app.orb_hits = []
    if k == core.BOSS:                                           # one big black hole and nothing else
        app.orb_hover = None
        holeview.draw(app, scr, geo)
        return
    # the orbits
    for b in bs:
        if b["parent"] is not None:
            continue
        r = orbit_radius(geo, b)
        on = b["key"] == sel
        st = state_of(g, b)
        col = (110, 130, 190) if on else ((58, 72, 118) if st in ("here", "owned") else (40, 48, 82))
        pygame.draw.ellipse(scr, col, (cx - r, cy - r * ry / rx, 2 * r, 2 * r * ry / rx), 2 if on else 1)
        if b["belt"]:
            _belt(scr, cx, cy, r, ry / rx, b["phase"], t)
    # positions
    cache = {}
    for b in bs:
        x, y, depth = body_pos(app, k, b, geo, t, cache)
        cache[b["key"]] = (x, y, depth)
    behind = [b for b in bs if cache[b["key"]][2] < 0]
    front = [b for b in bs if cache[b["key"]][2] >= 0]
    for b in behind:
        _body(app, scr, fonts, k, b, cache)
    _star(app, scr, k, geo)
    for b in front:
        _body(app, scr, fonts, k, b, cache)
    app.orb_hits.append((cx, cy, sr + 8, "star"))
    # hover
    hover = None
    if area(app).collidepoint(app.mouse) and not card_rect(app).collidepoint(app.mouse):
        best = 1e9
        for x, y, r, key in app.orb_hits:
            d = math.hypot(app.mouse[0] - x, app.mouse[1] - y)
            if d < r + 8 and d < best:
                best, hover = d, key
    app.orb_hover = hover
    # the labels: the hovered, the selected and the one you are on first, then the others where there is room
    cands = []
    for b in bs:
        x, y, _ = cache[b["key"]]
        key = b["key"]
        st = state_of(g, b)
        prio = 0 if key == hover else 1 if key == sel else 2 if st == "here" else 3 if st == "owned" else 4
        lab = "?" if "p" in b and st == "locked" else b["name"]
        if prio > 1 and lab.startswith(star["name"] + " "):               # "TRAPPIST-1 e" is just "e" next to its star
            lab = lab[len(star["name"]) + 1:]
        if len(lab) > 20:
            lab = lab[:19] + "."
        col = (255, 245, 200) if prio < 2 else ((235, 240, 255) if st in ("here", "owned") else (150, 158, 190))
        cands.append((prio, b["size"], x, y, lab, col))
    drawn = []
    for prio, size, x, y, lab, col in sorted(cands, key=lambda c: c[0]):
        w, h = fonts[3].size(lab)
        r = pygame.Rect(0, 0, w + 4, h + 2)
        r.midtop = (x, y + size // 2 + 5)
        if prio > 1 and any(r.colliderect(d) for d in drawn):
            continue
        drawn.append(r)
        app.txt(scr, fonts[3], lab, r.midtop, col, "midtop", True)


def _belt(scr, cx, cy, r, tilt, phase, t):
    """A ring of rocks round an orbit (a belt), turning slowly."""
    n = 70
    for i in range(n):
        h = zlib.crc32(f"{i}:{phase:.2f}".encode())
        ang = i * math.tau / n + (h % 100) / 100 * 0.08 + t * 0.03
        jr = r + ((h >> 8) % 9) - 4
        x, y = cx + math.cos(ang) * jr, cy + math.sin(ang) * jr * tilt
        v = 110 + (h >> 16) % 60
        scr.fill((v, v - 8, v - 20), (int(x), int(y), 2, 2))


def _star(app, scr, k, geo):
    cx, cy, rx, ry, sr = geo
    kind = galaxy.STARS[k]["kind"]
    pic = star_sprite(app, kind)
    col = STAR_LOOK.get(kind, DEFAULT_LOOK)[0]
    pulse = round(0.5 + 0.5 * math.sin(app.t * 1.3), 1)                  # (a few steps: every glow is cached)
    gr = int(sr * 3.4)
    scr.blit(glow(gr, scale_c(col, 0.16 + 0.05 * pulse)), (cx - gr, cy - gr), special_flags=ADD)
    if kind in ("Neutron star", "Pulsar"):                      # two beams that sweep round
        a = app.t * 3.0
        for da in (0, math.pi):
            pygame.draw.line(scr, scale_c(col, 0.8), (cx, cy), (cx + math.cos(a + da) * 80, cy + math.sin(a + da) * 80 * 0.7), 2)
    if kind == "Binary system":                                 # two stars round each other
        a = app.t * 0.9
        for da, f in ((0, 1.0), (math.pi, 0.72)):
            x, y = cx + math.cos(a + da) * sr * 0.9, cy + math.sin(a + da) * sr * 0.5
            p = star_sprite(app, "Yellow dwarf" if da == 0 else "Red dwarf")
            scr.blit(pygame.transform.smoothscale(p, (int(p.get_width() * f * 0.8), int(p.get_height() * f * 0.8))),
                     (x - p.get_width() * f * 0.4, y - p.get_height() * f * 0.4))
        return
    scr.blit(pic, pic.get_rect(center=(cx, cy)))


def _level(b, st):
    """How dark a body is drawn: 0 when you hold it or can take it now, 1 for a world waiting to be settled, 2 for a solar planet not found."""
    if st in ("here", "owned", "ready"):
        return 0
    return 2 if "p" in b and st == "locked" else 1


def _body(app, scr, fonts, k, b, cache):
    g = app.g
    x, y, _ = cache[b["key"]]
    st = state_of(g, b)
    held = st in ("here", "owned")
    pic = body_pic(app, b, _level(b, st))
    size = b["size"]
    rad = size // 2 + 2
    if held:
        scr.blit(glow(rad + 8, scale_c((90, 120, 200), 0.35)), (x - rad - 8, y - rad - 8), special_flags=ADD)
    scr.blit(pic, pic.get_rect(center=(int(x), int(y))))
    if b["ring"] and "p" in b:                                  # the rings of Saturn
        pygame.draw.ellipse(scr, (214, 194, 150), (x - size * 0.8, y - size * 0.2, size * 1.6, size * 0.4), 1)
    key = b["key"]
    if st == "here":
        pygame.draw.circle(scr, GOLD, (int(x), int(y)), rad + 4, 2)
    elif st == "owned":
        pygame.draw.circle(scr, (90, 190, 130), (int(x), int(y)), rad + 3, 1)
    elif st == "ready":
        pulse = 0.5 + 0.5 * math.sin(app.t * 4 + b["phase"])
        pygame.draw.circle(scr, scale_c(GOLD, 0.5 + 0.5 * pulse), (int(x), int(y)), rad + 3 + int(2 * pulse), 1)
    if key == app.sys_sel:
        a0 = app.t * 1.5
        for i in range(4):
            a = a0 + i * math.pi / 2
            pygame.draw.line(scr, (255, 255, 255), (x + math.cos(a) * (rad + 6), y + math.sin(a) * (rad + 6)),
                             (x + math.cos(a + 0.5) * (rad + 6), y + math.sin(a + 0.5) * (rad + 6)), 2)
    app.orb_hits.append((x, y, rad, key))


# ------------------------------------------------------------------ the overlay: navigation, the star's line and the card
def card_rect(app):
    A = area(app)
    return pygame.Rect(A.x + 8, A.bottom - CARD_H - 4, A.w - 16, CARD_H)


def pill(app, scr, font, rect, label, fn, on=False, col=(26, 34, 70)):
    """A button of the system view (clicks are handled by click(), through app.orb_btns)."""
    hot = rect.collidepoint(app.mouse) and not _touch()
    c = (60, 84, 150) if hot else ((56, 76, 140) if on else col)
    pygame.draw.rect(scr, c, rect, border_radius=8)
    pygame.draw.rect(scr, (140, 170, 235) if on or hot else (84, 104, 168), rect, 1, border_radius=8)
    app.txt(scr, font, label, rect.center, (240, 244, 255), "center")
    if fn is not None:
        app.orb_btns.append((rect, fn))


def _touch():
    import resources
    return resources.TOUCH


def crumbs(app, scr, fonts, k):
    """GALAXY > the star > the planet you are on: each part takes you there."""
    g = app.g
    big, med, sm, tiny = fonts
    star = galaxy.STARS[k]
    x, y = 12, 10
    items = [("GALAXY", (lambda: _to_galaxy(app, k)), False), (star["name"], None, True)]
    for label, fn, on in items:
        w = sm.size(label)[0] + 24
        pill(app, scr, sm, pygame.Rect(x, y, w, 28), label, fn, on)
        x += w + 4
        if label == "GALAXY":
            app.txt(scr, sm, ">", (x + 3, y + 14), (130, 150, 205), "midleft")
            x += 16
    here = g.sites[g.cur]
    if star_of_site(here) == k:
        app.txt(scr, sm, ">", (x - 2, y + 14), (130, 150, 205), "midleft")
        x += 14
        label = here["name"]
        w = sm.size(label)[0] + 24
        pill(app, scr, sm, pygame.Rect(x, y, w, 28), label, (lambda: leave(app)), False, col=(34, 52, 90))
        x += w + 4
    return x


def _to_galaxy(app, k):
    g = app.g
    if not g.galaxy_open:
        g.toast("Unlock Mars to open the galaxy map.", 3)
        return
    app.sel_sector = k
    app.view = "galaxy"
    app.tab = app.fv.tab_galaxy
    app.fv.opened()
    app.fv.focus(k)


def star_line(app, scr, fonts, k):
    g = app.g
    big, med, sm, tiny = fonts
    star = galaxy.STARS[k]
    ws = bodies(k)
    held = sum(1 for b in ws if b["parent"] is None and state_of(g, b) in ("here", "owned"))
    n = sum(1 for b in ws if b["parent"] is None)
    if k == core.BOSS:
        app.txt(scr, tiny, f"Black hole  -  Sagittarius A*, 4.3 million suns  -  {galaxy.fmt_ly(star['d'])} away",
                (14, 46), (160, 172, 210), "topleft", True)
        return
    if k == 0:
        sub = f"{star['kind']}  -  your home  -  {held} of {n} planets unlocked"
    else:
        sub = (f"{star['kind']}  -  {galaxy.fmt_ly(star['d'])} from the Sun  -  {star['region']}, {star['con']}  -  "
               f"{held} of {n} worlds settled")
    app.txt(scr, tiny, sub, (14, 46), (160, 172, 210), "topleft", True)


def draw_hud(app, scr, fonts):
    """The numbers at the top of the system view: the star's line and your income (the mining numbers belong to the planet view)."""
    g = app.g
    big, med, sm, tiny = fonts
    A = area(app)
    k = current_star(app)
    app.orb_btns = []
    crumbs(app, scr, fonts, k)
    star_line(app, scr, fonts, k)
    app.txt(scr, med, f"{fmt(g.credits)} credits", (A.right - 12, 8), (255, 218, 120), "topright", True)
    app.txt(scr, tiny, f"+{fmt(g.cred_ops)}/s", (A.right - 12, 30), (225, 190, 110), "topright", True)
    if g.sci_ops > 0 or g.science > 0:
        app.txt(scr, sm, f"{fmt(g.science)} science", (A.right - 12, 46), (125, 238, 255), "topright", True)
    draw_card(app, scr, fonts, k)


def describe(app, k, b):
    """What the card says about body b: (title, colour, sub, lines, picture-kind info)."""
    g = app.g
    st = state_of(g, b)
    if "p" in b:
        p = b["p"]
        s = g.sites[p]
        col = s["col"]
        if st in ("here", "owned"):
            lines = [(f"{fmt(g.ore[p])} {s['ore']} stored   (+{fmt(g.s_ops[p])}/s)", (215, 220, 240)), (s["perk"], (170, 175, 205))]
        elif st == "ready" or st == "next":
            ores, cr = g.unlock_cost(p)
            bits, ok = [], True
            for q, amt in ores:
                if amt > 0:
                    have = g.ore[q] >= amt
                    ok &= have
                    bits.append(f"{fmt(amt)} {g.sites[q]['ore']}")
            if cr > 0:
                ok &= g.credits >= cr
                bits.append(f"{fmt(cr)} credits")
            lines = [("cost: " + "  +  ".join(bits), GOOD if ok else BAD), (s["perk"], (170, 175, 205))]
        else:
            lines = [("Unlock the planet before it first.", (150, 158, 190))]
        sub = f"Planet of the solar system  -  mining {s['ore']}"
        if st == "locked":
            return "???", (140, 146, 180), "Not found yet", lines
        return s["name"], col, sub, lines
    w = b["world"]
    kk, i = b["key"][1], b["key"][2]
    col = KIND_COL[w["kind"]]
    site = colonies.site_of(kk, i)
    sub = f"{worlds.KIND_NAMES[w['kind']]}  -  {worlds.size_text(w['r'], w['m']).split(',')[0]}  -  {w['t']:.0f} K  -  {w['a']:.3g} AU"
    first = g.kind_first.get(w["kind"])
    perk = (site["perk"], (170, 175, 205)) if first is None or first == (kk, i) else (colonies.NO_PERK, (120, 126, 150))
    if st in ("here", "owned"):
        p = g.colony_planet[(kk, i)]
        lines = [(f"{fmt(g.ore[p])} {site['ore']} stored   (+{fmt(g.s_ops[p])}/s)", (215, 220, 240)), perk]
    elif st in ("ready", "next"):
        pays, cr = g.settle_cost(kk, i)
        bits, ok = [], True
        for p, amt in pays:
            have = p is not None and g.ore[p] >= amt
            ok &= have
            bits.append(f"{fmt(amt)} {g.sites[p]['ore'] if p is not None else 'ore'}")
        if cr > 0:
            ok &= g.credits >= cr
            bits.append(f"{fmt(cr)} credits")
        lines = [("cost: " + "  +  ".join(bits), GOOD if ok else BAD), perk]
    else:
        t = site["tier"] - 1
        lines = [(f"Needs a planet of tier {t}: {core.SITES[min(t, core.NSOL - 1)]['name']} is one", (230, 190, 130)), perk]
    return w["name"], col, sub, lines


def draw_card(app, scr, fonts, k):
    """The card at the bottom: the selected body (or the star) with its picture, its numbers and the main button."""
    g = app.g
    big, med, sm, tiny = fonts
    r = card_rect(app)
    bg = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(bg, (10, 13, 32, 238), bg.get_rect(), border_radius=10)
    pygame.draw.rect(bg, (90, 115, 185, 255), bg.get_rect(), 1, border_radius=10)
    scr.blit(bg, r)
    if k == core.BOSS:
        holeview.draw_card(app, scr, fonts, r)
        return
    b = body_of(k, app.sys_sel) if app.sys_sel not in (None, "star") else None
    if b is None:
        app.sys_sel = None if app.sys_sel != "star" else "star"
    star = galaxy.STARS[k]
    bx = r.right - 12
    if b is None:                                                # the star
        look = STAR_LOOK.get(star["kind"], DEFAULT_LOOK)
        pic = star_sprite(app, star["kind"])
        small = pygame.transform.smoothscale(pic, (pic.get_width() // 3, pic.get_height() // 3))
        scr.blit(small, small.get_rect(center=(r.x + 50, r.centery)))
        app.txt(scr, med, star["name"], (r.x + 104, r.y + 10), (235, 240, 255))
        app.txt(scr, tiny, star["kind"] if k else "Yellow dwarf  -  the Sun", (r.x + 104, r.y + 36), look[0])
        ws = [b2 for b2 in bodies(k) if b2["parent"] is None]
        held = sum(1 for b2 in ws if state_of(g, b2) in ("here", "owned"))
        app.txt(scr, tiny, f"{len(ws)} world{'s' if len(ws) != 1 else ''} - {held} held", (r.x + 104, r.y + 54), (205, 212, 235))
        if k:
            app.txt(scr, tiny, star["desc"], (r.x + 104, r.y + 72), (130, 255, 150))
            app.txt(scr, tiny, "Click a world to select it; the first of each kind brings a planet bonus.", (r.x + 104, r.y + 90), (140, 150, 185))
        else:
            app.txt(scr, tiny, "Click a planet to select it. Settle worlds of other stars from their own system view.", (r.x + 104, r.y + 72),
                    (140, 150, 185))
        pill(app, scr, sm, pygame.Rect(bx - 150, r.y + 12, 150, 34), "GALAXY MAP", (lambda: _to_galaxy(app, k)))
        return
    out = describe(app, k, b)
    name, col, sub, lines = out
    pic = body_pic(app, b, _level(b, state_of(g, b)))
    size = 76
    big_pic = pic if pic.get_width() >= size else pygame.transform.smoothscale(pic, (size, size))
    scr.blit(glow(52, scale_c(col, 0.3)), (r.x + 48 - 52, r.centery - 52), special_flags=ADD)
    scr.blit(pygame.transform.smoothscale(big_pic, (size, size)) if big_pic.get_width() != size else big_pic,
             (r.x + 48 - size // 2, r.centery - size // 2))
    app.txt(scr, med, name, (r.x + 104, r.y + 10), col)
    app.txt(scr, tiny, sub, (r.x + 104, r.y + 36), (170, 180, 210))
    for i, (t, c) in enumerate(lines[:2]):
        app.txt(scr, tiny, t, (r.x + 104, r.y + 56 + i * 18), c)
    label, fn, enabled = primary(app, b)
    rect = pygame.Rect(bx - 150, r.y + 12, 150, 38)
    hot = enabled and rect.collidepoint(app.mouse) and not _touch()
    c = (60, 130, 90) if enabled else (38, 40, 52)
    pygame.draw.rect(scr, tuple(min(255, v + 25) for v in c) if hot else c, rect, border_radius=8)
    pygame.draw.rect(scr, (140, 230, 170) if enabled else (62, 64, 80), rect, 1, border_radius=8)
    app.txt(scr, sm, label, rect.center, (240, 255, 245) if enabled else (120, 122, 140), "center")
    if enabled and fn is not None:
        app.orb_btns.append((rect, fn))
    pill(app, scr, tiny, pygame.Rect(bx - 150, r.y + 58, 150, 26), "SHOW THE STAR", (lambda: setattr(app, "sys_sel", None)))


# ------------------------------------------------------------------ clicks
def click(app, pos, grow=0):
    """A click in the system view: the buttons first, then a body (a second click on one you hold goes there), then the star. A
    finger is fatter than a pointer: grow widens what counts as a hit."""
    for rect, fn in reversed(app.orb_btns):
        if rect.inflate(grow, grow).collidepoint(pos):
            fn()
            return True
    if not area(app).collidepoint(pos) or card_rect(app).collidepoint(pos):
        return False
    k = current_star(app)
    best, bd = None, 1e9
    for x, y, r, key in app.orb_hits:
        d = math.hypot(pos[0] - x, pos[1] - y)
        if d < r + 10 + 2 * grow and d < bd:
            best, bd = key, d
    if best is None:
        return False
    if best == "star":
        app.sys_sel = None
        return True
    b = body_of(k, best)
    if app.sys_sel == best and b is not None and state_of(app.g, b) in ("here", "owned"):
        go_to(app, b)
    else:
        app.sys_sel = best
    return True


def select_next(app, step):
    """Left / right keys: the next or previous body."""
    k = current_star(app)
    keys = [b["key"] for b in bodies(k)]
    if not keys:
        return
    if app.sys_sel in keys:
        i = (keys.index(app.sys_sel) + step) % len(keys)
    else:
        i = 0 if step > 0 else len(keys) - 1
    app.sys_sel = keys[i]
