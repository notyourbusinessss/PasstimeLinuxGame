"""The worlds you have found, on screen: the "Other systems" page of the Planets tab and the line on the map's command bar.

The logic (what a system's planets are) is worlds.py and the pictures are gfx.make_world; this file only draws and handles
clicks. The functions take the App, like frontview does, and read the side panel's rectangle from space_miner when they run.
"""
import pygame

import colonies
import core
import galaxy
import gfx
import worlds
from core import fmt
from gfx import scale_c

PANEL = pygame.Rect(660, 104, 600, 608)       # the side panel: space_miner shares its own rectangle here (and resizes it in place)
ROW_H = 54
KIND_COL = dict(temperate=(120, 230, 140), ocean=(110, 170, 255), rocky=(190, 180, 170), desert=(235, 190, 120), ice=(190, 220, 255),
                lava=(255, 140, 80), dwarf=(190, 175, 165), mini=(190, 215, 230), ice_giant=(120, 215, 230), gas=(235, 180, 130))
EDGE = (120, 140, 195)


def summary(k):
    """A short line about the worlds of system k for the map's command bar, or None when it has none."""
    ws = worlds.planets_of(k)
    if not ws:
        return None
    nice = sum(1 for w in ws if worlds.GROUP_OF[w["kind"]] == "habitable")
    giants = sum(1 for w in ws if worlds.GROUP_OF[w["kind"]] == "giant")
    rock = len(ws) - nice - giants
    bits = [f"{n} {name}" for n, name in ((nice, "habitable"), (rock, "rocky"), (giants, "giant")) if n]
    return f"{len(ws)} world{'s' if len(ws) > 1 else ''}: " + ", ".join(bits)


def news_toasts(app):
    """Toast the worlds worth a message when a system is liberated: a real star's planets or the first habitable world you find. The
    rest is on the Other systems page (generals liberate many stars, so not every one is announced). Called every frame; it only does something when the systems you hold have changed."""
    g = app.g
    sig = worlds.sig(g.conquered)
    if sig == app.w_sig:
        return
    first = app.w_known is None
    new = set() if first else g.conquered - app.w_known
    app.w_sig, app.w_known = sig, set(g.conquered)
    best = None
    for k in sorted(new):
        ws = worlds.planets_of(k)
        hab = any(worlds.GROUP_OF[w["kind"]] == "habitable" for w in ws)
        if ws and (any(w["real"] for w in ws) or (hab and not app.w_hab)):
            best = k if best is None or sum(w["real"] for w in ws) > sum(w["real"] for w in worlds.planets_of(best)) else best
        app.w_hab = app.w_hab or hab
    if best is not None:
        g.toast(worlds.news(best), 5)


def has_news(app):
    """True while there are worlds you have not looked at on the Other systems page."""
    return worlds.stats(app.g.conquered)["total"] > app.w_seen


def draw_toggle(app, scr, fonts, y):
    """The three pages of the Planets tab: the solar system, the colony worlds you can settle, every world you found."""
    big, med, sm_f, tiny = fonts
    g = app.g
    n = worlds.stats(g.conquered)["total"]
    ready = sum(1 for k in range(core.NSOL, core.NSITE) if not g.unlocked[k] and g.can_unlock(k))
    labels = ["Solar system", f"Colonies {g.n_colonies}/{core.NSITE - core.NSOL}", f"All worlds ({n:,})"]
    w = (PANEL.w - 16) // 3
    for i, label in enumerate(labels):
        r = pygame.Rect(PANEL.x + i * (w + 8), y, w, 28)
        dot = (i == 1 and ready > 0 and app.pl_page != 1) or (i == 2 and app.pl_page != 2 and has_news(app))
        app.button(scr, r, label, sm_f, (lambda i=i: set_page(app, i)), col=(78, 100, 176) if app.pl_page == i else (34, 42, 74),
                   panel=True, selected=app.pl_page == i, dot=dot)
    return y + 38


def set_page(app, i):
    if app.pl_page != i:
        app.pl_page = i
        app.scroll[app.tab] = 0


def select(app, w):
    app.wsel = (w["sys"], w["idx"])


