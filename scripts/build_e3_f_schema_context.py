"""Build the source-audited E3-F Offline Schema Context artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ours.schema_cache import _extract_schema, _load_descriptions


VERSION = "e3-f-schema-v4"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _source_manifest(db_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(p for p in db_dir.rglob("*") if p.is_file()):
        if path.suffix.casefold() not in {".sqlite", ".db", ".csv"}:
            continue
        files.append({
            "path": path.relative_to(db_dir).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        })
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "root_role": "bird-evaluation-database-and-description-files",
        "files": files,
        "file_count": len(files),
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
        "contains_eval_questions": False,
        "contains_gold_sql": False,
    }


def _canonical_table(tables: dict[str, Any], name: str) -> str | None:
    lookup = {table.casefold(): table for table in tables}
    return lookup.get(str(name).casefold())


def _resolve_target_column(
    tables: dict[str, Any], target_table: str, target_column: Any, child_column: str
) -> str | None:
    columns = tables[target_table]["columns"]
    by_name = {str(column["name"]).casefold(): str(column["name"]) for column in columns}
    if target_column not in {None, "", "None"}:
        return by_name.get(str(target_column).casefold())
    primary = [str(column["name"]) for column in columns if column.get("primary_key")]
    if len(primary) == 1:
        return primary[0]
    return by_name.get(child_column.casefold())


def _repair_foreign_keys(tables: dict[str, Any]) -> list[dict[str, Any]]:
    unresolved = []
    for table, info in tables.items():
        repaired = []
        seen = set()
        for fk in info.get("foreign_keys", []):
            raw = str(fk.get("references", ""))
            target_name, _, target_column = raw.partition(".")
            target_table = _canonical_table(tables, target_name)
            resolved_column = (
                _resolve_target_column(
                    tables, target_table, target_column or None, str(fk.get("column", ""))
                )
                if target_table else None
            )
            if not target_table or not resolved_column:
                unresolved.append({"table": table, **fk})
                continue
            key = (str(fk["column"]).casefold(), target_table.casefold(), resolved_column.casefold())
            if key in seen:
                continue
            seen.add(key)
            repaired.append({
                "column": str(fk["column"]),
                "references": f"{target_table}.{resolved_column}",
            })
        info["foreign_keys"] = repaired
    return unresolved


def _column_stats(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    non_null, distinct = conn.execute(
        f"SELECT COUNT({_quote(column)}), COUNT(DISTINCT {_quote(column)}) "
        f"FROM {_quote(table)}"
    ).fetchone()
    return {"non_null_rows": int(non_null), "distinct_values": int(distinct)}


def _json_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _add_column_profiles(
    conn: sqlite3.Connection, tables: dict[str, Any], row_counts: dict[str, int]
) -> None:
    """Add low-cost filter metadata with one aggregate scan per table."""
    for table, info in tables.items():
        columns = info.get("columns", [])
        if not columns:
            continue
        expressions = []
        for column in columns:
            quoted = _quote(str(column["name"]))
            expressions.extend([
                f"COUNT({quoted})",
                f"MIN({quoted})",
                f"MAX({quoted})",
            ])
        values = conn.execute(
            f"SELECT {', '.join(expressions)} FROM {_quote(table)}"
        ).fetchone()
        row_count = row_counts[table]
        for index, column in enumerate(columns):
            non_null = int(values[index * 3] or 0)
            column["profile"] = {
                "non_null_rows": non_null,
                "null_fraction": round((row_count - non_null) / row_count, 6) if row_count else 0.0,
                "min_value": _json_scalar(values[index * 3 + 1]),
                "max_value": _json_scalar(values[index * 3 + 2]),
            }


def _relationship_stats(
    conn: sqlite3.Connection,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
) -> dict[str, Any]:
    child = _column_stats(conn, child_table, child_column)
    parent = _column_stats(conn, parent_table, parent_column)
    matched = int(conn.execute(
        f"SELECT COUNT(DISTINCT c.{_quote(child_column)}) "
        f"FROM {_quote(child_table)} AS c "
        f"INNER JOIN {_quote(parent_table)} AS p "
        f"ON c.{_quote(child_column)} = p.{_quote(parent_column)} "
        f"WHERE c.{_quote(child_column)} IS NOT NULL"
    ).fetchone()[0])
    max_child_rows = conn.execute(
        f"SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM {_quote(child_table)} "
        f"WHERE {_quote(child_column)} IS NOT NULL GROUP BY {_quote(child_column)})"
    ).fetchone()[0]
    child_unique = child["non_null_rows"] == child["distinct_values"]
    parent_unique = parent["non_null_rows"] == parent["distinct_values"]
    if parent_unique and child_unique:
        cardinality = "one-to-one"
    elif parent_unique:
        cardinality = "many-to-one"
    else:
        cardinality = "non-key-reference"
    return {
        "cardinality": cardinality,
        "child_non_null_rows": child["non_null_rows"],
        "child_distinct_keys": child["distinct_values"],
        "target_non_null_rows": parent["non_null_rows"],
        "target_distinct_keys": parent["distinct_values"],
        "matched_child_distinct_keys": matched,
        "referential_coverage": round(matched / child["distinct_values"], 6)
        if child["distinct_values"] else 0.0,
        "max_child_rows_per_key": int(max_child_rows or 0),
        "target_unique": parent_unique,
    }


def _name_tokens(value: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", spaced)
        if token.casefold() not in {"the", "of", "a", "an"}
    }


def _join_name_candidate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_name = str(left["name"])
    right_name = str(right["name"])
    left_cf = re.sub(r"[^a-z0-9]", "", left_name.casefold())
    right_cf = re.sub(r"[^a-z0-9]", "", right_name.casefold())
    if left_cf == right_cf and left_cf not in {"id", "name", "type", "date", "code"}:
        return True
    left_tokens = _name_tokens(left_name)
    right_tokens = _name_tokens(right_name)
    # The only non-exact name bridge currently admitted is a qualified code
    # name such as setCode -> code. Broader token-subset matching incorrectly
    # linked constructorId to constructorResultsId despite perfect value overlap.
    smaller, larger = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    return smaller == {"code"} and "code" in larger and len(larger) == 2


def _infer_join_edges(
    conn: sqlite3.Connection,
    tables: dict[str, Any],
    declared_edges: list[dict[str, Any]],
    row_counts: dict[str, int],
) -> list[dict[str, Any]]:
    """Infer only high-coverage, unique-target relationships from DB contents."""
    existing = {
        frozenset({
            (edge["from_table"].casefold(), edge["from_column"].casefold()),
            (edge["to_table"].casefold(), edge["to_column"].casefold()),
        })
        for edge in declared_edges
    }
    declared_child_columns = {
        (edge["from_table"].casefold(), edge["from_column"].casefold())
        for edge in declared_edges
    }
    inferred = []
    table_names = sorted(tables, key=str.casefold)
    for left_index, left_table in enumerate(table_names):
        for right_table in table_names[left_index + 1:]:
            for left in tables[left_table].get("columns", []):
                for right in tables[right_table].get("columns", []):
                    if not _join_name_candidate(left, right):
                        continue
                    pair = frozenset({
                        (left_table.casefold(), str(left["name"]).casefold()),
                        (right_table.casefold(), str(right["name"]).casefold()),
                    })
                    if pair in existing:
                        continue
                    left_stats = _column_stats(conn, left_table, str(left["name"]))
                    right_stats = _column_stats(conn, right_table, str(right["name"]))
                    directions = []
                    if left_stats["non_null_rows"] == left_stats["distinct_values"]:
                        directions.append((right_table, right, left_table, left))
                    if right_stats["non_null_rows"] == right_stats["distinct_values"]:
                        directions.append((left_table, left, right_table, right))
                    best = None
                    for child_table, child, parent_table, parent in directions:
                        if (
                            child_table.casefold(), str(child["name"]).casefold()
                        ) in declared_child_columns:
                            continue
                        stats = _relationship_stats(
                            conn, child_table, str(child["name"]),
                            parent_table, str(parent["name"]),
                        )
                        if stats["child_distinct_keys"] < 2 or stats["referential_coverage"] < 0.95:
                            continue
                        candidate = {
                            "from_table": child_table,
                            "from_column": str(child["name"]),
                            "to_table": parent_table,
                            "to_column": str(parent["name"]),
                            **stats,
                            "nullable": child["profile"]["non_null_rows"] < row_counts[child_table],
                            "provenance": "inferred_name_and_value_overlap",
                            "confidence": "high",
                        }
                        if best is None or candidate["referential_coverage"] > best["referential_coverage"]:
                            best = candidate
                    if best is not None:
                        inferred.append(best)
                        existing.add(pair)
    return inferred


def _add_statistics(sqlite_file: Path, tables: dict[str, Any]) -> list[dict[str, Any]]:
    edges = []
    uri = f"{sqlite_file.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row_counts = {}
        for table, info in tables.items():
            row_count = int(conn.execute(
                f"SELECT COUNT(*) FROM {_quote(table)}"
            ).fetchone()[0])
            row_counts[table] = row_count
            info["row_count"] = row_count
        _add_column_profiles(conn, tables, row_counts)
        for table, info in tables.items():
            for fk in info.get("foreign_keys", []):
                target_table, target_column = fk["references"].split(".", 1)
                stats = _relationship_stats(
                    conn, table, fk["column"], target_table, target_column
                )
                nullable = stats["child_non_null_rows"] < row_counts[table]
                edge = {
                    "from_table": table,
                    "from_column": fk["column"],
                    "to_table": target_table,
                    "to_column": target_column,
                    **stats,
                    "nullable": nullable,
                    "provenance": "declared_foreign_key",
                    "confidence": "declared",
                }
                edges.append(edge)
                fk.update({
                    "cardinality": stats["cardinality"],
                    "nullable": nullable,
                    "non_null_rows": stats["child_non_null_rows"],
                    "distinct_keys": stats["child_distinct_keys"],
                    "referential_coverage": stats["referential_coverage"],
                    "max_child_rows_per_key": stats["max_child_rows_per_key"],
                })
        edges.extend(_infer_join_edges(conn, tables, edges, row_counts))
        for edge in edges:
            for table_name, column_name in (
                (edge["from_table"], edge["from_column"]),
                (edge["to_table"], edge["to_column"]),
            ):
                for column in tables[table_name].get("columns", []):
                    if str(column["name"]).casefold() != str(column_name).casefold():
                        continue
                    column["join_key"] = True
                    sources = column.setdefault("join_key_provenance", [])
                    if edge["provenance"] not in sources:
                        sources.append(edge["provenance"])
                    sources.sort()
                    break
    return sorted(edges, key=lambda edge: (
        edge["from_table"].casefold(), edge["from_column"].casefold(),
        edge["to_table"].casefold(), edge["to_column"].casefold(),
    ))


def build(db_dir: Path, output: Path) -> dict[str, Any]:
    db_dir = db_dir.resolve()
    databases = {}
    unresolved = []
    for db_path in sorted(path for path in db_dir.iterdir() if path.is_dir()):
        sqlite_file = db_path / f"{db_path.name}.sqlite"
        if not sqlite_file.exists():
            sqlite_file = db_path / f"{db_path.name}.db"
        if not sqlite_file.exists():
            continue
        tables = _extract_schema(
            sqlite_file, _load_descriptions(db_path / "database_description")
        )
        tables = {
            name: info for name, info in tables.items()
            if not name.casefold().startswith("sqlite_")
        }
        unresolved.extend(
            {"database": db_path.name, **item}
            for item in _repair_foreign_keys(tables)
        )
        edges = _add_statistics(sqlite_file, tables)
        databases[db_path.name] = {"tables": tables, "join_edges": edges}
    if unresolved:
        raise ValueError(f"Unresolved foreign keys: {unresolved}")
    payload = {
        "version": VERSION,
        "source": {
            **_source_manifest(db_dir),
            "builder_path": Path(__file__).relative_to(PROJECT_ROOT).as_posix(),
            "builder_sha256": _sha256(Path(__file__)),
        },
        "build_config": {
            "exclude_internal_sqlite_tables": True,
            "sample_values_source": "read-only database distinct values",
            "foreign_key_target_resolution": "declared-column-or-single-primary-key",
            "column_profiles": "one-pass non-null/min/max per table",
            "inferred_join_policy": "name-compatible unique target with >=0.95 distinct-key coverage",
        },
        "databases": databases,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-dir", default="data/raw/bird/minidev/MINIDEV/dev_databases")
    parser.add_argument("--output", default="data/processed/e3_f_schema_v4.json")
    args = parser.parse_args()
    built = build(Path(args.db_dir), Path(args.output).resolve())
    print(f"wrote {args.output}: {len(built['databases'])} databases")
