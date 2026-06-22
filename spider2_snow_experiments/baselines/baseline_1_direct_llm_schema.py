"""Baseline 1: direct LLM with local Spider2-Snow schema context."""

from __future__ import annotations

import argparse
from pathlib import Path

from spider2_snow_experiments import config
from spider2_snow_experiments.data import Spider2SnowExample
from spider2_snow_experiments.runner import Prediction, add_common_args, run_method
from spider2_snow_experiments.schema import build_example_context
from spider2_snow_experiments.sql_generation import generate_sql_with_repair


METHOD_NAME = "baseline_1_direct_llm_schema"
SYSTEM_INSTRUCTION = (
    "You are an expert Text-to-SQL assistant for Spider2-Snow. "
    "Return only executable Snowflake SQL. Do not explain. "
    "Use only tables and columns that appear in the provided DDL. "
    "Always use fully-qualified table names exactly as listed in the schema context. "
    "Never output placeholders such as YOUR_TABLE_NAME or COLUMN_NAME."
)
PROMPT_PATH = config.PROMPTS_DIR / "baseline_1_direct_llm_schema.txt"


def build_prompt(example: Spider2SnowExample, schema_text: str, document_text: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        instance_id=example.instance_id,
        db_id=example.db_id,
        question=example.question,
        external_knowledge=document_text or "[None]",
        schema=schema_text,
    )


def predict(example: Spider2SnowExample, settings: config.Settings, args: argparse.Namespace) -> Prediction:
    context = build_example_context(
        example,
        databases_dir=settings.databases_dir,
        documents_dir=settings.documents_dir,
        max_schema_chars=settings.schema_max_chars,
        max_document_chars=settings.document_max_chars,
    )
    prompt = build_prompt(example, context.schema_text, context.document_text)
    response = generate_sql_with_repair(
        prompt,
        system_instruction=SYSTEM_INSTRUCTION,
        settings=settings,
        schema_tables=context.schema_tables,
        db_id=example.db_id,
        credential_path=str(settings.credential_path),
        validate_execution=args.repair_with_execution,
        execution_timeout=args.snowflake_timeout,
        max_repair_attempts=args.repair_max_attempts,
    )
    return Prediction(
        sql=response.sql,
        raw_response=response.raw_response,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        extra={
            "schema_tables": len(context.schema_tables),
            "schema_chars": len(context.schema_text),
            "document_chars": len(context.document_text),
            "sql_validation": response.diagnostics,
            "repair_attempted": response.repair_attempted,
            "repair_attempts": response.repair_attempts,
            "execution_validation": response.execution_validation,
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Spider2-Snow baseline 1.")
    add_common_args(parser)
    return parser.parse_args()


def main() -> None:
    run_method(method_name=METHOD_NAME, predict_fn=predict, args=parse_args())


if __name__ == "__main__":
    main()
