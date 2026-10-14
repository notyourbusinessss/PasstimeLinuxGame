"""Space Miner game logic (no pygame here, so it can be simulated headless for balancing)."""
import json
import math
import os
import random
import time
from collections import deque

SAVE_VER = 2
SAVE = os.path.expanduser("~/.space_miner_save.json")

GROWTH = 1.15            # ship price growth per owned ship
BGROWTH = 1.28           # colony building price growth per level
BMAX = 50
OFFLINE_CAP = 8 * 3600
OFFLINE_EFF = 0.5
SCALE = 10.0             # every planet's ore is worth/costs 10x the previous one
CSCALE = 5.0             # credit / science scale per planet
DM_DIV = 1e7             # lifetime (Earth-equivalent) ore for the first Dark Matter
DM_POW = 0.25            # Dark Matter owned ~ (lifetime ore / DM_DIV) ** DM_POW
SUPPLY = 60              # free ore (in ship-1 prices) a planet starts a run / unlock with

# ------------------------------------------------------------------ ships (every planet has the full ladder)
SHIPS = [  # name, base cost, ore/sec each, colour
    ("Mining Drone",      15,      0.1,    (140, 200, 255)),
    ("Laser Rig",         100,     1,      (255, 110, 110)),
    ("Mining Barge",      1_100,   8,      (255, 190, 90)),
    ("Refinery Ship",     12_000,  47,     (150, 255, 160)),
    ("Orbital Foundry",   130_000, 260,    (220, 140, 255)),
    ("Dyson Swarm",       1.4e6,   1_400,  (255, 245, 130)),
    ("Neutron Tap",       2e7,     7_800,  (110, 255, 235)),
    ("Black Hole Engine", 3.3e8,   44_000, (255, 120, 200)),
]
NSH = len(SHIPS)

# ------------------------------------------------------------------ colony buildings (per planet)
BUILDINGS = [  # name, resource paid, base cost, description, icon colour
    ("Mining Complex", "ore", 2e3, "+3% ore output here / level", (255, 190, 90)),
    ("Habitat Dome", "ore", 2e3, "Produces Credits", (255, 215, 110)),
    ("Research Lab", "ore", 4e3, "Produces Science", (120, 235, 255)),
    ("Shipyard", "credits", 200, "-0.6% ship prices here / level", (180, 190, 220)),
    ("Fusion Reactor", "credits", 600, "+2.5% ALL production / level", (255, 130, 90)),
    ("Defense Grid", "science", 25, "+4% supply crate frequency / level", (130, 255, 150)),
]
NB = len(BUILDINGS)

# ------------------------------------------------------------------ planets
# unlock = (normalised amount of previous planet's ore, of the one before that, credits)
SITES = [
    dict(name="Earth", ore="Iron", ocol=(215, 140, 120), col=(90, 160, 255), kind="earth", bonus=1,
         perk="Home world - where it all begins", fx=[], unlock=None),
    dict(name="Moon", ore="Silicon", ocol=(170, 190, 225), col=(200, 200, 210), kind="moon", bonus=0,
         perk="Low-gravity rigs: clicks x2", fx=[("click", 2)], unlock=(2e4, 0, 0)),
    dict(name="Mars", ore="Copper", ocol=(235, 145, 85), col=(225, 100, 60), kind="mars", bonus=3,
         perk="Martian foundries: ships 5% cheaper everywhere", fx=[("disc", 0.05)], unlock=(4e5, 8e3, 0)),
    dict(name="Venus", ore="Silver", ocol=(225, 232, 245), col=(240, 205, 130), kind="venus", bonus=4,
         perk="Trade winds: credit income x1.5", fx=[("cred", 1.5)], unlock=(8e6, 1.6e5, 1e3)),
    dict(name="Mercury", ore="Gold", ocol=(255, 208, 70), col=(170, 150, 130), kind="mercury", bonus=4,
         perk="Solar farms: all ore production x1.5", fx=[("ore", 1.5)], unlock=(1.5e8, 3e6, 2e4)),
    dict(name="Ceres", ore="Platinum", ocol=(190, 228, 255), col=(150, 150, 160), kind="ceres", bonus=5,
         perk="Belt beacons: crates 25% more often, pay x2", fx=[("crate", 0.25), ("crate_pay", 2)], unlock=(3e9, 6e7, 4e5)),
    dict(name="Jupiter", ore="Helium-3", ocol=(150, 255, 220), col=(230, 170, 110), kind="jupiter", bonus=2,
         perk="Gas-giant labs: science income x2", fx=[("sci", 2)], unlock=(6e10, 1.2e9, 8e6)),
    dict(name="Saturn", ore="Diamond", ocol=(195, 240, 255), col=(235, 215, 160), kind="saturn", bonus=1,
         perk="Ring-miners: ships 5% cheaper, clicks x2", fx=[("disc", 0.05), ("click", 2)], unlock=(1.2e12, 2.4e10, 1.6e8)),
    dict(name="Uranus", ore="Antimatter", ocol=(255, 125, 225), col=(130, 215, 225), kind="uranus", bonus=2,
         perk="Cold engines: all ore production x2", fx=[("ore", 2)], unlock=(2.5e13, 5e11, 3e9)),
    dict(name="Neptune", ore="Dark Crystal", ocol=(170, 120, 255), col=(70, 100, 230), kind="neptune", bonus=0,
         perk="Deep-space drift: offline progress at 75%", fx=[("offline", 0.75)], unlock=(5e14, 1e13, 6e10)),
    dict(name="Pluto", ore="Exotic Matter", ocol=(120, 255, 155), col=(220, 200, 180), kind="pluto", bonus=5,
         perk="Edge of the system: Dark Matter gain x1.5", fx=[("dm", 1.5)], unlock=(1e16, 2e14, 1.2e12)),
    dict(name="Proxima b", ore="Quantum Foam", ocol=(255, 175, 255), col=(220, 80, 50), kind="proxima", bonus=-1,
         perk="Another star: all ore production x3, buildings x1.5", fx=[("ore", 3)], unlock=(2e17, 4e15, 2.4e13)),
]
NSITE = len(SITES)
SC = [SCALE ** p for p in range(NSITE)]
CSC = [CSCALE ** p for p in range(NSITE)]

