"""Run our recursive DB-RLM method."""

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
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql


def build_variant_name(args: argparse.Namespace) -> str:
    parts = ["ours"]
    if args.use_metadata:
        parts.append("metadata")
    parts.append("rlm" if args.use_recursion else "no_rlm")
    if args.use_workspace:
        parts.append("workspace")
    if args.prompt_version != "recursive":
        parts.append(f"prompt_{args.prompt_version}")
    return "_".join(parts)


def run_one(example: dict, database_dir: Path, agent: DBRLM) -> dict:
    import time
    db_path = get_db_path(database_dir, example["db_id"])
    started = time.perf_counter()

    predicted_sql = ""
    termination = "error"
    error_msg = None

    try:
        predicted_sql = agent.complete_sql(example["question"], db_path)
        termination = "final"
    except KeyboardInterrupt:
        raise  # propagate so main loop can save and exit cleanly
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
        "method": "ours_recursive_db_rlm",
        "db_id": example["db_id"],
        "question": example["question"],
        "predicted_sql": predicted_sql,
        "predicted_answer": predicted_exec.get("answer"),
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec.get("answer"),
        "correct": (
            predicted_exec.get("error") is None
            and gold_exec.get("error") is None
            and is_correct(
                predicted_exec.get("answer"),
                gold_exec.get("answer"),
                gold_sql=example["gold_sql"],
            )
        ),
        "error": predicted_exec.get("error") or gold_exec.get("error"),
        "latency_seconds": round(time.perf_counter() - started, 4),
        "llm_calls": agent.stats["llm_calls"],
        "iterations": agent.stats["iterations"],
        "termination": termination,
        "ablation_config": agent.experiment_config.to_dict(),
    }


def main():
    parser = argparse.ArgumentParser(description="Run recursive DB-RLM on Spider")
    parser.add_argument("--dataset",      default=str(PROJECT_ROOT / "data/processed/dev_questions_sample_50.json"))
    parser.add_argument("--database-dir", default=str(PROJECT_ROOT / "data/databases"))
    parser.add_argument("--output",       default=None)
    parser.add_argument("--model",        default="groq/llama-3.3-70b-versatile")
    parser.add_argument("--recursive-model", default=None)
    parser.add_argument("--api-base",     default=None, help="API base URL (e.g. http://localhost:11434 for Ollama)")
    parser.add_argument("--limit",        type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--use-metadata", action="store_true")
    parser.add_argument("--use-recursion", dest="use_recursion", action="store_true", default=True)
    parser.add_argument("--no-recursion", dest="use_recursion", action="store_false")
    parser.add_argument("--use-workspace", action="store_true")
    parser.add_argument(
        "--prompt-version",
        choices=("basic", "recursive", "workspace"),
        default="recursive",
    )
    parser.add_argument("--sleep", type=float, default=0, help="Seconds between questions (set ~20 for Groq free tier)")
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
    else:
        api_key = None

    agent = DBRLM(
        model=args.model,
        recursive_model=args.recursive_model or args.model,
        api_key=api_key,
        api_base=args.api_base,
        max_iterations=args.max_iterations,
        max_depth=args.max_depth,
        use_metadata=args.use_metadata,
        use_recursion=args.use_recursion,
        use_workspace=args.use_workspace,
        prompt_version=args.prompt_version,
        temperature=0,
    )

    output_path = Path(args.output) if args.output else PROJECT_ROOT / "results" / f"{build_variant_name(args)}.json"
    output_path.parent.mkdir(exist_ok=True)

    # Resume from partial results if file already exists
    results = []
    done_ids = set()
    if output_path.exists():
        results = json.loads(output_path.read_text())
        done_ids = {r["id"] for r in results}
        print(f"Resuming — {len(done_ids)} already done")

    questions = [q for q in questions if q["id"] not in done_ids]
    print(f"Running {len(questions)} questions with {args.model}")
    print(f"Ablation config: {agent.experiment_config.to_dict()}")
    print(f"Output: {output_path}")

    for ex in tqdm(questions, desc="DB-RLM"):
        agent._llm_calls = 0
        agent._iterations = 0
        try:
            results.append(run_one(ex, Path(args.database_dir), agent))
        except KeyboardInterrupt:
            print(f"\nInterrupted - {len(results)} results saved to {output_path}")
            output_path.write_text(json.dumps(results, indent=2))
            break
        output_path.write_text(json.dumps(results, indent=2))
        time.sleep(args.sleep)

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    print(f"\nAccuracy: {correct}/{total} = {correct/total:.2%}")
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
