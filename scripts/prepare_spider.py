"""Prepare Spider dataset files.

Converts Spider examples into the unified format used by all methods:

{
  "id": "dev_000001",
  "db_id": "concert_singer",
  "question": "...",
  "gold_sql": "..."
}

It can also copy Spider SQLite databases from data/raw/spider/database into
data/databases/{db_id}/{db_id}.sqlite.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared import config
from shared.io_utils import read_json, write_json
from shared.logging_utils import setup_logger


RAW_SPIDER_DIR = config.DATA_DIR / "raw" / "spider"
RAW_DATABASE_DIR = RAW_SPIDER_DIR / "database"
TRAIN_INPUT = RAW_SPIDER_DIR / "train_spider.json"
DEV_INPUT = RAW_SPIDER_DIR / "dev.json"
TRAIN_OUTPUT = config.PROCESSED_DATA_DIR / "train_questions.json"
DEV_OUTPUT = config.PROCESSED_DATA_DIR / "dev_questions.json"


logger = setup_logger("prepare_spider")


def convert_spider_examples(path: str | Path, split: str) -> list[dict[str, Any]]:
    examples = read_json(path)
    if not isinstance(examples, list):
        raise ValueError(f"Expected Spider file to contain a list: {path}")

    converted = []
    for index, item in enumerate(examples):
        if not isinstance(item, dict):
            raise ValueError(f"Spider example at index {index} is not an object")

        missing = [field for field in ("db_id", "question", "query") if field not in item]
        if missing:
            raise ValueError(
                f"Spider example at index {index} is missing fields: {', '.join(missing)}"
            )

        converted.append(
            {
                "id": f"{split}_{index:06d}",
                "db_id": item["db_id"],
                "question": item["question"],
                "gold_sql": item["query"],
            }
        )

    return converted


def copy_spider_databases(
    source_dir: str | Path = RAW_DATABASE_DIR,
    target_dir: str | Path = config.DATABASE_DIR,
) -> int:
    source = Path(source_dir)
    target = Path(target_dir)
    if not source.exists():
        raise FileNotFoundError(f"Spider database directory not found: {source}")

    copied = 0
    for sqlite_path in source.glob("*/*.sqlite"):
        db_id = sqlite_path.stem
        output_dir = target / db_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{db_id}.sqlite"
        shutil.copy2(sqlite_path, output_path)
        copied += 1

    return copied


def prepare_spider(
    train_input: str | Path = TRAIN_INPUT,
    dev_input: str | Path = DEV_INPUT,
    train_output: str | Path = TRAIN_OUTPUT,
    dev_output: str | Path = DEV_OUTPUT,
    copy_databases: bool = True,
) -> dict[str, int]:
    train_examples = convert_spider_examples(train_input, "train")
    dev_examples = convert_spider_examples(dev_input, "dev")

    write_json(train_output, train_examples)
    write_json(dev_output, dev_examples)

    copied_databases = copy_spider_databases() if copy_databases else 0

    summary = {
        "train_examples": len(train_examples),
        "dev_examples": len(dev_examples),
        "copied_databases": copied_databases,
    }
    logger.info("Prepared Spider data: %s", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Spider data for this project.")
    parser.add_argument("--train-input", default=str(TRAIN_INPUT))
    parser.add_argument("--dev-input", default=str(DEV_INPUT))
    parser.add_argument("--train-output", default=str(TRAIN_OUTPUT))
    parser.add_argument("--dev-output", default=str(DEV_OUTPUT))
    parser.add_argument(
        "--no-copy-databases",
        action="store_true",
        help="Only convert JSON examples; do not copy Spider SQLite databases.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prepare_spider(
        train_input=args.train_input,
        dev_input=args.dev_input,
        train_output=args.train_output,
        dev_output=args.dev_output,
        copy_databases=not args.no_copy_databases,
    )


if __name__ == "__main__":
    main()
