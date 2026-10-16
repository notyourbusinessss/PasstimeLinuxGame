"""Generals (offence) and wardens (defence): the standing orders that run the war while you do other things.

Pure game logic (no pygame). It works on a core.Game instance `g` and keeps its state on that object, so it is saved with
the game and the balancing bot (sim.py) can run it headless.

Commanders
  * Liberating one of the twelve *command systems* (famous stars) earns you its commander for good: eight **generals**
    for the offence and four **wardens** for the defence. Each has a name and a trait.
  * A general commands an *army* (a share of your whole fleet) and carries **orders** you give once: where to go (a heading
    on the map, toward a place, clear a region, or anywhere) and under what circumstances (minimum odds, which factions it
    may fight, what to prefer, when to stop). It then picks its own targets and launches its own campaigns, offline too.
  * A warden covers one region of the map with a better defence and can retake systems you lose there by itself.

Offence and defence are separate pools of the fleet (see core.Game.defence): armies never defend, the defence pool never
leaves home. The defence pool is shared between the regions where the enemy can reach you, by each region's posture.
"""
import bisect
import math

import galaxy
import core
from core import SECTORS, MIN_SHARE, power_for

GENERAL, WARDEN = "general", "warden"

TRAITS = {   # id: (name, what it does)
    "pathfinder": ("Pathfinder", "Campaigns are 15% faster"),
    "quartermaster": ("Quartermaster", "Loses 30% fewer ships"),
    "tactician": ("Tactician", "Fights as if 15% stronger"),
    "warlord": ("Warlord", "Runs one more campaign at a time"),
    "diplomat": ("Diplomat", "Attacks anger the factions half as much"),
    "bastion": ("Bastion", "Defence of its region x1.3"),
    "bulwark": ("Bulwark", "Defence of its region x1.45"),
    "citadel": ("Citadel", "Defence of its region x1.6"),
    "aegis": ("Aegis", "Defence of its region x1.8"),
}
WARDEN_BONUS = {"bastion": 1.3, "bulwark": 1.45, "citadel": 1.6, "aegis": 1.8}

# (command system, role, name, trait, one line). Roughly by distance: the first general is a neighbour of the Sun.
COMMANDERS = [
    ("Alpha Centauri", GENERAL, "Ada Voss", "pathfinder", "Charts every road out of the solar system"),
    ("Barnard's Star", WARDEN, "Bastion Hale", "bastion", "Holds a line with half the ships"),
    ("Sirius", GENERAL, "Mara Okoye", "quartermaster", "Counts every ship twice before she spends one"),
    ("Epsilon Eridani", WARDEN, "Ines Marlow", "bulwark", "Never gave up a system"),
    ("Tau Ceti", GENERAL, "Ilya Brandt", "tactician", "Wins the fight on the whiteboard first"),
    ("Vega", GENERAL, "Soren Ito", "warlord", "Cannot be told to sit still"),
    ("Arcturus", GENERAL, "Zhen Ma", "diplomat", "Takes the system and leaves the grudge"),
    ("Aldebaran", WARDEN, "Koa Draven", "citadel", "Builds walls out of whatever is nearby"),
    ("Capella", GENERAL, "Tomas Reyes", "pathfinder", "Has never once asked for directions"),
    ("Betelgeuse", GENERAL, "Nia Calder", "tactician", "Takes the supergiants personally"),
    ("Polaris", WARDEN, "Petra Lund", "aegis", "The one fixed point everyone steers by"),
    ("Cygnus X-1", GENERAL, "Yara Quill", "warlord", "Fights where light itself gives up"),
]
GENERAL_IDS = [i for i, c in enumerate(COMMANDERS) if c[1] == GENERAL]
WARDEN_IDS = [i for i, c in enumerate(COMMANDERS) if c[1] == WARDEN]
SYSTEM_OF = [galaxy.BY_NAME[c[0]] for c in COMMANDERS]               # the star that earns each commander
COMMANDER_AT = {k: i for i, k in enumerate(SYSTEM_OF)}

