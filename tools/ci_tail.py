#!/usr/bin/env python3
"""Puts the end of a log file into a GitHub run's annotations (4096 characters each, at most 9), for when the logs themselves cannot be reached.
    python3 tools/ci_tail.py TITLE FILE [LINES]"""
import sys

title, path = sys.argv[1], sys.argv[2]
lines = int(sys.argv[3]) if len(sys.argv) > 3 else 150
try:
    with open(path, errors="replace") as f:
        text = "".join(f.readlines()[-lines:])
except OSError as e:
    text = f"(no {path}: {e})"
chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)][-9:]
for n, chunk in enumerate(chunks):
    print(f"::notice title={title}-{n}::" + chunk.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))
