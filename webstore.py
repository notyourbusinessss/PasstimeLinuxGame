"""The browser side of the web build (the iPhone version, made with pygbag): the save is kept in the page's localStorage, because the page's own
file system is gone when it is closed, and a few questions to the page (is this a touch screen, how big is the window). Standard library only;
outside a browser nothing here does anything."""
import logging
import os
import sys

WEB = sys.platform == "emscripten"
PREFIX = "space-miner:"                       # the keys in localStorage: PREFIX + the file name
LOG = logging.getLogger("space_miner")


def window():
    """The browser's window object (pygbag's platform module has it), or None when not in a browser."""
    if not WEB:
        return None
    try:
        import platform
        return platform.window
    except (ImportError, AttributeError):
        return None


def persist(path):
    """Copy the file to localStorage (called after every save). Returns True if it was stored."""
    w = window()
    if w is None:
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            w.localStorage.setItem(PREFIX + os.path.basename(path), f.read())
        return True
    except Exception as e:                    # a full or blocked localStorage (private browsing) must not stop the game
        LOG.warning("Could not keep %s in the browser's storage: %s", path, e)
        return False


def restore(directory, names):
    """Put the files kept in localStorage back into the (empty) file system at start-up. Returns the names restored."""
    w = window()
    got = []
    if w is None:
        return got
    for name in names:
        try:
            text = w.localStorage.getItem(PREFIX + name)
            if isinstance(text, str) and text:
                with open(os.path.join(directory, name), "w", encoding="utf-8") as f:
                    f.write(text)
                got.append(name)
        except Exception as e:
            LOG.warning("Could not restore %s from the browser's storage: %s", name, e)
    return got


def forget(name):
    """Remove a file's copy from localStorage."""
    w = window()
    if w is not None:
        try:
            w.localStorage.removeItem(PREFIX + name)
        except Exception:
            pass


def touch_device():
    """True when the main pointer is a finger (a phone or a tablet), or the address ends in ?touch=1 (to try it)."""
    w = window()
    if w is None:
        return False
    try:
        if "touch=1" in str(w.location.search):
            return True
        return bool(w.matchMedia("(pointer: coarse)").matches)
    except Exception:
        return False


def viewport():
    """(width, height) of the page in CSS pixels, or None."""
    w = window()
    if w is None:
        return None
    try:
        width, height = int(w.innerWidth), int(w.innerHeight)
        return (width, height) if width > 0 and height > 0 else None
    except Exception:
        return None
