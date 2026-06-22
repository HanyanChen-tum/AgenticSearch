"""Common CLI and execution loop for Spider2-Snow methods."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path
import time
from typing import Any, Callable

from spider2_snow_experiments import config
from spider2_snow_experiments.data import Spider2SnowExample, load_examples
from spider2_snow_experiments import snowflake_backend
from spider2_snow_experiments.result_utils import (
    clean_sql,
    extract_sql_from_text,
    postprocess_sql,
    write_json,
)
from spider2_snow_experiments.schema import load_schema_tables


@dataclass(frozen=True)
class Prediction:
    sql: str
    raw_response: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None
    extra: dict[str, Any] | None = None


PredictFn = Callable[[Spider2SnowExample, config.Settings, argparse.Namespace], Prediction]


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", default=str(config.SPIDER2_SNOW_DATASET))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--instance-id",
        action="append",
        default=None,
        help="Run one instance id. Can be repeated.",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--schema-max-chars", type=int, default=None)
    parser.add_argument("--document-max-chars", type=int, default=None)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute final SQL on Snowflake and store predicted_answer.",
    )
    parser.add_argument("--credential-path", default=None)
    parser.add_argument("--snowflake-timeout", type=int, default=60)
    parser.add_argument(
        "--repair-with-execution",
        action="store_true",
        help="Use Snowflake execution errors to repair generated SQL during generation.",
    )
    parser.add_argument(
        "--repair-max-attempts",
        type=int,
        default=1,
        help="Maximum LLM repair attempts after local or execution validation failures.",
    )


def settings_from_args(args: argparse.Namespace) -> config.Settings:
    settings = config.get_settings()
    updates: dict[str, Any] = {}
    for arg_name, field_name in (
        ("dataset", "dataset_path"),
        ("model", "model"),
        ("llm_provider", "llm_provider"),
        ("llm_base_url", "llm_base_url"),
        ("llm_api_key", "llm_api_key"),
        ("temperature", "temperature"),
        ("max_tokens", "max_tokens"),
        ("schema_max_chars", "schema_max_chars"),
        ("document_max_chars", "document_max_chars"),
        ("credential_path", "credential_path"),
    ):
        value = getattr(args, arg_name, None)
        if value is not None:
            updates[field_name] = Path(value) if field_name.endswith("_path") else value
    return replace(settings, **updates)


def default_output_path(method_name: str, settings: config.Settings) -> Path:
    return settings.results_dir / f"{method_name}.json"


def run_method(
    *,
    method_name: str,
    predict_fn: PredictFn,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    settings = settings_from_args(args)
    output_path = Path(args.output) if args.output else default_output_path(method_name, settings)
    examples = load_examples(
        args.dataset,
        limit=args.limit,
        instance_ids=args.instance_id,
    )
    if not examples:
        raise ValueError("No Spider2-Snow examples selected.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Method: {method_name}")
    print(f"Examples: {len(examples)}")
    print(f"Model: {settings.model}")
    print(f"Dataset: {args.dataset}")
    print(f"Output: {output_path}")
    print(f"Execute final SQL: {args.execute}")

    results: list[dict[str, Any]] = []
    for index, example in enumerate(examples, start=1):
        print(f"[{index}/{len(examples)}] {example.instance_id} ({example.db_id})")
        started_at = time.perf_counter()
        prediction = Prediction(sql="", error="not_run")
        try:
            prediction = predict_fn(example, settings, args)
        except Exception as error:
            prediction = Prediction(sql="", error=str(error))

        predicted_sql = clean_sql(prediction.sql)
        if not predicted_sql and prediction.raw_response:
            predicted_sql = extract_sql_from_text(prediction.raw_response)

        sql_postprocess: dict[str, Any] | None = None
        if predicted_sql:
            try:
                schema_tables = load_schema_tables(example.db_id, settings.databases_dir)
                predicted_sql, sql_postprocess = postprocess_sql(predicted_sql, schema_tables)
            except Exception as error:
                sql_postprocess = {"error": str(error)}

        execution_result: dict[str, Any] | None = None
        if args.execute and predicted_sql and prediction.error is None:
            execution_result = snowflake_backend.execute_sql(
                example.db_id,
                predicted_sql,
                credential_path=settings.credential_path,
                timeout=args.snowflake_timeout,
            )

        result = {
            "instance_id": example.instance_id,
            "method": method_name,
            "db_id": example.db_id,
            "question": example.question,
            "external_knowledge": example.external_knowledge,
            "model": settings.model,
            "predicted_sql": predicted_sql,
            "raw_response": prediction.raw_response,
            "generation_error": prediction.error,
            "latency_seconds": round(time.perf_counter() - started_at, 4),
            "input_tokens": prediction.input_tokens,
            "output_tokens": prediction.output_tokens,
            "executed": bool(args.execute),
            "execution": execution_result,
        }
        if sql_postprocess:
            result["sql_postprocess"] = sql_postprocess
        if prediction.extra:
            result.update(prediction.extra)
        results.append(result)
        write_json(output_path, results)

    print(f"Wrote {len(results)} results to {output_path}")
    return results
