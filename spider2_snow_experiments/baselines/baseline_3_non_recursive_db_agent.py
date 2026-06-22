"""Baseline 3: non-recursive multi-step Spider2-Snow database agent."""

from __future__ import annotations

import argparse
import json
from typing import Any

from spider2_snow_experiments import config, snowflake_backend
from spider2_snow_experiments.data import Spider2SnowExample
from spider2_snow_experiments.llm import chat
from spider2_snow_experiments.result_utils import clean_sql, postprocess_sql
from spider2_snow_experiments.runner import Prediction, add_common_args, run_method
from spider2_snow_experiments.schema import (
    SchemaTable,
    build_example_context,
    format_schema_tables,
)
from spider2_snow_experiments.sql_generation import validate_and_repair_sql


METHOD_NAME = "baseline_3_non_recursive_db_agent"
PROMPT_PATH = config.PROMPTS_DIR / "baseline_3_non_recursive_db_agent.txt"
MAX_OBSERVATION_CHARS = 12000


def _truncate(value: Any, max_chars: int = MAX_OBSERVATION_CHARS) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2) if not isinstance(value, str) else value
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n[TRUNCATED]"


def _parse_action(text: str) -> dict[str, Any]:
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
        action, _ = json.JSONDecoder().raw_decode(candidate[start:])

    if not isinstance(action, dict):
        raise ValueError("Agent action must be a JSON object")
    action_name = action.get("action")
    if not isinstance(action_name, str):
        raise ValueError("Agent action is missing string field: action")
    action["action"] = action_name.upper()
    return action


def _table_key(table: SchemaTable) -> str:
    return table.schema_qualified_name


def _resolve_table(tables: list[SchemaTable], requested_name: Any) -> SchemaTable:
    if not isinstance(requested_name, str) or not requested_name.strip():
        raise ValueError("A non-empty table name is required")
    requested = requested_name.strip().lower()
    for table in tables:
        if requested in {name.lower() for name in table.reference_names}:
            return table
    raise ValueError(f"Unknown table: {requested_name}")


def _run_tool(
    action: dict[str, Any],
    *,
    example: Spider2SnowExample,
    tables: list[SchemaTable],
    settings: config.Settings,
    allow_live_tools: bool,
    timeout: int,
) -> dict[str, Any]:
    action_name = action["action"]
    if action_name == "SHOW_TABLE_SCHEMA":
        action_name = "DESCRIBE_TABLE"
    if action_name == "SHOW_TABLES":
        return {
            "tables": [
                {
                    "schema": table.schema_name,
                    "table": table.short_name,
                    "schema_qualified_name": table.schema_qualified_name,
                    "full_name": table.full_name,
                    "name": table.full_name,
                    "description": table.description,
                }
                for table in tables
            ]
        }
    if action_name == "DESCRIBE_TABLE":
        table = _resolve_table(tables, action.get("table") or action.get("table_name"))
        return {
            "schema": table.schema_name,
            "table": table.short_name,
            "schema_qualified_name": table.schema_qualified_name,
            "full_name": table.full_name,
            "ddl": table.ddl,
        }
    if action_name in {"SAMPLE_ROWS", "EXECUTE_SQL"} and not allow_live_tools:
        return {
            "error": (
                f"{action_name} is disabled. Re-run with --allow-live-tools "
                "to query Snowflake during generation."
            )
        }
    if action_name == "SAMPLE_ROWS":
        table = _resolve_table(tables, action.get("table"))
        limit = int(action.get("limit") or 3)
        sql = f"SELECT * FROM {table.full_name} LIMIT {max(1, min(limit, 10))}"
        return snowflake_backend.execute_sql(
            example.db_id,
            sql,
            credential_path=settings.credential_path,
            timeout=timeout,
            max_rows=10,
        )
    if action_name == "EXECUTE_SQL":
        sql = clean_sql(str(action.get("sql") or ""))
        if not sql:
            return {"error": "EXECUTE_SQL requires non-empty sql"}
        sql, diagnostics = postprocess_sql(sql, tables)
        result = snowflake_backend.execute_sql(
            example.db_id,
            sql,
            credential_path=settings.credential_path,
            timeout=timeout,
            max_rows=20,
        )
        result["normalized_sql"] = sql
        result["sql_postprocess"] = diagnostics
        return result
    raise ValueError(f"Unsupported action: {action_name}")


