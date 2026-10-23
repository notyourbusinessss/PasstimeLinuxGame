#!/bin/sh
cd "$(dirname "$0")"
PY=python3
[ -x venv/bin/python ] && PY=venv/bin/python
if ! $PY -c "import pygame" 2>/dev/null; then
    $PY -m pip install --user pygame 2>/dev/null || {      # a Python that refuses to install into itself (Homebrew's, some distros'): use a venv
        python3 -m venv venv && PY=venv/bin/python && $PY -m pip install pygame
    }
fi
exec $PY space_miner.py "$@"
