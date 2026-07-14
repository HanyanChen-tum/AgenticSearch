"""DB-RLM with in-domain BIRD few-shot retrieval (k=1).

Uses correct examples from our own v4 run (same 11 BIRD databases).
Retrieves the single most similar example, prioritizing same-database matches.
This avoids schema bloat (1 example vs 3) and domain mismatch (BIRD vs Spider).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from ours.recursive_db_rlm import DBRLM
from ours.db_environment import get_db_path
from ours.bird_few_shot_retriever import get_bird_retriever
from ours.agent.config import agent_profile_names, get_agent_config
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql

BIRD_DB_DIR  = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"
BIRD_DATASET = PROJECT_ROOT / "data/processed/bird_dev_500.json"


class InDomainFewShotDBRLM(DBRLM):
    """Compatibility wrapper; the shared DBRLM owns the only agent loop."""

    def __init__(self, *args, retriever=None, k=1, **kwargs):
        super().__init__(*args, retriever=retriever, k=k, **kwargs)


def run_one(
    example: dict,
    database_dir: Path,
    agent: InDomainFewShotDBRLM,
    capture_trace: bool = False,
) -> dict:
    agent.reset_stats()
    db_path = get_db_path(database_dir, example["db_id"])
    started = time.perf_counter()
    predicted_sql = ""
    termination = "error"
    error_msg = None
    attempt_traces = []

    for attempt in range(3):
        try:
            predicted_sql = agent.complete_sql(
                example["question"], db_path,
                evidence=example.get("evidence", ""),
            )
            termination = "final"
            break
        except KeyboardInterrupt:
            raise
        except Exception as e:
            error_msg = str(e)
            termination = type(e).__name__
            # Retry infra failures; model failures (MaxIterations etc.) are real results
            if attempt < 2 and any(s in termination for s in ("API", "Connection", "Timeout")):
                time.sleep(5 * (attempt + 1))
                continue
            break
        finally:
            if capture_trace:
                snapshot = agent.trace_snapshot()
                snapshot["attempt"] = attempt + 1
                attempt_traces.append(snapshot)

    predicted_exec = (
        execute_sql(db_path, predicted_sql, read_only=True)
        if predicted_sql else {"answer": None, "error": error_msg or "No SQL"}
    )
    gold_exec = execute_sql(db_path, example["gold_sql"], read_only=True)

    record = {
        "id": example["id"],
        "method": "bird_indomain_fewshot_db_rlm",
        "db_id": example["db_id"],
        "question": example["question"],
        "difficulty": example.get("difficulty", "unknown"),
        "predicted_sql": predicted_sql,
        "predicted_answer": predicted_exec.get("answer"),
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec.get("answer"),
        "correct": (
            predicted_exec.get("error") is None
            and gold_exec.get("error") is None
            and is_correct(predicted_exec.get("answer"), gold_exec.get("answer"))
        ),
        "error": predicted_exec.get("error") or gold_exec.get("error"),
        "latency_seconds": round(time.perf_counter() - started, 4),
        "llm_calls": agent.stats["llm_calls"],
        "prompt_tokens": agent.stats["prompt_tokens"],
        "completion_tokens": agent.stats["completion_tokens"],
        "reasoning_tokens": agent.stats["reasoning_tokens"],
        "total_tokens": agent.stats["total_tokens"],
        "cached_prompt_tokens": agent.stats["cached_prompt_tokens"],
        "usage_missing_calls": agent.stats["usage_missing_calls"],
        "reasoning_usage_missing_calls": agent.stats["reasoning_usage_missing_calls"],
        "agent_profile": agent.agent_config.profile,
        "agent_config_sha256": agent.agent_config.sha256,
        "termination": termination,
    }
    if capture_trace:
        final_attempt = attempt_traces[-1] if attempt_traces else {
            "messages": [], "events": [], "attempt": 0,
        }
        record["_trace"] = {
            "messages": final_attempt.get("messages", []),
            "events": final_attempt.get("events", []),
            "llm_call_usage": agent.llm_call_usage_snapshot(),
            "token_usage": {
                key: agent.stats[key]
                for key in (
                    "llm_calls",
                    "prompt_tokens",
                    "completion_tokens",
                    "reasoning_tokens",
                    "total_tokens",
                    "cached_prompt_tokens",
                    "usage_missing_calls",
                    "reasoning_usage_missing_calls",
                )
            },
            "attempts": attempt_traces,
        }
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset",        default=str(BIRD_DATASET))
    parser.add_argument("--database-dir",   default=str(BIRD_DB_DIR))
    parser.add_argument("--output",         default=str(PROJECT_ROOT / "results/bird_indomain_fewshot_500.json"))
    parser.add_argument("--model",          default="azure/seminar-gpt-5.4-mini")
    parser.add_argument("--api-base",       default=None)
    parser.add_argument("--limit",          type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=15)
    parser.add_argument("--k",              type=int, default=1)
    parser.add_argument("--temperature",    type=float, default=0)
    parser.add_argument("--reasoning-effort", default=None,
                        help="gpt-5 family reasoning effort: minimal/low/medium/high")
    parser.add_argument(
        "--agent-profile",
        choices=agent_profile_names(),
        default="legacy-e0",
        help=(
            "agent profile; this runner uses dev-derived examples and is only for "
            "legacy reproduction, not clean evaluation"
        ),
    )
    parser.add_argument("--no-fewshot", action="store_true",
                        help="disable retrieval few-shot (static prompt examples only)")
    parser.add_argument("--sleep",          type=float, default=0)
    args = parser.parse_args()

    questions = json.loads(Path(args.dataset).read_text())
    if args.limit:
        questions = questions[:args.limit]

    if "groq" in args.model:
        api_key = os.environ.get("GROQ_API_KEY")
        api_base = args.api_base
    elif "azure" in args.model:
        api_key = os.environ.get("LLM_API_KEY")
        api_base = args.api_base or os.environ.get("LLM_BASE_URL")
    else:
        api_key = None
        api_base = args.api_base

    retriever = None if args.no_fewshot else get_bird_retriever()

    extra = {}
    if args.reasoning_effort:
        extra["reasoning_effort"] = args.reasoning_effort

    agent = InDomainFewShotDBRLM(
        model=args.model,
        api_key=api_key,
        api_base=api_base,
        max_iterations=args.max_iterations,
        temperature=args.temperature,
        retriever=retriever,
        k=args.k,
        agent_config=get_agent_config(args.agent_profile),
        **extra,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)

    results = []
    done_ids = set()
    if output_path.exists():
        results = json.loads(output_path.read_text())
        done_ids = {r["id"] for r in results}
        print(f"Resuming — {len(done_ids)} already done")

    questions = [q for q in questions if q["id"] not in done_ids]
    print(f"Running {len(questions)} questions with k={args.k} in-domain BIRD example(s)")

    for ex in tqdm(questions, desc="BIRD-InDomainFewShot"):
        try:
            results.append(run_one(ex, Path(args.database_dir), agent))
        except KeyboardInterrupt:
            print(f"\nInterrupted — {len(results)} saved")
            output_path.write_text(json.dumps(results, indent=2))
            break
        output_path.write_text(json.dumps(results, indent=2))
        if args.sleep > 0:
            time.sleep(args.sleep)

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    print(f"\nAccuracy: {correct}/{total} = {correct/total:.2%}")
    by_diff = {}
    for r in results:
        by_diff.setdefault(r.get("difficulty", "unknown"), []).append(r["correct"])
    for d, vals in sorted(by_diff.items()):
        print(f"  {d}: {sum(vals)}/{len(vals)} = {sum(vals)/len(vals):.2%}")


if __name__ == "__main__":
    main()
