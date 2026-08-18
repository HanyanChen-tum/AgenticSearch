"""Gather executable evidence about why a failure failed, before anyone labels it.

Mechanical classification has been wrong four times in this project, so this
script deliberately does not emit a cause. It runs counterfactual repairs on the
model's own SQL and reports which one, if any, makes its answer equal the gold
answer. "Adding COUNT(DISTINCT) makes this query produce the reference result"
is a fact that re-executes; "this is a fan-out error" is a judgement, and stays
with the human.

The distinction matters for the trace work: a failure a convention repair fixes
has no first wrong reasoning sentence to locate. The model reasoned its way to a
query that answers the question and lost on a reference convention. Running a
locator over those forces it to name a sentence that is not there.

Tests, all decided by re-execution or by comparing recorded answers:

  under_projection  gold returns more columns, and the model's rows are exactly
                    gold's rows restricted to a subset of columns
  ties              gold returns several rows, the model returns one, and that
                    row is among gold's -- the LIMIT 1 / ties split
  distinct_repair   rewriting COUNT(x) to COUNT(DISTINCT x) makes it match
  row_superset      the model returns gold's rows plus extras
  row_subset        the model returns some of gold's rows and nothing else
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
from scripts.compare_gold_versions import execute

# COUNT(x) but not COUNT(DISTINCT x) and not COUNT(*)
_COUNT = re.compile(r"\bCOUNT\s*\(\s*(?!DISTINCT\b)(?!\*)", re.I)


def _rows(value):
    if not isinstance(value, list):
        return None
    return [tuple(r) if isinstance(r, (list, tuple)) else (r,) for r in value]


def _as_multiset(rows):
    return sorted(rows)


def under_projection(gold, pred):
    """Model's rows are gold's rows with columns dropped."""
    if not gold or not pred or len(gold) != len(pred):
        return None
    width_g, width_p = len(gold[0]), len(pred[0])
    if width_p >= width_g:
        return None
    from itertools import combinations
    for cols in combinations(range(width_g), width_p):
        if _as_multiset([tuple(r[c] for c in cols) for r in gold]) == _as_multiset(pred):
            return {"gold_columns": width_g, "model_columns": width_p, "kept": list(cols)}
    return None


def ties(gold, pred):
    if not gold or not pred or len(pred) != 1 or len(gold) <= 1:
        return None
    if len(gold[0]) != len(pred[0]):
        return None
    return {"gold_rows": len(gold)} if pred[0] in gold else None


def distinct_repair(db_id, sql, gold):
    if not sql or not _COUNT.search(sql):
        return None
    patched = _COUNT.sub("COUNT(DISTINCT ", sql)
    got = _rows(execute(db_id, patched, 60))
    if got is None:
        return None
    return {"sql": " ".join(patched.split())[:200]} if _as_multiset(got) == _as_multiset(gold) else None


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="results rescored against corrected gold")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
    out = []
    for r in rows:
        if r.get("correct"):
            continue
        gold, pred = _rows(r.get("gold_answer")), _rows(r.get("predicted_answer"))
        rec = {"id": r["id"], "db_id": r["db_id"],
               "gold_rows": None if gold is None else len(gold),
               "model_rows": None if pred is None else len(pred),
               "tests": {}}
        if pred is None:
            rec["tests"]["no_answer"] = {"error": r.get("error")}
        elif gold is not None:
            for name, hit in (
                ("under_projection", under_projection(gold, pred)),
                ("ties", ties(gold, pred)),
                ("distinct_repair", distinct_repair(r["db_id"], r.get("predicted_sql"), gold)),
            ):
                if hit:
                    rec["tests"][name] = hit
            gset, pset = set(gold), set(pred)
            if not rec["tests"] and gset and pset:
                if gset < pset:
                    rec["tests"]["row_superset"] = {"extra": len(pset - gset)}
                elif pset < gset:
                    rec["tests"]["row_subset"] = {"missing": len(gset - pset)}
        out.append(rec)

    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    hit = [r for r in out if r["tests"]]
    print(f"{len(out)} failures, {len(hit)} matched at least one test\n")
    import collections
    c = collections.Counter(k for r in out for k in r["tests"])
    for k, v in c.most_common():
        print(f"  {k:18s} {v}")
    print(f"  {'(no test matched)':18s} {len(out)-len(hit)}")
    print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
