"""Offline schema precomputation for BIRD databases.

Extracts schema once per database and caches to JSON.
Enriches the raw SQLite schema with BIRD's column descriptions and value hints
from the database_description CSV files — the same signal top leaderboard teams use.

Usage:
    # Build cache (run once):
    python -m ours.schema_cache --db-dir data/raw/bird/minidev/MINIDEV/dev_databases

    # Use in agents:
    from ours.schema_cache import get_schema_cache
    cache = get_schema_cache()
    schema_str = cache.format_schema("california_schools")
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from functools import lru_cache

import pandas as pd

_DEFAULT_DB_DIR   = Path(__file__).resolve().parents[1] / "data/raw/bird/minidev/MINIDEV/dev_databases"
_DEFAULT_CACHE    = Path(__file__).resolve().parents[1] / "data/processed/schema_cache.json"
_MAX_VALUE_SAMPLE = 5


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_cache(db_dir: Path, output_path: Path) -> dict:
    """Walk all databases, extract enriched schema, write to JSON."""
    db_dir = Path(db_dir)
    cache = {}

    for db_path in sorted(db_dir.iterdir()):
        if not db_path.is_dir():
            continue
        db_id = db_path.name
        sqlite_file = db_path / f"{db_id}.sqlite"
        if not sqlite_file.exists():
            sqlite_file = db_path / f"{db_id}.db"
        if not sqlite_file.exists():
            continue

        print(f"  Processing {db_id}...")
        desc_dir = db_path / "database_description"
        col_descriptions = _load_descriptions(desc_dir)

        schema = _extract_schema(sqlite_file, col_descriptions)
        cache[db_id] = schema

    Path(output_path).parent.mkdir(exist_ok=True)
    Path(output_path).write_text(json.dumps(cache, indent=2))
    print(f"Cache written to {output_path} ({len(cache)} databases)")
    return cache


def _load_descriptions(desc_dir: Path) -> dict[str, dict[str, dict]]:
    """Load column descriptions from CSV files. Returns {table: {col: {desc, value_desc}}}."""
    result: dict[str, dict] = {}
    if not desc_dir.exists():
        return result
    for csv_file in desc_dir.glob("*.csv"):
        table = csv_file.stem
        try:
            df = pd.read_csv(csv_file, encoding="utf-8", on_bad_lines="skip")
        except Exception:
            try:
                df = pd.read_csv(csv_file, encoding="latin-1", on_bad_lines="skip")
            except Exception:
                continue

        result[table] = {}
        for _, row in df.iterrows():
            col = str(row.get("original_column_name", "")).strip()
            if not col or col == "nan":
                continue
            col_desc = str(row.get("column_description", "")).strip()
            val_desc = str(row.get("value_description", "")).strip()
            result[table][col] = {
                "description": col_desc if col_desc != "nan" else "",
                "value_description": val_desc if val_desc != "nan" else "",
            }
    return result


def _extract_schema(sqlite_file: Path, col_descriptions: dict) -> dict:
    """Extract tables, columns, types, PKs, FKs and merge descriptions."""
    uri = f"{sqlite_file.resolve().as_uri()}?mode=ro"
    tables = {}

    with sqlite3.connect(uri, uri=True) as conn:
        table_names = [
            row[0] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        ]

        for table in table_names:
            quoted = f'"{table}"'
            cols_raw = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
            fks_raw  = conn.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()

            # Sample distinct values for text columns (helps with filter conditions)
            value_samples: dict[str, list] = {}
            for col_row in cols_raw:
                col_name = col_row[1]
                col_type = (col_row[2] or "").upper()
                if "TEXT" in col_type or "CHAR" in col_type or col_type == "":
                    try:
                        rows = conn.execute(
                            f'SELECT DISTINCT "{col_name}" FROM {quoted} '
                            f'WHERE "{col_name}" IS NOT NULL LIMIT {_MAX_VALUE_SAMPLE}'
                        ).fetchall()
                        vals = [r[0] for r in rows if r[0] is not None]
                        if vals:
                            value_samples[col_name] = vals
                    except Exception:
                        pass

            table_desc = col_descriptions.get(table, {})
            columns = []
            for c in cols_raw:
                col_name = c[1]
                info = table_desc.get(col_name, {})
                col_entry: dict = {
                    "name": col_name,
                    "type": c[2] or "TEXT",
                    "primary_key": bool(c[5]),
                    "not_null": bool(c[3]),
                }
                if info.get("description"):
                    col_entry["description"] = info["description"]
                if info.get("value_description"):
                    col_entry["value_description"] = info["value_description"]
                if col_name in value_samples:
                    col_entry["sample_values"] = value_samples[col_name]
                columns.append(col_entry)

            tables[table] = {
                "columns": columns,
                "foreign_keys": [
                    {"column": fk[3], "references": f"{fk[2]}.{fk[4]}"}
                    for fk in fks_raw
                ],
            }

    return tables


# ---------------------------------------------------------------------------
# Runtime accessor
# ---------------------------------------------------------------------------

class SchemaCache:
    def __init__(self, cache_path: Path = _DEFAULT_CACHE):
        self._data: dict = json.loads(Path(cache_path).read_text())

    def format_schema(self, db_id: str, include_descriptions: bool = True,
                      include_samples: bool = True) -> str:
        """Return compact human-readable enriched schema for prompt injection."""
        db = self._data.get(db_id)
        if not db:
            return f"(schema not found for {db_id})"

        lines = [f"DATABASE: {db_id}"]
        for table, info in db.items():
            lines.append(f"\nTABLE: {table}")
            for col in info["columns"]:
                flags = []
                if col["primary_key"]:
                    flags.append("PK")
                if col["not_null"]:
                    flags.append("NOT NULL")
                suffix = f"  [{', '.join(flags)}]" if flags else ""
                line = f"  {col['name']} {col['type']}{suffix}"

                extras = []
                if include_descriptions and col.get("description"):
                    # Keep short — truncate at 80 chars
                    desc = col["description"][:80].replace("\n", " ")
                    extras.append(f"— {desc}")
                if include_descriptions and col.get("value_description"):
                    vd = col["value_description"][:60].replace("\n", " ")
                    extras.append(f"[values: {vd}]")
                elif include_samples and col.get("sample_values"):
                    samples = ", ".join(str(v) for v in col["sample_values"][:3])
                    extras.append(f"[e.g. {samples}]")

                if extras:
                    line += "  " + "  ".join(extras)
                lines.append(line)

            for fk in info["foreign_keys"]:
                lines.append(f"  FK: {fk['column']} → {fk['references']}")

        return "\n".join(lines)

    def available_dbs(self) -> list[str]:
        return list(self._data.keys())


@lru_cache(maxsize=1)
def get_schema_cache(cache_path: str = str(_DEFAULT_CACHE)) -> SchemaCache:
    """Singleton — load once, reuse everywhere."""
    return SchemaCache(Path(cache_path))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-dir",  default=str(_DEFAULT_DB_DIR))
    parser.add_argument("--output",  default=str(_DEFAULT_CACHE))
    args = parser.parse_args()
    print(f"Building schema cache from {args.db_dir}...")
    build_cache(Path(args.db_dir), Path(args.output))
