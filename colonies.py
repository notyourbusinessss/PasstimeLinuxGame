"""Colony worlds: the confirmed planets of the real stars, as planets you can settle and play.

Pure data (no pygame, no core). Every real planet of assets/worlds.json (89 of them, see worlds.py) becomes a site like
the twelve planets of the solar system: its own ore, fleet, upgrades, colony buildings and a planet bonus. core.py appends
them to SITES, so index 12 and up are colonies. A colony sits on the economy *tier* of a solar planet - tier 5 is as rich as
Ceres, so its ore, ships and prices are those of tier 5 - which one follows from how far its star is from the Sun (the further
the star, the later the tier). You can settle a colony when you have liberated its system and reached its tier (the solar planet
of the same tier is unlocked); the more colonies you hold, the more the next one costs.

The ships of a colony are those of the solar planet its kind of world looks like (a desert world flies the Mars ships...):
FAMILY says which. Everything about a colony is worked out from the catalogue data, so the list and its order never change
unless assets/worlds.json does.
"""
import math

import galaxy
import worlds

NSOL = 12                        # the planets of the solar system (core.SITES starts with them)
TIER_CAP = 11                    # the richest tier: the Kuiper Belt
COST_BASE = 0.5                  # the first colony costs this much of a solar planet of its tier...
COST_GROWTH = 1.35               # ...and every colony you already hold makes the next one this much dearer
G_BONUS = 0.02                   # every colony adds this to the production multiplier (a solar planet adds 0.05)
YIELD = 0.2                      # a colony's banks and labs make this share of the credits and science of a solar planet of its tier

# kind of world -> (the ore it yields, the colour of the ore, the planet bonus text, the bonus effect)
ORE = dict(temperate="Verdite", ocean="Brinite", rocky="Basalt", desert="Dune Glass", ice="Cryolite", lava="Magmite",
           dwarf="Cinder", mini="Haze Gas", ice_giant="Cryo Gas", gas="Aerogen")
ORE_COL = dict(temperate=(150, 235, 140), ocean=(120, 190, 255), rocky=(200, 190, 180), desert=(245, 205, 140), ice=(200, 230, 255),
               lava=(255, 150, 90), dwarf=(205, 190, 180), mini=(200, 225, 240), ice_giant=(140, 225, 235), gas=(245, 195, 150))
PERK = dict(
    temperate=("Settled world: credit income x1.04", [("cred", 1.04)]),
    ocean=("Deep research: science income x1.04", [("sci", 1.04)]),
    rocky=("Quarries: ships 1% cheaper everywhere", [("disc", 0.01)]),
    desert=("Solar glassworks: all ore production x1.04", [("ore", 1.04)]),
    ice=("Cold vaults: Dark Matter gain x1.03", [("dm", 1.03)]),
    lava=("Geothermal forges: all ore production x1.05", [("ore", 1.05)]),
    dwarf=("Light gravity rigs: clicks x1.2", [("click", 1.2)]),
    mini=("Cloud skimmers: crates 5% more often", [("crate", 0.05)]),
    ice_giant=("Deep labs: science income x1.05", [("sci", 1.05)]),
    gas=("Orbital yards: fleet power x1.03", [("fp", 1.03)]))
# kind of world -> the solar planet whose ships, laser style and look its fleet borrows
FAMILY = dict(temperate=0, ocean=9, rocky=1, desert=2, ice=10, lava=4, dwarf=5, mini=3, ice_giant=8, gas=6)


def tier_of(distance):
    """The economy tier of a colony from the distance of its star in light-years: 4 ly is tier 2, 40 ly tier 5, 1,400 ly tier 9."""
    return max(1, min(TIER_CAP, round(3.0 * math.log10(max(distance, 1.0)))))


def _build():
    rows = []
    for name in worlds.REAL:
        k = galaxy.BY_NAME[name]
        for w in worlds.planets_of(k):
            rows.append((tier_of(galaxy.STARS[k]["d"]), galaxy.STARS[k]["d"], w["a"], k, w))
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[4]["name"]))
    out = []
    for tier, _, _, k, w in rows:
        kind = w["kind"]
        fam = FAMILY[kind] if not (kind == "gas" and w["ring"]) else 7                   # a ringed giant flies the Saturn ships
        text, fx = PERK[kind]
        out.append(dict(name=w["name"], ore=ORE[kind], ocol=ORE_COL[kind], col=_colour(kind), kind="world", wkind=kind, bonus=_bonus(kind),
                        perk=text, fx=list(fx), unlock=None, colony=True, tier=tier, sys=k, widx=w["idx"], family=fam, seed=w["seed"],
                        ring=w["ring"]))
    return out


def _colour(kind):
    """The colour of a colony in the interface (the dot of its planet)."""
    return {"temperate": (110, 200, 120), "ocean": (90, 150, 235), "rocky": (170, 160, 150), "desert": (225, 170, 100),
            "ice": (180, 210, 240), "lava": (240, 110, 60), "dwarf": (170, 155, 145), "mini": (170, 205, 225),
            "ice_giant": (100, 205, 220), "gas": (225, 170, 120)}[kind]


def _bonus(kind):
    """Which colony building a kind of world is best at (2x), as core.BUILDINGS indexes: mine, bank, lab, shipyard, reactor, silo."""
    return {"temperate": 1, "ocean": 2, "rocky": 3, "desert": 0, "ice": 5, "lava": 4, "dwarf": 3, "mini": 5, "ice_giant": 2, "gas": 4}[kind]


COLONIES = _build()
NCOL = len(COLONIES)
