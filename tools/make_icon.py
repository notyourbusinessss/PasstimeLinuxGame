"""Draws the app icon (assets/icon.png and a 512 px version for Android) with the game's own procedural graphics.

    python3 tools/make_icon.py
"""
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pygame

import core
import gfx

ADD = pygame.BLEND_RGB_ADD


def draw(size):
    S = size
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    bg = pygame.Surface((S, S))
    for y in range(S):                                         # deep space gradient
        k = y / S
        pygame.draw.line(bg, (int(10 + 24 * k), int(8 + 6 * k), int(30 + 40 * k)), (0, y), (S, y))
    rng = random.Random(7)
    for _ in range(S // 3):
        x, y = rng.randrange(S), rng.randrange(S)
        v = rng.choice((120, 170, 230))
        bg.set_at((x, y), (v, v, min(255, v + 25)))
    bg.blit(gfx.glow(int(S * 0.55), (46, 28, 90)), (S * 0.5 - S * 0.55, S * 0.5 - S * 0.55), special_flags=ADD)
    mask = pygame.Surface((S, S), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, S, S), border_radius=int(S * 0.22))
    s.blit(bg, (0, 0))
    r = int(S * 0.27)
    site = core.SITES[0]
    planet = gfx.make_planet(58, site["kind"], site["col"], 100)          # the in-game size, scaled to fit
    planet = pygame.transform.smoothscale(planet, (2 * r + 2, 2 * r + 2))
    cx, cy = S * 0.46, S * 0.54
    s.blit(gfx.glow(int(r * 1.7), (40, 70, 140)), (cx - r * 1.7, cy - r * 1.7), special_flags=ADD)
    s.blit(planet, planet.get_rect(center=(cx, cy)))
    for i in range(7):                                         # an asteroid belt
        a = 0.35 + i * 0.52
        rad = r * 1.55
        ast = gfx.make_asteroid(int(S * (0.07 + 0.02 * (i % 3))), 11 + i, (255, 220, 190))
        s.blit(ast, ast.get_rect(center=(cx + math.cos(a) * rad, cy + math.sin(a) * rad * 0.72)))
    ship = gfx.make_ship(3, core.SHIPS[3][3], int(S * 0.2))
    ship = pygame.transform.rotate(ship, 38)
    s.blit(gfx.glow(int(S * 0.13), (255, 200, 120)), (S * 0.77 - S * 0.13, S * 0.23 - S * 0.13), special_flags=ADD)
    s.blit(ship, ship.get_rect(center=(S * 0.77, S * 0.23)))
    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return s


def main():
    pygame.display.init()
    pygame.display.set_mode((16, 16))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
    for size, name in ((256, "icon.png"), (512, "icon-512.png")):
        pygame.image.save(draw(size), os.path.join(out, name))
        print("wrote", name)


if __name__ == "__main__":
    main()