RANKS = [0, 3, 10, 25, 60, 150, 400]                                 # conquests needed for each rank
RANK_NAMES = ["Recruit", "Captain", "Major", "Colonel", "General", "Marshal", "Warlord"]
SLOT_RANKS = (2, 4, 6)                                               # ranks that each add a simultaneous campaign
GEN_PERIOD = 2.0                                                     # seconds between a general's looks at the map
IDLE_WAIT = 20.0                                                     # how long it waits after finding no target

MODES = ["heading", "toward", "region", "any"]
MODE_NAMES = {"heading": "Heading", "toward": "Toward a place", "region": "Clear a region", "any": "Anywhere"}
PREFERS = ["nearest", "weakest", "strongest", "landmark"]
PREFER_NAMES = {"nearest": "Nearest", "weakest": "Weakest", "strongest": "Strongest", "landmark": "Famous places"}
WAR_NAMES = {"declared": "Only factions at war", "any": "May declare war"}
LIMITS = [0, 3, 10, 25, 100]
POSTURES = ["skeleton", "balanced", "fortress"]
POSTURE_W = {"skeleton": 1.0, "balanced": 2.0, "fortress": 3.5}
POSTURE_NAMES = {"skeleton": "Skeleton", "balanced": "Balanced", "fortress": "Fortress"}
REGIONS = sorted({s["region"] for s in galaxy.STARS[1:]})
MARCH = 3.0                                                          # an army's campaign takes this much longer than a strike
STOP_DEFEATS = 2                                                     # a general pauses after this many defeats in a row
WARDEN_RETAKE = 0.3                                                  # share of the defence pool a warden may send to retake
ARMY_DEFAULT = 0.10
LANDMARKS = set(galaxy.LANDMARK_IDS)
COMPASS = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"]
COLOURS = [(255, 170, 120), (255, 215, 110), (150, 230, 150), (130, 200, 255), (220, 150, 255), (255, 140, 170), (150, 255, 230),
           (255, 255, 160)]


def colour(idx):
    """The colour of a general's orders on the map."""
    return COLOURS[GENERAL_IDS.index(idx) % len(COLOURS)] if idx in GENERAL_IDS else (140, 200, 255)


# ------------------------------------------------------------------ the commanders
def key(idx):
    """The tag a commander's campaigns carry (campaign["by"])."""
    return ("g" if COMMANDERS[idx][1] == GENERAL else "w") + str(idx)


def index_of(by):
    return int(by[1:])


def new_state(idx):
    if COMMANDERS[idx][1] == GENERAL:
        return dict(on=True, army=ARMY_DEFAULT, mode="any", angle=0.0, goal=None, region=None, odds=0.85, war="declared",
                    prefer="nearest", limit=0, run=0, took=0, lost=0, streak=0, paused=False, idle=0.0, status="")
    return dict(on=True, region=None, retake=True, held=0, retaken=0, idle=0.0, status="")


def clean_state(idx, raw, sec):
    """A commander's state from a save, with every field checked."""
    st = new_state(idx)
    try:
        st["on"] = bool(raw.get("on", True))
        if COMMANDERS[idx][1] == GENERAL:
            st["army"] = max(0.0, min(1.0, float(raw.get("army", ARMY_DEFAULT))))
            st["mode"] = raw["mode"] if raw.get("mode") in MODES else "any"
            st["angle"] = float(raw.get("angle", 0.0)) % math.tau
            goal = raw.get("goal")
            st["goal"] = sec(goal) if goal is not None and sec(goal) > 0 else None
            st["region"] = raw["region"] if raw.get("region") in REGIONS else None
            st["odds"] = max(0.5, min(0.99, float(raw.get("odds", 0.85))))
            st["war"] = raw["war"] if raw.get("war") in WAR_NAMES else "declared"
            st["prefer"] = raw["prefer"] if raw.get("prefer") in PREFERS else "nearest"
            st["limit"] = int(raw["limit"]) if raw.get("limit") in LIMITS else 0
            for f in ("run", "took", "lost", "streak"):
                st[f] = max(0, int(raw.get(f, 0)))
            st["paused"] = bool(raw.get("paused", False))
        else:
            st["region"] = raw["region"] if raw.get("region") in REGIONS else None
            st["retake"] = bool(raw.get("retake", True))
            st["held"] = max(0, int(raw.get("held", 0)))
            st["retaken"] = max(0, int(raw.get("retaken", 0)))
    except (TypeError, ValueError, AttributeError):
        return new_state(idx)
    return st


