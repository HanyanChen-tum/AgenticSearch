"""Write a generic markdown error analysis report for Text-to-SQL result files."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def is_empty_answer(answer: Any) -> bool:
    return answer in (None, [], ())


def classify_row(row: dict[str, Any]) -> str:
    if row.get("correct") is True:
        return "correct"

    error = row.get("error")
    predicted_sql = (row.get("predicted_sql") or "").strip()
    predicted_answer = row.get("predicted_answer")
    termination = row.get("termination") or row.get("termination_reason")

    if not predicted_sql:
        return "no_sql_generated"
    if termination in {"max_iterations", "MaxIterationsError"}:
        return "max_iterations"
    if error:
        lowered = str(error).lower()
        if "no such table" in lowered:
            return "sql_error_no_such_table"
        if "no such column" in lowered:
            return "sql_error_no_such_column"
        if "syntax" in lowered:
            return "sql_error_syntax"
        if "only read-only" in lowered:
            return "sql_error_not_read_only"
        if "api" in lowered or "connection" in lowered or "authentication" in lowered:
            return "llm_or_connection_error"
        return "sql_execution_error_other"
    if is_empty_answer(predicted_answer):
        return "empty_answer"
    return "wrong_answer"


def compact(value: Any, max_chars: int = 700) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "... [truncated]"
    return text


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories = Counter(classify_row(row) for row in rows)
    terminations = Counter(
        str(row.get("termination") or row.get("termination_reason") or "unknown")
        for row in rows
    )
    methods = Counter(str(row.get("method") or "unknown") for row in rows)
    total = len(rows)
    correct = categories["correct"]
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
        "categories": dict(categories),
        "terminations": dict(terminations),
        "methods": dict(methods),
    }


def write_markdown(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    result_file: Path,
    output_path: Path,
    max_examples: int,
) -> None:
    wrong_rows = [row for row in rows if row.get("correct") is not True]
    lines = [
        "# Text-to-SQL 错误分析报告",
        "",
        "## 基本信息",
        "",
        f"- result file: `{result_file}`",
        f"- total: {summary['total']}",
        f"- correct: {summary['correct']}",
        f"- accuracy: {summary['accuracy']}",
        "",
        "## 错误类型统计",
        "",
        "| category | count |",
        "|---|---:|",
    ]
    for category, count in sorted(summary["categories"].items()):
        lines.append(f"| {category} | {count} |")

    lines.extend(
        [
            "",
            "## Termination 统计",
            "",
            "| termination | count |",
            "|---|---:|",
        ]
    )
    for termination, count in sorted(summary["terminations"].items()):
        lines.append(f"| {termination} | {count} |")

    lines.extend(
        [
            "",
            "## 错例详情",
            "",
        ]
    )
    for row in wrong_rows[:max_examples]:
        lines.extend(
            [
                f"### {row.get('id')} | {classify_row(row)}",
                "",
                f"- db_id: `{row.get('db_id')}`",
                f"- method: `{row.get('method')}`",
                f"- termination: `{row.get('termination') or row.get('termination_reason')}`",
                f"- error: `{row.get('error')}`",
                f"- question: {row.get('question')}",
                "",
                "Predicted SQL:",
                "",
                "```sql",
                str(row.get("predicted_sql") or ""),
                "```",
                "",
                f"- predicted answer: `{compact(row.get('predicted_answer'))}`",
                f"- gold answer: `{compact(row.get('gold_answer'))}`",
                "",
                "Gold SQL:",
                "",
                "```sql",
                str(row.get("gold_sql") or ""),
                "```",
                "",
            ]
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze errors in a result JSON file.")
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--max-examples", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result_file = Path(args.result_file)
    rows = json.loads(result_file.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"Expected result list in {result_file}")

    summary = summarize(rows)
    write_markdown(
        rows,
        summary,
        result_file,
        Path(args.output_md),
        max_examples=args.max_examples,
    )
    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"Accuracy: {summary['correct']}/{summary['total']} = {summary['accuracy']}")
    print(f"Saved markdown report to {args.output_md}")
    if args.output_json:
        print(f"Saved JSON summary to {args.output_json}")


if __name__ == "__main__":
    main()
