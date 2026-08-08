"""Structured Root QueryPlan protocol for the E4-A ablation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any


QUERY_PLAN_SCHEMA_VERSION = 3
QUERY_PLAN_MODE = "root-query-plan-v1"

_INITIAL_PATTERN = re.compile(
    r"```queryplan\s*\n(?P<body>[\s\S]*?)\n```",
    re.IGNORECASE,
)
_REVISION_PATTERN = re.compile(
    r"```plan-revision\s*\n(?P<body>[\s\S]*?)\n```",
    re.IGNORECASE,
)

_REQUIRED_INITIAL_FIELDS = {
    "target_entity",
    "grain",
    "schema_links",
    "joins",
    "filters",
    "group_by",
    "aggregates",
    "having",
    "order_by",
    "limit",
    "answer_type",
    "answer_scope",
    "output_columns",
    "required_tables",
    "aggregation_scope",
    "aggregation_justification",
    "candidate_purpose",
    "expected_result_shape",
    "unresolved_assumptions",
    "revision",
}
_LIST_FIELDS = {
    "schema_links",
    "joins",
    "filters",
    "group_by",
    "aggregates",
    "having",
    "order_by",
    "output_columns",
    "required_tables",
    "unresolved_assumptions",
}


def protocol_manifest() -> dict[str, Any]:
    return {
        "version": QUERY_PLAN_SCHEMA_VERSION,
        "mode": QUERY_PLAN_MODE,
        "initial_block": "queryplan",
        "revision_block": "plan-revision",
        "required_initial_fields": sorted(_REQUIRED_INITIAL_FIELDS),
        "revision_fields": [
            "observation_ref",
            "changed_constraints",
            "updated_fields",
            "reason",
            "candidate_purpose",
        ],
        "separate_planner_call": False,
        "adherence_mode": "record-only",
        "python_block_policy": "execute-all-dedupe-consecutive",
        "observation_delivery": "structured-authoritative",
        "observation_ref_policy": "integer-or-numeric-string",
    }


def _parse_block(response: str, pattern: re.Pattern[str]) -> tuple[dict[str, Any] | None, list[str]]:
    match = pattern.search(response or "")
    if match is None:
        return None, ["required fenced JSON block is missing"]
    try:
        value = json.loads(match.group("body"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"]
    if not isinstance(value, dict):
        return None, ["block must contain one JSON object"]
    return value, []


def parse_initial_plan(response: str) -> tuple[dict[str, Any] | None, list[str]]:
    plan, errors = _parse_block(response, _INITIAL_PATTERN)
    if plan is None:
        return None, errors
    missing = sorted(_REQUIRED_INITIAL_FIELDS - set(plan))
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    for field_name in sorted(_LIST_FIELDS):
        if field_name in plan and not isinstance(plan[field_name], list):
            errors.append(f"{field_name} must be a list")
    if plan.get("answer_type") not in {"rows", "scalar", "boolean"}:
        errors.append("answer_type must be rows, scalar, or boolean")
    answer_scope = plan.get("answer_scope")
    allowed_scopes = {
        "per_entity_rows",
        "single_entity_row",
        "global_scalar",
        "boolean",
    }
    if answer_scope not in allowed_scopes:
        errors.append(
            "answer_scope must be per_entity_rows, single_entity_row, "
            "global_scalar, or boolean"
        )
    expected_scope_types = {
        "per_entity_rows": "rows",
        "single_entity_row": "rows",
        "global_scalar": "scalar",
        "boolean": "boolean",
    }
    if answer_scope in expected_scope_types and plan.get("answer_type") != expected_scope_types[answer_scope]:
        errors.append("answer_scope is inconsistent with answer_type")
    if plan.get("candidate_purpose") not in {"explore", "answer"}:
        errors.append("candidate_purpose must be explore or answer")

    limit = plan.get("limit")
    if limit is not None and (
        not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
    ):
        errors.append("limit must be null or a positive integer")

    required_tables = plan.get("required_tables")
    if isinstance(required_tables, list):
        if not required_tables:
            errors.append("required_tables must contain at least one table")
        elif any(not isinstance(value, str) or not value.strip() for value in required_tables):
            errors.append("required_tables entries must be non-empty strings")
        elif len({value.casefold() for value in required_tables}) != len(required_tables):
            errors.append("required_tables must not contain duplicates")

    output_columns = plan.get("output_columns")
    if isinstance(output_columns, list):
        required_output_fields = {
            "position",
            "semantic_item",
            "source_columns",
            "sql_expression",
            "source_justification",
            "aggregation",
        }
        positions: list[int] = []
        required_table_names = {
            value.casefold()
            for value in (required_tables or [])
            if isinstance(value, str)
        }
        for index, output in enumerate(output_columns, start=1):
            if not isinstance(output, dict):
                errors.append(f"output_columns[{index - 1}] must be an object")
                continue
            missing_output = sorted(required_output_fields - set(output))
            if missing_output:
                errors.append(
                    f"output_columns[{index - 1}] missing fields: "
                    + ", ".join(missing_output)
                )
            position = output.get("position")
            if not isinstance(position, int) or isinstance(position, bool) or position < 1:
                errors.append(f"output_columns[{index - 1}].position must be a positive integer")
            else:
                positions.append(position)
            for field_name in (
                "semantic_item",
                "sql_expression",
                "source_justification",
                "aggregation",
            ):
                if not isinstance(output.get(field_name), str) or not output.get(field_name, "").strip():
                    errors.append(
                        f"output_columns[{index - 1}].{field_name} must be a non-empty string"
                    )
            sources = output.get("source_columns")
            if not isinstance(sources, list) or any(
                not isinstance(value, str) or not value.strip() for value in (sources or [])
            ):
                errors.append(
                    f"output_columns[{index - 1}].source_columns must be a list of non-empty strings"
                )
            elif required_table_names:
                for source in sources:
                    if "." not in source:
                        errors.append(
                            f"output_columns[{index - 1}].source_columns entries must be fully qualified"
                        )
                        continue
                    table_name = source.split(".", 1)[0].strip('`"[]').casefold()
                    if table_name not in required_table_names:
                        errors.append(
                            f"output source table {table_name!r} is absent from required_tables"
                        )
        if positions and positions != list(range(1, len(output_columns) + 1)):
            errors.append("output_columns.position must be consecutive and match output order")

    aggregation_scope = plan.get("aggregation_scope")
    if aggregation_scope not in {"none", "per_entity", "global"}:
        errors.append("aggregation_scope must be none, per_entity, or global")
    aggregates = plan.get("aggregates")
    if isinstance(aggregates, list):
        if aggregates and aggregation_scope == "none":
            errors.append("aggregation_scope cannot be none when aggregates is non-empty")
        if not aggregates and aggregation_scope in {"per_entity", "global"}:
            errors.append("aggregates must be non-empty when aggregation_scope uses aggregation")
    aggregation_justification = plan.get("aggregation_justification")
    if aggregation_scope == "none":
        if aggregation_justification is not None and aggregation_justification != "":
            errors.append("aggregation_justification must be null when aggregation_scope is none")
    elif not isinstance(aggregation_justification, str) or not aggregation_justification.strip():
        errors.append("aggregation_justification must explain why the question requires aggregation")
    shape = plan.get("expected_result_shape")
    if not isinstance(shape, dict):
        errors.append("expected_result_shape must be an object")
    else:
        if shape.get("answer_type") not in {"rows", "scalar", "boolean"}:
            errors.append("expected_result_shape.answer_type must be rows, scalar, or boolean")
        elif shape.get("answer_type") != plan.get("answer_type"):
            errors.append("expected_result_shape.answer_type must equal answer_type")
        count = shape.get("column_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            errors.append("expected_result_shape.column_count must be a positive integer")
        elif isinstance(output_columns, list) and count != len(output_columns):
            errors.append("expected_result_shape.column_count must equal len(output_columns)")
        if not isinstance(shape.get("row_grain"), str) or not shape.get("row_grain", "").strip():
            errors.append("expected_result_shape.row_grain must be a non-empty string")
    if plan.get("revision") is not None:
        errors.append("initial revision must be null")
    return (plan if not errors else None), errors


def parse_revision(
    response: str,
    *,
    latest_observation_ref: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    revision, errors = _parse_block(response, _REVISION_PATTERN)
    if revision is None:
        return None, errors
    required = {
        "observation_ref",
        "changed_constraints",
        "updated_fields",
        "reason",
        "candidate_purpose",
    }
    missing = sorted(required - set(revision))
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    observation_ref = revision.get("observation_ref")
    if isinstance(observation_ref, str) and observation_ref.strip().isdigit():
        observation_ref = int(observation_ref.strip())
        revision["observation_ref"] = observation_ref
    if observation_ref != latest_observation_ref:
        errors.append(
            "observation_ref must equal the latest structured observation "
            f"sequence ({latest_observation_ref})"
        )
    if not isinstance(revision.get("changed_constraints"), list):
        errors.append("changed_constraints must be a list")
    if not isinstance(revision.get("updated_fields"), dict):
        errors.append("updated_fields must be an object")
    elif isinstance(revision.get("changed_constraints"), list):
        changed = set(revision["changed_constraints"])
        updated = set(revision["updated_fields"])
        if changed != updated:
            errors.append("changed_constraints must list exactly the updated_fields keys")
        unknown = sorted(updated - _REQUIRED_INITIAL_FIELDS)
        if unknown:
            errors.append(f"updated_fields contains unknown plan fields: {', '.join(unknown)}")
    if not isinstance(revision.get("reason"), str) or not revision.get("reason", "").strip():
        errors.append("reason must be a non-empty string")
    if revision.get("candidate_purpose") not in {"explore", "answer"}:
        errors.append("candidate_purpose must be explore or answer")
    return (revision if not errors else None), errors


def strip_plan_blocks(response: str) -> str:
    response = _INITIAL_PATTERN.sub("", response or "")
    return _REVISION_PATTERN.sub("", response).strip()


def _outer_projection_count(sql: str) -> int | None:
    text, depth, quote, select_end = sql or "", 0, None, None
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"', "`"):
            quote = char
        elif char == "[":
            quote = "]"
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and (char.isalpha() or char == "_"):
            end = index + 1
            while end < len(text) and (text[end].isalnum() or text[end] == "_"):
                end += 1
            word = text[index:end].casefold()
            if word == "select":
                select_end = end
            elif word == "from" and select_end is not None:
                clause, local_depth, local_quote, count = text[select_end:index], 0, None, 1
                for item in clause:
                    if local_quote:
                        if item == local_quote:
                            local_quote = None
                    elif item in ("'", '"', "`"):
                        local_quote = item
                    elif item == "[":
                        local_quote = "]"
                    elif item == "(":
                        local_depth += 1
                    elif item == ")":
                        local_depth = max(0, local_depth - 1)
                    elif item == "," and local_depth == 0:
                        count += 1
                return count
            index = end - 1
        index += 1
    return None


def plan_sql_adherence(plan: dict[str, Any], sql: str) -> dict[str, Any]:
    """Record deterministic, conservative checks; never block execution."""
    expected_shape = plan.get("expected_result_shape") or {}
    expected_columns = expected_shape.get("column_count")
    actual_columns = _outer_projection_count(sql)
    required_tables = [
        value for value in (plan.get("required_tables") or [])
        if isinstance(value, str) and value.strip()
    ]
    checks: dict[str, bool | None] = {
        "projection_count": (
            actual_columns == expected_columns
            if isinstance(actual_columns, int) and isinstance(expected_columns, int)
            else None
        ),
        "group_by_presence": bool(re.search(r"\bgroup\s+by\b", sql, re.I)) == bool(plan.get("group_by")),
        "having_presence": bool(re.search(r"\bhaving\b", sql, re.I)) == bool(plan.get("having")),
        "order_by_presence": bool(re.search(r"\border\s+by\b", sql, re.I)) == bool(plan.get("order_by")),
        "limit_presence": bool(re.search(r"\blimit\b", sql, re.I)) == (plan.get("limit") is not None),
        "required_tables_presence": all(
            re.search(
                rf"\b(?:from|join)\s+[`\"\[]?{re.escape(table)}(?:[`\"\]]|\b)",
                sql,
                re.I,
            )
            is not None
            for table in required_tables
        ),
    }
    known = [value for value in checks.values() if value is not None]
    return {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "checks": checks,
        "passed": all(known) if known else None,
        "expected_projection_count": expected_columns,
        "actual_projection_count": actual_columns,
        "enforced": False,
    }


@dataclass
class QueryPlanState:
    initial: dict[str, Any] | None = None
    revisions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def current_candidate_purpose(self) -> str | None:
        if self.revisions:
            return self.revisions[-1].get("candidate_purpose")
        if self.initial:
            return self.initial.get("candidate_purpose")
        return None

    @property
    def current_plan(self) -> dict[str, Any] | None:
        if self.initial is None:
            return None
        current = dict(self.initial)
        for revision in self.revisions:
            current.update(revision.get("updated_fields") or {})
            current["candidate_purpose"] = revision.get(
                "candidate_purpose", current.get("candidate_purpose")
            )
            current["revision"] = {
                key: revision.get(key)
                for key in ("observation_ref", "changed_constraints", "reason")
            }
        return current

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUERY_PLAN_SCHEMA_VERSION,
            "initial": self.initial,
            "revisions": list(self.revisions),
            "current_plan": self.current_plan,
            "current_candidate_purpose": self.current_candidate_purpose,
        }
