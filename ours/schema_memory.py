"""Deterministic schema retrieval and compact memory for RLM experiments."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ours.metadata import DatabaseMetadata


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "the", "to", "what",
    "when", "where", "which", "who", "with",
}


def _tokens(text: str) -> set[str]:
    values = set(re.findall(r"[a-z0-9]+", text.lower().replace("_", " ")))
    return {value for value in values if value not in _STOPWORDS}


def _score_name(name: str, query: str, query_tokens: set[str]) -> int:
    normalized = name.lower().replace("_", " ")
    name_tokens = _tokens(name)
    score = 0
    if normalized and normalized in query.lower():
        score += 8
    score += 4 * len(name_tokens & query_tokens)
    score += sum(1 for token in name_tokens if token in query.lower())
    return score


@dataclass
class MemoryColumn:
    table: str
    column: str
    column_type: str
    score: int
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "column": self.column,
            "type": self.column_type,
            "score": self.score,
            "sources": list(self.sources),
        }


class SchemaMemory:
    """Maintain the selected schema separately from the full schema catalog."""

    def __init__(self, metadata: DatabaseMetadata):
        self._metadata = metadata
        self._catalog = {
            table.name: {column["name"]: column for column in table.columns}
            for table in metadata.tables
        }
        self._foreign_keys = {
            table.name: list(table.foreign_keys) for table in metadata.tables
        }
        self._selected: dict[tuple[str, str], MemoryColumn] = {}
        self._events: list[dict[str, Any]] = []

    def search(self, query: str, top_k: int = 10, source: str = "recursive") -> list[dict[str, Any]]:
        """Retrieve top-k columns and add them to memory."""
        top_k = max(1, int(top_k))
        query_tokens = _tokens(query)
        ranked: list[tuple[int, str, str, str]] = []
        for table, columns in self._catalog.items():
            table_score = _score_name(table, query, query_tokens)
            for column, info in columns.items():
                score = table_score + _score_name(column, query, query_tokens)
                ranked.append((score, table, column, str(info.get("type") or "UNKNOWN")))
        ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        chosen = ranked[:top_k]
        for score, table, column, column_type in chosen:
            self.add_column(
                table,
                column,
                source=source,
                score=score,
                column_type=column_type,
            )
        self._events.append(
            {
                "action": "search",
                "query": query,
                "top_k": top_k,
                "source": source,
                "results": [f"{table}.{column}" for _, table, column, _ in chosen],
            }
        )
        return [
            {
                "table": table,
                "column": column,
                "type": column_type,
                "score": score,
            }
            for score, table, column, column_type in chosen
        ]

    def add_column(
        self,
        table: str,
        column: str,
        source: str = "agent",
        score: int = 0,
        column_type: str | None = None,
    ) -> dict[str, Any]:
        """Add one known catalog column to memory."""
        if table not in self._catalog or column not in self._catalog[table]:
            return {"added": False, "error": f"Unknown schema element: {table}.{column}"}
        key = (table, column)
        info = self._catalog[table][column]
        entry = self._selected.get(key)
        if entry is None:
            entry = MemoryColumn(
                table=table,
                column=column,
                column_type=column_type or str(info.get("type") or "UNKNOWN"),
                score=int(score),
            )
            self._selected[key] = entry
        entry.score = max(entry.score, int(score))
        if source not in entry.sources:
            entry.sources.append(source)
        return {"added": True, **entry.to_dict()}

    def add_table(self, table: str, source: str = "agent") -> dict[str, Any]:
        """Add every column from one table; intended for deliberate expansion."""
        if table not in self._catalog:
            return {"added": False, "error": f"Unknown table: {table}"}
        for column, info in self._catalog[table].items():
            self.add_column(
                table,
                column,
                source=source,
                column_type=str(info.get("type") or "UNKNOWN"),
            )
        self._events.append({"action": "add_table", "table": table, "source": source})
        return {"added": True, "table": table, "columns": sorted(self._catalog[table])}

    def merge_columns(
        self,
        columns_by_table: dict[str, list[str]],
        source: str = "recursive",
    ) -> None:
        for table, columns in columns_by_table.items():
            for column in columns:
                self.add_column(table, column, source=source)

    def snapshot(self) -> dict[str, Any]:
        columns = [
            entry.to_dict()
            for entry in sorted(
                self._selected.values(),
                key=lambda item: (item.table, item.column),
            )
        ]
        tables = sorted({entry.table for entry in self._selected.values()})
        return {
            "tables": tables,
            "columns": columns,
            "selected_table_count": len(tables),
            "selected_column_count": len(columns),
        }

    def events(self) -> list[dict[str, Any]]:
        return [dict(event) for event in self._events]

    def to_prompt(self, max_chars: int = 6000) -> str:
        """Return a deterministic compact representation of current memory."""
        lines = ["SCHEMA MEMORY (selected schema only):"]
        snapshot = self.snapshot()
        grouped: dict[str, list[MemoryColumn]] = {}
        for entry in self._selected.values():
            grouped.setdefault(entry.table, []).append(entry)
        for table in sorted(grouped):
            lines.append(f"\nTABLE {table}")
            for entry in sorted(grouped[table], key=lambda item: item.column):
                sources = ",".join(entry.sources)
                lines.append(
                    f"  - {entry.column} {entry.column_type} "
                    f"[score={entry.score}; source={sources}]"
                )
            for fk in self._foreign_keys.get(table, []):
                lines.append(
                    f"  FK {fk['column']} -> "
                    f"{fk['references_table']}.{fk['references_column']}"
                )
        lines.append(
            f"\nSelected {snapshot['selected_table_count']} tables / "
            f"{snapshot['selected_column_count']} columns."
        )
        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n[schema memory truncated]"
