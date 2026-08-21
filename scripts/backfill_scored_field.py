"""Add `scored` to result files written before shared.evaluator.MODEL_TERMINATIONS
existed, without re-running anything.

Every value needed is already recorded: `scored` is a pure function of
`termination`, which every run_one() has always written. This backfills that
one field from data already on disk so the whole repository's results share
one schema, instead of every analysis script re-deriving the same harness/
model split by hand (which is what purge_harness_crash_records.py,
triage_failure_causes.py, and this project's ad-hoc analyses have all done
independently up to now).

Records that predate `termination` itself (the baseline scripts, before this
same pass added it) are handled by the one signal available: a non-empty
`predicted_sql` means the LLM call itself returned, so `termination="final"`
is safe to infer regardless of whether the SQL then executed correctly --
that is a real model result, not a harness failure. A record with no
`termination` AND no `predicted_sql` cannot be classified this way (the only
observed crash before `termination` existed, evidence=None on bird_1507/
bird_1528, always produced empty predicted_sql) and is left alone with a
warning printed.

Dry run by default; --apply writes.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console
from shared.evaluator import is_scored


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=str(PROJECT_ROOT / "results/*.json"))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    touched = skipped = 0
    for raw in sorted(glob.glob(args.glob)):
        p = Path(raw)
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            continue
        if all("scored" in r for r in rows):
            continue  # already backfilled or written by the patched runner
        if not any("termination" in r or r.get("predicted_sql") for r in rows):
            skipped += 1
            continue

        changed = unclassifiable = 0
        for r in rows:
            if "scored" in r:
                continue
            term = r.get("termination")
            if term is None:
                if not r.get("predicted_sql"):
                    unclassifiable += 1
                    continue
                term = "final"
                r["termination"] = term
            r["scored"] = is_scored(term)
            changed += 1
        if unclassifiable:
            print(f"  ! {p.name}: {unclassifiable} record(s) have neither "
                  f"`termination` nor `predicted_sql` -- left unscored, check by hand")
        if not changed:
            continue
        n_false = sum(1 for r in rows if not r.get("scored", True))
        touched += 1
        verb = "backfilled" if args.apply else "would backfill"
        print(f"{p.name}: {verb} {changed} row(s) (scored=False: {n_false}/{len(rows)})")
        if args.apply:
            p.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{touched} files touched, {skipped} skipped (no `termination` field)")
    if not args.apply:
        print("dry run -- pass --apply to write")


if __name__ == "__main__":
    main()
