"""The galaxy the game is played on: the real Milky Way, thousands of star systems you can conquer.

Pure data and logic (no pygame). assets/galaxy.json holds the systems (see tools/make_galaxy.py): about 140 real stars and
objects at their real distances and directions, and thousands of generated systems spread over the real shape of the
galaxy. This module gives every system its power, its reward and its place in the lanes, and keeps track of which
systems your jump drive can reach (class Reach).

Coordinates are light-years, centred on the Galactic Centre, x to the right and y down: the Sun (system 0, "Sol") is at
the bottom of the map. System ids are indices into STARS; the same list is core.SECTORS.
"""
import json
import math

import resources

with open(resources.resource("assets/galaxy.json")) as _f:
    _D = json.load(_f)

GC_DIST = _D["gc"]                           # light-years from the Sun to the Galactic Centre
KINDS = _D["kinds"]
ARM_NAMES = _D["arms"]
SOL = 0
CORE_R = 4200.0                              # the Devourer's realm: this close to the Galactic Centre

# ------------------------------------------------------------------ what a system is worth
# kind of system: (what its conquest improves, how much)
KIND_BONUS = {
    "Red dwarf": ("ore", 1.0), "Orange dwarf": ("ore", 1.2), "Yellow dwarf": ("cred", 1.2), "White star": ("disc", 1.0),
    "Binary system": ("fp", 1.0), "Brown dwarf": ("click", 1.0), "White dwarf": ("sci", 1.0), "Red giant": ("ore", 1.8),
    "Blue giant": ("cred", 1.8), "Supergiant": ("fp", 1.8), "Wolf-Rayet star": ("fp", 1.5), "Neutron star": ("fp", 2.0),
    "Pulsar": ("sci", 2.0), "Black hole": ("dm", 2.0), "Nebula": ("crate", 1.5), "Star cluster": ("ore", 2.2),
    "Globular cluster": ("ore", 2.5), "Supernova remnant": ("sci", 1.6),
}
CAT_TEXT = {"ore": "production", "cred": "credit income", "sci": "science income", "fp": "fleet power", "disc": "cheaper ships",
            "click": "click power", "dm": "Dark Matter gain", "crate": "crate rate"}
CAT_SCALE = {"ore": 1.0, "cred": 1.0, "sci": 1.0, "fp": 1.0, "disc": 0.45, "click": 4.0, "dm": 0.25, "crate": 0.4}
BONUS_UNIT = 0.001                          # the bonus of a typical system at the weakest end; it grows with the system's power

