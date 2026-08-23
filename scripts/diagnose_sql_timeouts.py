"""Re-execute every question that a `run_one()` scored `correct=False` because
its own SQL execution timed out, with a much longer budget, and check whether
it was actually right.

`predicted_sql` is not necessarily equal to what the model wrote as its final
answer -- it is the SQL that finally executed; the earlier "does the model ever
run its own final query before submitting it" check (this session) found the
answer is no, so a timeout at scoring time is the *first* time this SQL is ever
run to completion, not a retry after seeing feedback. A slow-but-correct query
and a slow-and-wrong query both currently land on `correct=False` with no way
to tell them apart short of running this.

This does not change any recorded result -- it produces a separate diagnostic
file. Whether to fold a confirmed slow-but-correct case back into the official
accuracy is a scoring-policy decision for a human, not something this script
gets to decide by running.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql
from ours.db_environment import get_db_path

BIRD_DB_DIR = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--budget", type=float, default=180.0, help="seconds, per query")
    args = ap.parse_args()

    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
    candidates = [
        r for r in rows
        if r.get("termination") == "final" and "timed out" in str(r.get("error") or "").lower()
    ]
    print(f"{len(candidates)} timeout-masked records in {Path(args.results).name}")

    out_path = Path(args.output)
    out = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else []
    done_ids = {r["id"] for r in out}
    if done_ids:
        print(f"resuming -- {len(done_ids)} already done", flush=True)
    candidates = [r for r in candidates if r["id"] not in done_ids]

    for r in candidates:
        db_path = get_db_path(BIRD_DB_DIR, r["db_id"])
        started = time.perf_counter()
        result = execute_sql(db_path, r["predicted_sql"], read_only=True,
                              timeout_seconds=args.budget)
        elapsed = time.perf_counter() - started
        rec = {
            "id": r["id"], "db_id": r["db_id"], "elapsed_seconds": round(elapsed, 1),
        }
        if result.get("error"):
            rec["diagnosis"] = "still_times_out_or_errors"
            rec["error"] = result.get("error")
        else:
            gold = execute_sql(db_path, r["gold_sql"], read_only=True, timeout_seconds=args.budget)
            correct = (
                gold.get("error") is None
                and is_correct(result.get("answer"), gold.get("answer"))
            )
            rec["diagnosis"] = "slow_but_correct" if correct else "slow_and_wrong"
        out.append(rec)
        # Write after every record: some of these run for minutes, and a batch
        # of them killed partway through must not lose what already finished.
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {r['id']:11s} {rec['elapsed_seconds']:7.1f}s  {rec['diagnosis']}", flush=True)

    n = len(out)
    slow_correct = sum(1 for r in out if r["diagnosis"] == "slow_but_correct")
    slow_wrong = sum(1 for r in out if r["diagnosis"] == "slow_and_wrong")
    still_timed_out = sum(1 for r in out if r["diagnosis"] == "still_times_out_or_errors")
    print(f"\nslow_but_correct: {slow_correct}/{n}   slow_and_wrong: {slow_wrong}/{n}"
          f"   still_times_out(>{args.budget:.0f}s): {still_timed_out}/{n}", flush=True)
    print(f"-> {args.output}", flush=True)


if __name__ == "__main__":
    main()
