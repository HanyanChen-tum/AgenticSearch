"""SQLite bridge exposed to the RLM sandbox as the `db` variable."""

import sqlite3
from pathlib import Path
from typing import Any

MAX_ROWS = 20


class DBEnvironment:
    """Read-only SQLite connection wrapper for RLM agents.

    Injected into the REPL env as `db`. All public methods are accessible
    via RestrictedPython's safer_getattr (no leading underscore).

    Usage inside the sandbox:
        tables = db.get_tables()
        schema = db.get_schema("singer")
        rows   = db.sample_rows("singer", limit=3)
        result = db.execute("SELECT count(*) FROM singer")
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).resolve()
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        self._uri = f"{self.db_path.as_uri()}?mode=ro"
        self._trace: list[dict[str, Any]] = []

    def _record(self, tool: str, **details: Any) -> None:
        self._trace.append({"tool": tool, **details})

    def trace(self) -> list[dict[str, Any]]:
        """Return a copy of database tool calls made during this run."""
        return [dict(item) for item in self._trace]

    def stats(self) -> dict[str, Any]:
        """Return compact schema-exploration and tool-use statistics."""
        inspected_tables = sorted(
            {
                str(item["table"])
                for item in self._trace
                if item["tool"] in {"get_schema", "sample_rows"} and item.get("table")
            }
        )
        inspected_columns: dict[str, list[str]] = {}
        for item in self._trace:
            if item["tool"] != "get_schema" or not item.get("table"):
                continue
            inspected_columns[str(item["table"])] = list(item.get("columns") or [])
        return {
            "tool_calls": len(self._trace),
            "retrieval_calls": sum(
                item["tool"] in {"get_tables", "get_schema"} for item in self._trace
            ),
            "sql_execution_calls": sum(
                item["tool"] == "execute" for item in self._trace
            ),
            "inspected_tables": inspected_tables,
            "inspected_columns": inspected_columns,
        }

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._uri, uri=True)

    # ------------------------------------------------------------------
    # Schema exploration
    # ------------------------------------------------------------------

    def get_tables(self) -> list[str]:
        """Return all table names in the database, sorted alphabetically."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        tables = [row[0] for row in rows]
        self._record("get_tables", tables=tables)
        return tables

    def get_schema(self, table: str) -> dict[str, Any]:
        """Return column definitions and foreign keys for *table*."""
        quoted = _quote(table)
        with self._connect() as conn:
            cols = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
            fks = conn.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()
        if not cols:
            self._record("get_schema", table=table, columns=[], error="not found")
            return {"error": f"Table '{table}' not found"}
        self._record("get_schema", table=table, columns=[c[1] for c in cols])
        return {
            "table": table,
            "columns": [
                {
                    "name": c[1],
                    "type": c[2] or "UNKNOWN",
                    "primary_key": bool(c[5]),
                    "not_null": bool(c[3]),
                }
                for c in cols
            ],
            "foreign_keys": [
                {"column": fk[3], "references": f"{fk[2]}.{fk[4]}"}
                for fk in fks
            ],
        }

    def get_all_schemas(self) -> dict[str, Any]:
        """Return schema for every table — useful for initial context building."""
        return {t: self.get_schema(t) for t in self.get_tables()}

    # ------------------------------------------------------------------
    # Data sampling
    # ------------------------------------------------------------------

    def sample_rows(self, table: str, limit: int = 3) -> dict[str, Any]:
        """Return up to *limit* sample rows (capped at MAX_ROWS)."""
        limit = max(1, min(limit, MAX_ROWS))
        quoted = _quote(table)
        try:
            with self._connect() as conn:
                cursor = conn.execute(f"SELECT * FROM {quoted} LIMIT ?", (limit,))
                columns = [d[0] for d in cursor.description or []]
                rows = [list(r) for r in cursor.fetchall()]
            self._record("sample_rows", table=table, limit=limit, error=None)
            return {"table": table, "columns": columns, "rows": rows, "error": None}
        except sqlite3.Error as e:
            self._record("sample_rows", table=table, limit=limit, error=str(e))
            return {"table": table, "columns": [], "rows": [], "error": str(e)}

    # ------------------------------------------------------------------
    # SQL execution
    # ------------------------------------------------------------------

    def execute(self, sql: str) -> dict[str, Any]:
        """Execute a read-only SQL statement.

        Returns a dict with keys:
          - columns: list of column names
          - rows:    list of rows (each a list), truncated to MAX_ROWS
          - truncated: True if more rows exist than returned
          - error:   error message string, or None on success
        """
        sql = sql.strip()
        try:
            with self._connect() as conn:
                cursor = conn.execute(sql)
                columns = [d[0] for d in cursor.description or []]
                rows = cursor.fetchall()
            truncated = len(rows) > MAX_ROWS
            self._record("execute", sql=sql, error=None)
            return {
                "columns": columns,
                "rows": [list(r) for r in rows[:MAX_ROWS]],
                "truncated": truncated,
                "error": None,
            }
        except sqlite3.Error as e:
            self._record("execute", sql=sql, error=str(e))
            return {"columns": [], "rows": [], "truncated": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def describe(self) -> str:
        """One-line summary of the database for quick orientation."""
        tables = self.get_tables()
        return f"Database: {self.db_path.stem} | Tables ({len(tables)}): {', '.join(tables)}"

    def format_schema(self) -> str:
        """Compact human-readable schema for all tables — safe to put in a prompt."""
        lines = [f"DATABASE: {self.db_path.stem}"]
        for table in self.get_tables():
            info = self.get_schema(table)
            if "error" in info:
                continue
            lines.append(f"\nTABLE: {table}")
            for col in info["columns"]:
                flags = []
                if col["primary_key"]:
                    flags.append("PK")
                if col["not_null"]:
                    flags.append("NOT NULL")
                suffix = f"  [{', '.join(flags)}]" if flags else ""
                lines.append(f"  {col['name']} {col['type']}{suffix}")
            for fk in info["foreign_keys"]:
                lines.append(f"  FK: {fk['column']} → {fk['references']}")
        return "\n".join(lines)


def _quote(identifier: str) -> str:
    """Safely double-quote a SQLite identifier."""
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def get_db_path(database_dir: str | Path, db_id: str) -> Path:
    """Resolve the database file path for a given Spider db_id.

    Tries .sqlite first (Spider default), then falls back to .db.
    """
    base = Path(database_dir) / db_id / db_id
    for ext in (".sqlite", ".db"):
        candidate = base.with_suffix(ext)
        if candidate.exists():
            return candidate
    return base.with_suffix(".sqlite")  # let DBEnvironment raise a clear error
