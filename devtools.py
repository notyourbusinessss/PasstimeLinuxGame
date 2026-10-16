"""Developer cheats for Space Miner.

These are only reachable when the game is started from a terminal with the --dev flag:

    python3 space_miner.py --dev

Using any cheat marks the save as having cheated (which unlocks a secret achievement).
"""
import blackhole
import core
import director
import generals
from core import BMAX, NB, NSH, NSOL, NSEC, ARMORY, STARDUST_PERKS, PERKS, PROJECTS, SITES, TECHS, UPGRADES, ACHIEVEMENTS, fmt

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
        for p in range(g.nsite):
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
            g.add_ore(k, core.SUPPLY * g.sc[k])
            g.fx("unlock", k)

    def unlock_next():
        k = next((i for i in range(1, NSOL) if not g.unlocked[i]), None)
        if k is not None:
            unlock(k)
            g.toast(f"{SITES[k]['name']} unlocked (cheat)", 3)

    def unlock_all():
        for k in range(1, NSOL):
            unlock(k)

    def settle_all():
        """Settle the worlds of the nearest stars you hold (200 of them), for free."""
        for k, i in g.world_options()[:200]:
            g.credits += 1e300
            g.settle(k, i)

    def relock_all():
        g.set_sites([])
        n = NSOL
        g.ore, g.run_ore, g.all_ore = g.ore[:n], g.run_ore[:n], g.all_ore[:n]
        g.owned, g.ups, g.bld = g.owned[:n], g.ups[:n], g.bld[:n]
        g.unlocked = [True] + [False] * (n - 1)
        g.cur = 0
        g.travel = None

    def give_ships(n, all_planets=False):
        for p in (range(g.nsite) if all_planets else [here()]):
            if g.unlocked[p]:
                for i in range(NSH):
                    g.owned[p][i] += n

    def clear_ships():
        g.owned[here()] = [0] * NSH

    def all_upgrades(all_planets=False):
        for p in (range(g.nsite) if all_planets else [here()]):
            if g.unlocked[p]:
                added = len(UPGRADES) - len(g.ups[p])
                g.ups[p] = {u["id"] for u in UPGRADES}
                g.ups_bought += max(0, added)

    def max_buildings(all_planets=False):
        for p in (range(g.nsite) if all_planets else [here()]):
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
        n = g.nsite
        g.ore = [0.0] * n
        g.credits = 0.0
        g.science = 0.0

    def fill_all(norm):
        for p in range(g.nsite):
            if g.unlocked[p]:
                g.add_ore(p, norm * g.sc[p])

    def ore_times(k):
        p = here()
        g.ore[p] = max(g.ore[p], g.sc[p] * 100) * k

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
        fr = g.targets()
        if fr:
            k = min(fr, key=lambda q: core.SECTORS[q]["lp"])
            g.conquered.add(k)
            g.fx("conquer", k)

    def conquer_n(n):
        def run():
            for _ in range(n):
                fr = g.targets()
                if not fr:
                    break
                g.conquered.add(min(fr, key=lambda q: core.SECTORS[q]["lp"]))
        return run

    def conquer_all():
        for k in range(1, NSEC):
            g.conquered.add(k)

    def conquer_boss():
        g.conquered.add(core.BOSS)

    def max_jump():
        g.armory[core.JUMP] = ARMORY[core.JUMP][3]

    def max_command():
        g.armory[core.COMMAND] = ARMORY[core.COMMAND][3]

    def earn_commanders():
        g.conquered.update(generals.SYSTEM_OF)
        generals.ensure(g)

    def promote_generals():
        for idx, st in g.cmd.items():
            if generals.COMMANDERS[idx][1] == generals.GENERAL:
                st["took"] = max(st["took"], generals.RANKS[-1])

    def resume_generals():
        for st in g.cmd.values():
            if "paused" in st:
                generals.resume(st)

    def reset_galaxy():
        g.conquered = {0}
        g.campaigns = []

    def finish_campaign():
        for c in g.campaigns:
            c["t"] = c["dur"]

    def sure_win():
        for c in g.campaigns:
            c["chance"] = 1.0
            c["fp"] = max(c["fp"], 1.0)

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

    def force_war():
        """The attack cheats need a faction at war: start one (without its opening strike) if nobody is."""
        if not director.war_fronts(g) and g.border():
            f = core.SECTORS[min(g.border())]["faction"]
            g.war[f] = dict(since=g.play_time, by="enemy")

    def war_all():
        for f in core.FACTIONS:
            if f not in g.war:
                director.declare_war(g, f, "player")

    def peace_all():
        for f in list(g.war):
            g.war.pop(f, None)
            g.truce[f] = director.TRUCE_TIME
        g.incoming.clear()

    def max_tension():
        for f in core.FACTIONS:
            if f not in g.war and director.borders(g, f):
                g.tension[f] = 0.97
        g.grace = 0.0

    def sched_raid(tier):
        def run():
            force_war()
            if director.schedule_raid(g, tier=tier, lead=8.0) is None:
                g.toast("No enemy territory borders yours yet (liberate / reach Mars first).", 3)
        return run

    def sched_offensive():
        force_war()
        if director.schedule_offensive(g, lead=12.0) is None:
            g.toast("You hold no sector that borders enemy territory.", 3)

    def resolve_incoming():
        for inc in list(g.incoming):
            g.incoming.remove(inc)
            director.resolve(g, inc)

    def lose_sector():
        held = [k for k in g.conquered if k]
        if held:
            k = max(held, key=lambda q: core.SECTORS[q]["lp"])
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
    nm = g.sites[p]["name"]
    ore = g.sites[p]["ore"]
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
            (f"{nm}: +1M {ore} (Earth-equiv.)", cheat(lambda: g.add_ore(p, 1e6 * g.sc[p])), False),
            (f"{nm}: +1T {ore} (Earth-equiv.)", cheat(lambda: g.add_ore(p, 1e12 * g.sc[p])), False),
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
            ("Unlock ALL solar planets", cheat(unlock_all, "All solar planets unlocked"), False),
            ("Settle the worlds of every star you hold (free)", cheat(settle_all, "Worlds settled"), False),
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
            ("Build ALL megaprojects", cheat(lambda: g.projects.update(range(NSOL))), False),
            ("Remove all megaprojects", cheat(g.projects.clear), False),
            ("Black Hole Bomb: build every stage", cheat(lambda: setattr(g, "bomb", blackhole.N)), False),
            ("Black Hole Bomb: take it apart", cheat(lambda: setattr(g, "bomb", 0)), False),
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
            ("Liberate the weakest reachable system", cheat(conquer_next), False),
            ("Liberate 25 systems in reach", cheat(conquer_n(25)), False),
            ("Liberate 250 systems in reach", cheat(conquer_n(250)), False),
            ("Liberate ALL systems", cheat(conquer_all), False),
            ("Liberate The Void Throne (can Ascend)", cheat(conquer_boss), False),
            ("Max Jump Drive", cheat(max_jump), False),
            ("Max Command (8 manual campaigns)", cheat(max_command), False),
            ("Earn every general and warden", cheat(earn_commanders), False),
            ("Promote every general to Warlord", cheat(promote_generals), False),
            ("Resume paused generals", cheat(resume_generals), False),
            ("Reset galaxy to Sol only", cheat(reset_galaxy), False),
            ("Finish all running campaigns now", cheat(finish_campaign), False),
            ("Running campaigns: guaranteed win", cheat(sure_win), False),
            ("Max armory", cheat(max_armory), False),
            ("Max Intel (full warnings)", cheat(max_intel), False),
            ("Raid incoming: small (8 s)", cheat(sched_raid(0)), False),
            ("Raid incoming: regional (8 s)", cheat(sched_raid(1)), False),
            ("Raid incoming: system invasion (8 s)", cheat(sched_raid(2)), False),
            ("Counter-offensive incoming (12 s)", cheat(sched_offensive), False),
            ("Resolve all incoming now", cheat(resolve_incoming), False),
            ("Clear all incoming", cheat(lambda: g.incoming.clear()), False),
            ("Lose a sector", cheat(lose_sector), False),
            ("Declare war on every faction", cheat(war_all), False),
            ("Make peace with everyone (truce)", cheat(peace_all), False),
            ("Max tension: a border faction invades soon", cheat(max_tension), False),
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
