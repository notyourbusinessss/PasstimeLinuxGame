"""The Galactic Threat Director: decides when, where and how hard the enemy attacks.

Pure game logic (no pygame). It works on a core.Game instance `g` and keeps all of its state on that
object, so it is saved with the game and the balancing bot (sim.py) can run it headless.

What it does
  * keeps an *aggression* level: the weaker your fleet is compared with the enemies next to you, and the more
    undefended your planets are, the bolder the enemy gets;
  * schedules enemy **raids** of three sizes (small raid, regional assault, system invasion) against your planets,
    preferring the weakly defended ones;
  * schedules **counter-offensives** that try to retake systems you liberated - from several enemy fronts at once, hitting
    harder the stronger the enemy next door is, and bolder while your armies are away on campaign; a system is held by its
    garrison or by its region's share of the defence pool (see generals.py), never by an army that is out fighting;
  * announces attacks in advance depending on your **Intel** armory upgrade, and lets you **Fortify** the target;
  * stays quiet for a while after loading a save, Warping or Ascending, and never acts while the game is closed;
  * keeps the galaxy at **peace** until a war starts: either you invade a faction (a declaration of war), or a faction
    that borders you loses patience (its *tension* fills up) and invades you. Only factions at war attack you, and you
    can sue for peace to end a war.
"""
import math
import random

import core
import generals
from core import FACTIONS, NSEC, NSITE, SECTORS, SITES, fmt, win_chance

INTEL = 4                       # index of the Intel track in core.ARMORY
TIERS = [  # name, power multiplier, ore lost on failure, planets hit, credit loot multiplier, sectors you must hold, raiders drawn
    dict(name="Small raid", mult=1.0, loss=0.04, planets=1, loot=1.0, need=0, count=8),
    dict(name="Regional assault", mult=3.0, loss=0.10, planets=1, loot=4.0, need=3, count=16),
    dict(name="System invasion", mult=6.0, loss=0.14, planets=3, loot=10.0, need=8, count=24),
]
LEVELS = ["Quiet", "Watchful", "Hostile", "Aggressive", "Warlike"]
FORTIFY_PLANET = 2.5            # defence multiplier of a fortified planet
FORTIFY_SECTOR = 2.0            # defence multiplier of a fortified sector
OFFENSIVE_FRAC = 0.3            # an enemy offensive brings this share of the strength of the system it starts from...
OFFENSIVE_MIN, OFFENSIVE_MAX = 0.8, 6.0     # ...but between this many times the power of the system it attacks
MAX_STRIKES = 3                 # the most counter-offensives launched at once (one per enemy front)


# ------------------------------------------------------------------ helpers
def intel(g):
    """How much the player learns about an incoming attack: 0 nothing, 1 a signal, 2 the target, 3 size, 4 exact odds."""
    lvl = g.armory[INTEL]
    return 0 if lvl < 1 else 1 if lvl < 3 else 2 if lvl < 5 else 3 if lvl < 7 else 4


def lead_time(g, offensive=False):
    lvl = g.armory[INTEL]
    if lvl < 1:
        return 0.0
    return 60.0 + 100.0 * lvl if offensive else 15.0 + 45.0 * lvl


def hostility_mult(g, fac):
    return min(2.0, 1.0 + 0.15 * g.hostility.get(fac, 0.0))


# ------------------------------------------------------------------ war and peace
TENSION_TIME = 5400.0           # seconds of border contact until a faction of average temper declares war (90 minutes)
TRUCE_TIME = 2700.0             # how long a truce lasts after you make peace
WAR_MIN = 600.0                 # a war has to last this long before you can sue for peace
TEMPER = dict(pirates=1.4, hive=1.2, devourer=1.1, iron=1.0, void=0.9, crystal=0.7)     # how quickly each faction loses patience


def at_war(g, fac):
    return fac in g.war


def war_fronts(g):
    """Enemy systems linked to your territory whose faction is at war with you: the only places attacks come from."""
    return [k for k in g.border() if SECTORS[k]["faction"] in g.war]


