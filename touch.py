"""Touch input (Android and touch screens): tap, drag-to-scroll with momentum, pinch to zoom the galaxy map.

The game itself is written for a mouse. On a touch screen SDL turns the first finger into mouse events (with
event.touch == True) and also reports raw finger events; this module decides what a gesture means:

* a tap on the side panel is a click, but only on release and only if the finger did not move (so a drag scrolls the
  list instead of buying something); letting go while moving flings the list, which then slows down;
* a drag on the galaxy map pans it, a tap selects a sector, a double-tap zooms in on its front;
* two fingers pinch (and pan) the galaxy map; in the planet view a second finger is simply a second tap, so you can mine
  with several fingers at once;
* a tap on the planet view mines the nearest asteroid (however far away it is).
"""
import math
import time

SLOP = 12                  # pixels a finger may move and still count as a tap
FLING_MAX = 5000.0         # pixels per second


class Touch:
    def __init__(self, app, panel, canvas_size):
        self.app = app
        self.panel = panel                      # the side panel's Rect (it changes in place when the layout does)
        self.canvas_size = canvas_size          # () -> (w, h) of the game canvas
        self.fingers = {}                       # finger id -> (x, y) in canvas pixels
        self.gesture = None                     # the one-finger gesture in progress
        self.pinch = None                       # (previous distance, previous midpoint) while two fingers are down
        self.fling = 0.0
        self.last_t = 0.0

    # ------------------------------------------------------------------ one finger (arrives as a mouse event)
    def down(self, pos):
        app = self.app
        self.fling = 0.0
        if self.pinch:
            return
        g = app.g
        if g.event or (g.crate and g.crate.get("rect") and g.crate["rect"].collidepoint(pos)):
            app.mouse_down(pos, touch=True)
        elif app.panel_visible() and pos[0] >= self.panel.x - 10:
            self.gesture = dict(kind="panel", start=pos, last=pos, moved=False)
            self.last_t = time.monotonic()
        elif app.view == "galaxy" and app.fv.down(pos):
            self.gesture = dict(kind="map", start=pos, last=pos, moved=False)
        else:
            app.mouse_down(pos, touch=True)

    def move(self, pos):
        gs = self.gesture
        if not gs or self.pinch:
            return
        app = self.app
        if not gs["moved"] and math.hypot(pos[0] - gs["start"][0], pos[1] - gs["start"][1]) > SLOP:
            gs["moved"] = True
        if gs["kind"] == "map":
            app.fv.move(pos)
        elif gs["moved"]:
            now = time.monotonic()
            dy = pos[1] - gs["last"][1]
            app.scroll[app.tab] -= dy
            inst = -dy / max(now - self.last_t, 0.008)
            self.fling = max(-FLING_MAX, min(FLING_MAX, 0.6 * self.fling + 0.4 * inst))
            self.last_t = now
        gs["last"] = pos

    def up(self, pos):
        gs, self.gesture = self.gesture, None
        if not gs or self.pinch:
            return
        if gs["kind"] == "map":
            self.app.fv.up(pos)
        elif not gs["moved"]:
            self.fling = 0.0
            self.app.mouse_down(gs["start"], touch=True)
        elif time.monotonic() - self.last_t > 0.12:         # stopped before letting go: no fling
            self.fling = 0.0

    def update(self, dt):
        """Momentum of a flung list."""
        if abs(self.fling) > 30 and self.gesture is None:
            app = self.app
            app.scroll[app.tab] += self.fling * dt
            self.fling *= math.exp(-dt * 5.0)
            if app.scroll[app.tab] <= 0:
                self.fling = 0.0
        else:
            self.fling = 0.0 if self.gesture is None else self.fling

    # ------------------------------------------------------------------ raw fingers (pinch, extra taps)
    def to_canvas(self, x, y, window):
        """Finger events are normalised to the window; the canvas may be scaled and centred inside it."""
        W, H = self.canvas_size()
        ww, wh = window
        scale = min(ww / W, wh / H)
        ox, oy = (ww - W * scale) / 2, (wh - H * scale) / 2
        return (x * ww - ox) / scale, (y * wh - oy) / scale

    def finger(self, kind, fid, x, y, window):
        app = self.app
        pos = self.to_canvas(x, y, window)
        if kind == "down":
            self.fingers[fid] = pos
            if len(self.fingers) == 2:
                if app.view == "galaxy" and not app.g.event:      # a pinch: cancel the first finger's gesture
                    self.gesture = None
                    app.fv.drag = None
                    self.pinch = self.measure()
                elif app.view == "system" and not app.g.event:    # a second finger is a second tap
                    app.mouse_down(pos, touch=True)
        elif kind == "motion" and fid in self.fingers:
            self.fingers[fid] = pos
            if self.pinch and len(self.fingers) == 2:
                d, mid = self.measure()
                d0, mid0 = self.pinch
                if d0 > 8 and d > 8:
                    app.fv.zoom_at(mid, d / d0)
                if app.fv.zt > 1.0:                                # two fingers also pan
                    from frontview import MAPH, MAPW
                    app.fv.xt -= (mid[0] - mid0[0]) / (MAPW * app.fv.zt)
                    app.fv.yt -= (mid[1] - mid0[1]) / (MAPH * app.fv.zt)
                    app.fv.clamp()
                self.pinch = (d, mid)
        elif kind == "up":
            self.fingers.pop(fid, None)
            if len(self.fingers) < 2:
                self.pinch = None

    def measure(self):
        (x1, y1), (x2, y2) = list(self.fingers.values())[:2]
        return math.hypot(x2 - x1, y2 - y1), ((x1 + x2) / 2, (y1 + y2) / 2)
