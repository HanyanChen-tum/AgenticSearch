"""Record the funnel from a results file down to Phase A's candidate population.

The classification order matters and is fixed here, matching
triage_failure_causes.py's own precedence (a record is placed in the first
category it matches, scanning top to bottom):

  no_answer          predicted_answer is None -- hard fact, no judgement
  confident_miss     ties / under_projection / distinct_repair -- all three
                      re-execute or do exhaustive column-subset/rewrite
                      comparison; this is the "model doesn't know it's wrong"
                      class (reasoning volume 0.79x of correct answers)
  shape_miss         column_permutation / concat_columns -- same evidence
                      standard, different reasoning-volume signature (1.94x)
  rowset             row_superset / row_subset -- pure set comparison,
                      catch-all among the executable checks
  ratio_formula      NOT executed -- a regex match on SQL text shape
                      (CAST(...AS REAL)/, SUM(...)/(COUNT|SUM)) on gold, and a
                      bare "/" on the prediction. Detects "looks like a
                      numerator/denominator question", does not verify which
                      denominator is correct -- doing that mechanically was
                      judged too close to the already-disabled
                      count_no_distinct post-processing rule's failure mode.
  other              none of the above matched; this is what Phase A draws
                      its candidates from

This is a record-keeping script, not a new method -- it just writes down, for
one results file, exactly which count each category got and why a given
question landed where it did, instead of leaving that arithmetic to be
recomputed by hand in conversation each time someone asks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console

CONFIDENT = {"ties", "under_projection", "distinct_repair"}
SHAPE = {"column_permutation", "concat_columns"}
ROWSET = {"row_superset", "row_subset"}
RATIO = re.compile(
    r"(CAST\s*\(.*?AS\s+REAL\).*?/|SUM\s*\([^)]*\).*?/.*?(COUNT|SUM)|COUNT\s*\([^)]*\).*?/.*?COUNT)",
    re.I | re.S,
)


def classify(rr: dict, tri: dict | None) -> str:
    cats = set((tri or {}).get("tests", {}))
    if "no_answer" in cats:
        return "no_answer"
    if cats & CONFIDENT:
        return "confident_miss"
    if cats & SHAPE:
        return "shape_miss"
    if cats & ROWSET:
        return "rowset"
    if RATIO.search(rr.get("gold_sql") or "") and "/" in (rr.get("predicted_sql") or ""):
        return "ratio_formula"
    return "other"


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--triage", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    res = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    tri = {t["id"]: t for t in json.loads(Path(args.triage).read_text(encoding="utf-8"))}

    total = len(res)
    unscored = [q for q, r in res.items() if not r.get("scored", True)]
    correct = [q for q, r in res.items() if r.get("scored", True) and r["correct"]]
    wrong = [q for q, r in res.items() if r.get("scored", True) and not r["correct"]]

    by_cat: dict[str, list[str]] = {}
    for q in wrong:
        cat = classify(res[q], tri.get(q))
        by_cat.setdefault(cat, []).append(q)

    summary = {
        "results_file": args.results,
        "total_questions": total,
        "unscored_harness_fault": len(unscored),
        "unscored_ids": unscored,
        "scored": total - len(unscored),
        "correct": len(correct),
        "wrong": len(wrong),
        "by_category": {k: {"n": len(v), "ids": sorted(v)} for k, v in by_cat.items()},
        "other_ids": sorted(by_cat.get("other", [])),
    }
    Path(args.output).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{args.results}")
    print(f"  total={total}  unscored(harness)={len(unscored)}  scored={total-len(unscored)}")
    print(f"  correct={len(correct)}  wrong={len(wrong)}")
    for cat in ("no_answer", "confident_miss", "shape_miss", "rowset", "ratio_formula", "other"):
        print(f"    {cat:16s} {len(by_cat.get(cat, []))}")
    print(f"-> {args.output}")


if __name__ == "__main__":
    main()
