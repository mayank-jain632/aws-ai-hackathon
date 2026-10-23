import os
import sys
from pathlib import Path

# Make `backend.app...` importable when pytest is run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# The watchdog never reaches Alpaca or AWS from tests; tests that need live data stub it.
os.environ.setdefault("WATCHDOG_LIVE_DATA", "0")
os.environ.setdefault("WATCHDOG_AWS", "0")
