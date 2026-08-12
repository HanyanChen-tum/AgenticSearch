"""Test whether a decision node causes the outcome, or merely marks hard questions.

The ranking in `rank_decision_points.py` is observational: it measures how much
knowing a decision reduces uncertainty about correctness. Query structure tops it
at 0.0567 bits, spanning 40.6 points of success rate (flat 72.7%, subquery 32.1%,
CTE 36.4%). That number cannot say whether writing a subquery *causes* the failure
or whether hard questions simply attract subqueries.

Thought Anchors answers the same question by resampling: replace a step with a
semantically different one, continue, and see how far the answer distribution
moves. The trajectory-level analogue is to force the other branch and re-run.

Two arms, identical questions and budget:

  A  resample with no instruction        -- isolates the effect of resampling
  B  resample, forced onto the other branch

If the decision is causal, B beats A. If it only marks difficulty, they match --
which is what happened on the E6 empty-result trigger, where a mechanically
correct diagnosis moved nothing that a plain retry did not.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

import sqlglot
from sqlglot import exp

from ours.agent.config import get_agent_config
from ours.db_environment import get_db_path
from ours.train_few_shot_retriever import get_train_retriever
from shared.evaluator import is_correct
from shared.llm_config import resolve_llm_config
from shared.sql_executor import execute_sql
from scripts.run_bird_indomain_fewshot import BIRD_DB_DIR, InDomainFewShotDBRLM

# Forcing the branch, not suggesting it: vague wording measured no behavioural
# change on this project's own conventions (violations 24 vs 25), while naming
# the form outright moved them 19 -> 4.
FORCE = (
    "\n\nWrite this as a single flat SELECT. Do not use a subquery and do not use "
    "a WITH clause — put the joins and filters directly in one SELECT. If the "
    "question genuinely cannot be expressed that way, say so in your reasoning and "
    "write it your usual way."
)
PLAIN = "\n\nWrite the SQL for this question."


def structure(sql: str) -> str:
    try:
        tree = sqlglot.parse_one(sql or "", read="sqlite")
    except Exception:
        return "无法解析"
    if list(tree.find_all(exp.CTE)):
        return "含 CTE"
    if list(tree.find_all(exp.Subquery)):
        return "含子查询"
    return "平铺"


def build_agent():
    cfg = resolve_llm_config("azure/seminar-gpt-5.4-mini")
    return InDomainFewShotDBRLM(
        model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base,
        temperature=0, max_iterations=8, retriever=get_train_retriever(), k=1,
        agent_config=get_agent_config("e3-c-conv-rules"), reasoning_effort="high")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["A", "B"], required=True)
    parser.add_argument("--results", default="results/e3_c_conv_rules_dev500_run1.json")
    parser.add_argument("--trace", default="trace/e3_c_conv_rules_dev500_run1/transcripts.jsonl")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    hints = {r["id"]: r.get("evidence") or "" for r in json.loads(
        (PROJECT_ROOT / "data/processed/bird_dev_500.json").read_text(encoding="utf-8"))}
    model_sql = {}
    with Path(args.trace).open(encoding="utf-8") as handle:
        for line in handle:
            rec = json.loads(line)
            rw = (rec.get("_trace") or rec).get("sql_convention_rewrite") or {}
            if rw.get("changed") and rw.get("original_sql"):
                model_sql[rec["id"]] = rw["original_sql"]

    targets = [
        r for r in rows.values()
        if structure(model_sql.get(r["id"], r.get("predicted_sql"))) in ("含子查询", "含 CTE")
    ]
    print(f"触发集（模型写了子查询或 CTE）: {len(targets)} 题, arm={args.arm}")

    agent = build_agent()
    out_path = Path(args.output).resolve()
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else []
    seen = {(d["id"], d["repeat"]) for d in done}

    for rep in range(1, args.repeat + 1):
        for row in targets:
            if (row["id"], rep) in seen:
                continue
            prompt = row["question"] + (FORCE if args.arm == "B" else PLAIN)
            db_path = get_db_path(BIRD_DB_DIR, row["db_id"])
            agent.reset_stats()
            new_sql, failure = None, None
            for attempt in range(3):
                try:
                    new_sql = agent.complete_sql(prompt, db_path, hints.get(row["id"], ""))
                    break
                except Exception as exc:
                    failure = f"{type(exc).__name__}: {exc}"[:160]
                    time.sleep(5 * (attempt + 1))
            if new_sql is None:
                # Infrastructure failures are recorded apart from results; folding
                # them in once read as "the mechanism failed".
                rec = {"id": row["id"], "arm": args.arm, "repeat": rep,
                       "infra_error": failure, "was_correct": bool(row.get("correct"))}
            else:
                ex = execute_sql(db_path, new_sql, read_only=True)
                ok = (ex.get("error") is None
                      and is_correct(ex.get("answer"), row.get("gold_answer")))
                rec = {
                    "id": row["id"], "arm": args.arm, "repeat": rep, "infra_error": None,
                    "was_correct": bool(is_correct(row.get("predicted_answer"),
                                                   row.get("gold_answer"))),
                    "now_correct": ok, "new_sql": new_sql,
                    "old_structure": structure(model_sql.get(row["id"], row.get("predicted_sql"))),
                    "new_structure": structure(new_sql),
                }
            done.append(rec)
            out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
            tag = "INFRA" if rec["infra_error"] else f'{rec["old_structure"]}→{rec["new_structure"]}'
            mark = "" if rec["infra_error"] else (" ✓" if rec["now_correct"] else " ✗")
            print(f'  rep{rep} {row["id"]:<12} {tag}{mark}')

    valid = [d for d in done if not d["infra_error"]]
    flipped = sum(1 for d in valid if d["new_structure"] == "平铺")
    was = sum(1 for d in valid if d["was_correct"])
    now = sum(1 for d in valid if d["now_correct"])
    print(f'\narm {args.arm}: 有效 {len(valid)} 次 | 改为平铺 {flipped} '
          f'| 原本对 {was} → 现在对 {now} | 净 {now - was:+d}')
