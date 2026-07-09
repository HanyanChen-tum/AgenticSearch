"""Heuristic query-enrichment stage for DB-RLM."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ours.db_environment import DBEnvironment
from ours.metadata import DatabaseMetadata

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
}


@dataclass
class QueryEnrichment:
    """Structured hints extracted before the main reasoning loop."""

    normalized_question: str
    candidate_tables: list[dict[str, Any]]
    candidate_columns: list[dict[str, Any]]
    matched_values: list[dict[str, Any]]
    numeric_mentions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_question": self.normalized_question,
            "candidate_tables": self.candidate_tables,
            "candidate_columns": self.candidate_columns,
            "matched_values": self.matched_values,
            "numeric_mentions": self.numeric_mentions,
        }

    def to_prompt(self, max_chars: int = 3000) -> str:
        lines = ["QUERY ENRICHMENT:"]
        lines.append(f"- normalized_question: {self.normalized_question}")
        if self.numeric_mentions:
            lines.append(f"- numeric_mentions: {', '.join(self.numeric_mentions)}")
        if self.candidate_tables:
            lines.append("- likely_tables:")
            for item in self.candidate_tables[:6]:
                reason = ", ".join(item.get("reasons", [])) or "token overlap"
                lines.append(f"  - {item['table']} (score={item['score']}; {reason})")
        if self.candidate_columns:
            lines.append("- likely_columns:")
            for item in self.candidate_columns[:10]:
                lines.append(
                    f"  - {item['table']}.{item['column']} (score={item['score']})"
                )
        if self.matched_values:
            lines.append("- matched_values:")
            for item in self.matched_values[:8]:
                values = ", ".join(repr(v) for v in item["values"])
                lines.append(f"  - {item['table']}.{item['column']}: {values}")

        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n[query enrichment truncated]"


def enrich_question(
    question: str,
    db: DBEnvironment,
    metadata: DatabaseMetadata | None = None,
    sample_limit: int = 5,
    max_tables: int = 4,
) -> QueryEnrichment:
    """Infer likely tables, columns, and filter values from question text."""
    normalized = _normalize_space(question)
    question_lower = normalized.lower()
    question_tokens = _tokenize(normalized)
    numeric_mentions = re.findall(r"\b\d+(?:\.\d+)?\b", normalized)

    candidate_tables: list[dict[str, Any]] = []
    candidate_columns: list[dict[str, Any]] = []
    scored_tables: list[tuple[int, str]] = []

    if metadata is not None:
        for table in metadata.tables:
            table_tokens = _tokenize(table.name)
            score = _overlap_score(question_tokens, table_tokens) * 3
            reasons: list[str] = []
            if score:
                reasons.append("table-name overlap")

            local_columns: list[dict[str, Any]] = []
            for column in table.columns:
                column_tokens = _tokenize(column["name"])
                column_score = _overlap_score(question_tokens, column_tokens)
                if column_score:
                    local_columns.append(
                        {
                            "table": table.name,
                            "column": column["name"],
                            "score": column_score,
                        }
                    )
                    score += column_score

            if local_columns:
                reasons.append("column-name overlap")
                candidate_columns.extend(local_columns)

            if score > 0:
                candidate_tables.append(
                    {"table": table.name, "score": score, "reasons": reasons}
                )
                scored_tables.append((score, table.name))

    if not scored_tables and metadata is not None:
        scored_tables = [(1, table.name) for table in metadata.tables[:max_tables]]
        candidate_tables = [
            {"table": table.name, "score": 1, "reasons": ["fallback-top-table"]}
            for table in metadata.tables[:max_tables]
        ]

    candidate_tables.sort(key=lambda item: (-item["score"], item["table"]))
    candidate_columns.sort(
        key=lambda item: (-item["score"], item["table"], item["column"])
    )

    matched_values = _collect_value_matches(
        db=db,
        question_lower=question_lower,
        candidate_tables=[table for _, table in sorted(scored_tables, reverse=True)[:max_tables]],
        sample_limit=sample_limit,
    )

    return QueryEnrichment(
        normalized_question=normalized,
        candidate_tables=candidate_tables,
        candidate_columns=candidate_columns,
        matched_values=matched_values,
        numeric_mentions=numeric_mentions,
    )


def _collect_value_matches(
    db: DBEnvironment,
    question_lower: str,
    candidate_tables: list[str],
    sample_limit: int,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    index: dict[tuple[str, str], dict[str, Any]] = {}
    exact_tokens = sorted(_tokenize(question_lower))

    for table in candidate_tables:
        schema = db.get_schema(table)
        text_columns = [
            column["name"]
            for column in schema.get("columns", [])
            if "CHAR" in column["type"].upper() or "TEXT" in column["type"].upper()
        ]

        for column in text_columns:
            for token in exact_tokens:
                sql = (
                    "SELECT DISTINCT "
                    f"{_quote_identifier(column)} AS value "
                    f"FROM {_quote_identifier(table)} "
                    f"WHERE LOWER({_quote_identifier(column)}) = '{token}' "
                    "LIMIT 3"
                )
                result = db.execute(sql)
                if result.get("error") or not result.get("rows"):
                    continue
                values = [row[0] for row in result["rows"] if row and row[0] is not None]
                if not values:
                    continue
                key = (table, column)
                if key not in index:
                    index[key] = {"table": table, "column": column, "values": []}
                    matches.append(index[key])
                for value in values:
                    if value not in index[key]["values"]:
                        index[key]["values"].append(value)

        sample = db.sample_rows(table, limit=sample_limit)
        if sample.get("error"):
            continue

        columns = sample.get("columns", [])
        for row in sample.get("rows", []):
            for column, value in zip(columns, row):
                if not isinstance(value, str):
                    continue
                compact = value.strip()
                if len(compact) < 2 or len(compact) > 40:
                    continue
                if compact.lower() not in question_lower:
                    continue

                key = (table, column)
                if key not in index:
                    index[key] = {"table": table, "column": column, "values": []}
                    matches.append(index[key])
                if compact not in index[key]["values"]:
                    index[key]["values"].append(compact)

    return matches


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[A-Za-z0-9_]+", text.lower()))
    return {token for token in tokens if token and token not in _STOPWORDS}


def _overlap_score(question_tokens: set[str], name_tokens: set[str]) -> int:
    return len(question_tokens & name_tokens)


def _quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'
