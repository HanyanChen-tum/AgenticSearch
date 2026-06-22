"""SQL execution helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def execute_sql(
    db_path: str | Path,
    sql: str,
    *,
    read_only: bool = False,
) -> dict[str, Any]:
    try:
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

