"""The planets of the other star systems: what you find when you liberate a star.

Pure data and logic (no pygame). A system's worlds are not stored in the save: they are worked out from the system itself,
the same way every time, so liberating a star always reveals the same planets. The ~30 real stars of the game that have
confirmed planets in the Open Exoplanet Catalogue (assets/worlds.json, see tools/make_worlds.py) show those real planets;
every other star gets a generated system that fits its kind (a red dwarf, a giant, a pulsar...). A world is a dict:

    sys     the system it orbits (index into galaxy.STARS)        name    "TRAPPIST-1 e" (real) or "Cen 1990 III" (generated)
    kind    one of KINDS                                          real    True for a confirmed planet of the catalogue
    r, m    radius and mass in Earth radii / masses               t       temperature in kelvin
    per, a  year in days, distance from its star in AU            year    the year it was found (real worlds only)
    ring    a ringed giant                                        seed    for its picture
"""
import json
import math
import random
import zlib

import galaxy
import resources

with open(resources.resource("assets/worlds.json")) as _f:
    REAL = json.load(_f)

KINDS = ["temperate", "ocean", "rocky", "desert", "ice", "lava", "dwarf", "mini", "ice_giant", "gas"]
KIND_NAMES = dict(temperate="Temperate world", ocean="Ocean world", rocky="Rocky world", desert="Desert world", ice="Ice world",
                  lava="Lava world", dwarf="Dwarf planet", mini="Sub-Neptune", ice_giant="Ice giant", gas="Gas giant")
KIND_BLURB = dict(
    temperate="Mild air, liquid water, green land: a world one could live on.",
    ocean="One global ocean under a thick sky.",
    rocky="Bare rock, craters and no air to speak of.",
    desert="Scorched dunes under a harsh sun.",
    ice="Frozen: ice over rock, a pale and silent world.",
    lava="So close to its star that its surface is molten.",
    dwarf="A small cold body, too small to clear its orbit.",
    mini="A deep hazy atmosphere over a small core.",
    ice_giant="A cold giant of water, ammonia and methane ices.",
    gas="A giant of hydrogen and helium, banded by storms.")
GROUPS = [("all", "All"), ("habitable", "Habitable"), ("rocky", "Rocky"), ("giant", "Giants")]
GROUP_OF = dict(temperate="habitable", ocean="habitable", rocky="rocky", desert="rocky", ice="rocky", lava="rocky", dwarf="rocky",
                mini="giant", ice_giant="giant", gas="giant")
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]

# star kind -> (luminosity in suns, mass in suns) and how many planets it has: (mean, spread, least, most). Kinds that are not
# a star (a nebula, a cluster, a black hole) have no worlds.
STAR = {"Red dwarf": (0.02, 0.3), "Orange dwarf": (0.25, 0.75), "Yellow dwarf": (1.0, 1.0), "White star": (10.0, 1.8),
        "Binary system": (1.5, 1.2), "Brown dwarf": (0.0005, 0.06), "White dwarf": (0.002, 0.6), "Red giant": (100.0, 1.2),
        "Blue giant": (8000.0, 15.0), "Supergiant": (30000.0, 20.0), "Neutron star": (0.01, 1.4), "Pulsar": (0.01, 1.4)}
COUNT = {"Red dwarf": (2.6, 1.4, 0, 6), "Orange dwarf": (3.2, 1.5, 0, 7), "Yellow dwarf": (3.6, 1.6, 0, 8), "White star": (2.8, 1.4, 0, 6),
         "Binary system": (3.4, 1.6, 0, 8), "Brown dwarf": (1.2, 1.0, 0, 3), "White dwarf": (1.1, 1.0, 0, 3),
         "Red giant": (1.5, 1.0, 0, 4), "Blue giant": (0.8, 0.9, 0, 3), "Supergiant": (0.5, 0.8, 0, 2),
         "Neutron star": (0.7, 0.8, 0, 2), "Pulsar": (1.4, 1.0, 0, 3)}
T_LOW, T_HIGH = 45.0, 1250.0                   # the temperatures of generated worlds (log-uniform)


# ------------------------------------------------------------------ sizes
def radius_from_mass(m):
    """Earth radii of a planet of m Earth masses (a rough fit through Earth, Neptune and Jupiter)."""
    if m < 2:
        return max(0.2, m ** 0.3)
    if m < 25:
        return 1.23 * (m / 2) ** 0.58
    return min(16.0, 5.3 * (m / 25) ** 0.3)


def mass_from_radius(r):
    if r < 1.23:
        return r ** 3.33
    if r < 5.3:
        return 2 * (r / 1.23) ** (1 / 0.58)
    return 25 * (r / 5.3) ** (1 / 0.3)


