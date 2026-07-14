"""SQL execution helpers."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any


DEFAULT_QUERY_TIMEOUT_SECONDS = 30.0


def execute_sql(
    db_path: str | Path,
    sql: str,
    *,
    read_only: bool = False,
    timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        path = Path(db_path).resolve()
        connection_target = f"{path.as_uri()}?mode=ro" if read_only else str(path)
        with closing(sqlite3.connect(connection_target, uri=read_only)) as conn:
            deadline = time.monotonic() + timeout_seconds
            conn.set_progress_handler(
                lambda: 1 if time.monotonic() > deadline else 0,
                100_000,
            )
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                result = cursor.fetchall()
            except sqlite3.OperationalError as exc:
                if str(exc).lower() == "interrupted":
                    return {
                        "answer": None,
                        "error": (
                            "SQL execution timed out after "
                            f"{timeout_seconds:g} seconds"
                        ),
                    }
                raise

        return {
            "answer": [list(row) for row in result],
            "error": None,
        }
    except Exception as e:
        return {
            "answer": None,
            "error": str(e),
        }
