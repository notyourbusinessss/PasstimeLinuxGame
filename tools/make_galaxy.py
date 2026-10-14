"""Builds assets/galaxy.json: the Milky Way the game is played on.

    python tools/make_galaxy.py            # rewrites assets/galaxy.json (deterministic: the same file every time)
    python tools/make_galaxy.py --preview out.png

What is in it
  * about 130 REAL stars and objects, at their real distances and directions (the Sun's neighbours, the bright
    stars, famous nebulae, pulsars, black holes, supernova remnants, globular clusters and the Galactic Centre),
    placed from their right ascension, declination and distance;
  * thousands of generated systems between them, spread over the real shape of the galaxy (four spiral arms, the bar
    and bulge, the Orion Spur the Sun sits in), thinning out with distance so that every size of jump has plenty of
    targets: dense near the Sun, sparse far away;
  * which faction holds each system, and the lanes (each system's nearest neighbours).

The Sun is at the bottom of the map and the Galactic Centre in the middle, as in the usual picture of the galaxy seen from
above. Coordinates are in light-years, centred on the Galactic Centre, x to the right and y downwards.
"""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from milkyway import (ARM_NAMES, GC_DIST, arm_strength, bar_strength, density, from_map, longitude, region_of)
OUT = os.path.join(HERE, "..", "assets", "galaxy.json")

FACTIONS = ["pirates", "hive", "crystal", "iron", "void", "devourer"]
KINDS = ["Red dwarf", "Orange dwarf", "Yellow dwarf", "White star", "Binary system", "Brown dwarf", "White dwarf",
         "Red giant", "Blue giant", "Supergiant", "Wolf-Rayet star", "Neutron star", "Pulsar", "Black hole", "Nebula",
         "Star cluster", "Globular cluster", "Supernova remnant"]
CONSTELLATIONS = [  # galactic longitude as seen from the Sun, name, abbreviation
    (0, "Sagittarius", "Sgr"), (12, "Scutum", "Sct"), (30, "Aquila", "Aql"), (45, "Vulpecula", "Vul"),
    (60, "Cygnus", "Cyg"), (80, "Cygnus", "Cyg"), (95, "Cepheus", "Cep"), (110, "Cassiopeia", "Cas"),
    (135, "Cassiopeia", "Cas"), (150, "Perseus", "Per"), (170, "Auriga", "Aur"), (185, "Taurus", "Tau"),
    (200, "Gemini", "Gem"), (215, "Monoceros", "Mon"), (230, "Canis Major", "CMa"), (245, "Puppis", "Pup"),
    (260, "Vela", "Vel"), (275, "Vela", "Vel"), (290, "Carina", "Car"), (305, "Crux", "Cru"),
    (320, "Centaurus", "Cen"), (335, "Norma", "Nor"), (348, "Scorpius", "Sco")]