def predict(example: Spider2SnowExample, settings: config.Settings, args: argparse.Namespace) -> Prediction:
    context = build_example_context(
        example,
        databases_dir=settings.databases_dir,
        documents_dir=settings.documents_dir,
        max_schema_chars=settings.schema_max_chars,
        max_document_chars=settings.document_max_chars,
        top_k_tables=args.initial_top_k_tables,
    )
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    system_instruction = prompt_template.format(
        max_steps=args.max_steps,
        db_id=example.db_id,
        live_tools_status="enabled" if args.allow_live_tools else "disabled",
        external_knowledge=context.document_text or "[None]",
        initial_schema=format_schema_tables(context.schema_tables),
    )
    repair_prompt = (
        f"Instance: {example.instance_id}\n"
        f"Question:\n{example.question}\n\n"
        "Repair the final SQL if needed using the schema context in the system prompt."
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Instance: {example.instance_id}\n"
                f"Question:\n{example.question}\n\n"
                "Choose the first database action."
            ),
        }
    ]
    trace: list[dict[str, Any]] = []
    input_tokens: int | None = None
    output_tokens: int | None = None
    last_sql = ""
    raw_response = ""

    def build_prediction(
        *,
        sql: str,
        raw: str,
        termination_reason: str,
    ) -> Prediction:
        validated = validate_and_repair_sql(
            prompt=repair_prompt,
            system_instruction=system_instruction,
            settings=settings,
            schema_tables=context.schema_tables,
            initial_sql=sql,
            initial_raw_response=raw,
            db_id=example.db_id,
            credential_path=str(settings.credential_path),
            validate_execution=args.repair_with_execution,
            execution_timeout=args.snowflake_timeout,
            max_repair_attempts=args.repair_max_attempts,
        )
        return Prediction(
            sql=validated.sql,
            raw_response=validated.raw_response,
            input_tokens=(input_tokens or 0) + (validated.input_tokens or 0),
            output_tokens=(output_tokens or 0) + (validated.output_tokens or 0),
            extra={
                "agent_steps": len(trace),
                "tool_trace": trace,
                "termination_reason": termination_reason,
                "live_tools_enabled": args.allow_live_tools,
                "sql_validation": validated.diagnostics,
                "repair_attempted": validated.repair_attempted,
                "repair_attempts": validated.repair_attempts,
                "execution_validation": validated.execution_validation,
            },
        )

    for step in range(1, args.max_steps + 1):
        if step == args.max_steps:
            messages.append(
                {
                    "role": "user",
                    "content": "This is the final step. Return FINAL with executable SQL.",
                }
            )

        response = chat(messages, system_instruction=system_instruction, settings=settings)
        raw_response = response.text
        input_tokens = (input_tokens or 0) + (response.input_tokens or 0)
        output_tokens = (output_tokens or 0) + (response.output_tokens or 0)
        messages.append({"role": "assistant", "content": response.text})

        try:
            action = _parse_action(response.text)
        except Exception as error:
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
                        f"Observation:\n{_truncate(observation)}\n"
                        "Return exactly one valid JSON action."
                    ),
                }
            )
            continue

        if action["action"] == "FINAL":
            final_sql = clean_sql(str(action.get("sql") or ""))
            trace.append({"step": step, "action": action, "observation": None})
            return build_prediction(
                sql=final_sql,
                raw=raw_response,
                termination_reason="final",
            )

        try:
            observation = _run_tool(
                action,
                example=example,
                tables=context.schema_tables,
                settings=settings,
                allow_live_tools=args.allow_live_tools,
                timeout=args.snowflake_timeout,
            )
            if action["action"] == "EXECUTE_SQL" and observation.get("error") is None:
                last_sql = clean_sql(
                    str(observation.get("normalized_sql") or action.get("sql") or "")
                )
        except Exception as error:
            observation = {"error": str(error)}

        trace.append({"step": step, "action": action, "observation": observation})
        messages.append(
            {
                "role": "user",
                "content": f"Observation:\n{_truncate(observation)}\nChoose the next action.",
            }
        )

    if last_sql:
        return build_prediction(
            sql=last_sql,
            raw=raw_response,
            termination_reason="max_steps_fallback",
        )

    return Prediction(
        sql=last_sql,
        raw_response=raw_response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        extra={
            "agent_steps": len(trace),
            "tool_trace": trace,
            "termination_reason": "max_steps_fallback" if last_sql else "max_steps_no_sql",
            "live_tools_enabled": args.allow_live_tools,
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Spider2-Snow baseline 3.")
    add_common_args(parser)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--initial-top-k-tables", type=int, default=25)
    parser.add_argument(
        "--allow-live-tools",
        action="store_true",
        help="Allow SAMPLE_ROWS and EXECUTE_SQL during agent reasoning.",
    )
    return parser.parse_args()


def main() -> None:
    run_method(method_name=METHOD_NAME, predict_fn=predict, args=parse_args())


if __name__ == "__main__":
    main()
