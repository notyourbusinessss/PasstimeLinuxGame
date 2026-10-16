"""Small vector icons for the side panel's tabs, drawn with pygame (no image files) and cached."""
import math

import pygame

_CACHE = {}
TAB_ACCENT = {"Ships": (120, 175, 255), "Upgrades": (130, 235, 160), "Colony": (255, 200, 110), "Planets": (125, 210, 235),
              "Galaxy": (190, 160, 255), "Tech": (110, 235, 225), "Quests": (255, 190, 120), "Warp": (255, 140, 200),
              "Awards": (255, 215, 90), "Dev": (255, 110, 110)}


def _poly(s, col, pts, w=0):
    S = s.get_width()
    pygame.draw.polygon(s, col, [(x * S, y * S) for x, y in pts], w)


def _spiral(s, col, arms, turns, w):
    S = s.get_width()
    for a in range(arms):
        pts = []
        for i in range(30):
            t = i / 29
            ang = a * math.pi * 2 / arms + t * turns
            r = 0.08 + 0.4 * t
            pts.append((S / 2 + math.cos(ang) * r * S, S / 2 + math.sin(ang) * r * S))
        pygame.draw.lines(s, col, False, pts, w)


def _draw(name, s, col):
    S = s.get_width()
    w = max(2, S // 12)
    if name == "Ships":
        _poly(s, col, [(0.5, 0.06), (0.86, 0.9), (0.5, 0.7), (0.14, 0.9)])
    elif name == "Upgrades":
        _poly(s, col, [(0.5, 0.06), (0.9, 0.52), (0.64, 0.52), (0.64, 0.94), (0.36, 0.94), (0.36, 0.52), (0.1, 0.52)])
    elif name == "Colony":
        pygame.draw.arc(s, col, (S * 0.1, S * 0.22, S * 0.8, S * 1.0), 0, math.pi, w + 1)
        pygame.draw.line(s, col, (S * 0.1, S * 0.72), (S * 0.9, S * 0.72), w + 1)
        pygame.draw.rect(s, col, (S * 0.42, S * 0.52, S * 0.16, S * 0.2))
        pygame.draw.line(s, col, (S * 0.18, S * 0.9), (S * 0.82, S * 0.9), w)
    elif name == "Planets":
        pygame.draw.circle(s, col, (S // 2, S // 2), int(S * 0.27))
        pygame.draw.ellipse(s, col, (S * 0.02, S * 0.36, S * 0.96, S * 0.28), w)
    elif name == "Galaxy":
        _spiral(s, col, 2, 3.6, w)
    elif name == "Tech":
        pygame.draw.circle(s, col, (S // 2, S // 2), int(S * 0.09))
        for rot in (0, 60, 120):
            layer = pygame.Surface((S, S), pygame.SRCALPHA)
            pygame.draw.ellipse(layer, col, (S * 0.06, S * 0.3, S * 0.88, S * 0.4), w)
            turned = pygame.transform.rotate(layer, rot)
            s.blit(turned, turned.get_rect(center=(S // 2, S // 2)))
    elif name == "Quests":
        pygame.draw.line(s, col, (S * 0.22, S * 0.08), (S * 0.22, S * 0.94), w + 1)
        _poly(s, col, [(0.22, 0.1), (0.88, 0.28), (0.22, 0.5)])
    elif name == "Warp":
        _spiral(s, col, 1, 5.4, w)
        pygame.draw.circle(s, col, (S // 2, S // 2), max(2, S // 11))
    elif name == "Awards":
        pygame.draw.circle(s, col, (S // 2, int(S * 0.38)), int(S * 0.27))
        _poly(s, col, [(0.3, 0.6), (0.18, 0.96), (0.4, 0.84), (0.5, 0.96), (0.46, 0.64)])
        _poly(s, col, [(0.7, 0.6), (0.82, 0.96), (0.6, 0.84), (0.5, 0.96), (0.54, 0.64)])
    else:                                                        # Dev: < >
        pygame.draw.lines(s, col, False, [(S * 0.36, S * 0.22), (S * 0.1, S * 0.5), (S * 0.36, S * 0.78)], w)
        pygame.draw.lines(s, col, False, [(S * 0.64, S * 0.22), (S * 0.9, S * 0.5), (S * 0.64, S * 0.78)], w)


def tab_icon(name, size, col):
    """The icon of a tab, size x size pixels (drawn at twice the size and scaled down so the edges are smooth)."""
    key = (name, size, col)
    pic = _CACHE.get(key)
    if pic is None:
        big = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
        _draw(name, big, col)
        pic = _CACHE[key] = pygame.transform.smoothscale(big, (size, size))
    return pic
