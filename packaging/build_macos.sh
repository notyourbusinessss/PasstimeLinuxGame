#!/bin/sh
# Builds the macOS release: dist/space-miner-<version>-macos-<arch>.dmg (+ .sha256) holding "Space Miner.app"
# (no Python or pygame needed) and a short note on opening it. Run it on a Mac (it needs sips, iconutil, codesign and hdiutil):
#   ./packaging/build_macos.sh
# The app is signed ad hoc, not with an Apple Developer ID, and is not notarized: see the README for the one-time "Open Anyway".
set -e
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "from version import __version__; print(__version__)")
case "$(uname -m)" in
    arm64) ARCH=arm64; MIN_MACOS=11.0 ;;         # the first macOS for Apple Silicon
    x86_64) ARCH=x86_64; MIN_MACOS=10.13 ;;
    *) ARCH=$(uname -m); MIN_MACOS=11.0 ;;
esac
NAME="space-miner-$VERSION-macos-$ARCH"
APP_NAME="Space Miner"
ROOT=$(pwd)

rm -rf build dist
python3 -m venv build/venv
build/venv/bin/pip install -q --upgrade pip
build/venv/bin/pip install -q pygame pyinstaller

# The icon: a .icns made from the 512 pixel picture (the 1024 pixel size is that picture scaled up).
ICONSET="build/SpaceMiner.iconset"
mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
    sips -z $s $s assets/icon-512.png --out "$ICONSET/icon_${s}x${s}.png" > /dev/null
    sips -z $((s * 2)) $((s * 2)) assets/icon-512.png --out "$ICONSET/icon_${s}x${s}@2x.png" > /dev/null
done
iconutil -c icns "$ICONSET" -o build/SpaceMiner.icns

# A windowed one-folder build, which PyInstaller wraps into build/bin/Space Miner.app (a one-file build starts slower and
# PyInstaller no longer supports it for apps).
build/venv/bin/pyinstaller --noconfirm --clean --windowed --name "$APP_NAME" \
    --osx-bundle-identifier io.github.notyourbusinessss.spaceminer \
    --icon "$ROOT/build/SpaceMiner.icns" \
    --distpath build/bin --workpath build/work --specpath build \
    --add-data "$ROOT/assets:assets" \
    --collect-submodules pygame._sdl2 \
    space_miner.py
APP="build/bin/$APP_NAME.app"
test -d "$APP"

# Info.plist: the version shown in Finder, the Games category, and the oldest macOS it is built for.
PLIST="$APP/Contents/Info.plist"
plist_set() {       # plist_set key type value
    /usr/libexec/PlistBuddy -c "Set :$1 $3" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :$1 $2 $3" "$PLIST"
}
plist_set CFBundleShortVersionString string "$VERSION"
plist_set CFBundleVersion string "$VERSION"
plist_set CFBundleDisplayName string "$APP_NAME"
plist_set LSApplicationCategoryType string public.app-category.games
plist_set LSMinimumSystemVersion string "$MIN_MACOS"
plist_set NSHumanReadableCopyright string "Space Miner $VERSION"
plist_set NSHighResolutionCapable bool true

# Sign the whole bundle ad hoc (last, after the changes above). An Apple Silicon Mac will not run unsigned code at all.
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

# The disk image: the app, a shortcut to /Applications to drag it onto, and the note about the first start.
STAGE="build/dmg"
mkdir -p "$STAGE" dist
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp README.md CHANGELOG.md "$STAGE/"
cp assets/fonts/LICENSE-DejaVu.txt "$STAGE/"
cat > "$STAGE/Open Space Miner for the first time.txt" <<'EOF'
Space Miner is free and open source, and this build is not signed with an Apple Developer ID,
so macOS asks you to confirm it the first time:

1. Drag "Space Miner" onto "Applications" in this window.
2. In Applications, hold Control and click "Space Miner" (or right-click it), choose Open, then click Open.
   (On macOS 15 Sequoia or later: double-click it, close the message, then open System Settings >
   Privacy & Security, scroll down to "Space Miner was blocked" and click Open Anyway.)
3. After that it opens like any other app.

If it says the app is damaged, run this once in Terminal:
    xattr -dr com.apple.quarantine "/Applications/Space Miner.app"

Your save is ~/.space_miner_save.json. The log is in ~/Library/Logs/Space Miner.
Full-screen: Cmd+Enter (or F11, or Ctrl+Cmd+F). Cmd+Q quits.
EOF
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "dist/$NAME.dmg" > /dev/null
(cd dist && shasum -a 256 "$NAME.dmg" > "$NAME.dmg.sha256")
echo
echo "Built dist/$NAME.dmg ($(du -h "dist/$NAME.dmg" | cut -f1))"
