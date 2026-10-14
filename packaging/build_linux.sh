#!/bin/sh
# Builds the Linux release: dist/space-miner-<version>-linux-<arch>.tar.gz (+ .sha256)
# containing a one-file executable (no Python or pygame needed), an installer, the icon and the docs.
#   ./packaging/build_linux.sh
set -e
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "from version import __version__; print(__version__)")
ARCH=$(uname -m)
NAME="space-miner-$VERSION-linux-$ARCH"
ROOT=$(pwd)

rm -rf build dist
python3 -m venv build/venv
build/venv/bin/pip install -q --upgrade pip
build/venv/bin/pip install -q pygame pyinstaller

build/venv/bin/pyinstaller --noconfirm --clean --onefile --name space-miner \
    --distpath build/bin --workpath build/work --specpath build \
    --add-data "$ROOT/assets:assets" \
    --collect-submodules pygame._sdl2 \
    space_miner.py

STAGE="build/$NAME"
mkdir -p "$STAGE" dist
cp build/bin/space-miner "$STAGE/space-miner"
cp packaging/install.sh packaging/space-miner.desktop "$STAGE/"
cp assets/icon-512.png "$STAGE/space-miner.png"
cp README.md CHANGELOG.md "$STAGE/"
cp assets/fonts/LICENSE-DejaVu.txt "$STAGE/"
tar -C build -czf "dist/$NAME.tar.gz" "$NAME"
(cd dist && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256")
echo
echo "Built dist/$NAME.tar.gz ($(du -h "dist/$NAME.tar.gz" | cut -f1))"