# name, kind, right ascension (hours), declination (degrees), distance (light-years)
REAL = [
    ("Oort Cloud", "Brown dwarf", None, None, 0.8),
    ("Proxima Centauri", "Red dwarf", 14.495, -62.68, 4.24), ("Alpha Centauri", "Binary system", 14.66, -60.83, 4.37),
    ("Barnard's Star", "Red dwarf", 17.963, 4.69, 5.96), ("Luhman 16", "Brown dwarf", 10.82, -53.32, 6.5),
    ("WISE 0855-0714", "Brown dwarf", 8.92, -7.24, 7.43), ("Wolf 359", "Red dwarf", 10.94, 7.01, 7.86),
    ("Lalande 21185", "Red dwarf", 11.05, 35.97, 8.31), ("Sirius", "Binary system", 6.752, -16.72, 8.6),
    ("Luyten 726-8", "Binary system", 1.65, -17.95, 8.73), ("Ross 154", "Red dwarf", 18.83, -23.83, 9.69),
    ("Ross 248", "Red dwarf", 23.70, 44.18, 10.3), ("Epsilon Eridani", "Orange dwarf", 3.548, -9.46, 10.5),
    ("Lacaille 9352", "Red dwarf", 23.09, -35.85, 10.7), ("Ross 128", "Red dwarf", 11.80, 0.80, 11.0),
    ("EZ Aquarii", "Red dwarf", 22.64, -15.3, 11.3), ("61 Cygni", "Binary system", 21.115, 38.75, 11.4),
    ("Procyon", "Binary system", 7.655, 5.22, 11.46), ("Struve 2398", "Binary system", 18.71, 59.63, 11.5),
    ("Groombridge 34", "Binary system", 0.29, 44.02, 11.6), ("DX Cancri", "Red dwarf", 8.50, 26.78, 11.7),
    ("Tau Ceti", "Yellow dwarf", 1.734, -15.94, 11.9), ("Epsilon Indi", "Orange dwarf", 22.05, -56.79, 11.87),
    ("YZ Ceti", "Red dwarf", 1.20, -16.99, 12.1), ("Luyten's Star", "Red dwarf", 7.45, 5.23, 12.35),
    ("Teegarden's Star", "Red dwarf", 2.89, 16.88, 12.5), ("Kapteyn's Star", "Red dwarf", 5.19, -44.95, 12.8),
    ("Lacaille 8760", "Red dwarf", 21.29, -38.87, 12.95), ("Kruger 60", "Binary system", 22.46, 57.7, 13.1),
    ("Ross 614", "Binary system", 6.61, -2.81, 13.4), ("Wolf 1061", "Red dwarf", 16.51, -12.66, 14.05),
    ("Van Maanen's Star", "White dwarf", 0.82, 5.39, 14.1), ("Gliese 1", "Red dwarf", 0.08, -37.36, 14.2),
    ("Wolf 424", "Binary system", 12.56, 9.02, 14.3), ("TZ Arietis", "Red dwarf", 2.0, 13.05, 14.5),
    ("Gliese 687", "Red dwarf", 17.58, 68.34, 14.8), ("LHS 292", "Red dwarf", 10.8, 1.2, 14.8),
    ("Gliese 674", "Red dwarf", 17.48, -46.9, 14.8), ("GJ 1245", "Red dwarf", 19.89, 44.4, 15.0),
    ("Gliese 876", "Red dwarf", 22.89, -14.26, 15.2), ("Gliese 832", "Red dwarf", 21.56, -49.0, 16.1),
    ("40 Eridani", "Binary system", 4.25, -7.65, 16.3), ("70 Ophiuchi", "Binary system", 18.07, 2.5, 16.6),
    ("Altair", "White star", 19.846, 8.87, 16.7), ("Gliese 229", "Binary system", 6.61, -21.86, 18.8),
    ("Eta Cassiopeiae", "Binary system", 0.82, 57.82, 19.4), ("36 Ophiuchi", "Binary system", 17.25, -26.6, 19.5),
    ("82 Eridani", "Yellow dwarf", 3.32, -43.07, 19.7), ("Delta Pavonis", "Yellow dwarf", 20.14, -66.18, 19.9),
    ("Scholz's Star", "Binary system", 7.2, -4.75, 20.0), ("Gliese 581", "Red dwarf", 15.32, -7.72, 20.4),
    ("Gliese 667", "Red dwarf", 17.30, -34.99, 23.6), ("Vega", "White star", 18.616, 38.78, 25.0),
    ("Fomalhaut", "White star", 22.96, -29.62, 25.1), ("Gliese 436", "Red dwarf", 11.71, 26.7, 31.9),
    ("Pollux", "Red giant", 7.755, 28.03, 33.8), ("Denebola", "White star", 11.82, 14.57, 35.9),
    ("Arcturus", "Red giant", 14.26, 19.18, 36.7), ("Zeta Reticuli", "Binary system", 3.30, -62.5, 39.5),
    ("TRAPPIST-1", "Red dwarf", 23.1, -5.04, 40.7), ("55 Cancri", "Binary system", 8.87, 28.33, 41.0),
    ("HD 40307", "Orange dwarf", 5.89, -60.0, 42.0), ("Capella", "Binary system", 5.278, 45.998, 42.9),
    ("LHS 1140", "Red dwarf", 0.76, -15.27, 49.0), ("51 Pegasi", "Yellow dwarf", 22.96, 20.77, 50.9),
    ("Castor", "Binary system", 7.577, 31.89, 51.0), ("Beta Pictoris", "White star", 5.79, -51.07, 63.0),
    ("Gliese 710", "Orange dwarf", 18.82, -1.94, 63.0), ("Aldebaran", "Red giant", 4.599, 16.51, 65.0),
    ("HD 189733", "Orange dwarf", 20.0, 22.71, 64.5), ("Mizar", "Binary system", 13.4, 54.93, 83.0),
    ("Regulus", "Blue giant", 10.14, 11.97, 79.0), ("Algol", "Binary system", 3.136, 40.96, 90.0),
    ("TOI-700", "Red dwarf", 6.47, -65.58, 101.0), ("K2-18", "Red dwarf", 11.51, 7.59, 124.0),
    ("Achernar", "Blue giant", 1.628, -57.24, 139.0), ("Hyades", "Star cluster", 4.47, 15.87, 153.0),
    ("Eltanin", "Red giant", 17.94, 51.49, 154.0), ("HD 209458", "Yellow dwarf", 22.05, 18.88, 159.0),
    ("Spica", "Blue giant", 13.42, -11.16, 250.0), ("Bellatrix", "Blue giant", 5.419, 6.35, 250.0),
    ("Mira", "Red giant", 2.32, -2.98, 300.0), ("Canopus", "Supergiant", 6.4, -52.7, 310.0),
    ("Acrux", "Blue giant", 12.44, -63.1, 320.0), ("Hadar", "Blue giant", 14.06, -60.37, 390.0),
    ("Polaris", "Supergiant", 2.53, 89.26, 433.0), ("Pleiades", "Star cluster", 3.79, 24.1, 444.0),
    ("Betelgeuse", "Supergiant", 5.92, 7.41, 548.0), ("Antares", "Supergiant", 16.49, -26.43, 550.0),
    ("Kepler-186", "Red dwarf", 19.8, 43.95, 580.0), ("Kepler-22", "Yellow dwarf", 19.28, 47.88, 620.0),
    ("Helix Nebula", "Nebula", 22.49, -20.84, 650.0), ("Geminga", "Pulsar", 6.57, 17.77, 800.0),
    ("Rigel", "Supergiant", 5.242, -8.2, 860.0), ("Vela Pulsar", "Pulsar", 8.58, -45.18, 960.0),
    ("Kepler-62", "Orange dwarf", 18.85, 45.35, 1200.0), ("Kepler-442", "Orange dwarf", 19.0, 39.3, 1200.0),
    ("Dumbbell Nebula", "Nebula", 19.99, 22.72, 1230.0), ("Orion's Belt", "Blue giant", 5.679, -1.94, 1260.0),
    ("Orion Nebula", "Nebula", 5.588, -5.39, 1344.0), ("Kepler-452", "Yellow dwarf", 19.73, 44.28, 1400.0),
    ("Tabby's Star", "White star", 20.10, 44.46, 1470.0), ("Sadr", "Supergiant", 20.37, 40.26, 1800.0),
    ("Ring Nebula", "Nebula", 18.89, 33.03, 2300.0), ("Veil Nebula", "Supernova remnant", 20.76, 30.7, 2400.0),
    ("Deneb", "Supergiant", 20.69, 45.28, 2600.0), ("North America Nebula", "Nebula", 20.98, 44.3, 2600.0),
    ("Cat's Eye Nebula", "Nebula", 17.97, 66.63, 3300.0), ("Lagoon Nebula", "Nebula", 18.06, -24.38, 4100.0),
    ("Trifid Nebula", "Nebula", 18.04, -23.03, 4100.0), ("Cygnus OB2", "Star cluster", 20.56, 41.3, 5000.0),
    ("Rosette Nebula", "Nebula", 6.55, 4.95, 5200.0), ("Omega Nebula", "Nebula", 18.35, -16.18, 5500.0),
    ("Cygnus X-1", "Black hole", 19.97, 35.2, 7200.0), ("Crab Nebula", "Supernova remnant", 5.575, 22.01, 6500.0),
    ("Eagle Nebula", "Nebula", 18.31, -13.82, 7000.0), ("PSR B1919+21", "Pulsar", 19.37, 21.9, 7000.0),
    ("M4", "Globular cluster", 16.39, -26.53, 7200.0), ("Eta Carinae", "Supergiant", 10.75, -59.68, 7500.0),
    ("WR 104", "Wolf-Rayet star", 18.03, -23.62, 8000.0), ("Tycho's Supernova", "Supernova remnant", 0.40, 64.14, 8000.0),
    ("Carina Nebula", "Nebula", 10.73, -59.87, 8500.0), ("M22", "Globular cluster", 18.61, -23.9, 10400.0),
    ("Cassiopeia A", "Supernova remnant", 23.39, 58.81, 11000.0), ("Westerlund 1", "Star cluster", 16.76, -45.85, 12000.0),
    ("47 Tucanae", "Globular cluster", 0.40, -72.08, 14800.0), ("WR 124", "Wolf-Rayet star", 19.19, 16.87, 15000.0),
    ("Omega Centauri", "Globular cluster", 13.45, -47.48, 17090.0), ("Kepler's Supernova", "Supernova remnant", 17.51, -21.49, 17000.0),
    ("SS 433", "Black hole", 19.19, 4.97, 18000.0), ("NGC 3603", "Nebula", 11.25, -61.26, 20000.0),
    ("V838 Monocerotis", "Red giant", 7.07, -3.84, 20000.0), ("M13", "Globular cluster", 16.69, 36.46, 22200.0),
    ("M5", "Globular cluster", 15.31, 2.08, 24500.0), ("Arches Cluster", "Star cluster", 17.76, -28.82, 25000.0),
    ("Sagittarius B2", "Nebula", 17.79, -28.4, 26000.0), ("M92", "Globular cluster", 17.29, 43.14, 26700.0),
    ("M15", "Globular cluster", 21.5, 12.17, 33600.0), ("M3", "Globular cluster", 13.70, 28.38, 33900.0),
]
# the two special places at the middle of the galaxy (placed by hand, around Sagittarius A*)
CENTRE = [("Galactic Core", "Star cluster", 350.0, 900.0, 40.0), ("The Void Throne", "Black hole", 0.0, 0.0, 0.0)]


