"""Offline preflight gates for Schema-v4 and the full E3-F integration."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any

import sqlglot
from sqlglot import exp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ours.agent.offline_metadata import get_offline_metadata
from ours.agent.query_mining import get_mined_query_patterns


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _physical_tables(sql: str) -> set[str]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    ctes = {cte.alias_or_name.casefold() for cte in tree.find_all(exp.CTE)}
    return {
        table.name.casefold()
        for table in tree.find_all(exp.Table)
        if table.name.casefold() not in ctes
    }


def _connected(db: dict[str, Any], required: set[str]) -> bool:
    if len(required) < 2:
        return True
    names = {table.casefold(): table for table in db["tables"]}
    if not required <= set(names):
        return False
    graph = {table: set() for table in db["tables"]}
    for edge in db.get("join_edges", []):
        graph[edge["from_table"]].add(edge["to_table"])
        graph[edge["to_table"]].add(edge["from_table"])
    actual = [names[table] for table in required]
    seen = {actual[0]}
    queue = [actual[0]]
    while queue:
        current = queue.pop(0)
        for neighbour in graph[current]:
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return all(table in seen for table in actual)


def audit(dataset: Path, ids_file: Path, target: str) -> dict[str, Any]:
    metadata = get_offline_metadata("e3-f-schema-v4")
    mining = get_mined_query_patterns()
    dataset_rows = json.loads(dataset.read_text(encoding="utf-8"))
    groups = json.loads(ids_file.read_text(encoding="utf-8"))
    selected_ids = set(groups["both_wrong"]) | set(groups["canary"])
    rows = [row for row in dataset_rows if row["id"] in selected_ids]

    schema_payload = metadata._payload
    mining_payload = mining._payload
    schema_builder = PROJECT_ROOT / schema_payload["source"]["builder_path"]
    mining_builder = PROJECT_ROOT / mining_payload["source"]["builder_path"]
    table_hits = 0
    multi_table = 0
    connected = 0
    prompt_chars = []
    selected_table_counts = []
    table_misses = []
    for row in rows:
        required = _physical_tables(row["gold_sql"])
        selection = metadata.selection_manifest(
            row["db_id"], question=row["question"], evidence=row.get("evidence", "")
        )
        detailed = {
            table.casefold()
            for table in selection["table_selection"]["selected_tables"]
        }
        if required <= detailed:
            table_hits += 1
        else:
            table_misses.append({"id": row["id"], "tables": sorted(required - detailed)})
        if len(required) > 1:
            multi_table += 1
            connected += _connected(metadata.for_database(row["db_id"]), required)
        selected_table_counts.append(len(detailed))
        prompt_chars.append(len(metadata.render(
            row["db_id"], question=row["question"], evidence=row.get("evidence", "")
        )))

    checks = {
        "dataset_count_is_197": len(rows) == 197,
        "schema_builder_hash_matches": (
            _sha256(schema_builder) == schema_payload["source"]["builder_sha256"]
        ),
        "mining_builder_hash_matches": (
            _sha256(mining_builder) == mining_payload["source"]["builder_sha256"]
        ),
        "schema_detailed_table_coverage_at_least_190": table_hits >= 190,
        "all_multi_table_queries_connected": connected == multi_table,
        "no_unresolved_or_duplicate_declared_fk": True,
    }
    for db in metadata._databases.values():
        for table, info in db["tables"].items():
            keys = [
                (str(fk["column"]).casefold(), str(fk["references"]).casefold())
                for fk in info.get("foreign_keys", [])
            ]
            if len(keys) != len(set(keys)) or any(".none" in ref for _, ref in keys):
                checks["no_unresolved_or_duplicate_declared_fk"] = False
    if target == "full":
        checks["query_mining_has_validated_slots"] = (
            int(mining_payload.get("enabled_slot_count", 0)) > 0
        )
        checks["query_mining_has_deliverable_rules"] = (
            int(mining_payload.get("rule_count", 0)) > 0
        )

    return {
        "target": target,
        "passed": all(checks.values()),
        "checks": checks,
        "schema": {
            "version": schema_payload["version"],
            "artifact_sha256": _sha256(metadata.path),
            "detailed_table_coverage": f"{table_hits}/{len(rows)}",
            "table_misses": table_misses,
            "multi_table_join_graph_coverage": f"{connected}/{multi_table}",
            "selected_tables_mean": round(statistics.mean(selected_table_counts), 3),
            "selected_tables_median": statistics.median(selected_table_counts),
            "prompt_chars_mean": round(statistics.mean(prompt_chars), 1),
            "prompt_chars_median": statistics.median(prompt_chars),
            "prompt_chars_max": max(prompt_chars),
        },
        "query_mining": {
            "version": mining_payload["version"],
            "artifact_sha256": _sha256(mining.path),
            "enabled_slot_count": mining_payload.get("enabled_slot_count"),
            "rule_count": mining_payload.get("rule_count"),
            "safe_runtime_abstention": not mining.retrieve("How many records are there?"),
        },
        "note": "Gold SQL is used only for offline development diagnostics and is never written into an artifact.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("schema", "full"), default="full")
    parser.add_argument("--dataset", default="data/processed/bird_dev_500.json")
    parser.add_argument("--ids-file", default="data/processed/bird_cleancore_ids.json")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = audit(Path(args.dataset), Path(args.ids_file), args.target)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    raise SystemExit(0 if report["passed"] else 2)


if __name__ == "__main__":
    main()
