"""Run Recursive DB-RLM from the scripts directory."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spider1_experiments.ours.recursive_db_rlm import main


if __name__ == "__main__":
    main()


