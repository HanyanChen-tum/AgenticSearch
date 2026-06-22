"""Database schema utilities."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def get_database_path(database_dir: str | Path, db_id: str) -> Path:
    return Path(database_dir) / db_id / f"{db_id}.sqlite"


def list_tables(db_path: str | Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return [row[0] for row in rows]


def extract_schema_text(db_path: str | Path) -> str:
    """Return a stable full-schema text representation for prompting."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    tables = list_tables(path)
    schema_blocks: list[str] = []

    with sqlite3.connect(path) as conn:
        for table in tables:
            quoted_table = table.replace('"', '""')
            columns = conn.execute(f'PRAGMA table_info("{quoted_table}")').fetchall()
            foreign_keys = conn.execute(f'PRAGMA foreign_key_list("{quoted_table}")').fetchall()

            lines = [f"Table: {table}", "", "Columns:"]
            for column in columns:
                _, name, col_type, not_null, default_value, primary_key = column
                parts = [f"- {name}", col_type or "UNKNOWN"]
                if primary_key:
                    parts.append("PRIMARY KEY")
                if not_null:
                    parts.append("NOT NULL")
                if default_value is not None:
                    parts.append(f"DEFAULT {default_value}")
                lines.append(" ".join(parts))

            if foreign_keys:
                lines.extend(["", "Foreign keys:"])
                for fk in foreign_keys:
                    _, _, ref_table, from_col, to_col, *_ = fk
                    lines.append(f"- {from_col} -> {ref_table}.{to_col}")

            schema_blocks.append("\n".join(lines))

    return "\n\n".join(schema_blocks)

