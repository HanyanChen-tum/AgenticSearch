"""SQL execution helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def execute_sql(db_path: str | Path, sql: str) -> dict[str, Any]:
    try:
        with sqlite3.connect(db_path) as conn:
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