def borders(g, fac):
    g.border()
    return fac in g._border_facs


def stance(g, fac):
    return "war" if fac in g.war else ("truce" if g.truce.get(fac, 0.0) > 0 else "peace")


def war_age(g, fac):
    return g.play_time - g.war[fac]["since"] if fac in g.war else 0.0


def peace_cost(g, fac):
    return max(2000.0, g.cred_ops * 600.0)


def can_sue(g, fac):
    """(ok, why not): you can sue for peace after 10 minutes of war, when you are not attacking that faction."""
    if fac not in g.war:
        return False, "Not at war"
    if war_age(g, fac) < WAR_MIN:
        return False, f"Too early ({int((WAR_MIN - war_age(g, fac)) // 60) + 1} min)"
    if any(SECTORS[c["k"]]["faction"] == fac for c in g.campaigns):
        return False, "Your fleet is attacking them"
    if g.credits < peace_cost(g, fac):
        return False, "Not enough credits"
    return True, ""


def declare_war(g, fac, by):
    """by = "player" (you invade) or "enemy" (they invade you). Returns False if already at war."""
    if fac in g.war or fac not in FACTIONS:
        return False
    broke_truce = g.truce.pop(fac, 0.0) > 0
    g.war[fac] = dict(since=g.play_time, by=by)
    g.tension[fac] = 0.0
    name = FACTIONS[fac]["name"]
    if by == "player":
        g.wars_declared += 1
        g.raid_t = min(g.raid_t, 300.0)               # they answer within a few minutes
        text = f"You declared war on the {name}"
        if broke_truce:
            g.hostility[fac] = g.hostility.get(fac, 0.0) + 1.0
            text += " (the truce is broken)"
        g.toast(f"WAR! You invade the {name}. Their fleets will strike back.", 7)
    else:
        g.wars_suffered += 1
        g.raid_t = min(g.raid_t, 120.0)
        text = f"The {name} declared war on you"
        g.toast(f"WAR! The {name} invade! Defend your planets and sectors.", 8)
    log(g, text)
    core.log.info("War: %s (%s)", text, by)
    g.fx("war", dict(fac=fac, by=by))
    if by == "enemy":
        first_strike(g, fac)
    return True


def first_strike(g, fac):
    """The opening move of a faction that declares war: a counter-offensive on your weakest border sector, or a raid."""
    exposed = exposed_systems(g, fac)
    if len(g.conquered) - 1 >= 2 and exposed:
        dmap = generals.defence_map(g)
        k = min(exposed, key=lambda q: sector_defense(g, q, dmap=dmap) / max(g.sector_power(q), 1e-9))
        if schedule_offensive(g, target=k, src_fac=fac):
            return
    schedule_raid(g)


def end_war(g, fac, why):
    if g.war.pop(fac, None) is None:
        return
    g.incoming = [i for i in g.incoming if i["fac"] != fac]       # their fleets turn back
    log(g, f"War with the {FACTIONS[fac]['name']} ended: {why}")
    core.log.info("War with %s ended: %s", fac, why)


def sue_for_peace(g, fac):
    ok, _ = can_sue(g, fac)
    if not ok:
        return False
    g.credits -= peace_cost(g, fac)
    end_war(g, fac, "you sued for peace")
    g.truce[fac] = TRUCE_TIME
    g.tension[fac] = 0.0
    g.peaces_made += 1
    g.toast(f"PEACE with the {FACTIONS[fac]['name']}. A truce holds for {int(TRUCE_TIME // 60)} minutes.", 7)
    g.fx("peace", dict(fac=fac))
    return True


