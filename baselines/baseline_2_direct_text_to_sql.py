"""Baseline 2: one-shot schema retrieval + direct text-to-SQL.

This baseline first retrieves top-k relevant tables and columns from the
database schema, then gives the LLM the user question plus that retrieved
schema. It does not inspect table contents, execute SQL during generation,
self-correct, or retry.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared import config
from shared.data_loader import load_questions
from shared.evaluator import is_correct
from shared.io_utils import read_text, write_json
from shared.llm_client import generate_sql
from shared.logging_utils import setup_logger
from shared.schema_utils import get_database_path, list_tables
from shared.sql_executor import execute_sql


METHOD_NAME = "baseline_2_direct_text_to_sql"
PROMPT_PATH = config.PROMPTS_DIR / "baseline_2_direct_text_to_sql.txt"
OUTPUT_PATH = config.RESULTS_DIR / f"{METHOD_NAME}.json"
LOG_PATH = config.PROJECT_ROOT / "logs" / "baseline_2.log"
DEFAULT_TOP_K_TABLES = 5
DEFAULT_TOP_K_COLUMNS = 8


logger = setup_logger(METHOD_NAME, LOG_PATH)
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True)
class ColumnInfo:
    """数据库列的 schema 信息。

    Schema information for one database column.
    """

    name: str
    column_type: str
    not_null: bool
    default_value: Any
    primary_key: bool


@dataclass(frozen=True)
class ForeignKeyInfo:
    """数据库外键的 schema 信息。

    Schema information for one database foreign key.
    """

    from_column: str
    ref_table: str
    ref_column: str


@dataclass(frozen=True)
class TableInfo:
    """数据库表的 schema 信息。

    Schema information for one database table.
    """

    name: str
    columns: list[ColumnInfo]
    foreign_keys: list[ForeignKeyInfo]


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


def tokenize(text: str) -> set[str]:
    """把问题、表名或列名切成可匹配的 token。

    Tokenize a question, table name, or column name into comparable tokens.
    """
    normalized = text.lower().replace("_", " ")
    return {token for token in TOKEN_RE.findall(normalized) if token not in STOPWORDS}


def score_name(name: str, question_tokens: set[str], question_lower: str) -> int:
    """计算表名或列名与问题的词面相关性分数。

    Compute a lexical relevance score between a schema name and the question.
    """
    name_lower = name.lower()
    name_text = name_lower.replace("_", " ")
    name_tokens = tokenize(name)
    score = 0

    if name_text in question_lower:
        score += 5

    for token in name_tokens:
        if token in question_tokens:
            score += 3
        if token in question_lower:
            score += 1

    for token in question_tokens:
        if token in name_lower:
            score += 1

    return score


def load_schema(db_path: str | Path) -> list[TableInfo]:
    """从 SQLite 数据库读取表、列和外键信息。

    Read table, column, and foreign-key metadata from a SQLite database.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    tables = list_tables(path)
    schema: list[TableInfo] = []

    with sqlite3.connect(path) as conn:
        for table in tables:
            quoted_table = table.replace('"', '""')
            raw_columns = conn.execute(f'PRAGMA table_info("{quoted_table}")').fetchall()
            raw_foreign_keys = conn.execute(
                f'PRAGMA foreign_key_list("{quoted_table}")'
            ).fetchall()

            columns = [
                ColumnInfo(
                    name=name,
                    column_type=column_type or "UNKNOWN",
                    not_null=bool(not_null),
                    default_value=default_value,
                    primary_key=bool(primary_key),
                )
                for _, name, column_type, not_null, default_value, primary_key in raw_columns
            ]
            foreign_keys = [
                ForeignKeyInfo(from_column=from_col, ref_table=ref_table, ref_column=to_col)
                for _, _, ref_table, from_col, to_col, *_ in raw_foreign_keys
            ]
            schema.append(TableInfo(name=table, columns=columns, foreign_keys=foreign_keys))

    return schema


def format_column(column: ColumnInfo) -> str:
    """把列信息格式化成 prompt 中的 schema 行。

    Format one column as a schema line for the prompt.
    """
    parts = [f"- {column.name}", column.column_type]
    if column.primary_key:
        parts.append("PRIMARY KEY")
    if column.not_null:
        parts.append("NOT NULL")
    if column.default_value is not None:
        parts.append(f"DEFAULT {column.default_value}")
    return " ".join(parts)


