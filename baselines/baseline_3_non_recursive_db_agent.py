"""Baseline 3: non-recursive DB agent.""

This baseline can inspect schema, sample relevant tables, generate SQL,
execute SQL, and retry after SQL execution errors.

It is non-recursive:
- no child agents
- no recursive sub-question decomposition
"""

from __future__ import annotations
from shared import config 
import argparse
import re
import sqlite3
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
from shared.schema_utils import extract_schema_text, get_database_path, list_tables
from shared.sql_executor import execute_sql


METHOD_NAME = "baseline_3_non_recursive_db_agent"
PROMPT_PATH = config.PROMPTS_DIR / "baseline_3_non_recursive_db_agent.txt"
OUTPUT_PATH = config.RESULTS_DIR / f"{METHOD_NAME}.json"
LOG_PATH = config.PROJECT_ROOT / "logs" / "baseline_3.log"
SELF_CHECK_PROMPT_PATH = config.PROMPTS_DIR / "baseline_3_self_check_sql.txt"
DEFAULT_ENABLE_SELF_CHECK = True
DEFAULT_TOP_K_TABLES = 5
DEFAULT_SAMPLE_ROWS = 3
DEFAULT_MAX_ATTEMPTS = 3

logger = setup_logger(METHOD_NAME, LOG_PATH)

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "and", "are", "as", "by", "for", "from", "in",
    "is", "of", "on", "or", "the", "to", "with", "what", "which",
    "who", "how", "many", "list", "show", "return", "give"
}

def extract_selected_schema_text(db_path: str | Path, selected_tables: list[str]) -> str:
    """Return schema text only for selected tables."""
    path = Path(db_path)

    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    selected_set = set(selected_tables)
    schema_blocks: list[str] = []

    with sqlite3.connect(path) as conn:
        for table in selected_tables:
            quoted_table = table.replace('"', '""')

            columns = conn.execute(
                f'PRAGMA table_info("{quoted_table}")'
            ).fetchall()

            foreign_keys = conn.execute(
                f'PRAGMA foreign_key_list("{quoted_table}")'
            ).fetchall()

            lines = [f"Table: {table}", "", "Columns:"]

            for column in columns:
                _, name, col_type, not_null, default_value, primary_key = column

                parts = [f"- {name}", col_type or "UNKNOWN"]

                if primary_key:
                    parts.append("PRIMARY KEY")

                if not_null:
                    parts.append("NOT NULL")

                if default_value is not None:
                    parts.append(f"DEFAULT {default_value}")

                lines.append(" ".join(parts))

            relevant_foreign_keys = [
                fk for fk in foreign_keys
                if fk[2] in selected_set
            ]

            if relevant_foreign_keys:
                lines.extend(["", "Foreign keys:"])
                for fk in relevant_foreign_keys:
                    _, _, ref_table, from_col, to_col, *_ = fk
                    lines.append(f"- {from_col} -> {ref_table}.{to_col}")

            schema_blocks.append("\n".join(lines))

    return "\n\n".join(schema_blocks)
def build_self_check_prompt(
    question: str,
    schema: str,
    table_samples: str,
    previous_sql: str,
    previous_answer: Any,
    prompt_template: str,
) -> str:
    return prompt_template.format(
        question=question,
        schema=schema,
        table_samples=table_samples,
        previous_sql=previous_sql,
        previous_answer=previous_answer,
    )
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


def tokenize(text: str) -> set[str]:
    normalized = text.lower().replace("_", " ")
    return {token for token in TOKEN_RE.findall(normalized) if token not in STOPWORDS}


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def get_table_columns(db_path: str | Path, table_name: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        quoted_table = table_name.replace('"', '""')
        rows = conn.execute(f'PRAGMA table_info("{quoted_table}")').fetchall()
    return [row[1] for row in rows]


def score_table(question: str, table_name: str, columns: list[str]) -> int:
    question_lower = question.lower()
    question_tokens = tokenize(question)

    score = 0

    table_text = table_name.lower().replace("_", " ")
    table_tokens = tokenize(table_name)

    if table_text in question_lower:
        score += 5

    for token in table_tokens:
        if token in question_tokens:
            score += 3
        if token in question_lower:
            score += 1

    for column in columns:
        column_text = column.lower().replace("_", " ")
        column_tokens = tokenize(column)

        if column_text in question_lower:
            score += 4

        for token in column_tokens:
            if token in question_tokens:
                score += 2
            if token in question_lower:
                score += 1

    return score


def select_relevant_tables(
    question: str,
    db_path: str | Path,
    top_k: int = DEFAULT_TOP_K_TABLES,
) -> list[str]:
    tables = list_tables(db_path)

    scored_tables = []
    for table in tables:
        columns = get_table_columns(db_path, table)
        score = score_table(question, table, columns)
        scored_tables.append((score, table))

    ranked = sorted(scored_tables, key=lambda item: (-item[0], item[1]))
    return [table for _, table in ranked[:top_k]]


def sample_table_rows(
    db_path: str | Path,
    table_name: str,
    limit: int = DEFAULT_SAMPLE_ROWS,
) -> dict[str, Any]:
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query = f"SELECT * FROM {quote_identifier(table_name)} LIMIT {limit}"
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]

        return {
            "table": table_name,
            "columns": columns,
            "rows": [list(row) for row in rows],
            "error": None,
        }

    except Exception as e:
        return {
            "table": table_name,
            "columns": [],
            "rows": [],
            "error": str(e),
        }


