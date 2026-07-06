"""SQL execution helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


READ_ONLY_PREFIXES = ("select", "with", "pragma", "explain")


def is_read_only_sql(sql: str) -> bool:
    stripped = sql.strip().lower()
    return stripped.startswith(READ_ONLY_PREFIXES)


def execute_sql(
    db_path: str | Path,
    sql: str,
    *,
    read_only: bool = True,
) -> dict[str, Any]:
    try:
        if read_only and not is_read_only_sql(sql):
            return {
                "answer": None,
                "error": "Only read-only SQL statements are allowed.",
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
        }
    except Exception as e:
        return {
            "answer": None,
            "error": str(e),
        }
