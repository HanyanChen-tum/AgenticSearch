"""Prepare Spider dataset files.

Converts Spider examples into the unified format used by all methods:

{
  "id": "dev_000001",
  "db_id": "concert_singer",
  "question": "...",
  "gold_sql": "..."
}

It also installs Spider SQLite databases under
data/databases/{db_id}/{db_id}.sqlite by symlinking or copying them.
"""

from __future__ import annotations

import argparse
import os
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


DEFAULT_SPIDER_DIR = config.DATA_DIR / "spider_data"
TRAIN_OUTPUT = config.PROCESSED_DATA_DIR / "train_questions.json"
DEV_OUTPUT = config.PROCESSED_DATA_DIR / "dev_questions.json"
DATABASE_MODES = ("symlink", "copy", "skip")


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


def install_spider_databases(
    source_dir: str | Path,
    target_dir: str | Path = config.DATABASE_DIR,
    mode: str = "symlink",
) -> dict[str, int]:
    source = Path(source_dir)
    target = Path(target_dir)
    if mode not in DATABASE_MODES:
        raise ValueError(f"Unsupported database mode: {mode}")
    if mode == "skip":
        return {"linked_databases": 0, "copied_databases": 0, "reused_databases": 0}
    if not source.exists():
        raise FileNotFoundError(f"Spider database directory not found: {source}")

    sqlite_paths = sorted(source.glob("*/*.sqlite"))
    if not sqlite_paths:
        raise FileNotFoundError(f"No SQLite databases found under: {source}")

    counts = {"linked_databases": 0, "copied_databases": 0, "reused_databases": 0}
    target.mkdir(parents=True, exist_ok=True)

    for sqlite_path in sqlite_paths:
        db_id = sqlite_path.parent.name
        output_dir = target / db_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{db_id}.sqlite"

        if output_path.exists():
            counts["reused_databases"] += 1
            continue
        if output_path.is_symlink():
            output_path.unlink()

        if mode == "copy":
            shutil.copy2(sqlite_path, output_path)
            counts["copied_databases"] += 1
        else:
            relative_source = os.path.relpath(sqlite_path.resolve(), output_dir.resolve())
            output_path.symlink_to(relative_source)
            counts["linked_databases"] += 1

    return counts


def prepare_spider(
    spider_dir: str | Path = DEFAULT_SPIDER_DIR,
    train_input: str | Path | None = None,
    dev_input: str | Path | None = None,
    train_output: str | Path = TRAIN_OUTPUT,
    dev_output: str | Path = DEV_OUTPUT,
    database_dir: str | Path = config.DATABASE_DIR,
    database_mode: str = "symlink",
) -> dict[str, int]:
    spider_path = Path(spider_dir)
    train_path = Path(train_input) if train_input else spider_path / "train_spider.json"
    dev_path = Path(dev_input) if dev_input else spider_path / "dev.json"
    source_database_dir = spider_path / "database"

    train_examples = convert_spider_examples(train_path, "train")
    dev_examples = convert_spider_examples(dev_path, "dev")

    write_json(train_output, train_examples)
    write_json(dev_output, dev_examples)

    database_counts = install_spider_databases(
        source_database_dir,
        database_dir,
        mode=database_mode,
    )

    summary = {
        "train_examples": len(train_examples),
        "dev_examples": len(dev_examples),
        **database_counts,
    }
    logger.info("Prepared Spider data: %s", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Spider data for this project.")
    parser.add_argument(
        "--spider-dir",
        default=str(DEFAULT_SPIDER_DIR),
        help="Extracted Spider directory containing train_spider.json, dev.json, and database/.",
    )
    parser.add_argument(
        "--train-input",
        default=None,
        help="Optional train JSON override; defaults to <spider-dir>/train_spider.json.",
    )
    parser.add_argument(
        "--dev-input",
        default=None,
        help="Optional dev JSON override; defaults to <spider-dir>/dev.json.",
    )
    parser.add_argument("--train-output", default=str(TRAIN_OUTPUT))
    parser.add_argument("--dev-output", default=str(DEV_OUTPUT))
    parser.add_argument(
        "--database-dir",
        default=str(config.DATABASE_DIR),
        help="Destination directory used by experiment scripts.",
    )
    parser.add_argument(
        "--database-mode",
        choices=DATABASE_MODES,
        default="symlink",
        help="Symlink databases (default), copy them, or skip database installation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prepare_spider(
        spider_dir=args.spider_dir,
        train_input=args.train_input,
        dev_input=args.dev_input,
        train_output=args.train_output,
        dev_output=args.dev_output,
        database_dir=args.database_dir,
        database_mode=args.database_mode,
    )


if __name__ == "__main__":
    main()