def classify(r, t, roll):
    """The kind of a world from its radius (Earth radii), temperature (K) and a 0..1 roll that settles the rest."""
    if r >= 6:
        return "gas"
    if r >= 3.2:
        return "ice_giant"
    if r >= 1.8:
        return "mini"
    if r < 0.4:
        return "dwarf"
    if t >= 1000:
        return "lava"
    if t >= 330:
        return "desert" if r >= 0.7 else "rocky"
    if t >= 210:
        if r < 0.55:
            return "rocky"
        return "ocean" if (r > 1.25 and roll < 0.6) or roll < 0.2 else "temperate"
    return "ice" if roll < 0.7 else "rocky"


def star_scale(star):
    return STAR.get(star["kind"], (1.0, 1.0))


def temperature(lum, a):
    """Equilibrium temperature (K) at a AU from a star of lum suns, for an albedo of 0.3."""
    return 278.0 * lum ** 0.25 / math.sqrt(max(a, 1e-4))


def distance(lum, t):
    return (278.0 * lum ** 0.25 / max(t, 1.0)) ** 2


def year_days(a, mass):
    return 365.25 * math.sqrt(a ** 3 / max(mass, 0.05))


# ------------------------------------------------------------------ the worlds of a system
_CACHE = {}


def _real_world(k, star, row, rng, lum, smass):
    name, r, m, t, per, a, year = row
    if a is None and per is not None:
        a = (smass * (per / 365.25) ** 2) ** (1 / 3)
    if t is None and a:
        t = temperature(lum, a)
    if t is None:
        t = math.exp(rng.uniform(math.log(T_LOW), math.log(T_HIGH)))
    if a is None:
        a = distance(lum, t)
    if per is None:
        per = year_days(a, smass)
    if r is None and m is not None:
        r = radius_from_mass(m)
    if m is None and r is not None:
        m = mass_from_radius(r)
    if r is None:                                           # nothing known of its size: a typical rocky world
        r = max(0.45, min(1.7, math.exp(rng.gauss(0.0, 0.3))))
        m = mass_from_radius(r)
    return dict(sys=k, name=name, kind=classify(r, t, rng.random()), r=r, m=m, t=t, per=per, a=a, real=True, year=year)


def _made_world(k, star, rng, lum, smass):
    t = math.exp(rng.uniform(math.log(T_LOW), math.log(T_HIGH)))
    roll = rng.random()
    if t > 180:                                             # inside the frost line: mostly rock, some Neptunes, hot Jupiters
        if roll < 0.70:
            r = max(0.3, min(1.9, math.exp(rng.gauss(-0.1, 0.45))))
        elif roll < 0.92:
            r = rng.uniform(1.8, 3.4)
        else:
            r = rng.uniform(8.0, 14.0)
    else:                                                   # beyond it: giants and ice
        if roll < 0.35:
            r = rng.uniform(6.0, 13.0)
        elif roll < 0.65:
            r = rng.uniform(3.2, 5.6)
        else:
            r = max(0.3, min(1.9, math.exp(rng.gauss(-0.1, 0.45))))
    a = distance(lum, t)
    return dict(sys=k, name=None, kind=classify(r, t, rng.random()), r=r, m=mass_from_radius(r), t=t, per=year_days(a, smass), a=a,
                real=False, year=None)


def planets_of(k):
    """The worlds of system k, nearest to their star first (a tuple of dicts; empty for Sol and for places that are not a star)."""
    got = _CACHE.get(k)
    if got is not None:
        return got
    star = galaxy.STARS[k]
    lum, smass = star_scale(star)
    rng = random.Random(f"worlds:{k}:{star['name']}")
    worlds = []
    if k and star["name"] in REAL:
        worlds = [_real_world(k, star, row, rng, lum, smass) for row in REAL[star["name"]]]
    elif k and star["kind"] in COUNT:
        mu, sd, lo, hi = COUNT[star["kind"]]
        n = max(lo, min(hi, round(rng.gauss(mu, sd))))
        worlds = [_made_world(k, star, rng, lum, smass) for _ in range(n)]
    worlds.sort(key=lambda w: w["a"])
    for i, w in enumerate(worlds):
        w["idx"] = i
        if w["name"] is None:
            w["name"] = f"{star['name']} {ROMAN[i]}"
        w["seed"] = zlib.crc32(w["name"].encode()) & 0x7FFFFFFF
        w["ring"] = w["kind"] == "gas" and (w["seed"] % 100) < 30
    got = _CACHE[k] = tuple(worlds)
    return got


def count_of(k):
    return len(planets_of(k))


# ------------------------------------------------------------------ what you have found
_STATS = {"sig": None}


def sig(conquered):
    """A cheap fingerprint of the set of systems you hold, to know when a cached answer is out of date."""
    return (len(conquered), sum(conquered), sum(k * k for k in conquered))