def rd_to_xyz(ra_h, dec, dist):
    """Right ascension/declination/distance -> galactic X (towards the centre), Y (the way the Sun moves), Z (north)."""
    a, d = math.radians(ra_h * 15.0), math.radians(dec)
    ap, dp, lncp = math.radians(192.85948), math.radians(27.12825), math.radians(122.93192)
    sb = math.sin(d) * math.sin(dp) + math.cos(d) * math.cos(dp) * math.cos(a - ap)
    b = math.asin(max(-1.0, min(1.0, sb)))
    y_ = math.cos(d) * math.sin(a - ap)
    x_ = math.sin(d) * math.cos(dp) - math.cos(d) * math.sin(dp) * math.cos(a - ap)
    l = lncp - math.atan2(y_, x_)
    return dist * math.cos(b) * math.cos(l), dist * math.cos(b) * math.sin(l), dist * math.sin(b)


def to_map(X, Y, Z):
    """Galactic (Sun-centred) -> map coordinates: centred on the Galactic Centre, x right, y down, the Sun at the bottom."""
    return -Y, GC_DIST - X, Z


def constellation(l):
    best = min(CONSTELLATIONS, key=lambda c: min(abs(l - c[0]), 360 - abs(l - c[0])))
    return best[1], best[2]


def base_faction(x, y):
    """Which faction rules the neighbourhood of a point (the large-scale pattern)."""
    R = math.hypot(x, y)
    d_sol = math.hypot(x, y - GC_DIST)
    if R < 4200:
        return "devourer"
    if d_sol < 110:
        return "pirates"
    l = longitude(x, y)
    if y < 0 and abs(x) < 16000 and d_sol > GC_DIST * 0.98:            # the far side of the galaxy, beyond the centre
        return "void"
    if l >= 330 or l < 60:
        return "iron"
    if l < 150:
        return "hive"
    if l < 240:
        return "void"
    return "crystal"