def step_war(g, dt):
    """Truces run out, tension builds at the border of factions at peace, and a faction at the limit declares war."""
    rate = dt / TENSION_TIME * (1.0 + 0.25 * min(8, len(g.conquered) - 1))      # the more of the galaxy you hold, the more they fear you
    for fac in FACTIONS:
        if fac in g.war:
            if g.faction_left(fac) <= 0:
                end_war(g, fac, "nothing of them is left")
            continue
        left = g.truce.get(fac, 0.0)
        if left > 0:
            g.truce[fac] = left - dt
            if g.truce[fac] <= 0:
                g.truce.pop(fac, None)
                g.toast(f"The truce with the {FACTIONS[fac]['name']} has ended.", 5)
            continue
        t = g.tension.get(fac, 0.0)
        if not borders(g, fac):
            g.tension[fac] = max(0.0, t - dt / 1200.0)
            continue
        t += rate * TEMPER.get(fac, 1.0)
        g.tension[fac] = min(1.0, t)
        if t >= 0.8 and fac not in g.warned:
            g.warned.add(fac)
            g.toast(f"The {FACTIONS[fac]['name']} are massing on your border - war is near!", 8)
        if t >= 1.0:
            g.warned.discard(fac)
            declare_war(g, fac, "enemy")


def weakest_front(g):
    front = war_fronts(g)
    return min(front, key=g.sector_power) if front else None


def planet_defense(g, p, fortified=False):
    return g.planet_power(p, defense=True) * (FORTIFY_PLANET if fortified else 1.0)


def sector_defense(g, k, fortified=False, strikes=1, dmap=None):
    """What defends system k: its garrison, or the defence pool of its region (armies on campaign defend nothing), whichever is
    bigger. dmap is generals.defence_map(g) when many systems are asked about at once."""
    base = max(g.garrison.get(k, 0.0), generals.defence_power(g, k, strikes, dmap))
    return base * (FORTIFY_SECTOR if fortified else 1.0)


def offensive_power(g, target, src, fac, roll=1.0):
    """Strength of a counter-offensive from the enemy system src against your system target: a share of what src can field,
    never less than the target's own strength and never more than OFFENSIVE_MAX times it."""
    tp = g.sector_power(target)
    mult = max(OFFENSIVE_MIN, min(OFFENSIVE_MAX, OFFENSIVE_FRAC * g.sector_power(src) / max(tp, 1e-9)))
    return tp * mult * roll * hostility_mult(g, fac)


def exposed_systems(g, fac=None):
    """Systems you hold that touch an enemy system of a faction at war with you (of faction fac, if given): what they can attack."""
    held = g.conquered
    out = set()
    for e in war_fronts(g):
        if fac is None or SECTORS[e]["faction"] == fac:
            out.update(n for n in SECTOR_LINKS_[e] if n in held and n != 0)
    return sorted(out)


def strikes_with(g, inc):
    """How many counter-offensives hit the same region at the same time as this one (itself included): they share its defence."""
    r = generals.region_of(inc["target"])
    return 1 + sum(1 for o in g.incoming if o["kind"] == "offensive" and o["id"] != inc["id"] and generals.region_of(o["target"]) == r)


def away(g):
    """0..1: how much of the fleet that is free to go out is away on campaign (the defence pool never leaves, so it does not count)."""
    return min(1.0, g.committed_share() / max(0.05, 1.0 - g.defence))


def aggression(g):
    """0..1: how bold the enemy feels."""
    if not g.galaxy_open:
        return 0.0
    k = weakest_front(g)
    if k is None:                                   # at peace nobody attacks
        return 0.0
    fp = max(1.0, g.fleet_power())
    ep = g.sector_power(k)
    a = 0.3 + 0.3 * math.tanh(0.5 * math.log(ep / fp))
    hostile = [h for h in g.hostility.values()]
    if hostile:
        a += 0.1 * min(1.0, (sum(hostile) / len(hostile)) / 3.0)
    rp = 0.12 * ep
    planets = [p for p in range(NSITE) if g.unlocked[p]]
    weak = sum(1 for p in planets if planet_defense(g, p) < rp)
    a += 0.2 * weak / max(1, len(planets))
    a += 0.25 * away(g)                             # they strike while your armies are away
    a += 0.15 * max(0.0, 1.0 - g.defence / 0.3)     # ...and when you leave your borders unguarded
    return max(0.0, min(1.0, a))


def level(g):
    return min(4, int(aggression(g) * 5))


def log(g, text):
    g.director_log.append((g.play_time, text))
    del g.director_log[:-8]


