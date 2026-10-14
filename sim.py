#!/usr/bin/env python3
"""Headless balancing bot:  python3 sim.py [hours] [check_interval_seconds]
Plays Space Miner with a reasonable greedy strategy and prints a pacing timeline."""
import math
import random
import sys

import core
from core import (BUILDINGS, NB, NSH, NSITE, SC, SHIPS, SITES, TECHS, PERKS, GROWTH, geo_max, fmt)


def site_mult(g, p):
    sm = 1.0
    for uid in g.ups[p]:
        u = core.UPG_BY_ID[uid]
        if u["kind"] == "global":
            sm *= u["arg"]
    return sm


def options(g, p):
    """(payback_seconds, cost, kind, arg) for ships / upgrades / mining complex at site p."""
    out = []
    mine = 1 + g.s_mine[p] * g.E["minebonus"]
    k = mine * g.G * site_mult(g, p)
    for i in range(NSH):
        d = SHIPS[i][2] * SC[p] * g.s_gm[p][i] * k
        c = g.ship_cost1(p, i)
        out.append((c / d, c, "ship", i))
    for u in g.avail_upgrades(p):
        c = u["cost"] * SC[p]
        if u["kind"] == "gen":
            i, m = u["arg"]
            d = g.owned[p][i] * SHIPS[i][2] * SC[p] * g.s_gm[p][i] * (m - 1) * k
        elif u["kind"] == "global":
            d = g.s_ops[p] * (u["arg"] - 1) / u["arg"] * 1.0
        else:
            continue
        if d > 0:
            out.append((c / d, c, "up", u["id"]))
    # mining complex
    L = g.bld[p][0]
    if L < core.BMAX:
        bonus = SITES[p]["bonus"]
        f = 2.0 if bonus == 0 else (1.5 if bonus == -1 else 1.0)
        c = g.bld_cost1(p, 0, L)
        d = 0.03 * f * g.E["minebonus"] * g.s_base[p] * g.G * site_mult(g, p)
        if d > 0:
            out.append((c / d, c, "mine", 0))
    return out


def next_locked(g):
    return next((k for k in range(1, NSITE) if not g.unlocked[k]), None)


def reserves(g):
    res = [0.0] * NSITE
    cres = 0.0
    k = next_locked(g)
    if k is None:
        return res, cres
    ores, cr = g.unlock_cost(k)
    for p, amt in ores:
        if amt > 0 and g.ore[p] + g.s_ops[p] * 1800 >= amt:
            res[p] = amt
    if cr > 0 and g.credits + g.cred_ops * 1800 >= cr:
        cres = cr
    return res, cres


WARP_FRAC = 1.0
BOT_CHANCE = 0.85


