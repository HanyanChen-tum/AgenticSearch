"""Gold-schema extraction and schema selection metrics for Text-to-SQL."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlglot import exp, parse_one
from sqlglot.optimizer.qualify import qualify


def load_sqlite_schema(db_path: str | Path) -> dict[str, dict[str, str]]:
    path = Path(db_path).resolve()
    schema: dict[str, dict[str, str]] = {}
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as connection:
        tables = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        for (table,) in tables:
            quoted = table.replace('"', '""')
            columns = connection.execute(
                f'PRAGMA table_info("{quoted}")'
            ).fetchall()
            schema[table] = {
                str(column[1]): str(column[2] or "UNKNOWN") for column in columns
            }
    return schema


def extract_gold_schema(
    gold_sql: str,
    db_path: str | Path,
) -> dict[str, Any]:
    """Extract physical tables and qualified columns from a SQLite gold query."""
    schema = load_sqlite_schema(db_path)
    expression = parse_one(gold_sql, read="sqlite")
    try:
        expression = qualify(
            expression,
            dialect="sqlite",
            schema=schema,
            identify=False,
            validate_qualify_columns=False,
        )
    except Exception:
        # Parsing still provides reliable table names and many qualified columns.
        pass

    cte_names = {cte.alias_or_name for cte in expression.find_all(exp.CTE)}
    alias_to_table: dict[str, str] = {}
    tables: set[str] = set()
    for table in expression.find_all(exp.Table):
        table_name = table.name
        if table_name in cte_names or table_name not in schema:
            continue
        tables.add(table_name)
        alias_to_table[table.alias_or_name] = table_name
        alias_to_table[table_name] = table_name

    columns: set[tuple[str, str]] = set()
    unresolved: set[str] = set()
    for column in expression.find_all(exp.Column):
        column_name = column.name
        qualifier = column.table
        if qualifier:
            table_name = alias_to_table.get(qualifier, qualifier)
            if table_name in schema and column_name in schema[table_name]:
                columns.add((table_name, column_name))
            continue
        candidates = [
            table_name
            for table_name in tables
            if column_name in schema.get(table_name, {})
        ]
        if len(candidates) == 1:
            columns.add((candidates[0], column_name))
        elif len(candidates) > 1:
            unresolved.add(column_name)

    return {
        "tables": sorted(tables),
        "columns": [
            {"table": table, "column": column}
            for table, column in sorted(columns)
        ],
        "unresolved_columns": sorted(unresolved),
    }


def calculate_schema_metrics(
    gold_schema: dict[str, Any],
    selected_tables: list[str],
    selected_columns: list[dict[str, Any]],
) -> dict[str, Any]:
    gold_tables = set(gold_schema.get("tables") or [])
    gold_columns = {
        (str(item["table"]), str(item["column"]))
        for item in gold_schema.get("columns") or []
    }
    selected_table_set = set(selected_tables)
    selected_column_set = {
        (str(item["table"]), str(item["column"]))
        for item in selected_columns
    }

    table_hits = gold_tables & selected_table_set
    column_hits = gold_columns & selected_column_set
    table_recall = len(table_hits) / len(gold_tables) if gold_tables else 1.0
    column_recall = len(column_hits) / len(gold_columns) if gold_columns else 1.0
    precision = (
        len(column_hits) / len(selected_column_set)
        if selected_column_set
        else (1.0 if not gold_columns else 0.0)
    )
    f1 = (
        2 * precision * column_recall / (precision + column_recall)
        if precision + column_recall
        else 0.0
    )
    return {
        "gold_schema": gold_schema,
        "selected_table_count": len(selected_table_set),
        "selected_column_count": len(selected_column_set),
        "table_recall": round(table_recall, 6),
        "column_recall": round(column_recall, 6),
        "strict_schema_recall": (
            gold_tables <= selected_table_set and gold_columns <= selected_column_set
        ),
        "schema_precision": round(precision, 6),
        "schema_f1": round(f1, 6),
        "missing_tables": sorted(gold_tables - selected_table_set),
        "missing_columns": [
            {"table": table, "column": column}
            for table, column in sorted(gold_columns - selected_column_set)
        ],
    }
