# Changelog

## Unreleased

- **The Kuiper Belt replaces Proxima b** as the 12th and last planet of the solar system: Proxima b belongs to another star, so the first part of the game is now the solar system only. Same place in the game (price, ore production x3, buildings x1.5, megaproject x5), new look: an ice dwarf world with tholin patches, Tholin ore, the *Comet Catchers* megaproject and a fleet of comets and snowballs (Comet Skiff ... Eris Citadel, Halley Ark) that sweep round the planet on long comet orbits. Saves are unchanged (the Interstellar achievement is now Last Frontier and is kept).

## 1.1.0

The galaxy is now the real Milky Way with thousands of systems, you can attack several fronts at once, the enemy can take your systems, and every planet has two more ship classes.

- **Two new ship classes: Citadel and Ark** (10 classes now, with a name, description and look on every planet). They are the biggest ships: a Citadel is a flagship with its escorts, an Ark a line of three flagships, both built from the planet's own hulls, drawn larger and leading the fleets on the galaxy map. They cost 6.0B and 60.0B base, mine 110K and 280K ore/s, fight 1.2x better than the class before, and come with upgrades (68 per planet) and two more "Fan" achievements (182 in total). Old saves load with the new classes at zero. The balancing bot still reaches the Void Throne at about 70 hours.
- **Multiple fronts.** Attack several systems at the same time: the new **Command** armory track (7 levels) adds one front per level, up to 8. Each attack sends a share of the fleet that is at home - the smallest force that wins with 95% (*Enough*, the default), 25%, 50% or *All* - so splitting the fleet trades odds for speed; losses count only the ships that were sent. The Galaxy tab has a Fronts card with every fleet in the field, the map shows each fleet on its own lane and each siege, the wide map's top bar lists the next arrivals, and the Fleet Admiral fills every free front by itself. Old saves with a running campaign keep it as one front. New achievements: Two-Front War, Multi-Front Command, War on Every Front.
- **Enemies take your systems.** Counter-offensives now come from every enemy faction at war with you at once (waves of up to three), hit as hard as the system they start from allows (0.8x to 6x the power of the system they attack) and are met by the garrison or by the part of your fleet that is at home - fleets away on a campaign defend nothing. The enemy grows bolder and strikes sooner while your fleets are away.
- The balancing bot fills every front and goes for the Void Throne first; `--selftest` covers fronts, saves and counter-offensives.
- `--new-game` (also `--reset`): start over from the terminal. It asks you to type yes (`--yes` skips the question), erases the save and its backup and starts a new game, keeping a copy of the old save as `.space_miner_save.json.before-reset-DATE`.
- **The real Milky Way as the galaxy map.** The 15 fixed sectors are gone: the map is now the Milky Way seen from above, with **more than 6,000 star systems** to conquer. About 140 are real stars and objects at their real distances and directions (Alpha Centauri, Sirius, Betelgeuse, the Orion and Crab nebulae, Cygnus X-1, Omega Centauri, Sagittarius A*...) and thousands are generated over the real shape of the galaxy. **Travel is free**: you can attack any system within your new **Jump Drive** range (22 levels, 6 light-years to 45,000) of a system you hold. Systems have their own power, faction and reward; the map zooms from the whole galaxy to a single star, with names, lanes, range circles, a ruler and a mini-map; the Galaxy tab has a Jump Drive card and a target browser. Old saves are converted (your sectors become the same stars).
- **Fleet Admiral** (new tech): launches campaigns by itself against the factions you are at war with.
- Campaigns take longer against stronger systems plus the flight; an easy win costs few ships.
- Stardust perks that kept your first sectors now keep your nearest systems (25 / 100). New achievements for the size of your empire, famous places and the Jump Drive.
- `tools/make_galaxy.py` rebuilds `assets/galaxy.json`.
- **A bigger galaxy map with a screen of its own**: a star-chart background, a slim top bar, a map that fills the window (a *wide* layout with a command bar for the selected system, or beside the side panel), incoming-attack chips with Fortify.
- **Every planet's ships look and move differently.** Each planet now has its own design language instead of the same hulls with extras bolted on: silver landers on spindly legs (Moon), wheeled rovers (Mars), airships (Venus), sun-shields and solar wings (Mercury), tumbling rocks with claws (Ceres), striped storm hulls (Jupiter), discs with tilted rings (Saturn), crystals (Uranus), deep-sea creatures (Neptune), ice sleds and hearts (Pluto) and living spores (Proxima b), each in its own colours. They also fly their own paths (hopping, driving over the planet, floating, swinging round a lopsided orbit, spiralling, a flat ring plane, over the poles, weaving, drifting, a figure of eight) and fire their own mining lasers. Prices, output and balance are unchanged.
- `tools/ship_sheet.py` draws a contact sheet of every ship.

## 1.0.0

The first release.

### The game
- Idle mining across 12 planets, each with its own ore, 8 ship types, 58 upgrades and 6 colony buildings; travel between planets, megaprojects, a 30-tech tree, quests, supply crates and 9 kinds of random events.
- Warp (prestige) with Dark Matter and 22 perks; **New Game+** (Ascension) with Stardust and 21 perks.
- The **galaxy**: 15 enemy-held sectors in 6 factions, campaigns, an armory (weapons, armor, engines, shields, intel) and permanent sector bonuses.
- The **Threat Director**: adaptive raids and counter-offensives, Intel warnings, Fortify, faction hostility.
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
