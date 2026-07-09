"""Automatic probe-query stage for DB-RLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ours.db_environment import DBEnvironment
from ours.query_enrichment import QueryEnrichment
from ours.workspace import EvidenceWorkspace


@dataclass
class ProbeQuerySummary:
    """Compact record of exploratory SQL queries run before final reasoning."""

    queries: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"queries": self.queries}

    def to_prompt(self, max_chars: int = 3000) -> str:
        lines = ["PROBE QUERY RESULTS:"]
        for item in self.queries:
            lines.append(f"- {item['note']}")
            lines.append(f"  SQL: {item['sql']}")
            if item.get("error"):
                lines.append(f"  ERROR: {item['error']}")
            else:
                lines.append(f"  ROWS: {item['rows']}")
        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n[probe query summary truncated]"


def run_probe_queries(
    db: DBEnvironment,
    enrichment: QueryEnrichment,
    workspace: EvidenceWorkspace | None = None,
    max_queries: int = 4,
) -> ProbeQuerySummary:
    """Run a few read-only exploratory SQL queries and capture the results."""
    plans: list[tuple[str, str]] = []

    for table_item in enrichment.candidate_tables[:max_queries]:
        table = table_item["table"]
        sql = f"SELECT COUNT(*) AS row_count FROM {_quote_identifier(table)}"
        plans.append((f"row count for {table}", sql))

    for value_item in enrichment.matched_values:
        table = value_item["table"]
        column = value_item["column"]
        for value in value_item["values"]:
            if len(plans) >= max_queries:
                break
            safe_value = value.replace("'", "''")
            sql = (
                "SELECT "
                f"{_quote_identifier(column)} AS matched_value, "
                "COUNT(*) AS matched_count "
                f"FROM {_quote_identifier(table)} "
                f"WHERE {_quote_identifier(column)} = '{safe_value}' "
                f"GROUP BY {_quote_identifier(column)}"
            )
            plans.append((f"value frequency for {table}.{column}={value!r}", sql))
        if len(plans) >= max_queries:
            break

    results: list[dict[str, Any]] = []
    for note, sql in plans[:max_queries]:
        execution = db.execute(sql)
        item = {
            "note": note,
            "sql": sql,
            "rows": execution.get("rows"),
            "columns": execution.get("columns"),
            "error": execution.get("error"),
        }
        results.append(item)
        if workspace is not None:
            workspace.add(note, item)

    return ProbeQuerySummary(queries=results)


def _quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'
