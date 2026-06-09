"""Baseline 3: non-recursive multi-step database agent."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from tqdm import tqdm

from shared import config
from shared.data_loader import load_questions
from shared.evaluator import is_correct
from shared.io_utils import read_text, write_json
from shared.llm_client import generate_chat
from shared.logging_utils import setup_logger
from shared.schema_utils import get_database_path, list_tables
from shared.sql_executor import execute_sql


METHOD_NAME = "baseline_3_non_recursive_db_agent"
PROMPT_PATH = config.PROMPTS_DIR / "baseline_3_non_recursive_db_agent.txt"
OUTPUT_PATH = config.RESULTS_DIR / f"{METHOD_NAME}.json"
LOG_PATH = config.PROJECT_ROOT / "logs" / "baseline_3.log"
DEFAULT_MAX_STEPS = 8
DEFAULT_SAMPLE_LIMIT = 3
MAX_SAMPLE_LIMIT = 10
MAX_OBSERVATION_ROWS = 20
TOOL_ACTIONS = {"SHOW_TABLES", "DESCRIBE_TABLE", "SAMPLE_ROWS", "EXECUTE_SQL"}


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


def parse_action(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    try:
        action = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        if start < 0:
            raise ValueError("Agent response does not contain a JSON object")
        try:
            action, _ = json.JSONDecoder().raw_decode(candidate[start:])
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid agent JSON: {candidate}") from error

    if not isinstance(action, dict):
        raise ValueError("Agent action must be a JSON object")
    action_name = action.get("action")
    if not isinstance(action_name, str):
        raise ValueError("Agent action is missing a string 'action' field")
    action["action"] = action_name.upper()
    return action


def resolve_table_name(db_path: Path, requested_name: Any) -> str:
    if not isinstance(requested_name, str) or not requested_name.strip():
        raise ValueError("A non-empty table name is required")

    requested = requested_name.strip()
    table_map = {table.lower(): table for table in list_tables(db_path)}
    if requested.lower() not in table_map:
        raise ValueError(f"Unknown table: {requested}")
    return table_map[requested.lower()]


def quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def describe_table(db_path: Path, table_name: Any) -> dict[str, Any]:
    table = resolve_table_name(db_path, table_name)
    quoted_table = quote_identifier(table)
    with sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True) as conn:
        columns = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        foreign_keys = conn.execute(f"PRAGMA foreign_key_list({quoted_table})").fetchall()

    return {
        "table": table,
        "columns": [
            {
                "name": row[1],
                "type": row[2] or "UNKNOWN",
                "not_null": bool(row[3]),
                "default": row[4],
                "primary_key": bool(row[5]),
            }
            for row in columns
        ],
        "foreign_keys": [
            {
                "column": row[3],
                "references_table": row[2],
                "references_column": row[4],
            }
            for row in foreign_keys
        ],
    }


def sample_rows(db_path: Path, table_name: Any, requested_limit: Any) -> dict[str, Any]:
    table = resolve_table_name(db_path, table_name)
    if requested_limit is None:
        limit = DEFAULT_SAMPLE_LIMIT
    elif isinstance(requested_limit, int):
        limit = max(1, min(requested_limit, MAX_SAMPLE_LIMIT))
    else:
        raise ValueError("SAMPLE_ROWS limit must be an integer")

    quoted_table = quote_identifier(table)
    with sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True) as conn:
        cursor = conn.execute(f"SELECT * FROM {quoted_table} LIMIT ?", (limit,))
        columns = [description[0] for description in cursor.description or []]
        rows = [list(row) for row in cursor.fetchall()]

    return {"table": table, "columns": columns, "rows": rows}


def execute_tool_sql(db_path: Path, sql: Any) -> dict[str, Any]:
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("EXECUTE_SQL requires a non-empty SQL string")

    result = execute_sql(db_path, clean_sql(sql), read_only=True)
    answer = result["answer"]
    truncated = isinstance(answer, list) and len(answer) > MAX_OBSERVATION_ROWS
    if truncated:
        answer = answer[:MAX_OBSERVATION_ROWS]
    return {
        "answer": answer,
        "error": result["error"],
        "truncated": truncated,
    }


def run_tool(db_path: Path, action: dict[str, Any]) -> dict[str, Any]:
    action_name = action["action"]
    if action_name == "SHOW_TABLES":
        return {"tables": list_tables(db_path)}
    if action_name == "DESCRIBE_TABLE":
        return describe_table(db_path, action.get("table"))
    if action_name == "SAMPLE_ROWS":
        return sample_rows(db_path, action.get("table"), action.get("limit"))
    if action_name == "EXECUTE_SQL":
        return execute_tool_sql(db_path, action.get("sql"))
    raise ValueError(f"Unsupported tool action: {action_name}")


def add_optional_tokens(total: int | None, value: int | None) -> int | None:
    if value is None:
        return total
    return (total or 0) + value


def run_agent(
    question: str,
    db_path: Path,
    prompt_template: str,
    max_steps: int,
) -> dict[str, Any]:
    system_instruction = prompt_template.replace("{max_steps}", str(max_steps))
    messages = [
        {
            "role": "user",
            "content": (
                f"Original question:\n{question}\n\n"
                "Choose the first database action."
            ),
        }
    ]
    trace: list[dict[str, Any]] = []
    input_tokens: int | None = None
    output_tokens: int | None = None
    last_successful_sql = ""

    for step in range(1, max_steps + 1):
        if step == max_steps:
            messages.append(
                {
                    "role": "user",
                    "content": "This is the final turn. Return the FINAL action now.",
                }
            )

        response = generate_chat(messages, system_instruction=system_instruction)
        input_tokens = add_optional_tokens(input_tokens, response.input_tokens)
        output_tokens = add_optional_tokens(output_tokens, response.output_tokens)
        messages.append({"role": "assistant", "content": response.text})

        try:
            action = parse_action(response.text)
        except ValueError as error:
            observation = {"error": str(error)}
            trace.append(
                {
                    "step": step,
                    "action": "INVALID",
                    "raw_response": response.text,
                    "observation": observation,
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Observation:\n{json.dumps(observation, ensure_ascii=False)}\n"
                        "Return one valid JSON action."
                    ),
                }
            )
            continue

        action_name = action["action"]
        if action_name == "FINAL":
            final_sql = clean_sql(str(action.get("sql") or ""))
            if not final_sql:
                observation = {"error": "FINAL requires a non-empty SQL string"}
                trace.append(
                    {
                        "step": step,
                        "action": action,
                        "observation": observation,
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Observation:\n{json.dumps(observation)}\n"
                            "Return FINAL with executable SQLite SQL."
                        ),
                    }
                )
                continue
            trace.append({"step": step, "action": action, "observation": None})
            return {
                "sql": final_sql,
                "trace": trace,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "termination_reason": "final",
            }

        try:
            observation = run_tool(db_path, action)
            if (
                action_name == "EXECUTE_SQL"
                and observation.get("error") is None
                and isinstance(action.get("sql"), str)
            ):
                last_successful_sql = clean_sql(action["sql"])
        except Exception as error:
            observation = {"error": str(error)}

        trace.append(
            {
                "step": step,
                "action": action,
                "observation": observation,
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Observation:\n{json.dumps(observation, ensure_ascii=False)}\n"
                    "Choose the next action."
                ),
            }
        )

    return {
        "sql": last_successful_sql,
        "trace": trace,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "termination_reason": (
            "max_steps_fallback" if last_successful_sql else "max_steps_no_sql"
        ),
    }


def run_one(
    example: dict[str, Any],
    prompt_template: str,
    database_dir: Path,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> dict[str, Any]:
    db_id = example["db_id"]
    db_path = get_database_path(database_dir, db_id)
    started_at = time.perf_counter()
    predicted_sql = ""
    trace: list[dict[str, Any]] = []
    input_tokens: int | None = None
    output_tokens: int | None = None
    termination_reason = "error"
    generation_error: str | None = None

    try:
        agent_result = run_agent(
            example["question"],
            db_path,
            prompt_template,
            max_steps=max_steps,
        )
        predicted_sql = agent_result["sql"]
        trace = agent_result["trace"]
        input_tokens = agent_result["input_tokens"]
        output_tokens = agent_result["output_tokens"]
        termination_reason = agent_result["termination_reason"]
    except Exception as error:
        generation_error = str(error)

    predicted_exec = (
        execute_sql(db_path, predicted_sql, read_only=True)
        if predicted_sql and generation_error is None
        else {"answer": None, "error": generation_error or "No SQL generated"}
    )
    gold_exec = execute_sql(db_path, example["gold_sql"], read_only=True)
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
        "agent_steps": len(trace),
        "tool_calls": sum(
            1
            for item in trace
            if isinstance(item.get("action"), dict)
            and item["action"].get("action") in TOOL_ACTIONS
        ),
        "termination_reason": termination_reason,
        "tool_trace": trace,
    }


def run_baseline(
    dataset_path: str | Path = config.DEFAULT_DATASET_PATH,
    output_path: str | Path = OUTPUT_PATH,
    database_dir: str | Path = config.DATABASE_DIR,
    limit: int | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> list[dict[str, Any]]:
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")

    questions = load_questions(dataset_path)
    if limit is not None:
        questions = questions[:limit]

    logger.info("Starting %s with %d examples", METHOD_NAME, len(questions))
    logger.info("Dataset: %s", dataset_path)
    logger.info("Database dir: %s", database_dir)
    logger.info("Output: %s", output_path)
    logger.info("max_steps=%d", max_steps)

    prompt_template = read_text(PROMPT_PATH)
    results = [
        run_one(
            example,
            prompt_template,
            Path(database_dir),
            max_steps=max_steps,
        )
        for example in tqdm(questions, desc=METHOD_NAME)
    ]

    write_json(output_path, results)
    total = len(results)
    correct = sum(1 for row in results if row["correct"])
    accuracy = correct / total if total else 0
    tool_calls = sum(row["tool_calls"] for row in results)
    logger.info(
        "Finished %s: total=%d correct=%d execution_accuracy=%.4f tool_calls=%d",
        METHOD_NAME,
        total,
        correct,
        accuracy,
        tool_calls,
    )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run baseline 3: Non-recursive multi-step DB agent."
    )
    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_baseline(
        dataset_path=args.dataset,
        output_path=args.output,
        database_dir=args.database_dir,
        limit=args.limit,
        max_steps=args.max_steps,
    )


if __name__ == "__main__":
    main()
