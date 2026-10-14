"""Tiny procedural sound effects (no audio files). Everything is synthesised at start-up."""
import array
import math
import random
import time

import pygame

RATE = 22050


def synth(segments, vol=0.5, wave="sine"):
    """segments: list of (start_hz, end_hz, seconds). Returns signed 16-bit samples."""
    out = array.array("h")
    phase = 0.0
    for f0, f1, dur in segments:
        n = int(RATE * dur)
        for i in range(n):
            t = i / max(1, n)
            f = f0 + (f1 - f0) * t
            phase += 2 * math.pi * f / RATE
            if wave == "noise":
                s = random.uniform(-1, 1)
            elif wave == "bell":
                s = 0.7 * math.sin(phase) + 0.25 * math.sin(phase * 2.01) + 0.1 * math.sin(phase * 3.02)
            else:
                s = math.sin(phase)
            env = min(1.0, i / (RATE * 0.004)) * (1 - t) ** 1.4
            out.append(int(32767 * vol * env * s))
    return out


class Sounds:
    """settings is the game's settings dict ({'sound': bool, 'volume': 0..1}); it is read on every play()."""

    def __init__(self, settings):
        self.settings = settings
        self.ok = False
        self.snd = {}
        self.last = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 1, 512)
            self.ok = True
        except Exception:
            return
        defs = {
            "click": ([(760, 480, 0.05)], 0.22, "sine"),
            "buy": ([(520, 520, 0.05), (780, 780, 0.09)], 0.3, "sine"),
            "unlock": ([(392, 392, 0.1), (523, 523, 0.1), (659, 659, 0.1), (784, 784, 0.3)], 0.35, "bell"),
            "project": ([(262, 262, 0.14), (330, 330, 0.14), (392, 392, 0.14), (523, 523, 0.45)], 0.38, "bell"),
            "ach": ([(784, 784, 0.07), (988, 988, 0.07), (1175, 1175, 0.07), (1568, 1568, 0.35)], 0.33, "bell"),
            "crate": ([(900, 1400, 0.1), (1400, 1900, 0.16)], 0.28, "sine"),
            "warp": ([(90, 1400, 0.9)], 0.3, "sine"),
            "travel": ([(380, 90, 0.7)], 0.25, "sine"),
            "event": ([(440, 440, 0.1), (330, 330, 0.18)], 0.3, "bell"),
            "win": ([(392, 392, 0.12), (523, 523, 0.12), (659, 659, 0.12), (784, 784, 0.12), (1047, 1047, 0.5)], 0.36, "bell"),
            "lose": ([(330, 330, 0.2), (262, 262, 0.2), (196, 196, 0.5)], 0.32, "sine"),
            "raid": ([(880, 880, 0.1), (660, 660, 0.1), (880, 880, 0.1), (660, 660, 0.1)], 0.28, "sine"),
        }
        for name, (segs, vol, wave) in defs.items():
            try:
                self.snd[name] = pygame.mixer.Sound(buffer=synth(segs, vol, wave).tobytes())
            except Exception:
                pass

    def play(self, name):
        if not self.ok or not self.settings.get("sound", True):
            return
        s = self.snd.get(name)
        if s is None:
            return
        now = time.time()
        if now - self.last.get(name, 0) < (0.04 if name == "click" else 0.12):
            return
        self.last[name] = now
        s.set_volume(max(0.0, min(1.0, self.settings.get("volume", 0.6))))
        s.play()
