"""Where the game finds its files: bundled assets (also inside a PyInstaller build) and the save file. No pygame here."""
import os
import sys

ANDROID = "ANDROID_ARGUMENT" in os.environ          # set by python-for-android


def is_ios(environ=os.environ, platform=sys.platform):
    """True in the iPhone app: Python 3.13 and later say so, and the launcher of the app (kivy-ios) sets KIVY_BUILD."""
    return platform == "ios" or environ.get("KIVY_BUILD") == "ios" or environ.get("SPACE_MINER_IOS") == "1"


IOS = is_ios()
MOBILE = ANDROID or IOS                             # a phone or tablet app: always fullscreen, scaled to the screen, no window to drag
TOUCH = MOBILE                                      # touch-screen user interface (--touch turns it on for testing on a desktop)


def base_dir():
    if getattr(sys, "frozen", False):               # a PyInstaller build unpacks its data into sys._MEIPASS
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource(rel):
    """Absolute path of a bundled file, e.g. resource("assets/icon.png")."""
    return os.path.join(base_dir(), *rel.split("/"))


def save_path():
    """The save file: ~/.space_miner_save.json (the app's private folder on Android, its Documents folder on an iPhone)."""
    if ANDROID:
        return os.path.join(os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~")), ".space_miner_save.json")
    if IOS:
        return os.path.join(os.path.expanduser("~"), "Documents", ".space_miner_save.json")
    return os.path.expanduser("~/.space_miner_save.json")


def log_dir():
    """Where the log and crash reports go: ~/.local/state/space-miner (the app's private folder on Android,
    ~/Library/Logs/Space Miner on a Mac, where the Console app looks, and in the iPhone app)."""
    if ANDROID:
        return os.path.join(os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~")), "logs")
    if sys.platform == "darwin" or IOS:
        return os.path.expanduser("~/Library/Logs/Space Miner")
    state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(state, "space-miner")
