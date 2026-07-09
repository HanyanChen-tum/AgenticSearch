"""Prepare BIRD Mini-Dev files for this project.

Converts BIRD Mini-Dev SQLite examples into the unified project format:

{
  "id": "bird_mini_dev_000001",
  "db_id": "...",
  "question": "...",
  "gold_sql": "..."
}

It also installs the SQLite databases under
data/databases/{db_id}/{db_id}.sqlite by symlinking or copying them.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared import config
from shared.io_utils import write_json
from shared.logging_utils import setup_logger


DEFAULT_BIRD_ARCHIVE = config.DATA_DIR / "raw" / "bird" / "minidev_0703.zip"
DEFAULT_EXTRACT_DIR = config.DATA_DIR / "raw" / "bird" / "minidev_0703"
DEFAULT_OUTPUT = config.PROCESSED_DATA_DIR / "bird_mini_dev_questions.json"
DATABASE_MODES = ("symlink", "copy", "skip")


logger = setup_logger("prepare_bird")


def ensure_extracted(archive_path: str | Path, extract_dir: str | Path) -> Path:
    archive = Path(archive_path)
    target = Path(extract_dir)
    marker = target / "minidev" / "MINIDEV" / "mini_dev_sqlite.json"
    if marker.exists():
        return target
    if not archive.exists():
        raise FileNotFoundError(f"BIRD archive not found: {archive}")

    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target)
    return target


def find_minidev_root(extract_dir: str | Path) -> Path:
    base = Path(extract_dir)
    candidates = [
        base / "minidev" / "MINIDEV",
        base / "MINIDEV",
    ]
    for candidate in candidates:
        if (candidate / "mini_dev_sqlite.json").exists():
            return candidate
    raise FileNotFoundError(f"Could not locate MINIDEV root under {base}")


def format_question(question: str, evidence: str | None, include_evidence: bool) -> str:
    if not include_evidence or not evidence or not evidence.strip():
        return question
    return f"{question}\n\nEvidence: {evidence.strip()}"


def convert_bird_examples(
    json_path: str | Path,
    split: str = "bird_mini_dev",
    include_evidence: bool = True,
) -> list[dict[str, Any]]:
    examples = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if not isinstance(examples, list):
        raise ValueError(f"Expected a list of examples in {json_path}")

    converted = []
    for index, item in enumerate(examples):
        if not isinstance(item, dict):
            raise ValueError(f"Example at index {index} is not an object")

        missing = [field for field in ("question_id", "db_id", "question", "SQL") if field not in item]
        if missing:
            raise ValueError(
                f"Example at index {index} is missing fields: {', '.join(missing)}"
            )

        evidence = item.get("evidence")
        converted.append(
            {
                "id": f"{split}_{index:06d}",
                "bird_question_id": item["question_id"],
                "db_id": item["db_id"],
                "question": format_question(item["question"], evidence, include_evidence),
                "raw_question": item["question"],
                "evidence": evidence,
                "difficulty": item.get("difficulty"),
                "gold_sql": item["SQL"],
            }
        )

    return converted


def install_bird_databases(
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
        raise FileNotFoundError(f"BIRD database directory not found: {source}")

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


def prepare_bird(
    archive_path: str | Path = DEFAULT_BIRD_ARCHIVE,
    extract_dir: str | Path = DEFAULT_EXTRACT_DIR,
    output_path: str | Path = DEFAULT_OUTPUT,
    database_dir: str | Path = config.DATABASE_DIR,
    database_mode: str = "symlink",
    include_evidence: bool = True,
) -> dict[str, int]:
    extracted = ensure_extracted(archive_path, extract_dir)
    root = find_minidev_root(extracted)

    examples = convert_bird_examples(
        root / "mini_dev_sqlite.json",
        include_evidence=include_evidence,
    )
    write_json(output_path, examples)

    database_counts = install_bird_databases(
        root / "dev_databases",
        database_dir,
        mode=database_mode,
    )

    summary = {"examples": len(examples), **database_counts}
    logger.info("Prepared BIRD Mini-Dev data: %s", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare BIRD Mini-Dev data for this project.")
    parser.add_argument("--archive", default=str(DEFAULT_BIRD_ARCHIVE))
    parser.add_argument("--extract-dir", default=str(DEFAULT_EXTRACT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument(
        "--database-mode",
        choices=DATABASE_MODES,
        default="symlink",
        help="Symlink databases (default), copy them, or skip database installation.",
    )
    parser.add_argument(
        "--exclude-evidence",
        action="store_true",
        help="Keep the original question text without appending BIRD evidence.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prepare_bird(
        archive_path=args.archive,
        extract_dir=args.extract_dir,
        output_path=args.output,
        database_dir=args.database_dir,
        database_mode=args.database_mode,
        include_evidence=not args.exclude_evidence,
    )


if __name__ == "__main__":
    main()