def make_seeds(rng):
    """Territory seeds scattered at every scale around the Sun; each system belongs to the nearest seed (nearest in terms
    of the seed's own size), which gives ragged, many-sided borders instead of straight wedges."""
    seeds = []
    for lo, hi, n in [(20, 60, 6), (60, 200, 9), (200, 600, 12), (600, 2000, 16), (2000, 6000, 20), (6000, 14000, 26),
                      (14000, 30000, 36), (30000, 70000, 30)]:
        made = 0
        while made < n:
            r = math.exp(rng.uniform(math.log(lo), math.log(hi)))
            th = rng.uniform(0, math.tau)
            x, y = r * math.cos(th), GC_DIST + r * math.sin(th)
            if density(x, y) <= 0.02:
                continue
            fac = base_faction(x, y)
            if fac not in ("devourer", "pirates") and rng.random() < 0.22:
                fac = rng.choice(["pirates", "hive", "crystal", "iron", "void"])
            seeds.append((x, y, max(25.0, 0.3 * r), fac))
            made += 1
    return seeds


def faction_of(x, y, seeds):
    R = math.hypot(x, y)
    d_sol = math.hypot(x, y - GC_DIST)
    if R < 4200:
        return "devourer"
    if d_sol < 110:
        return "pirates"
    best, fac = 1e18, "pirates"
    for sx_, sy_, size, f in seeds:
        d = math.hypot(x - sx_, y - sy_) / size
        if d < best:
            best, fac = d, f
    return fac


