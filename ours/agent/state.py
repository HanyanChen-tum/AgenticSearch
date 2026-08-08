"""Execution state and FINAL validation for the root DB agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    NONE = "none"
    SUCCESS = "success"
    ERROR = "error"
    EMPTY = "empty"
    ALL_NULL = "all_null"


def normalize_sql(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


# Column compared to a string literal, e.g. `T1.status = 'active'` or `status != 'x'`.
_LITERAL_COMPARISON = re.compile(
    r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*(?:=|!=|<>)\s*'(?:[^'\\]|\\.)*'"
)
# Column IN a list of string literals; `IN (SELECT ...)` is excluded because the
# parenthesis there is followed by a keyword, not a quote.
_LITERAL_IN = re.compile(
    r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s+IN\s*\(\s*'", re.I
)


def _bare_column(name: str) -> str:
    return name.rsplit(".", 1)[-1].strip().casefold()


def find_unverified_literal_columns(sql: str, sampled_columns: set[str]) -> list[str]:
    """Bare column names compared to a string literal that were never passed to
    ``db.sample_values`` in this trace. Matching is by column name only (not
    table-qualified) since the same column name rarely means two different
    encodings within one database, and this is a soft nudge, not a hard check.
    """
    found: dict[str, None] = {}
    for pattern in (_LITERAL_COMPARISON, _LITERAL_IN):
        for match in pattern.finditer(sql or ""):
            column = _bare_column(match.group(1))
            if column and column not in sampled_columns:
                found.setdefault(column, None)
    return list(found)


@dataclass
class ExecutionRecord:
    sql: str
    normalized_sql: str
    status: ExecutionStatus
    result: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "normalized_sql": self.normalized_sql,
            "status": self.status.value,
            "result": self.result,
        }


class AgentExecutionState:
    def __init__(self) -> None:
        self.last_execution: ExecutionRecord | None = None
        self.sampled_columns: set[str] = set()
        self._warned_literal_columns: set[str] = set()

    def record_sample_values(self, column: str) -> None:
        if column:
            self.sampled_columns.add(column.strip().casefold())

    def unverified_literal_warning(self, sql: str) -> str | None:
        """Soft nudge (never blocks) for columns compared to a literal that were
        never checked with db.sample_values in this trace. Fires once per column
        per trace so it doesn't repeat every turn once the model has seen it.
        """
        columns = find_unverified_literal_columns(sql, self.sampled_columns)
        new_columns = [c for c in columns if c not in self._warned_literal_columns]
        if not new_columns:
            return None
        self._warned_literal_columns.update(new_columns)
        listed = ", ".join(sorted(new_columns))
        return (
            f"WARNING: column(s) {listed} are compared to a literal string value, but "
            "db.sample_values was never called on them in this trace. If the literal "
            "doesn't exactly match how the value is actually stored (encoding, casing, "
            "date format), the query will silently return wrong or empty results. "
            "Consider calling db.sample_values on the column before relying on the literal."
        )

    def record(self, sql: str, result: dict[str, Any]) -> ExecutionRecord:
        rows = result.get("rows")
        if result.get("error"):
            status = ExecutionStatus.ERROR
        elif rows == []:
            status = ExecutionStatus.EMPTY
        elif rows and all(all(value is None for value in row) for row in rows):
            status = ExecutionStatus.ALL_NULL
        else:
            status = ExecutionStatus.SUCCESS
        record = ExecutionRecord(
            sql=sql,
            normalized_sql=normalize_sql(sql),
            status=status,
            result=result,
        )
        self.last_execution = record
        return record

    def validate_final(self, sql: str, *, require_verified: bool) -> tuple[bool, str]:
        final_sql = normalize_sql(sql)
        last = self.last_execution
        if not require_verified:
            return True, ""
        if last and last.status in {
            ExecutionStatus.ERROR,
            ExecutionStatus.EMPTY,
        }:
            return False, f"last SQL execution status is {last.status.value}"
        if last is None:
            return False, "FINAL SQL has not been executed"
        if last.status not in {ExecutionStatus.SUCCESS, ExecutionStatus.ALL_NULL}:
            return False, f"last SQL execution status is {last.status.value}"
        if final_sql != last.normalized_sql:
            return False, "FINAL SQL differs from the most recent successful execution"
        return True, ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_execution": (
                self.last_execution.to_dict() if self.last_execution else None
            ),
            "sampled_columns": sorted(self.sampled_columns),
            "warned_literal_columns": sorted(self._warned_literal_columns),
        }
