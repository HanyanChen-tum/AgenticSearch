"""Analyze prediction errors from experiment result files."""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared import config
from shared.io_utils import read_json, write_json


def classify_error(row: dict[str, Any]) -> str:
    if row.get("correct") is True:
        return "correct"

    error = (row.get("error") or "").lower()
    predicted_sql = (row.get("predicted_sql") or "").strip()

    if not predicted_sql:
        return "no_sql_generated"
    if "syntax error" in error:
        return "sql_syntax_error"
    if "no such table" in error:
        return "unknown_table"
    if "no such column" in error:
        return "unknown_column"
    if error:
        return "execution_error"
    return "wrong_answer"


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories = Counter()
    by_db: dict[str, Counter[str]] = defaultdict(Counter)
    by_termination = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        category = classify_error(row)
        categories[category] += 1
        by_db[str(row.get("db_id", "unknown"))][category] += 1
        termination = row.get("termination_reason") or row.get("termination") or "unknown"
        by_termination[str(termination)] += 1

        if category != "correct" and len(examples[category]) < 10:
            examples[category].append(
                {
                    "id": row.get("id"),
                    "db_id": row.get("db_id"),
                    "question": row.get("question"),
                    "predicted_sql": row.get("predicted_sql"),
                    "gold_sql": row.get("gold_sql"),
                    "error": row.get("error"),
                }
            )

    total = len(rows)
    correct = categories["correct"]
    return {
        "total": total,
        "correct": correct,
        "execution_accuracy": round(correct / total, 4) if total else None,
        "error_categories": dict(categories),
        "errors_by_database": {db_id: dict(counter) for db_id, counter in by_db.items()},
        "termination_reasons": dict(by_termination),
        "example_errors": dict(examples),
    }


def analyze_file(path: str | Path) -> dict[str, Any]:
    rows = read_json(path)
    if not isinstance(rows, list):
        raise ValueError(f"Expected result list in {path}")
    summary = summarize_rows(rows)
    summary["file"] = str(path)
    summary["method"] = rows[0].get("method") if rows else None
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze experiment result errors.")
    parser.add_argument(
        "--results",
        nargs="+",
        default=[
            str(config.RESULTS_DIR / "baseline_1_direct_llm_schema.json"),
            str(config.RESULTS_DIR / "baseline_2_direct_text_to_sql.json"),
            str(config.RESULTS_DIR / "baseline_3_non_recursive_db_agent.json"),
            str(config.RESULTS_DIR / "ours_recursive_db_rlm.json"),
        ],
        help="One or more result JSON files.",
    )
    parser.add_argument(
        "--output",
        default=str(config.RESULTS_DIR / "error_analysis.json"),
        help="Path for error analysis JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summaries = []
    for raw_path in args.results:
        path = Path(raw_path)
        if path.exists():
            summaries.append(analyze_file(path))
        else:
            summaries.append({"file": str(path), "error": "missing_result_file"})

    write_json(args.output, summaries)
    for summary in summaries:
        if "error" in summary:
            print(f"{summary['file']}: {summary['error']}")
            continue
        print(
            f"{summary['file']}: "
            f"{summary['correct']}/{summary['total']} "
            f"accuracy={summary['execution_accuracy']}"
        )


if __name__ == "__main__":
    main()
