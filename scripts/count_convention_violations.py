"""Count how often a run's raw SQL violates the three mined conventions.

Reuses `ours.agent.sql_conventions._RULES` as pure detectors: each rule
function mutates a copy of the parsed tree and returns whether it fired, so
"fired" here means "violated the convention", independent of whether the run
actually applied post-processing (sql_convention_mode must be "none" for
`predicted_sql` to be the model's own output, not an already-rewritten one).

This is the offline, gold-independent measurement `convention_postprocessing_
2026-08-08.md` used to show that stating the conventions in the prompt does
not change how often the model violates them (24 vs 25 out of 197). No LLM
calls, no scoring -- it only asks what the model wrote.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlglot
from sqlglot import exp

from shared.console import force_utf8_console
from ours.agent.sql_conventions import _RULES, DIALECT


def count(results_path: Path) -> dict:
    rows = json.loads(results_path.read_text(encoding="utf-8"))
    per_rule = {name: [] for name in _RULES}
    unparsed = []
    for r in rows:
        sql = r.get("predicted_sql")
        if not sql:
            continue
        try:
            tree = sqlglot.parse_one(sql, read=DIALECT)
        except Exception:
            unparsed.append(r["id"])
            continue
        for name, rule in _RULES.items():
            if rule(tree.copy()):
                per_rule[name].append(r["id"])
    return {
        "n": len(rows),
        "unparsed": unparsed,
        "violations": {name: len(ids) for name, ids in per_rule.items()},
        "violation_ids": per_rule,
    }


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    out = {}
    for raw in args.results:
        p = Path(raw)
        c = count(p)
        out[p.stem] = c
        total = sum(c["violations"].values())
        print(f"{p.name}: n={c['n']} unparsed={len(c['unparsed'])} "
              f"total_violations={total}  {c['violations']}")

    if args.output:
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
