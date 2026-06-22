"""Shared result and SQL formatting helpers."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from spider2_snow_experiments.schema import SchemaTable


SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
SQL_LIKE_RE = re.compile(r"^\s*(?:with|select|insert|update|delete|merge|create)\b", re.IGNORECASE)
JSON_SQL_FIELD_RE = re.compile(r'"sql"\s*:', re.IGNORECASE)
PLACEHOLDER_RE = re.compile(
    r"\b(?:your|placeholder|sample|example)_(?:table|column|database|schema|name)\b"
    r"|<[^>]+>"
    r"|\bTODO\b",
    re.IGNORECASE,
)
TABLE_REF_RE = re.compile(
    r"\b(?P<keyword>FROM|JOIN|UPDATE|INTO|MERGE\s+INTO|DELETE\s+FROM)\s+"
    r"(?P<ref>(?:\"[^\"]+\"|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:\"[^\"]+\"|[A-Za-z_][\w$]*)){0,2})",
    re.IGNORECASE,
)
TABLE_ALIAS_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+"
    r"(?P<ref>(?:\"[^\"]+\"|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:\"[^\"]+\"|[A-Za-z_][\w$]*)){0,2})"
    r"(?:\s+(?:AS\s+)?(?P<alias>[A-Za-z_][\w$]*))?",
    re.IGNORECASE,
)
QUALIFIED_COLUMN_RE = re.compile(
    r"\b(?P<alias>[A-Za-z_][\w$]*)\s*\.\s*(?:\"(?P<quoted>[^\"]+)\"|(?P<plain>[A-Za-z_][\w$]*))"
)
VARIANT_DOT_PATH_RE = re.compile(
    r'(?P<column>"[^"]+"|[A-Za-z_][\w$]*)\s*\.\s*(?P<field>"[^"]+"|[A-Za-z_][\w$]*)'
)
CTE_RE = re.compile(
    r"(?:\bWITH|,)\s+(?P<name>\"[^\"]+\"|[A-Za-z_][\w$]*)\s+AS\s*\(",
    re.IGNORECASE,
)
IGNORED_TABLE_REFS = {
    "FLATTEN",
    "GENERATOR",
    "LATERAL",
    "RESULT_SCAN",
    "TABLE",
    "UNNEST",
    "VALUES",
}
NON_ALIAS_TOKENS = {
    "FULL",
    "GROUP",
    "INNER",
    "JOIN",
    "LEFT",
    "LIMIT",
    "ON",
    "ORDER",
    "QUALIFY",
    "RIGHT",
    "UNION",
    "USING",
    "WHERE",
}
IDENTIFIER_RE = re.compile(r'(?<!["\w$])([A-Za-z_][\w$]*)(?!["\w$])')
STRING_LITERAL_RE = re.compile(r"('(?:''|[^'])*')")


def clean_sql(text: str) -> str:
    sql = (text or "").strip()
    match = SQL_FENCE_RE.search(sql)
    if match:
        sql = match.group(1).strip()
    return sql.strip()


def _strip_identifier_quotes(value: str) -> str:
    parts = [part.strip() for part in value.split(".")]
    return ".".join(part[1:-1] if part.startswith('"') and part.endswith('"') else part for part in parts)


def _normalise_ref(value: str) -> str:
    return re.sub(r"\s+", "", _strip_identifier_quotes(value)).upper()


def _extract_json_sql_field(text: str) -> str:
    match = JSON_SQL_FIELD_RE.search(text)
    if not match:
        return ""
    index = match.end()
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != '"':
        return ""
    index += 1
    chars: list[str] = []
    escaped = False
    closed = False
    while index < len(text):
        char = text[index]
        if escaped:
            chars.append(
                {
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                    '"': '"',
                    "\\": "\\",
                }.get(char, char)
            )
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            tail = text[index + 1 :].lstrip()
            if tail.startswith(("}", ",", "```")) or not tail:
                closed = True
                break
            chars.append(char)
        else:
            chars.append(char)
        index += 1
    return "".join(chars).strip() if closed else ""


def extract_sql_from_text(text: str) -> str:
    cleaned = clean_sql(text)
    if SQL_LIKE_RE.search(cleaned):
        return cleaned

    candidate = (text or "").strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            sql = str(parsed.get("sql") or "").strip()
            if sql:
                return clean_sql(sql)
    except json.JSONDecodeError:
        pass

    sql = _extract_json_sql_field(candidate)
    if sql:
        return clean_sql(sql)
    return cleaned if SQL_LIKE_RE.search(cleaned) else ""


def _build_table_maps(
    tables: list[SchemaTable],
) -> tuple[dict[str, str], dict[str, str], dict[str, SchemaTable]]:
    qualified_map: dict[str, str] = {}
    table_by_ref: dict[str, SchemaTable] = {}
    bare_candidates: dict[str, set[str]] = {}
    for table in tables:
        for reference_name in table.reference_names:
            normalised = _normalise_ref(reference_name)
            qualified_map[normalised] = table.full_name
            table_by_ref[normalised] = table
        bare_candidates.setdefault(_normalise_ref(table.short_name), set()).add(table.full_name)
    bare_map = {
        bare_name: next(iter(full_names))
        for bare_name, full_names in bare_candidates.items()
        if len(full_names) == 1
    }
    return qualified_map, bare_map, table_by_ref


def _build_mixed_case_column_map(tables: list[SchemaTable]) -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    for table in tables:
        for column in table.mixed_case_columns:
            candidates.setdefault(column.upper(), set()).add(column)
    return {
        normalised: next(iter(exact_names))
        for normalised, exact_names in candidates.items()
        if len(exact_names) == 1
    }


def _build_variant_column_map(tables: list[SchemaTable]) -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    for table in tables:
        for column in table.variant_columns:
            candidates.setdefault(column.upper(), set()).add(column)
    return {
        normalised: next(iter(exact_names))
        for normalised, exact_names in candidates.items()
        if len(exact_names) == 1
    }


def _quote_mixed_case_columns(sql: str, column_map: dict[str, str]) -> tuple[str, int]:
    if not column_map:
        return sql, 0
    replacements = 0

    def replace_segment(segment: str) -> str:
        nonlocal replacements

        def replace_identifier(match: re.Match[str]) -> str:
            nonlocal replacements
            identifier = match.group(1)
            exact = column_map.get(identifier.upper())
            if exact is None:
                return identifier
            replacements += 1
            return f'"{exact}"'

        return IDENTIFIER_RE.sub(replace_identifier, segment)

    parts = STRING_LITERAL_RE.split(sql)
    for index in range(0, len(parts), 2):
        parts[index] = replace_segment(parts[index])
    return "".join(parts), replacements


def _rewrite_variant_dot_paths(sql: str, variant_column_map: dict[str, str]) -> tuple[str, int]:
    if not variant_column_map:
        return sql, 0
    replacements = 0

    def strip_quotes(value: str) -> str:
        return value[1:-1] if value.startswith('"') and value.endswith('"') else value

    def replace_segment(segment: str) -> str:
        nonlocal replacements

        def replace_path(match: re.Match[str]) -> str:
            nonlocal replacements
            column = strip_quotes(match.group("column"))
            exact_column = variant_column_map.get(column.upper())
            if exact_column is None:
                return match.group(0)
            field = strip_quotes(match.group("field"))
            replacements += 1
            return f'"{exact_column}":{field}'

        return VARIANT_DOT_PATH_RE.sub(replace_path, segment)

    parts = STRING_LITERAL_RE.split(sql)
    for index in range(0, len(parts), 2):
        parts[index] = replace_segment(parts[index])
    return "".join(parts), replacements


def _resolve_table_ref(
    ref_text: str,
    *,
    qualified_map: dict[str, str],
    bare_map: dict[str, str],
    table_by_ref: dict[str, SchemaTable],
) -> SchemaTable | None:
    normalised = _normalise_ref(ref_text)
    table = table_by_ref.get(normalised)
    if table is not None:
        return table
    full_name = bare_map.get(normalised)
    if full_name is None:
        full_name = qualified_map.get(normalised)
    return table_by_ref.get(_normalise_ref(full_name)) if full_name else None


def _find_unknown_column_refs(
    sql: str,
    *,
    qualified_map: dict[str, str],
    bare_map: dict[str, str],
    table_by_ref: dict[str, SchemaTable],
) -> list[str]:
    alias_to_table: dict[str, SchemaTable] = {}
    for match in TABLE_ALIAS_RE.finditer(sql):
        table = _resolve_table_ref(
            match.group("ref"),
            qualified_map=qualified_map,
            bare_map=bare_map,
            table_by_ref=table_by_ref,
        )
        if table is None:
            continue
        alias = match.group("alias")
        if alias and alias.upper() not in NON_ALIAS_TOKENS:
            alias_to_table[alias.upper()] = table
        alias_to_table[table.short_name.upper()] = table

    unknown_refs: list[str] = []
    for match in QUALIFIED_COLUMN_RE.finditer(sql):
        alias = match.group("alias").upper()
        table = alias_to_table.get(alias)
        if table is None:
            continue
        column = match.group("quoted") or match.group("plain") or ""
        known_columns = {known_column.upper() for known_column in table.columns}
        if column.upper() not in known_columns:
            ref = f"{match.group('alias')}.{column}"
            if ref not in unknown_refs:
                unknown_refs.append(ref)
    return unknown_refs


def postprocess_sql(sql: str, tables: list[SchemaTable]) -> tuple[str, dict[str, Any]]:
    cleaned = clean_sql(sql)
    qualified_map, bare_map, table_by_ref = _build_table_maps(tables)
    mixed_case_column_map = _build_mixed_case_column_map(tables)
    variant_column_map = _build_variant_column_map(tables)
    cte_names = {_normalise_ref(match.group("name")) for match in CTE_RE.finditer(cleaned)}
    diagnostics: dict[str, Any] = {
        "qualified_table_refs": 0,
        "quoted_column_refs": 0,
        "rewritten_variant_paths": 0,
        "unknown_table_refs": [],
        "unknown_column_refs": [],
        "placeholder_detected": bool(PLACEHOLDER_RE.search(cleaned)),
    }

    def replace_ref(match: re.Match[str]) -> str:
        keyword = match.group("keyword")
        ref_text = match.group("ref")
        normalised = _normalise_ref(ref_text)
        if normalised in cte_names or normalised in IGNORED_TABLE_REFS:
            return match.group(0)

        replacement = qualified_map.get(normalised)
        if replacement is None and "." not in normalised:
            replacement = bare_map.get(normalised)
        if replacement is None:
            if normalised not in diagnostics["unknown_table_refs"]:
                diagnostics["unknown_table_refs"].append(normalised)
            return match.group(0)

        if _normalise_ref(replacement) == normalised:
            return match.group(0)
        diagnostics["qualified_table_refs"] += 1
        return f"{keyword} {replacement}"

    processed = TABLE_REF_RE.sub(replace_ref, cleaned)
    processed, diagnostics["quoted_column_refs"] = _quote_mixed_case_columns(
        processed,
        mixed_case_column_map,
    )
    processed, diagnostics["rewritten_variant_paths"] = _rewrite_variant_dot_paths(
        processed,
        variant_column_map,
    )
    diagnostics["unknown_column_refs"] = _find_unknown_column_refs(
        processed,
        qualified_map=qualified_map,
        bare_map=bare_map,
        table_by_ref=table_by_ref,
    )
    return processed.strip(), diagnostics


def write_json(path: str | Path, data: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)
