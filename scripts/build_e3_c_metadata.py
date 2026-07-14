"""Build the source-audited E3-C Offline metadata artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ours.schema_cache import _extract_schema, _load_descriptions


VERSION = "e3-c-metadata-v2"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _join_paths(tables: dict) -> list[str]:
    paths = []
    for table, info in tables.items():
        for fk in info.get("foreign_keys", []):
            paths.append(f"{table}.{fk['column']} = {fk['references']}")
    return sorted(set(paths))


def _add_relation_statistics(sqlite_file: Path, tables: dict) -> None:
    """Add offline-only row counts and FK multiplicity without using questions/gold."""
    uri = f"{sqlite_file.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        for table, info in tables.items():
            quoted_table = '"' + table.replace('"', '""') + '"'
            info["row_count"] = conn.execute(
                f"SELECT COUNT(*) FROM {quoted_table}"
            ).fetchone()[0]
            for fk in info.get("foreign_keys", []):
                column = str(fk["column"])
                quoted_column = '"' + column.replace('"', '""') + '"'
                non_null, distinct = conn.execute(
                    f"SELECT COUNT({quoted_column}), COUNT(DISTINCT {quoted_column}) "
                    f"FROM {quoted_table}"
                ).fetchone()
                fk["relationship"] = (
                    "one-to-one-or-sparse" if non_null == distinct else "many-to-one"
                )
                fk["non_null_rows"] = non_null
                fk["distinct_keys"] = distinct


def build(db_dir: Path, output: Path) -> dict:
    databases = {}
    for db_path in sorted(db_dir.iterdir()):
        if not db_path.is_dir():
            continue
        sqlite_file = db_path / f"{db_path.name}.sqlite"
        if not sqlite_file.exists():
            sqlite_file = db_path / f"{db_path.name}.db"
        if not sqlite_file.exists():
            continue
        schema = _extract_schema(sqlite_file, _load_descriptions(db_path / "database_description"))
        _add_relation_statistics(sqlite_file, schema)
        databases[db_path.name] = {"tables": schema, "join_paths": _join_paths(schema)}
    payload = {
        "version": VERSION,
        "source": {
            "database_dir": str(db_dir.resolve()),
            "database_dir_sha256": hashlib.sha256(
                "\n".join(f"{name}:{databases[name]['join_paths']}" for name in sorted(databases)).encode()
            ).hexdigest(),
            "contains_eval_questions": False,
            "contains_gold_sql": False,
        },
        "databases": databases,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-dir", default="data/raw/bird/minidev/MINIDEV/dev_databases")
    parser.add_argument("--output", default="data/processed/e3_c_metadata_v2.json")
    args = parser.parse_args()
    payload = build(Path(args.db_dir).resolve(), Path(args.output).resolve())
    print(f"wrote {args.output}: {len(payload['databases'])} databases")