class Bot:
    def __init__(self, g, click_rate=4.0, active_after=300.0):
        self.g = g
        self.click_rate = click_rate
        self.active_after = active_after
        self.click_until = active_after
        self.click_site = 0
        self.last_warp = 0.0
        self.log = []
        self.seen_conq = 1
        self.conq_logged = {0}

    def galaxy(self):
        g = self.g
        if not g.galaxy_open:
            return
        # armory: weapons / engines / armor when they cost a small slice of credits and science
        for i in sorted(range(len(core.ARMORY)), key=lambda i: core.armory_cost(i, g.armory[i])[0]):
            if i == 3 or g.armory[i] >= core.ARMORY[i][3]:
                continue
            cr, sci = core.armory_cost(i, g.armory[i])
            res, cres = reserves(g)
            if cr <= 0.3 * max(0.0, g.credits - cres) and sci <= 0.3 * g.science:
                g.buy_armory(i)
        if g.campaign is None:
            options = [k for k in g.frontier()
                       if core.win_chance(g.fleet_power(), g.sector_power(k)) >= BOT_CHANCE]
            if options:
                g.start_campaign(min(options))
        while self.seen_conq < len(g.conquered):
            self.seen_conq += 1
        new = sorted(g.conquered - self.conq_logged)
        for k in new:
            self.log.append((g.t, f"conquer {core.SECTORS[k]['name']}"))
        self.conq_logged |= set(new)

    def ascend(self):
        g = self.g
        if g.can_ascend():
            gain, old = g.sd_gain(), g.cycle
            g.ascend()
            self.log.append((g.t, f"ASCEND to cycle {g.cycle} (+{gain} Stardust, {g.sd_total} total)"))
            self.last_warp = g.t
            self.click_until = g.t + self.active_after
            self.click_site = 0
            self.conq_logged = set(g.conquered)
        for pk in sorted(core.STARDUST_PERKS, key=lambda p: p[2]):
            g.buy_sd_perk(pk[0])

    def click(self, dt):
        g = self.g
        if g.t < self.click_until:
            p = self.click_site
            if g.unlocked[p]:
                g.add_ore(p, g.s_click[p] * self.click_rate * dt)

    def decide(self):
        g = self.g
        for _ in range(400):
            changed = False
            k = next_locked(g)
            if k is not None and g.can_unlock(k):
                g.unlock_planet(k)
                self.log.append((g.t, f"unlock {SITES[k]['name']}"))
                self.click_until = g.t + self.active_after
                self.click_site = k
                changed = True
            for t in sorted(TECHS, key=lambda t: t[2]):
                if g.research(t[0]):
                    changed = True
            for p in sorted(PERKS, key=lambda p: p[2]):
                if g.buy_perk(p[0]):
                    changed = True
            for p in range(NSITE):
                if g.unlocked[p] and g.can_buy_project(p) and g.buy_project(p):
                    self.log.append((g.t, f"project {core.PROJECTS[p][0]}"))
                    changed = True
            res, cres = reserves(g)
            for p in range(NSITE):
                if not g.unlocked[p]:
                    continue
                spare = g.ore[p] - res[p]
                # Habitat / Lab: affordable slice of stock
                for b in (1, 2):
                    L = g.bld[p][b]
                    if L < core.BMAX and g.bld_cost1(p, b, L) <= (spare if L < 3 else 0.3 * spare):
                        g.buy_mode = 1
                        if g.buy_building(p, b):
                            changed = True
                            spare = g.ore[p] - res[p]
                for b in (3, 4):
                    L = g.bld[p][b]
                    if L < core.BMAX and g.bld_cost1(p, b, L) <= 0.5 * max(0.0, g.credits - cres):
                        g.buy_mode = 1
                        if g.buy_building(p, b):
                            changed = True
                # best payback ship / upgrade
                opts = [o for o in options(g, p) if o[1] <= spare and o[0] < 4 * 3600]
                if opts:
                    pb, c, kind, arg = min(opts)
                    if kind == "ship":
                        n_aff = geo_max(g.ship_cost1(p, arg), GROWTH, spare)
                        g.buy_mode = max(1, min(n_aff // 3, 25))
                        g.buy_ship(p, arg)
                    elif kind == "up":
                        g.buy_upgrade(p, arg)
                    else:
                        g.buy_mode = 1
                        g.buy_building(p, 0)
                    changed = True
            if not changed:
                break
        g.buy_mode = 1
        self.galaxy()
        self.ascend()
        # warp policy
        gain = g.warp_gain()
        if gain >= max(1, int(WARP_FRAC * g.dm)) and g.t - self.last_warp > 2700:
            g.do_warp()
            self.log.append((g.t, f"WARP +{gain} DM (total {g.dm})"))
            self.last_warp = g.t
            self.click_until = g.t + self.active_after
            self.click_site = 0


def fmt_t(s):
    h = s / 3600
    return f"{h:6.2f}h" if h >= 1 else f"{s / 60:5.1f}m "


def main():
    kw = dict(a.split("=") for a in sys.argv[1:] if "=" in a)
    hours = float(kw.pop("hours", 100))
    interval = float(kw.pop("interval", 60))
    quiet = kw.pop("quiet", "0") == "1"
    warp_frac = float(kw.pop("warp_frac", 1.0))
    global BOT_CHANCE
    BOT_CHANCE = float(kw.pop("bot_chance", 0.85))
    core.apply_tune(**{k: float(v) for k, v in kw.items()})
    global WARP_FRAC
    WARP_FRAC = warp_frac
    random.seed(1)
    g = core.Game(load=False, sim=True)
    bot = Bot(g)
    t_end = hours * 3600
    next_report = 3600 * 2
    seen = 0
    while g.t < t_end:
        dt = interval if g.t > 1800 else min(interval, 15)
        bot.click(dt)
        g.step(dt)
        bot.decide()
        while seen < len(bot.log):
            t, msg = bot.log[seen]
            if not quiet:
                print(f"  [{fmt_t(t)}] {msg}")
            elif msg.startswith(("unlock", "project", "conquer", "ASCEND")):
                print(f"  [{fmt_t(t)}] {msg}")
            seen += 1
        if g.t >= next_report and not quiet:
            next_report += 3600 * 4
            print(f"{fmt_t(g.t)} planets={g.n_unlocked:2d} techs={len(g.techs):2d} DM={g.dm:<7d} warps={g.warps:<3d} "
                  f"ops(norm)={fmt(g.norm_ops):>8} cred/s={fmt(g.cred_ops):>8} sci/s={fmt(g.sci_ops):>8} "
                  f"G={fmt(g.G)} ships={g.total_ships()} FP={fmt(g.fleet_power())} sectors={len(g.conquered) - 1}")
        if g.n_unlocked == NSITE and len(g.techs) == len(TECHS) and g.warps > 3 and g.t > 3600 * 20:
            pass
    print(f"END {fmt_t(g.t)} planets={g.n_unlocked} techs={len(g.techs)}/{len(TECHS)} DM={g.dm} warps={g.warps} "
          f"achievements={len(g.ach)}/{len(core.ACHIEVEMENTS)}")


if __name__ == "__main__":
    main()
