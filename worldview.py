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
    labels = ["Solar system", f"Colonies {len(g.colonies):,}", f"All worlds ({n:,})"]
    w = (PANEL.w - 16) // 3
    for i, label in enumerate(labels):
        r = pygame.Rect(PANEL.x + i * (w + 8), y, w, 28)
        dot = (i == 1 and app.pl_page != 1 and colony_ready(app)) or (i == 2 and app.pl_page != 2 and has_news(app))
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


CL_FILTERS = [("ready", "Ready"), ("settled", "Settled"), ("waiting", "Waiting"), ("star", "This star")]
CL_ROW = 88


def colony_ready(app):
    """True while a world you hold can be settled with what you have (looked at once a second: it scans every world of your stars)."""
    now = int(app.t)
    if app.cl_ready_t != now:
        app.cl_ready_t = now
        app.cl_ready = bool(app.g.colony_options(1))
    return app.cl_ready


def colony_lists(app):
    """The worlds of the stars you hold in the three states: settled (latest first), ready and waiting (nearest star first). Cached
    until the stars you hold, the colonies or the tiers you have change."""
    g = app.g
    owned = g.owned_tiers()
    key = (worlds.sig(g.conquered), len(g.colonies), frozenset(owned))
    if app.cl_cache is None or app.cl_cache[0] != key:
        ready, waiting = [], []
        for k, i in g.world_options():
            (ready if colonies.tier_of(k) - 1 in owned else waiting).append((k, i))
        app.cl_cache = (key, dict(settled=list(reversed(g.colonies)), ready=ready, waiting=waiting))
    return app.cl_cache[1]


def settle_all(app):
    """Settle every world you can pay for, cheapest first (at most 25 at a time)."""
    g = app.g
    done = 0
    while done < 25:
        opts = g.colony_options(1)
        if not opts or g.settle(*opts[0]) is None:
            break
        done += 1
    if done:
        g.toast(f"{done} world{'s' if done > 1 else ''} settled.", 4)


