"""Frontline model: where the battle line between your territory and an enemy sector sits, and how safe a sector is.

Pure game logic (no pygame): the zoomable galaxy view in frontview.py draws it, and the Galaxy tab reads the reports.
Nothing here changes the game state; the numbers come from the same rules the campaigns and the Threat Director use.
"""
import math

from core import NSH, SECTORS, SECTOR_LINKS, fmt, win_chance
import director

STATUS = [  # win chance at least, label, colour
    (0.80, "Dominating", (120, 255, 150)),
    (0.55, "Advantage", (190, 240, 120)),
    (0.40, "Stalemate", (255, 220, 110)),
    (0.15, "Under pressure", (255, 160, 100)),
    (0.00, "Outgunned", (255, 110, 100)),
]
RISK = [  # chance to hold against a counter-offensive at least, label, colour
    (0.80, "Secure", (120, 255, 150)),
    (0.50, "Holding", (255, 220, 110)),
    (0.00, "Vulnerable", (255, 110, 100)),
]


def ships_for(power, cap=30):
    """How many ships to draw for a force of this power."""
    return max(3, min(cap, int(3 + 2.0 * math.log10(max(power, 1.0)))))


def lanes(g):
    """Every lane that is a front: (your sector, enemy sector)."""
    out = []
    for k in g.frontier():
        for n in SECTOR_LINKS[k]:
            if n in g.conquered:
                out.append((n, k))
    return out


def share(g, k):
    """Your share of the combined strength on the front against sector k (0..1)."""
    fp = max(1.0, g.fleet_power())
    ep = g.sector_power(k)
    return fp / (fp + ep)


def front_pos(g, k):
    """How far along the lane from your sector (0) to the enemy sector k (1) the front line sits.
    A stronger fleet pushes it towards the enemy; a running campaign pushes it further."""
    pos = 0.12 + 0.76 * share(g, k)
    c = g.campaign
    if c and c["k"] == k:
        pos += (0.94 - pos) * 0.55 * max(0.0, min(1.0, c["t"] / max(1.0, c["dur"])))
    return pos


def status(g, k):
    """(label, colour) of the fighting at enemy sector k."""
    ch = win_chance(g.fleet_power(), g.sector_power(k))
    for lo, label, col in STATUS:
        if ch >= lo:
            return label, col
    return STATUS[-1][1:]


def source_sector(g, k):
    """The sector of yours the attack on k would launch from (the nearest held neighbour)."""
    held = [n for n in SECTOR_LINKS[k] if n in g.conquered]
    if not held:
        return None
    px, py = SECTORS[k]["pos"]
    return min(held, key=lambda n: (SECTORS[n]["pos"][0] - px) ** 2 + (SECTORS[n]["pos"][1] - py) ** 2)


def neighbours(g, k):
    """Neighbouring sectors of k split into (held by you, held by the enemy)."""
    mine = [n for n in SECTOR_LINKS[k] if n in g.conquered]
    theirs = [n for n in SECTOR_LINKS[k] if n not in g.conquered]
    return mine, theirs


def exposure(g, k):
    """For a sector you hold: the enemy sectors that border it and your worst chance to hold against a
    counter-offensive from any of them (None if it is not on a front)."""
    foes = [n for n in SECTOR_LINKS[k] if n not in g.conquered]
    if k == 0 or not foes:
        return foes, None
    defense = director.sector_defense(g, k)
    worst = 1.0
    for n in foes:
        fac = SECTORS[n]["faction"] or SECTORS[k]["faction"]
        power = g.sector_power(k) * director.hostility_mult(g, fac)
        worst = min(worst, win_chance(defense, power))
    return foes, worst


def risk(chance):
    for lo, label, col in RISK:
        if chance >= lo:
            return label, col
    return RISK[-1][1:]


def fleet_tiers(g, n=3):
    """The ship types that make up your fleet, biggest first (for drawing it)."""
    have = [sum(g.owned[p][i] for p in range(len(g.owned))) for i in range(NSH)]
    tiers = [i for i in range(NSH - 1, -1, -1) if have[i] > 0][:n]
    return tiers or [0]


def report(g, k):
    """Lines for the 'Front report' card of sector k: ([(text, colour), ...], your power share or None)."""
    lines = []
    if k in g.conquered:
        if k == 0:
            return [("Your home system. Nothing threatens it directly.", (170, 176, 205))], None
        foes, hold = exposure(g, k)
        gar = director.sector_defense(g, k)
        lines.append((f"Garrison {fmt(gar)}   -   borders: " +
                      (", ".join(SECTORS[n]["name"] for n in foes) if foes else "no enemy sectors"), (205, 210, 230)))
        if hold is None:
            lines.append(("Rear sector: no counter-offensive can reach it.", (130, 255, 150)))
        else:
            label, col = risk(hold)
            lines.append((f"{label}: {hold * 100:.0f}% to hold against a counter-offensive", col))
        return lines, None
    mine, theirs = neighbours(g, k)
    label, col = status(g, k)
    fp, ep = g.fleet_power(), g.sector_power(k)
    sh = share(g, k)
    lines.append((f"{label}   -   you {fmt(fp)} vs enemy {fmt(ep)}", col))
    lines.append((f"Power split: you {sh * 100:.0f}% / enemy {100 - sh * 100:.0f}%", (205, 210, 230)))
    src = source_sector(g, k)
    lines.append(("Attack from " + (SECTORS[src]["name"] if src is not None else "-") + "   -   borders: " +
                  ", ".join(SECTORS[n]["name"] for n in mine + theirs), (170, 176, 205)))
    return lines, sh
