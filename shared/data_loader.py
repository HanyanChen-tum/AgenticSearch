"""Dataset loading utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.io_utils import read_json


REQUIRED_FIELDS = ("id", "db_id", "question", "gold_sql")


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of questions in {path}")

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Question at index {index} is not an object")

        missing = [field for field in REQUIRED_FIELDS if field not in item]
        if missing:
            raise ValueError(
                f"Question at index {index} is missing fields: {', '.join(missing)}"
            )

    return data