def trait(idx):
    return COMMANDERS[idx][3]


def rank(st):
    return bisect.bisect_right(RANKS, st.get("took", 0)) - 1


def slots(idx, st):
    r = rank(st)
    return 1 + (trait(idx) == "warlord") + sum(1 for q in SLOT_RANKS if r >= q)


def power_mult(idx, st):
    return (1.15 if trait(idx) == "tactician" else 1.0) * (1 + 0.03 * rank(st))


def ensure(g):
    """Create the commander of every command system you hold (once: they stay for good). Returns the new ones."""
    new = []
    for k, idx in COMMANDER_AT.items():
        if k in g.conquered and idx not in g.cmd:
            st = g.cmd[idx] = new_state(idx)
            if COMMANDERS[idx][1] == GENERAL:
                st["army"] = max(0.02, min(ARMY_DEFAULT, g.manual_cap()))
            else:
                st["region"] = SECTORS[k]["region"]
            new.append(idx)
            sysname, role, name, tr, _ = COMMANDERS[idx]
            core.log.info("Commander joins: %s (%s) from %s", name, role, sysname)
            g.toast(f"{role.upper()} {name} joins you from {sysname}!  ({TRAITS[tr][0]}: {TRAITS[tr][1]})", 8)
    return new


def commanders(g, role=None):
    """[(idx, state)] of the commanders you have, in order."""
    return [(i, g.cmd[i]) for i in sorted(g.cmd) if role is None or COMMANDERS[i][1] == role]


def army_total(g):
    return sum(st["army"] for i, st in g.cmd.items() if COMMANDERS[i][1] == GENERAL and st["on"])


def set_defence(g, x):
    """The share of the fleet that guards your territory; the armies shrink if they no longer fit beside it."""
    g.defence = max(0.0, min(core.DEFENCE_MAX, round(x, 2)))
    over = army_total(g) - (1.0 - g.defence)
    if over > 1e-9:
        tot = army_total(g)
        for i, st in g.cmd.items():
            if COMMANDERS[i][1] == GENERAL and st["on"]:
                st["army"] = round(st["army"] * (1.0 - g.defence) / tot, 3)


def set_army(g, idx, x):
    """An army's share of the fleet, never more than is left after the defence and the other armies."""
    st = g.cmd[idx]
    others = army_total(g) - (st["army"] if st["on"] else 0.0)
    st["army"] = round(max(0.0, min(x, 1.0 - g.defence - others)), 3)


# ------------------------------------------------------------------ orders
def compass(angle):
    return COMPASS[int(round(angle / (math.pi / 4))) % 8]


def heading_from(g, k):
    """The direction (radians, map coordinates) from the middle of your territory to system k."""
    cx, cy = _centre(g)
    return math.atan2(galaxy.YS[k] - cy, galaxy.XS[k] - cx)


def _centre(g):
    key_ = (len(g.conquered), sum(g.conquered))
    if getattr(g, "_gen_centre_key", None) != key_:
        n = len(g.conquered)
        g._gen_centre = (sum(galaxy.XS[k] for k in g.conquered) / n, sum(galaxy.YS[k] for k in g.conquered) / n)
        g._gen_centre_key = key_
    return g._gen_centre


def tip(g, angle):
    """The system of yours furthest along a heading: where an arrow in that direction starts."""
    key_ = (len(g.conquered), sum(g.conquered), round(angle, 2))
    cache = g.__dict__.setdefault("_gen_tip", {})
    if key_ not in cache:
        ca, sa = math.cos(angle), math.sin(angle)
        cache.clear()
        cache[key_] = max(g.conquered, key=lambda k: galaxy.XS[k] * ca + galaxy.YS[k] * sa)
    return cache[key_]


