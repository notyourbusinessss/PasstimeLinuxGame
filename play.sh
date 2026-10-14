#!/bin/sh
cd "$(dirname "$0")"
python3 -c "import pygame" 2>/dev/null || pip install --user pygame
exec python3 space_miner.py
