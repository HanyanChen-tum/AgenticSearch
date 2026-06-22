"""Validated SQL generation helpers for Spider2-Snow baselines."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from spider2_snow_experiments import config, snowflake_backend
from spider2_snow_experiments.llm import generate_sql
from spider2_snow_experiments.result_utils import clean_sql, postprocess_sql
from spider2_snow_experiments.schema import SchemaTable


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    raw_response: str
    input_tokens: int | None
    output_tokens: int | None
    diagnostics: dict[str, object]
    repair_attempted: bool
    repair_attempts: int = 0
    execution_validation: dict[str, object] | None = None


def _needs_repair(diagnostics: dict[str, object]) -> bool:
    return bool(
        diagnostics.get("placeholder_detected")
        or diagnostics.get("unknown_table_refs")
        or diagnostics.get("unknown_column_refs")
    )


def _is_read_only_sql(sql: str) -> bool:
    return bool(re.match(r"^\s*(?:SELECT|WITH)\b", sql, re.IGNORECASE))


def _validate_execution(
    sql: str,
    *,
    db_id: str,
    credential_path: str,
    timeout: int,
) -> dict[str, object]:
    if not _is_read_only_sql(sql):
        return {
            "error": "Execution validation only supports SELECT/WITH queries.",
            "rows_returned": None,
        }
    result = snowflake_backend.execute_sql(
        db_id,
        sql,
        credential_path=credential_path,
        timeout=timeout,
        max_rows=1,
    )
    answer = result.get("answer")
    return {
        "error": result.get("error"),
        "rows_returned": len(answer) if isinstance(answer, list) else None,
        "columns": result.get("columns") or [],
    }


def _build_repair_prompt(
    prompt: str,
    *,
    previous_sql: str,
    diagnostics: dict[str, object],
    execution_validation: dict[str, object] | None,
) -> str:
    execution_section = ""
    if execution_validation and execution_validation.get("error"):
        execution_section = (
            "\nExecution validation error from Snowflake:\n"
            f"{execution_validation['error']}\n"
        )
    return (
        f"{prompt}\n\n"
        "The previous SQL failed validation.\n"
        "Repair it using only the DDL objects and columns shown above.\n"
        "Use exact fully-qualified table names.\n"
        "Quote mixed-case columns, use Snowflake VARIANT path syntax where needed, "
        "and cast string dates before date functions.\n"
        "Do not include placeholders.\n\n"
        f"Previous SQL:\n{previous_sql}\n\n"
        f"Local validation diagnostics:\n{json.dumps(diagnostics, ensure_ascii=False, indent=2)}\n"
        f"{execution_section}\n"
        "Return only corrected executable Snowflake SQL."
    )


def validate_and_repair_sql(
    *,
    prompt: str,
    system_instruction: str,
    settings: config.Settings,
    schema_tables: list[SchemaTable],
    initial_sql: str,
    initial_raw_response: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    db_id: str | None = None,
    credential_path: str | None = None,
    validate_execution: bool = False,
    execution_timeout: int = 60,
    max_repair_attempts: int = 1,
) -> ValidatedSQL:
    current_sql = clean_sql(initial_sql)
    raw_response = initial_raw_response
    total_input_tokens = input_tokens
    total_output_tokens = output_tokens
    execution_validation: dict[str, object] | None = None
    repair_attempts = 0

    while True:
        current_sql, diagnostics = postprocess_sql(current_sql, schema_tables)
        needs_repair = _needs_repair(diagnostics)
        execution_validation = None

        if not needs_repair and validate_execution and db_id and credential_path:
            execution_validation = _validate_execution(
                current_sql,
                db_id=db_id,
                credential_path=credential_path,
                timeout=execution_timeout,
            )
            needs_repair = bool(execution_validation.get("error"))

        if not needs_repair or repair_attempts >= max_repair_attempts:
            return ValidatedSQL(
                sql=current_sql,
                raw_response=raw_response,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                diagnostics=diagnostics,
                repair_attempted=repair_attempts > 0,
                repair_attempts=repair_attempts,
                execution_validation=execution_validation,
            )

        repair_prompt = _build_repair_prompt(
            prompt,
            previous_sql=current_sql,
            diagnostics=diagnostics,
            execution_validation=execution_validation,
        )
        repair_response = generate_sql(
            repair_prompt,
            system_instruction=system_instruction,
            settings=settings,
        )
        repair_attempts += 1
        current_sql = clean_sql(repair_response.text)
        raw_response = (
            f"{raw_response}\n\n"
            f"--- SQL REPAIR ATTEMPT {repair_attempts} ---\n\n"
            f"{repair_response.text}"
        )
        total_input_tokens = (total_input_tokens or 0) + (repair_response.input_tokens or 0)
        total_output_tokens = (total_output_tokens or 0) + (repair_response.output_tokens or 0)


def generate_sql_with_repair(
    prompt: str,
    *,
    system_instruction: str,
    settings: config.Settings,
    schema_tables: list[SchemaTable],
    db_id: str | None = None,
    credential_path: str | None = None,
    validate_execution: bool = False,
    execution_timeout: int = 60,
    max_repair_attempts: int = 1,
) -> ValidatedSQL:
    first_response = generate_sql(
        prompt,
        system_instruction=system_instruction,
        settings=settings,
    )
    return validate_and_repair_sql(
        prompt=prompt,
        system_instruction=system_instruction,
        settings=settings,
        schema_tables=schema_tables,
        initial_sql=first_response.text,
        initial_raw_response=first_response.text,
        input_tokens=first_response.input_tokens,
        output_tokens=first_response.output_tokens,
        db_id=db_id,
        credential_path=credential_path,
        validate_execution=validate_execution,
        execution_timeout=execution_timeout,
        max_repair_attempts=max_repair_attempts,
    )