def pick_kind(rng, x, y):
    R = math.hypot(x, y)
    d_sol = math.hypot(x, y - GC_DIST)
    arm, _ = arm_strength(x, y)
    bulge = math.exp(-(R / 5000.0) ** 2)
    w = {"Red dwarf": 38, "Orange dwarf": 11, "Yellow dwarf": 8, "White star": 4, "Binary system": 12,
         "White dwarf": 6, "Red giant": 3 + 6 * bulge, "Blue giant": 0.6 + 7 * arm, "Supergiant": 0.2 + 1.3 * arm,
         "Wolf-Rayet star": 0.1 + 0.9 * arm, "Neutron star": 0.5 + 1.5 * bulge, "Pulsar": 0.4 + 1.0 * bulge,
         "Black hole": 0.15 + 1.2 * bulge, "Nebula": 0.5 + 6 * arm, "Star cluster": 0.4 + 2.5 * arm + 2 * bulge,
         "Globular cluster": (0.2 + 4 * bulge) if (R > 5000 or bulge > 0.1) else 0.0,
         "Supernova remnant": 0.4 + 1.8 * arm}
    if d_sol < 400:
        w["Brown dwarf"] = 4
    names = list(w)
    return rng.choices(names, weights=[w[n] for n in names])[0]


# ------------------------------------------------------------------ building the catalogue
def build():
    rng = random.Random(20240614)
    stars = []                                   # dicts: name, kind, x, y, z, real

    def add(name, kind, x, y, z, real):
        stars.append(dict(name=name, kind=kind, x=x, y=y, z=z, real=real))

    sx, sy, sz = to_map(0, 0, 0)
    add("Sol", "Yellow dwarf", sx, sy, 0.0, True)
    oort = REAL[0]
    for name, kind, ra, dec, dist in REAL:
        if ra is None:                                         # the Oort Cloud: a little way out of the solar system
            X, Y, Z = 0.55, 0.52, 0.12
        else:
            X, Y, Z = rd_to_xyz(ra, dec, dist)
        x, y, z = to_map(X, Y, Z)
        add(name, kind, x, y, z, True)
    for name, kind, dx, dy, dz in CENTRE:
        add(name, kind, dx, dy, dz, True)
    # two stars that share a spot on the map get nudged apart a little (in proportion to their distance) so both can be clicked
    placed = []
    for s in stars:
        dist = math.dist((s["x"], s["y"]), (sx, sy))
        thr = max(0.2, 0.004 * dist)
        for p in placed:
            if math.hypot(s["x"] - p["x"], s["y"] - p["y"]) < thr and s["name"] != "Sol":
                s["x"] += rng.uniform(1.0, 1.6) * thr * rng.choice([-1, 1])
                s["y"] += rng.uniform(1.0, 1.6) * thr * rng.choice([-1, 1])
        placed.append(s)
    # the thousands of others
    octaves = [(20, 40, 70), (40, 80, 110), (80, 160, 170), (160, 320, 250), (320, 640, 340), (640, 1280, 460),
               (1280, 2560, 620), (2560, 5120, 780), (5120, 10240, 920), (10240, 20480, 1050), (20480, 41000, 1050),
               (41000, 80000, 420)]
    grid = {}
    cs = 4.0

    def key_of(x, y, c):
        return int(x // c), int(y // c)

    all_pts = [(s["x"], s["y"]) for s in stars]
    used_names = {s["name"] for s in stars}
    counters = {}
    for lo, hi, count in octaves:
        made, tries = 0, 0
        sep = max(2.5, min(150.0, 0.5 * math.sqrt(math.pi * (hi * hi - lo * lo) / count) * 0.45))
        cell = sep
        cells = {}
        for (px, py) in all_pts:
            r = math.hypot(px - sx, py - sy)
            if lo * 0.6 <= r <= hi * 1.4:
                cells.setdefault(key_of(px, py, cell), []).append((px, py))
        dmax = 1.0
        while made < count and tries < count * 4000:
            tries += 1
            r = math.exp(rng.uniform(math.log(lo), math.log(hi)))
            th = rng.uniform(0, math.tau)
            x, y = sx + r * math.cos(th), sy + r * math.sin(th)
            dens = density(x, y)
            if dens <= 0 or rng.random() * 3.2 > dens:
                continue
            kx, ky = key_of(x, y, cell)
            if any(math.hypot(x - qx, y - qy) < sep for ix in (-1, 0, 1) for iy in (-1, 0, 1)
                   for qx, qy in cells.get((kx + ix, ky + iy), ())):
                continue
            cells.setdefault((kx, ky), []).append((x, y))
            kind = pick_kind(rng, x, y)
            R = math.hypot(x, y)
            zs = 120.0 + 900.0 * math.exp(-(R / 4000.0) ** 2)
            z = rng.gauss(0, zs) if r > 60 else rng.gauss(0, 25)
            con, abbr = constellation(longitude(x, y))
            tag = {"Nebula": "Neb", "Star cluster": "Cl", "Globular cluster": "GC", "Supernova remnant": "SNR",
                   "Pulsar": "PSR", "Black hole": "BH", "Neutron star": "NS", "Wolf-Rayet star": "WR"}.get(kind, "")
            while True:
                n = rng.randint(1, 9999)
                name = f"{abbr} {tag + ' ' if tag else ''}{n}"
                if name not in used_names:
                    used_names.add(name)
                    break
            add(name, kind, x, y, z, False)
            all_pts.append((x, y))
            made += 1
        print(f"  {lo:>6}-{hi:<6} ly: {made}/{count} systems (min spacing {sep:.1f} ly)", file=sys.stderr)
    # ids: the Sun first, then real objects and generated ones by distance from the Sun
    sol = stars[0]
    rest = sorted(stars[1:], key=lambda s: (not s["real"], math.dist((s["x"], s["y"], s["z"]), (sx, sy, 0.0))))
    # real ones sorted by distance (the Oort Cloud first), generated ones by distance, the two centre places last
    centre_names = {c[0] for c in CENTRE}
    real = sorted([s for s in rest if s["real"] and s["name"] not in centre_names],
                  key=lambda s: math.dist((s["x"], s["y"], s["z"]), (sx, sy, 0.0)))
    gen = sorted([s for s in rest if not s["real"]], key=lambda s: math.dist((s["x"], s["y"], s["z"]), (sx, sy, 0.0)))
    cen = [s for c in CENTRE for s in rest if s["name"] == c[0]]
    stars = [sol] + real + cen + gen
    # which faction holds each system, which region it is in, which constellation it is seen in
    seeds = make_seeds(random.Random(77))
    for i, s in enumerate(stars):
        s["fac"] = "pirates" if i == 0 else faction_of(s["x"], s["y"], seeds)
        s["reg"] = region_of(s["x"], s["y"])
        s["con"] = constellation(longitude(s["x"], s["y"]))[0] if i else "Orion"
    byname = {s["name"]: s for s in stars}
    byname["The Void Throne"]["fac"] = "devourer"
    byname["Galactic Core"]["fac"] = "devourer"
    # lanes: every system is joined to its nearest neighbours
    N = len(stars)
    xs = [s["x"] for s in stars]
    ys = [s["y"] for s in stars]
    zs_ = [s["z"] for s in stars]
    edges = set()
    K = 4
    cellw = 60.0
    # a coarse grid keeps this fast: search outwards ring by ring until K neighbours are surely found
    cells = {}
    for i in range(N):
        cells.setdefault((int(xs[i] // cellw), int(ys[i] // cellw)), []).append(i)
    for i in range(N):
        cx, cy = int(xs[i] // cellw), int(ys[i] // cellw)
        ring, found = 0, []
        while True:
            for ix in range(-ring, ring + 1):
                for iy in range(-ring, ring + 1):
                    if max(abs(ix), abs(iy)) == ring:
                        found += cells.get((cx + ix, cy + iy), [])
            if len(found) > K and ring >= 1:
                ds = sorted(math.dist((xs[i], ys[i], zs_[i]), (xs[j], ys[j], zs_[j])) for j in found if j != i)
                if len(ds) > K and ds[K - 1] <= ring * cellw:
                    break
            ring += 1
            if ring > 2000:
                break
        near = sorted((math.dist((xs[i], ys[i], zs_[i]), (xs[j], ys[j], zs_[j])), j) for j in found if j != i)[:K]
        for d, j in near:
            edges.add((min(i, j), max(i, j)))
    names = [s["name"] for s in stars]
    cons = sorted({s["con"] for s in stars})
    regs = sorted({s["reg"] for s in stars})
    data = dict(
        version=1, gc=GC_DIST, kinds=KINDS, factions=FACTIONS, constellations=cons, regions=regs, arms=ARM_NAMES,
        names=names, kind=[KINDS.index(s["kind"]) for s in stars],
        x=[round(s["x"], 2 if i < 140 else 0) for i, s in enumerate(stars)],
        y=[round(s["y"], 2 if i < 140 else 0) for i, s in enumerate(stars)],
        z=[round(s["z"], 2 if i < 140 else 0) for i, s in enumerate(stars)],
        fac=[FACTIONS.index(s["fac"]) for s in stars], con=[cons.index(s["con"]) for s in stars],
        reg=[regs.index(s["reg"]) for s in stars], real=[i for i, s in enumerate(stars) if s["real"]],
        edges=[v for e in sorted(edges) for v in e])
    return data


def preview(data, path):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    W = 1100
    scr = pygame.Surface((W, W))
    scr.fill((6, 8, 18))
    k = W / 112000.0
    cols = dict(pirates=(235, 90, 80), hive=(130, 220, 90), crystal=(110, 220, 255), iron=(225, 150, 80),
                void=(175, 110, 255), devourer=(255, 80, 200))
    for i, (x, y) in enumerate(zip(data["x"], data["y"])):
        c = cols[data["factions"][data["fac"][i]]]
        pygame.draw.circle(scr, c, (W / 2 + x * k, W / 2 + y * k), 1)
    pygame.draw.circle(scr, (255, 255, 255), (W / 2, W / 2 + data["gc"] * k), 3)
    pygame.image.save(scr, path)


if __name__ == "__main__":
    d = build()
    print(f"{len(d['names'])} systems, {len(d['edges']) // 2} lanes, {len(d['real'])} real", file=sys.stderr)
    if "--preview" in sys.argv:
        preview(d, sys.argv[sys.argv.index("--preview") + 1])
    else:
        with open(OUT, "w") as f:
            json.dump(d, f, separators=(",", ":"))
        print("wrote", os.path.normpath(OUT), os.path.getsize(OUT) // 1024, "KB", file=sys.stderr)