def stats(conquered):
    """The worlds of every system you hold, counted: total, systems with worlds, per kind, real ones, temperate ones. Cached."""
    key = sig(conquered)
    if _STATS["sig"] != key:
        by_kind = dict.fromkeys(KINDS, 0)
        total = systems = real = 0
        for k in conquered:
            ws = planets_of(k)
            if ws:
                systems += 1
            total += len(ws)
            for w in ws:
                by_kind[w["kind"]] += 1
                real += w["real"]
        _STATS.update(sig=key, total=total, systems=systems, real=real, by_kind=by_kind,
                      habitable=by_kind["temperate"] + by_kind["ocean"], kinds=sum(1 for n in by_kind.values() if n))
    return _STATS


def found(conquered, group="all", sysid=None):
    """The worlds you have found, nearest systems first: (system, world) pairs, filtered by group (GROUPS) or by one system."""
    out = []
    for k in sorted(conquered, key=lambda q: (galaxy.STARS[q]["d"], q)):
        if sysid is not None and k != sysid:
            continue
        for w in planets_of(k):
            if group == "all" or GROUP_OF[w["kind"]] == group:
                out.append(w)
    return out


def news(k):
    """The line for the toast when system k is liberated, or None if it has no worlds."""
    ws = planets_of(k)
    if not ws:
        return None
    star = galaxy.STARS[k]["name"]
    nice = sum(1 for w in ws if GROUP_OF[w["kind"]] == "habitable")
    s = f"{len(ws)} world{'s' if len(ws) > 1 else ''} found at {star}"
    return s + (f" - {nice} habitable" if nice else "")


# ------------------------------------------------------------------ words
def year_text(days):
    if days < 2:
        return f"{days * 24:.0f} hours"
    if days < 500:
        return f"{days:.1f} days" if days < 100 else f"{days:.0f} days"
    return f"{days / 365.25:.1f} years"


def temp_text(t):
    return f"{t:.0f} K ({t - 273.15:.0f} C)"


def size_text(r, m):
    def x(v):
        return f"{v:.2f}" if v < 10 else f"{v:.0f}"
    if r >= 6:
        return f"{r / 11.209:.2f} Jupiter radii, {m / 317.83:.2f} Jupiter masses"
    return f"{x(r)} Earth radii, {x(m)} Earth masses"


def lines(w):
    """The facts of a world, for its card: (label, value) pairs."""
    star = galaxy.STARS[w["sys"]]
    out = [("Type", KIND_NAMES[w["kind"]] + (" with rings" if w["ring"] else "")), ("Size", size_text(w["r"], w["m"])),
           ("Temperature", temp_text(w["t"])), ("Year", year_text(w["per"])),
           ("Orbit", f"{w['a']:.3g} AU from its {star['kind'].lower()}"),
           ("System", f"{star['name']}, {galaxy.fmt_ly(star['d'])} from the Sun")]
    return out


def origin(w):
    return f"Confirmed exoplanet, found in {w['year']}." if w["real"] and w["year"] else (
        "Confirmed exoplanet." if w["real"] else "Surveyed by your scouts.")


# ------------------------------------------------------------------ achievements
def achievements():
    """The achievements of the worlds you find, as core builds them: dicts with id, name, desc, cat, tier, cond, prog, secret."""
    A = []

    def add(name, desc, tier, cond, prog):
        A.append(dict(id=name, name=name, desc=desc, cat="Galaxy", tier=tier, cond=cond, prog=prog, secret=False))

    def ms(rows, descf, get):
        for name, t, tier in rows:
            add(name, descf(t), tier, lambda g, t=t: get(g) >= t, lambda g, t=t: (min(get(g), t), t))

    ms([("First Light", 1, "bronze"), ("Survey Team", 10, "bronze"), ("Cartographer of Worlds", 50, "silver"),
        ("Planet Hunter", 200, "gold"), ("A Thousand Worlds", 1000, "gold"), ("Worldbuilder", 5000, "platinum")],
       lambda t: f"Find {t:,} world{'s' if t > 1 else ''} in the systems you liberate", lambda g: stats(g.conquered)["total"])
    ms([("Goldilocks", 1, "bronze"), ("Garden Worlds", 10, "silver"), ("A Home for Everyone", 50, "gold")],
       lambda t: f"Find {t} habitable world{'s' if t > 1 else ''}: temperate or ocean", lambda g: stats(g.conquered)["habitable"])
    ms([("Known Worlds", 25, "silver"), ("Exoplanet Archivist", 80, "gold")],
       lambda t: f"Find {t} confirmed exoplanets of real stars", lambda g: stats(g.conquered)["real"])
    ms([("Planetary Zoo", len(KINDS), "gold")],
       lambda t: f"Find every one of the {t} kinds of world", lambda g: stats(g.conquered)["kinds"])
    t1 = galaxy.BY_NAME.get("TRAPPIST-1")
    if t1 is not None:
        add("Seven Sisters", "Liberate TRAPPIST-1 and find its seven worlds", "silver", lambda g: t1 in g.conquered,
            lambda g: (7 if t1 in g.conquered else 0, 7))
    return A