# hand-made rewards of famous places: name -> (effects, description). The first fifteen are the original sectors.
LANDMARKS = {
    "Oort Cloud": ([("disc", 0.05)], "Ships 5% cheaper everywhere"),
    "Alpha Centauri": ([("ore", 1.3)], "All production x1.3"),
    "Barnard's Star": ([("cred", 2)], "Credit income x2"),
    "Wolf 359": ([("fp", 1.5)], "Fleet power x1.5"),
    "Sirius": ([("sci", 2)], "Science income x2"),
    "Epsilon Eridani": ([("ore", 1.5)], "All production x1.5"),
    "Tau Ceti": ([("crate", 0.5), ("crate_pay", 2)], "Crates 50% more often, pay x2"),
    "Vega": ([("dm", 1.25)], "Dark Matter gain x1.25"),
    "Procyon": ([("click", 10)], "Clicks x10"),
    "Altair": ([("ore", 2)], "All production x2"),
    "Betelgeuse": ([("disc", 0.10)], "Ships 10% cheaper everywhere"),
    "Orion Nebula": ([("dm", 1.5), ("fp", 1.5)], "Dark Matter gain x1.5, fleet power x1.5"),
    "Crab Nebula": ([("ore", 2)], "All production x2"),
    "Galactic Core": ([("ore", 3), ("fp", 2)], "All production x3, fleet power x2"),
    "The Void Throne": ([("ore", 5), ("sd", 1.5)], "All production x5, Stardust gain x1.5  -  the final boss"),
    # more of the sky's famous places
    "Proxima Centauri": ([("click", 2)], "Clicks x2"),
    "Luhman 16": ([("sci", 1.2)], "Science income x1.2"),
    "Gliese 581": ([("disc", 0.02)], "Ships 2% cheaper everywhere"),
    "Fomalhaut": ([("crate", 0.25)], "Crates 25% more often"),
    "Pollux": ([("fp", 1.2)], "Fleet power x1.2"),
    "Arcturus": ([("ore", 1.2)], "All production x1.2"),
    "TRAPPIST-1": ([("cred", 1.3)], "Credit income x1.3"),
    "Capella": ([("sci", 1.3)], "Science income x1.3"),
    "Kepler-452": ([("disc", 0.03)], "Ships 3% cheaper everywhere"),
    "Achernar": ([("fp", 1.2)], "Fleet power x1.2"),
    "Canopus": ([("ore", 1.25)], "All production x1.25"),
    "Polaris": ([("click", 1.5)], "Clicks x1.5"),
    "Pleiades": ([("cred", 1.4)], "Credit income x1.4"),
    "Antares": ([("fp", 1.25)], "Fleet power x1.25"),
    "Rigel": ([("fp", 1.3)], "Fleet power x1.3"),
    "Tabby's Star": ([("ore", 1.3)], "A megastructure? All production x1.3"),
    "Deneb": ([("ore", 1.4)], "All production x1.4"),
    "Helix Nebula": ([("crate_pay", 1.5)], "Crates pay x1.5"),
    "Vela Pulsar": ([("sci", 1.5)], "Science income x1.5"),
    "Geminga": ([("sci", 1.25)], "Science income x1.25"),
    "Cygnus X-1": ([("dm", 1.2)], "Dark Matter gain x1.2"),
    "Eta Carinae": ([("ore", 1.5), ("fp", 1.2)], "All production x1.5, fleet power x1.2"),
    "Carina Nebula": ([("crate", 0.3)], "Crates 30% more often"),
    "Eagle Nebula": ([("dm", 1.2)], "Dark Matter gain x1.2"),
    "Cassiopeia A": ([("sci", 1.5)], "Science income x1.5"),
    "Tycho's Supernova": ([("sci", 1.3)], "Science income x1.3"),
    "Westerlund 1": ([("fp", 1.4)], "Fleet power x1.4"),
    "Omega Centauri": ([("ore", 1.5)], "All production x1.5"),
    "Kepler's Supernova": ([("sci", 1.3)], "Science income x1.3"),
    "SS 433": ([("dm", 1.2)], "Dark Matter gain x1.2"),
    "Arches Cluster": ([("fp", 1.3)], "Fleet power x1.3"),
    "Sagittarius B2": ([("ore", 1.4)], "All production x1.4"),
    "M13": ([("ore", 1.2)], "All production x1.2"),
}
BONUS_EXP = 0.12      # how fast a system's bonus grows with its power (per log10 step)
SUM_POW = 0.6      # the sum of the small bonuses counts to this power (below 1: diminishing returns)
LM_SOFT = 0.35          # how much of their face value the extra landmarks give (the original fifteen: all)
FX_TEXT = {"ore": "All production x{v:g}", "cred": "Credit income x{v:g}", "sci": "Science income x{v:g}",
           "fp": "Fleet power x{v:g}", "dm": "Dark Matter gain x{v:g}", "click": "Clicks x{v:g}", "crate_pay": "Crates pay x{v:g}",
           "sd": "Stardust gain x{v:g}", "disc": "Ships {p:g}% cheaper everywhere", "crate": "Crates {p:g}% more often"}
# the sixteen systems of the old fixed map, in their old order: saves from before the Milky Way are converted with this
OLD_SECTORS = ["Sol", "Oort Cloud", "Alpha Centauri", "Barnard's Star", "Wolf 359", "Sirius", "Epsilon Eridani", "Tau Ceti",
               "Vega", "Procyon", "Altair", "Betelgeuse", "Orion Nebula", "Crab Nebula", "Galactic Core", "The Void Throne"]

# ------------------------------------------------------------------ power: how strong the enemy is
KIND_POWER = {"Black hole": 0.3, "Supergiant": 0.2, "Neutron star": 0.15, "Pulsar": 0.1, "Wolf-Rayet star": 0.15,
              "Globular cluster": 0.1, "Star cluster": 0.05, "Nebula": -0.05, "Brown dwarf": -0.1, "Red dwarf": -0.05}
