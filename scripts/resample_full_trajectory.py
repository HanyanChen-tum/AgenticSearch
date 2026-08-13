"""Resample a question through the full agent, not just one turn, to test whether
a high total tool-call count is intrinsic to the question or a symptom of the
model chasing an unproductive line of inquiry.

`resample_turn.py` can only regenerate one turn from a fixed prefix -- it has no
tool loop, so it can't show what a *different* first move leads to three turns
later. This script runs the real agent (the same one the eval harness uses) from
scratch, N times, and records how many tool calls each independent attempt makes
and whether it lands on the right answer. If a question's call count barely
moves across resamples, the count is a property of the question. If it swings
widely -- and low-call resamples do better -- the original high count was more
churn than necessity.
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

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from ours.agent.config import get_agent_config
from ours.db_environment import get_db_path
from ours.train_few_shot_retriever import get_train_retriever
from shared.evaluator import is_correct
from shared.llm_config import resolve_llm_config
from shared.sql_executor import execute_sql
from scripts.run_bird_indomain_fewshot import BIRD_DB_DIR, InDomainFewShotDBRLM

PLAIN = "\n\nWrite the SQL for this question."


def build_agent():
    cfg = resolve_llm_config("azure/seminar-gpt-5.4-mini")
    return InDomainFewShotDBRLM(
        model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base,
        temperature=0, max_iterations=8, retriever=get_train_retriever(), k=1,
        agent_config=get_agent_config("e3-c-conv-rules"), reasoning_effort="high")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results/e3_c_conv_rules_dev500_run1.json")
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    hints = {r["id"]: r.get("evidence") or "" for r in json.loads(
        (PROJECT_ROOT / "data/processed/bird_dev_500.json").read_text(encoding="utf-8"))}

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else []
    seen = {(d["id"], d["repeat"]) for d in done}

    agent = build_agent()
    for qid in args.ids:
        row = rows[qid]
        db_path = get_db_path(BIRD_DB_DIR, row["db_id"])
        for rep in range(1, args.repeat + 1):
            if (qid, rep) in seen:
                continue
            agent.reset_stats()
            new_sql, failure = None, None
            for attempt in range(3):
                try:
                    new_sql = agent.complete_sql(row["question"] + PLAIN, db_path, hints.get(qid, ""))
                    break
                except Exception as exc:
                    failure = f"{type(exc).__name__}: {exc}"[:160]
                    time.sleep(5 * (attempt + 1))
            events = getattr(agent, "_trace_events", [])
            n_calls = sum(1 for e in events if e.get("tool") in ("db.execute", "db.sample_values"))
            if new_sql is None:
                rec = {"id": qid, "repeat": rep, "infra_error": failure, "n_calls": n_calls}
            else:
                ex = execute_sql(db_path, new_sql, read_only=True)
                ok = ex.get("error") is None and is_correct(ex.get("answer"), row.get("gold_answer"))
                rec = {"id": qid, "repeat": rep, "infra_error": None, "n_calls": n_calls,
                       "correct": bool(ok), "sql": new_sql}
            done.append(rec)
            out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
            tag = "INFRA" if rec.get("infra_error") else ("correct" if rec.get("correct") else "wrong")
            print(f"  {qid:<12} rep{rep} calls={n_calls:<3} {tag}")

    print(f"\n已写入 {out_path}（{len(done)} 条）")
