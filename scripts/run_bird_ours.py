"""Run DB-RLM on BIRD mini-dev (500 questions)."""

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
from ours.agent.config import agent_profile_names, get_agent_config
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql

BIRD_DB_DIR  = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"
BIRD_DATASET = PROJECT_ROOT / "data/processed/bird_dev_500.json"


def run_one(example: dict, database_dir: Path, agent: DBRLM) -> dict:
    agent.reset_stats()
    db_path = get_db_path(database_dir, example["db_id"])
    started = time.perf_counter()

    predicted_sql = ""
    termination = "error"
    error_msg = None

    try:
        predicted_sql = agent.complete_sql(
            example["question"], db_path,
            evidence=example.get("evidence", ""),
        )
        termination = "final"
    except KeyboardInterrupt:
        raise
    except Exception as e:
        error_msg = str(e)
        termination = type(e).__name__

    predicted_exec = (
        execute_sql(db_path, predicted_sql, read_only=True)
        if predicted_sql else {"answer": None, "error": error_msg or "No SQL generated"}
    )
    gold_exec = execute_sql(db_path, example["gold_sql"], read_only=True)

    return {
        "id": example["id"],
        "method": "bird_db_rlm",
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
        "iterations": agent.stats["iterations"],
        "termination": termination,
    }


def main():
    parser = argparse.ArgumentParser(description="Run DB-RLM on BIRD mini-dev")
    parser.add_argument("--dataset",        default=str(BIRD_DATASET))
    parser.add_argument("--database-dir",   default=str(BIRD_DB_DIR))
    parser.add_argument("--output",         default=str(PROJECT_ROOT / "results/bird_ours_500.json"))
    parser.add_argument("--model",          default="groq/llama-3.3-70b-versatile")
    parser.add_argument("--api-base",       default=None)
    parser.add_argument("--limit",          type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument(
        "--agent-profile",
        choices=agent_profile_names(),
        default="legacy-e0",
        help="legacy runner profile; use run_bird_train_fewshot.py for clean experiments",
    )
    parser.add_argument("--sleep",          type=float, default=0)
    args = parser.parse_args()

    questions = json.loads(Path(args.dataset).read_text())
    if args.limit:
        questions = questions[:args.limit]

    if "groq" in args.model:
        api_key = os.environ.get("GROQ_API_KEY")
    elif "gemini" in args.model:
        api_key = os.environ.get("GEMINI_API_KEY")
    elif "openrouter" in args.model:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    elif "azure" in args.model:
        api_key = os.environ.get("LLM_API_KEY")
    else:
        api_key = None

    # Fall back to LLM_BASE_URL from .env when --api-base not given
    api_base = args.api_base or os.environ.get("LLM_BASE_URL")

    agent = DBRLM(
        model=args.model,
        api_key=api_key,
        api_base=api_base,
        max_iterations=args.max_iterations,
        temperature=0,
        agent_config=get_agent_config(args.agent_profile),
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
    print(f"Running {len(questions)} BIRD questions with {args.model}")

    for ex in tqdm(questions, desc="BIRD-DBRLM"):
        try:
            results.append(run_one(ex, Path(args.database_dir), agent))
        except KeyboardInterrupt:
            print(f"\nInterrupted — {len(results)} results saved to {args.output}")
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
        d = r.get("difficulty", "unknown")
        by_diff.setdefault(d, []).append(r["correct"])
    for d, vals in sorted(by_diff.items()):
        print(f"  {d}: {sum(vals)}/{len(vals)} = {sum(vals)/len(vals):.2%}")
    print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
