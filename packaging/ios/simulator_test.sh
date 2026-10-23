#!/bin/sh
# Starts the app built by `build_ios.sh simulator` in the iOS Simulator and checks that the game runs: its log says it is ready and its
# autosave (every 15 seconds) appears in the app's Documents folder.   ./packaging/ios/simulator_test.sh [seconds to wait, default 60]
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
WORK="$ROOT/build/ios"
APP=$(ls -d "$WORK"/dd-sim/Build/Products/Release-iphonesimulator/*.app | head -1)
BUNDLE_ID="io.github.notyourbusinessss.spaceminer"
WAIT=${1:-60}
UDID=$(xcrun simctl list devices available --json | python3 -c '
import json, sys
d = json.load(sys.stdin)["devices"]
best = None
for runtime, devices in d.items():
    if "iOS" not in runtime:
        continue
    for dev in devices:
        if dev.get("isAvailable") and "iPhone" in dev["name"]:
            key = (runtime, dev["name"])
            if best is None or key > best[0]:
                best = (key, dev["udid"])
print(best[1])
')
echo "Simulator $UDID"
xcrun simctl boot "$UDID" 2> /dev/null || true
xcrun simctl bootstatus "$UDID" -b > /dev/null
xcrun simctl install "$UDID" "$APP"
rm -f "$WORK/sim-out.log" "$WORK/sim-err.log"
xcrun simctl launch --stdout="$WORK/sim-out.log" --stderr="$WORK/sim-err.log" "$UDID" "$BUNDLE_ID"
sleep "$WAIT"
DATA=$(xcrun simctl get_app_container "$UDID" "$BUNDLE_ID" data)
echo "--- data folder: $DATA"
ls -la "$DATA" "$DATA/Documents" "$DATA/Library/Logs/Space Miner" 2>&1 || true
xcrun simctl io "$UDID" screenshot "$WORK/sim.png" 2>&1 || true
sips -Z 560 --setProperty format jpeg --setProperty formatOptions 30 "$WORK/sim.png" --out "$WORK/sim.jpg" > /dev/null 2>&1 || true
xcrun simctl terminate "$UDID" "$BUNDLE_ID" || true
echo "--- stdout"; cat "$WORK/sim-out.log" 2> /dev/null | tail -30
echo "--- stderr"; cat "$WORK/sim-err.log" 2> /dev/null | tail -60
LOG="$DATA/Library/Logs/Space Miner/space-miner.log"
echo "--- space-miner.log"; tail -40 "$LOG" 2> /dev/null || true
test -f "$LOG" && grep -q "Ready in" "$LOG" || { echo "FAIL: the game did not get ready"; exit 1; }
test -f "$DATA/Documents/.space_miner_save.json" || { echo "FAIL: no autosave after $WAIT seconds"; exit 1; }
echo "PASS: the game runs in the simulator and saves"
