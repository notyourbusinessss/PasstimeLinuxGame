"""Colony worlds: any planet of any star you have liberated, as a planet you can settle and play.

Pure data (no pygame, no core). worlds.py says what orbits every star (about 15,900 worlds in the galaxy); this module turns one
of them into a *site*: a planet like the twelve of the solar system, with its own ore, fleet, upgrades, colony buildings and
planet bonus. A site is worked out from the world every time it is asked for, so nothing but (star, world number) is saved.

Every planet, solar or not, has an economy **tier**: its ore is worth 10 ** tier, its ships and buildings are priced on that
tier. The tier of a solar planet is its place in the line (Earth 0 ... the Kuiper Belt 11); the tier of any other world follows
from the strength of its star (see tier_of): a weak star near the Sun gives tier 3 worlds, the far and strong ones tier 10.
You can settle a world once you hold its star; it costs the ore of the planets of the tier before it, and more for every colony
you already have. The ships of a world are those of the solar planet its kind of world looks like (FAMILY).
"""
import galaxy
import worlds

NSOL = 12                        # the planets of the solar system (core.SITES)
TIER_CAP = 11                    # the richest tier: the Kuiper Belt
COST_BASE = 0.4                  # a colony costs this much of a solar planet of its tier...
COST_GROWTH = 1.06               # ...and every colony you already hold makes the next one this much dearer
G_BONUS = 0.01                   # every colony adds this to the production multiplier (a solar planet adds 0.05)
YIELD = 0.2                      # a colony's banks and labs make this share of the credits and science of a solar planet of its tier
NORM = 0.1                       # the share of a colony's ore that counts towards Dark Matter (a Warp) and your cycle's progress
FLEET = 0.3                      # a colony's ships fight at this share of the strength of a solar planet's

# kind of world -> the ore it yields, and its colour
ORE = dict(temperate="Verdite", ocean="Brinite", rocky="Basalt", desert="Dune Glass", ice="Cryolite", lava="Magmite",
           dwarf="Cinder", mini="Haze Gas", ice_giant="Cryo Gas", gas="Aerogen")
ORE_COL = dict(temperate=(150, 235, 140), ocean=(120, 190, 255), rocky=(200, 190, 180), desert=(245, 205, 140), ice=(200, 230, 255),
               lava=(255, 150, 90), dwarf=(205, 190, 180), mini=(200, 225, 240), ice_giant=(140, 225, 235), gas=(245, 195, 150))
COL = dict(temperate=(110, 200, 120), ocean=(90, 150, 235), rocky=(170, 160, 150), desert=(225, 170, 100), ice=(180, 210, 240),
           lava=(240, 110, 60), dwarf=(170, 155, 145), mini=(170, 205, 225), ice_giant=(100, 205, 220), gas=(225, 170, 120))
# the planet bonus of a kind of world: the first world of that kind you settle brings it (the later ones do not, so the bonuses
# of fifteen thousand worlds stay ten)
PERK = dict(
    temperate=("Settled world: credit income x1.1", [("cred", 1.1)]),
    ocean=("Deep research: science income x1.1", [("sci", 1.1)]),
    rocky=("Quarries: ships 2% cheaper everywhere", [("disc", 0.02)]),
    desert=("Solar glassworks: all ore production x1.1", [("ore", 1.1)]),
    ice=("Cold vaults: Dark Matter gain x1.1", [("dm", 1.1)]),
    lava=("Geothermal forges: all ore production x1.15", [("ore", 1.15)]),
    dwarf=("Light gravity rigs: clicks x1.5", [("click", 1.5)]),
    mini=("Cloud skimmers: crates 10% more often", [("crate", 0.1)]),
    ice_giant=("Deep labs: science income x1.15", [("sci", 1.15)]),
    gas=("Orbital yards: fleet power x1.1", [("fp", 1.1)]))
NO_PERK = "No planet bonus: you already hold a world of this kind"
# kind of world -> the solar planet whose ships, laser style and look its fleet borrows
FAMILY = dict(temperate=0, ocean=9, rocky=1, desert=2, ice=10, lava=4, dwarf=5, mini=3, ice_giant=8, gas=6)
# which colony building a kind of world is best at (2x), as core.BUILDINGS indexes: mine, bank, lab, shipyard, reactor, silo
BONUS = dict(temperate=1, ocean=2, rocky=3, desert=0, ice=5, lava=4, dwarf=3, mini=5, ice_giant=2, gas=4)


def tier_of(k):
    """The economy tier of the worlds of star k from the strength of the star (galaxy.STARS[k]["lp"], 2.5 near the Sun to 14 in the
    core): 4 ly away is tier 2, 40 ly tier 5, 1,000 ly tier 8, the Galactic Centre tier 11."""
    return max(1, min(TIER_CAP, round(0.85 * galaxy.STARS[k]["lp"] - 1.0)))


_SITES = {}


def site_of(k, i):
    """The site of world i of star k: a dict like core.SITES' (name, ore, colours, bonus, perk...) plus the colony's own keys."""
    got = _SITES.get((k, i))
    if got is None:
        w = worlds.planets_of(k)[i]
        kind = w["kind"]
        fam = 7 if kind == "gas" and w["ring"] else FAMILY[kind]             # a ringed giant flies the Saturn ships
        text, fx = PERK[kind]
        got = _SITES[(k, i)] = dict(
            name=w["name"], ore=ORE[kind], ocol=ORE_COL[kind], col=COL[kind], kind="world", wkind=kind, bonus=BONUS[kind], perk=text,
            fx=list(fx), unlock=None, colony=True, tier=tier_of(k), sys=k, widx=i, family=fam, seed=w["seed"], ring=w["ring"],
            id=("c", k, i))
    return got