FACTION_POWER = {"pirates": -0.25, "hive": 0.0, "crystal": 0.1, "iron": 0.2, "void": 0.3, "devourer": 0.0}
BOSS_LP = 12.78
# log10 power of the original sectors (kept, because their rewards were balanced against it)
ORIGINAL_LP = dict(zip(OLD_SECTORS[1:], [2.52, 5.14, 6.81, 7.96, 8.53, 8.86, 9.44, 9.79, 10.25, 10.33, 10.72, 11.18, 12.09, 12.3, 12.78]))


def power_log(d):
    """log10 of the enemy fleet power at a distance of d light-years from the Sun (before the per-system extras)."""
    return 2.5 + 10.28 * (math.log10(1.0 + d) / math.log10(1.0 + GC_DIST)) ** 0.9


def _jitter(i):
    h = (i * 2654435761 + 40503) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    return ((h & 0xFFFF) / 65536.0 - 0.5) * 0.3


# ------------------------------------------------------------------ build the systems
_names = _D["names"]
N = len(_names)
XS, YS, ZS = _D["x"], _D["y"], _D["z"]
STARS = []
BY_NAME = {}
_real = set(_D["real"])
for _i in range(N):
    _kind = KINDS[_D["kind"][_i]]
    _fac = _D["factions"][_D["fac"][_i]]
    _x, _y, _z = XS[_i], YS[_i], ZS[_i]
    _d = math.dist((_x, _y, _z), (0.0, GC_DIST, 0.0))
    _name = _names[_i]
    _lp = power_log(_d) + KIND_POWER.get(_kind, 0.0) + FACTION_POWER[_fac] + (_jitter(_i) if _i else 0.0)
    if _fac == "devourer":
        _lp = min(_lp, BOSS_LP - 0.08)
    if _name in ORIGINAL_LP:
        _lp = ORIGINAL_LP[_name]                   # the original fifteen keep their fortress-strength power
    elif _name in LANDMARKS and _i:
        _lp += 0.3
    if _fac == "devourer":
        _lp = min(_lp, BOSS_LP - 0.08)
    if _name == "The Void Throne":
        _lp = BOSS_LP
    _star = dict(id=_i, name=_name, kind=_kind, faction=_fac, x=_x, y=_y, z=_z, pos=(_x, _y), d=_d, lp=_lp,
                 region=_D["regions"][_D["reg"][_i]], con=_D["constellations"][_D["con"][_i]], real=_i in _real)
    if _name in LANDMARKS:
        _fx = [tuple(e) for e in LANDMARKS[_name][0]]
        _desc = LANDMARKS[_name][1]
        if _name not in ORIGINAL_LP and LM_SOFT != 1.0:
            _fx = [(e[0], e[1] * LM_SOFT) if e[0] in ("disc", "crate") else (e[0], 1 + (e[1] - 1) * LM_SOFT) for e in _fx]
            _desc = ", ".join(FX_TEXT[e[0]].format(v=round(e[1], 3), p=round(e[1] * 100, 1)) for e in _fx)
        _star["fx"], _star["desc"] = _fx, _desc
        _star["landmark"] = True
    else:
        _cat, _m = KIND_BONUS[_kind]
        _w = BONUS_UNIT * 10 ** (BONUS_EXP * (_lp - 2.5)) * _m * CAT_SCALE[_cat]
        _star["fx"], _star["desc"] = [("gal_" + _cat, _w)], f"{_kind}: {CAT_TEXT[_cat]} +{_w * 100:.2f}%"
        _star["landmark"] = False
    if _i == SOL:
        _star["fx"], _star["desc"] = [], "Your home system"
    STARS.append(_star)
    BY_NAME[_name] = _i
NSTARS = N
BOSS = BY_NAME["The Void Throne"]
CORE = BY_NAME["Galactic Core"]
LANDMARK_IDS = [s["id"] for s in STARS if s["real"] and s["id"]]

LINKS = [[] for _ in range(N)]
for _a, _b in zip(_D["edges"][0::2], _D["edges"][1::2]):
    LINKS[_a].append(_b)
    LINKS[_b].append(_a)
EDGES = list(zip(_D["edges"][0::2], _D["edges"][1::2]))
del _D


# ------------------------------------------------------------------ distance and the jump drive
def dist(a, b):
    return math.sqrt((XS[a] - XS[b]) ** 2 + (YS[a] - YS[b]) ** 2 + (ZS[a] - ZS[b]) ** 2)


JUMP_BASE = 6.0                              # light-years at jump drive level 0
JUMP_GROWTH = 1.5                            # per level
SCAN_FACTOR = 2.5                            # you see systems up to this many jump ranges away from your territory


