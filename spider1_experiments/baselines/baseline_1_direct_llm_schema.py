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

from spider1_experiments.shared import config
from spider1_experiments.shared.data_loader import load_questions
from spider1_experiments.shared.evaluator import build_result_evaluation
from spider1_experiments.shared.io_utils import read_json, read_text, write_json
from spider1_experiments.shared.llm_client import generate_sql
from spider1_experiments.shared.logging_utils import setup_logger
from spider1_experiments.shared.schema_utils import extract_schema_text, get_database_path
from spider1_experiments.shared.sql_executor import execute_sql


METHOD_NAME = "baseline_1_direct_llm_schema"
PROMPT_PATH = config.PROMPTS_DIR / "baseline_1_direct_llm_schema.txt"
OUTPUT_PATH = config.RESULTS_DIR / f"{METHOD_NAME}.json"
LOG_PATH = config.LOGS_DIR / "baseline_1.log"


logger = setup_logger(METHOD_NAME, LOG_PATH)


def clean_sql(text: str) -> str:
    """娓呯悊 LLM 杈撳嚭涓殑 Markdown 浠ｇ爜鍧楋紝鍙繚鐣?SQL銆?

    Clean Markdown code fences from the LLM output and keep only SQL.
    """
    sql = text.strip()
    if sql.startswith("```"):
        # 鍘绘帀 ```sql ... ``` 杩欑被 Markdown 鍖呰９銆?
        # Remove Markdown fences such as ```sql ... ```.
        lines = sql.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines).strip()
    return sql


def build_prompt(question: str, schema: str, prompt_template: str) -> str:
    """鎶婇棶棰樺拰瀹屾暣 schema 濉叆 prompt 妯℃澘銆?

    Fill the prompt template with the question and full database schema.
    """
    return prompt_template.format(question=question, schema=schema)


def run_one(example: dict[str, Any], prompt_template: str, database_dir: Path) -> dict[str, Any]:
    """杩愯骞惰瘎娴嬪崟鏉℃牱鏈€?

    Run and evaluate one example by prompting the LLM with the question plus
    full schema, executing both predicted and gold SQL, then comparing answers.
    """
    # 鏍规嵁鏍锋湰鎵€灞炴暟鎹簱 ID 鎵惧埌瀵瑰簲 SQLite 鏂囦欢銆?
    # Locate the SQLite database file for this example's database ID.
    db_id = example["db_id"]
    db_path = get_database_path(database_dir, db_id)

    # 鍒濆鍖栨湰鏉℃牱鏈殑杩愯鐘舵€佸拰璁℃椂鍣ㄣ€?
    # Initialize per-example runtime state and latency timer.
    started_at = time.perf_counter()
    predicted_sql = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    generation_error: str | None = None

    try:
        # Baseline 1 鐨勬牳蹇冭緭鍏ワ細鑷劧璇█闂 + 瀹屾暣鏁版嵁搴?schema銆?
        # Core baseline 1 input: natural-language question + full DB schema.
        schema = extract_schema_text(db_path)
        prompt = build_prompt(example["question"], schema, prompt_template)
        llm_response = generate_sql(prompt)
        predicted_sql = clean_sql(llm_response.text)
        input_tokens = llm_response.input_tokens
        output_tokens = llm_response.output_tokens
    except Exception as e:
        generation_error = str(e)

    # 鍙湪鎴愬姛鐢熸垚 SQL 鍚庢墽琛岄娴?SQL锛涚敓鎴愬け璐ユ椂璁板綍閿欒銆?
    # Execute predicted SQL only after successful generation; otherwise record the error.
    predicted_exec = (
        execute_sql(db_path, predicted_sql)
        if predicted_sql and generation_error is None
        else {"answer": None, "error": generation_error or "No SQL generated"}
    )
    # 鎵ц鏁版嵁闆嗘彁渚涚殑鏍囧噯 SQL锛岀敤浣滅瓟妗堝鐓с€?
    # Execute the dataset-provided gold SQL as the answer reference.
    gold_exec = execute_sql(db_path, example["gold_sql"])

    latency_seconds = time.perf_counter() - started_at
    evaluation_fields = build_result_evaluation(
        predicted_sql,
        example["gold_sql"],
        predicted_answer=predicted_exec["answer"],
        gold_answer=gold_exec["answer"],
        predicted_error=predicted_exec["error"],
        gold_error=gold_exec["error"],
    )

    # correct 姣旇緝鐨勬槸鎵ц缁撴灉锛屼笉鏄?SQL 瀛楃涓叉湰韬€?
    # correct compares execution results, not raw SQL strings.
    return {
        "id": example["id"],
        "method": METHOD_NAME,
        "db_id": db_id,
        "question": example["question"],
        "predicted_sql": predicted_sql,
        "predicted_answer": predicted_exec["answer"],
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec["answer"],
        **evaluation_fields,
        "latency_seconds": round(latency_seconds, 4),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": 0,
    }