# ------------------------------------------------------------------ tech tree (Science)
TECHS = [  # id, name, science cost, prereqs, description, effects
    ("t1", "Improved Optics", 20, [], "All ore production x1.1", [("ore", 1.1)]),
    ("t2", "Ergonomic Tools", 30, [], "Clicks x2", [("click", 2)]),
    ("t3", "Trade Protocols", 40, [], "Credit income x1.5", [("cred", 1.5)]),
    ("t4", "Peer Review", 60, ["t1"], "Science income x1.5", [("sci", 1.5)]),
    ("t5", "Bulk Contracts", 150, ["t3"], "Ships 5% cheaper", [("disc", 0.05)]),
    ("t6", "Auto-Drones", 200, ["t1", "t2"], "Auto-buys ships on every planet (spends up to 25% of a stockpile)", [("auto", 1)]),
    ("t7", "Signal Booster", 250, ["t4"], "Crates appear 25% more often", [("crate", 0.25)]),
    ("t8", "Drone Swarm AI", 400, ["t6"], "Drones x3, Laser Rigs x2", [("gen", 0, 3), ("gen", 1, 2)]),
    ("t9", "Deep Core Drilling", 1e3, ["t5"], "Mining Complexes x1.5 stronger", [("minebonus", 1.5)]),
    ("t10", "Quantum Computing", 2.5e3, ["t4"], "Science income x2", [("sci", 2)]),
    ("t11", "Credit Futures", 4e3, ["t3", "t5"], "Credit income x2", [("cred", 2)]),
    ("t12", "Automated Salvage", 6e3, ["t7"], "Supply crates are collected automatically", [("autocrate", 1)]),
    ("t13", "Fusion Ignition", 1e4, ["t9"], "All ore production x1.5", [("ore", 1.5)]),
    ("t14", "Laser Focusing", 2e4, ["t8"], "Lasers, Barges, Refineries x2",
     [("gen", 1, 2), ("gen", 2, 2), ("gen", 3, 2)]),
    ("t15", "Stellar Cartography", 5e4, ["t10"], "Crates pay x2 and appear 25% more", [("crate_pay", 2), ("crate", 0.25)]),
    ("t16", "Warp Theory", 1e5, ["t13"], "Dark Matter gain x1.25", [("dm", 1.25)]),
    ("t17", "Dyson Blueprints", 3e5, ["t14"], "Foundries & Dyson Swarms x2", [("gen", 4, 2), ("gen", 5, 2)]),
    ("t18", "Matter Compression", 8e5, ["t11", "t13"], "Ships 10% cheaper", [("disc", 0.10)]),
    ("t19", "Time Dilation Field", 1.5e6, ["t16"], "Offline progress at 75%", [("offline", 0.75)]),
    ("t20", "Antimatter Engines", 4e6, ["t17"], "All ore production x2", [("ore", 2)]),
    ("t21", "Auto-Engineers", 6e6, ["t6", "t18"], "Auto-buys upgrades on every planet (up to 25% of a stockpile)", [("autoup", 1)]),
    ("t22", "Hyper Clicks", 2e7, ["t2", "t15"], "Clicks x5, +2% of ore/s per click", [("click", 5), ("clickops", 0.02)]),
    ("t23", "Head Start Program", 5e7, ["t19"], "Every planet starts a run with extra free ore", [("start", 5e3)]),
    ("t24", "Singularity Lab", 1e8, ["t20"], "Science income x3", [("sci", 3)]),
    ("t25", "Neutron Weave", 5e8, ["t24"], "Neutron Taps & Black Hole Engines x3", [("gen", 6, 3), ("gen", 7, 3)]),
    ("t26", "Omega Reactor", 2e9, ["t20", "t21"], "All ore production x3", [("ore", 3)]),
    ("t27", "Galactic Federation", 1e10, ["t22", "t24"], "Credits x5, ships 10% cheaper", [("cred", 5), ("disc", 0.10)]),
    ("t28", "Reality Engineering", 1e11, ["t25", "t26"], "Every ship type x2, ore x2",
     [("gen", i, 2) for i in range(NSH)] + [("ore", 2)]),
    ("t29", "Dark Matter Harvesters", 1e12, ["t23", "t28"], "Dark Matter gain x2", [("dm", 2)]),
    ("t30", "Transcendence", 1e13, ["t27", "t29"], "All ore production x10", [("ore", 10)]),
]
_TECH_BASE = {t[0]: t[2] for t in TECHS}
TECH_BY_ID = {t[0]: t for t in TECHS}

# ------------------------------------------------------------------ pacing knobs (tuned with sim.py)
UNLOCK_LOG = [3.32, 4.24, 7.56, 12.83, 16.45, 17.71, 19.23, 19.6, 21.42, 22.27, 24.21]   # log10 of normalised price, Moon..Proxima b
TUNE = dict(ushift=0.0, B=50.0, ccoef=0.17, texp=0.5, tpow=0.75, pshift=0.0, pcoef=0.17, dmbase=0.40, dm_div=1e9, dm_pow=0.25)


def project_cost(p):
    """(raw ore of that planet, credits, science)"""
    n = 10 ** (PROJECT_LOG[p] + TUNE["pshift"])
    return n * SC[p], TUNE["pcoef"] * n ** 0.6, TUNE["pcoef"] * 0.5 * n ** 0.6


def apply_tune(**kw):
    """Rebuild planet unlock prices / tech prices from the knobs."""
    global DM_DIV, DM_POW
    TUNE.update(kw)
    for k in range(1, NSITE):
        a = 10 ** (UNLOCK_LOG[k - 1] + TUNE["ushift"])
        b = a / TUNE["B"] if k >= 2 else 0
        cr = TUNE["ccoef"] * a ** 0.6 if k >= 3 else 0
        SITES[k]["unlock"] = (a, b, cr)
    for i, t in enumerate(TECHS):
        base = _TECH_BASE[t[0]]
        cut = 1e8 ** (1 + TUNE["texp"])
        cost = base ** (1 + TUNE["texp"]) if base <= 1e8 else cut * (base / 1e8) ** TUNE["tpow"]
        TECHS[i] = (t[0], t[1], cost, t[3], t[4], t[5])
        TECH_BY_ID[t[0]] = TECHS[i]
    DM_DIV, DM_POW = TUNE["dm_div"], TUNE["dm_pow"]



# ------------------------------------------------------------------ Dark Matter perks
PERKS = [  # id, name, DM cost, description, effects
    ("p1", "Quantum Pickaxe", 1, "Clicks x3", [("click", 3)]),
    ("p2", "Dark Reactors", 2, "Dark Matter production bonus 50% stronger", [("dmbase", 0.20)]),
    ("p3", "Bargain Warp", 2, "Ships 5% cheaper", [("disc", 0.05)]),
    ("p4", "Fast Travel", 3, "Travel between planets takes half the time", [("travel", 0.5)]),
    ("p5", "Entangled Trade", 4, "Credit income x2", [("cred", 2)]),
    ("p6", "Dark Science", 4, "Science income x2", [("sci", 2)]),
    ("p7", "Crate Magnet", 5, "Crates appear 50% more often", [("crate", 0.5)]),
    ("p8", "Time Loop", 6, "Offline progress at 100%", [("offline", 1.0)]),
    ("p9", "Dark Frenzy", 6, "Frenzies last 15s longer", [("frenzy", 15)]),
    ("p10", "Matter Siphon", 10, "Dark Matter gain x1.5", [("dm", 1.5)]),
    ("p11", "Void Engines", 12, "All production x2", [("ore", 2)]),
    ("p12", "Event Horizon", 20, "All production x2 and clicks x3", [("ore", 2), ("click", 3)]),
]
PERKS += [
    ("p13", "Cosmic Bargain", 40, "Ships 5% cheaper", [("disc", 0.05)]),
    ("p14", "Warp Engines", 100, "All production x1.5", [("ore", 1.5)]),
    ("p15", "Supply Drop", 150, "Planets start each run with much more free ore", [("start", 3e4)]),
    ("p16", "Stellar Forge", 500, "All production x2", [("ore", 2)]),
    ("p17", "Infinite Tools", 1500, "Clicks x10", [("click", 10)]),
    ("p18", "Matter Siphon II", 3000, "Dark Matter gain x1.5", [("dm", 1.5)]),
    ("p19", "Void Heart", 8000, "All production x2", [("ore", 2)]),
    ("p20", "Galactic Mind", 20000, "Credit and science income x3", [("cred", 3), ("sci", 3)]),
    ("p21", "Reality Anchor", 60000, "All production x3", [("ore", 3)]),
    ("p22", "Omega Point", 200000, "All production x4", [("ore", 4)]),
]
PERK_BY_ID = {p[0]: p for p in PERKS}

# ------------------------------------------------------------------ megaprojects: one per planet, bought with that planet's ore
PROJECTS = [  # name, description, effects   (cost: normalised ore PROJECT_LOG, + credits + science)
    ("Orbital Ring", "Ships 10% cheaper everywhere", [("disc", 0.10)]),
    ("Lunar Mass Driver", "All production x1.5", [("ore", 1.5)]),
    ("Terraformers", "All production x2", [("ore", 2)]),
    ("Cloud Cities", "Credit income x3", [("cred", 3)]),
    ("Solar Array", "All production x2", [("ore", 2)]),
    ("Belt Network", "Crates 50% more often, pay x2", [("crate", 0.5), ("crate_pay", 2)]),
    ("Gas Siphons", "Science income x3", [("sci", 3)]),
    ("Ring Elevator", "All production x2", [("ore", 2)]),
    ("Ice Forges", "Ships 10% cheaper everywhere", [("disc", 0.10)]),
    ("Deep Core Mine", "All production x3", [("ore", 3)]),
    ("Edge Gate", "Dark Matter gain x2", [("dm", 2)]),
    ("Alpha Dyson Swarm", "All production x5", [("ore", 5)]),
]
PROJECT_LOG = [4.39, 8.49, 12.24, 14.03, 16.68, 17.36, 19.23, 19.56, 21.42, 22.27, 24.71, 27.44]   # log10 of normalised ore

