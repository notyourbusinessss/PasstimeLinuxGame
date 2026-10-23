"""A kivy-ios recipe for pygame (kivy-ios builds Python and SDL2 for iOS, but has no pygame).

pygame is built from its source package like Pillow is in kivy-ios: its own setup.py, told by a hand-made "Setup" file which modules to
build (no automatic search for SDL, which cannot work when cross compiling), run by the host Python with the iOS compiler. Every module
ends up as an object file in libpygame.a, which the app links in; the launcher finds them again by their init functions, which
the recipe renames where they would clash with a module of Python itself (math, time).

Use: copy this folder into kivy_ios/recipes (build_ios.sh does), then: toolchain build python3 sdl2 sdl2_image sdl2_mixer sdl2_ttf libpng pygame
"""
import os

from kivy_ios.toolchain import CythonRecipe

# The modules pygame needs (and the game uses). Left out on purpose: the _sdl2 helpers, freetype, gfxdraw, scrap, midi and camera.
SETUP = """\
SDL = -D_REENTRANT -DSDL2
FONT =
IMAGE =
MIXER =
PNG =
DEBUG =

base src_c/base.c $(SDL) $(DEBUG)
color src_c/color.c $(SDL) $(DEBUG)
constants src_c/constants.c $(SDL) $(DEBUG)
display src_c/display.c $(SDL) $(DEBUG)
event src_c/event.c $(SDL) $(DEBUG)
key src_c/key.c $(SDL) $(DEBUG)
mouse src_c/mouse.c $(SDL) $(DEBUG)
rect src_c/rect.c $(SDL) $(DEBUG)
rwobject src_c/rwobject.c $(SDL) $(DEBUG)
surface src_c/surface.c src_c/alphablit.c src_c/surface_fill.c $(SDL) $(DEBUG)
surflock src_c/surflock.c $(SDL) $(DEBUG)
joystick src_c/joystick.c $(SDL) $(DEBUG)
draw src_c/draw.c $(SDL) $(DEBUG)
image src_c/image.c $(SDL) $(DEBUG)
transform src_c/transform.c src_c/rotozoom.c src_c/scale2x.c src_c/scale_mmx.c $(SDL) $(DEBUG) -D_NO_MMX_FOR_X86_64
mask src_c/mask.c src_c/bitmask.c $(SDL) $(DEBUG)
bufferproxy src_c/bufferproxy.c $(SDL) $(DEBUG)
pixelarray src_c/pixelarray.c $(SDL) $(DEBUG)
pixelcopy src_c/pixelcopy.c $(SDL) $(DEBUG)
newbuffer src_c/newbuffer.c $(SDL) $(DEBUG)
_sprite src_c/_sprite.c $(SDL) $(DEBUG)
font src_c/font.c $(SDL) $(FONT) $(DEBUG)
mixer src_c/mixer.c $(SDL) $(MIXER) $(DEBUG)
mixer_music src_c/music.c $(SDL) $(MIXER) $(DEBUG)
imageext src_c/imageext.c $(SDL) $(IMAGE) $(PNG) $(DEBUG)

# Python has its own math and time (inside the app), so the init functions of these two must have other names. The launcher
# first looks for PyInit_pygame_<module>, so that is what they are called. (distutils drops the first character after the = of a
# -D in a Setup file, hence the two =.)
math src_c/math.c $(SDL) $(DEBUG) -DPyInit_math==PyInit_pygame_math
time src_c/time.c $(SDL) $(DEBUG) -DPyInit_time==PyInit_pygame_time
"""

# pygame's header defines the pointers to the C interfaces of its modules in every file that uses them (void **_PGSLOTS_base = NULL;). That is fine
# when every module is a library of its own, but they all end up in one program here: as weak definitions they become one pointer each.
SLOTS_OLD = "#define PYGAMEAPI_DEFINE_SLOTS(module) void **_PGSLOTS_##module = NULL"
SLOTS_NEW = "#define PYGAMEAPI_DEFINE_SLOTS(module) __attribute__((weak)) void **_PGSLOTS_##module = NULL"


class PygameRecipe(CythonRecipe):
    version = "2.6.1"
    url = "https://files.pythonhosted.org/packages/49/cc/08bba60f00541f62aaa252ce0cfbd60aebd04616c0b9574f755b583e45ae/pygame-{version}.tar.gz"
    library = "libpygame.a"
    depends = ["hostpython3", "python3", "sdl2", "sdl2_image", "sdl2_mixer", "sdl2_ttf", "libpng"]
    pbx_libraries = ["libz"]
    cythonize = False                        # (the sdist has the C files of the Cython modules, and those are left out anyway)

    def prebuild_platform(self, plat):
        if self.has_marker("configured"):
            return
        with open("Setup", "w") as f:        # setup.py takes it instead of searching for SDL and the other libraries
            f.write(SETUP)
        header = os.path.join("src_c", "include", "pgimport.h")
        with open(header) as f:
            text = f.read()
        assert SLOTS_OLD in text, "pygame's pgimport.h is not what this recipe expects (is it still pygame 2.6.1?)"
        with open(header, "w") as f:
            f.write(text.replace(SLOTS_OLD, SLOTS_NEW))
        self.set_marker("configured")

    def get_recipe_env(self, plat):
        env = super().get_recipe_env(plat)
        env["PATH"] = os.environ["PATH"]
        return env


recipe = PygameRecipe()
