"""Every planet has its own fleet: different ships with their own names, descriptions and looks.

The ten ship *classes* (Drone, Rig, Barge, Refinery, Foundry, Swarm, Tap, Engine, Citadel, Ark) are the same on every planet,
with the same costs and output. What differs is the roster: a Mars "Dune Rover" and a Saturn "Ring Skipper" are both Drones,
but they are built differently, look different and have their own story. The two biggest classes, Citadel and Ark, are
formations of the planet's own hulls (see gfx.make_ship).
Pure data, no pygame.
"""
import math

CLASSES = ["Drone", "Rig", "Barge", "Refinery", "Foundry", "Swarm", "Tap", "Engine", "Citadel", "Ark"]

# per planet (same order as core.SITES): the ten ship names (a plural is made by adding "s") and a one-line description
# for each
ROSTERS = [
    dict(  # Earth
         names=["Mining Drone", "Laser Rig", "Mining Barge", "Refinery Ship", "Orbital Foundry", "Dyson Swarm", "Neutron Tap",
                "Black Hole Engine", "Star Citadel", "Galaxy Ark"],
         blurbs=["A scrappy little miner", "Cuts rock with a focused beam", "Hauls ore by the tonne",
                 "Smelts ore on the way home", "A factory that never lands", "Mirrors that harvest a star",
                 "Drinks from a dead star", "Eats everything, pays in ore",
                 "A mobile fortress that mines whole belts", "A fleet that never comes home"]),
    dict(  # Moon
         names=["Dust Crawler", "Regolith Digger", "Lunar Hauler", "Mass-Driver Barge", "Crater Smelter", "Mare Harvester",
                "Helium-3 Siphon", "Tide-Lock Engine", "Mare Citadel", "Earthrise Ark"],
         blurbs=["A rover that sifts moondust", "Bites craters for silicon", "Low gravity, heavy loads",
                 "Flings ore into orbit", "A furnace in a crater", "Sweeps the dark seas",
                 "Pumps solar wind from the soil", "Earth's tides, put to work",
                 "A crater base that learned to fly", "Carries a lunar colony to any rock"]),
    dict(  # Mars
         names=["Dune Rover", "Canyon Driller", "Ochre Hauler", "Olympus Refinery", "Phobos Foundry", "Dust-Storm Swarm",
                "Valles Tap", "Red Planet Engine", "Olympus Citadel", "Ares Ark"],
         blurbs=["Rolls over rust and dust", "Bores into the canyon walls", "Red dust on every plate",
                 "Smelts copper under the volcano", "Built in the shadow of Phobos", "A storm that mines",
                 "Taps the great canyon", "Terraforming's heavy hammer",
                 "A volcano-sized fortress on treads", "A rolling city that crosses planets"]),
    dict(  # Venus
         names=["Cloud Skimmer", "Acid Lance", "Aerostat Barge", "Sulfur Refinery", "Sky Foundry", "Storm Swarm",
                "Pressure Tap", "Deep-Crush Engine", "Cloud Citadel", "Storm-Eye Ark"],
         blurbs=["Floats above the burning surface", "A beam that shrugs off acid", "A balloon the size of a town",
                 "Runs on sulfuric rain", "A factory hung from the clouds", "Lightning-fed mining drones",
                 "Mines where steel melts", "Built to survive 90 atmospheres",
                 "A floating city of a hundred balloons", "A hurricane that carries a fleet"]),
    dict(  # Mercury
         names=["Sunshade Drone", "Solar Lance", "Heat-Sink Barge", "Sunforge Refinery", "Photon Foundry",
                "Sun-Skimmer Swarm", "Flare Tap", "Corona Engine", "Sunshield Citadel", "Daybreak Ark"],
         blurbs=["Hides behind a golden shield", "Burns rock with sunlight", "Carries ore through the heat",
                 "Forges at 400 degrees", "Runs on pure photons", "Dips in and out of the glare",
                 "Rides the solar flares", "Lives inside the Sun's halo",
                 "A fortress under a golden shield", "Chases the dawn across the galaxy"]),
    dict(  # Ceres
         names=["Pebble Hopper", "Ice Drill", "Belt Hauler", "Slag Refinery", "Dwarf Foundry", "Belt Swarm",
                "Gravity Tap", "Collapsar Engine", "Belt Citadel", "Rock-Fleet Ark"],
         blurbs=["Hops between floating rocks", "Drills through ancient ice", "Tows rocks through the belt",
                 "Melts slag into pure metal", "A factory on a dwarf planet", "A cloud of tiny diggers",
                 "Taps the belt's tugging gravity", "A dying star, caged",
                 "A hollow asteroid full of furnaces", "A thousand rocks in formation"]),
    dict(  # Jupiter
         names=["Gas Scoop", "Storm Lance", "Ammonia Barge", "Hydrogen Refinery", "Red Spot Foundry", "Moon-Hopper Swarm",
                "Magnetosphere Tap", "Gas Giant Engine", "Great Red Citadel", "Giant's Ark"],
         blurbs=["Skims the clouds for fuel", "Cuts through hurricane winds", "Floats on a sea of gas",
                 "Cracks hydrogen for helium-3", "Forges inside a raging storm", "Hops from moon to moon",
                 "Drinks lightning and radiation", "Burns a whole planet's worth",
                 "Lives in the eye of a storm", "A fleet with its own weather"]),
    dict(  # Saturn
         names=["Ring Skipper", "Ice-Ring Laser", "Ring Barge", "Cassini Refinery", "Ring Foundry", "Ring Swarm",
                "Titan Tap", "Hex-Storm Engine", "Ring Citadel", "Ring-Lord Ark"],
         blurbs=["Skips over the ring's ice", "Slices ring ice into diamonds", "Hauls glittering ring dust",
                 "Presses carbon into diamond", "Spins diamonds in the ring plane", "Millions of ring-riding drones",
                 "Taps Titan's methane seas", "Harnesses the polar hexagon",
                 "A fortress built into the ring", "A whole ring system in formation"]),
    dict(  # Uranus
         names=["Frost Drone", "Cryo Lance", "Ice-Giant Barge", "Methane Refinery", "Cold Foundry", "Sideways Swarm",
                "Tilt Tap", "Antimatter Engine", "Frost Citadel", "Glacier Ark"],
         blurbs=["Barely warm enough to move", "A beam from absolute cold", "Slides across a frozen sea",
                 "Makes fuel from methane ice", "Works at minus 220 degrees", "Orbits the sideways planet",
                 "Taps the tilted magnetic field", "Annihilates itself for power",
                 "A fortress of frozen glass", "A drifting iceberg of a fleet"]),
    dict(  # Neptune
         names=["Gale Drone", "Deep Lance", "Diamond-Rain Barge", "Crystal Refinery", "Trident Foundry", "Tide Swarm",
                "Triton Tap", "Dark Engine", "Abyss Citadel", "Leviathan Ark"],
         blurbs=["Rides the fastest winds", "Cuts the deep blue dark", "Catches falling diamonds",
                 "Grows crystals in the dark", "Forges where it never dawns", "Drifts on slow cold tides",
                 "Taps the backwards moon", "Powered by what light can't reach",
                 "A fortress at the bottom of the sky", "The deep fleet that never surfaces"]),
    dict(  # Pluto
         names=["Ice Skipper", "Heart Lance", "Frozen Barge", "Nitrogen Refinery", "Charon Foundry", "Kuiper Swarm",
                "Edge Tap", "Exotic Engine", "Heartland Citadel", "Edge Ark"],
         blurbs=["Skips over nitrogen ice", "Aimed at the glacier's heart", "Drags ore over frozen plains",
                 "Cracks ice into exotic fuel", "A twin world's workshop", "Hunters at the system's edge",
                 "Taps the last sunlight", "Bends space at the edge",
                 "A fortress on the nitrogen glacier", "The last fleet at the edge of the Sun"]),
    dict(  # Proxima b
         names=["Spore Drone", "Bloom Lance", "Hive Barge", "Quantum Refinery", "Foam Foundry", "Alien Swarm",
                "Red-Dwarf Tap", "Foam Engine", "Bloom Citadel", "Spore Ark"],
         blurbs=["A living seed with an engine", "A beam grown, not built", "A drifting alien hive",
                 "Refines the fabric of space", "Forges bubbles of foam", "Strange minds, many wings",
                 "Drinks the red dwarf's glow", "Turns quantum foam to power",
                 "A fortress grown like a flower", "Seeds a thousand worlds"]),
]

