"""Builds assets/worlds.json: the confirmed planets of the real stars of the game, from the Open Exoplanet Catalogue.

    python3 tools/make_worlds.py path/to/systems.xml.gz

The catalogue (https://github.com/OpenExoplanetCatalogue/oec_gzip, MIT licence) is not part of the game: only the few
thousand numbers this script keeps are. For every star of assets/galaxy.json whose name is in the catalogue it writes
[name, radius (Earth radii), mass (Earth masses), temperature (K), period (days), semi-major axis (AU), year found].
A number the catalogue does not have is null; worlds.py fills it in from the others.
"""
import gzip
import json
import math
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
R_JUP, M_JUP = 11.209, 317.83                     # Earth radii / masses in one Jupiter
SKIP = {"Alpha Centauri B b"}                      # a retracted planet
NO_CATALOGUE = {"Alpha Centauri"}                  # the catalogue files Proxima's planets under this name too


def num(el, tag):
    e = el.find(tag)
    try:
        return float(e.text)
    except (AttributeError, TypeError, ValueError):
        return None


def main(path):
    sys.path.insert(0, ROOT)
    import galaxy
    names = {s["name"].lower().replace(" ", ""): s["name"] for s in galaxy.STARS if s["real"] and s["name"] not in NO_CATALOGUE}
    root = ET.fromstring(gzip.open(path).read())
    out = {}
    for system in root.iter("system"):
        keys = [n.text.lower().replace(" ", "") for n in system.findall("name") if n.text]
        hit = next((names[k] for k in keys if k in names), None)
        if not hit or hit in out:
            continue
        planets = []
        for star in system.iter("star"):
            st = num(star, "temperature")
            sr = num(star, "radius")
            for p in star.findall("planet"):
                pn = [n.text for n in p.findall("name") if n.text]
                if not pn or pn[0] in SKIP:
                    continue
                r, m = num(p, "radius"), num(p, "mass")
                a, per, t = num(p, "semimajoraxis"), num(p, "period"), num(p, "temperature")
                if t is None and st and sr and a:                      # the temperature of a planet with an albedo of 0.3
                    t = st * math.sqrt(sr * 0.00465047 / (2 * a)) * 0.7 ** 0.25
                year = num(p, "discoveryyear")
                name = pn[0]
                if name[0].islower():
                    name = name[0].upper() + name[1:]
                tail = name.rsplit(" ", 1)[-1]
                if len(tail) == 1 and tail.isalpha() and not name.lower().startswith(hit.lower()):
                    name = f"{hit} {tail}"                              # "alf Tau b" is Aldebaran b here
                planets.append([name, None if r is None else round(r * R_JUP, 3), None if m is None else round(m * M_JUP, 2),
                                None if t is None else round(t), None if per is None else round(per, 4),
                                None if a is None else round(a, 5), None if year is None else int(year)])
        merged = {}                                                     # a planet the catalogue lists twice: keep what each entry knows
        for q in planets:
            if q[0] in merged:
                merged[q[0]] = [a if a is not None else b for a, b in zip(merged[q[0]], q)]
            else:
                merged[q[0]] = q
        planets = list(merged.values())
        if planets:
            planets.sort(key=lambda q: (q[5] is None, q[5] or 0, q[0]))
            out[hit] = planets
    with open(os.path.join(ROOT, "assets", "worlds.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"), sort_keys=True)
    print(f"{len(out)} systems, {sum(len(v) for v in out.values())} planets -> assets/worlds.json")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
