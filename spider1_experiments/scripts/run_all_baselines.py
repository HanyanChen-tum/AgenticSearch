"""Run all three baselines sequentially and write a comparison summary."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spider1_experiments.baselines.baseline_1_direct_llm_schema import (
    METHOD_NAME as BASELINE_1_NAME,
    run_baseline as run_baseline_1,
)
from spider1_experiments.baselines.baseline_2_direct_text_to_sql import (
    DEFAULT_TOP_K_COLUMNS,
    DEFAULT_TOP_K_TABLES,
    METHOD_NAME as BASELINE_2_NAME,
    run_baseline as run_baseline_2,
)
from spider1_experiments.baselines.baseline_3_non_recursive_db_agent import (
    DEFAULT_MAX_STEPS,
    METHOD_NAME as BASELINE_3_NAME,
    run_baseline as run_baseline_3,
)
from spider1_experiments.scripts.evaluate_results import compare_results, print_summary
from spider1_experiments.shared import config
from spider1_experiments.shared.data_loader import load_questions
from spider1_experiments.shared.io_utils import write_json


BASELINE_NAMES = (BASELINE_1_NAME, BASELINE_2_NAME, BASELINE_3_NAME)


def result_path(results_dir: Path, method_name: str) -> Path:
    return results_dir / f"{method_name}.json"


def run_all(
    dataset_path: str | Path = config.DEFAULT_DATASET_PATH,
    database_dir: str | Path = config.DATABASE_DIR,
    results_dir: str | Path = config.RESULTS_DIR,
    limit: int | None = None,
    top_k_tables: int = DEFAULT_TOP_K_TABLES,
    top_k_columns: int = DEFAULT_TOP_K_COLUMNS,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> list[dict[str, object]]:
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")
    if top_k_tables < 1 or top_k_columns < 1:
        raise ValueError("top-k values must be at least 1")
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")

    dataset = Path(dataset_path)
    databases = Path(database_dir)
    output_dir = Path(results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    questions = load_questions(dataset)
    selected_questions = questions[:limit] if limit is not None else questions
    database_count = len({row["db_id"] for row in selected_questions})

    print(
        f"Running 3 baselines on {len(selected_questions)} questions "
        f"across {database_count} databases."
    )
    print(f"Dataset: {dataset}")
    print(f"Database dir: {databases}")
    print(f"Results dir: {output_dir}")

    runs = [
        (
            BASELINE_1_NAME,
            lambda: run_baseline_1(
                dataset_path=dataset,
                database_dir=databases,
                output_path=result_path(output_dir, BASELINE_1_NAME),
                limit=limit,
            ),
        ),
        (
            BASELINE_2_NAME,
            lambda: run_baseline_2(
                dataset_path=dataset,
                database_dir=databases,
                output_path=result_path(output_dir, BASELINE_2_NAME),
                limit=limit,
                top_k_tables=top_k_tables,
                top_k_columns=top_k_columns,
            ),
        ),
        (
            BASELINE_3_NAME,
            lambda: run_baseline_3(
                dataset_path=dataset,
                database_dir=databases,
                output_path=result_path(output_dir, BASELINE_3_NAME),
                limit=limit,
                max_steps=max_steps,
            ),
        ),
    ]

    total_started_at = time.perf_counter()
    for index, (method_name, runner) in enumerate(runs, start=1):
        print(f"\n[{index}/3] Starting {method_name}")
        started_at = time.perf_counter()
        runner()
        elapsed = time.perf_counter() - started_at
        print(f"[{index}/3] Finished {method_name} in {elapsed:.2f} seconds")

    summary = [
        row
        for row in compare_results(output_dir)
        if row["method"] in BASELINE_NAMES
    ]
    summary_path = output_dir / "summary_metrics.json"
    write_json(summary_path, summary)

    print("\nAll baselines finished.")
    print(f"Total time: {time.perf_counter() - total_started_at:.2f} seconds")
    print(f"Summary: {summary_path}")
    print_summary(summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Baselines 1, 2, and 3 sequentially."
    )
    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--results-dir", default=str(config.RESULTS_DIR))
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N questions. Omit to run the full dataset.",
    )
    parser.add_argument("--top-k-tables", type=int, default=DEFAULT_TOP_K_TABLES)
    parser.add_argument("--top-k-columns", type=int, default=DEFAULT_TOP_K_COLUMNS)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_all(
        dataset_path=args.dataset,
        database_dir=args.database_dir,
        results_dir=args.results_dir,
        limit=args.limit,
        top_k_tables=args.top_k_tables,
        top_k_columns=args.top_k_columns,
        max_steps=args.max_steps,
    )


if __name__ == "__main__":
    main()