# How each planet's ships look and move. style: the hull family drawn by shipart.py; pal: the colours (hull, shade, trim,
# glow); scale: sprite size factor; motion: how they fly round the planet (see orbit()).
LOOKS = [
    dict(style="classic", pal=None, scale=1.0, motion="orbit"),                                       # Earth
    dict(style="lander", pal=((176, 182, 198), (106, 112, 132), (238, 242, 252), (200, 225, 255)),
         scale=1.15, motion="hop"),                                                                   # Moon
    dict(style="rover", pal=((184, 86, 54), (112, 48, 34), (255, 178, 122), (255, 120, 70)),
         scale=1.0, motion="crawl"),                                                                  # Mars
    dict(style="airship", pal=((240, 232, 170), (196, 150, 70), (255, 252, 214), (255, 236, 130)),
         scale=1.2, motion="float"),                                                                  # Venus
    dict(style="solar", pal=((44, 44, 62), (74, 70, 96), (255, 200, 70), (255, 170, 40)),
         scale=1.1, motion="swing"),                                                                  # Mercury
    dict(style="rock", pal=((122, 112, 102), (74, 68, 64), (200, 190, 178), (170, 225, 255)),
         scale=1.1, motion="scatter"),                                                                # Ceres
    dict(style="storm", pal=((214, 142, 82), (112, 58, 40), (248, 222, 184), (255, 140, 70)),
         scale=1.15, motion="spiral"),                                                                # Jupiter
    dict(style="ringed", pal=((228, 208, 152), (152, 132, 94), (255, 246, 208), (255, 232, 150)),
         scale=1.25, motion="ring"),                                                                  # Saturn
    dict(style="crystal", pal=((122, 214, 228), (64, 140, 162), (228, 255, 255), (170, 255, 255)),
         scale=1.15, motion="polar"),                                                                  # Uranus
    dict(style="deep", pal=((38, 66, 172), (20, 34, 112), (112, 162, 255), (80, 210, 255)),
         scale=1.25, motion="weave"),                                                                  # Neptune
    dict(style="sled", pal=((208, 186, 222), (142, 118, 162), (255, 246, 255), (255, 170, 212)),
         scale=1.1, motion="drift"),                                                                 # Pluto
    dict(style="spore", pal=((40, 152, 122), (20, 92, 82), (150, 255, 206), (255, 90, 170)),
         scale=1.15, motion="eight"),                                                                 # Proxima b
]
for _r, _look in zip(ROSTERS, LOOKS):
    _r.update(_look)


