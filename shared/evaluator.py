"""Evaluation utilities."""

from __future__ import annotations

from typing import Any


def normalize_answer(answer: Any) -> Any:
    if answer is None:
        return None

    return sorted(tuple(row) for row in answer)


def is_correct(pred_answer: Any, gold_answer: Any) -> bool:
    return normalize_answer(pred_answer) == normalize_answer(gold_answer)
