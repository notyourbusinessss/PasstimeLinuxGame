"""Draw a contact sheet of every planet's ships (rows = planets, columns = ship classes).

usage: python tools/ship_sheet.py [out.png] [--names] [--game] [--diff]
  --names  write each ship's name under it (the README picture)
  --game   draw the ships at the size the game uses, enlarged 3x, to judge how they read in play
  --diff   also print the pairs of planets whose ships look most alike (a rough check that the fleets are distinct)
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame

import gfx
import resources
import ships
from core import NSH, SHIPS, SITES


def sprite(p, i, size):
    return gfx.make_ship(i, SHIPS[i][3], size, ships.style(p), ships.palette(p))


def game_size(p, i):
    return round((26 + i * 2) * ships.scale(p))


def difference(a, b):
    """Mean per-pixel colour difference (0..255) between two same-size sprites, ignoring pixels empty in both."""
    n = tot = 0
    wa, ha = a.get_size()
    for x in range(wa):
        for y in range(ha):
            pa, pb = a.get_at((x, y)), b.get_at((x, y))
            if pa[3] < 40 and pb[3] < 40:
                continue
            n += 1
            tot += (abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])) / 3 + abs(pa[3] - pb[3]) / 3
    return tot / max(n, 1)


def main():
    pygame.init()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else "ship_sheet.png"
    names, game = "--names" in sys.argv, "--game" in sys.argv
    pygame.display.set_mode((8, 8))
    font = pygame.font.Font(resources.resource("assets/fonts/DejaVuSans.ttf"), 12)
    bold = pygame.font.Font(resources.resource("assets/fonts/DejaVuSans-Bold.ttf"), 14)
    size = 3 * 46 if game else 64
    cw = (size + 10) if not names else 122
    ch = size + 10 + (16 if names else 0)
    label = 96
    sheet = pygame.Surface((label + cw * NSH + 6, 30 + ch * len(SITES)))
    sheet.fill((14, 16, 30))
    for p, site in enumerate(SITES):
        y = 30 + p * ch
        if p % 2 == 0:
            pygame.draw.rect(sheet, (19, 22, 40), (0, y, sheet.get_width(), ch))
        sheet.blit(bold.render(site["name"], True, site["col"] if max(site["col"]) > 90 else (200, 205, 230)),
                   (10, y + ch // 2 - 9))
        for i in range(NSH):
            s = sprite(p, i, game_size(p, i) if game else size)
            if game:
                s = pygame.transform.scale(s, (s.get_width() * 3, s.get_height() * 3))
            cx = label + i * cw + cw // 2
            sheet.blit(s, s.get_rect(center=(cx, y + (size + 10) // 2)))
            if names:
                t = font.render(ships.name(p, i), True, (176, 182, 210))
                sheet.blit(t, t.get_rect(center=(cx, y + size + 10)))
    for i in range(NSH):
        t = bold.render(ships.class_name(i), True, (255, 214, 110))
        sheet.blit(t, t.get_rect(center=(label + i * cw + cw // 2, 15)))
    pygame.image.save(sheet, out)
    print("wrote", out)
    if "--diff" in sys.argv:
        worst = []
        for i in range(NSH):
            for p in range(len(SITES)):
                for q in range(p + 1, len(SITES)):
                    worst.append((difference(sprite(p, i, 40), sprite(q, i, 40)), i, p, q))
        worst.sort()
        print("most alike pairs (lower = more alike):")
        for d, i, p, q in worst[:12]:
            print(f"  {d:5.1f}  {ships.class_name(i):9s} {SITES[p]['name']} vs {SITES[q]['name']}")


if __name__ == "__main__":
    main()