def name(p, i):
    return ROSTERS[p]["names"][i]


def blurb(p, i):
    return ROSTERS[p]["blurbs"][i]


def style(p):
    return ROSTERS[p]["style"]


def palette(p):
    """(hull, shade, trim, glow) colours of the planet's ships, or None for the classic Earth colours."""
    return ROSTERS[p]["pal"]


def scale(p):
    return ROSTERS[p]["scale"]


def motion(p):
    return ROSTERS[p]["motion"]


def class_name(i):
    return CLASSES[i]


def shown(p, owned):
    """How many ships of a class are drawn round the planet (the rest are only counted)."""
    return min(owned, 2 if ROSTERS[p]["motion"] == "crawl" else 4)


def orbit(p, i, j, n, t, d):
    """Where ship j of the n of class i is round planet p at time t, relative to the planet's centre (in pixels):
    (dx, dy, depth). depth > 0 means in front of the planet. Every planet's ships fly differently: Moon landers hop,
    Mars rovers drive over the planet's face, Venus airships float, Mercury ships swing round on a lopsided orbit...
    d is 1 or -1 (the direction the class circles in)."""
    m = ROSTERS[p]["motion"]
    rad = 82 + i * 7
    spd = 0.65 - i * 0.04
    ph = j * math.tau / n + i                                # where on its orbit this ship starts
    if m == "hop":
        a = t * spd * .85 * d + ph
        hop = abs(math.sin(t * 1.7 + j * 1.9 + i))
        r = rad * (1 + .06 * hop)
        return math.cos(a) * r, math.sin(a) * r * .7 - hop * 16, math.sin(a)
    if m == "crawl":                                         # drives over the planet itself
        a = t * spd * .55 * d + ph
        r = 14 + i * 5.4
        return math.cos(a) * r, math.sin(a) * r * .88, 1.0
    if m == "float":
        a = t * spd * .5 * d + ph
        r = rad * (1 + .07 * math.sin(t * .6 + j * 2 + i))
        return math.cos(a) * r, math.sin(a) * r * .7 + 10 * math.sin(t * 1.1 + j * 2.3 + i), math.sin(a)
    if m == "swing":                                         # an eccentric orbit: fast and close, then slow and far
        e = .32
        mean = t * spd * 1.25 * d + ph
        nu = mean + 2 * e * math.sin(mean) + 1.25 * e * e * math.sin(2 * mean)
        r = rad * 1.05 * (1 - e * e) / (1 + e * math.cos(nu))
        return math.cos(nu) * r, math.sin(nu) * r * .7, math.sin(nu)
    if m == "scatter":                                       # rocks tumbling about
        a = t * spd * .8 * d + ph + .4 * math.sin(t * .5 + j * 4.1 + i)
        r = rad * (1 + .16 * math.sin(t * .8 + j * 3.3 + i * 1.3))
        return math.cos(a) * r, math.sin(a) * r * .7, math.sin(a)
    if m == "spiral":                                        # breathing in and out like a storm
        a = t * spd * 1.1 * d + ph
        r = rad * (.72 + .3 * (.5 + .5 * math.sin(t * .4 + j * 2 + i)))
        return math.cos(a) * r, math.sin(a) * r * .7, math.sin(a)
    if m == "ring":                                          # all in one flat, tilted plane
        a = t * spd * .7 * d + ph
        r = 74 + i * 5
        x, y = math.cos(a) * r, math.sin(a) * r * .24
        return x * math.cos(-.3) - y * math.sin(-.3), x * math.sin(-.3) + y * math.cos(-.3), math.sin(a)
    if m == "polar":                                         # over the poles, round the sideways planet
        a = t * spd * .9 * d + ph
        return math.cos(a) * rad * .36, math.sin(a) * rad * .95, math.cos(a)
    if m == "weave":
        a = t * spd * .75 * d + ph
        r = rad * (1 + .1 * math.sin(a * 3 + t * .5))
        return math.cos(a) * r, math.sin(a) * r * .7, math.sin(a)
    if m == "drift":                                         # slow, wide and lonely
        a = t * spd * .4 * d + ph
        return math.cos(a) * rad * 1.15, math.sin(a) * rad * .9, math.sin(a)
    if m == "eight":                                         # a figure of eight that crosses over the planet
        a = t * spd * .8 * d + ph
        return math.sin(a) * rad * 1.1, math.sin(a) * math.cos(a) * rad * .95, math.cos(a)
    return math.cos(t * spd * d + ph) * rad, math.sin(t * spd * d + ph) * rad * .7, math.sin(t * spd * d + ph)


def heading(p, i, j, n, t, d):
    """The direction (radians, screen coordinates) the ship is flying in."""
    x0, y0, _ = orbit(p, i, j, n, t, d)
    x1, y1, _ = orbit(p, i, j, n, t + .1, d)
    return math.atan2(y1 - y0, x1 - x0)
