"""Every planet has its own fleet: different ships with their own names, descriptions and looks.

The eight ship *classes* (Drone, Rig, Barge, Refinery, Foundry, Swarm, Tap, Engine) are the same on every planet, with
the same costs and output, so the balance does not change. What differs is the roster: a Mars "Dune Rover" and a Saturn
"Ring Skipper" are both Drones, but they are built differently, look different and have their own story.
Pure data, no pygame.
"""
CLASSES = ["Drone", "Rig", "Barge", "Refinery", "Foundry", "Swarm", "Tap", "Engine"]

# per planet (same order as core.SITES): hull style (see gfx.SHIP_STYLES), colour tint (None = the classic colours),
# the eight ship names (a plural is made by adding "s") and a one-line description for each
ROSTERS = [
    dict(style="classic", tint=None,                       # Earth
         names=["Mining Drone", "Laser Rig", "Mining Barge", "Refinery Ship", "Orbital Foundry", "Dyson Swarm", "Neutron Tap",
                "Black Hole Engine"],
         blurbs=["A scrappy little miner", "Cuts rock with a focused beam", "Hauls ore by the tonne",
                 "Smelts ore on the way home", "A factory that never lands", "Mirrors that harvest a star",
                 "Drinks from a dead star", "Eats everything, pays in ore"]),
    dict(style="rover", tint=(190, 200, 225),              # Moon
         names=["Dust Crawler", "Regolith Digger", "Lunar Hauler", "Mass-Driver Barge", "Crater Smelter", "Mare Harvester",
                "Helium-3 Siphon", "Tide-Lock Engine"],
         blurbs=["A rover that sifts moondust", "Bites craters for silicon", "Low gravity, heavy loads",
                 "Flings ore into orbit", "A furnace in a crater", "Sweeps the dark seas",
                 "Pumps solar wind from the soil", "Earth's tides, put to work"]),
    dict(style="rover", tint=(235, 120, 75),               # Mars
         names=["Dune Rover", "Canyon Driller", "Ochre Hauler", "Olympus Refinery", "Phobos Foundry", "Dust-Storm Swarm",
                "Valles Tap", "Red Planet Engine"],
         blurbs=["Rolls over rust and dust", "Bores into the canyon walls", "Red dust on every plate",
                 "Smelts copper under the volcano", "Built in the shadow of Phobos", "A storm that mines",
                 "Taps the great canyon", "Terraforming's heavy hammer"]),
    dict(style="balloon", tint=(240, 215, 140),            # Venus
         names=["Cloud Skimmer", "Acid Lance", "Aerostat Barge", "Sulfur Refinery", "Sky Foundry", "Storm Swarm",
                "Pressure Tap", "Deep-Crush Engine"],
         blurbs=["Floats above the burning surface", "A beam that shrugs off acid", "A balloon the size of a town",
                 "Runs on sulfuric rain", "A factory hung from the clouds", "Lightning-fed mining drones",
                 "Mines where steel melts", "Built to survive 90 atmospheres"]),
    dict(style="solar", tint=(255, 205, 90),               # Mercury
         names=["Sunshade Drone", "Solar Lance", "Heat-Sink Barge", "Sunforge Refinery", "Photon Foundry",
                "Sun-Skimmer Swarm", "Flare Tap", "Corona Engine"],
         blurbs=["Hides behind a golden shield", "Burns rock with sunlight", "Carries ore through the heat",
                 "Forges at 400 degrees", "Runs on pure photons", "Dips in and out of the glare",
                 "Rides the solar flares", "Lives inside the Sun's halo"]),
    dict(style="belt", tint=(200, 195, 185),               # Ceres
         names=["Pebble Hopper", "Ice Drill", "Belt Hauler", "Slag Refinery", "Dwarf Foundry", "Belt Swarm",
                "Gravity Tap", "Collapsar Engine"],
         blurbs=["Hops between floating rocks", "Drills through ancient ice", "Tows rocks through the belt",
                 "Melts slag into pure metal", "A factory on a dwarf planet", "A cloud of tiny diggers",
                 "Taps the belt's tugging gravity", "A dying star, caged"]),
    dict(style="storm", tint=(255, 175, 110),              # Jupiter
         names=["Gas Scoop", "Storm Lance", "Ammonia Barge", "Hydrogen Refinery", "Red Spot Foundry", "Moon-Hopper Swarm",
                "Magnetosphere Tap", "Gas Giant Engine"],
         blurbs=["Skims the clouds for fuel", "Cuts through hurricane winds", "Floats on a sea of gas",
                 "Cracks hydrogen for helium-3", "Forges inside a raging storm", "Hops from moon to moon",
                 "Drinks lightning and radiation", "Burns a whole planet's worth"]),
    dict(style="ring", tint=(245, 225, 170),               # Saturn
         names=["Ring Skipper", "Ice-Ring Laser", "Ring Barge", "Cassini Refinery", "Ring Foundry", "Ring Swarm",
                "Titan Tap", "Hex-Storm Engine"],
         blurbs=["Skips over the ring's ice", "Slices ring ice into diamonds", "Hauls glittering ring dust",
                 "Presses carbon into diamond", "Spins diamonds in the ring plane", "Millions of ring-riding drones",
                 "Taps Titan's methane seas", "Harnesses the polar hexagon"]),
    dict(style="ice", tint=(150, 235, 245),                # Uranus
         names=["Frost Drone", "Cryo Lance", "Ice-Giant Barge", "Methane Refinery", "Cold Foundry", "Sideways Swarm",
                "Tilt Tap", "Antimatter Engine"],
         blurbs=["Barely warm enough to move", "A beam from absolute cold", "Slides across a frozen sea",
                 "Makes fuel from methane ice", "Works at minus 220 degrees", "Orbits the sideways planet",
                 "Taps the tilted magnetic field", "Annihilates itself for power"]),
    dict(style="ice", tint=(110, 150, 255),                # Neptune
         names=["Gale Drone", "Deep Lance", "Diamond-Rain Barge", "Crystal Refinery", "Trident Foundry", "Tide Swarm",
                "Triton Tap", "Dark Engine"],
         blurbs=["Rides the fastest winds", "Cuts the deep blue dark", "Catches falling diamonds",
                 "Grows crystals in the dark", "Forges where it never dawns", "Drifts on slow cold tides",
                 "Taps the backwards moon", "Powered by what light can't reach"]),
    dict(style="ice", tint=(225, 200, 255),                # Pluto
         names=["Ice Skipper", "Heart Lance", "Frozen Barge", "Nitrogen Refinery", "Charon Foundry", "Kuiper Swarm",
                "Edge Tap", "Exotic Engine"],
         blurbs=["Skips over nitrogen ice", "Aimed at the glacier's heart", "Drags ore over frozen plains",
                 "Cracks ice into exotic fuel", "A twin world's workshop", "Hunters at the system's edge",
                 "Taps the last sunlight", "Bends space at the edge"]),
    dict(style="xeno", tint=(110, 240, 200),               # Proxima b
         names=["Spore Drone", "Bloom Lance", "Hive Barge", "Quantum Refinery", "Foam Foundry", "Alien Swarm",
                "Red-Dwarf Tap", "Foam Engine"],
         blurbs=["A living seed with an engine", "A beam grown, not built", "A drifting alien hive",
                 "Refines the fabric of space", "Forges bubbles of foam", "Strange minds, many wings",
                 "Drinks the red dwarf's glow", "Turns quantum foam to power"]),
]


def name(p, i):
    return ROSTERS[p]["names"][i]


def blurb(p, i):
    return ROSTERS[p]["blurbs"][i]


def style(p):
    return ROSTERS[p]["style"]


def tint(p):
    return ROSTERS[p]["tint"]


def class_name(i):
    return CLASSES[i]