def build_table_samples_text(samples: list[dict[str, Any]]) -> str:
    blocks = []

    for sample in samples:
        lines = [f"Table: {sample['table']}"]

        if sample["error"]:
            lines.append(f"Sampling error: {sample['error']}")
        else:
            lines.append(f"Columns: {sample['columns']}")
            lines.append(f"Sample rows: {sample['rows']}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def build_prompt(
    question: str,
    schema: str,
    table_samples: str,
    prompt_template: str,
    previous_sql: str | None = None,
    previous_error: str | None = None,
) -> str:
    return prompt_template.format(
        question=question,
        schema=schema,
        table_samples=table_samples,
        previous_sql=previous_sql or "",
        previous_error=previous_error or "",
    )


def run_one(
    
    example: dict[str, Any],
    prompt_template: str,
    self_check_prompt_template: str,
    database_dir: Path,
    top_k_tables: int = DEFAULT_TOP_K_TABLES,
    sample_rows: int = DEFAULT_SAMPLE_ROWS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    enable_self_check: bool = DEFAULT_ENABLE_SELF_CHECK,
) -> dict[str, Any]:
    db_id = example["db_id"]
    db_path = get_database_path(database_dir, db_id)

    started_at = time.perf_counter()

    predicted_sql = ""
    predicted_exec = {"answer": None, "error": "No SQL generated"}

    input_tokens_total = 0
    output_tokens_total = 0

    agent_trace: list[dict[str, Any]] = []

    # Step 1: select relevant tables
    selected_tables = select_relevant_tables(
        question=example["question"],
        db_path=db_path,
        top_k=top_k_tables,
    )

    # Step 2: extract schema only for selected tables
    schema = extract_selected_schema_text(db_path, selected_tables)

    agent_trace.append({
        "step": "inspect_selected_schema",
        "selected_tables": selected_tables,
        "observation_preview": schema[:2000],
    })

    samples = [
        sample_table_rows(db_path, table, sample_rows)
        for table in selected_tables
    ]

    table_samples_text = build_table_samples_text(samples)

    agent_trace.append({
        "step": "sample_tables",
        "selected_tables": selected_tables,
        "samples": samples,
    })

    previous_sql = None
    previous_error = None

    # Step 3: generate SQL, execute, retry if SQL error happens
    for attempt in range(1, max_attempts + 1):
        prompt = build_prompt(
            question=example["question"],
            schema=schema,
            table_samples=table_samples_text,
            prompt_template=prompt_template,
            previous_sql=previous_sql,
            previous_error=previous_error,
        )

        try:
            llm_response = generate_sql(prompt)
            predicted_sql = clean_sql(llm_response.text)

            if llm_response.input_tokens is not None:
                input_tokens_total += llm_response.input_tokens

            if llm_response.output_tokens is not None:
                output_tokens_total += llm_response.output_tokens

        except Exception as e:
            predicted_exec = {"answer": None, "error": str(e)}

            agent_trace.append({
                "step": "llm_generation_error",
                "attempt": attempt,
                "error": str(e),
            })

            break

        predicted_exec = execute_sql(db_path, predicted_sql)

        agent_trace.append({
            "step": "execute_sql",
            "attempt": attempt,
            "predicted_sql": predicted_sql,
            "answer": predicted_exec["answer"],
            "error": predicted_exec["error"],
        })

        if predicted_exec["error"] is None:
            if enable_self_check:
                try:
                    self_check_prompt = build_self_check_prompt(
                        question=example["question"],
                        schema=schema,
                        table_samples=table_samples_text,
                        previous_sql=predicted_sql,
                        previous_answer=predicted_exec["answer"],
                        prompt_template=self_check_prompt_template,
                    )

                    self_check_response = generate_sql(self_check_prompt)
                    refined_sql = clean_sql(self_check_response.text)

                    if self_check_response.input_tokens is not None:
                        input_tokens_total += self_check_response.input_tokens

                    if self_check_response.output_tokens is not None:
                        output_tokens_total += self_check_response.output_tokens

                    refined_exec = execute_sql(db_path, refined_sql)

                    agent_trace.append({
                        "step": "self_check_sql",
                        "attempt": attempt,
                        "original_sql": predicted_sql,
                        "original_answer": predicted_exec["answer"],
                        "refined_sql": refined_sql,
                        "refined_answer": refined_exec["answer"],
                        "refined_error": refined_exec["error"],
                    })

                    # Only replace the SQL if the refined SQL executes successfully.
                    if refined_exec["error"] is None:
                        predicted_sql = refined_sql
                        predicted_exec = refined_exec

                except Exception as e:
                    agent_trace.append({
                        "step": "self_check_error",
                        "attempt": attempt,
                        "error": str(e),
                    })

            break

        previous_sql = predicted_sql
        previous_error = predicted_exec["error"]

    # Step 4: evaluate against gold SQL
    gold_exec = execute_sql(db_path, example["gold_sql"])
    latency_seconds = time.perf_counter() - started_at

    error = predicted_exec["error"] or gold_exec["error"]

    correct = (
        predicted_exec["error"] is None
        and gold_exec["error"] is None
        and is_correct(predicted_exec["answer"], gold_exec["answer"])
    )

    return {
        "id": example["id"],
        "method": METHOD_NAME,
        "db_id": db_id,
        "question": example["question"],
        "selected_tables": selected_tables,
        "table_samples": samples,
        "predicted_sql": predicted_sql,
        "predicted_answer": predicted_exec["answer"],
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec["answer"],
        "correct": correct,
        "error": error,
        "latency_seconds": round(latency_seconds, 4),
        "input_tokens": input_tokens_total or None,
        "output_tokens": output_tokens_total or None,
        "attempts": len([step for step in agent_trace if step["step"] == "execute_sql"]),
        "agent_trace": agent_trace,
    }


