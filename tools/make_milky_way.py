#!/usr/bin/env python3
"""Paint the Milky Way of the galaxy map once and save it as assets/milky_way.png.

The game paints this picture itself when the file is missing (about half a second on a computer, but ten seconds or more in the
background of a phone, which made the game stutter right after Mars was unlocked), so the finished picture is shipped instead:

    python3 tools/make_milky_way.py

Run it again whenever gfx.make_milky_way or milkyway.py change (selftest checks that the file has the size the map expects).
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pygame  # noqa: E402

import frontview  # noqa: E402
import gfx  # noqa: E402

if __name__ == "__main__":
    pygame.display.init()
    pygame.display.set_mode((64, 64))
    img = gfx.make_milky_way(frontview.IMG)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "milky_way.png")
    pygame.image.save(img, out)
    print("saved", os.path.normpath(out), img.get_size(), os.path.getsize(out) // 1024, "KB")
