#!/bin/sh
# Builds the iPhone app with kivy-ios (Python and SDL2 for iOS) and the pygame recipe in recipes/pygame next to this file. It needs a Mac with Xcode:
#   ./packaging/ios/build_ios.sh [toolchain|project|simulator|device|all]       (default: all)
#     toolchain  Python, SDL2 and pygame for iOS (about 30 minutes the first time; build/ios/{build,dist,.cache} are kept for the next run)
#     project    the Xcode project (build/ios/spaceminer-ios) with the game, its assets, the icon and the Info.plist
#     simulator  builds the app for the iOS Simulator (build/ios/dd-sim/.../spaceminer.app)
#     device     builds it for a phone, unsigned, and packs dist/space-miner-<version>-ios-unsigned.ipa
# The .ipa is NOT signed: Apple only runs signed apps, so it has to be signed on its way to your phone (AltStore or Sideloadly with a free
# Apple ID, which lasts 7 days at a time, or Xcode / TestFlight with a paid Apple Developer account). See the README.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
VERSION=$(python3 -c "from version import __version__; print(__version__)")
WORK="$ROOT/build/ios"
APPSRC="$WORK/app"
PROJ="$WORK/spaceminer-ios"
PLIST="$PROJ/spaceminer-Info.plist"
BUNDLE_ID="io.github.notyourbusinessss.spaceminer"
case "$(uname -m)" in arm64) SIM_ARCH=arm64 ;; *) SIM_ARCH=x86_64 ;; esac
mkdir -p "$WORK" "$ROOT/dist"
STEP=${1:-all}

step_toolchain() {
    # The pygame recipe goes next to the recipes of kivy-ios (as a "custom" recipe it would be left out of the Xcode project).
    RECIPES=$(python3 -c "import kivy_ios, os; print(os.path.join(os.path.dirname(kivy_ios.__file__), 'recipes'))")
    rm -rf "$RECIPES/pygame" && cp -R "$ROOT/packaging/ios/recipes/pygame" "$RECIPES/pygame"
    cd "$WORK"
    toolchain clean pygame || true                             # (always rebuilt: it is quick, and the recipe may have changed)
    toolchain build python3 sdl2 sdl2_image sdl2_mixer sdl2_ttf libpng pygame
}

step_project() {
    cd "$ROOT"
    rm -rf "$APPSRC" "$PROJ"
    mkdir -p "$APPSRC/assets/fonts"
    for f in *.py; do
        case "$f" in sim.py|calibrate.py|main.py) ;; *) cp "$f" "$APPSRC/" ;; esac
    done
    cp packaging/ios/main.py "$APPSRC/main.py"
    cp assets/galaxy.json assets/worlds.json assets/milky_way.png assets/icon.png "$APPSRC/assets/"
    cp assets/fonts/*.ttf assets/fonts/LICENSE-DejaVu.txt "$APPSRC/assets/fonts/"
    cd "$WORK"
    toolchain create SpaceMiner "$APPSRC"
    # Info.plist: the name, the id, the version, landscape only (the game is played sideways), no status bar, the Games category
    PB=/usr/libexec/PlistBuddy
    for key in CFBundleDisplayName CFBundleIdentifier CFBundleShortVersionString CFBundleVersion; do
        case "$key" in
            CFBundleDisplayName) value="Space Miner" ;;
            CFBundleIdentifier) value="$BUNDLE_ID" ;;
            *) value="$VERSION" ;;
        esac
        $PB -c "Set :$key $value" "$PLIST"
    done
    for key in UISupportedInterfaceOrientations "UISupportedInterfaceOrientations~ipad"; do
        $PB -c "Delete :$key" "$PLIST" 2> /dev/null || true
        $PB -c "Add :$key array" -c "Add :$key:0 string UIInterfaceOrientationLandscapeRight" -c "Add :$key:1 string UIInterfaceOrientationLandscapeLeft" "$PLIST"
    done
    $PB -c "Add :UIRequiresFullScreen bool true" "$PLIST" || true
    $PB -c "Add :UIViewControllerBasedStatusBarAppearance bool false" "$PLIST" || true
    $PB -c "Add :LSApplicationCategoryType string public.app-category.games" "$PLIST" || true
    $PB -c "Add :ITSAppUsesNonExemptEncryption bool false" "$PLIST" || true
    # the icon (the toolchain makes every size from one picture)
    sips -z 1024 1024 "$ROOT/assets/icon-512.png" --out "$WORK/icon-1024.png" > /dev/null
    toolchain icon "$PROJ" "$WORK/icon-1024.png" || echo "WARNING: could not make the icon set"
    echo "Project ready: $PROJ"
}

step_simulator() {
    xcodebuild -project "$PROJ/spaceminer.xcodeproj" -scheme spaceminer -configuration Release \
        -destination "generic/platform=iOS Simulator" -derivedDataPath "$WORK/dd-sim" \
        ARCHS=$SIM_ARCH ONLY_ACTIVE_ARCH=NO CODE_SIGNING_ALLOWED=NO build
    ls -d "$WORK"/dd-sim/Build/Products/Release-iphonesimulator/*.app
}

step_device() {
    xcodebuild -project "$PROJ/spaceminer.xcodeproj" -scheme spaceminer -configuration Release \
        -destination "generic/platform=iOS" -derivedDataPath "$WORK/dd-device" \
        CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO build
    APP=$(ls -d "$WORK"/dd-device/Build/Products/Release-iphoneos/*.app | head -1)
    test -d "$APP"
    rm -rf "$WORK/ipa" && mkdir -p "$WORK/ipa/Payload"
    cp -R "$APP" "$WORK/ipa/Payload/"
    OUT="$ROOT/dist/space-miner-$VERSION-ios-unsigned.ipa"
    rm -f "$OUT"
    (cd "$WORK/ipa" && zip -qry "$OUT" Payload)
    (cd "$ROOT/dist" && shasum -a 256 "$(basename "$OUT")" > "$(basename "$OUT").sha256")
    echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
}

case "$STEP" in
    toolchain) step_toolchain ;;
    project) step_project ;;
    simulator) step_simulator ;;
    device) step_device ;;
    all) step_toolchain; step_project; step_simulator; step_device ;;
    *) echo "usage: $0 [toolchain|project|simulator|device|all]"; exit 1 ;;
esac
