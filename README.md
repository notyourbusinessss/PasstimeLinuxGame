# Space Miner

An idle game for Linux, written in Python with pygame.

Start on Earth and mine the asteroids that orbit it. Every planet has its own ore, fleet, colony and bonus.
Unlock the next world with the ores of the ones behind you, travel between the planets, build megaprojects,
research tech, survive random events, then **Warp** for permanent Dark Matter.

## Run

```sh
./play.sh          # installs pygame if needed, then starts the game
```

Controls: click asteroids (or press SPACE) to mine, keys 1-8 switch tabs, click the planets along the bottom to travel.
Progress autosaves to `~/.space_miner_save.json` and your fleets keep mining while you're away.

## Files

- `space_miner.py` - the game window and UI
- `core.py` - game rules and state (no pygame, so it can run headless)
- `gfx.py` - procedural graphics (every sprite is generated at start-up)
- `sim.py` / `calibrate.py` - a bot that plays the game headless, used to balance the pacing
