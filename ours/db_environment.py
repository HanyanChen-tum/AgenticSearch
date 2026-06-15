"""Read-only database tools exposed to recursive agents."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


READ_ONLY_SQL = re.compile(r"^\s*(SELECT|WITH|EXPLAIN)\b", re.IGNORECASE)


class DatabaseEnvironment:
    """A bounded, read-only interface over one SQLite database."""

    def __init__(self, db_path: str | Path, max_rows: int = 20) -> None:
        self.db_path = Path(db_path)
        self.max_rows = max_rows
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def list_tables(self) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return {"tables": [row[0] for row in rows]}

    def describe_table(self, table: str) -> dict[str, Any]:
        self._require_table(table)
        quoted = self._quote_identifier(table)
        with self._connect() as conn:
            columns = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
            foreign_keys = conn.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()

        return {
            "table": table,
            "columns": [
                {
                    "name": row[1],
                    "type": row[2] or "UNKNOWN",
                    "not_null": bool(row[3]),
                    "default": row[4],
                    "primary_key": bool(row[5]),
                }
                for row in columns
            ],
            "foreign_keys": [
                {
                    "from": row[3],
                    "to_table": row[2],
                    "to_column": row[4],
                }
                for row in foreign_keys
            ],
        }

    def sample_rows(self, table: str, limit: int = 5) -> dict[str, Any]:
        self._require_table(table)
        bounded_limit = max(1, min(limit, self.max_rows))
        quoted = self._quote_identifier(table)
        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT * FROM {quoted} LIMIT ?",
                (bounded_limit + 1,),
            )
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description or []]
        return {
            "table": table,
            "columns": columns,
            "rows": [list(row) for row in rows[:bounded_limit]],
            "truncated": len(rows) > bounded_limit,
        }

    def execute_sql(self, sql: str) -> dict[str, Any]:
        return self._execute_sql(sql, row_limit=self.max_rows)

    def execute_sql_full(self, sql: str) -> dict[str, Any]:
        """Execute final SQL read-only without truncating its answer rows."""
        return self._execute_sql(sql, row_limit=None)

    def _execute_sql(
        self,
        sql: str,
        *,
        row_limit: int | None,
    ) -> dict[str, Any]:
        statement = sql.strip()
        if not READ_ONLY_SQL.match(statement):
            return {
                "columns": [],
                "rows": None,
                "error": "Only read-only SELECT, WITH, or EXPLAIN queries are allowed",
                "truncated": False,
            }

        try:
            with self._connect() as conn:
                cursor = conn.execute(statement)
                rows = (
                    cursor.fetchall()
                    if row_limit is None
                    else cursor.fetchmany(row_limit + 1)
                )
                columns = [description[0] for description in cursor.description or []]
            truncated = row_limit is not None and len(rows) > row_limit
            return {
                "columns": columns,
                "rows": [
                    list(row)
                    for row in (rows if row_limit is None else rows[:row_limit])
                ],
                "error": None,
                "truncated": truncated,
            }
        except sqlite3.Error as exc:
            return {
                "columns": [],
                "rows": None,
                "error": str(exc),
                "truncated": False,
            }

    def _require_table(self, table: str) -> None:
        if table not in self.list_tables()["tables"]:
            raise ValueError(f"Unknown table: {table}")

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'
