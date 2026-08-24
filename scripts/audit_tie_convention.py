"""Ask whether BIRD's gold is consistent about ties, before anyone writes a rule.

The `ties` failures (the bulk of what the funnel calls `confident_miss`) all have
the same shape: the question is phrased in the singular -- "who is the dumbest
superhero?" -- the model writes ORDER BY ... LIMIT 1, and gold returns every row
tied at the extremum. The tempting fix is a prompt rule telling the model to
return all ties.

This project's own gate says a rule must be checked against the official train
split before it goes anywhere near the system: the "yes/no questions shouldn't
answer with a bare boolean" rule looked perfect on dev (9/9) and turned out to
contradict 29% of train gold. So the question here is not "what should the model
do" but "what does BIRD's gold actually do", measured on 9,428 train examples the
model never trains against.

Gold's tie handling is read off the SQL form, not by execution -- the train
databases are not available locally, and the form is the convention anyway:

  LIMIT1        ORDER BY ... LIMIT 1        gold itself keeps one row, ties lost
  MAX-subquery  WHERE x = (SELECT MAX(...)) gold keeps every tied row
  neither       some other shape (bare MAX() in the projection, window function,
                IN (SELECT ...)); not classified, and excluded from the ratio

The question-side filter is deliberately conservative: a superlative marker must
be present and no explicit plural ask ("top 5", "list all") may be, so that what
remains is the class where the English genuinely reads as asking for one thing.
It is a regex over English text and will misfile some questions; the counts are
meant to establish a lopsided ratio, not a precise rate.

Run it on the dev results too (--results) to get the same split plus the model's
accuracy under each gold convention, which is the number that says whether the
model is the part that is broken.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console

SUPERLATIVE = re.compile(
    r"\b(most|highest|lowest|largest|smallest|greatest|best|worst|longest|shortest"
    r"|fastest|slowest|oldest|youngest|maximum|minimum|max|min|top)\b|\b\w+est\b", re.I)
EXPLICIT_PLURAL = re.compile(
    r"\b(top\s+\d+|list|name all|all the|first \d+|\d+\s+(highest|lowest|most|best)"
    r"|five|three|ten|top-\d+)\b", re.I)
LIMIT1 = re.compile(r"\bLIMIT\s+1\b", re.I)
MAXSUB = re.compile(r"=\s*\(\s*SELECT\s+(MAX|MIN)\s*\(", re.I)


def singular_superlative(question: str) -> bool:
    return bool(SUPERLATIVE.search(question or "")) and not EXPLICIT_PLURAL.search(question or "")


def gold_convention(sql: str) -> str:
    lim, mx = bool(LIMIT1.search(sql or "")), bool(MAXSUB.search(sql or ""))
    if lim and mx:
        return "both"
    if lim:
        return "LIMIT1"
    if mx:
        return "MAX-subquery"
    return "neither"


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-pool", default=str(PROJECT_ROOT / "data/train_pool.json"))
    ap.add_argument("--results", help="a dev results file, to also split accuracy by gold convention")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    report: dict = {}

    pool = json.loads(Path(args.train_pool).read_text(encoding="utf-8"))
    train = [r for r in pool if singular_superlative(r.get("question", ""))]
    tc = collections.Counter(gold_convention(r.get("SQL", "")) for r in train)
    decidable = tc["LIMIT1"] + tc["MAX-subquery"]
    report["train"] = {
        "pool_size": len(pool), "singular_superlative": len(train),
        "by_convention": dict(tc),
        "share_LIMIT1_among_decidable": round(tc["LIMIT1"] / decidable, 4) if decidable else None,
    }
    print(f"train pool {len(pool)} -> singular-superlative {len(train)}")
    for k, v in tc.most_common():
        print(f"    {k:14s} {v:5d}  {v/len(train):6.1%}")
    if decidable:
        print(f"  among the two decidable forms: LIMIT1 {tc['LIMIT1']/decidable:.1%}"
              f" / MAX-subquery {tc['MAX-subquery']/decidable:.1%}")

    if args.results:
        rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
        dev = [r for r in rows if singular_superlative(r.get("question", ""))]
        dc = collections.Counter(gold_convention(r.get("gold_sql", "")) for r in dev)
        acc = {}
        for tag in ("LIMIT1", "MAX-subquery"):
            grp = [r for r in dev
                   if gold_convention(r.get("gold_sql", "")) == tag and r.get("scored", True)]
            ok = sum(1 for r in grp if r.get("correct"))
            acc[tag] = {"n": len(grp), "correct": ok,
                        "accuracy": round(ok / len(grp), 4) if grp else None,
                        "wrong_ids": sorted(r["id"] for r in grp if not r.get("correct"))}
        report["dev"] = {"results_file": args.results, "singular_superlative": len(dev),
                         "by_convention": dict(dc), "accuracy_by_gold_convention": acc}
        print(f"\n{args.results} -> singular-superlative {len(dev)}")
        for k, v in dc.most_common():
            print(f"    {k:14s} {v:5d}  {v/len(dev):6.1%}")
        print("  model accuracy under each gold convention:")
        for tag, a in acc.items():
            if a["n"]:
                print(f"    gold={tag:14s} n={a['n']:3d}  correct {a['correct']:3d}"
                      f"  ({a['accuracy']:.1%})")

    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
