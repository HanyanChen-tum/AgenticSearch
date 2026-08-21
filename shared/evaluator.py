"""Evaluation utilities."""

from __future__ import annotations

from typing import Any

# `termination` values that are genuine outcomes of the model attempting the
# question. Everything else -- a console print raising UnicodeEncodeError, an
# AttributeError from a None field, a content-policy rejection -- is this
# harness failing to run the attempt, not the model failing to answer it.
#
# The runner used to invert this: it enumerated the terminations to *retry*
# and defaulted everything unrecognised to "the model's real result" with
# correct=False. Most unrecognised exceptions are our own code breaking, so
# that default silently turned harness crashes into wrong answers -- see
# harness_defects_2026-08-18.md. A record whose termination is not in this set
# must be excluded from any accuracy computation (`scored: False`), not
# counted as `correct: False`.
MODEL_TERMINATIONS = frozenset({"final", "MaxIterationsError"})


def is_scored(termination: str) -> bool:
    """Whether a record is a genuine model outcome, not a harness failure."""
    return termination in MODEL_TERMINATIONS


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
