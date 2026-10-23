#!/usr/bin/env python3
"""Puts a small picture (a JPEG of about 20 KB) into a GitHub run's annotations as base64 text (4096 characters each, at most 9 per step):
    python3 tools/ci_image.py TITLE FILE [FIRST_CHUNK]       prints chunks FIRST_CHUNK .. FIRST_CHUNK+8 of the picture
Reading them back: join the messages of TITLE-0, TITLE-1... (in order) and base64-decode."""
import base64
import sys

title, path = sys.argv[1], sys.argv[2]
first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
try:
    with open(path, "rb") as f:
        text = base64.b64encode(f.read()).decode()
except OSError as e:
    print(f"::notice title={title}-missing::(no {path}: {e})")
    sys.exit(0)
chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)]
print(f"::notice title={title}-info::{len(chunks)} chunks, {len(text)} characters")
for n in range(first, min(len(chunks), first + 9)):
    print(f"::notice title={title}-{n:02d}::{chunks[n]}")
