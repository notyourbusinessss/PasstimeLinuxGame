#!/bin/sh
# Builds the web version, which runs in Safari on an iPhone (and in any other modern browser):
#   ./packaging/build_web.sh        ->  dist/space-miner-<version>-web.zip  (and build/web/, ready to put on any web server)
# It is the game itself, run by Python compiled to WebAssembly (pygbag + pygame-ce). Needs Python 3.9+ and internet access (pygbag
# fetches its page template; the browser fetches the Python runtime from pygbag's CDN when the game is opened).
set -e
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "from version import __version__; print(__version__)")
ROOT=$(pwd)
APP=build/spaceminer                  # (the folder's name is the name of the bundle in the page)

rm -rf "$APP" build/web build/venv-web
mkdir -p "$APP/assets/fonts" dist

# The game (not the balancing tools) and the assets it reads.
for f in *.py; do
    case "$f" in sim.py|calibrate.py) ;; *) cp "$f" "$APP/" ;; esac
done
cp assets/galaxy.json assets/worlds.json assets/milky_way.png assets/icon.png "$APP/assets/"
cp assets/fonts/*.ttf assets/fonts/LICENSE-DejaVu.txt "$APP/assets/fonts/"

python3 -m venv build/venv-web
build/venv-web/bin/pip install -q --upgrade pip
build/venv-web/bin/pip install -q "pygbag==0.9.3"

build/venv-web/bin/pygbag --build --no_opt --title "Space Miner" --icon "$ROOT/assets/icon.png" "$APP"

WEB="$APP/build/web"
test -f "$WEB/index.html"
python3 packaging/web/postprocess.py "$WEB" "$VERSION" assets/icon-512.png
rm -rf build/web && cp -R "$WEB" build/web

rm -f "dist/space-miner-$VERSION-web.zip"
(cd build/web && python3 -c "
import os, sys, zipfile
with zipfile.ZipFile(os.path.join('$ROOT', 'dist', 'space-miner-$VERSION-web.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
    for d, _, names in os.walk('.'):
        for n in sorted(names):
            z.write(os.path.join(d, n), os.path.relpath(os.path.join(d, n), '.'))
")
(cd dist && shasum -a 256 "space-miner-$VERSION-web.zip" > "space-miner-$VERSION-web.zip.sha256" 2>/dev/null || sha256sum "space-miner-$VERSION-web.zip" > "space-miner-$VERSION-web.zip.sha256")
echo
echo "Built dist/space-miner-$VERSION-web.zip ($(du -h "dist/space-miner-$VERSION-web.zip" | cut -f1)); the site itself is in build/web/"
echo "Try it: cd build/web && python3 -m http.server 8000   then open http://localhost:8000 (on a phone: http://<this computer's address>:8000)"
