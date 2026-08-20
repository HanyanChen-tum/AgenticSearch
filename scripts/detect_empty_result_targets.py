"""Offline detector for the E6 recursion trigger: does the final SQL return an
empty set / all-NULL / an execution error?

This is the harness-deterministic part of `rootcause/e6_recursion_2026-08-09.md`'s
design -- runtime-checkable, no gold needed. The implementation that consumed
this signal (feed it back as text, or force a structural constraint) was never
committed to this repository; full-text and git-history search both come back
empty. Rebuilding that part is real engineering, not a rerun, so before
committing to it this asks the cheaper question first: on the current
population, how many questions would even have a target.

No LLM calls -- reruns each row's already-recorded `predicted_sql` against the
database and classifies the result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console
from shared.sql_executor import execute_sql
from ours.db_environment import get_db_path

BIRD_DB_DIR = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"


def is_empty(result: dict) -> bool:
    if result.get("error"):
        return True
    rows = result.get("answer")
    if not rows:
        return True
    return all(v is None for row in rows for v in (row if isinstance(row, (list, tuple)) else [row]))


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--ids", default=None, help="JSON list of ids to restrict to")
    args = ap.parse_args()

    rows = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    keep = set(json.loads(Path(args.ids).read_text(encoding="utf-8"))) if args.ids else set(rows)

    targets = []
    for qid in sorted(keep & set(rows)):
        r = rows[qid]
        sql = r.get("predicted_sql")
        if not sql or r.get("correct"):
            continue
        db_path = get_db_path(BIRD_DB_DIR, r["db_id"])
        result = execute_sql(db_path, sql, read_only=True)
        if is_empty(result):
            targets.append(qid)

    print(f"scanned {len(keep & set(rows))} failures, {len(targets)} have the empty-set trigger")
    print(f"  {targets}")


if __name__ == "__main__":
    main()
