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
    """清理 LLM 输出中的 Markdown 代码块，只保留 SQL。

    Clean Markdown code fences from the LLM output and keep only SQL.
    """
    sql = text.strip()
    if sql.startswith("```"):
        # 去掉 ```sql ... ``` 这类 Markdown 包裹。
        # Remove Markdown fences such as ```sql ... ```.
        lines = sql.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines).strip()
    return sql


def build_prompt(question: str, schema: str, prompt_template: str) -> str:
    """把问题和完整 schema 填入 prompt 模板。

    Fill the prompt template with the question and full database schema.
    """
    return prompt_template.format(question=question, schema=schema)


def run_one(example: dict[str, Any], prompt_template: str, database_dir: Path) -> dict[str, Any]:
    """运行并评测单条样本。

    Run and evaluate one example by prompting the LLM with the question plus
    full schema, executing both predicted and gold SQL, then comparing answers.
    """
    # 根据样本所属数据库 ID 找到对应 SQLite 文件。
    # Locate the SQLite database file for this example's database ID.
    db_id = example["db_id"]
    db_path = get_database_path(database_dir, db_id)

    # 初始化本条样本的运行状态和计时器。
    # Initialize per-example runtime state and latency timer.
    started_at = time.perf_counter()
    predicted_sql = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    generation_error: str | None = None

    try:
        # Baseline 1 的核心输入：自然语言问题 + 完整数据库 schema。
        # Core baseline 1 input: natural-language question + full DB schema.
        schema = extract_schema_text(db_path)
        prompt = build_prompt(example["question"], schema, prompt_template)
        llm_response = generate_sql(prompt)
        predicted_sql = clean_sql(llm_response.text)
        input_tokens = llm_response.input_tokens
        output_tokens = llm_response.output_tokens
    except Exception as e:
        generation_error = str(e)

    # 只在成功生成 SQL 后执行预测 SQL；生成失败时记录错误。
    # Execute predicted SQL only after successful generation; otherwise record the error.
    predicted_exec = (
        execute_sql(db_path, predicted_sql)
        if predicted_sql and generation_error is None
        else {"answer": None, "error": generation_error or "No SQL generated"}
    )
    # 执行数据集提供的标准 SQL，用作答案对照。
    # Execute the dataset-provided gold SQL as the answer reference.
    gold_exec = execute_sql(db_path, example["gold_sql"])

    latency_seconds = time.perf_counter() - started_at
    error = predicted_exec["error"] or gold_exec["error"]

    # correct 比较的是执行结果，不是 SQL 字符串本身。
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
    sleep: float = 0,
) -> list[dict[str, Any]]:
    """批量运行 baseline 1 并保存结果。

    Run baseline 1 over a dataset, save per-example results, and log execution
    accuracy.
    """
    # 读取问题列表；limit 用于快速小规模调试。
    # Load examples; limit is useful for quick small-scale debugging.
    questions = load_questions(dataset_path)
    if limit is not None:
        questions = questions[:limit]

    logger.info("Starting %s with %d examples", METHOD_NAME, len(questions))
    logger.info("Dataset: %s", dataset_path)
    logger.info("Database dir: %s", database_dir)
    logger.info("Output: %s", output_path)

    # 同一个 prompt 模板会被复用于所有样本。
    # The same prompt template is reused for all examples.
    prompt_template = read_text(PROMPT_PATH)

    output_path = Path(output_path)
    results: list[dict[str, Any]] = []
    done_ids: set[str] = set()
    if output_path.exists():
        import json
        existing = json.loads(output_path.read_text())
        results = existing
        done_ids = {r["id"] for r in results}
        logger.info("Resuming — %d already done", len(done_ids))
    questions = [q for q in questions if q["id"] not in done_ids]

    for example in tqdm(questions, desc=METHOD_NAME):
        results.append(run_one(example, prompt_template, Path(database_dir)))
        write_json(output_path, results)
        if sleep > 0:
            time.sleep(sleep)
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
    """解析命令行参数。

    Parse command-line arguments for running baseline 1.
    """
    parser = argparse.ArgumentParser(description="Run baseline 1: Direct LLM + full schema.")
    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0)
    return parser.parse_args()


def main() -> None:
    """命令行入口函数。

    Command-line entry point for baseline 1.
    """
    args = parse_args()
    run_baseline(
        dataset_path=args.dataset,
        output_path=args.output,
        database_dir=args.database_dir,
        limit=args.limit,
        sleep=args.sleep,
    )


if __name__ == "__main__":
    main()