def describe_orders(st):
    m = st["mode"]
    if m == "heading":
        return f"Heading {compass(st['angle'])}"
    if m == "toward":
        return "Toward " + (SECTORS[st["goal"]]["name"] if st["goal"] is not None else "(pick a place)")
    if m == "region":
        return "Clear " + (st["region"] or "(pick a region)")
    return "Anywhere in reach"


def _index(g):
    """The reachable systems sorted by strength and by distance (rebuilt when your reach changes): choosing a target walks these
    lists and stops at the first match, so a look at the map is cheap even with thousands of systems in range."""
    tl = g.targets()
    cache = g.__dict__.get("_gen_index")
    if cache is None or cache["key"] != g._targets_key:
        by_lp = sorted(tl, key=lambda k: SECTORS[k]["lp"])
        cache = g._gen_index = dict(key=g._targets_key, by_lp=by_lp, lps=[SECTORS[k]["lp"] for k in by_lp],
                                    by_d=sorted(tl, key=lambda k: g.source_of(k)[1]), goals={})
    return cache


def _order(g, st, cache, lp_limit):
    """The candidates in the order the general prefers them, never stronger than it can beat."""
    mode, pref = st["mode"], st["prefer"]
    if mode == "toward":
        goal = st["goal"]
        lst = cache["goals"].get(goal)
        if lst is None:
            if len(cache["goals"]) > 8:
                cache["goals"].clear()
            lst = cache["goals"][goal] = sorted(cache["by_d"], key=lambda k: galaxy.dist(k, goal))
        return (k for k in lst if SECTORS[k]["lp"] <= lp_limit)
    if pref == "weakest":
        n = bisect.bisect_right(cache["lps"], lp_limit)
        return iter(cache["by_lp"][:n])
    if pref == "strongest":
        n = bisect.bisect_right(cache["lps"], lp_limit)
        return reversed(cache["by_lp"][:n])
    if pref == "landmark":
        d = [k for k in cache["by_d"] if SECTORS[k]["lp"] <= lp_limit]
        return iter([k for k in d if k in LANDMARKS] + [k for k in d if k not in LANDMARKS])
    return (k for k in cache["by_d"] if SECTORS[k]["lp"] <= lp_limit)


def _fits(g, st, k, cone, ca, sa):
    """Does system k suit the orders (region, heading, toward a place)?"""
    mode = st["mode"]
    if mode == "region":
        return SECTORS[k]["region"] == st["region"]
    if mode == "heading":
        src = g.source_of(k)[0]
        dx, dy = galaxy.XS[k] - galaxy.XS[src], galaxy.YS[k] - galaxy.YS[src]
        return (dx * ca + dy * sa) >= cone * (math.hypot(dx, dy) or 1.0)
    if mode == "toward":
        goal = st["goal"]
        return galaxy.dist(k, goal) < galaxy.dist(g.source_of(k)[0], goal)
    return True


def choose(g, idx, st):
    """The system this general would attack next under its orders, or None (st["status"] says why not)."""
    by = key(idx)
    fp = g.fleet_power()
    free = g.free_share(by)
    pm = power_mult(idx, st)
    if fp <= 0 or free < MIN_SHARE:
        st["status"] = "No army free"
        return None
    if st["limit"] and st["run"] >= st["limit"]:
        st["status"] = "Limit reached"
        return None
    mode = st["mode"]
    if mode == "toward" and st["goal"] is not None and st["goal"] in g.conquered:
        st["status"] = "Goal reached"
        return None
    if (mode == "toward" and st["goal"] is None) or (mode == "region" and st["region"] is None):
        st["status"] = "Pick where to go"
        return None
    limit = fp * pm * free / (power_for(1.0, st["odds"]) or 1.0)          # the strongest enemy this army beats with these odds
    lp_limit = math.log10(limit) - core.TUNE["sshift"] - (g.cycle - 1) * math.log10(core.TUNE["cpow"])
    cache = _index(g)
    busy = {c["k"] for c in g.campaigns}
    war = g.war
    declared = st["war"] == "declared"
    cone = math.cos(math.radians(75))
    ca, sa = math.cos(st["angle"]), math.sin(st["angle"])
    for k in _order(g, st, cache, lp_limit):
        if k in busy or (declared and SECTORS[k]["faction"] not in war):
            continue
        if _fits(g, st, k, cone, ca, sa):
            return k
    # nothing: say why (a slower look, only when the general is idle anyway)
    fitting = any(k not in busy and not (declared and SECTORS[k]["faction"] not in war) and _fits(g, st, k, cone, ca, sa)
                  for k in cache["by_lp"])
    if fitting:
        st["status"] = "Targets are too strong for this army"
    elif mode == "region" and not any(SECTORS[k]["region"] == st["region"] and k not in g.conquered for k in range(1, len(SECTORS))):
        st["status"] = "Region cleared"
    elif mode == "heading":
        st["status"] = "Nothing to attack that way"
    elif mode == "toward":
        st["status"] = "No step toward the goal in reach"
    else:
        st["status"] = "Nothing to attack"
    return None


