"""The iPhone app starts here: the launcher of the app (from kivy-ios) runs main.py in the app's folder. It does what space_miner.py does."""
import os
import sys

os.environ.setdefault("SPACE_MINER_IOS", "1")      # (resources.IOS: the touch interface, always fullscreen, the save in Documents)
print("Space Miner: starting on iOS, Python", sys.version.split()[0], flush=True)

import space_miner  # noqa: E402

space_miner.main()
