"""Metadata extraction helpers for DB-RLM ablations."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TableMetadata:
    name: str
    row_count: int | None
    columns: list[dict[str, Any]]
    foreign_keys: list[dict[str, str]]


@dataclass
class DatabaseMetadata:
    db_path: str
    tables: list[TableMetadata]

    def to_dict(self) -> dict[str, Any]:
        return {
            "db_path": self.db_path,
            "tables": [
                {
                    "name": table.name,
                    "row_count": table.row_count,
                    "columns": table.columns,
                    "foreign_keys": table.foreign_keys,
                }
                for table in self.tables
            ],
        }

    def to_prompt(self, max_chars: int = 6000) -> str:
        lines = [f"METADATA FOR: {Path(self.db_path).stem}"]
        for table in self.tables:
            count = "unknown" if table.row_count is None else str(table.row_count)
            lines.append(f"\nTABLE {table.name} | rows={count}")
            for column in table.columns:
                flags = []
                if column["primary_key"]:
                    flags.append("PK")
                if column["not_null"]:
                    flags.append("NOT NULL")
                suffix = f" [{', '.join(flags)}]" if flags else ""
                lines.append(f"  - {column['name']} {column['type']}{suffix}")
            for fk in table.foreign_keys:
                lines.append(
                    f"  FK {fk['column']} -> {fk['references_table']}.{fk['references_column']}"
                )

        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n[metadata truncated]"


def extract_database_metadata(db_path: str | Path) -> DatabaseMetadata:
    path = Path(db_path).resolve()
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as conn:
        table_names = [
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        tables = []
        for table_name in table_names:
            quoted = _quote(table_name)
            columns = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
            foreign_keys = conn.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()
            try:
                row_count = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            except sqlite3.Error:
                row_count = None

            tables.append(
                TableMetadata(
                    name=table_name,
                    row_count=row_count,
                    columns=[
                        {
                            "name": column[1],
                            "type": column[2] or "UNKNOWN",
                            "not_null": bool(column[3]),
                            "primary_key": bool(column[5]),
                        }
                        for column in columns
                    ],
                    foreign_keys=[
                        {
                            "column": fk[3],
                            "references_table": fk[2],
                            "references_column": fk[4],
                        }
                        for fk in foreign_keys
                    ],
                )
            )

    return DatabaseMetadata(db_path=str(path), tables=tables)


def _quote(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'
