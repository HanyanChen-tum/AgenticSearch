"""Baseline 1: Direct LLM + full schema.

This baseline gives the LLM only the user question and the full database
schema. It does not inspect table contents, execute SQL during generation,
self-correct, or retry.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from tqdm import tqdm

from shared import config
from shared.data_loader import load_questions
from shared.evaluator import is_correct
from shared.io_utils import read_text, write_json
from shared.llm_client import generate_sql
from shared.logging_utils import setup_logger
from shared.schema_utils import extract_schema_text, get_database_path
from shared.sql_executor import execute_sql


METHOD_NAME = "baseline_1_direct_llm_schema"
PROMPT_PATH = config.PROMPTS_DIR / "baseline_1_direct_llm_schema.txt"
OUTPUT_PATH = config.RESULTS_DIR / f"{METHOD_NAME}.json"
LOG_PATH = config.PROJECT_ROOT / "logs" / "baseline_1.log"


logger = setup_logger(METHOD_NAME, LOG_PATH)


def clean_sql(text: str) -> str:
    sql = text.strip()
    if sql.startswith("```"):
        lines = sql.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines).strip()
    return sql


def build_prompt(question: str, schema: str, prompt_template: str) -> str:
    return prompt_template.format(question=question, schema=schema)


def run_one(example: dict[str, Any], prompt_template: str, database_dir: Path) -> dict[str, Any]:
    db_id = example["db_id"]
    db_path = get_database_path(database_dir, db_id)

    started_at = time.perf_counter()
    predicted_sql = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    generation_error: str | None = None

    try:
        schema = extract_schema_text(db_path)
        prompt = build_prompt(example["question"], schema, prompt_template)
        llm_response = generate_sql(prompt)
        predicted_sql = clean_sql(llm_response.text)
        input_tokens = llm_response.input_tokens
        output_tokens = llm_response.output_tokens
    except Exception as e:
        generation_error = str(e)

    predicted_exec = (
        execute_sql(db_path, predicted_sql)
        if predicted_sql and generation_error is None
        else {"answer": None, "error": generation_error or "No SQL generated"}
    )
    gold_exec = execute_sql(db_path, example["gold_sql"])

    latency_seconds = time.perf_counter() - started_at
    error = predicted_exec["error"] or gold_exec["error"]

    return {
        "id": example["id"],
        "method": METHOD_NAME,
        "db_id": db_id,
        "question": example["question"],
        "predicted_sql": predicted_sql,
        "predicted_answer": predicted_exec["answer"],
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec["answer"],
        "correct": (
            predicted_exec["error"] is None
            and gold_exec["error"] is None
            and is_correct(predicted_exec["answer"], gold_exec["answer"])
        ),
        "error": error,
        "latency_seconds": round(latency_seconds, 4),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def run_baseline(
    dataset_path: str | Path = config.DEFAULT_DATASET_PATH,
    output_path: str | Path = OUTPUT_PATH,
    database_dir: str | Path = config.DATABASE_DIR,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    questions = load_questions(dataset_path)
    if limit is not None:
        questions = questions[:limit]

    logger.info("Starting %s with %d examples", METHOD_NAME, len(questions))
    logger.info("Dataset: %s", dataset_path)
    logger.info("Database dir: %s", database_dir)
    logger.info("Output: %s", output_path)

    prompt_template = read_text(PROMPT_PATH)
    results = [
        run_one(example, prompt_template, Path(database_dir))
        for example in tqdm(questions, desc=METHOD_NAME)
    ]

    write_json(output_path, results)
    total = len(results)
    correct = sum(1 for row in results if row["correct"])
    accuracy = correct / total if total else 0
    logger.info(
        "Finished %s: total=%d correct=%d execution_accuracy=%.4f",
        METHOD_NAME,
        total,
        correct,
        accuracy,
    )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline 1: Direct LLM + full schema.")
    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_baseline(
        dataset_path=args.dataset,
        output_path=args.output,
        database_dir=args.database_dir,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
