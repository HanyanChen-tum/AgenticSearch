"""Smoke test for Spider 1.0 experiment setup."""

from __future__ import annotations

import argparse

from spider1_experiments.shared import config
from spider1_experiments.shared.data_loader import load_questions
from spider1_experiments.shared.llm_client import generate_sql
from spider1_experiments.shared.schema_utils import extract_schema_text, get_database_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test Spider 1.0 setup.")
    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--llm", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    examples = load_questions(args.dataset)[: args.limit]
    print(f"Loaded examples: {len(examples)}")
    for example in examples:
        db_path = get_database_path(args.database_dir, example["db_id"])
        schema = extract_schema_text(db_path)
        print(
            f"- {example['id']}: db={example['db_id']}, "
            f"db_exists={db_path.exists()}, schema_chars={len(schema)}"
        )

    if args.llm:
        response = generate_sql("Return this SQL exactly: SELECT 1;")
        print(f"LLM smoke response: {response.text.strip()}")


if __name__ == "__main__":
    main()

