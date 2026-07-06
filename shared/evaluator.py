"""Evaluation utilities."""

from __future__ import annotations

from typing import Any


def normalize_answer(answer: Any, *, preserve_order: bool = False) -> Any:
    if answer is None:
        return None

    rows = [tuple(row) for row in answer]
    return rows if preserve_order else sorted(rows)


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