SUFFIX = ["", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc", "Ud", "Dd", "Td", "Qd"]


def fmt(n, decimals=1):
    if n < 0:
        return "-" + fmt(-n, decimals)
    if n < 1000:
        if n < 10 and n != int(n):
            return f"{n:.{decimals}f}" if n >= 1 else f"{n:.2f}"
        return f"{int(n)}"
    idx = int(math.log10(n) // 3)
    if idx >= len(SUFFIX):
        return f"{n:.2e}".replace("e+", "e")
    return f"{n / 1000 ** idx:.{decimals}f}{SUFFIX[idx]}"


def geo_cost(first, g, n):
    return first * (g ** n - 1) / (g - 1)


def geo_max(first, g, budget):
    if budget < first:
        return 0
    return max(0, int(math.log(budget * (g - 1) / first + 1) / math.log(g)))


# ------------------------------------------------------------------ per-planet upgrades (cost in that planet's ore)
def build_upgrades():
    ups = []
    tiers = [(10, 2, 50), (25, 2, 1_000), (50, 3, 30_000), (100, 3, 1e6), (150, 5, 5e7)]
    for i, (n, c, r, _) in enumerate(SHIPS):
        for k, (thr, mult, cm) in enumerate(tiers):
            ups.append(dict(id=f"g{i}_{k}", name=f"{n} Mk{k + 2}", cost=c * cm,
                            desc=f"{n}s here are x{mult} as efficient (own {thr})", kind="gen",
                            arg=(i, mult), req=("own", i, thr)))
    for k in range(8):
        cost = 100 * 10 ** k
        ups.append(dict(id=f"c{k}", name=f"Pickaxe Mk{k + 1}", cost=cost,
                        desc="Clicking here is x2 stronger", kind="click", arg=2, req=("ore", cost * 0.3)))
    for k in range(4):
        cost = 5e4 * 100 ** k
        ups.append(dict(id=f"co{k}", name=f"Resonance Drill {k + 1}", cost=cost,
                        desc="Each click also mines +1% of this planet's ore/sec", kind="clickops",
                        arg=0.01, req=("ore", cost * 0.3)))
    for k in range(6):
        cost = 2e4 * 100 ** k
        ups.append(dict(id=f"gl{k}", name=f"Star Charts {k + 1}", cost=cost,
                        desc="ALL production on this planet x1.5", kind="global", arg=1.5,
                        req=("ore", cost * 0.3)))
    return ups


UPGRADES = build_upgrades()
UPG_BY_ID = {u["id"]: u for u in UPGRADES}


# ------------------------------------------------------------------ achievements
TIER_BONUS = {"bronze": 0.005, "silver": 0.01, "gold": 0.02, "platinum": 0.04}   # production bonus each
TIER_NAMES = ["bronze", "silver", "gold", "platinum"]
ACH_CATS = ["Mining", "Fleet", "Planets", "Colony", "Projects", "Science", "Wealth", "Quests", "Warp", "General", "Secret"]


def nf(t):
    return f"{int(t):,}" if t < 1e6 else fmt(t)


def build_achievements():
    A = []

    def add(name, desc, cat, tier, cond, prog=None, secret=False):
        A.append(dict(id=name, name=name, desc=desc, cat=cat, tier=tier, cond=cond, prog=prog, secret=secret))

    def ms(cat, rows, descf, get):
        for name, t, tier in rows:
            add(name, descf(t), cat, tier, lambda g, t=t: get(g) >= t, lambda g, t=t: (get(g), t))

    # --- Mining
    ms("Mining", [("First Rock", 1, "bronze"), ("Calloused Hands", 100, "bronze"), ("Carpal Tunnel", 1000, "silver"),
                  ("Click Maniac", 10000, "gold"), ("Finger of God", 100000, "platinum")],
       lambda t: f"Click asteroids {nf(t)} times", lambda g: g.clicks)
    ms("Mining", [("Speed Miner", 30, "silver"), ("Machine-Gun Finger", 60, "gold")],
       lambda t: f"Click {t} times within 10 seconds", lambda g: g.best_burst)
    ms("Mining", [("Pocket Change", 1e3, "bronze"), ("Millionaire Miner", 1e6, "bronze"), ("Billion Dollar Rock", 1e9, "bronze"),
                  ("Trillion Club", 1e12, "silver"), ("Cosmic Hoarder", 1e15, "silver"), ("Quintillionaire", 1e18, "silver"),
                  ("Sextillion Scrooge", 1e21, "gold"), ("Septillion Sage", 1e24, "gold"), ("Beyond Numbers", 1e27, "gold"),
                  ("Lord of Ore", 1e30, "platinum")],
       lambda t: f"Mine {fmt(t)} ore in total (Earth-equivalent)", lambda g: g.all_norm)
    ms("Mining", [("Tinkerer", 25, "bronze"), ("Engineer", 100, "silver"), ("Mad Scientist", 500, "gold")],
       lambda t: f"Buy {nf(t)} upgrades", lambda g: g.ups_bought)
    # --- Fleet
    ms("Fleet", [("Small Fleet", 50, "bronze"), ("Armada", 200, "bronze"), ("Space Empire", 500, "silver"),
                 ("Endless Horde", 2000, "silver"), ("Sea of Stars", 10000, "gold"), ("Galactic Swarm", 50000, "platinum")],
       lambda t: f"Own {nf(t)} ships in total", lambda g: g.total_ships())
    for i, (n, _, _, _) in enumerate(SHIPS):
        add(f"{n} Fan", f"Own 100 {n}s on one planet", "Fleet", "bronze" if i < 3 else "silver" if i < 6 else "gold",
            lambda g, i=i: max(o[i] for o in g.owned) >= 100, lambda g, i=i: (max(o[i] for o in g.owned), 100))
    add("Diversified", "Own every ship type on Earth", "Fleet", "bronze", lambda g: all(o > 0 for o in g.owned[0]),
        lambda g: (sum(1 for o in g.owned[0] if o > 0), NSH))
    ms("Fleet", [("Full Roster", 6, "silver"), ("Fleet Admiral", NSITE, "platinum")],
       lambda t: f"Own every ship type on {t} planets at once", lambda g: sum(1 for row in g.owned if all(o > 0 for o in row)))
    # --- Planets
    for name, k, tier in [("Moonwalker", 1, "bronze"), ("Red Planet", 2, "bronze"), ("Morning Star", 3, "bronze"),
                          ("Scorched Earth", 4, "silver"), ("Belt Rider", 5, "silver"), ("Gas Giant", 6, "silver"),
                          ("Lord of the Rings", 7, "gold"), ("Ice Giant", 8, "gold"), ("Deep Blue", 9, "gold"),
                          ("Edge of the System", 10, "platinum"), ("Interstellar", 11, "platinum")]:
        add(name, f"Unlock {SITES[k]['name']}", "Planets", tier, lambda g, k=k: g.unlocked[k])
    ms("Planets", [("Tourist", 5, "bronze"), ("Grand Tour", NSITE, "gold")],
       lambda t: f"Visit {t} different planets", lambda g: len(g.visited))
    ms("Planets", [("Frequent Traveler", 10, "bronze"), ("Interplanetary Commuter", 50, "silver"), ("Space Trucker", 250, "gold")],
       lambda t: f"Travel between planets {t} times", lambda g: g.travels)
    # --- Colony
    ms("Colony", [("Builder", 50, "bronze"), ("Architect", 250, "silver"), ("Megastructures", 800, "gold"),
                  ("Dyson Dreams", 2000, "platinum")], lambda t: f"Build {nf(t)} colony levels", lambda g: g.bldg)
    for b, nm in enumerate(["Mining Baron", "Dome Builder", "Lab Rat", "Shipwright", "Reactor Boy", "Fortress"]):
        add(nm, f"Max out a {BUILDINGS[b][0]} (level {BMAX})", "Colony", "silver",
            lambda g, b=b: any(row[b] >= BMAX for row in g.bld), lambda g, b=b: (max(row[b] for row in g.bld), BMAX))
    add("Perfect Colony", "Max out all six buildings on one planet", "Colony", "platinum",
        lambda g: any(all(x >= BMAX for x in row) for row in g.bld),
        lambda g: (max(sum(min(x, BMAX) for x in row) for row in g.bld), NB * BMAX))
    # --- Projects
    ms("Projects", [("First Wonder", 1, "bronze"), ("Megabuilder", 4, "silver"), ("Master Builder", 8, "gold"),
                    ("Wonders of the System", NSITE, "platinum")], lambda t: f"Complete {t} megaprojects", lambda g: len(g.projects))
    # --- Science
    ms("Science", [("Eureka!", 1, "bronze"), ("Student", 5, "bronze"), ("Scientist", 15, "silver"), ("Professor", 25, "gold"),
                   ("Omniscient", len(TECHS), "platinum")], lambda t: f"Research {t} techs", lambda g: len(g.techs))
    ms("Science", [("Curious Mind", 1e3, "bronze"), ("Big Brain", 1e6, "bronze"), ("Nobel Laureate", 1e9, "silver"),
                   ("Galaxy Brain", 1e12, "gold"), ("Omniscience Engine", 1e15, "platinum")],
       lambda t: f"Produce {fmt(t)} science in total", lambda g: g.all_sci)
    # --- Wealth
    ms("Wealth", [("Small Change", 1e3, "bronze"), ("Penny Pincher", 1e6, "bronze"), ("Tycoon", 1e9, "silver"),
                  ("Mogul", 1e12, "gold"), ("Galactic Banker", 1e15, "platinum")],
       lambda t: f"Earn {fmt(t)} credits in total", lambda g: g.all_cred)
    add("Dragon's Hoard", "Sit on 1e30 of a single ore", "Wealth", "silver", lambda g: max(g.ore) >= 1e30,
        lambda g: (max(g.ore), 1e30))
    # --- Quests, events & crates
    ms("Quests", [("Odd Jobs", 1, "bronze"), ("Taskmaster", 10, "bronze"), ("Employee of the Month", 50, "silver"),
                  ("Workaholic", 200, "gold")], lambda t: f"Complete {t} quests", lambda g: g.quests_done)
    ms("Quests", [("First Contact", 1, "bronze"), ("Decisive", 5, "bronze"), ("Space Diplomat", 25, "silver"),
                  ("Troubleshooter", 100, "gold")], lambda t: f"Resolve {t} random events", lambda g: g.events_done)
    ms("Quests", [("Lucky Find", 5, "bronze"), ("Treasure Hunter", 25, "bronze"), ("Crate Baron", 100, "silver"),
                  ("Crate Tycoon", 500, "gold")], lambda t: f"Grab {t} supply crates", lambda g: g.crates)
    ms("Quests", [("Frenzied", 5, "bronze"), ("Frenzy Fanatic", 25, "silver")],
       lambda t: f"Trigger {t} Mining Frenzies", lambda g: g.frenzies)
    # --- Warp & Dark Matter
    ms("Warp", [("Warp Speed", 1, "bronze"), ("Frequent Flyer", 5, "silver"), ("Warp Addict", 20, "gold"),
                ("Time Lord", 50, "platinum")], lambda t: f"Warp {t} times", lambda g: g.warps)
    ms("Warp", [("Spark of Darkness", 1, "bronze"), ("Dark Beginnings", 10, "bronze"), ("Dark Collector", 100, "silver"),
                ("Dark Hoarder", 1000, "silver"), ("Void Lord", 10000, "gold"), ("Heart of the Abyss", 100000, "gold"),
                ("Dark Matter Singularity", 1e6, "platinum")], lambda t: f"Own {nf(t)} Dark Matter", lambda g: g.dm)
    ms("Warp", [("First Perk", 1, "bronze"), ("Shopaholic", 6, "silver"), ("Big Spender", 12, "gold"),
                ("One of Everything", len(PERKS), "platinum")], lambda t: f"Buy {t} Dark Matter perks", lambda g: len(g.perks))
    # --- General
    ms("General", [("Dedicated", 1, "bronze"), ("Devoted", 10, "silver"), ("Obsessed", 100, "gold")],
       lambda t: f"Play for {t} hour{'s' if t > 1 else ''}", lambda g: g.play_time / 3600)
    ms("General", [("Returning Hero", 1, "bronze"), ("Long Nap", 4, "silver")],
       lambda t: f"Come back after being away for {t}+ hours", lambda g: g.away_max)
    add("Perfectionist", "Earn every non-secret achievement", "General", "platinum",
        lambda g: all(a["id"] in g.ach for a in ACHIEVEMENTS if not a["secret"] and a["id"] != "Perfectionist"),
        lambda g: (sum(1 for a in ACHIEVEMENTS if not a["secret"] and a["id"] != "Perfectionist" and a["id"] in g.ach),
                   sum(1 for a in ACHIEVEMENTS if not a["secret"] and a["id"] != "Perfectionist")))
    # --- Secret
    add("Caught in the Act", "Use a developer cheat", "Secret", "bronze", lambda g: "cheated" in g.flags, secret=True)
    add("Quick Draw", "Grab a supply crate within 3 seconds of it appearing", "Secret", "silver",
        lambda g: "quickdraw" in g.flags, secret=True)
    add("Jackpot!", "Win the Cosmic Lottery", "Secret", "silver", lambda g: "jackpot" in g.flags, secret=True)
    add("Pirate Hunter", "Beat the pirates in a fight", "Secret", "silver", lambda g: "pirates" in g.flags, secret=True)
    add("Whisperer", "Listen to the whispers from the void", "Secret", "gold", lambda g: "whisper" in g.flags, secret=True)
    add("Night Owl", "Mine for 10 minutes between midnight and 5 am", "Secret", "silver",
        lambda g: g.night_secs >= 600, secret=True)
    add("Home Sweet Home", "Fly back to Earth after unlocking Mars", "Secret", "bronze",
        lambda g: "home" in g.flags, secret=True)
    return A


ACHIEVEMENTS = build_achievements()
ACH_BY_ID = {a["id"]: a for a in ACHIEVEMENTS}

QUEST_TXT = {"clicks": "Click asteroids {} times", "bought": "Buy {} ships",
             "all_norm": "Mine {} ore (Earth-equivalent)", "crates": "Grab {} supply crates",
             "bldg": "Upgrade colony buildings {} times", "all_sci": "Produce {} science",
             "events_done": "Resolve {} events"}


class Game:
    def __init__(self, load=True, sim=False):
        self.sim = sim                      # headless balancing mode: no events / crates
        self.reset_all()
        self.t = 0.0
        self.buy_mode = 1
        self.cur = 0
        self.travel = None
        self.crate = None
        self.next_crate = random.uniform(25, 50)
        self.buffs = []
        self.event = None
        self.event_t = random.uniform(100, 200)
        self.auto_t = 0.0
        self.autosave_t = 0.0
        self.toasts = []
        self.fx_events = []                 # (kind, data) for the UI to animate
        self.settings = dict(sound=True, volume=0.6)
        self.dev_mult = 1.0                 # developer cheat: production multiplier
        self.click_times = deque()
        self.notified_unlock = -1
        self.recalc()
        if load:
            self.load()
            self.recalc()
        while len(self.quests) < 3:
            self.new_quest()

    # ---------------- state -----------------
    def reset_all(self):
        n = NSITE
        self.ore = [0.0] * n
        self.run_ore = [0.0] * n
        self.all_ore = [0.0] * n
        self.owned = [[0] * NSH for _ in range(n)]
        self.ups = [set() for _ in range(n)]
        self.unlocked = [True] + [False] * (n - 1)
        self.bld = [[0] * NB for _ in range(n)]
        self.credits = self.all_cred = 0.0
        self.science = self.all_sci = 0.0
        self.all_norm = self.run_norm = 0.0
        self.techs = set()
        self.perks = set()
        self.projects = set()
        self.dm = self.dm_spent = 0
        self.warps = self.clicks = self.crates = 0
        self.bought = self.bldg = self.events_done = self.quests_done = 0
        self.ach = set()
        self.ach_bonus = 0.0
        self.quests = []
        self.play_time = 0.0
        self.ups_bought = self.travels = self.frenzies = self.best_burst = 0
        self.away_max = 0.0
        self.night_secs = 0.0
        self.visited = {0}
        self.flags = set()

    def total_ships(self):
        return sum(sum(o) for o in self.owned)

    def save(self):
        d = dict(ver=SAVE_VER, ore=self.ore, run_ore=self.run_ore, all_ore=self.all_ore, owned=self.owned,
                 ups=[sorted(u) for u in self.ups], unlocked=self.unlocked, bld=self.bld,
                 credits=self.credits, all_cred=self.all_cred, science=self.science, all_sci=self.all_sci,
                 all_norm=self.all_norm, run_norm=self.run_norm, techs=sorted(self.techs),
                 perks=sorted(self.perks), projects=sorted(self.projects), dm=self.dm, dm_spent=self.dm_spent, warps=self.warps,
                 clicks=self.clicks, crates=self.crates, bought=self.bought, bldg=self.bldg,
                 events_done=self.events_done, quests_done=self.quests_done, ach=sorted(self.ach),
                 quests=self.quests, cur=self.cur, play_time=self.play_time, ups_bought=self.ups_bought,
                 travels=self.travels, frenzies=self.frenzies, best_burst=self.best_burst, away_max=self.away_max,
                 night_secs=self.night_secs, visited=sorted(self.visited), flags=sorted(self.flags),
                 settings=self.settings, time=time.time())
        try:
            tmp = SAVE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(d, f)
            os.replace(tmp, SAVE)
        except OSError:
            pass

    def load(self):
        try:
            with open(SAVE) as f:
                d = json.load(f)
        except (OSError, ValueError):
            self.toast("Welcome, Miner! Mine the asteroids around Earth to begin.")
            return
        if d.get("ver") != SAVE_VER:           # old single-asteroid save: keep a backup, start fresh
            try:
                os.replace(SAVE, SAVE + ".v1.bak")
            except OSError:
                pass
            self.toast("New solar-system version! Your old save was backed up. Welcome to Earth.", 8)
            return
        try:
            n = NSITE

            def fl(x, default=0.0):
                return [float(v) for v in (list(x) + [default] * n)[:n]]
            self.ore = fl(d["ore"]); self.run_ore = fl(d["run_ore"]); self.all_ore = fl(d["all_ore"])
            self.owned = [(list(map(int, o)) + [0] * NSH)[:NSH] for o in (list(d["owned"]) + [[0] * NSH] * n)[:n]]
            self.ups = [{u for u in s if u in UPG_BY_ID} for s in (list(d["ups"]) + [[]] * n)[:n]]
            self.unlocked = [bool(v) for v in (list(d["unlocked"]) + [False] * n)[:n]]
            self.unlocked[0] = True
            self.bld = [(list(map(int, b)) + [0] * NB)[:NB] for b in (list(d["bld"]) + [[0] * NB] * n)[:n]]
            self.credits = float(d["credits"]); self.all_cred = float(d["all_cred"])
            self.science = float(d["science"]); self.all_sci = float(d["all_sci"])
            self.all_norm = float(d["all_norm"]); self.run_norm = float(d["run_norm"])
            self.techs = {t for t in d["techs"] if t in TECH_BY_ID}
            self.perks = {p for p in d["perks"] if p in PERK_BY_ID}
            self.projects = {int(p) for p in d.get("projects", []) if 0 <= int(p) < NSITE}
            self.dm = int(d["dm"]); self.dm_spent = int(d["dm_spent"])
            self.warps = int(d["warps"]); self.clicks = int(d["clicks"]); self.crates = int(d["crates"])
            self.bought = int(d["bought"]); self.bldg = int(d["bldg"])
            self.events_done = int(d["events_done"]); self.quests_done = int(d["quests_done"])
            self.ach = {a for a in d["ach"] if a in ACH_BY_ID}
            self.ups_bought = int(d.get("ups_bought", 0)); self.travels = int(d.get("travels", 0))
            self.frenzies = int(d.get("frenzies", 0)); self.best_burst = int(d.get("best_burst", 0))
            self.away_max = float(d.get("away_max", 0)); self.night_secs = float(d.get("night_secs", 0))
            self.visited = {int(v) for v in d.get("visited", [0]) if 0 <= int(v) < NSITE} | {0}
            self.flags = {str(f) for f in d.get("flags", [])}
            if isinstance(d.get("settings"), dict):
                self.settings.update({k: v for k, v in d["settings"].items() if k in self.settings})
            self.quests = [q for q in d["quests"] if isinstance(q, dict) and q.get("k") in QUEST_TXT][:3]
            self.cur = int(d.get("cur", 0)) if self.unlocked[int(d.get("cur", 0)) % n] else 0
            self.play_time = float(d.get("play_time", 0))
            real_away = max(0.0, time.time() - float(d["time"]))
            away = min(real_away, OFFLINE_CAP)
            self.away_max = max(self.away_max, real_away / 3600)
        except (KeyError, TypeError, ValueError, IndexError):
            self.reset_all()
            return
        self.update_ach_bonus()
        self.recalc()
        eff = self.E["offline"]
        total = 0.0
        for p in range(NSITE):
            if self.unlocked[p] and self.s_ops[p] > 0:
                g = self.s_ops[p] * away * eff
                self.add_ore(p, g)
                total += g / SC[p]
        self.add_credits(self.cred_ops * away * eff)
        self.add_sci(self.sci_ops * away * eff)
        if away > 60 and total > 0:
            m = int(away // 60)
            self.toast(f"Welcome back! Away {m // 60}h {m % 60}m: your fleets mined {fmt(total)} "
                       f"ore (Earth-equivalent) across {self.n_unlocked} planets", 8)

    # ---------------- maths -----------------
    @property
    def n_unlocked(self):
        return sum(self.unlocked)

    def dm_avail(self):
        return self.dm - self.dm_spent

    def recalc(self):
        E = dict(ore=1.0, click=1.0, cred=1.0, sci=1.0, disc=0.0, crate=0.0, crate_pay=1.0,
                 dm=1.0, auto=0, autoup=0, autocrate=0, start=0.0, offline=OFFLINE_EFF, minebonus=1.0,
                 clickops=0.0, frenzy=0.0, dmbase=TUNE["dmbase"], travel=1.0)
        gm = [1.0] * NSH
        effects = []
        for t in self.techs:
            effects += TECH_BY_ID[t][5]
        for p in self.perks:
            effects += PERK_BY_ID[p][4]
        for k, s in enumerate(SITES):
            if self.unlocked[k]:
                effects += s["fx"]
        for k in self.projects:
            effects += PROJECTS[k][2]
        for e in effects:
            k = e[0]
            if k in ("ore", "click", "cred", "sci", "crate_pay", "dm", "minebonus", "travel"):
                E[k] *= e[1]
            elif k in ("disc", "crate", "clickops", "frenzy", "start", "dmbase"):
                E[k] += e[1]
            elif k == "offline":
                E[k] = max(E[k], e[1])
            elif k in ("auto", "autoup", "autocrate"):
                E[k] = 1
            elif k == "gen":
                gm[e[1]] *= e[2]
        self.E = E
        mine = [0.0] * NSITE
        disc = [0.0] * NSITE
        cred = sci = reactor = crate = 0.0
        for p in range(NSITE):
            if not self.unlocked[p]:
                continue
            bonus = SITES[p]["bonus"]
            for b, L in enumerate(self.bld[p]):
                if not L:
                    continue
                f = 2.0 if bonus == b else (1.5 if bonus == -1 else 1.0)
                if b == 0:
                    mine[p] += 0.03 * L * f
                elif b == 1:
                    cred += 0.5 * L * f * CSC[p]
                elif b == 2:
                    sci += 0.15 * L * f * CSC[p]
                elif b == 3:
                    disc[p] += 0.006 * L * f
                elif b == 4:
                    reactor += 0.025 * L * f
                elif b == 5:
                    crate += 0.04 * L * f
        ach = 1 + self.ach_bonus
        buff = 1.0
        for b in self.buffs:
            buff *= b["mult"]
        self.buff_mult = buff
        self.G = ((1 + E["dmbase"] * math.sqrt(self.dm)) * ach * E["ore"] * (1 + reactor)
                  * (1 + 0.05 * (self.n_unlocked - 1)) * buff * self.dev_mult)
        self.crate_rate = 1 + E["crate"] + crate
        self.cred_ops = cred * E["cred"] * ach
        self.sci_ops = sci * E["sci"] * ach
        self.s_ops = [0.0] * NSITE
        self.s_click = [0.0] * NSITE
        self.s_base = [0.0] * NSITE
        self.s_gm = [None] * NSITE
        self.s_disc = [0.0] * NSITE
        self.s_mine = mine
        for p in range(NSITE):
            g = list(gm)
            cm, co, sm = 1.0, 0.0, 1.0
            for uid in self.ups[p]:
                u = UPG_BY_ID[uid]
                if u["kind"] == "gen":
                    g[u["arg"][0]] *= u["arg"][1]
                elif u["kind"] == "click":
                    cm *= u["arg"]
                elif u["kind"] == "clickops":
                    co += u["arg"]
                else:
                    sm *= u["arg"]
            self.s_gm[p] = g
            self.s_disc[p] = min(0.75, E["disc"] + disc[p])
            base = SC[p] * sum(self.owned[p][i] * SHIPS[i][2] * g[i] for i in range(NSH))
            self.s_base[p] = base
            if self.unlocked[p]:
                self.s_ops[p] = base * (1 + mine[p] * E["minebonus"]) * self.G * sm
            self.s_click[p] = (E["click"] * cm * SC[p] + (E["clickops"] + co) * base) * self.G * sm
        self.norm_ops = sum(self.s_ops[p] / SC[p] for p in range(NSITE))

    def ship_cost1(self, p, i):
        return SHIPS[i][1] * SC[p] * GROWTH ** self.owned[p][i] * (1 - self.s_disc[p])

    def ship_cost(self, p, i, n):
        return geo_cost(self.ship_cost1(p, i), GROWTH, n)

    def ship_count(self, p, i):
        if self.buy_mode == 0:
            return max(1, geo_max(self.ship_cost1(p, i), GROWTH, self.ore[p]))
        return self.buy_mode

    def bld_cost1(self, p, b, L):
        _, res, base, _, _ = BUILDINGS[b]
        return base * (SC[p] if res == "ore" else CSC[p]) * BGROWTH ** L

    def bld_count(self, p, b):
        L = self.bld[p][b]
        room = BMAX - L
        if room <= 0:
            return 0
        if self.buy_mode == 0:
            res = BUILDINGS[b][1]
            have = self.ore[p] if res == "ore" else getattr(self, res)
            return max(1, min(room, geo_max(self.bld_cost1(p, b, L), BGROWTH, have)))
        return min(room, self.buy_mode)

    def bld_total_cost(self, p, b, n):
        return geo_cost(self.bld_cost1(p, b, self.bld[p][b]), BGROWTH, n)

    def have_for(self, p, b):
        res = BUILDINGS[b][1]
        return self.ore[p] if res == "ore" else getattr(self, res)

    def unlock_cost(self, k):
        a, b, cr = SITES[k]["unlock"]
        return [(k - 1, a * SC[k - 1]), (k - 2, b * SC[k - 2] if k >= 2 else 0)], cr

    def can_unlock(self, k):
        if k <= 0 or k >= NSITE or self.unlocked[k] or not self.unlocked[k - 1]:
            return False
        ores, cr = self.unlock_cost(k)
        return all(self.ore[p] >= amt for p, amt in ores) and self.credits >= cr

    def dm_potential(self):
        if self.all_norm < DM_DIV:
            return 0
        return int((self.all_norm / DM_DIV) ** DM_POW * self.E["dm"])

    def warp_gain(self):
        return max(0, self.dm_potential() - self.dm)

    def add_ore(self, p, x):
        self.ore[p] += x
        self.run_ore[p] += x
        self.all_ore[p] += x
        self.run_norm += x / SC[p]
        self.all_norm += x / SC[p]

    def add_credits(self, x):
        self.credits += x
        self.all_cred += x

    def add_sci(self, x):
        self.science += x
        self.all_sci += x

    # ---------------- actions -----------------
    def toast(self, msg, secs=4):
        self.toasts.append([msg, secs])

    def fx(self, kind, data=None):
        if not self.sim:
            self.fx_events.append((kind, data))

    def buy_ship(self, p, i):
        n = self.ship_count(p, i)
        cost = self.ship_cost(p, i, n)
        if self.unlocked[p] and self.ore[p] >= cost:
            self.ore[p] -= cost
            self.owned[p][i] += n
            self.bought += n
            self.fx("buy", (p, i))
            self.recalc()
            return True
        return False

    def avail_upgrades(self, p):
        out = []
        for u in UPGRADES:
            if u["id"] in self.ups[p]:
                continue
            req = u["req"]
            if req[0] == "own":
                if self.owned[p][req[1]] >= req[2]:
                    out.append(u)
            elif self.run_ore[p] >= req[1] * SC[p]:
                out.append(u)
        return sorted(out, key=lambda u: u["cost"])

    def buy_upgrade(self, p, uid):
        u = UPG_BY_ID[uid]
        c = u["cost"] * SC[p]
        if self.unlocked[p] and uid not in self.ups[p] and self.ore[p] >= c:
            self.ore[p] -= c
            self.ups[p].add(uid)
            self.ups_bought += 1
            self.recalc()
            return True
        return False

    def buy_all_upgrades(self, p):
        n = 0
        for u in self.avail_upgrades(p):
            if self.ore[p] >= u["cost"] * SC[p]:
                self.ore[p] -= u["cost"] * SC[p]
                self.ups[p].add(u["id"])
                n += 1
        if n:
            self.ups_bought += n
            self.recalc()
        return n

    def buy_building(self, p, b):
        n = self.bld_count(p, b)
        if n <= 0 or not self.unlocked[p]:
            return False
        cost = self.bld_total_cost(p, b, n)
        res = BUILDINGS[b][1]
        if self.have_for(p, b) >= cost:
            if res == "ore":
                self.ore[p] -= cost
            else:
                setattr(self, res, getattr(self, res) - cost)
            self.bld[p][b] += n
            self.bldg += n
            self.recalc()
            return True
        return False

    def unlock_planet(self, k):
        if not self.can_unlock(k):
            return False
        ores, cr = self.unlock_cost(k)
        for p, amt in ores:
            self.ore[p] -= amt
        self.credits -= cr
        self.unlocked[k] = True
        self.add_ore(k, SUPPLY * SC[k])
        self.toast(f"{SITES[k]['name']} unlocked! New ore: {SITES[k]['ore']}.  {SITES[k]['perk']}", 7)
        self.fx("unlock", k)
        self.recalc()
        return True

    def start_travel(self, k):
        if k == self.cur or not self.unlocked[k] or self.travel:
            return False
        dur = min(3.2, 1.0 + 0.22 * abs(k - self.cur)) * self.E["travel"]
        self.travels += 1
        self.visited.add(k)
        if k == 0 and self.unlocked[2]:
            self.flags.add("home")
        self.fx("travel", k)
        if self.sim:
            self.cur = k
            return True
        self.travel = dict(to=k, t=0.0, dur=dur, swapped=False)
        return True

    def can_buy_project(self, p):
        if p in self.projects or not self.unlocked[p]:
            return False
        ore, cr, sci = project_cost(p)
        return self.ore[p] >= ore and self.credits >= cr and self.science >= sci

    def buy_project(self, p):
        if not self.can_buy_project(p):
            return False
        ore, cr, sci = project_cost(p)
        self.ore[p] -= ore
        self.credits -= cr
        self.science -= sci
        self.projects.add(p)
        self.toast(f"Megaproject complete: {PROJECTS[p][0]}!  {PROJECTS[p][1]}", 7)
        self.fx("project", p)
        self.recalc()
        return True

    def research(self, tid):
        t = TECH_BY_ID[tid]
        if tid in self.techs or any(p not in self.techs for p in t[3]):
            return False
        if self.science >= t[2]:
            self.science -= t[2]
            self.techs.add(tid)
            self.toast(f"Researched: {t[1]}", 4)
            self.recalc()
            return True
        return False

    def buy_perk(self, pid):
        p = PERK_BY_ID[pid]
        if pid not in self.perks and self.dm_avail() >= p[2]:
            self.dm_spent += p[2]
            self.perks.add(pid)
            self.recalc()
            return True
        return False

    def do_warp(self, force=False):
        gain = self.warp_gain()
        if gain < 1:
            if not force:
                return False
            gain = 1
        self.dm += gain
        self.warps += 1
        n = NSITE
        self.ore = [0.0] * n
        self.run_ore = [0.0] * n
        self.owned = [[0] * NSH for _ in range(n)]
        self.ups = [set() for _ in range(n)]
        self.run_norm = 0.0
        self.crate = None
        self.buffs = []
        self.recalc()
        for p in range(n):
            if self.unlocked[p]:
                self.add_ore(p, (SUPPLY + self.E["start"]) * SC[p])
        self.toast(f"WARP COMPLETE!  +{gain} Dark Matter", 5)
        self.fx("warp", gain)
        self.save()
        return True

    def hard_reset(self):
        self.reset_all()
        self.cur = 0
        self.crate = None
        self.buffs = []
        self.travel = None
        self.recalc()
        while len(self.quests) < 3:
            self.new_quest()
        self.toast("Save wiped. A new journey begins.", 4)
        self.save()

    def click(self, pos=None):
        p = self.cur
        x = self.s_click[p]
        self.add_ore(p, x)
        self.clicks += 1
        self.click_times.append(self.t)
        while self.click_times and self.click_times[0] < self.t - 10:
            self.click_times.popleft()
        self.best_burst = max(self.best_burst, len(self.click_times))
        return x

    def add_buff(self, name, mult, secs):
        if name == "Mining Frenzy":
            self.frenzies += 1
        for b in self.buffs:
            if b["name"] == name:
                b["t"] = b["dur"] = max(b["t"], secs)
                b["mult"] = max(b["mult"], mult)
                return
        self.buffs.append(dict(name=name, mult=mult, t=secs, dur=secs))

    def grab_crate(self):
        c = self.crate
        self.crate = None
        self.crates += 1
        if c and c.get("life", 99) < 3:
            self.flags.add("quickdraw")
        p = self.cur
        pay = self.E["crate_pay"]
        r = random.random()
        if r < 0.20 and self.cred_ops > 0:
            gain = (self.cred_ops * 120 + 50) * pay
            self.add_credits(gain)
            self.toast(f"Supply crate! +{fmt(gain)} credits", 3)
        elif r < 0.45:
            self.add_buff("Mining Frenzy", 7, 25 + self.E["frenzy"])
            self.toast("MINING FRENZY! Production x7", 4)
        else:
            gain = (max(self.s_ops[p] * 90, self.s_click[p] * 40) + 13 * SC[p]) * pay
            self.add_ore(p, gain)
            self.toast(f"Supply crate! +{fmt(gain)} {SITES[p]['ore']}", 3)
        self.fx("crate", c)
        self.recalc()

    # ---------------- quests -----------------
    def new_quest(self):
        used = {q["k"] for q in self.quests}
        opts = ["clicks", "bought", "all_norm", "crates", "events_done"]
        if any(self.bld[p][b] for p in range(NSITE) for b in range(NB)) or self.n_unlocked > 1:
            opts.append("bldg")
        if self.sci_ops > 0:
            opts.append("all_sci")
        opts = [o for o in opts if o not in used] or opts
        k = random.choice(opts)
        p = self.cur
        if k == "clicks":
            tgt = random.choice([50, 100, 200, 400])
        elif k == "bought":
            tgt = random.choice([10, 25, 50, 100])
        elif k == "all_norm":
            tgt = float(f"{max(1000, self.norm_ops * random.choice([300, 600, 1200])):.2g}")
        elif k == "crates":
            tgt = random.choice([1, 2])
        elif k == "bldg":
            tgt = random.choice([3, 6, 12])
        elif k == "all_sci":
            tgt = float(f"{self.sci_ops * random.choice([300, 600]):.2g}")
        else:
            tgt = random.choice([1, 2])
        rk = random.choice(["ore", "ore", "credits", "science", "frenzy"])
        if (rk == "credits" and self.cred_ops <= 0) or (rk == "science" and self.sci_ops <= 0):
            rk = "ore"
        mult = random.choice([240, 400, 600])
        if rk == "ore":
            amt = max(self.s_ops[p] * mult + 100 * SC[p], 100)
        elif rk == "credits":
            amt = max(self.cred_ops * mult, 50)
        elif rk == "science":
            amt = max(self.sci_ops * mult, 20)
        else:
            amt = 20
        self.quests.append(dict(k=k, tgt=tgt, base=getattr(self, k), r=rk, amt=float(f"{amt:.3g}"), site=p))

    def quest_prog(self, q):
        return max(0.0, getattr(self, q["k"]) - q["base"])

    def claim_quest(self, idx):
        q = self.quests[idx]
        if self.quest_prog(q) < q["tgt"]:
            return False
        rk, amt = q["r"], q["amt"]
        site = q.get("site", 0)
        if rk == "ore":
            self.add_ore(site, amt)
        elif rk == "credits":
            self.add_credits(amt)
        elif rk == "science":
            self.add_sci(amt)
        else:
            self.add_buff("Mining Frenzy", 7, amt)
        self.quests_done += 1
        del self.quests[idx]
        self.new_quest()
        what = f"{fmt(amt)} {SITES[site]['ore']}" if rk == "ore" else (f"{fmt(amt)} {rk}" if rk != "frenzy" else f"{amt:.0f}s of frenzy")
        self.toast(f"Quest complete! +{what}", 4)
        self.recalc()
        return True

    # ---------------- events -----------------
    def pick_event(self, force=None):
        pool = ["meteor", "pirates", "flare", "lottery", "derelict"]
        if self.cred_ops > 0:
            pool.append("trader")
        if self.sci_ops > 0:
            pool += ["grant", "distress"]
        if random.random() < 0.06:
            pool = ["whisper"]
        name = force or random.choice(pool)
        g = self
        p = self.cur
        nm = SITES[p]["name"]
        ore = SITES[p]["ore"]
        if name == "meteor":
            def harvest():
                if random.random() < 0.7:
                    x = g.s_ops[p] * 300 + 100 * SC[p]; g.add_ore(p, x)
                    return f"The debris yielded {fmt(x)} {ore}!"
                x = g.ore[p] * 0.03; g.ore[p] -= x
                return f"Debris smashed your ships. Lost {fmt(x)} {ore}."
            return dict(title=f"Meteor Shower at {nm}", text="A dense meteor swarm is passing close. Harvesting it "
                        "is lucrative, but dangerous.", opts=[("Harvest the debris (risky)", harvest),
                        ("Steer clear", lambda: "You wait it out safely.")])
        if name == "pirates":
            def pay():
                x = g.ore[p] * 0.08; g.ore[p] -= x
                return f"You paid {fmt(x)} {ore} in tribute."

            def fight():
                if random.random() < 0.5:
                    g.flags.add("pirates")
                    x = g.s_ops[p] * 500 + 200 * SC[p]; g.add_ore(p, x)
                    return f"Victory! Salvaged {fmt(x)} {ore} from the wrecks."
                x = g.ore[p] * 0.2; g.ore[p] -= x
                return f"Defeat... lost {fmt(x)} {ore}."
            return dict(title=f"Pirate Raid at {nm}", text="Space pirates demand tribute, or you can fight them off.",
                        opts=[("Pay 8% of your ore", pay), ("Fight them! (50/50)", fight)])
        if name == "flare":
            def over():
                g.add_buff("Overclock", 2.5, 60)
                if random.random() < 0.3:
                    x = g.ore[p] * 0.1; g.ore[p] -= x
                    return f"Overclocked! x2.5 for 60s, but a reactor blew: -{fmt(x)} {ore}."
                return "Overclocked! Production x2.5 for 60s."

            def shield():
                g.add_buff("Shielded", 1.25, 45)
                return "Shields up. Production x1.25 for 45s."
            return dict(title="Solar Flare", text="A solar flare is washing over the system. Overclock your "
                        "reactors, or play it safe.", opts=[("Overclock (risky)", over), ("Raise shields", shield)])
        if name == "lottery":
            def bet():
                x = g.ore[p] * 0.10
                g.ore[p] -= x
                if random.random() < 0.3:
                    g.flags.add("jackpot")
                    g.add_ore(p, x * 4)
                    return f"JACKPOT! Won {fmt(x * 4)} {ore}."
                return f"Lost your {fmt(x)} {ore} stake."
            return dict(title="Cosmic Lottery", text="A mysterious vendor offers a ticket: 30% chance to "
                        "win 4x your stake (10% of your ore here).", opts=[("Gamble!", bet), ("Walk away", lambda: "Wise.")])
        if name == "derelict":
            def salvage():
                have = [i for i in range(NSH) if g.owned[p][i] > 0]
                if have and random.random() < 0.6:
                    i = random.choice(have)
                    n = random.randint(3, 8)
                    g.owned[p][i] += n
                    return f"Salvaged {n} free {SHIPS[i][0]}s!"
                x = g.s_ops[p] * 200 + 150 * SC[p]; g.add_ore(p, x)
                return f"Found a cargo hold with {fmt(x)} {ore}."
            return dict(title="Derelict Ship", text=f"An abandoned vessel drifts near {nm}. Salvage it?",
                        opts=[("Salvage it", salvage), ("Leave it", lambda: "You move on.")])
        if name == "trader":
            def trade():
                x = max(g.cred_ops * 400, 100); g.add_credits(x)
                y = g.ore[p] * 0.2; g.ore[p] -= y
                return f"Traded {fmt(y)} {ore} for {fmt(x)} credits."
            return dict(title="Alien Trader", text=f"A trader offers credits in exchange for 20% of your {ore}.",
                        opts=[("Accept the deal", trade), ("Decline", lambda: "The trader leaves.")])
        if name == "grant":
            def grant():
                x = g.sci_ops * 500 + 50; g.add_sci(x)
                return f"Accepted the grant: +{fmt(x)} science."

            def decline():
                g.add_ore(p, g.s_ops[p] * 150 + 100 * SC[p])
                return "A modest ore donation arrives instead."
            return dict(title="Research Grant", text="The Galactic Academy offers funding for your labs.",
                        opts=[("Accept grant", grant), ("Decline, take ore instead", decline)])
        if name == "distress":
            def rescue():
                x = g.ore[p] * 0.05; g.ore[p] -= x
                if random.random() < 0.6:
                    s = g.sci_ops * 800 + 80; g.add_sci(s)
                    return f"Rescued scientists gave you {fmt(s)} science!"
                g.add_buff("Grateful Crew", 3, 40)
                return "The grateful crew boosts production x3 for 40s!"
            return dict(title="Distress Signal", text="A research vessel is stranded. Helping costs 5% of "
                        "your ore, but they may reward you.", opts=[("Rescue them", rescue),
                        ("Ignore the signal", lambda: "The signal fades.")])

        def listen():
            g.flags.add("whisper")
            g.dm += 1
            return "A whisper from the void... +1 Dark Matter!"
        return dict(title="Whispers From the Void", text="You hear something deep in the dark between stars.",
                    opts=[("Listen closely", listen), ("Cover your ears", lambda: "Silence returns.")])

    def resolve_event(self, fn):
        msg = fn()
        self.event = None
        self.events_done += 1
        self.toast(msg, 6)
        self.event_t = random.uniform(150, 300)
        self.recalc()

    # ---------------- tick -----------------
    def step(self, dt):
        self.t += dt
        self.play_time += dt
        self.recalc()
        for p in range(NSITE):
            if self.unlocked[p] and self.s_ops[p] > 0:
                self.add_ore(p, self.s_ops[p] * dt)
        self.add_credits(self.cred_ops * dt)
        self.add_sci(self.sci_ops * dt)
        for b in self.buffs:
            b["t"] -= dt
        self.buffs = [b for b in self.buffs if b["t"] > 0]
        tr = self.travel
        if tr:
            tr["t"] += dt
            if not tr["swapped"] and tr["t"] >= tr["dur"] / 2:
                tr["swapped"] = True
                self.cur = tr["to"]
            if tr["t"] >= tr["dur"]:
                self.travel = None
        if not self.sim:
            if time.localtime().tm_hour < 5:
                self.night_secs += dt
            self.step_crate(dt)
            self.step_events(dt)
        if self.E["auto"] or self.E["autoup"]:
            self.auto_t += dt
            if self.auto_t > 1.0:
                self.auto_t = 0
                self.auto_buy()
        for t in self.toasts:
            t[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0][-4:]
        # one-time hint when the next planet becomes affordable
        nxt = next((k for k in range(1, NSITE) if not self.unlocked[k]), None)
        if nxt is not None and nxt != self.notified_unlock and self.can_unlock(nxt) and not self.sim:
            self.notified_unlock = nxt
            self.toast(f"You can unlock {SITES[nxt]['name']}!  (Planets tab)", 6)
        if not self.sim or int(self.t) % 5 == 0:
            self.check_achievements()
        if not self.sim:
            self.autosave_t += dt
            if self.autosave_t > 15:
                self.autosave_t = 0
                self.save()

    def update_ach_bonus(self):
        self.ach_bonus = sum(TIER_BONUS[ACH_BY_ID[a]["tier"]] for a in self.ach if a in ACH_BY_ID)

    def check_achievements(self):
        new = []
        for a in ACHIEVEMENTS:
            if a["id"] not in self.ach and a["cond"](self):
                self.ach.add(a["id"])
                new.append(a)
        if new:
            self.update_ach_bonus()
            for a in new:
                self.fx("ach", a["id"])
        return new

    def fast_forward(self, seconds):
        """Developer helper: add `seconds` of production to every planet, credits and science."""
        self.recalc()
        for p in range(NSITE):
            if self.unlocked[p] and self.s_ops[p] > 0:
                self.add_ore(p, self.s_ops[p] * seconds)
        self.add_credits(self.cred_ops * seconds)
        self.add_sci(self.sci_ops * seconds)

    def auto_buy(self):
        """Auto-buyers only spend up to 25% of a planet's stockpile per purchase, so savings can pile up."""
        for p in range(NSITE):
            if not self.unlocked[p]:
                continue
            cap = 0.25 * self.ore[p]
            if self.E["auto"]:
                top = max([i for i in range(NSH) if self.owned[p][i] > 0], default=-1) + 1
                for i in range(min(top, NSH - 1), -1, -1):
                    c = self.ship_cost1(p, i)
                    if c <= cap:
                        self.ore[p] -= c
                        self.owned[p][i] += 1
                        self.bought += 1
                        break
            if self.E["autoup"]:
                for u in self.avail_upgrades(p):
                    c = u["cost"] * SC[p]
                    if c <= 0.25 * self.ore[p]:
                        self.ore[p] -= c
                        self.ups[p].add(u["id"])
                        self.ups_bought += 1
                        break

    def step_crate(self, dt):
        if self.crate is None:
            self.next_crate -= dt * self.crate_rate
            if self.next_crate <= 0 and not self.travel:
                left = random.random() < 0.5
                self.crate = dict(x=-30 if left else 650, y=random.uniform(190, 600),
                                  vx=(90 if left else -90), ph=random.uniform(0, 6), life=0)
                self.next_crate = random.uniform(45, 100)
        else:
            c = self.crate
            c["x"] += c["vx"] * dt
            c["life"] += dt
            c["yy"] = c["y"] + math.sin(c["life"] * 2 + c["ph"]) * 35
            if c["x"] < -50 or c["x"] > 700:
                self.crate = None
            elif self.E["autocrate"] and c["life"] > 1.5:
                self.grab_crate()

    def step_events(self, dt):
        if self.event is None:
            self.event_t -= dt
            if self.event_t <= 0 and self.all_norm > 500 and not self.travel:
                self.event = self.pick_event()
                self.event["left"] = 90.0
        else:
            self.event["left"] -= dt
            if self.event["left"] <= 0:
                self.event = None
                self.event_t = random.uniform(150, 300)
                self.toast("The moment passed.", 3)


apply_tune()


def dm_bonus(dm, dmbase):
    return 1 + dmbase * math.sqrt(dm)
