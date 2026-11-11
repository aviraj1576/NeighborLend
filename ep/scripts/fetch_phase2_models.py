"""Download only the explicitly user-approved immutable Phase 2 asset manifest."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ep_engine.cv.assets import fetch_all

if __name__ == "__main__":
    result = fetch_all()
    print(f"All {len(result['files'])} approved assets validated")
