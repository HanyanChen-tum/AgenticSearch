"""Evaluation utilities."""

from __future__ import annotations

from typing import Any


def _sort_key(row: tuple) -> tuple:
    # Make mixed None/str rows sortable by converting None → "" for comparison
    return tuple("" if v is None else str(v) for v in row)


def normalize_answer(answer: Any) -> Any:
    if answer is None:
        return None

    return sorted((tuple(row) for row in answer), key=_sort_key)


def is_correct(pred_answer: Any, gold_answer: Any) -> bool:
    """Official BIRD protocol: set comparison over result tuples.

    The official BIRD evaluation.py uses
    `set(predicted_res) == set(ground_truth_res)`, so duplicate rows and
    row order are ignored.
    """
    if pred_answer is None or gold_answer is None:
        return pred_answer == gold_answer
    return {tuple(row) for row in pred_answer} == {tuple(row) for row in gold_answer}


def is_correct_strict(pred_answer: Any, gold_answer: Any) -> bool:
    """Stricter multiset comparison (duplicates matter). Kept for ablation."""
    return normalize_answer(pred_answer) == normalize_answer(gold_answer)
