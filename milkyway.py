"""The shape of the Milky Way, as the game uses it (pure maths, no pygame): where the stars are dense and where the arms run.

Coordinates are light-years, centred on the Galactic Centre, x to the right and y down: the Sun is at (0, GC_DIST), at the
bottom of the map. tools/make_galaxy.py uses this to place the generated systems, gfx.py to paint the galaxy.
"""
import math

GC_DIST = 26670.0                    # light-years from the Sun to Sagittarius A*
PITCH = 0.21                         # tan of the arms' pitch angle (about 12 degrees)
ARM_R = [11500.0 * 1.39 ** k for k in range(4)]          # where each arm crosses the line from the centre to the Sun
ARM_NAMES = ["Norma Arm", "Scutum-Centaurus Arm", "Sagittarius Arm", "Perseus Arm"]
ARM_WEIGHT = [0.55, 1.0, 0.6, 1.0]                      # the two major arms are brighter than the two minor ones

def from_map(x, y):
    return GC_DIST - y, -x                 # galactic X (towards the centre), Y (the way the Sun moves)


def longitude(x, y):
    """Galactic longitude (0..360) of a map position as seen from the Sun."""
    X, Y = from_map(x, y)
    return math.degrees(math.atan2(Y, X)) % 360.0


# ------------------------------------------------------------------ the shape of the galaxy
def arm_strength(x, y):
    """(0..1 how close the point is to a spiral arm, index of the nearest arm)."""
    R = math.hypot(x, y)
    if R < 1500:
        return 0.0, -1
    a = math.atan2(x, y)
    best, which = 0.0, -1
    for k, rk in enumerate(ARM_R):
        arm_a = math.log(R / rk) / PITCH
        d = (a - arm_a + math.pi) % math.tau - math.pi
        perp = R * abs(d) * 0.208
        s = ARM_WEIGHT[k] * math.exp(-(perp / 1900.0) ** 2)
        if s > best:
            best, which = s, k
    return best, which


def bar_strength(x, y):
    ang = math.radians(27.0)
    u = x * -math.sin(ang) + y * math.cos(ang)
    v = x * math.cos(ang) + y * math.sin(ang)
    return math.exp(-(u / 6500.0) ** 2 - (v / 1500.0) ** 2)


def density(x, y):
    R = math.hypot(x, y)
    if R > 52000:
        return 0.0
    arm, _ = arm_strength(x, y)
    disc = math.exp(-R / 10000.0)
    bulge = 2.4 * math.exp(-(R / 2600.0) ** 2)
    spur = 0.9 * math.exp(-((x / 3800.0) ** 2 + ((y - GC_DIST) / 900.0) ** 2))      # the Orion Spur: a short arm segment through the Sun
    edge = 1.0 if R < 44000 else max(0.0, 1.0 - (R - 44000) / 8000.0)
    return (disc * (0.08 + 1.0 * arm) + bulge + 1.2 * bar_strength(x, y) + spur) * edge


def region_of(x, y):
    R = math.hypot(x, y)
    if R < 3200:
        return "Galactic Bulge"
    if bar_strength(x, y) > 0.35:
        return "Galactic Bar"
    if abs(x) < 4200 and abs(y - GC_DIST) < 1400:
        return "Orion Spur"
    arm, which = arm_strength(x, y)
    if arm > 0.3 and which >= 0:
        return ARM_NAMES[which]
    if R > 38000:
        return "Outer Rim"
    return "Inter-arm space"


