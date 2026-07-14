"""E3-C offline Schema/metadata retrieval and compact prompt rendering."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


SUPPORTED_METADATA_VERSIONS = {"e3-c-metadata-v2", "e3-f-schema-v3", "e3-f-schema-v4"}
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATHS = {
    "e3-c-metadata-v2": _PROJECT_ROOT / "data" / "processed" / "e3_c_metadata_v2.json",
    "e3-f-schema-v3": _PROJECT_ROOT / "data" / "processed" / "e3_f_schema_v3.json",
    "e3-f-schema-v4": _PROJECT_ROOT / "data" / "processed" / "e3_f_schema_v4.json",
}
_MAX_TABLES = 6
_MAX_COLUMNS_PER_TABLE = 12
_E3_F_MAX_TABLES = 10
_E3_F_V4_MAX_TABLES = 8
_E3_F_MAX_COLUMNS_PER_TABLE = 16
_E3_F_MAX_JOIN_EDGES = 10
_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "to", "for", "and", "or", "is", "are",
    "was", "were", "what", "which", "who", "how", "many", "much", "with", "from",
    "by", "as", "that", "this", "their", "each", "all", "show", "find", "give",
}


def _is_e3_f_version(version: str) -> bool:
    return version in {"e3-f-schema-v3", "e3-f-schema-v4"}


def _tokens(text: str) -> set[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    def normalize(token: str) -> str:
        if token.endswith("ies") and len(token) > 4:
            return token[:-3] + "y"
        if token.endswith("uses") and len(token) > 5:
            return token[:-2]
        if token.endswith(("ches", "shes", "xes", "zes")) and len(token) > 4:
            return token[:-2]
        if token.endswith("s") and len(token) > 3 and not token.endswith(("ss", "us", "is")):
            return token[:-1]
        return token
    return {
        normalize(token) for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _score(text: str, query_tokens: set[str]) -> int:
    values = _tokens(text)
    return len(values & query_tokens)


def _compact(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OfflineMetadata:
    def __init__(self, path: Path | None = None, version: str = "e3-c-metadata-v2") -> None:
        if version not in SUPPORTED_METADATA_VERSIONS:
            raise ValueError(f"Unsupported metadata version: {version!r}")
        path = path or _DEFAULT_PATHS[version]
        self.path = Path(path).resolve()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("version") != version:
            raise ValueError(f"Unsupported metadata artifact: {payload.get('version')!r}")
        self.version = version
        self._payload = payload
        self._databases: dict[str, dict[str, Any]] = payload.get("databases", {})

    def for_database(self, db_id: str) -> dict[str, Any] | None:
        return self._databases.get(db_id)

    def _select_tables(self, db: dict[str, Any], query: str) -> list[str]:
        if _is_e3_f_version(self.version):
            return self._select_tables_v3(db, query)
        tables = db.get("tables", {})
        query_tokens = _tokens(query)
        ranked: list[tuple[int, str]] = []
        for name, info in tables.items():
            searchable = [name]
            for col in info.get("columns", []):
                searchable.extend([
                    col.get("name", ""), col.get("description", ""),
                    col.get("value_description", ""),
                ])
            ranked.append((_score(" ".join(searchable), query_tokens), name))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected = [name for score, name in ranked if score > 0][:_MAX_TABLES]
        if not selected:
            selected = [name for _, name in ranked[:min(3, len(ranked))]]

        # Add one-hop FK neighbours so selected attributes remain joinable.
        neighbours: list[str] = []
        for table in selected:
            for fk in tables[table].get("foreign_keys", []):
                target = str(fk.get("references", "")).split(".", 1)[0]
                if target in tables and target not in selected and target not in neighbours:
                    neighbours.append(target)
        return (selected + neighbours)[:_MAX_TABLES]

    @staticmethod
    def _table_searchable(name: str, info: dict[str, Any], *, include_samples: bool) -> str:
        values = [name]
        for col in info.get("columns", []):
            values.extend([
                str(col.get("name", "")), str(col.get("description", "")),
                str(col.get("value_description", "")),
            ])
            if include_samples:
                values.extend(map(str, col.get("sample_values", [])[:5]))
        return " ".join(values)

    @staticmethod
    def _graph(db: dict[str, Any]) -> dict[str, set[str]]:
        graph = {table: set() for table in db.get("tables", {})}
        for edge in db.get("join_edges", []):
            left, right = edge.get("from_table"), edge.get("to_table")
            if left in graph and right in graph:
                graph[left].add(right)
                graph[right].add(left)
        return graph

    @staticmethod
    def _relevant_edges(
        db: dict[str, Any], selected_tables: list[str], query: str
    ) -> list[dict[str, Any]]:
        selected = set(selected_tables)
        query_tokens = _tokens(query)
        candidates = [
            edge for edge in db.get("join_edges", [])
            if edge.get("from_table") in selected or edge.get("to_table") in selected
        ]
        candidates.sort(key=lambda edge: (
            -int(edge.get("from_table") in selected and edge.get("to_table") in selected),
            -_score(" ".join([
                str(edge.get("from_table", "")), str(edge.get("from_column", "")),
                str(edge.get("to_table", "")), str(edge.get("to_column", "")),
            ]), query_tokens),
            -int(str(edge.get("provenance", "")).startswith("inferred")),
            str(edge.get("from_table", "")).casefold(),
            str(edge.get("from_column", "")).casefold(),
        ))
        return candidates[:_E3_F_MAX_JOIN_EDGES]

    @staticmethod
    def _shortest_path(graph: dict[str, set[str]], start: str, goal: str) -> list[str]:
        if start == goal:
            return [start]
        queue = [[start]]
        visited = {start}
        while queue:
            path = queue.pop(0)
            for neighbour in sorted(graph.get(path[-1], ()), key=str.casefold):
                if neighbour in visited:
                    continue
                candidate = path + [neighbour]
                if neighbour == goal:
                    return candidate
                visited.add(neighbour)
                queue.append(candidate)
        return []

    def _select_tables_v3(self, db: dict[str, Any], query: str) -> list[str]:
        return self._table_selection_diagnostics_v3(db, query)["selected_tables"]

    def _table_selection_diagnostics_v3(self, db: dict[str, Any], query: str) -> dict[str, Any]:
        tables = db.get("tables", {})
        query_tokens = _tokens(query)
        ranked = list(
            (
                _score(self._table_searchable(name, info, include_samples=True), query_tokens),
                name,
            )
            for name, info in tables.items()
        )
        ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
        matched_tokens = {
            name: sorted(
                _tokens(self._table_searchable(name, tables[name], include_samples=True))
                & query_tokens
            )
            for _, name in ranked
        }
        positive = [name for score, name in ranked if score > 0]
        seed_limit = 4 if self.version == "e3-f-schema-v4" else 6
        seeds = positive[:seed_limit] or [name for _, name in ranked[:3]]
        seed_mode = "positive-lexical" if positive else "zero-score-fallback"
        graph = self._graph(db)
        ordered = list(seeds)
        reasons: dict[str, list[str]] = {
            table: ["lexical_seed" if positive else "zero_score_fallback_seed"]
            for table in seeds
        }
        path_expansions = []
        neighbour_expansions = []
        fill_additions = []

        # Preserve bridge tables between the strongest lexical anchors.
        for index, left in enumerate(seeds[:4]):
            for right in seeds[index + 1:4]:
                path = self._shortest_path(graph, left, right)
                added = []
                for table in path:
                    if table not in ordered:
                        ordered.append(table)
                        added.append(table)
                    reason = f"shortest_path:{left}->{right}"
                    if reason not in reasons.setdefault(table, []):
                        reasons[table].append(reason)
                if path:
                    path_expansions.append({
                        "from_seed": left,
                        "to_seed": right,
                        "path": path,
                        "added_tables": added,
                    })

        max_tables = (
            _E3_F_V4_MAX_TABLES
            if self.version == "e3-f-schema-v4"
            else _E3_F_MAX_TABLES
        )
        # V3 expanded every neighbour. V4 adds at most one best-ranked neighbour
        # per seed and caps the detailed fragment, while other endpoints remain
        # visible through the join-edge and names-only blocks.
        if self.version == "e3-f-schema-v4":
            score_by_table = {table: score for score, table in ranked}
            for seed in list(seeds):
                if len(ordered) >= max_tables:
                    break
                candidates = sorted(
                    graph.get(seed, ()),
                    key=lambda table: (-score_by_table.get(table, 0), table.casefold()),
                )
                for neighbour in candidates:
                    if neighbour in ordered:
                        continue
                    ordered.append(neighbour)
                    reason = f"best_fk_neighbour:{seed}"
                    reasons.setdefault(neighbour, []).append(reason)
                    neighbour_expansions.append({
                        "seed": seed, "neighbour": neighbour, "added": True,
                    })
                    break
        else:
            for seed in list(seeds):
                for neighbour in sorted(graph.get(seed, ()), key=str.casefold):
                    added = neighbour not in ordered
                    if neighbour not in ordered:
                        ordered.append(neighbour)
                    reason = f"bidirectional_fk_neighbour:{seed}"
                    if reason not in reasons.setdefault(neighbour, []):
                        reasons[neighbour].append(reason)
                    neighbour_expansions.append({
                        "seed": seed,
                        "neighbour": neighbour,
                        "added": added,
                    })

        # V3 filled the entire budget, which selected every table in most small
        # databases. V4 fills only a minimum context floor; all other identifiers
        # remain available in the compact outside-detail index.
        minimum_tables = 3 if self.version == "e3-f-schema-v4" else _E3_F_MAX_TABLES
        if len(ordered) < minimum_tables:
            for _, table in ranked:
                if table not in ordered:
                    ordered.append(table)
                    reasons.setdefault(table, []).append("ranked_budget_fill")
                    fill_additions.append(table)
                if len(ordered) >= minimum_tables:
                    break
        selected = ordered[:max_tables]
        score_by_table = {table: score for score, table in ranked}
        candidates = [
            {
                "rank": rank,
                "table": table,
                "lexical_score": score,
                "matched_tokens": matched_tokens[table],
                "selected": table in selected,
                "selection_reasons": reasons.get(table, []),
                "truncation_reason": None if table in selected else "max_tables_budget",
            }
            for rank, (score, table) in enumerate(ranked, 1)
        ]
        unselected = [table for _, table in ranked if table not in selected]
        ordered_overflow = set(ordered[max_tables:])
        return {
            "query_tokens": sorted(query_tokens),
            "seed_mode": seed_mode,
            "seeds": seeds,
            "candidate_count": len(ranked),
            "candidates": candidates,
            "path_expansions": path_expansions,
            "fk_neighbour_expansions": neighbour_expansions,
            "ranked_fill_additions": fill_additions,
            "selected_tables": selected,
            "max_tables": max_tables,
            "truncated": bool(unselected),
            "truncated_tables": [
                {
                    "table": table,
                    "lexical_score": score_by_table.get(table, 0),
                    "selection_reasons": reasons.get(table, []),
                    "truncation_reason": (
                        "max_tables_budget_after_graph_expansion"
                        if table in ordered_overflow
                        else "not_reached_before_max_tables_budget"
                    ),
                }
                for table in unselected
            ],
        }

    @staticmethod
    def _rank_columns(info: dict[str, Any], query: str) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        fks = {str(fk.get("column", "")).casefold() for fk in info.get("foreign_keys", [])}
        raw = []
        for index, col in enumerate(info.get("columns", [])):
            searchable = " ".join([
                str(col.get("name", "")), str(col.get("description", "")),
                str(col.get("value_description", "")),
                " ".join(map(str, col.get("sample_values", [])[:5])),
            ])
            score = _score(searchable, query_tokens)
            is_pk = bool(col.get("primary_key"))
            is_fk = str(col.get("name", "")).casefold() in fks
            is_join_key = bool(col.get("join_key"))
            raw.append({
                "column": col,
                "original_index": index,
                "lexical_score": score,
                "matched_tokens": sorted(_tokens(searchable) & query_tokens),
                "primary_key": is_pk,
                "foreign_key": is_fk,
                "join_key": is_join_key,
            })
        return sorted(raw, key=lambda item: (
            -int(item["primary_key"] or item["foreign_key"] or item["join_key"]),
            -item["lexical_score"],
            item["original_index"],
        ))

    def _column_selection_diagnostics(self, info: dict[str, Any], query: str) -> dict[str, Any]:
        ranked = self._rank_columns(info, query)
        limit = _E3_F_MAX_COLUMNS_PER_TABLE if _is_e3_f_version(self.version) else _MAX_COLUMNS_PER_TABLE
        selected = ranked[:limit]
        candidates = []
        for rank, item in enumerate(ranked, 1):
            reasons = []
            if item["primary_key"]:
                reasons.append("primary_key")
            if item["foreign_key"]:
                reasons.append("foreign_key")
            if item["join_key"] and not item["foreign_key"]:
                reasons.append("join_key")
            if item["lexical_score"] > 0:
                reasons.append("lexical_match")
            if rank <= limit and not reasons:
                reasons.append("ranked_budget_fill")
            candidates.append({
                "rank": rank,
                "column": str(item["column"]["name"]),
                "lexical_score": item["lexical_score"],
                "matched_tokens": item["matched_tokens"],
                "primary_key": item["primary_key"],
                "foreign_key": item["foreign_key"],
                "join_key": item["join_key"],
                "selected": rank <= limit,
                "selection_reasons": reasons,
                "truncation_reason": None if rank <= limit else "max_columns_per_table_budget",
            })
        return {
            "selected_columns": [str(item["column"]["name"]) for item in selected],
            "candidates": candidates,
            "max_columns": limit,
            "truncated": len(ranked) > limit,
            "omitted_count": max(0, len(ranked) - limit),
        }

    def _select_columns(self, info: dict[str, Any], query: str) -> list[dict[str, Any]]:
        if _is_e3_f_version(self.version):
            selected_names = self._column_selection_diagnostics(info, query)["selected_columns"]
            by_name = {str(column["name"]): column for column in info.get("columns", [])}
            return [by_name[name] for name in selected_names]
        query_tokens = _tokens(query)
        fks = {str(fk.get("column", "")) for fk in info.get("foreign_keys", [])}
        ranked = []
        for index, col in enumerate(info.get("columns", [])):
            searchable = " ".join([
                col.get("name", ""), col.get("description", ""),
                col.get("value_description", ""),
            ])
            structural = bool(col.get("primary_key") or col.get("name") in fks)
            ranked.append((_score(searchable, query_tokens), structural, -index, col))
        ranked.sort(key=lambda item: (-item[0], -int(item[1]), -item[2]))
        limit = _E3_F_MAX_COLUMNS_PER_TABLE if _is_e3_f_version(self.version) else _MAX_COLUMNS_PER_TABLE
        return [item[3] for item in ranked[:limit]]

    def render(self, db_id: str, *, question: str = "", evidence: str = "") -> str:
        db = self.for_database(db_id)
        if not db:
            return ""
        query = f"{question}\n{evidence}"
        selected_tables = self._select_tables(db, query)
        tables = db.get("tables", {})
        all_tables = list(tables)
        label = (
            "SCHEMA V4" if self.version == "e3-f-schema-v4"
            else "E3-F" if self.version == "e3-f-schema-v3" else "E3-C"
        )
        lines = [
            f"\nOFFLINE SCHEMA CONTEXT ({label}, retrieved before the run):",
            "The runtime full Schema is intentionally omitted. Use this retrieved fragment and verify uncertain values with db.sample_values.",
            "RETRIEVED TABLES: " + ", ".join(selected_tables),
        ]
        if self.version == "e3-f-schema-v3":
            lines.insert(2, "DATABASE TABLE DIRECTORY: " + ", ".join(all_tables))
            lines.append("COMPLETE COMPACT SCHEMA INDEX (names only; detailed metadata follows):")
            for table, info in tables.items():
                column_names = ", ".join(str(column["name"]) for column in info.get("columns", []))
                lines.append(f"  - {table}({column_names})")
        elif self.version == "e3-f-schema-v4":
            outside = [table for table in all_tables if table not in selected_tables]
            if outside:
                lines.append("SCHEMA IDENTIFIERS OUTSIDE DETAILED TABLES (names only):")
                for table in outside:
                    column_names = ", ".join(
                        str(column["name"]) for column in tables[table].get("columns", [])
                    )
                    lines.append(f"  - {table}({column_names})")
        for table in selected_tables:
            info = tables[table]
            row_count = info.get("row_count")
            suffix = f"; rows={row_count}" if row_count is not None else ""
            lines.append(f"- TABLE {table}{suffix}:")
            columns = self._select_columns(info, query)
            for col in columns:
                flags = []
                if col.get("primary_key"):
                    flags.append("PK")
                if col.get("not_null"):
                    flags.append("NOT NULL")
                if col.get("join_key") and not col.get("primary_key"):
                    flags.append("JOIN KEY")
                flag_text = f"; {','.join(flags)}" if flags else ""
                bits = [f"{col['name']} ({col.get('type', 'TEXT')}){flag_text}"]
                if col.get("description"):
                    bits.append(f"meaning={_compact(col['description'], 140)}")
                if col.get("value_description"):
                    bits.append(f"values={_compact(col['value_description'], 100)}")
                elif col.get("sample_values"):
                    bits.append("examples=" + _compact(", ".join(map(str, col["sample_values"][:2])), 100))
                if self.version == "e3-f-schema-v4" and _score(
                    " ".join([
                        str(col.get("name", "")), str(col.get("description", "")),
                        str(col.get("value_description", "")),
                    ]),
                    _tokens(query),
                ) > 0:
                    profile = col.get("profile") or {}
                    if profile.get("null_fraction", 0) > 0:
                        bits.append(f"null_fraction={profile['null_fraction']}")
                    if profile.get("min_value") is not None or profile.get("max_value") is not None:
                        bits.append(
                            "range=" + _compact(
                                f"{profile.get('min_value')}..{profile.get('max_value')}", 80
                            )
                        )
                lines.append("  - " + "; ".join(bits))
            omitted = len(info.get("columns", [])) - len(columns)
            if omitted > 0:
                if self.version == "e3-f-schema-v4":
                    chosen = {str(column["name"]) for column in columns}
                    omitted_names = [
                        str(column["name"]) for column in info.get("columns", [])
                        if str(column["name"]) not in chosen
                    ]
                    lines.append(
                        f"  - [{omitted} lower-relevance columns names only: "
                        + ", ".join(omitted_names) + "]"
                    )
                else:
                    lines.append(f"  - [{omitted} lower-relevance columns omitted]")
            for fk in ([] if self.version == "e3-f-schema-v4" else info.get("foreign_keys", [])):
                cardinality = fk.get("cardinality") or fk.get("relationship")
                relation = f"; {cardinality}" if cardinality else ""
                lines.append(f"  - FK {table}.{fk['column']} -> {fk['references']}{relation}")
        if _is_e3_f_version(self.version):
            relevant_edges = self._relevant_edges(db, selected_tables, query)
            if relevant_edges:
                lines.append("JOIN GRAPH EDGES AROUND RETRIEVED TABLES:")
                for edge in relevant_edges:
                    nullable = "; nullable" if edge.get("nullable") else ""
                    provenance = edge.get("provenance", "declared_foreign_key")
                    coverage = edge.get("referential_coverage")
                    coverage_text = f"; key_coverage={coverage}" if coverage is not None else ""
                    fanout = edge.get("max_child_rows_per_key")
                    fanout_text = f"; max_child_rows_per_key={fanout}" if fanout is not None else ""
                    lines.append(
                        f"  - {edge['from_table']}.{edge['from_column']} = "
                        f"{edge['to_table']}.{edge['to_column']} "
                        f"[{edge['cardinality']}; {provenance}{nullable}"
                        f"{coverage_text}{fanout_text}]"
                    )
        return "\n".join(lines) + "\n"

    def selection_manifest(self, db_id: str, *, question: str = "", evidence: str = "") -> dict[str, Any]:
        db = self.for_database(db_id)
        if not db:
            return {"database": db_id, "found": False}
        query = f"{question}\n{evidence}"
        if _is_e3_f_version(self.version):
            table_diagnostics = self._table_selection_diagnostics_v3(db, query)
            tables = table_diagnostics["selected_tables"]
            column_diagnostics = {
                table: self._column_selection_diagnostics(db["tables"][table], query)
                for table in tables
            }
            selected_set = set(tables)
            fk_edges = []
            for edge in self._relevant_edges(db, tables, query):
                fk_edges.append({
                    "from_table": edge["from_table"],
                    "from_column": edge["from_column"],
                    "to_table": edge["to_table"],
                    "to_column": edge["to_column"],
                    "cardinality": edge["cardinality"],
                    "nullable": edge.get("nullable", False),
                    "provenance": edge.get("provenance", "declared_foreign_key"),
                    "confidence": edge.get("confidence"),
                    "referential_coverage": edge.get("referential_coverage"),
                    "max_child_rows_per_key": edge.get("max_child_rows_per_key"),
                    "both_endpoint_tables_selected": (
                        edge["from_table"] in selected_set
                        and edge["to_table"] in selected_set
                    ),
                    "inclusion_reason": "incident_to_selected_table",
                })
            return {
                "database": db_id,
                "found": True,
                "artifact_version": self.version,
                "table_selection": table_diagnostics,
                "column_selection": column_diagnostics,
                "fk_edges": fk_edges,
                "complete_compact_schema_index": True,
                "truncation_summary": {
                    "tables_truncated": table_diagnostics["truncated"],
                    "table_count_omitted_from_detailed_context": len(table_diagnostics["truncated_tables"]),
                    "columns_truncated_by_table": {
                        table: diagnostics["omitted_count"]
                        for table, diagnostics in column_diagnostics.items()
                        if diagnostics["truncated"]
                    },
                    "identifier_availability_after_truncation": (
                        "selected tables retain omitted column names; unselected tables remain in names-only index"
                        if self.version == "e3-f-schema-v4"
                        else "all table/column names remain in compact index"
                    ),
                },
            }
        tables = self._select_tables(db, query)
        return {
            "database": db_id,
            "found": True,
            "artifact_version": self.version,
            "tables": tables,
            "columns": {
                table: [str(column["name"]) for column in self._select_columns(db["tables"][table], query)]
                for table in tables
            },
            "complete_compact_schema_index": _is_e3_f_version(self.version),
        }

    def manifest(self) -> dict[str, Any]:
        return {
            "version": self._payload["version"],
            "path": str(self.path),
            "artifact_sha256": _sha256(self.path),
            "runtime_sha256": _sha256(Path(__file__)),
            "source": self._payload.get("source"),
            "build_config": self._payload.get("build_config"),
            "database_count": len(self._databases),
            "retrieval": {
                "mode": (
                    "deterministic-lexical-plus-bidirectional-fk-shortest-path"
                    if _is_e3_f_version(self.version)
                    else "deterministic-lexical-plus-fk-neighbours"
                ),
                "max_tables": (
                    _E3_F_V4_MAX_TABLES
                    if self.version == "e3-f-schema-v4"
                    else _E3_F_MAX_TABLES if _is_e3_f_version(self.version) else _MAX_TABLES
                ),
                "max_columns_per_table": (
                    _E3_F_MAX_COLUMNS_PER_TABLE
                    if _is_e3_f_version(self.version) else _MAX_COLUMNS_PER_TABLE
                ),
                "complete_compact_schema_index": _is_e3_f_version(self.version),
            },
        }


def get_offline_metadata(
    version: str = "e3-c-metadata-v2", path: Path | None = None
) -> OfflineMetadata:
    return OfflineMetadata(path, version=version)
