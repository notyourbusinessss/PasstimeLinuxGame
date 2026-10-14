"""Developer cheats for Space Miner.

These are only reachable when the game is started from a terminal with the --dev flag:

    python3 space_miner.py --dev

Using any cheat marks the save as having cheated (which unlocks a secret achievement).
"""
import core
import director
from core import BMAX, NB, NSH, NSITE, NSEC, ARMORY, STARDUST_PERKS, PERKS, PROJECTS, SC, SITES, TECHS, UPGRADES, ACHIEVEMENTS, fmt

EVENT_NAMES = [("Meteor shower", "meteor"), ("Pirate raid", "pirates"), ("Solar flare", "flare"),
               ("Cosmic lottery", "lottery"), ("Derelict ship", "derelict"), ("Alien trader", "trader"),
               ("Research grant", "grant"), ("Distress signal", "distress"), ("Void whispers", "whisper")]


class DevState:
    def __init__(self):
        self.speed = 1
        self.infinite = False
        self.god = False
        self.fps = False


def tick(app, dt):
    """Called every frame while dev mode is on."""
    g, d = app.g, app.dev_state
    g.dev_mult = 1000.0 if d.god else 1.0
    if d.infinite:
        g.credits = max(g.credits, 1e80)
        g.science = max(g.science, 1e80)
        for p in range(NSITE):
            if g.unlocked[p]:
                g.ore[p] = max(g.ore[p], 1e80)
        g.flags.add("cheated")


