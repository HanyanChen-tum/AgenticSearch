"""SQL execution helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


READ_ONLY_PREFIXES = ("select", "with", "pragma", "explain")


def normalize_sql_text(sql: str) -> str:
    """Clean common LLM string-literal artifacts before SQLite execution."""
    cleaned = (sql or "").strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    return (
        cleaned.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\'", "'")
    ).strip()


def is_read_only_sql(sql: str) -> bool:
    stripped = normalize_sql_text(sql).lower()
    return stripped.startswith(READ_ONLY_PREFIXES)


def execute_sql(
    db_path: str | Path,
    sql: str,
    *,
    read_only: bool = True,
) -> dict[str, Any]:
    try:
        sql = normalize_sql_text(sql)
        if read_only and not is_read_only_sql(sql):
            return {
                "answer": None,
                "error": "Only read-only SQL statements are allowed.",
                "executed_sql": sql,
            }

        path = Path(db_path).resolve()
        connection_target = f"{path.as_uri()}?mode=ro" if read_only else str(path)
        with sqlite3.connect(connection_target, uri=read_only) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            result = cursor.fetchall()

        return {
            "answer": [list(row) for row in result],
            "error": None,
            "executed_sql": sql,
        }
    except Exception as e:
        return {
            "answer": None,
            "error": str(e),
            "executed_sql": sql,
        }
