"""Rescore result files with the official BIRD protocol (set comparison).

Official BIRD evaluation.py uses `set(predicted_res) == set(ground_truth_res)`,
ignoring duplicate rows and row order. Our earlier runs were scored with a
stricter sorted-list comparison; this script re-executes pred/gold SQL for
answers marked wrong and flips those that match under the official protocol.
"""

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_DIR = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"


def run_sql(db_id: str, sql: str, timeout_s: float = 30.0):
    p = (DB_DIR / db_id / f"{db_id}.sqlite").resolve()
    conn = sqlite3.connect(f"{p.as_uri()}?mode=ro", uri=True, timeout=timeout_s)
    conn.execute(f"PRAGMA busy_timeout = {int(timeout_s * 1000)}")
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def rescore(fname: str, name: str):
    results = json.loads(Path(fname).read_text())
    strict = sum(1 for r in results if r["correct"])
    official = strict
    flipped = []
    for r in results:
        if r["correct"] or not r.get("predicted_sql"):
            continue
        try:
            pr = run_sql(r["db_id"], r["predicted_sql"])
            gr = run_sql(r["db_id"], r["gold_sql"])
        except Exception:
            continue
        if set(map(tuple, pr)) == set(map(tuple, gr)):
            official += 1
            flipped.append(r["id"])
    t = len(results)
    print(
        f"{name}: strict {strict}/{t}={strict/t:.2%} -> "
        f"official {official}/{t}={official/t:.2%} (+{len(flipped)})",
        flush=True,
    )
    if flipped:
        print(f"  flipped: {flipped}", flush=True)


if __name__ == "__main__":
    files = [
        ("results/bird_schema_samples_500.json", "SchemaFix"),
        ("results/bird_indomain_fewshot_500.json", "InDomain"),
        ("results/bird_sc_indomain_500.json", "SC-InDomain"),
        ("results/bird_b1_azure_500.json", "B1"),
        ("results/bird_b2_azure_500.json", "B2"),
    ]
    for f, n in files:
        if Path(f).exists():
            rescore(f, n)
