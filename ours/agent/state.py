"""Execution state and FINAL validation for the root DB agent."""

from __future__ import annotations

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
            )
        }