def launch(g, idx, st, k):
    """Send the general's next campaign. Returns True if it left."""
    tr = trait(idx)
    by = key(idx)
    pm = power_mult(idx, st)
    ok = g.start_campaign(k, mode=0, odds=st["odds"], by=by, pmult=pm,
                          dur_mult=MARCH * (0.85 if tr == "pathfinder" else 1.0),
                          loss_mult=0.7 if tr == "quartermaster" else 1.0,
                          hostile=0.5 if tr == "diplomat" else 1.0)
    if ok:
        st["status"] = "Campaign under way"
    return ok


def step(g, dt):
    """Every commander looks at the map now and then and acts on its orders. One general looks per call (the others wait for the
    next frame), so a look at the map never makes the game stutter."""
    scans = 0
    for idx, st in list(g.cmd.items()):
        st["idle"] = st.get("idle", 0.0) - dt
        if st["idle"] > 0 or not st["on"]:
            continue
        if COMMANDERS[idx][1] == WARDEN:
            st["idle"] = GEN_PERIOD
            _warden_step(g, idx, st)
            continue
        if st["paused"]:
            st["idle"] = GEN_PERIOD
            st["status"] = "Paused after defeats"
            continue
        by = key(idx)
        if sum(1 for c in g.campaigns if c.get("by") == by) >= slots(idx, st):
            st["idle"] = GEN_PERIOD
            st["status"] = "Campaigns under way"
            continue
        if scans:
            continue
        scans += 1
        st["idle"] = GEN_PERIOD
        k = choose(g, idx, st)
        if k is None:
            st["idle"] = IDLE_WAIT
        else:
            launch(g, idx, st, k)


def _warden_step(g, idx, st):
    """A warden with the retake order sends part of the defence pool to take back a system lost in its region."""
    if not st["retake"] or st["region"] is None:
        st["status"] = "Holding its region"
        return
    by = key(idx)
    if any(c.get("by") == by for c in g.campaigns):
        st["status"] = "Retaking a system"
        return
    tset = g.targets_set()
    busy = {c["k"] for c in g.campaigns}
    lost = [k for k in g.lost_sectors if k in tset and k not in busy and SECTORS[k]["region"] == st["region"]
            and SECTORS[k]["faction"] in g.war]
    if not lost:
        st["status"] = "Holding its region"
        st["idle"] = IDLE_WAIT
        return
    k = min(lost, key=lambda q: SECTORS[q]["lp"])
    if g.start_campaign(k, mode=0, odds=0.9, by=by):
        st["status"] = "Retaking " + SECTORS[k]["name"]
    else:
        st["status"] = "Cannot retake yet"
        st["idle"] = IDLE_WAIT


def on_result(g, c, won):
    """A commander's campaign ended."""
    by = c.get("by")
    if not by or index_of(by) not in g.cmd:
        return
    idx = index_of(by)
    st = g.cmd[idx]
    name = COMMANDERS[idx][2]
    if COMMANDERS[idx][1] == WARDEN:
        if won:
            st["retaken"] = st.get("retaken", 0) + 1
        return
    st["idle"] = 0.0
    if won:
        before = rank(st)
        st["took"] += 1
        st["run"] += 1
        st["streak"] = 0
        if rank(st) > before:
            g.toast(f"General {name} is promoted to {RANK_NAMES[rank(st)]}!", 6)
    else:
        st["lost"] += 1
        st["streak"] += 1
        if st["streak"] >= STOP_DEFEATS:
            st["paused"] = True
            g.toast(f"General {name} pauses after {st['streak']} defeats in a row - new orders?", 7)


