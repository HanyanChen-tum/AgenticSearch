"""Compare result files and write summary metrics."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared import config
from shared.io_utils import read_json, write_json


METHOD_FILES = {
    "baseline_1_direct_llm_schema": "baseline_1_direct_llm_schema.json",
    "baseline_2_direct_text_to_sql": "baseline_2_direct_text_to_sql.json",
    "baseline_3_non_recursive_db_agent": "baseline_3_non_recursive_db_agent.json",
    "ours_recursive_db_rlm": "ours_recursive_db_rlm.json",
}


def safe_sum(values: list[Any]) -> int | None:
    numeric_values = [value for value in values if isinstance(value, (int, float))]
    if not numeric_values:
        return None
    return int(sum(numeric_values))


def summarize_results(method: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row.get("correct") is True)
    latencies = [
        row.get("latency_seconds")
        for row in rows
        if isinstance(row.get("latency_seconds"), (int, float))
    ]
    errors = Counter(
        row.get("error") or "none"
        for row in rows
        if row.get("correct") is not True
    )

    return {
        "method": method,
        "total": total,
        "correct": correct,
        "execution_accuracy": round(correct / total, 4) if total else None,
        "avg_latency_seconds": round(sum(latencies) / len(latencies), 4) if latencies else None,
        "total_input_tokens": safe_sum([row.get("input_tokens") for row in rows]),
        "total_output_tokens": safe_sum([row.get("output_tokens") for row in rows]),
        "error_counts": dict(errors),
    }


def compare_results(results_dir: str | Path = config.RESULTS_DIR) -> list[dict[str, Any]]:
    base_dir = Path(results_dir)
    summary = []

    for method, file_name in METHOD_FILES.items():
        path = base_dir / file_name
        if not path.exists():
            summary.append(
                {
                    "method": method,
                    "total": 0,
                    "correct": 0,
                    "execution_accuracy": None,
                    "avg_latency_seconds": None,
                    "total_input_tokens": None,
                    "total_output_tokens": None,
                    "error_counts": {"missing_result_file": 1},
                }
            )
            continue

        rows = read_json(path)
        if not isinstance(rows, list):
            raise ValueError(f"Expected result list in {path}")

        summary.append(summarize_results(method, rows))

    return summary


def print_summary(summary: list[dict[str, Any]]) -> None:
    headers = [
        "method",
        "total",
        "correct",
        "execution_accuracy",
        "avg_latency_seconds",
        "total_input_tokens",
        "total_output_tokens",
    ]
    widths = {
        header: max(
            len(header),
            *[len(str(row.get(header))) for row in summary],
        )
        for header in headers
    }

    print(" | ".join(header.ljust(widths[header]) for header in headers))
    print("-+-".join("-" * widths[header] for header in headers))
    for row in summary:
        print(" | ".join(str(row.get(header)).ljust(widths[header]) for header in headers))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare baseline and DB-RLM result files.")
    parser.add_argument("--results-dir", default=str(config.RESULTS_DIR))
    parser.add_argument(
        "--output",
        default=str(config.RESULTS_DIR / "summary_metrics.json"),
        help="Path for summary metrics JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = compare_results(args.results_dir)
    write_json(args.output, summary)
    print_summary(summary)


if __name__ == "__main__":
    main()
