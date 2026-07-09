"""Analyze candidate-ensemble errors and write a markdown report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.evaluator import is_correct


def candidate_is_correct(candidate: dict[str, Any], row: dict[str, Any]) -> bool:
    if candidate.get("error") is not None:
        return False
    return is_correct(
        candidate.get("answer"),
        row.get("gold_answer"),
        gold_sql=row.get("gold_sql"),
    )


def is_empty_answer(answer: Any) -> bool:
    return answer in (None, [], ())


def classify_error(row: dict[str, Any]) -> str:
    if row.get("correct") is True:
        return "correct"

    candidates = row.get("candidates") or []
    usable = [candidate for candidate in candidates if candidate.get("usable")]
    correct_candidates = [
        candidate for candidate in candidates if candidate_is_correct(candidate, row)
    ]

    selected_error = row.get("error")
    selected_answer = row.get("predicted_answer")

    if not candidates:
        return "no_candidates"
    if selected_error:
        return "selected_sql_execution_error"
    if is_empty_answer(selected_answer):
        return "selected_empty_answer"
    if correct_candidates:
        return "selector_chose_wrong_candidate"
    if not usable:
        return "no_usable_candidates_after_repair"
    return "all_candidates_wrong"


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    category_counts = Counter()
    selected_label_counts = Counter()
    wrong_selected_label_counts = Counter()
    verifier_counts = Counter()
    repair_attempted = 0
    repair_success = 0
    oracle_correct = 0
    wrong_examples: list[dict[str, Any]] = []

    for row in rows:
        category = classify_error(row)
        category_counts[category] += 1
        selected_label = row.get("selected_candidate_label") or "none"
        selected_label_counts[selected_label] += 1

        candidates = row.get("candidates") or []
        candidate_correct_labels = [
            candidate.get("label")
            for candidate in candidates
            if candidate_is_correct(candidate, row)
        ]
        if candidate_correct_labels:
            oracle_correct += 1

        repair_attempted += int(row.get("repair_attempted_count") or 0)
        repair_success += int(row.get("repair_success_count") or 0)
        verifier_counts["called" if row.get("verifier_called") else "not_called"] += 1

        if row.get("correct") is not True:
            wrong_selected_label_counts[selected_label] += 1
            wrong_examples.append(
                {
                    "id": row.get("id"),
                    "db_id": row.get("db_id"),
                    "category": category,
                    "question": row.get("question"),
                    "selected_label": selected_label,
                    "selected_sql": row.get("predicted_sql"),
                    "selected_answer": row.get("predicted_answer"),
                    "gold_answer": row.get("gold_answer"),
                    "error": row.get("error"),
                    "candidate_correct_labels": candidate_correct_labels,
                    "selection_reason": row.get("selection_reason"),
                    "repair_attempted_count": row.get("repair_attempted_count"),
                    "repair_success_count": row.get("repair_success_count"),
                }
            )

    total = len(rows)
    correct = category_counts["correct"]
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
        "oracle_correct": oracle_correct,
        "oracle_accuracy": round(oracle_correct / total, 4) if total else None,
        "category_counts": dict(category_counts),
        "selected_label_counts": dict(selected_label_counts),
        "wrong_selected_label_counts": dict(wrong_selected_label_counts),
        "verifier_counts": dict(verifier_counts),
        "repair_attempted": repair_attempted,
        "repair_success": repair_success,
        "wrong_examples": wrong_examples,
    }


def markdown_report(summary: dict[str, Any], max_examples: int) -> str:
    lines = [
        "# Candidate Ensemble Error Analysis",
        "",
        "## Summary",
        "",
        f"- total: {summary['total']}",
        f"- correct: {summary['correct']}",
        f"- accuracy: {summary['accuracy']}",
        f"- oracle correct if selector always picked a correct candidate: {summary['oracle_correct']}",
        f"- oracle accuracy: {summary['oracle_accuracy']}",
        f"- repair attempted: {summary['repair_attempted']}",
        f"- repair success: {summary['repair_success']}",
        "",
        "## Error Categories",
        "",
        "| category | count |",
        "|---|---:|",
    ]
    for category, count in sorted(summary["category_counts"].items()):
        lines.append(f"| {category} | {count} |")

    lines.extend(
        [
            "",
            "## Selected Candidate Labels",
            "",
            "| label | selected count | wrong count |",
            "|---|---:|---:|",
        ]
    )
    labels = set(summary["selected_label_counts"]) | set(summary["wrong_selected_label_counts"])
    for label in sorted(labels):
        lines.append(
            f"| {label} | {summary['selected_label_counts'].get(label, 0)} | "
            f"{summary['wrong_selected_label_counts'].get(label, 0)} |"
        )

    lines.extend(
        [
            "",
            "## Verifier",
            "",
            "| status | count |",
            "|---|---:|",
        ]
    )
    for status, count in sorted(summary["verifier_counts"].items()):
        lines.append(f"| {status} | {count} |")

    lines.extend(
        [
            "",
            "## Wrong Examples",
            "",
        ]
    )
    for example in summary["wrong_examples"][:max_examples]:
        lines.extend(
            [
                f"### {example['id']} | {example['category']}",
                "",
                f"- db_id: `{example['db_id']}`",
                f"- selected label: `{example['selected_label']}`",
                f"- correct candidate labels: `{example['candidate_correct_labels']}`",
                f"- error: `{example['error']}`",
                f"- selection reason: {example['selection_reason']}",
                f"- question: {example['question']}",
                "",
                "Selected SQL:",
                "",
                "```sql",
                str(example["selected_sql"] or ""),
                "```",
                "",
                f"- selected answer: `{example['selected_answer']}`",
                f"- gold answer: `{example['gold_answer']}`",
                "",
            ]
        )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze candidate ensemble errors.")
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--max-examples", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = json.loads(Path(args.result_file).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"Expected result list in {args.result_file}")

    summary = analyze(rows)
    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(
        markdown_report(summary, max_examples=args.max_examples),
        encoding="utf-8",
    )

    if args.output_json:
        output_json = Path(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"Accuracy: {summary['correct']}/{summary['total']} = {summary['accuracy']}")
    print(f"Oracle: {summary['oracle_correct']}/{summary['total']} = {summary['oracle_accuracy']}")
    print(f"Saved markdown report to {output_md}")
    if args.output_json:
        print(f"Saved JSON summary to {args.output_json}")


if __name__ == "__main__":
    main()