def run_baseline(
    dataset_path: str | Path = config.DEFAULT_DATASET_PATH,
    output_path: str | Path = OUTPUT_PATH,
    database_dir: str | Path = config.DATABASE_DIR,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """鎵归噺杩愯 baseline 1 骞朵繚瀛樼粨鏋溿€?

    Run baseline 1 over a dataset, save per-example results, and log execution
    accuracy.
    """
    # 璇诲彇闂鍒楄〃锛沴imit 鐢ㄤ簬蹇€熷皬瑙勬ā璋冭瘯銆?
    # Load examples; limit is useful for quick small-scale debugging.
    questions = load_questions(dataset_path)
    if limit is not None:
        questions = questions[:limit]

    logger.info("Starting %s with %d examples", METHOD_NAME, len(questions))
    logger.info("Dataset: %s", dataset_path)
    logger.info("Database dir: %s", database_dir)
    logger.info("Output: %s", output_path)

    # 鍚屼竴涓?prompt 妯℃澘浼氳澶嶇敤浜庢墍鏈夋牱鏈€?
    # The same prompt template is reused for all examples.
    prompt_template = read_text(PROMPT_PATH)
    output = Path(output_path)
    saved_results = read_json(output) if output.exists() else []
    if not isinstance(saved_results, list):
        raise ValueError(f"Expected result list in {output}")
    results_by_id = {
        row["id"]: row
        for row in saved_results
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    remaining = [row for row in questions if row["id"] not in results_by_id]
    if results_by_id:
        logger.info(
            "Resuming %s: loaded=%d remaining=%d",
            METHOD_NAME,
            len(results_by_id),
            len(remaining),
        )

    for example in tqdm(remaining, desc=METHOD_NAME):
        results_by_id[example["id"]] = run_one(
            example,
            prompt_template,
            Path(database_dir),
        )
        write_json(
            output,
            [results_by_id[row["id"]] for row in questions if row["id"] in results_by_id],
        )

    results = [results_by_id[row["id"]] for row in questions]

    # 淇濆瓨閫愭潯缁撴灉锛屽苟鍦ㄦ棩蹇椾腑璁板綍鏁翠綋鎵ц鍑嗙‘鐜囥€?
    # Save per-example results and log aggregate execution accuracy.
    write_json(output, results)
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
    """瑙ｆ瀽鍛戒护琛屽弬鏁般€?

    Parse command-line arguments for running baseline 1.
    """
    parser = argparse.ArgumentParser(description="Run baseline 1: Direct LLM + full schema.")
    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    """鍛戒护琛屽叆鍙ｅ嚱鏁般€?

    Command-line entry point for baseline 1.
    """
    args = parse_args()
    run_baseline(
        dataset_path=args.dataset,
        output_path=args.output,
        database_dir=args.database_dir,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()

