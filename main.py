"""Entry point for the Android build (python-for-android starts main.py) and the web build (pygbag runs it in the browser). On a desktop it does the
same as space_miner.py."""
# /// script
# dependencies = [
#     "pygame-ce",
# ]
# ///
import asyncio  # noqa: F401  (pygbag reads the imports of this file to know what to load)
import pygame  # noqa: F401

import space_miner

space_miner.main()
