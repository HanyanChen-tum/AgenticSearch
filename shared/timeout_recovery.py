"""Recovery for scoring-time SQL executions that hit the timeout budget.

`execute_sql` at scoring time can time out not because a query is wrong, but
because the raw BIRD dev databases carry almost no secondary indexes on
foreign-key-style join columns (Player_Attributes.player_api_id,
legalities.uuid, comments.PostId, ... all had zero indexes as shipped). A
query that joins or correlates through one of those columns degrades to an
O(n*m) nested scan. Confirmed directly: a correlated-EXISTS query for
bird_1148 took 262s unindexed and returned the exact gold answer -- it was
never wrong, just physically slow against an unindexed table. Raising
DEFAULT_QUERY_TIMEOUT_SECONDS (30s -> 180s, 2026-08-24) does not fully cover
this on its own; some genuine answers need more than 180s unindexed.

An index never changes a query's result, only its speed, so retrying a
timed-out query against a throwaway indexed copy of the same db file
recovers the answer the query would have produced given a fair amount of
time -- without altering the benchmark database files (never written back;
built fresh under the system temp dir) and without guessing at a rewrite of
the model's SQL. This is the automatic, run-time version of the one-off
backfill in scripts/apply_timeout_diagnosis.py and the 2026-08-24 indexed
diagnosis pass (docs/analysis/week_2026-08-18/) -- it exists so future runs
don't need another backfill sweep to avoid the same measurement bug.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from shared.sql_executor import DEFAULT_QUERY_TIMEOUT_SECONDS, execute_sql

RECOVERY_TIMEOUT_SECONDS = 60.0
_CACHE_ROOT = Path(tempfile.gettempdir()) / "agentic_search_timeout_recovery"


def _extract_table_aliases(sql: str) -> dict[str, str]:
    # Only explicit "AS alias" is recognized -- a bare-word implicit alias
    # (`FROM a b`) risks the regex swallowing the next clause's keyword
    # (`FROM a JOIN` reading "JOIN" as a's alias) and skipping that table.
    alias_map: dict[str, str] = {}
    for m in re.finditer(r"\b(?:FROM|JOIN)\s+([A-Za-z_]\w*)(?:\s+AS\s+([A-Za-z_]\w*))?", sql, re.IGNORECASE):
        table, alias = m.group(1), m.group(2)
        if alias:
            alias_map[alias] = table
        alias_map[table] = table
    return alias_map


def _extract_join_columns(sql: str) -> set[tuple[str, str]]:
    alias_map = _extract_table_aliases(sql)
    cols = set()
    for m in re.finditer(r"(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)", sql):
        a, ac, b, bc = m.groups()
        if a in alias_map:
            cols.add((alias_map[a], ac))
        if b in alias_map:
            cols.add((alias_map[b], bc))
    return cols


def _existing_indexed_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    covered = set()
    for (idx_name,) in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?", (table,)
    ).fetchall():
        info = cur.execute(f"PRAGMA index_info({idx_name!r})").fetchall()
        if info:
            covered.add(info[0][2])  # leading column of the index
    return covered


def _indexed_copy(db_path: Path, hint_sql: str) -> Path:
    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    dst = _CACHE_ROOT / f"{db_path.stem}.sqlite"
    if not dst.exists():
        shutil.copyfile(db_path, dst)
    conn = sqlite3.connect(str(dst))
    try:
        cur = conn.cursor()
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, col in _extract_join_columns(hint_sql):
            if table not in tables or col in _existing_indexed_columns(cur, table):
                continue
            try:
                cur.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_{col}" ON "{table}"("{col}")')
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()
    return dst


def execute_sql_with_recovery(
    db_path,
    sql: str,
    *,
    read_only: bool = True,
    timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
    recovery_timeout_seconds: float = RECOVERY_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Same contract as `execute_sql`, plus a `recovered_via_index` flag.

    On a timeout, retries once against a throwaway indexed copy of the same
    db file (never written back to the original) before giving up. The flag
    records whether the returned answer needed recovery to obtain, so
    callers can keep it in the scored record rather than silently blending
    it in.
    """
    result = execute_sql(db_path, sql, read_only=read_only, timeout_seconds=timeout_seconds)
    if result.get("error") is None or "timed out" not in str(result["error"]).lower():
        result["recovered_via_index"] = False
        return result

    indexed_path = _indexed_copy(Path(db_path), sql)
    recovered = execute_sql(indexed_path, sql, read_only=True, timeout_seconds=recovery_timeout_seconds)
    if recovered.get("error") is not None:
        # Recovery didn't help either -- a genuine execution-cost problem,
        # not a measurement artifact. Keep the original timeout result.
        result["recovered_via_index"] = False
        return result
    recovered["recovered_via_index"] = True
    return recovered
