"""Create a per-question E3-F retrieval/adherence audit from completed traces."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_e3_f_query_mining import _shape, _signature
from ours.agent.offline_metadata import get_offline_metadata
from shared.trace_io import load_jsonl


def _sql_features(sql: str, schema_tables: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception as exc:
        return {
            "parse_error": f"{type(exc).__name__}: {exc}",
            "tables": [],
            "columns": [],
            "column_refs": [],
            "shape": [],
        }
    scopes = list(traverse_scope(tree))
    table_nodes = {
        source
        for scope in scopes
        for source in scope.sources.values()
        if isinstance(source, exp.Table)
    }
    known_columns = {
        str(column["name"]).casefold()
        for info in (schema_tables or {}).values()
        for column in info.get("columns", [])
    }
    column_refs = []
    for scope in scopes:
        sources_by_alias = {
            str(alias).casefold(): source
            for alias, source in scope.sources.items()
        }
        physical_sources = [
            source.name.casefold()
            for source in scope.sources.values()
            if isinstance(source, exp.Table)
        ]
        for column in scope.local_columns:
            name = column.name.casefold()
            if column.table:
                source = sources_by_alias.get(column.table.casefold())
                if not isinstance(source, exp.Table):
                    # A reference to a CTE/derived output is represented by the
                    # physical columns inside that source's own scope.
                    continue
                physical_table = source.name.casefold()
            else:
                physical_table = physical_sources[0] if len(physical_sources) == 1 else None
            if physical_table is None and known_columns and name not in known_columns:
                continue
            column_refs.append({"table": physical_table, "column": name})
    return {
        "parse_error": None,
        "tables": sorted({table.name.casefold() for table in table_nodes}),
        "columns": sorted({item["column"] for item in column_refs}),
        "column_refs": column_refs,
        "shape": _shape(_signature(tree)),
    }


def _last_selection(trace: dict[str, Any]) -> dict[str, Any]:
    attempts = trace.get("attempts") or []
    if attempts:
        return attempts[-1].get("knowledge_selection") or {}
    return trace.get("knowledge_selection") or {}


def _artifact_version(traces: list[dict[str, Any]], section: str, default: str) -> str:
    for trace in traces:
        selection = _last_selection(trace)
        payload = selection.get(section) or {}
        version = payload.get("artifact_version")
        if version:
            return str(version)
        attempts = trace.get("attempts") or []
        if attempts:
            manifest = (attempts[-1].get("knowledge_manifest") or {}).get(
                "offline_metadata" if section == "offline_schema" else "query_patterns"
            ) or {}
            if manifest.get("version"):
                return str(manifest["version"])
    return default


def build_rows(results: list[dict[str, Any]], traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace_by_id = {str(trace.get("id")): trace for trace in traces}
    schema_version = _artifact_version(traces, "offline_schema", "e3-f-schema-v4")
    metadata = get_offline_metadata(schema_version)
    rows = []
    for result in results:
        item_id = str(result["id"])
        selection = _last_selection(trace_by_id.get(item_id, {}))
        mining = selection.get("query_patterns") or {}
        schema = selection.get("offline_schema") or {}
        table_selection = schema.get("table_selection") or {}
        selected_tables = [str(value) for value in table_selection.get("selected_tables", [])]
        selected_table_cf = {value.casefold() for value in selected_tables}
        column_selection = schema.get("column_selection") or {}
        selected_columns_by_table = {
            str(table).casefold(): {
                str(column).casefold()
                for column in diagnostics.get("selected_columns", [])
            }
            for table, diagnostics in column_selection.items()
        }
        db_metadata = metadata.for_database(str(result.get("db_id"))) or {}
        schema_tables = db_metadata.get("tables", {})
        predicted = _sql_features(str(result.get("predicted_sql") or ""), schema_tables)
        gold = _sql_features(str(result.get("gold_sql") or ""), schema_tables)
        selected_constraints = mining.get("selected_constraints", [])
        selected_ids = mining.get("selected_constraint_ids", [])
        if not selected_ids:
            selected_ids = mining.get("selected_pattern_ids", [])
        selected_items = selected_constraints
        if not selected_items and selected_ids:
            selected_id_set = {str(value) for value in selected_ids}
            selected_items = [
                candidate
                for candidate in mining.get("candidates", [])
                if str(candidate.get("pattern_id")) in selected_id_set
            ]
        missing_gold_tables = sorted(set(gold["tables"]) - selected_table_cf)
        missing_gold_columns = []
        for reference in gold.get("column_refs", []):
            table = reference["table"]
            column = reference["column"]
            if table:
                covered = column in selected_columns_by_table.get(table, set())
            else:
                covered = any(column in values for values in selected_columns_by_table.values())
            if not covered:
                missing_gold_columns.append(
                    f"{table}.{column}" if table else column
                )
        missing_gold_columns = sorted(set(missing_gold_columns))
        final_unselected_tables = sorted(set(predicted["tables"]) - selected_table_cf)
        if result.get("correct"):
            diagnostic = "correct"
        elif missing_gold_tables:
            diagnostic = "detailed_schema_table_miss"
        elif missing_gold_columns:
            diagnostic = "detailed_schema_column_miss_or_compact_index_only"
        elif selected_items:
            diagnostic = "retrieval_complete_with_mined_items_semantic_failure"
        else:
            diagnostic = "retrieval_complete_mining_abstained_semantic_failure"
        rows.append({
            "id": item_id,
            "db_id": result.get("db_id"),
            "difficulty": result.get("difficulty"),
            "correct": bool(result.get("correct")),
            "diagnostic": diagnostic,
            "mining_artifact_version": _artifact_version(
                [trace_by_id.get(item_id, {})], "query_patterns", "unknown"
            ),
            "mining_selection_mode": mining.get("selection_mode"),
            "mining_selected_item_ids": selected_ids,
            "mining_selected_items": selected_items,
            "mining_abstained": mining.get("abstained"),
            "schema_artifact_version": schema.get("artifact_version", schema_version),
            "schema_selected_tables": selected_tables,
            "schema_seed_mode": table_selection.get("seed_mode"),
            "schema_seeds": table_selection.get("seeds", []),
            "schema_path_expansions": table_selection.get("path_expansions", []),
            "schema_fk_neighbour_expansions": table_selection.get("fk_neighbour_expansions", []),
            "schema_truncated_tables": table_selection.get("truncated_tables", []),
            "schema_columns_truncated": (schema.get("truncation_summary") or {}).get("columns_truncated_by_table", {}),
            "gold_tables": gold["tables"],
            "gold_columns": gold["columns"],
            "gold_shape": gold["shape"],
            "gold_detail_table_misses": missing_gold_tables,
            "gold_detail_column_name_misses": missing_gold_columns,
            "final_tables": predicted["tables"],
            "final_columns": predicted["columns"],
            "final_shape": predicted["shape"],
            "final_tables_outside_detailed_context": final_unselected_tables,
            "predicted_sql_parse_error": predicted["parse_error"],
            "gold_sql_parse_error": gold["parse_error"],
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--transcripts", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-csv", required=True)
    args = parser.parse_args()
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    traces = load_jsonl(Path(args.transcripts))
    rows = build_rows(results, traces)
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.out_csv).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                    for key, value in row.items()
                })
    print(f"wrote {len(rows)} retrieval audit rows")


if __name__ == "__main__":
    main()
