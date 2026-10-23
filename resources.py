"""Where the game finds its files: bundled assets (also inside a PyInstaller build) and the save file. No pygame here."""
import os
import sys

ANDROID = "ANDROID_ARGUMENT" in os.environ          # set by python-for-android
WEB = sys.platform == "emscripten"                  # running in a browser (the pygbag build: Safari on an iPhone, any other browser)
TOUCH = ANDROID                                     # touch-screen user interface (--touch turns it on for testing on a desktop; a touch screen turns it on in a browser)


def base_dir():
    if getattr(sys, "frozen", False):               # a PyInstaller build unpacks its data into sys._MEIPASS
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource(rel):
    """Absolute path of a bundled file, e.g. resource("assets/icon.png")."""
    return os.path.join(base_dir(), *rel.split("/"))


def save_path():
    """The save file: ~/.space_miner_save.json (the app's private folder on Android)."""
    if ANDROID:
        return os.path.join(os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~")), ".space_miner_save.json")
    if WEB:
        return "/tmp/.space_miner_save.json"        # (webstore keeps a copy of it in the browser's localStorage)
    return os.path.expanduser("~/.space_miner_save.json")


def log_dir():
    """Where the log and crash reports go: ~/.local/state/space-miner (the app's private folder on Android,
    ~/Library/Logs/Space Miner on a Mac, where the Console app looks)."""
    if ANDROID:
        return os.path.join(os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~")), "logs")
    if WEB:
        return "/tmp/space-miner"                   # (the page's file system is gone when it closes; the log is for the browser's console)
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Logs/Space Miner")
    state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(state, "space-miner")