def sections(app):
    """[(title, [(label, callback, active)])] for the dev tab. Rebuilt every frame."""
    g, d = app.g, app.dev_state

    def cheat(fn, msg=None):
        def run():
            g.flags.add("cheated")
            fn()
            g.recalc()
            if msg:
                g.toast(msg, 2.5)
        return run

    def here():
        return g.cur

    def unlock(k):
        if not g.unlocked[k]:
            g.unlocked[k] = True
            g.add_ore(k, core.SUPPLY * SC[k])
            g.fx("unlock", k)

    def unlock_next():
        k = next((i for i in range(1, NSITE) if not g.unlocked[i]), None)
        if k is not None:
            unlock(k)
            g.toast(f"{SITES[k]['name']} unlocked (cheat)", 3)

    def unlock_all():
        for k in range(1, NSITE):
            unlock(k)

    def relock_all():
        for k in range(1, NSITE):
            g.unlocked[k] = False
        g.cur = 0
        g.travel = None

    def give_ships(n, all_planets=False):
        for p in (range(NSITE) if all_planets else [here()]):
            if g.unlocked[p]:
                for i in range(NSH):
                    g.owned[p][i] += n

    def clear_ships():
        g.owned[here()] = [0] * NSH

    def all_upgrades(all_planets=False):
        for p in (range(NSITE) if all_planets else [here()]):
            if g.unlocked[p]:
                added = len(UPGRADES) - len(g.ups[p])
                g.ups[p] = {u["id"] for u in UPGRADES}
                g.ups_bought += max(0, added)

    def max_buildings(all_planets=False):
        for p in (range(NSITE) if all_planets else [here()]):
            if g.unlocked[p]:
                for b in range(NB):
                    g.bldg += max(0, BMAX - g.bld[p][b])
                    g.bld[p][b] = BMAX

    def research_all():
        g.techs = {t[0] for t in TECHS}

    def perks_all():
        g.perks = {p[0] for p in PERKS}

    def perks_reset():
        g.perks = set()
        g.dm_spent = 0

    def quests_complete():
        for q in g.quests:
            q["base"] = -1e30
        for _ in range(len(g.quests)):
            g.claim_quest(0)

    def quests_new():
        g.quests = []
        while len(g.quests) < 3:
            g.new_quest()

    def ach_all():
        g.ach = {a["id"] for a in ACHIEVEMENTS}
        g.update_ach_bonus()

    def ach_none():
        g.ach = set()
        g.update_ach_bonus()

    def clear_resources():
        n = NSITE
        g.ore = [0.0] * n
        g.credits = 0.0
        g.science = 0.0

    def fill_all(norm):
        for p in range(NSITE):
            if g.unlocked[p]:
                g.add_ore(p, norm * SC[p])

    def ore_times(k):
        p = here()
        g.ore[p] = max(g.ore[p], SC[p] * 100) * k

    def spawn_crate():
        g.crate = dict(x=-20, y=300, vx=110, ph=0.0, life=0.0)

    def frenzy():
        g.add_buff("Mining Frenzy", 7, 60)

    def force_event(name):
        def run():
            g.event = g.pick_event(force=name)
            g.event["left"] = 90.0
        return run

    def conquer_next():
        fr = g.frontier()
        if fr:
            k = min(fr)
            g.conquered.add(k)
            g.fx("conquer", k)

    def conquer_all():
        for k in range(1, NSEC):
            g.conquered.add(k)

    def reset_galaxy():
        g.conquered = {0}
        g.campaign = None

    def finish_campaign():
        if g.campaign:
            g.campaign["t"] = g.campaign["dur"]

    def sure_win():
        if g.campaign:
            g.campaign["chance"] = 1.0
            g.campaign["fp"] = max(g.campaign["fp"], 1.0)

    def max_armory():
        g.armory = [a[3] for a in ARMORY]

    def add_sd(n):
        def run():
            g.stardust += n
            g.sd_total += n
        return run

    def sd_all():
        g.sd_perks = {p[0] for p in STARDUST_PERKS}
        g.apply_sd_start()

    def sd_reset():
        g.sd_perks = set()
        g.stardust = g.sd_total

    def sched_raid(tier):
        def run():
            if director.schedule_raid(g, tier=tier, lead=8.0) is None:
                g.toast("No enemy territory borders yours yet (liberate / reach Mars first).", 3)
        return run

    def sched_offensive():
        if director.schedule_offensive(g, lead=12.0) is None:
            g.toast("You hold no sector that borders enemy territory.", 3)

    def resolve_incoming():
        for inc in list(g.incoming):
            g.incoming.remove(inc)
            director.resolve(g, inc)

    def lose_sector():
        held = [k for k in g.conquered if k]
        if held:
            k = max(held)
            g.conquered.discard(k)
            g.lost_sectors.add(k)
            g.sectors_lost += 1
            g.fx("sector_lost", k)

    def max_intel():
        g.armory[director.INTEL] = ARMORY[director.INTEL][3]

    def more_hostile():
        for f in core.FACTIONS:
            g.hostility[f] = g.hostility.get(f, 0.0) + 3.0

    def set_speed(k):
        def run():
            d.speed = k
            g.flags.add("cheated")
        return run

    def toggle(attr):
        def run():
            setattr(d, attr, not getattr(d, attr))
            g.flags.add("cheated")
        return run

    def reload_save():
        g.load()
        g.recalc()

    def wipe():
        g.hard_reset()

    p = here()
    nm = SITES[p]["name"]
    ore = SITES[p]["ore"]
    S = [
        ("Time", [
            ("+1 hour of production", cheat(lambda: g.fast_forward(3600), "+1 hour"), False),
            ("+1 day of production", cheat(lambda: g.fast_forward(86400), "+1 day"), False),
            ("+30 days of production", cheat(lambda: g.fast_forward(86400 * 30), "+30 days"), False),
            ("Game speed x1", set_speed(1), d.speed == 1),
            ("Game speed x5", set_speed(5), d.speed == 5),
            ("Game speed x20", set_speed(20), d.speed == 20),
            ("Game speed x100", set_speed(100), d.speed == 100),
        ]),
        ("Resources", [
            (f"{nm}: ore x10", cheat(lambda: ore_times(10)), False),
            (f"{nm}: +1M {ore} (Earth-equiv.)", cheat(lambda: g.add_ore(p, 1e6 * SC[p])), False),
            (f"{nm}: +1T {ore} (Earth-equiv.)", cheat(lambda: g.add_ore(p, 1e12 * SC[p])), False),
            ("ALL planets: +1T ore each", cheat(lambda: fill_all(1e12)), False),
            ("+1 billion credits", cheat(lambda: g.add_credits(1e9)), False),
            ("Credits x1000", cheat(lambda: g.add_credits(max(g.credits, 1e3) * 999)), False),
            ("+1 billion science", cheat(lambda: g.add_sci(1e9)), False),
            ("Science x1000", cheat(lambda: g.add_sci(max(g.science, 1e3) * 999)), False),
            ("+10 Dark Matter", cheat(lambda: setattr(g, "dm", g.dm + 10)), False),
            ("+1,000 Dark Matter", cheat(lambda: setattr(g, "dm", g.dm + 1000)), False),
            ("+1,000,000 Dark Matter", cheat(lambda: setattr(g, "dm", g.dm + 1000000)), False),
            ("Infinite resources", toggle("infinite"), d.infinite),
            ("God mode (production x1000)", toggle("god"), d.god),
            ("Clear all resources", cheat(clear_resources), False),
        ]),
        ("Planets", [
            ("Unlock next planet (free)", cheat(unlock_next), False),
            ("Unlock ALL planets", cheat(unlock_all, "All planets unlocked"), False),
            ("Relock everything but Earth", cheat(relock_all), False),
        ]),
        ("Fleet & upgrades", [
            (f"{nm}: +10 of every ship", cheat(lambda: give_ships(10)), False),
            (f"{nm}: +100 of every ship", cheat(lambda: give_ships(100)), False),
            ("ALL planets: +100 of every ship", cheat(lambda: give_ships(100, True)), False),
            (f"{nm}: remove all ships", cheat(clear_ships), False),
            (f"{nm}: every upgrade (free)", cheat(lambda: all_upgrades()), False),
            ("ALL planets: every upgrade (free)", cheat(lambda: all_upgrades(True)), False),
        ]),
        ("Colonies & megaprojects", [
            (f"{nm}: max all buildings", cheat(lambda: max_buildings()), False),
            ("ALL planets: max all buildings", cheat(lambda: max_buildings(True)), False),
            (f"{nm}: build megaproject", cheat(lambda: g.projects.add(p)), False),
            ("Build ALL megaprojects", cheat(lambda: g.projects.update(range(NSITE))), False),
            ("Remove all megaprojects", cheat(g.projects.clear), False),
        ]),
        ("Tech, perks & quests", [
            ("Research ALL techs", cheat(research_all), False),
            ("Reset techs", cheat(lambda: g.techs.clear()), False),
            ("Grant ALL Dark Matter perks", cheat(perks_all), False),
            ("Reset perks (refund)", cheat(perks_reset), False),
            ("Complete + claim all quests", cheat(quests_complete), False),
            ("Roll new quests", cheat(quests_new), False),
        ]),
        ("Events & crates", [("Event: " + n, cheat(force_event(k)), False) for n, k in EVENT_NAMES] + [
            ("Spawn a supply crate", cheat(spawn_crate), False),
            ("Mining Frenzy x7 (60s)", cheat(frenzy), False),
        ]),
        ("Galaxy & enemies", [
            ("Liberate next sector", cheat(conquer_next), False),
            ("Liberate ALL sectors", cheat(conquer_all), False),
            ("Reset galaxy to Sol only", cheat(reset_galaxy), False),
            ("Finish current campaign now", cheat(finish_campaign), False),
            ("Current campaign: guaranteed win", cheat(sure_win), False),
            ("Max armory", cheat(max_armory), False),
            ("Max Intel (full warnings)", cheat(max_intel), False),
            ("Raid incoming: small (8 s)", cheat(sched_raid(0)), False),
            ("Raid incoming: regional (8 s)", cheat(sched_raid(1)), False),
            ("Raid incoming: system invasion (8 s)", cheat(sched_raid(2)), False),
            ("Counter-offensive incoming (12 s)", cheat(sched_offensive), False),
            ("Resolve all incoming now", cheat(resolve_incoming), False),
            ("Clear all incoming", cheat(lambda: g.incoming.clear()), False),
            ("Lose a sector", cheat(lose_sector), False),
            ("All factions +3 hostility", cheat(more_hostile), False),
            ("Skip the enemy grace period", cheat(lambda: setattr(g, "grace", 0.0)), False),
            ("Enemy raid here (repelled)", cheat(lambda: g.raid(g.cur, force=True)), False),
            ("Enemy raid here (lost)", cheat(lambda: g.raid(g.cur, force=False)), False),
        ]),
        ("Ascension (New Game+)", [
            ("+100 Stardust", cheat(add_sd(100)), False),
            ("+10,000 Stardust", cheat(add_sd(10000)), False),
            ("Ascend now (forced)", cheat(lambda: g.ascend(force=True)), False),
            ("Grant ALL Stardust perks", cheat(sd_all), False),
            ("Reset Stardust perks (refund)", cheat(sd_reset), False),
        ]),
        ("Achievements & warp", [
            ("Unlock ALL achievements", cheat(ach_all), False),
            ("Lock ALL achievements", cheat(ach_none), False),
            ("Force warp now", cheat(lambda: g.do_warp(force=True)), False),
        ]),
        ("Game", [
            ("Save now", lambda: (g.save(), g.toast("Saved", 2)), False),
            ("Reload save from disk", cheat(reload_save, "Reloaded"), False),
            ("Wipe save (hard reset)", wipe, False),
            ("Show FPS counter", toggle("fps"), d.fps),
            ("Test: raise one error (check the log)", lambda: setattr(app, "test_fault", 1), False),
            ("Test: fail every frame (crash report)", lambda: setattr(app, "test_fault", 10 ** 9), False),
        ]),
    ]
    return S
