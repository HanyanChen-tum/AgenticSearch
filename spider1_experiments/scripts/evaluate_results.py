"""Compare result files and write summary metrics."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spider1_experiments.shared import config
from spider1_experiments.shared.evaluator import build_evaluation_fields
from spider1_experiments.shared.io_utils import read_json, write_json


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


def safe_average(values: list[Any]) -> float | None:
    numeric_values = [value for value in values if isinstance(value, (int, float))]
    if not numeric_values:
        return None
    return round(sum(numeric_values) / len(numeric_values), 4)


def safe_accuracy(matches: int, total: int) -> float | None:
    return round(matches / total, 4) if total else None


def get_tool_calls(row: dict[str, Any]) -> int | None:
    value = row.get("tool_calls", row.get("actions_used"))
    return value if isinstance(value, int) else 0


def get_evaluation_fields(row: dict[str, Any]) -> dict[str, Any]:
    if {
        "sql_valid",
        "execution_correct",
        "exact_match",
        "component_match",
        "component_match_correct",
        "failure_type",
    }.issubset(row):
        return {
            "sql_valid": row["sql_valid"],
            "execution_correct": row["execution_correct"],
            "exact_match": row["exact_match"],
            "component_match": row["component_match"],
            "component_match_correct": row["component_match_correct"],
            "failure_type": row["failure_type"],
        }

    execution_correct = row.get("execution_correct", row.get("correct") is True)
    error = row.get("error") if row.get("correct") is not True else None
    return build_evaluation_fields(
        row.get("predicted_sql") or "",
        row.get("gold_sql") or "",
        predicted_error=error,
        gold_error=None,
        execution_correct=execution_correct,
    )


def summarize_results(method: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row.get("correct") is True)
    evaluation_rows = [get_evaluation_fields(row) for row in rows]
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
    failure_types = Counter(
        row.get("failure_type") or "none"
        for row in evaluation_rows
        if row.get("execution_correct") is not True
    )
    component_names = ["tables", "columns", "joins", "aggregations"]
    component_accuracy = {
        name: safe_accuracy(
            sum(
                1
                for row in evaluation_rows
                if isinstance(row.get("component_match"), dict)
                and row["component_match"].get(name) is True
            ),
            total,
        )
        for name in component_names
    }

    return {
        "method": method,
        "total": total,
        "correct": correct,
        "execution_accuracy": safe_accuracy(correct, total),
        "sql_valid_rate": safe_accuracy(
            sum(1 for row in evaluation_rows if row.get("sql_valid") is True),
            total,
        ),
        "error_rate": safe_accuracy(
            sum(1 for row in evaluation_rows if row.get("sql_valid") is not True),
            total,
        ),
        "exact_match_accuracy": safe_accuracy(
            sum(1 for row in evaluation_rows if row.get("exact_match") is True),
            total,
        ),
        "component_match_accuracy": safe_accuracy(
            sum(
                1
                for row in evaluation_rows
                if row.get("component_match_correct") is True
            ),
            total,
        ),
        "component_accuracy": component_accuracy,
        "avg_latency_seconds": round(sum(latencies) / len(latencies), 4) if latencies else None,
        "total_input_tokens": safe_sum([row.get("input_tokens") for row in rows]),
        "total_output_tokens": safe_sum([row.get("output_tokens") for row in rows]),
        "total_tool_calls": safe_sum([get_tool_calls(row) for row in rows]),
        "avg_tool_calls": safe_average([get_tool_calls(row) for row in rows]),
        "error_counts": dict(errors),
        "failure_type_counts": dict(failure_types),
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
                    "sql_valid_rate": None,
                    "error_rate": None,
                    "exact_match_accuracy": None,
                    "component_match_accuracy": None,
                    "component_accuracy": {
                        "tables": None,
                        "columns": None,
                        "joins": None,
                        "aggregations": None,
                    },
                    "avg_latency_seconds": None,
                    "total_input_tokens": None,
                    "total_output_tokens": None,
                    "total_tool_calls": None,
                    "avg_tool_calls": None,
                    "error_counts": {"missing_result_file": 1},
                    "failure_type_counts": {"missing_result_file": 1},
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
        "sql_valid_rate",
        "error_rate",
        "exact_match_accuracy",
        "component_match_accuracy",
        "avg_latency_seconds",
        "total_input_tokens",
        "total_output_tokens",
        "total_tool_calls",
        "avg_tool_calls",
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


