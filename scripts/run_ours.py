"""Run our recursive DB-RLM method."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import litellm
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from ours.recursive_db_rlm import DBRLM
from ours.db_environment import get_db_path
from shared import config
from shared.evaluator import is_correct
from shared.experiment_tracking import (
    build_manifest,
    ensure_compatible_resume,
    write_manifest,
)
from shared.schema_metrics import calculate_schema_metrics, extract_gold_schema
from shared.sql_executor import execute_sql


def build_variant_name(args: argparse.Namespace) -> str:
    parts = ["ours"]
    if args.use_metadata:
        parts.append("metadata")
    if args.use_enrichment:
        parts.append("enrichment")
    if args.use_probe_queries:
        parts.append("probe")
    if args.use_schema_memory:
        parts.append(f"schema_memory_top{args.initial_top_k}")
    parts.append("rlm" if args.use_recursion else "no_rlm")
    if args.use_workspace:
        parts.append("workspace")
    if args.prompt_version != "recursive":
        parts.append(f"prompt_{args.prompt_version}")
    return "_".join(parts)


def is_fatal_llm_error(error_text: str | None) -> bool:
    if not error_text:
        return False
    lowered = error_text.lower()
    markers = (
        "invalid api key",
        "authentication",
        "apiconnectionerror",
        "connection error",
        "model not found",
        "azureexception",
    )
    return any(marker in lowered for marker in markers)


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

    experiment_stats = agent.experiment_stats
    selected_columns_by_key: dict[tuple[str, str], dict] = {}
    for table, columns in experiment_stats["preloaded_columns"].items():
        for column in columns:
            selected_columns_by_key[(table, column)] = {
                "table": table,
                "column": column,
            }
    for table, columns in experiment_stats["inspected_columns"].items():
        for column in columns:
            selected_columns_by_key[(table, column)] = {
                "table": table,
                "column": column,
            }
    for item in experiment_stats["schema_memory"]["columns"]:
        selected_columns_by_key[(item["table"], item["column"])] = {
            "table": item["table"],
            "column": item["column"],
        }
    for item in experiment_stats["enrichment_columns"]:
        selected_columns_by_key[(item["table"], item["column"])] = dict(item)
    selected_columns = list(selected_columns_by_key.values())
    selected_tables = sorted(
        set(experiment_stats["preloaded_tables"])
        | set(experiment_stats["inspected_tables"])
        | set(experiment_stats["schema_memory"]["tables"])
        | set(experiment_stats["enrichment_tables"])
    )
    try:
        schema_metrics = calculate_schema_metrics(
            extract_gold_schema(example["gold_sql"], db_path),
            selected_tables,
            selected_columns,
        )
    except Exception as error:
        schema_metrics = {"error": str(error)}
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
        "llm_calls": experiment_stats["llm_calls"],
        "iterations": experiment_stats["iterations"],
        "input_tokens": experiment_stats["input_tokens"],
        "output_tokens": experiment_stats["output_tokens"],
        "tool_calls": experiment_stats["tool_calls"],
        "retrieval_calls": experiment_stats["retrieval_calls"],
        "sql_execution_calls": experiment_stats["sql_execution_calls"],
        "inspected_tables": experiment_stats["inspected_tables"],
        "inspected_columns": experiment_stats["inspected_columns"],
        "preloaded_tables": experiment_stats["preloaded_tables"],
        "preloaded_columns": experiment_stats["preloaded_columns"],
        "schema_memory": experiment_stats["schema_memory"],
        "schema_memory_events": experiment_stats["schema_memory_events"],
        "selected_tables": selected_tables,
        "selected_columns": selected_columns,
        "schema_metrics": schema_metrics,
        "recursion_calls": experiment_stats["recursion_calls"],
        "recursion_used": experiment_stats["recursion_used"],
        "recursion_trace": experiment_stats["recursion_trace"],
        "db_trace": experiment_stats["db_trace"],
        "termination": termination,
        "ablation_config": agent.experiment_config.to_dict(),
    }


def main():
    parser = argparse.ArgumentParser(description="Run recursive DB-RLM on Spider")
    parser.add_argument(
        "--dataset",
        default=str(PROJECT_ROOT / "data/processed/bird_mini_dev_questions.json"),
    )
    parser.add_argument("--database-dir", default=str(PROJECT_ROOT / "data/databases"))
    parser.add_argument("--output",       default=None)
    parser.add_argument("--model",        default=os.environ.get("MODEL", "groq/llama-3.3-70b-versatile"))
    parser.add_argument("--recursive-model", default=None)
    parser.add_argument(
        "--api-base",
        default=os.environ.get("AZURE_API_BASE") or None,
        help="API base URL (e.g. http://localhost:11434 for Ollama or Azure endpoint).",
    )
    parser.add_argument("--limit",        type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--use-metadata", action="store_true")
    parser.add_argument("--use-enrichment", action="store_true")
    parser.add_argument("--use-probe-queries", action="store_true")
    parser.add_argument("--use-schema-memory", action="store_true")
    parser.add_argument("--initial-top-k", type=int, default=10)
    parser.add_argument("--use-recursion", dest="use_recursion", action="store_true", default=True)
    parser.add_argument("--no-recursion", dest="use_recursion", action="store_false")
    parser.add_argument("--use-workspace", action="store_true")
    parser.add_argument(
        "--prompt-version",
        choices=("basic", "recursive", "workspace", "schema"),
        default="recursive",
    )
    parser.add_argument("--sleep", type=float, default=0, help="Seconds between questions (set ~20 for Groq free tier)")
    args = parser.parse_args()
    if args.initial_top_k < 1:
        parser.error("--initial-top-k must be at least 1")
    if args.use_schema_memory and args.use_metadata:
        parser.error(
            "--use-schema-memory cannot be combined with --use-metadata because "
            "full metadata would bypass the bounded schema treatment"
        )

    questions = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if args.limit:
        questions = questions[:args.limit]

    if "groq" in args.model:
        api_key = os.environ.get("GROQ_API_KEY")
    elif "gemini" in args.model:
        api_key = os.environ.get("GEMINI_API_KEY")
    elif "openrouter" in args.model:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    elif args.model.startswith("azure/"):
        api_key = os.environ.get("AZURE_API_KEY")
    else:
        api_key = None

    if args.model.startswith("azure/"):
        litellm.drop_params = True

    agent = DBRLM(
        model=args.model,
        recursive_model=args.recursive_model or args.model,
        api_key=api_key,
        api_base=args.api_base,
        max_iterations=args.max_iterations,
        max_depth=args.max_depth,
        use_metadata=args.use_metadata,
        use_enrichment=args.use_enrichment,
        use_probe_queries=args.use_probe_queries,
        use_schema_memory=args.use_schema_memory,
        initial_top_k=args.initial_top_k,
        use_recursion=args.use_recursion,
        use_workspace=args.use_workspace,
        prompt_version=args.prompt_version,
        api_version=os.environ.get("AZURE_API_VERSION"),
        azure_deployment=os.environ.get("AZURE_DEPLOYMENT"),
        temperature=config.effective_temperature(args.model, provider="azure" if args.model.startswith("azure/") else None),
    )

    output_path = Path(args.output) if args.output else PROJECT_ROOT / "results" / f"{build_variant_name(args)}.json"
    output_path.parent.mkdir(exist_ok=True)
    run_config = {
        "method": "ours_recursive_db_rlm",
        "variant": build_variant_name(args),
        "model": args.model,
        "recursive_model": args.recursive_model or args.model,
        "api_base": args.api_base,
        "api_version": os.environ.get("AZURE_API_VERSION"),
        "azure_deployment": os.environ.get("AZURE_DEPLOYMENT"),
        "temperature": config.effective_temperature(
            args.model,
            provider="azure" if args.model.startswith("azure/") else None,
        ),
        "max_iterations": args.max_iterations,
        "max_depth": args.max_depth,
        "limit": args.limit,
        "ablation_config": agent.experiment_config.to_dict(),
    }
    tracked_code = [
        PROJECT_ROOT / "scripts/run_ours.py",
        PROJECT_ROOT / "ours/recursive_db_rlm.py",
        PROJECT_ROOT / "ours/subquestion_agent.py",
        PROJECT_ROOT / "ours/db_environment.py",
        PROJECT_ROOT / "ours/metadata.py",
        PROJECT_ROOT / "ours/query_enrichment.py",
        PROJECT_ROOT / "ours/probe_queries.py",
        PROJECT_ROOT / "ours/schema_memory.py",
        PROJECT_ROOT / "src/rlm/core.py",
        PROJECT_ROOT / "src/rlm/parser.py",
        PROJECT_ROOT / "shared/evaluator.py",
        PROJECT_ROOT / "shared/sql_executor.py",
        PROJECT_ROOT / "prompts/ours_recursive_db_rlm.txt",
    ]
    manifest = build_manifest(
        project_root=PROJECT_ROOT,
        result_path=output_path,
        dataset_path=args.dataset,
        database_dir=args.database_dir,
        code_paths=tracked_code,
        run_config=run_config,
    )
    ensure_compatible_resume(output_path, manifest)
    write_manifest(output_path, manifest)

    # Resume from partial results if file already exists
    results = []
    done_ids = set()
    if output_path.exists():
        results = json.loads(output_path.read_text(encoding="utf-8"))
        done_ids = {r["id"] for r in results}
        print(f"Resuming — {len(done_ids)} already done")

    questions = [q for q in questions if q["id"] not in done_ids]
    print(f"Running {len(questions)} questions with {args.model}")
    print(f"Ablation config: {agent.experiment_config.to_dict()}")
    print(f"Output: {output_path}")

    for ex in tqdm(questions, desc="DB-RLM"):
        agent._llm_calls = 0
        agent._iterations = 0
        agent._input_tokens = 0
        agent._output_tokens = 0
        try:
            results.append(run_one(ex, Path(args.database_dir), agent))
        except KeyboardInterrupt:
            print(f"\nInterrupted - {len(results)} results saved to {output_path}")
            output_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            break
        if is_fatal_llm_error(results[-1].get("error")):
            output_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\nAborting after fatal LLM error: {results[-1]['error']}")
            break
        output_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        time.sleep(args.sleep)

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    print(f"\nAccuracy: {correct}/{total} = {correct/total:.2%}")
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
