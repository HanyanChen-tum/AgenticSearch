"""Spider2-Snow JSONL data loading."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from spider2_snow_experiments import config


@dataclass(frozen=True)
class Spider2SnowExample:
    instance_id: str
    db_id: str
    question: str
    external_knowledge: str | None
    raw: dict


def load_examples(
    dataset_path: str | Path = config.SPIDER2_SNOW_DATASET,
    *,
    limit: int | None = None,
    instance_ids: Iterable[str] | None = None,
) -> list[Spider2SnowExample]:
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Spider2-Snow dataset not found: {path}")

    selected_ids = set(instance_ids or [])
    examples: list[Spider2SnowExample] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            missing = [
                field
                for field in ("instance_id", "instruction", "db_id")
                if field not in item
            ]
            if missing:
                raise ValueError(
                    f"{path}:{line_number} is missing fields: {', '.join(missing)}"
                )
            if selected_ids and item["instance_id"] not in selected_ids:
                continue
            examples.append(
                Spider2SnowExample(
                    instance_id=item["instance_id"],
                    db_id=item["db_id"],
                    question=item["instruction"],
                    external_knowledge=item.get("external_knowledge"),
                    raw=item,
                )
            )
            if limit is not None and len(examples) >= limit:
                break

    return examples