def fortify_cost(g, inc):
    if inc["kind"] == "offensive":
        return max(500.0, g.cred_ops * 300)
    return max(100.0, g.cred_ops * 90)


def incoming_chance(g, inc, key=None):
    """The player's chance to hold, for the UI and the bot."""
    if inc["kind"] == "offensive":
        return win_chance(sector_defense(g, inc["target"], bool(inc["fort"]), strikes_with(g, inc)), inc["power"])
    p = key if key is not None else inc["targets"][0]
    return win_chance(planet_defense(g, p, p in inc["fort"]), inc["power"])


# ------------------------------------------------------------------ scheduling
def next_id(g):
    g.director_id += 1
    return g.director_id


def interval(g, base_low, base_high):
    a = aggression(g)
    return (base_high + (base_low - base_high) * a) * random.uniform(0.75, 1.25)


def pick_targets(g, n):
    planets = [p for p in range(NSITE) if g.unlocked[p]]
    if not planets:
        return []
    rp = 0.12 * g.sector_power(weakest_front(g) or 1)
    weights = [1.0 / (0.25 + planet_defense(g, p) / max(rp, 1e-9)) for p in planets]
    chosen = []
    for _ in range(min(n, len(planets))):
        p = random.choices(planets, weights=weights)[0]
        i = planets.index(p)
        chosen.append(p)
        planets.pop(i)
        weights.pop(i)
    return chosen


def schedule_raid(g, tier=None, lead=None, targets=None):
    """Create an enemy raid. Returns the incoming record, or None if there is nobody to raid you."""
    src = weakest_front(g)
    if src is None:
        return None
    if tier is None:
        n = len(g.conquered) - 1
        a = aggression(g)
        weights = [1.0, (0.1 + 0.5 * a) if n >= TIERS[1]["need"] else 0.0, (0.03 + 0.25 * a) if n >= TIERS[2]["need"] else 0.0]
        tier = random.choices(range(3), weights=weights)[0]
    t = TIERS[tier]
    fac = SECTORS[src]["faction"]
    tg = targets if targets is not None else pick_targets(g, t["planets"])
    if not tg:
        return None
    inc = dict(id=next_id(g), kind="raid", tier=tier, fac=fac, src=src, targets=tg, t=0.0,
               eta=lead if lead is not None else lead_time(g), fort=[],
               power=0.12 * g.sector_power(src) * t["mult"] * hostility_mult(g, fac))
    announce(g, inc)
    if inc["eta"] <= 0:
        resolve(g, inc)
    else:
        g.incoming.append(inc)
    return inc


def schedule_offensive(g, target=None, lead=None, src_fac=None):
    """An enemy counter-offensive against a system you hold that borders the territory of a faction at war with you (of faction
    src_fac, if given). The weakly defended systems are the likeliest targets."""
    if target is None:
        under_attack = {o["target"] for o in g.incoming if o["kind"] == "offensive"}
        exposed = [k for k in exposed_systems(g, src_fac) if k not in under_attack]
        if not exposed:
            return None
        dmap = generals.defence_map(g)
        weights = [1.0 / (0.3 + sector_defense(g, k, dmap=dmap) / max(g.sector_power(k), 1e-9)) for k in exposed]
        target = random.choices(exposed, weights=weights)[0]
    enemies = [n for n in SECTOR_LINKS_[target] if n not in g.conquered and (src_fac is None or SECTORS[n]["faction"] == src_fac)]
    enemies = [n for n in enemies if SECTORS[n]["faction"] in g.war] or enemies
    src = max(enemies, key=g.sector_power) if enemies else target          # the strongest neighbour sends the fleet
    fac = SECTORS[src]["faction"] or SECTORS[target]["faction"]
    inc = dict(id=next_id(g), kind="offensive", tier=-1, fac=fac, src=src, target=target, targets=[], t=0.0,
               eta=lead if lead is not None else lead_time(g, True), fort=[],
               power=offensive_power(g, target, src, fac, random.uniform(0.9, 1.2)))
    announce(g, inc)
    if inc["eta"] <= 0:
        resolve(g, inc)
    else:
        g.incoming.append(inc)
    return inc


