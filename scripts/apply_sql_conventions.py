"""Re-score an existing run with convention post-processing, without any LLM calls.

The rewrites are deterministic functions of the recorded `predicted_sql`, so
applying them offline gives exactly the accuracy an inline run would have
produced.  That keeps every historical run re-scorable without paying for it
again, and keeps the decomposition explicit: the report always states how many
questions the model got right on its own and how many post-processing moved.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ours.agent.sql_conventions import get_sql_convention_rewriter
from ours.db_environment import get_db_path
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql
# Reuse the runner's constant rather than re-deriving the path: a wrong database
# directory makes every execution error out, which reads as a large accuracy
# regression instead of as the configuration bug it is.
from scripts.run_bird_indomain_fewshot import BIRD_DB_DIR


def rescore(results_path: Path, database_dir: Path) -> dict[str, Any]:
    if not database_dir.is_dir():
        raise SystemExit(f"database dir not found: {database_dir}")
    rows = json.loads(results_path.read_text(encoding="utf-8"))
    rewriter = get_sql_convention_rewriter()

    baseline = sum(1 for r in rows if r.get("correct"))
    gained: list[str] = []
    broken: list[str] = []
    unchanged_wrong = 0
    rule_hits: Counter = Counter()
    log: list[dict[str, Any]] = []

    for row in rows:
        result = rewriter.rewrite(row.get("predicted_sql") or "")
        if not result.changed:
            continue
        rule_hits.update(result.applied)
        db_path = get_db_path(database_dir, row["db_id"])
        executed = execute_sql(db_path, result.sql, read_only=True)
        now_correct = (
            executed.get("error") is None
            and is_correct(executed.get("answer"), row.get("gold_answer"))
        )
        was_correct = bool(row.get("correct"))
        if now_correct and not was_correct:
            outcome = "gained"
            gained.append(row["id"])
        elif was_correct and not now_correct:
            outcome = "broken"
            broken.append(row["id"])
        else:
            outcome = "unchanged"
            unchanged_wrong += int(not now_correct)
        log.append({
            "id": row["id"],
            "db_id": row["db_id"],
            "applied": list(result.applied),
            "outcome": outcome,
            "was_correct": was_correct,
            "now_correct": now_correct,
            "original_sql": result.original_sql,
            "rewritten_sql": result.sql,
            "execution_error": executed.get("error"),
        })

    final = baseline + len(gained) - len(broken)
    return {
        "results_path": str(results_path),
        "question_count": len(rows),
        "baseline_correct": baseline,
        "final_correct": final,
        "net_change": final - baseline,
        "gained_ids": gained,
        "broken_ids": broken,
        "rewritten_question_count": len(log),
        "rewritten_still_wrong": unchanged_wrong,
        "rule_hits": dict(rule_hits),
        "convention_manifest": rewriter.manifest(),
        "rewrite_log": log,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="+")
    parser.add_argument("--database-dir", default=str(BIRD_DB_DIR))
    parser.add_argument("--output", default=None, help="write the full report JSON here")
    args = parser.parse_args()

    reports = []
    for path in args.results:
        report = rescore(Path(path).resolve(), Path(args.database_dir))
        reports.append(report)
        n = report["question_count"]
        base, final = report["baseline_correct"], report["final_correct"]
        print(
            f"{Path(path).stem:<34} {base:>3}/{n} ({base / n * 100:5.2f}%) -> "
            f"{final:>3}/{n} ({final / n * 100:5.2f}%)  net {report['net_change']:+d}   "
            f"rewritten={report['rewritten_question_count']} "
            f"gained={len(report['gained_ids'])} broken={len(report['broken_ids'])}"
        )
        print(f"    rules fired: {report['rule_hits']}")
        if report["gained_ids"]:
            print(f"    gained: {report['gained_ids']}")
        if report["broken_ids"]:
            print(f"    broken: {report['broken_ids']}")

    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(reports, indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
