#!/usr/bin/env python3
"""Find planet-unlock and megaproject prices so a bot checking in every `interval` seconds hits a target timeline.
Usage: python3 calibrate.py [interval=120]"""
import random
import sys
import core
import sim

# (kind, index, target hours): u = unlock planet, p = megaproject, c = liberate sector
EVENTS = [("u", 1, 0.2), ("p", 0, 0.9), ("u", 2, 0.7), ("p", 1, 2.0), ("u", 3, 1.7), ("p", 2, 3.2), ("u", 4, 3.5),
          ("p", 3, 4.5), ("u", 5, 6.0), ("p", 4, 7.5), ("u", 6, 10.0), ("p", 5, 11.0), ("u", 7, 15.0), ("p", 6, 15.5),
          ("u", 8, 21.0), ("p", 7, 21.5), ("u", 9, 29.0), ("p", 8, 30.0), ("u", 10, 40.0), ("p", 9, 41.0),
          ("u", 11, 55.0), ("p", 10, 58.0), ("p", 11, 80.0)]
EVENTS += [("c", k, t) for k, t in zip(range(1, 16), [1.0, 2.2, 3.5, 5.5, 7.5, 10, 14, 18, 23, 29, 37, 45, 55, 67, 80])]
EVENTS.sort(key=lambda e: e[2])
BIG = 99.0


def event_time(kind, idx, horizon_h, interval):
    core.apply_tune()
    random.seed(1)
    g = core.Game(load=False, sim=True)
    bot = sim.Bot(g)
    end = horizon_h * 3600
    while g.t < end:
        dt = interval if g.t > 1800 else min(interval, 15)
        bot.click(dt)
        g.step(dt)
        bot.decide()
        if (kind == "u" and g.unlocked[idx]) or (kind == "p" and idx in g.projects) or (kind == "c" and idx in g.conquered):
            return g.t / 3600
    return None


def main():
    kw = dict(a.split("=") for a in sys.argv[1:] if "=" in a)
    interval = float(kw.get("interval", 120))
    core.UNLOCK_LOG[:] = [BIG] * len(core.UNLOCK_LOG)
    core.PROJECT_LOG[:] = [BIG] * len(core.PROJECT_LOG)
    core.SECTOR_LOG[:] = [BIG] * len(core.SECTOR_LOG)
    for kind, idx, target in EVENTS:
        arr = {"u": core.UNLOCK_LOG, "p": core.PROJECT_LOG, "c": core.SECTOR_LOG}[kind]
        pos = idx if kind == "p" else idx - 1
        lo, hi = 0.0, 40.0
        for _ in range(13):
            mid = (lo + hi) / 2
            arr[pos] = mid
            t = event_time(kind, idx, target * 1.4 + 0.3, interval)
            if t is not None and t < target:
                lo = mid
            else:
                hi = mid
        arr[pos] = round((lo + hi) / 2, 2)
        t = event_time(kind, idx, target * 2 + 1, interval)
        print(f"{ {'u': 'unlock', 'p': 'project', 'c': 'conquer'}[kind]:8s}{idx:3d} log={arr[pos]:5.2f}  at {t if t is None else round(t, 2)}h (target {target})", flush=True)
    print("UNLOCK_LOG =", core.UNLOCK_LOG)
    print("PROJECT_LOG =", core.PROJECT_LOG)
    print("SECTOR_LOG =", core.SECTOR_LOG)


if __name__ == "__main__":
    main()
