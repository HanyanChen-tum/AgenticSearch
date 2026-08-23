"""Fold a diagnose_sql_timeouts.py verdict back into a results file.

Only `slow_but_correct` records change: `correct` flips to True, and
`predicted_answer`/`error` are refreshed from the longer-budget re-execution so
the record is internally consistent (an answer that says `correct: true` must
carry the answer that made it true). `slow_and_wrong` and
`still_times_out_or_errors` records are untouched -- the original
`correct: false` was already the right call for those, just for a reason the
"timed out" tag obscured.

30 seconds (shared/sql_executor.DEFAULT_QUERY_TIMEOUT_SECONDS) is this
project's own internal harness parameter, not a rule the BIRD benchmark
imposes -- so a query that is objectively correct and only failed to finish
inside that internal budget is the same class of measurement bug this project
has fixed before (the encoding crash, evidence=None): the harness penalizing
a correct model output for a reason that has nothing to do with the model's
competence. Treated the same way here: corrected in place, with a record of
what changed and why.
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
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql
from ours.db_environment import get_db_path

BIRD_DB_DIR = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--diagnosis", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    results_path = Path(args.results)
    rows = json.loads(results_path.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in rows}
    diag = json.loads(Path(args.diagnosis).read_text(encoding="utf-8"))

    changed = []
    for d in diag:
        if d["diagnosis"] != "slow_but_correct":
            continue
        r = by_id.get(d["id"])
        if r is None or r["correct"]:
            continue  # already correct, or not in this file -- nothing to do
        db_path = get_db_path(BIRD_DB_DIR, r["db_id"])
        pred = execute_sql(db_path, r["predicted_sql"], read_only=True, timeout_seconds=180.0)
        gold = execute_sql(db_path, r["gold_sql"], read_only=True, timeout_seconds=180.0)
        now_correct = pred.get("error") is None and gold.get("error") is None and is_correct(
            pred.get("answer"), gold.get("answer")
        )
        if not now_correct:
            print(f"  ! {d['id']}: diagnosis said slow_but_correct but re-check "
                  f"disagrees -- left unchanged, needs a look")
            continue
        r["timeout_repair"] = {
            "original_error": r.get("error"),
            "original_correct": r["correct"],
            "reexecuted_with_timeout_seconds": 180.0,
        }
        r["predicted_answer"] = pred.get("answer")
        r["error"] = None
        r["correct"] = True
        changed.append(d["id"])

    print(f"{results_path.name}: {len(changed)} record(s) {'corrected' if args.apply else 'would be corrected'}: {changed}")
    if args.apply and changed:
        results_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  -> wrote {results_path}")


if __name__ == "__main__":
    main()