def format_retrieved_schema(tables: list[TableInfo], selected_columns: dict[str, list[ColumnInfo]]) -> str:
    """把检索到的表和列格式化成 schema 文本。

    Format retrieved tables and columns into prompt-ready schema text.
    """
    blocks: list[str] = []
    selected_table_names = {table.name for table in tables}

    for table in tables:
        columns = selected_columns.get(table.name, [])
        lines = [f"Table: {table.name}", "", "Columns:"]
        lines.extend(format_column(column) for column in columns)

        relevant_foreign_keys = [
            fk
            for fk in table.foreign_keys
            if fk.ref_table in selected_table_names
            or fk.from_column in {column.name for column in columns}
        ]
        if relevant_foreign_keys:
            lines.extend(["", "Foreign keys:"])
            for fk in relevant_foreign_keys:
                lines.append(f"- {fk.from_column} -> {fk.ref_table}.{fk.ref_column}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def retrieve_schema(
    question: str,
    db_path: str | Path,
    top_k_tables: int = DEFAULT_TOP_K_TABLES,
    top_k_columns: int = DEFAULT_TOP_K_COLUMNS,
) -> str:
    """检索与问题最相关的 top-k tables / columns。

    Retrieve top-k relevant tables and columns for the question.
    """
    top_k_tables = max(1, top_k_tables)
    top_k_columns = max(1, top_k_columns)

    schema = load_schema(db_path)
    question_lower = question.lower()
    question_tokens = tokenize(question)

    # 用表名和列名的词面匹配分数检索 schema，不查看表内容。
    # Retrieve schema with lexical table/column matching, without reading table contents.
    table_scores: list[tuple[int, TableInfo]] = []
    column_scores_by_table: dict[str, list[tuple[int, ColumnInfo]]] = {}

    for table in schema:
        column_scores = [
            (score_name(column.name, question_tokens, question_lower), column)
            for column in table.columns
        ]
        column_scores_by_table[table.name] = column_scores
        table_score = score_name(table.name, question_tokens, question_lower)
        top_column_scores = sorted(
            column_scores,
            key=lambda item: (-item[0], item[1].name),
        )[:3]
        table_score += sum(score for score, _ in top_column_scores)
        table_scores.append((table_score, table))

    ranked_tables = sorted(table_scores, key=lambda item: (-item[0], item[1].name))
    selected_tables = [table for _, table in ranked_tables[:top_k_tables]]

    selected_columns: dict[str, list[ColumnInfo]] = {}
    for table in selected_tables:
        scored_columns = column_scores_by_table[table.name]
        ranked_columns = sorted(scored_columns, key=lambda item: (-item[0], item[1].name))
        required_columns = {
            column.name
            for column in table.columns
            if column.primary_key
            or any(fk.from_column == column.name for fk in table.foreign_keys)
        }

        columns: list[ColumnInfo] = []
        for _, column in ranked_columns:
            if len(columns) < top_k_columns or column.name in required_columns:
                columns.append(column)

        selected_columns[table.name] = columns

    return format_retrieved_schema(selected_tables, selected_columns)


def build_prompt(question: str, retrieved_schema: str, prompt_template: str) -> str:
    """把问题和检索到的 schema 填入 prompt 模板。

    Fill the prompt template with the question and retrieved schema.
    """
    return prompt_template.format(question=question, retrieved_schema=retrieved_schema)


def run_one(
    example: dict[str, Any],
    prompt_template: str,
    database_dir: Path,
    top_k_tables: int = DEFAULT_TOP_K_TABLES,
    top_k_columns: int = DEFAULT_TOP_K_COLUMNS,
) -> dict[str, Any]:
    """运行并评测单条样本。

    Run and evaluate one example by prompting the LLM with the question plus
    retrieved schema, executing both predicted and gold SQL, then
    comparing answers.
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
    retrieved_schema = ""

    try:
        # Baseline 2 的核心输入：自然语言问题 + 一次性检索到的 schema。
        # Core baseline 2 input: natural-language question + one-shot retrieved schema.
        retrieved_schema = retrieve_schema(
            example["question"],
            db_path,
            top_k_tables=top_k_tables,
            top_k_columns=top_k_columns,
        )
        prompt = build_prompt(example["question"], retrieved_schema, prompt_template)
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
        "retrieved_schema": retrieved_schema,
        "top_k_tables": top_k_tables,
        "top_k_columns": top_k_columns,
        "predicted_sql": predicted_sql,
        "predicted_answer": predicted_exec["answer"],
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec["answer"],
        "correct": (
            predicted_exec["error"] is None
            and gold_exec["error"] is None
            and is_correct(
                predicted_exec["answer"],
                gold_exec["answer"],
                gold_sql=example["gold_sql"],
            )
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
    top_k_tables: int = DEFAULT_TOP_K_TABLES,
    top_k_columns: int = DEFAULT_TOP_K_COLUMNS,
    sleep: float = 0,
) -> list[dict[str, Any]]:
    """批量运行 baseline 2 并保存结果。

    Run baseline 2 over a dataset, save per-example results, and log execution
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
    logger.info("top_k_tables=%d top_k_columns=%d", top_k_tables, top_k_columns)

    # 同一个 prompt 模板会被复用于所有样本。
    # The same prompt template is reused for all examples.
    prompt_template = read_text(PROMPT_PATH)

    output_path = Path(output_path)
    results: list[dict[str, Any]] = []
    done_ids: set[str] = set()
    if output_path.exists():
        import json
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        results = existing
        done_ids = {r["id"] for r in results}
        logger.info("Resuming — %d already done", len(done_ids))
    questions = [q for q in questions if q["id"] not in done_ids]

    for example in tqdm(questions, desc=METHOD_NAME):
        results.append(run_one(
            example,
            prompt_template,
            Path(database_dir),
            top_k_tables=top_k_tables,
            top_k_columns=top_k_columns,
        ))
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

    Parse command-line arguments for running baseline 2.
    """
    parser = argparse.ArgumentParser(
        description="Run baseline 2: One-shot schema retrieval + text-to-SQL."
    )
    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--top-k-tables", type=int, default=DEFAULT_TOP_K_TABLES)
    parser.add_argument("--top-k-columns", type=int, default=DEFAULT_TOP_K_COLUMNS)
    parser.add_argument("--sleep", type=float, default=0)
    return parser.parse_args()


def main() -> None:
    """命令行入口函数。

    Command-line entry point for baseline 2.
    """
    args = parse_args()
    run_baseline(
        dataset_path=args.dataset,
        output_path=args.output,
        database_dir=args.database_dir,
        limit=args.limit,
        top_k_tables=args.top_k_tables,
        top_k_columns=args.top_k_columns,
        sleep=args.sleep,
    )


if __name__ == "__main__":
    main()