def schedule_strikes(g):
    """A wave of counter-offensives: one from each enemy faction at war that touches your territory (at most MAX_STRIKES)."""
    facs = sorted({SECTORS[k]["faction"] for k in war_fronts(g)})
    random.shuffle(facs)
    return sum(1 for fac in facs[:MAX_STRIKES] if schedule_offensive(g, src_fac=fac))


def describe(g, inc, level_=None):
    """What the player is told about an incoming attack, at their Intel level."""
    lv = intel(g) if level_ is None else level_
    fname = FACTIONS[inc["fac"]]["name"] if inc["fac"] else "Enemy"
    if inc["kind"] == "offensive":
        if lv <= 1:
            return "Unknown ships are massing near your territory"
        s = SECTORS[inc["target"]]["name"]
        return f"{fname} counter-offensive against {s}" if lv < 3 else \
            f"{fname} counter-offensive against {s}  ({incoming_chance(g, inc) * 100:.0f}% to hold)" if lv >= 4 else \
            f"{fname} counter-offensive against {s}  (power {fmt(inc['power'])})"
    t = TIERS[inc["tier"]]
    if lv <= 1:
        return "Unknown ships detected near the system"
    names = ", ".join(SITES[p]["name"] for p in inc["targets"])
    if lv == 2:
        return f"{fname} fleet heading for {names}"
    if lv == 3:
        return f"{t['name']} ({fname}) heading for {names}  (power {fmt(inc['power'])})"
    return f"{t['name']} ({fname}) on {names}  ({incoming_chance(g, inc) * 100:.0f}% to hold)"


def announce(g, inc):
    lv = intel(g)
    if inc["eta"] <= 0 or lv < 1:
        return
    text = describe(g, inc, lv)
    log(g, "WARNING: " + text)
    g.toast(f"WARNING: {text}  -  arrives in {int(inc['eta'])}s", 7)
    if lv >= 2:
        g.flags.add("forewarned")
    g.fx("warning", dict(id=inc["id"], kind=inc["kind"], tier=inc["tier"], text=text, eta=inc["eta"]))


def fortify(g, iid, key=None):
    """Spend credits to harden the target of an incoming attack."""
    inc = next((i for i in g.incoming if i["id"] == iid), None)
    if inc is None or intel(g) < 2:
        return False
    cost = fortify_cost(g, inc)
    if inc["kind"] == "offensive":
        if inc["fort"] or g.credits < cost:
            return False
        inc["fort"] = [inc["target"]]
    else:
        p = key if key is not None else next((q for q in inc["targets"] if q not in inc["fort"]), None)
        if p is None or p in inc["fort"] or g.credits < cost:
            return False
        inc["fort"].append(p)
    g.credits -= cost
    g.flags.add("fortified")
    log(g, f"Fortified {SECTORS[inc['target']]['name'] if inc['kind'] == 'offensive' else SITES[p]['name']}")
    g.recalc()
    return True


# ------------------------------------------------------------------ resolution
def resolve(g, inc):
    if inc["kind"] == "offensive":
        return resolve_offensive(g, inc)
    return resolve_raid(g, inc)


def resolve_raid(g, inc):
    t = TIERS[inc["tier"]]
    fac = inc["fac"]
    wins = 0
    for p in inc["targets"]:
        if not g.unlocked[p]:
            continue
        chance = win_chance(planet_defense(g, p, p in inc["fort"]), inc["power"])
        win = (chance >= 0.5) if g.sim else (random.random() < chance)
        nm = SITES[p]["name"]
        lost = 0.0
        if win:
            wins += 1
            g.raids_repelled += 1
            loot = (g.cred_ops * 40 + 10) * t["loot"]
            g.add_credits(loot)
            g.toast(f"{t['name']} by the {FACTIONS[fac]['name']} on {nm} repelled!  Salvaged {fmt(loot)} credits.", 6)
        else:
            g.raids_lost += 1
            lost = g.ore[p] * t["loss"] * max(0.05, 1 - 0.08 * g.armory[3])
            g.ore[p] -= lost
            g.toast(f"{t['name']} by the {FACTIONS[fac]['name']} hit {nm}!  Lost {fmt(lost)} {SITES[p]['ore']}.", 7)
        log(g, f"{t['name']} on {nm}: {'repelled' if win else 'lost ' + fmt(lost) + ' ' + SITES[p]['ore']}")
        g.fx("raid", dict(p=p, win=win, faction=fac, lost=lost, tier=inc["tier"]))
    if wins and wins == len([p for p in inc["targets"] if g.unlocked[p]]):
        g.tier_wins[inc["tier"]] += 1


