"""What would happen if this class of question never used ``LIMIT 1``?

`audit_tie_convention.py` established the ratio: among BIRD train golds that are
decidable, 90% drop ties via ``ORDER BY ... LIMIT 1`` and 10% keep them via
``WHERE x = (SELECT MAX(x) ...)``, and on dev that split costs 44pp of accuracy.
The natural follow-up -- "so just always return the ties" -- was rejected on the
ratio alone (docs/analysis/week_2026-08-18/tie_convention_audit_2026-08-24.md).

That rejection is directionally right but incomplete, because the two conventions
only *disagree when a tie actually exists in the data*. On a question whose
extremum is unique, ``ORDER BY x DESC LIMIT 1`` and ``WHERE x = (SELECT MAX(x))``
return exactly the same single row, and the rule is free. So the real cost of the
rule is not "90% of questions" -- it is "the subset of those where the data
happens to tie", which is an empirical quantity nobody has measured.

This script measures it. For every dev singular-superlative question whose gold
uses the LIMIT-1 convention, it re-executes the gold's own ORDER BY key without
the LIMIT and counts how many rows sit at the extreme:

    ties == 1  -> the rule would change nothing here (free)
    ties >  1  -> the rule would turn a passing answer into a failing one (cost)

Emits per-question facts only; the trade-off itself is left to the reader.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import sqlglot
from sqlglot import exp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ours.db_environment import get_db_path  # noqa: E402
from scripts.run_bird_indomain_fewshot import BIRD_DB_DIR  # noqa: E402
from shared.console import force_utf8_console  # noqa: E402
from shared.sql_executor import execute_sql  # noqa: E402

LIMIT1 = re.compile(r"\bLIMIT\s+1\b", re.I)
MAXSUB = re.compile(r"=\s*\(\s*SELECT\s+(MAX|MIN)\s*\(", re.I)
SUPERLATIVE = re.compile(
    r"\b(most|least|highest|lowest|largest|smallest|greatest|maximum|minimum|"
    r"max|min|oldest|youngest|longest|shortest|best|worst|top|strongest|fastest|"
    r"cheapest|biggest|earliest|latest)\b", re.I)
PLURAL_ASK = re.compile(
    r"\b(top\s+\d+|list\s+all|all\s+the|names\s+of\s+the|every|each\s+of)\b", re.I)


def singular_superlative(question: str) -> bool:
    q = question or ""
    return bool(SUPERLATIVE.search(q)) and not PLURAL_ASK.search(q)


def gold_convention(sql: str) -> str:
    lim, mx = bool(LIMIT1.search(sql or "")), bool(MAXSUB.search(sql or ""))
    if lim and mx:
        return "both"
    if lim:
        return "LIMIT1"
    if mx:
        return "MAX-subquery"
    return "neither"


def tie_probe(gold_sql: str) -> tuple[str | None, str | None]:
    """Build a query counting how many rows sit at the gold's ORDER BY extreme.

    Returns (probe_sql, None) or (None, reason_it_could_not_be_built). The probe
    keeps the gold's own FROM/JOIN/WHERE/GROUP BY intact and only replaces the
    projection with the ORDER BY key, so it measures ties under exactly the
    conditions the gold itself imposes -- not an approximation of them.
    """
    try:
        tree = sqlglot.parse_one(gold_sql, dialect="sqlite")
    except Exception as exc:  # noqa: BLE001 - unparseable gold is a fact, not a crash
        return None, f"unparseable: {type(exc).__name__}"
    if not isinstance(tree, exp.Select):
        return None, "not a plain SELECT"

    order = tree.args.get("order")
    if not order or len(order.expressions) != 1:
        # Multi-key ORDER BY means the gold already broke ties deliberately
        # (e.g. bird_189: "with ties broken by district average salary"), so the
        # question is not in the ambiguous class at all.
        return None, "no ORDER BY" if not order else "multi-key ORDER BY (ties already broken)"

    ordered = order.expressions[0]
    key = ordered.this
    # Which end is "the extremum" depends on the sort direction, and SQLite's
    # default is ASC. Taking MAX unconditionally measures ties at the wrong end
    # for every "oldest / lowest / earliest" question -- bird_1238 asks for the
    # oldest patient (ORDER BY Birthday ASC) and a MAX probe counts ties among
    # the *youngest* instead, which is how this was caught.
    agg = "MAX" if ordered.args.get("desc") else "MIN"

    probe = tree.copy()
    probe.set("order", None)
    probe.set("limit", None)
    probe.set("expressions", [exp.alias_(key.copy(), "k")])

    outer = exp.select("COUNT(*) AS n").from_(
        exp.Subquery(this=probe, alias=exp.TableAlias(this=exp.to_identifier("t")))
    ).where(f"k = (SELECT {agg}(k) FROM (" + probe.sql(dialect='sqlite') + "))")
    return outer.sql(dialect="sqlite"), None


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="a scored dev results file")
    ap.add_argument("--database-dir", default=str(BIRD_DB_DIR))
    ap.add_argument("--output", required=True)
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
    pool = [r for r in rows
            if singular_superlative(r.get("question", ""))
            and gold_convention(r.get("gold_sql", "")) == "LIMIT1"]

    out, tally = [], collections.Counter()
    for r in pool:
        probe, why = tie_probe(r.get("gold_sql", ""))
        rec = {"id": r["id"], "db_id": r["db_id"], "question": r.get("question"),
               "model_was_correct": r.get("correct"), "gold_sql": r.get("gold_sql")}
        if probe is None:
            rec["ties"], rec["skipped"] = None, why
            tally[f"skipped: {why}"] += 1
        else:
            res = execute_sql(get_db_path(Path(args.database_dir), r["db_id"]), probe,
                              timeout_seconds=args.timeout)
            if res["error"] or not res["answer"]:
                rec["ties"], rec["skipped"] = None, f"probe failed: {res['error']}"
                tally["skipped: probe failed"] += 1
            else:
                n = res["answer"][0][0]
                rec["ties"] = n
                tally["would break (ties > 1)" if n > 1 else "unaffected (unique extremum)"] += 1
        out.append(rec)
        print(f"  {rec['id']:<12} ties={rec.get('ties')} {rec.get('skipped','')}")

    measured = sum(v for k, v in tally.items() if not k.startswith("skipped"))
    broke = tally["would break (ties > 1)"]
    report = {
        "results_file": args.results,
        "pool": len(pool),
        "tally": dict(tally),
        "measured": measured,
        "would_break": broke,
        "share_of_measured_that_would_break": round(broke / measured, 4) if measured else None,
        "questions": out,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nLIMIT1-convention singular-superlative questions: {len(pool)}")
    for k, v in sorted(tally.items()):
        print(f"  {k:36s} {v:4d}")
    if measured:
        print(f"\nOf the {measured} measured, {broke} would break "
              f"({broke/measured:.1%}) if this class always returned all ties.")


if __name__ == "__main__":
    main()