def run_baseline(
    dataset_path: str | Path = config.DEFAULT_DATASET_PATH,
    output_path: str | Path = OUTPUT_PATH,
    database_dir: str | Path = config.DATABASE_DIR,
    limit: int | None = None,
    top_k_tables: int = DEFAULT_TOP_K_TABLES,
    sample_rows: int = DEFAULT_SAMPLE_ROWS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    enable_self_check: bool = DEFAULT_ENABLE_SELF_CHECK,
) -> list[dict[str, Any]]:
    questions = load_questions(dataset_path)

    if limit is not None:
        questions = questions[:limit]

    logger.info("Starting %s with %d examples", METHOD_NAME, len(questions))
    logger.info("Dataset: %s", dataset_path)
    logger.info("Database dir: %s", database_dir)
    logger.info("Output: %s", output_path)
    logger.info(
        "top_k_tables=%d sample_rows=%d max_attempts=%d",
        top_k_tables,
        sample_rows,
        max_attempts,
    )

    prompt_template = read_text(PROMPT_PATH)
    self_check_prompt_template = read_text(SELF_CHECK_PROMPT_PATH)

    results = [
        run_one(
    example=example,
    prompt_template=prompt_template,
    self_check_prompt_template=self_check_prompt_template,
    database_dir=Path(database_dir),
    top_k_tables=top_k_tables,
    sample_rows=sample_rows,
    max_attempts=max_attempts,
    enable_self_check=enable_self_check,
)
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
    parser = argparse.ArgumentParser(
        description="Run baseline 3: Non-recursive DB agent."
    )

    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--top-k-tables", type=int, default=DEFAULT_TOP_K_TABLES)
    parser.add_argument("--sample-rows", type=int, default=DEFAULT_SAMPLE_ROWS)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument(
    "--no-self-check",
    action="store_true",
    help="Disable the SQL self-check/refinement step.",
)
    return parser.parse_args()


def main() -> None:
   
    args = parse_args()

    run_baseline(
    dataset_path=args.dataset,
    output_path=args.output,
    database_dir=args.database_dir,
    limit=args.limit,
    top_k_tables=args.top_k_tables,
    sample_rows=args.sample_rows,
    max_attempts=args.max_attempts,
    enable_self_check=not args.no_self_check,
)


if __name__ == "__main__":
    main()