# ------------------------------------------------------------------ defence
def region_of(k):
    return SECTORS[k]["region"]


def exposed_counts(g):
    """{region: how many of your systems the enemy at war with you can reach there} (cached)."""
    key_ = (len(g.conquered), sum(g.conquered), tuple(sorted(g.war)))
    if getattr(g, "_gen_exp_key", None) != key_:
        counts = {}
        for k in core.director.exposed_systems(g):
            r = region_of(k)
            counts[r] = counts.get(r, 0) + 1
        g._gen_exp, g._gen_exp_key = counts, key_
    return g._gen_exp


def exposed_regions(g):
    """The regions where the enemy at war with you touches your territory."""
    return set(exposed_counts(g))


def warden_mult(g, region):
    best = 1.0
    for idx, st in g.cmd.items():
        if COMMANDERS[idx][1] == WARDEN and st["on"] and st["region"] == region:
            best = max(best, WARDEN_BONUS[trait(idx)])
    return best


def defence_pool(g):
    """Fleet power of the defence pool (what is not out retaking systems)."""
    used = sum(c["share"] for c in g.campaigns if str(c.get("by", "")).startswith("w"))
    return g.fleet_power() * max(0.0, g.defence - used)


def defence_map(g, extra=()):
    """{region: defending fleet power}: the pool shared between the exposed regions by their postures, times the wardens."""
    regs = set(exposed_regions(g)) | set(extra)
    if not regs:
        return {}
    pool = defence_pool(g)
    w = {r: POSTURE_W[g.posture.get(r, "balanced")] for r in regs}
    tot = sum(w.values())
    return {r: pool * w[r] / tot * warden_mult(g, r) for r in regs}


def defence_power(g, k, strikes=1, dmap=None):
    """The fleet that defends system k when attacked, shared with the other attacks on its region at the same time."""
    r = region_of(k)
    if dmap is None or r not in dmap:
        dmap = defence_map(g, (r,))
    return dmap[r] / max(1, strikes)


# ------------------------------------------------------------------ editing orders (the interface calls these)
ODDS_STEPS = [0.70, 0.80, 0.85, 0.90, 0.95]


def set_orders(st, **fields):
    """Change a general's orders; it starts afresh (no stop-count, no pause, looks at the map at once)."""
    st.update(fields)
    st["run"] = 0
    st["paused"] = False
    st["idle"] = 0.0


def _next(options, value):
    return options[(options.index(value) + 1) % len(options)] if value in options else options[0]


def cycle_odds(st):
    nxt = next((o for o in ODDS_STEPS if o > st["odds"] + 1e-9), ODDS_STEPS[0])
    set_orders(st, odds=nxt)


def cycle_prefer(st):
    set_orders(st, prefer=_next(PREFERS, st["prefer"]))


def cycle_war(st):
    set_orders(st, war="any" if st["war"] == "declared" else "declared")


def cycle_limit(st):
    set_orders(st, limit=_next(LIMITS, st["limit"]))


def resume(st):
    set_orders(st)


def held_regions(g):
    """The regions of the map where you hold at least one system, with how many (cached)."""
    key_ = (len(g.conquered), sum(g.conquered))
    if getattr(g, "_gen_held_key", None) != key_:
        out = {}
        for k in g.conquered:
            if k:
                out[region_of(k)] = out.get(region_of(k), 0) + 1
        g._gen_held, g._gen_held_key = out, key_
    return g._gen_held


def cycle_region(g, st):
    """A warden's region: the next of the regions you hold."""
    held = sorted(held_regions(g)) or [st["region"]]
    st["region"] = _next(held, st["region"]) if st["region"] in held else held[0]
