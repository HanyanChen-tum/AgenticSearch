"""Analyze correctness overlap among candidate result files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_result(path: Path) -> dict[str, dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"Expected result list in {path}")
    return {str(row["id"]): row for row in rows}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze candidate correctness overlap.")
    parser.add_argument(
        "--result-files",
        nargs="+",
        required=True,
        help="Result JSON files to compare.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    loaded = [(Path(path).stem, load_result(Path(path))) for path in args.result_files]
    if not loaded:
        raise ValueError("No result files provided")

    common_ids = set(loaded[0][1])
    for _, rows_by_id in loaded[1:]:
        common_ids &= set(rows_by_id)
    ordered_ids = sorted(common_ids)

    print(f"Common examples: {len(ordered_ids)}")
    print()

    correct_sets: dict[str, set[str]] = {}
    for label, rows_by_id in loaded:
        correct_ids = {
            example_id
            for example_id in ordered_ids
            if rows_by_id[example_id].get("correct") is True
        }
        correct_sets[label] = correct_ids
        accuracy = len(correct_ids) / len(ordered_ids) if ordered_ids else 0
        print(f"{label}: {len(correct_ids)}/{len(ordered_ids)} = {accuracy:.4f}")

    union = set().union(*correct_sets.values()) if correct_sets else set()
    intersection = set(ordered_ids)
    for correct_ids in correct_sets.values():
        intersection &= correct_ids

    print()
    print(f"Oracle union upper bound: {len(union)}/{len(ordered_ids)} = {len(union) / len(ordered_ids):.4f}")
    print(f"All-correct intersection: {len(intersection)}/{len(ordered_ids)} = {len(intersection) / len(ordered_ids):.4f}")
    print()

    labels = list(correct_sets)
    for left in labels:
        for right in labels:
            if left == right:
                continue
            left_only = correct_sets[left] - correct_sets[right]
            right_only = correct_sets[right] - correct_sets[left]
            print(
                f"{left} vs {right}: "
                f"{left}_only={len(left_only)}, {right}_only={len(right_only)}"
            )


if __name__ == "__main__":
    main()