def selected(app):
    if app.wsel is None:
        return None
    k, i = app.wsel
    ws = worlds.planets_of(k) if k in app.g.conquered else ()
    return ws[i] if i < len(ws) else None


def show_on_map(app, k):
    """Open the galaxy map on system k."""
    if not app.g.galaxy_open:
        return
    app.sel_sector = k
    app.view = "galaxy"
    app.fv.focus(k)


def draw_page(app, scr, fonts, y):
    """The Other systems page: a summary, the filters, the card of the selected world and the list of every world you found."""
    big, med, sm_f, tiny = fonts
    g = app.g
    P = PANEL
    st = worlds.stats(g.conquered)
    app.w_seen = st["total"]
    y = draw_toggle(app, scr, fonts, y)
    if not g.galaxy_open:
        app.txt(scr, sm_f, "Unlock Mars to open the galaxy map; every star you liberate shows you its planets here.", (P.x + 4, y), (170, 180, 210))
        return y + 30
    app.txt(scr, sm_f, f"{st['total']:,} worlds in {st['systems']:,} systems", (P.x + 4, y), (230, 232, 250))
    app.txt(scr, tiny, f"{st['habitable']:,} habitable  -  {st['real']:,} confirmed exoplanets  -  {st['kinds']} of {len(worlds.KINDS)} kinds",
            (P.right - 4, y + 4), (160, 170, 200), "topright")
    y += 26
    if st["total"] == 0:
        for i, line in enumerate(["No worlds yet.", "Liberate a star in the Galaxy tab and its planets are charted here: real planets for the",
                                  "real stars (TRAPPIST-1, Kepler-186, Proxima...) and surveyed worlds for the rest."]):
            app.txt(scr, sm_f if i == 0 else tiny, line, (P.x + 4, y + i * 18), (200, 205, 230) if i == 0 else (150, 160, 190))
        return y + 70
    # --- filters
    sysid = app.wf_sys if app.wf_sys in g.conquered and worlds.count_of(app.wf_sys) else None
    app.wf_sys = sysid
    held = [(grp, label, sum(st["by_kind"][k] for k in worlds.KINDS if grp == "all" or worlds.GROUP_OF[k] == grp))
            for grp, label in worlds.GROUPS]
    sel = app.sel_sector if app.sel_sector in g.conquered and worlds.count_of(app.sel_sector) else None
    chips = [(f"{label} {n:,}", sysid is None and app.wf_group == grp, (lambda grp=grp: set_filter(app, grp, None))) for grp, label, n in held]
    if sel is not None:
        name = galaxy.STARS[sel]["name"]
        chips.append((f"{name if len(name) < 14 else name[:13] + '.'} {worlds.count_of(sel)}", sysid == sel,
                      (lambda: set_filter(app, "all", sel if app.wf_sys != sel else None))))
    cw = (P.w - 4 * (len(chips) - 1)) // len(chips)
    for i, (label, on, fn) in enumerate(chips):
        app.button(scr, pygame.Rect(P.x + i * (cw + 4), y, cw, 26), label, tiny, fn, col=(78, 100, 176) if on else (34, 42, 74),
                   panel=True, selected=on)
    y += 36
    # --- the selected world
    w = selected(app)
    if w is not None:
        y = draw_card(app, scr, fonts, y, w)
    # --- the list
    lst = world_list(app, sysid)
    if not lst:
        app.txt(scr, sm_f, "No worlds of that kind yet.", (P.x + 4, y + 6), (190, 196, 220))
        return y + 40
    first = max(0, int((P.y - y) // ROW_H) - 1)
    last = min(len(lst), int((P.bottom - y) // ROW_H) + 2)
    for i in range(first, last):
        draw_row(app, scr, fonts, pygame.Rect(P.x, y + i * ROW_H, P.w, ROW_H - 4), lst[i], w)
    return y + len(lst) * ROW_H


CL_FILTERS = [("open", "Open"), ("ready", "Ready"), ("settled", "Settled"), ("locked", "Locked"), ("all", "All")]
CL_RANK = dict(settled=0, ready=1, waiting=2, locked=3)


def colony_state(g, k):
    """settled; ready (its star is liberated and its tier reached); waiting (liberated, tier not reached yet); locked (star not liberated)."""
    if g.unlocked[k]:
        return "settled"
    c = core.SITES[k]
    if c["sys"] not in g.conquered:
        return "locked"
    return "ready" if g.unlocked[c["tier"]] else "waiting"


def draw_colonies(app, scr, fonts, y):
    """The Colonies page: the 89 real planets of other stars that you can settle and play like the planets of the solar system."""
    big, med, sm_f, tiny = fonts
    g = app.g
    P = PANEL
    y = draw_toggle(app, scr, fonts, y)
    ks = list(range(core.NSOL, core.NSITE))
    state = {k: colony_state(g, k) for k in ks}
    count = {st: sum(1 for k in ks if state[k] == st) for st in CL_RANK}
    shown = {"open": count["settled"] + count["ready"] + count["waiting"], "ready": count["ready"], "settled": count["settled"],
             "locked": count["locked"], "all": len(ks)}
    app.txt(scr, sm_f, f"{g.n_colonies} of {len(ks)} colony worlds settled", (P.x + 4, y), (230, 232, 250))
    nxt = colonies.COST_BASE * colonies.COST_GROWTH ** g.n_colonies
    app.txt(scr, tiny, f"next colony: {nxt:.2g}x the price of its tier", (P.right - 4, y + 4), (160, 170, 200), "topright")
    y += 24
    app.txt(scr, tiny, "Liberate a star, reach its planet's tier, then settle it: own ore, fleet, colony, bonus.",
            (P.x + 4, y), (150, 160, 190))
    y += 24
    cw = (P.w - 4 * (len(CL_FILTERS) - 1)) // len(CL_FILTERS)
    for i, (key, label) in enumerate(CL_FILTERS):
        on = app.cl_filter == key
        app.button(scr, pygame.Rect(P.x + i * (cw + 4), y, cw, 26), f"{label} {shown[key]}", tiny, (lambda key=key: set_cl_filter(app, key)),
                   col=(78, 100, 176) if on else (34, 42, 74), panel=True, selected=on)
    y += 36
    pick = [k for k in ks if (app.cl_filter == "all" or (app.cl_filter == "open" and state[k] != "locked") or state[k] == app.cl_filter)]
    pick.sort(key=lambda k: (CL_RANK[state[k]], k))
    if not pick:
        near = []
        for k in sorted(ks, key=lambda q: galaxy.STARS[core.SITES[q]["sys"]]["d"]):
            nm = galaxy.STARS[core.SITES[k]["sys"]]["name"]
            if nm not in near:
                near.append(nm)
        app.txt(scr, sm_f, "Nothing here yet." if app.cl_filter != "open" else "No colony world is open yet.", (P.x + 4, y + 4), (200, 205, 230))
        if app.cl_filter == "open":
            app.txt(scr, tiny, "Liberate a star with planets. The nearest are " + ", ".join(near[:3]) + ".", (P.x + 4, y + 30), (150, 160, 190))
        return y + 60
    good, bad = (130, 255, 150), (230, 130, 130)
    for k in pick:
        c = core.SITES[k]
        st = state[k]
        star = galaxy.STARS[c["sys"]]
        lines = [(c["perk"], (170, 175, 205))]
        rt, ok, fn, dim = None, True, None, False
        if st == "settled":
            rt = "YOU ARE HERE" if k == g.cur else "TRAVEL"
            fn = (lambda k=k: app.strip_click(k)) if k != g.cur else None
            lines.append((f"{fmt(g.ore[k])} {c['ore']} stored   (+{fmt(g.s_ops[k])}/s)", (205, 210, 230)))
        elif st == "ready":
            ores, cr = g.unlock_cost(k)
            for pp, amt in ores:
                if amt > 0:
                    lines.append((f"{fmt(amt)} {core.SITES[pp]['ore']}   (have {fmt(g.ore[pp])})", good if g.ore[pp] >= amt else bad))
            if cr > 0:
                lines.append((f"{fmt(cr)} credits   (have {fmt(g.credits)})", good if g.credits >= cr else bad))
            ok = g.can_unlock(k)
            rt, fn = "SETTLE", (lambda k=k: g.unlock_planet(k))
        elif st == "waiting":
            lines.append((f"Unlock {core.SITES[c['tier']]['name']} (planet {c['tier'] + 1}) first: this world is on its tier", (230, 190, 130)))
            rt, ok, dim = "WAITING", False, True
        else:
            lines.append((f"Liberate {star['name']} ({galaxy.fmt_ly(star['d'])}) to settle it", (230, 190, 130)))
            rt, ok, dim, fn = "LOCKED", False, True, (lambda s=c["sys"]: show_on_map(app, s))
        r = pygame.Rect(P.x, y, P.w, 54 + 15 * len(lines))
        y += r.h + 6
        if not r.colliderect(P):
            continue
        icon = (app.planet_dark[k] if dim else app.planet_icons[k])
        app.row(scr, fonts, r, c["name"], f"{worlds.KIND_NAMES[c['wkind']]}  -  {star['name']}, {galaxy.fmt_ly(star['d'])}  -  tier {c['tier']}",
                rt, f"{core.SITES[c['tier']]['name']}-class", ok, c["col"], fn, dim=dim, icon=icon, lines=lines,
                tcol=c["col"] if not dim else (130, 135, 160))
    return y


def set_cl_filter(app, key):
    app.cl_filter = key
    app.scroll[app.tab] = 0


def set_filter(app, grp, sysid):
    app.wf_group, app.wf_sys = grp, sysid
    app.scroll[app.tab] = 0


def world_list(app, sysid):
    """The worlds shown, cached until the systems you hold or the filter change."""
    g = app.g
    key = (worlds.sig(g.conquered), app.wf_group, sysid)
    if app.w_cache is None or app.w_cache[0] != key:
        app.w_cache = (key, worlds.found(g.conquered, app.wf_group, sysid))
    return app.w_cache[1]


def draw_row(app, scr, fonts, r, w, current):
    big, med, sm_f, tiny = fonts
    ring = w["ring"]
    icon = gfx.make_world(w["kind"], w["seed"], 40, ring)
    on = current is not None and current is w
    col = KIND_COL[w["kind"]]
    app.row(scr, fonts, r, w["name"], f"{worlds.KIND_NAMES[w['kind']]}  -  {worlds.size_text(w['r'], w['m']).split(',')[0]}  -  "
            f"{w['t']:.0f} K", "CONFIRMED" if w["real"] else None, None, True, col if not on else (255, 215, 110),
            (lambda w=w: select(app, w)), icon=icon)


def draw_card(app, scr, fonts, y, w):
    """The card of the selected world: its picture, its numbers and what kind of place it is."""
    big, med, sm_f, tiny = fonts
    P = PANEL
    r = pygame.Rect(P.x, y, P.w, 196)
    if r.colliderect(P):
        col = KIND_COL[w["kind"]]
        pygame.draw.rect(scr, (24, 30, 56), r, border_radius=10)
        pygame.draw.rect(scr, col, r, 1, border_radius=10)
        pic = gfx.make_world(w["kind"], w["seed"], 150, w["ring"])
        scr.blit(gfx.glow(88, scale_c(col, 0.28)), (r.x + 87 - 88, r.y + 100 - 88), special_flags=pygame.BLEND_RGB_ADD)
        scr.blit(pic, (r.x + 12, r.y + 22))
        x = r.x + 184
        app.txt(scr, med, w["name"], (x, r.y + 10), (245, 245, 252))
        for i, (label, value) in enumerate(worlds.lines(w)):
            app.txt(scr, tiny, label, (x, r.y + 40 + i * 17), (130, 140, 175))
            app.txt(scr, tiny, value, (x + 92, r.y + 40 + i * 17), (214, 220, 240))
        app.txt(scr, tiny, worlds.KIND_BLURB[w["kind"]], (x, r.y + 148), col)
        app.txt(scr, tiny, worlds.origin(w), (x, r.y + 166), (150, 158, 190))
        k = w["sys"]
        app.button(scr, pygame.Rect(r.right - 150, r.y + 8, 138, 24), "Show on the map", tiny, (lambda k=k: show_on_map(app, k)),
                   panel=True, col=(50, 84, 120))
    return y + 204
