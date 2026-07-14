"""Shared trace schema, persistence, and run-pair validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


TRACE_SCHEMA_VERSION = 3


def normalize_sql(sql: str) -> str:
    text = re.sub(r"\s+", " ", (sql or "").strip().rstrip(";"))
    text = re.sub(r"\s*([(),=<>+*/])\s*", r"\1", text)
    return text.casefold()


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records = []
    path = Path(path)
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if "id" not in record:
                raise ValueError(f"{path}:{line_number}: missing id")
            records.append(record)
    return records


def by_id(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """De-duplicate reruns by ID, keeping the last record."""
    return {record["id"]: record for record in records}


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        handle.flush()


def write_json(path: str | Path, value: Any) -> None:
    """Atomically replace a JSON artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def extract_final_sql(trace: dict[str, Any]) -> str:
    if "final_sql" in trace:
        return str(trace.get("final_sql") or "")
    for message in reversed(trace.get("messages", [])):
        if message.get("role") != "assistant":
            continue
        content = str(message.get("content", ""))
        match = re.search(r'FINAL\("(?P<sql>[\s\S]*)"\)\s*$', content)
        if match:
            return match.group("sql").replace(r'\"', '"').strip()
    return ""


def validate_run_pair(
    results: Iterable[dict[str, Any]],
    traces: Iterable[dict[str, Any]],
    *,
    allow_legacy: bool = False,
) -> tuple[str | None, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    result_map, trace_map = by_id(results), by_id(traces)
    result_ids, trace_ids = set(result_map), set(trace_map)
    if result_ids != trace_ids:
        missing = sorted(result_ids - trace_ids)
        extra = sorted(trace_ids - result_ids)
        raise ValueError(
            "results/transcripts ID mismatch: "
            f"missing traces={missing[:10]} extra traces={extra[:10]}"
        )

    result_run_ids = {item.get("run_id") for item in result_map.values()}
    trace_run_ids = {item.get("run_id") for item in trace_map.values()}
    if allow_legacy and result_run_ids == {None} and trace_run_ids == {None}:
        run_id = None
    else:
        if None in result_run_ids or None in trace_run_ids:
            raise ValueError("run_id is required in every result and transcript record")
        if len(result_run_ids) != 1 or result_run_ids != trace_run_ids:
            raise ValueError(
                f"run_id mismatch: results={sorted(result_run_ids)} "
                f"transcripts={sorted(trace_run_ids)}"
            )
        run_id = next(iter(result_run_ids))

    mismatches = []
    for item_id, result in result_map.items():
        predicted = str(result.get("predicted_sql") or "")
        traced = extract_final_sql(trace_map[item_id])
        if normalize_sql(predicted) != normalize_sql(traced):
            mismatches.append(item_id)
    if mismatches:
        raise ValueError(
            "results/transcripts final SQL mismatch for IDs: "
            + ", ".join(mismatches[:10])
        )
    return run_id, result_map, trace_map
