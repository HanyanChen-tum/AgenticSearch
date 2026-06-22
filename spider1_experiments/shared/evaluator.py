"""Evaluation utilities."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

try:
    import sqlglot
    from sqlglot import exp
except ImportError:  # pragma: no cover - exercised only without optional dependency.
    sqlglot = None
    exp = None


AGGREGATION_RE = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)
COLUMN_RE = re.compile(r"\b(?:[a-z_][\w]*\.)?([a-z_][\w]*)\b", re.IGNORECASE)
JOIN_RE = re.compile(
    r"\bjoin\s+([a-z_][\w]*)\b(?:\s+(?:as\s+)?[a-z_][\w]*)?"
    r"(?:\s+on\s+(.*?))?(?=\bjoin\b|\bwhere\b|\bgroup\b|\border\b|\blimit\b|$)",
    re.IGNORECASE | re.DOTALL,
)
TABLE_RE = re.compile(r"\b(?:from|join)\s+([a-z_][\w]*)\b", re.IGNORECASE)
SQL_KEYWORDS = {
    "as",
    "and",
    "by",
    "count",
    "desc",
    "distinct",
    "from",
    "group",
    "join",
    "limit",
    "max",
    "min",
    "on",
    "or",
    "order",
    "select",
    "sum",
    "avg",
    "where",
}


def normalize_answer(answer: Any) -> Any:
    if answer is None:
        return None

    # SQLite columns can contain values with different Python types (for
    # example, Spider's wta_1.birth_date contains both integers and strings).
    # Sorting raw tuples raises TypeError when Python has to compare those
    # values.  A typed multiset keeps row order irrelevant, preserves duplicate
    # rows, and does not incorrectly treat 1 and "1" as the same value.
    return Counter(
        tuple((type(value).__name__, value) for value in row)
        for row in answer
    )


def is_correct(pred_answer: Any, gold_answer: Any) -> bool:
    return normalize_answer(pred_answer) == normalize_answer(gold_answer)


def normalize_sql(sql: str) -> str:
    if not isinstance(sql, str):
        return ""

    cleaned = sql.strip().rstrip(";")
    if not cleaned:
        return ""

    if sqlglot is not None:
        try:
            return sqlglot.parse_one(cleaned, read="sqlite").sql(
                dialect="sqlite",
                pretty=False,
            ).lower()
        except Exception:
            pass

    return re.sub(r"\s+", " ", cleaned).lower()


def exact_sql_match(predicted_sql: str, gold_sql: str) -> bool:
    predicted_normalized = normalize_sql(predicted_sql)
    gold_normalized = normalize_sql(gold_sql)
    return bool(predicted_normalized) and predicted_normalized == gold_normalized


def _parse_sql(sql: str) -> Any | None:
    if sqlglot is None or not isinstance(sql, str) or not sql.strip():
        return None
    try:
        return sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return None


def _fallback_projection(sql: str) -> str:
    match = re.search(r"\bselect\b(.*?)\bfrom\b", sql, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else sql


def _extract_components(sql: str) -> dict[str, set[str]] | None:
    parsed = _parse_sql(sql)
    if parsed is not None and exp is not None:
        return {
            "tables": {
                table.name.lower()
                for table in parsed.find_all(exp.Table)
                if table.name
            },
            "columns": {
                column.name.lower()
                for column in parsed.find_all(exp.Column)
                if column.name
            },
            "joins": {
                normalize_sql(join.sql(dialect="sqlite", pretty=False))
                for join in parsed.find_all(exp.Join)
            },
            "aggregations": {
                aggregation.key.lower()
                for aggregation in parsed.find_all(exp.AggFunc)
            },
        }

    if not isinstance(sql, str) or not sql.strip():
        return None

    projection = _fallback_projection(sql)
    columns = {
        token.lower()
        for token in COLUMN_RE.findall(projection)
        if token.lower() not in SQL_KEYWORDS
    }
    joins = {
        f"{table.lower()}:{normalize_sql(condition or '')}"
        for table, condition in JOIN_RE.findall(sql)
    }
    return {
        "tables": {table.lower() for table in TABLE_RE.findall(sql)},
        "columns": columns,
        "joins": joins,
        "aggregations": {match.lower() for match in AGGREGATION_RE.findall(sql)},
    }


def component_sql_match(predicted_sql: str, gold_sql: str) -> dict[str, bool]:
    predicted = _extract_components(predicted_sql)
    gold = _extract_components(gold_sql)
    if predicted is None or gold is None:
        return {
            "tables": False,
            "columns": False,
            "joins": False,
            "aggregations": False,
        }

    return {
        "tables": predicted["tables"] == gold["tables"],
        "columns": predicted["columns"] == gold["columns"],
        "joins": predicted["joins"] == gold["joins"],
        "aggregations": predicted["aggregations"] == gold["aggregations"],
    }


def component_match_correct(component_match: dict[str, bool]) -> bool:
    return bool(component_match) and all(component_match.values())


def classify_failure(
    predicted_sql: str,
    gold_sql: str,
    *,
    predicted_error: str | None,
    gold_error: str | None,
    execution_correct: bool,
    component_match: dict[str, bool] | None = None,
) -> str | None:
    if execution_correct:
        return None
    if predicted_error or gold_error:
        return "invalid_sql"

    components = component_match or component_sql_match(predicted_sql, gold_sql)
    if not components["tables"]:
        return "wrong_table"
    if not components["joins"]:
        return "wrong_join"
    if not components["aggregations"]:
        return "wrong_aggregation"
    return "wrong_result"


def build_evaluation_fields(
    predicted_sql: str,
    gold_sql: str,
    *,
    predicted_error: str | None,
    gold_error: str | None,
    execution_correct: bool,
) -> dict[str, Any]:
    component_match = component_sql_match(predicted_sql, gold_sql)
    return {
        "sql_valid": predicted_error is None,
        "execution_correct": execution_correct,
        "exact_match": exact_sql_match(predicted_sql, gold_sql),
        "component_match": component_match,
        "component_match_correct": component_match_correct(component_match),
        "failure_type": classify_failure(
            predicted_sql,
            gold_sql,
            predicted_error=predicted_error,
            gold_error=gold_error,
            execution_correct=execution_correct,
            component_match=component_match,
        ),
    }


def build_result_evaluation(
    predicted_sql: str,
    gold_sql: str,
    *,
    predicted_answer: Any,
    gold_answer: Any,
    predicted_error: str | None,
    gold_error: str | None,
) -> dict[str, Any]:
    execution_correct = (
        predicted_error is None
        and gold_error is None
        and is_correct(predicted_answer, gold_answer)
    )
    return {
        "correct": execution_correct,
        **build_evaluation_fields(
            predicted_sql,
            gold_sql,
            predicted_error=predicted_error,
            gold_error=gold_error,
            execution_correct=execution_correct,
        ),
        "error": predicted_error or gold_error,
    }

