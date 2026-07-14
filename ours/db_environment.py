"""SQLite bridge exposed to the RLM sandbox as the `db` variable."""

import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

MAX_ROWS = 20
QUERY_TIMEOUT_S = 30  # abort any single query after this long (runaway JOINs)


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

    def __init__(
        self,
        db_path: str | Path,
        event_sink: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
    ):
        self.db_path = Path(db_path).resolve()
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        self._uri = f"{self.db_path.as_uri()}?mode=ro"
        self._event_sink = event_sink

    def _emit(self, tool: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(tool, arguments, result)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._uri, uri=True)
        deadline = time.monotonic() + QUERY_TIMEOUT_S
        # Nonzero return aborts the running query with "interrupted";
        # checked every N sqlite VM ops, so it also stops runaway JOINs.
        conn.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0, 100_000
        )
        return conn

    # ------------------------------------------------------------------
    # Schema exploration
    # ------------------------------------------------------------------

    def get_tables(self) -> list[str]:
        """Return all table names in the database, sorted alphabetically."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        return [row[0] for row in rows]

    def get_schema(self, table: str) -> dict[str, Any]:
        """Return column definitions and foreign keys for *table*."""
        quoted = _quote(table)
        with closing(self._connect()) as conn:
            cols = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
            fks = conn.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()
        if not cols:
            return {"error": f"Table '{table}' not found"}
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
            with closing(self._connect()) as conn:
                cursor = conn.execute(f"SELECT * FROM {quoted} LIMIT ?", (limit,))
                columns = [d[0] for d in cursor.description or []]
                rows = [list(r) for r in cursor.fetchall()]
            result = {"table": table, "columns": columns, "rows": rows, "error": None}
        except sqlite3.Error as e:
            result = {"table": table, "columns": [], "rows": [], "error": str(e)}
        self._emit("db.sample_rows", {"table": table, "limit": limit}, result)
        return result

    def sample_values(self, table: str, column: str, limit: int = 10) -> dict[str, Any]:
        """Return distinct sample values for a column — use this to discover actual string values."""
        limit = max(1, min(limit, MAX_ROWS))
        schema = self.get_schema(table)
        if "error" in schema:
            result = {"table": table, "column": column, "values": [], "error": schema["error"]}
            self._emit("db.sample_values", {"table": table, "column": column, "limit": limit}, result)
            return result
        column_names = {
            item["name"].casefold(): item["name"] for item in schema["columns"]
        }
        actual_column = column_names.get(column.casefold())
        if actual_column is None:
            result = {
                "table": table,
                "column": column,
                "values": [],
                "error": f"Column '{column}' not found in table '{table}'",
            }
            self._emit("db.sample_values", {"table": table, "column": column, "limit": limit}, result)
            return result
        quoted_t = _quote(table)
        quoted_c = _quote(actual_column)
        try:
            with closing(self._connect()) as conn:
                cursor = conn.execute(
                    f"SELECT DISTINCT {quoted_c} FROM {quoted_t} WHERE {quoted_c} IS NOT NULL LIMIT ?",
                    (limit,)
                )
                rows = [r[0] for r in cursor.fetchall()]
            result = {"table": table, "column": column, "values": rows, "error": None}
        except sqlite3.Error as e:
            result = {"table": table, "column": column, "values": [], "error": str(e)}
        self._emit("db.sample_values", {"table": table, "column": column, "limit": limit}, result)
        return result

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
            with closing(self._connect()) as conn:
                cursor = conn.execute(sql)
                columns = [d[0] for d in cursor.description or []]
                rows = cursor.fetchall()
            truncated = len(rows) > MAX_ROWS
            result = {
                "columns": columns,
                "rows": [list(r) for r in rows[:MAX_ROWS]],
                "truncated": truncated,
                "error": None,
            }
        except sqlite3.Error as e:
            result = {"columns": [], "rows": [], "truncated": False, "error": str(e)}
        self._emit("db.execute", {"sql": sql}, result)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def describe(self) -> str:
        """One-line summary of the database for quick orientation."""
        tables = self.get_tables()
        return f"Database: {self.db_path.stem} | Tables ({len(tables)}): {', '.join(tables)}"

    def format_schema(self) -> str:
        """Schema with 2 sample values per column — helps model understand data formats and column semantics."""
        conn = self._connect()
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
                suffix = f" [{', '.join(flags)}]" if flags else ""
                # Add sample values (skip PK-only integer columns to save tokens)
                sample_str = ""
                if not col["primary_key"]:
                    try:
                        rows = conn.execute(
                            f'SELECT DISTINCT "{col["name"]}" FROM "{table}" '
                            f'WHERE "{col["name"]}" IS NOT NULL LIMIT 2'
                        ).fetchall()
                        if rows:
                            samples = []
                            for r in rows:
                                v = r[0]
                                if isinstance(v, str) and len(v) > 30:
                                    v = v[:27] + "..."
                                samples.append(repr(v))
                            sample_str = f"  e.g. {', '.join(samples)}"
                    except Exception:
                        pass
                lines.append(f"  {col['name']} ({col['type']}){suffix}{sample_str}")
            for fk in info["foreign_keys"]:
                lines.append(f"  FK: {fk['column']} → {fk['references']}")
        conn.close()
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
