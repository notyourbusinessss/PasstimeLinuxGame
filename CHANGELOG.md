# Changelog

## 1.0.0

The first release.

### The game
- Idle mining across 12 planets, each with its own ore, 8 ship types, 58 upgrades and 6 colony buildings; travel between planets, megaprojects, a 30-tech tree, quests, supply crates and 9 kinds of random events.
- Warp (prestige) with Dark Matter and 22 perks; **New Game+** (Ascension) with Stardust and 21 perks.
- The **galaxy**: 15 enemy-held sectors in 6 factions, campaigns, an armory (weapons, armor, engines, shields, intel) and permanent sector bonuses.
- The **Threat Director**: adaptive raids and counter-offensives, Intel warnings, Fortify, faction hostility.
- **A galaxy screen of its own**: a star-chart background, a slim top bar, a map that fills the window (a *wide* layout with a command bar for the selected sector, or beside the side panel), incoming-attack chips with Fortify.
- **Frontline close-up**: a zoomable galaxy map with battle lines, fleets, garrison shields and a mini-map.
- 165 achievements, a stats page, procedural graphics and sound (no asset files for those).

### Release
- Resizable window, fullscreen (F11 / Alt+Enter, `--fullscreen`) that scales to fit any screen.
- **Higher resolutions**: 1280x720, 1600x900, 1920x1080 and 2560x1440 (automatic by default, `--resolution WxH`, a Size button in the settings). The whole layout adapts: a taller panel, a bigger map and a larger asteroid field.
- **Android**: the game plays on phones and tablets (landscape): tap, drag to scroll with momentum, pinch to zoom the galaxy map, back button, saves when you leave the app and pays the offline progress when you return. The canvas takes the shape of the screen. `buildozer.spec` and a release job build the APK.
- Linux build: a one-file executable with an installer and a menu entry; no Python or pygame needed.
- The DejaVu Sans font is bundled, so the game looks the same on every system.
- `--version`, `--help`, `--dev` (cheats, terminal only) and `--selftest` (uses a temporary save).
- **Logging and crash reports**: a rotating log (`~/.local/state/space-miner/space-miner.log`), a crash report file, a stack dump for native crashes, and errors in a single frame are logged without ending your game. The Stats page has an *Open log folder* button.
- Fixed a crash in the frontline close-up (a random number could land exactly on the end of a list, about once in 65,000 laser shots).
- Save safety: a rolling backup, automatic restore of a damaged save, and an unreadable save is copied aside instead of being overwritten.
