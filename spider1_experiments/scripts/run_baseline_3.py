"""Run baseline 3 from the scripts directory."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spider1_experiments.baselines.baseline_3_non_recursive_db_agent import main


if __name__ == "__main__":
    main()