def resolve_offensive(g, inc):
    k = inc["target"]
    if k not in g.conquered:
        return
    chance = win_chance(sector_defense(g, k, bool(inc["fort"]), strikes_with(g, inc)), inc["power"])
    held = (chance >= 0.5) if g.sim else (random.random() < chance)
    nm = SECTORS[k]["name"]
    fname = FACTIONS[inc["fac"]]["name"] if inc["fac"] else "The enemy"
    if held:
        g.offensives_repelled += 1
        g.toast(f"{fname} counter-offensive on {nm} repelled!", 7)
        log(g, f"Counter-offensive on {nm}: held")
        g.fx("held", k)
    else:
        g.conquered.discard(k)
        g.lost_sectors.add(k)
        g.sectors_lost += 1
        g.garrison.pop(k, None)
        g.toast(f"SECTOR LOST! {fname} retook {nm}.  Its bonus is gone until you liberate it again.", 9)
        log(g, f"{nm} LOST to the {fname}")
        g.fx("sector_lost", k)
        g.recalc()


def instant_raid(g, p=None, force=None):
    """Developer helper: an immediate small raid on planet p with a chosen outcome."""
    src = weakest_front(g) or (min(g.border(), key=g.sector_power) if g.border() else None)
    if src is None:
        return False
    p = p if p is not None else random.choice([q for q in range(NSITE) if g.unlocked[q]])
    fac = SECTORS[src]["faction"]
    power = 0.12 * g.sector_power(src)
    if force is not None:                       # make the outcome certain
        power = 1e-9 if force else 1e300
    inc = dict(id=next_id(g), kind="raid", tier=0, fac=fac, src=src, targets=[p], t=0.0, eta=0.0, fort=[], power=power)
    resolve_raid_forced(g, inc, force)
    return True


def resolve_raid_forced(g, inc, force):
    old = g.sim
    if force is not None:
        g.sim = True                           # deterministic comparison: chance >= 0.5
    try:
        resolve_raid(g, inc)
    finally:
        g.sim = old


# ------------------------------------------------------------------ main loop
def step(g, dt):
    """Advance incoming attacks and, when it is time, schedule new ones."""
    for inc in list(g.incoming):
        inc["t"] += dt
        if inc["t"] >= inc["eta"]:
            g.incoming.remove(inc)
            resolve(g, inc)
    # hostility cools down slowly
    for fac in list(g.hostility):
        g.hostility[fac] = max(0.0, g.hostility[fac] - dt / 6000.0)
    if g.grace > 0:
        g.grace = max(0.0, g.grace - dt)
        return
    if not g.galaxy_open or not g.border():
        return
    step_war(g, dt)
    if not war_fronts(g):                           # at peace: nothing attacks you
        return
    g.raid_t -= dt
    guard = 0
    while g.raid_t <= 0 and guard < 3:
        guard += 1
        g.raid_t += interval(g, 420.0, 1200.0)
        schedule_raid(g)
    g.offensive_t -= dt * (1.0 + away(g))                              # the more of your fleet is away, the sooner they come
    if g.offensive_t <= 0:
        g.offensive_t = interval(g, 1800.0, 3600.0)
        if len(g.conquered) - 1 >= 2 and aggression(g) >= 0.35:
            schedule_strikes(g)


SECTOR_LINKS_ = core.SECTOR_LINKS
