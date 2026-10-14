"""Logging and crash reports for Space Miner. No pygame here, so the game logic can use it too.

* A rotating log file (space-miner.log) with the important events: start-up details, saves and loads, warps, setting
  changes, warnings and every error with its full traceback.
* faulthandler.log: a Python stack dump if the process dies for a native reason (a segfault in SDL, say).
* crash-<time>.txt: a report written when the game has to stop, with the traceback, a game-state summary,
  the system details and the end of the log.
* An error inside one frame is logged and the game carries on (see report()), so one bug does not end your session.

Find them in ~/.local/state/space-miner/  (the Stats page has a button that opens the folder).
"""
import faulthandler
import logging
import logging.handlers
import os
import platform
import sys
import threading
import time
import traceback

import resources
from version import __version__

LOG = logging.getLogger("space_miner")
LOG.addHandler(logging.NullHandler())

_state = dict(dir=None, fault=None, context=None, seen={}, ready=False)
KEEP_REPORTS = 10


def log_dir():
    return _state["dir"] or resources.log_dir()


def enabled():
    """True when the log files are being written."""
    return _state["dir"] is not None


def log_path():
    return os.path.join(log_dir(), "space-miner.log")


def set_context(fn):
    """fn() returns a short text about the current game state; it is added to every error and crash report."""
    _state["context"] = fn


def context_text():
    fn = _state["context"]
    if not fn:
        return ""
    try:
        return str(fn())
    except Exception as e:                                       # never let the reporting fail
        return f"(could not read the game state: {e!r})"


def setup(debug=False, directory=None):
    """Start logging. Returns the log file path (or None if the folder cannot be written)."""
    if _state["ready"]:
        return log_path()
    LOG.setLevel(logging.DEBUG if debug else logging.INFO)
    LOG.propagate = False
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if debug else logging.WARNING)
    console.setFormatter(logging.Formatter("space-miner: %(levelname)s %(message)s"))
    LOG.addHandler(console)
    d = directory or resources.log_dir()
    try:
        os.makedirs(d, exist_ok=True)
        _state["dir"] = d
        fh = logging.handlers.RotatingFileHandler(os.path.join(d, "space-miner.log"), maxBytes=1_000_000, backupCount=3,
                                                  encoding="utf-8")
        fh.setLevel(logging.DEBUG if debug else logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        LOG.addHandler(fh)
        fpath = os.path.join(d, "faulthandler.log")
        big = os.path.exists(fpath) and os.path.getsize(fpath) > 100_000       # keep it from growing for ever
        fault = open(fpath, "w" if big else "a", encoding="utf-8")
        fault.write(f"\n--- session start {time.strftime('%Y-%m-%d %H:%M:%S')}  Space Miner {__version__} ---\n")
        fault.flush()
        _state["fault"] = fault                                  # keep the file open for the whole run
        faulthandler.enable(file=fault, all_threads=True)
    except OSError as e:
        LOG.warning("Cannot write the log files in %s (%s); logging to the terminal only.", d, e)
        _state["dir"] = None
    sys.excepthook = _excepthook
    threading.excepthook = lambda a: _excepthook(a.exc_type, a.exc_value, a.exc_traceback, "thread")
    _state["ready"] = True
    return log_path() if _state["dir"] else None


def system_info():
    info = [f"Space Miner {__version__}", f"Python {sys.version.split()[0]} ({platform.python_implementation()}) "
            f"{'frozen build' if getattr(sys, 'frozen', False) else 'from source'}",
            f"{platform.system()} {platform.release()} {platform.machine()}", f"argv: {' '.join(sys.argv[1:]) or '-'}"]
    try:
        import pygame
        info.append(f"pygame {pygame.version.ver} (SDL {'.'.join(map(str, pygame.get_sdl_version()))})")
        if pygame.display.get_init():
            info.append(f"video driver: {pygame.display.get_driver()}")
            try:
                info.append(f"desktop: {pygame.display.get_desktop_sizes()}  window: {pygame.display.get_window_size()}"
                            f"  surface: {pygame.display.get_surface().get_size()}")
            except Exception:
                pass
        if pygame.mixer.get_init():
            info.append(f"audio: {pygame.mixer.get_init()}")
        else:
            info.append("audio: not available")
    except Exception as e:
        info.append(f"pygame info unavailable: {e!r}")
    return info


def log_session():
    LOG.info("=" * 60)
    for line in system_info():
        LOG.info(line)
    LOG.info("log folder: %s", log_dir())


def _excepthook(exc_type, exc, tb, where="main"):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    LOG.critical("Uncaught exception (%s):\n%s\n-- game state --\n%s", where,
                 "".join(traceback.format_exception(exc_type, exc, tb)).rstrip(), context_text())
    sys.__excepthook__(exc_type, exc, tb)


def _signature(exc_info):
    et, ev, tb = exc_info
    last = traceback.extract_tb(tb)[-1] if tb else None
    return (et.__name__, last.filename if last else "", last.lineno if last else 0)


def report(where, exc_info=None):
    """Log an exception that happened while the game keeps running. True the first time this particular error is seen
    (so the UI can tell the player once), False for repeats, which are only counted."""
    exc_info = exc_info or sys.exc_info()
    sig = _signature(exc_info)
    n = _state["seen"].get(sig, 0) + 1
    _state["seen"][sig] = n
    if n == 1:
        LOG.error("Error in %s:\n%s\n-- game state --\n%s", where,
                  "".join(traceback.format_exception(*exc_info)).rstrip(), context_text())
        return True
    if n in (10, 100, 1000) or n % 5000 == 0:
        LOG.error("Error in %s repeated %d times: %s: %s", where, n, sig[0], exc_info[1])
    return False


def error_count():
    return sum(_state["seen"].values())


def tail(path, lines=80):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()[-lines:]
    except OSError:
        return []


def write_crash_report(exc_info=None, reason="The game stopped because of repeated errors."):
    """Write crash-<time>.txt next to the log and return its path (None if it could not be written)."""
    exc_info = exc_info or sys.exc_info()
    d = _state["dir"]
    if not d:
        return None
    name = f"crash-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    path = os.path.join(d, name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Space Miner crash report - {time.strftime('%Y-%m-%d %H:%M:%S')}\n{reason}\n\n")
            f.write("== System ==\n" + "\n".join(system_info()) + "\n\n")
            f.write("== Error ==\n" + "".join(traceback.format_exception(*exc_info)) + "\n")
            f.write("== Game state ==\n" + context_text() + "\n\n")
            f.write("== End of the log ==\n" + "".join(tail(log_path(), 60)))
        old = sorted(n for n in os.listdir(d) if n.startswith("crash-") and n.endswith(".txt"))
        for n in old[:-KEEP_REPORTS]:
            os.remove(os.path.join(d, n))
    except OSError:
        return None
    LOG.critical("Crash report written to %s", path)
    return path