def jump_range(level):
    return JUMP_BASE * JUMP_GROWTH ** level


def fmt_ly(d):
    if d < 10:
        return f"{d:.1f} ly"
    if d < 1000:
        return f"{d:.0f} ly"
    if d < 1e5:
        return f"{d:,.0f} ly"
    return f"{d / 1000:.0f}k ly"


class Reach:
    """Which systems the jump drive can reach from the systems you hold, and which you can see (scan).

    `reach[k]` is 1 when some held system is within the jump range of k; `scan[k]` when one is within SCAN_FACTOR times the
    range. Conquering a system updates both in one pass over the galaxy; changing the range or losing a system rebuilds them
    with a grid of the held systems, which stays fast with thousands of them."""

    def __init__(self):
        self.range = 0.0
        self.held = set()
        self.reach = bytearray(N)
        self.scan = bytearray(N)
        self.version = 0                      # changes whenever reach or scan do

    def set(self, held, rng_ly):
        self.held = set(held)
        self.range = rng_ly
        self.rebuild()

    def rebuild(self):
        R, S = self.range, self.range * SCAN_FACTOR
        reach, scan = bytearray(N), bytearray(N)
        cs = S if S > 0 else 1.0
        grid = {}
        for k in self.held:
            grid.setdefault((int(XS[k] // cs), int(YS[k] // cs)), []).append(k)
        R2, S2 = R * R, S * S
        for i in range(N):
            cx, cy = int(XS[i] // cs), int(YS[i] // cs)
            xi, yi, zi = XS[i], YS[i], ZS[i]
            seen = False
            for ix in (-1, 0, 1):
                for iy in (-1, 0, 1):
                    for k in grid.get((cx + ix, cy + iy), ()):
                        d2 = (xi - XS[k]) ** 2 + (yi - YS[k]) ** 2 + (zi - ZS[k]) ** 2
                        if d2 <= R2:
                            reach[i] = scan[i] = 1
                            seen = True
                            break
                        if d2 <= S2:
                            scan[i] = 1
                    if seen:
                        break
                if seen:
                    break
        self.reach, self.scan = reach, scan
        self.version += 1

    def add(self, k):
        if k in self.held:
            return
        self.held.add(k)
        R2, S2 = self.range ** 2, (self.range * SCAN_FACTOR) ** 2
        xk, yk, zk = XS[k], YS[k], ZS[k]
        reach, scan = self.reach, self.scan
        for i in range(N):
            d2 = (XS[i] - xk) ** 2 + (YS[i] - yk) ** 2 + (ZS[i] - zk) ** 2
            if d2 <= S2:
                scan[i] = 1
                if d2 <= R2:
                    reach[i] = 1
        self.version += 1

    def discard(self, k):
        if k in self.held:
            self.held.discard(k)
            self.rebuild()

    def nearest_held(self, k):
        """The held system closest to k, and its distance."""
        best, bd = None, 1e30
        for h in self.held:
            d = dist(h, k)
            if d < bd:
                best, bd = h, d
        return best, bd


def within(k, rng_ly):
    """Every system within rng_ly of system k (not k itself)."""
    xk, yk, zk, r2 = XS[k], YS[k], ZS[k], rng_ly * rng_ly
    return [i for i in range(N) if i != k and (XS[i] - xk) ** 2 + (YS[i] - yk) ** 2 + (ZS[i] - zk) ** 2 <= r2]


def empire_mult(cat, total):
    """The multiplier (or addition, for discounts and crates) the generated systems give in a category."""
    return (1.0 + total) ** SUM_POW - 1.0 if total > 0 else 0.0


def empire_bonus(held):
    """The sums of the small bonuses of generated systems, per category (the landmarks have their own effects)."""
    out = {}
    for k in held:
        for e in STARS[k]["fx"]:
            if e[0].startswith("gal_"):
                out[e[0][4:]] = out.get(e[0][4:], 0.0) + e[1]
    return out


def find(text):
    """Systems whose name contains the text (case-insensitive), landmarks first."""
    t = text.strip().lower()
    if not t:
        return []
    hits = [s["id"] for s in STARS if t in s["name"].lower()]
    return sorted(hits, key=lambda i: (not STARS[i]["real"], STARS[i]["name"].lower().find(t), STARS[i]["d"]))[:40]