def draw_colonies(app, scr, fonts, y):
    """The Colonies page: the worlds of every star you hold, which you can settle and play like the planets of the solar system."""
    big, med, sm_f, tiny = fonts
    g = app.g
    P = PANEL
    y = draw_toggle(app, scr, fonts, y)
    lists = colony_lists(app)
    sel = app.sel_sector if app.sel_sector in g.conquered and worlds.count_of(app.sel_sector) else None
    nxt = colonies.COST_BASE * colonies.COST_GROWTH ** len(g.colonies)
    n_ready = len(lists["ready"])
    app.txt(scr, sm_f, f"{len(g.colonies):,} worlds settled  -  {n_ready + len(lists['waiting']):,} more in the stars you hold", (P.x + 4, y), (230, 232, 250))
    y += 24
    app.txt(scr, tiny, f"The next one costs {nxt:.2g}x the price of a solar planet of its tier, in the ore of the tiers before it.", (P.x + 4, y), (150, 160, 190))
    y += 22
    chips = [(key, label, len(lists[key]) if key != "star" else (worlds.count_of(sel) if sel else 0)) for key, label in CL_FILTERS]
    if app.cl_filter == "star" and not sel:
        app.cl_filter = "ready"
    auto = g.E["autoset"]
    cw = (P.w - (112 + (124 if auto else 0)) - 4 * len(chips)) // len(chips)
    for i, (key, label, n) in enumerate(chips):
        on = app.cl_filter == key
        app.button(scr, pygame.Rect(P.x + i * (cw + 4), y, cw, 26), f"{label} {n:,}", tiny, (lambda key=key: set_cl_filter(app, key)),
                   enabled=key != "star" or sel is not None, col=(78, 100, 176) if on else (34, 42, 74), panel=True, selected=on)
    app.button(scr, pygame.Rect(P.right - 108, y, 108, 26), "Settle all", tiny, (lambda: settle_all(app)), enabled=colony_ready(app),
               col=(50, 120, 84), panel=True)
    if auto:
        app.button(scr, pygame.Rect(P.right - 232, y, 120, 26), "Auto-settle: " + ("ON" if g.auto_settle else "off"), tiny,
                   (lambda: setattr(g, "auto_settle", not g.auto_settle)), col=(50, 120, 84) if g.auto_settle else (34, 42, 74), panel=True)
    y += 36
    if app.cl_filter == "star":
        pick = [(sel, i) for i in range(worlds.count_of(sel))]
    else:
        pick = lists[app.cl_filter]
    if not pick:
        msg = {"ready": "Nothing to settle yet.", "settled": "No world settled yet.", "waiting": "Nothing is waiting for a tier."}[app.cl_filter]
        app.txt(scr, sm_f, msg, (P.x + 4, y + 4), (200, 205, 230))
        if app.cl_filter == "ready":
            app.txt(scr, tiny, "Liberate a star in the Galaxy tab: all its worlds can then be settled here.", (P.x + 4, y + 30), (150, 160, 190))
        return y + 60
    first = max(0, int((P.y - y) // CL_ROW) - 1)
    last = min(len(pick), int((P.bottom - y) // CL_ROW) + 2)
    for n in range(first, last):
        draw_colony_row(app, scr, fonts, pygame.Rect(P.x, y + n * CL_ROW, P.w, CL_ROW - 6), *pick[n])
    return y + len(pick) * CL_ROW


def draw_colony_row(app, scr, fonts, r, k, i):
    big, med, sm_f, tiny = fonts
    g = app.g
    w = worlds.planets_of(k)[i]
    site = colonies.site_of(k, i)
    star = galaxy.STARS[k]
    state = g.settle_state(k, i)
    sub = f"{worlds.KIND_NAMES[w['kind']]}  -  {star['name']}, {galaxy.fmt_ly(star['d'])}  -  tier {site['tier']}"
    good, bad = (130, 255, 150), (230, 130, 130)
    first = g.kind_first.get(w["kind"])
    perk = (site["perk"], (170, 175, 205)) if first is None or first == (k, i) else (colonies.NO_PERK, (120, 126, 150))
    rt, ok, fn, dim = None, True, None, False
    pic = site_picture(app, site)
    if state == "settled":
        p = g.colony_planet[(k, i)]
        rt = "YOU ARE HERE" if p == g.cur else "TRAVEL"
        fn = (lambda p=p: app.strip_click(p)) if p != g.cur else None
        line2 = (f"{fmt(g.ore[p])} {site['ore']} stored   (+{fmt(g.s_ops[p])}/s)", (205, 210, 230))
    elif state == "ready":
        pays, cr = g.settle_cost(k, i)
        bits, afford = [], True
        for p, amt in pays:
            okp = p is not None and g.ore[p] >= amt
            afford &= okp
            bits.append(f"{fmt(amt)} {g.sites[p]['ore']}")
        if cr > 0:
            afford &= g.credits >= cr
            bits.append(f"{fmt(cr)} credits")
        line2 = ("cost: " + "  +  ".join(bits), good if afford else bad)
        ok, rt, fn = afford, "SETTLE", (lambda k=k, i=i: g.settle(k, i))
    else:
        t = site["tier"] - 1
        line2 = (f"Needs a planet of tier {t}: {core.SITES[min(t, core.NSOL - 1)]['name']} is one", (230, 190, 130))
        rt, ok, dim = "WAITING", False, True
    if not r.colliderect(PANEL):
        return
    icon = site_picture(app, site, dark=dim)
    app.row(scr, fonts, r, w["name"], sub, rt, f"{core.SITES[min(site['tier'], core.NSOL - 1)]['name']}-class", ok, site["col"], fn, dim=dim,
            icon=icon, lines=[perk, line2], tcol=site["col"] if not dim else (130, 135, 160))


def site_picture(app, site, dark=False):
    """The 50-pixel picture of a world in a list (made once)."""
    key = ("list", site["id"], dark)
    pic = app.art.get(key)
    if pic is None:
        pic = gfx.make_world(site["wkind"], site["seed"], 50, site["ring"])
        if dark:
            pic = pic.copy()
            pic.fill((24, 28, 46, 255), special_flags=pygame.BLEND_RGBA_MULT)
        app.art[key] = pic
    return pic


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
