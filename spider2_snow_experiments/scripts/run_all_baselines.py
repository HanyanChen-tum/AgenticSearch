"""Run all Spider2-Snow baselines sequentially."""

from __future__ import annotations

import argparse
from pathlib import Path

from spider2_snow_experiments import config
from spider2_snow_experiments.baselines import (
    baseline_1_direct_llm_schema,
    baseline_2_retrieved_schema,
    baseline_3_non_recursive_db_agent,
)
from spider2_snow_experiments.runner import run_method


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all Spider2-Snow baselines.")
    parser.add_argument("--dataset", default=str(config.SPIDER2_SNOW_DATASET))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--instance-id", action="append", default=None)
    parser.add_argument("--results-dir", default=str(config.RESULTS_DIR))
    parser.add_argument("--model", default=None)
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--schema-max-chars", type=int, default=None)
    parser.add_argument("--document-max-chars", type=int, default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--credential-path", default=None)
    parser.add_argument("--snowflake-timeout", type=int, default=60)
    parser.add_argument("--repair-with-execution", action="store_true")
    parser.add_argument("--repair-max-attempts", type=int, default=1)
    parser.add_argument("--top-k-tables", type=int, default=12)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--initial-top-k-tables", type=int, default=25)
    parser.add_argument("--allow-live-tools", action="store_true")
    return parser.parse_args()


def _args_for_method(args: argparse.Namespace, method_name: str) -> argparse.Namespace:
    method_args = argparse.Namespace(**vars(args))
    method_args.output = str(Path(args.results_dir) / f"{method_name}.json")
    return method_args


def main() -> None:
    args = parse_args()
    runs = [
        (
            baseline_1_direct_llm_schema.METHOD_NAME,
            baseline_1_direct_llm_schema.predict,
        ),
        (
            baseline_2_retrieved_schema.METHOD_NAME,
            baseline_2_retrieved_schema.predict,
        ),
        (
            baseline_3_non_recursive_db_agent.METHOD_NAME,
            baseline_3_non_recursive_db_agent.predict,
        ),
    ]
    for method_name, predict_fn in runs:
        print(f"\n=== {method_name} ===")
        run_method(
            method_name=method_name,
            predict_fn=predict_fn,
            args=_args_for_method(args, method_name),
        )


if __name__ == "__main__":
    main()
