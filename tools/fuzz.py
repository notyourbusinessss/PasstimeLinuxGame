"""Random-input stress test: plays the game with random clicks, drags, scrolls, key presses and time jumps in several
game states and reports every distinct exception. Finds crashes the self-test does not.

    python3 tools/fuzz.py                 # all states, 2500 frames each
    python3 tools/fuzz.py frames=6000 seed=7 states=late,ascended
"""
import os
import random
import sys
import tempfile
import time
import traceback

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import pygame

import core
import gamelog
import generals
import sim
import space_miner as sm

ARGS = dict(a.split("=") for a in sys.argv[1:] if "=" in a)
FRAMES = int(ARGS.get("frames", 2500))
SEED = int(ARGS.get("seed", 1))
STATES = ARGS.get("states", "fresh,mid,late,ascended,dev,command").split(",")
TOUCH = ARGS.get("touch", "0") == "1"          # touch=1: use the touch screen interface (taps, drags, pinches) as well


def play(hours, interval=90):
    random.seed(SEED)
    g = core.Game(load=False, sim=True)
    bot = sim.Bot(g)
    while g.t < hours * 3600:
        dt = interval if g.t > 1800 else 15
        bot.click(dt)
        g.step(dt)
        bot.decide()
    g.sim = False
    return g


def make_state(name):
    if name == "fresh":
        return core.Game(load=False), False
    if name == "mid":
        return play(7), False
    if name == "late":
        return play(30, 120), False
    if name == "ascended":
        g = play(30, 120)
        g.conquered = set(range(core.NSEC))
        g.recalc()
        g.ascend(force=True)
        return g, False
    if name == "dev":
        return play(7), True
    if name == "command":                                   # every general and warden earned, orders set, on the Galaxy tab
        g = play(7)
        g.conquered |= set(generals.SYSTEM_OF)
        generals.ensure(g)
        g.recalc()
        return g, False
    raise SystemExit(f"unknown state {name}")


def main():
    pygame.display.init()
    pygame.font.init()
    scr = pygame.display.set_mode((sm.W, sm.H))
    fonts = tuple(pygame.font.Font(sm.resources.resource("assets/fonts/DejaVuSans%s.ttf" % ("-Bold" if b else "")), s)
                  for s, b in ((30, True), (18, True), (15, False), (12, False)))
    tmp = tempfile.mkdtemp(prefix="space_miner_fuzz_")
    core.SAVE = os.path.join(tmp, "save.json")
    gamelog.setup(directory=tmp)
    found = {}
    total = 0
    for name in STATES:
        t0 = time.time()
        g, dev = make_state(name)
        app = sm.App(dev=dev)
        app.g = g
        app.can_scale = True
        sm.resources.TOUCH = TOUCH
        app.scr = pygame.display.get_surface()
        sm.apply_layout(1280, 720)
        app.set_resolution(1280, 720)
        rng = random.Random(SEED)
        keys = [pygame.K_1 + i for i in range(9)] + [pygame.K_g, pygame.K_z, pygame.K_PLUS, pygame.K_MINUS, pygame.K_UP,
                                                    pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_SPACE]
        errors = 0
        for frame in range(FRAMES):
            try:
                for _ in range(rng.choice((0, 1, 1, 2, 3))):
                    r = rng.random()
                    pos = (rng.randrange(0, sm.W), rng.randrange(0, sm.H))      # sm.W / sm.H follow the current canvas
                    app.mouse = pos
                    if TOUCH and r < 0.5:
                        kind = rng.random()
                        if kind < 0.4:                                                    # a tap
                            app.touch.down(pos); app.touch.up(pos)
                        elif kind < 0.75:                                                 # a drag (maybe a fling)
                            app.touch.down(pos)
                            for _ in range(rng.randrange(1, 8)):
                                pos = (pos[0] + rng.randrange(-80, 80), pos[1] + rng.randrange(-120, 120))
                                app.touch.move(pos)
                            app.touch.up(pos)
                        else:                                                             # a pinch
                            a, b = pos, (pos[0] + rng.randrange(20, 200), pos[1] + rng.randrange(-80, 80))
                            win = (sm.W, sm.H)
                            ft = lambda k, i, q: app.touch.finger(k, i, q[0] / sm.W, q[1] / sm.H, win)
                            app.touch.down(a); ft("down", 1, a); ft("down", 2, b)
                            for s in range(rng.randrange(1, 6)):
                                a = (a[0] - 8, a[1]); b = (b[0] + 8 * rng.choice((-1, 1)), b[1])
                                ft("motion", 1, a); ft("motion", 2, b)
                            ft("up", 2, b); ft("up", 1, a); app.touch.up(a)
                        app.touch.update(0.016)
                    elif r < 0.40:
                        if not (app.view == "galaxy" and not g.event and app.fv.down(pos)):
                            app.mouse_down(pos)
                        app.fv.up(pos)
                    elif r < 0.52:                                                        # a drag
                        app.fv.down(pos)
                        for _ in range(rng.randrange(1, 6)):
                            pos = (pos[0] + rng.randrange(-60, 60), pos[1] + rng.randrange(-60, 60))
                            app.fv.move(pos)
                        app.fv.up(pos)
                    elif r < 0.64:                                                        # wheel
                        if sm.PANEL.collidepoint(pos):
                            app.scroll[app.tab] = max(0, app.scroll[app.tab] - rng.choice((-3, -1, 1, 3, 40)) * 50)
                        else:
                            app.fv.wheel(pos, rng.choice((-3, -1, 1, 3)))
                    elif r < 0.90:
                        k = rng.choice(keys)
                        if k == pygame.K_SPACE:
                            app.space_click()
                        elif pygame.K_1 <= k <= pygame.K_9 and k - pygame.K_1 < len(app.tabs):
                            app.set_tab(k - pygame.K_1)
                        elif k == pygame.K_g:
                            app.strip_click(-1)
                        else:
                            app.galaxy_key(k)
                    elif r < 0.95 and dev:
                        app.set_tab(len(app.tabs) - 1)
                    elif r < 0.953:
                        app.gal_page = rng.randrange(len(sm.App.GAL_PAGES))
                    elif r < 0.954:
                        app.pl_page = rng.randrange(3)                                  # the Planets tab: Solar system / Colonies / All worlds
                        app.tab = sm.T_PLANETS if rng.random() < 0.6 else app.tab
                    elif r < 0.955:
                        rng.choice((app.toggle_gal_wide, app.leave_galaxy, lambda: app.strip_click(-1)))()
                    elif r < 0.97:
                        app.set_resolution_choice(rng.choice(["auto", "1280x720", "1600x900", "1920x1080", "1600x720", "2560x1440"]))
                    else:
                        app.select_sector(rng.randrange(1, core.NSEC))
                dt = rng.choice((0.016, 0.016, 0.033, 0.1, 0.25, 5.0, 60.0)) if rng.random() < 0.97 else rng.choice((600.0, 3600.0))
                app.update(min(dt, 0.25) if rng.random() < 0.9 else dt)
                app.draw(app.scr, fonts)
            except Exception:
                app.scr.set_clip(None)
                errors += 1
                if gamelog.report("fuzz", sys.exc_info()):
                    sig = "".join(traceback.format_exception_only(*sys.exc_info()[:2])).strip()
                    found.setdefault(name + ": " + sig, traceback.format_exc())
        total += errors
        print(f"{name:9s} {FRAMES} frames in {time.time() - t0:5.1f}s  errors: {errors}")
    print()
    for sig, tb in found.items():
        print("=" * 70)
        print(sig)
        print(tb)
    print(f"{len(found)} distinct error(s), {total} occurrence(s)")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
