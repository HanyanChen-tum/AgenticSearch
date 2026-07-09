"""Evaluation utilities."""

from __future__ import annotations

from typing import Any


def canonical_sort_key(value: Any) -> Any:
    """Return a deterministic key for values Python cannot directly compare."""
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (2, value)
    if isinstance(value, str):
        return (3, value)
    if isinstance(value, (list, tuple)):
        return (4, tuple(canonical_sort_key(item) for item in value))
    return (5, repr(value))


def normalize_answer(answer: Any, *, preserve_order: bool = False) -> Any:
    if answer is None:
        return None

    rows = [tuple(row) for row in answer]
    return rows if preserve_order else sorted(rows, key=canonical_sort_key)


def sql_requires_order(sql: str | None) -> bool:
    return bool(sql and "order by" in sql.lower())


def is_correct(
    pred_answer: Any,
    gold_answer: Any,
    *,
    gold_sql: str | None = None,
    preserve_order: bool | None = None,
) -> bool:
    if preserve_order is None:
        preserve_order = sql_requires_order(gold_sql)
    return normalize_answer(pred_answer, preserve_order=preserve_order) == normalize_answer(
        gold_answer,
        preserve_order=preserve_order,
    )
