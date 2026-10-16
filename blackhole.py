"""The Black Hole Bomb: a megabuild at the Void Throne, the black hole at the middle of the galaxy (Sagittarius A*).

Pure data and logic (no pygame, no core). Once you hold the Void Throne you can visit it: the system view shows the black hole and
nothing else, and the bomb is built round it in five stages, each a megaproject of its own that costs the ore of your richest
tier-11 planet, credits and science. A finished bomb goes off when you Ascend (it is used up): the Stardust of that Ascension is
doubled and the galaxy shakes. An unfinished bomb is lost at the Ascension.

The costs are multiples of the price of the last megaproject (the Comet Catchers): see core.Game.bomb_cost. The five together are
about 4.7 times that price, which is some ten hours of the credit and science income you have when you first beat the Devourer
(measured with sim.py bomb=1).
"""

SD_MULT = 2.0                    # Stardust gain of the Ascension that sets a finished bomb off
TIER = 11                        # the ore the stages are paid in: the richest planet of this economy tier (the Kuiper Belt is one)
STAGES = [
    dict(name="Mirror Shell", mult=0.4, text="A shell of mirrors round the black hole: the light it throws out comes back to it."),
    dict(name="Superradiant Core", mult=0.6, text="A ring of lasers feeds the hole's spin back into the light, which grows with every pass."),
    dict(name="Containment Lattice", mult=0.9, text="Pylons hold the shell together against the light pressing on it from inside."),
    dict(name="Spin-up Rings", mult=1.2, text="Rings of engines drag the hole round faster, until its edge turns at nearly the speed of light."),
    dict(name="Trigger Array", mult=1.6, text="Eight satellites to open the shell at the one moment all that light has to go somewhere."),
]
N = len(STAGES)
NAME = "Black Hole Bomb"


def stage_name(i):
    return STAGES[i]["name"]


def status(built):
    """One line about the bomb for the Ascension screen: (text, armed)."""
    if built >= N:
        return f"{NAME} armed: it goes off when you Ascend. Stardust x{SD_MULT:g}", True
    if built:
        return f"{NAME}: {built} of {N} stages built. An unfinished bomb is lost at the Ascension.", False
    return f"{NAME}: not built (build it at the Void Throne, in the system view).", False
