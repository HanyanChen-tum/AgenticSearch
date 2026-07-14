import json
import tempfile
import unittest
from pathlib import Path

from ours.agent.config import get_agent_config
from ours.agent.knowledge import KnowledgeAssembler
from ours.agent.offline_metadata import get_offline_metadata
from ours.agent.query_mining import get_mined_query_patterns
from scripts.build_e3_f_query_mining import build as build_query_mining
from scripts.analyze_e3_f_retrieval import build_rows as build_retrieval_audit_rows
from scripts.run_bird_train_fewshot import (
    _offline_metadata_manifest,
    _query_pattern_manifest,
)


class E3FSetupTests(unittest.TestCase):
    def test_profile_is_complete_offline_plus_few_shot(self):
        config = get_agent_config("e3-f")
        self.assertEqual(config.few_shot_mode, "train-retrieval")
        self.assertEqual(config.query_pattern_mode, "train-mined-v2")
        self.assertEqual(config.offline_metadata_mode, "e3-f-schema-v4")
        self.assertEqual(config.schema_context_mode, "offline-retrieval")
        self.assertTrue(config.capability_gate)
        self.assertEqual(config.allowed_db_methods, ("execute", "sample_values"))

    def test_prompt_blocks_use_mined_patterns_and_repaired_schema(self):
        config = get_agent_config("e3-f")
        assembler = KnowledgeAssembler(
            query_pattern_mode=config.query_pattern_mode,
            offline_metadata_mode=config.offline_metadata_mode,
        )
        blocks = assembler.blocks(
            "What is the highest monthly consumption in 2012?",
            "debit_card_specializing",
            "",
        )
        self.assertEqual(blocks["query_patterns"], "")
        self.assertNotIn("TRAIN-ONLY SQL PATTERN LIBRARY", blocks["query_patterns"])
        self.assertIn("OFFLINE SCHEMA CONTEXT (SCHEMA V4", blocks["offline_metadata"])
        self.assertIn("JOIN GRAPH EDGES", blocks["offline_metadata"])
        self.assertIn("key_coverage=", blocks["offline_metadata"])
        self.assertNotIn(".None", blocks["offline_metadata"])
        selection = assembler.selection_manifest(
            "What is the highest monthly consumption in 2012?",
            "debit_card_specializing",
            "",
        )
        mining = selection["query_patterns"]
        self.assertTrue(mining["abstained"])
        self.assertEqual(mining["selected_constraints"], [])
        self.assertTrue(all(not slot["enabled"] for slot in mining["slots"]))
        schema = selection["offline_schema"]
        self.assertIn("yearmonth", schema["table_selection"]["selected_tables"])
        self.assertIn("candidates", schema["table_selection"])
        self.assertIn("path_expansions", schema["table_selection"])
        self.assertIn("fk_neighbour_expansions", schema["table_selection"])
        self.assertIn("yearmonth", schema["column_selection"])
        self.assertIn("selection_reasons", schema["column_selection"]["yearmonth"]["candidates"][0])
        self.assertIn("truncation_summary", schema)
        self.assertGreater(len(schema["fk_edges"]), 0)

    def test_schema_artifact_foreign_keys_are_resolved_and_unique(self):
        metadata = get_offline_metadata("e3-f-schema-v4")
        for db in metadata._databases.values():
            tables = db["tables"]
            table_lookup = {name.casefold(): name for name in tables}
            for table, info in tables.items():
                keys = []
                for fk in info.get("foreign_keys", []):
                    self.assertNotIn(".None", fk["references"])
                    target_name, target_column = fk["references"].split(".", 1)
                    canonical = table_lookup[target_name.casefold()]
                    columns = {str(col["name"]).casefold() for col in tables[canonical]["columns"]}
                    self.assertIn(target_column.casefold(), columns)
                    keys.append((fk["column"].casefold(), fk["references"].casefold()))
                self.assertEqual(len(keys), len(set(keys)), table)
            for edge in db["join_edges"]:
                self.assertIn(edge["provenance"], {
                    "declared_foreign_key", "inferred_name_and_value_overlap",
                })
                self.assertGreaterEqual(edge["referential_coverage"], 0)

    def test_manifests_freeze_both_artifacts(self):
        patterns = _query_pattern_manifest(get_agent_config("e3-f"))
        schema = _offline_metadata_manifest(get_agent_config("e3-f"))
        self.assertEqual(patterns["version"], "train-mined-v2")
        self.assertEqual(schema["version"], "e3-f-schema-v4")
        self.assertEqual(len(patterns["artifact_sha256"]), 64)
        self.assertEqual(len(schema["artifact_sha256"]), 64)
        self.assertEqual(patterns["parsed_sql_count"], 9428)
        self.assertEqual(patterns["enabled_slot_count"], 0)
        self.assertFalse(patterns["retrieval"]["forced_fallback"])
        self.assertTrue(schema["retrieval"]["complete_compact_schema_index"])
        self.assertGreater(schema["source"]["file_count"], 0)

    def test_query_mining_builder_stores_abstract_cards_not_raw_sql(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool = root / "train.json"
            output = root / "artifact.json"
            output_2 = root / "artifact-2.json"
            raw_sql = "SELECT secret_customer FROM secret_orders ORDER BY amount DESC LIMIT 1"
            pool.write_text(json.dumps([{
                "db_id": "private_train_db",
                "question": "Which customer has the highest amount?",
                "SQL": raw_sql,
            }]), encoding="utf-8")
            artifact = build_query_mining(pool, output)
            build_query_mining(pool, output_2)
            rendered = output.read_text(encoding="utf-8")
            self.assertEqual(output.read_bytes(), output_2.read_bytes())
        self.assertEqual(artifact["parsed_sql_count"], 1)
        self.assertFalse(artifact["build_config"]["stores_raw_sql"])
        self.assertNotIn(raw_sql, rendered)
        self.assertNotIn("secret_customer", rendered)
        self.assertNotIn("secret_orders", rendered)

    def test_mined_retrieval_is_deterministic(self):
        library = get_mined_query_patterns()
        first = library.retrieve("Which school has the highest average score?")
        second = library.retrieve("Which school has the highest average score?")
        self.assertEqual(first, second)
        self.assertEqual(first, [])
        self.assertTrue(library.retrieval_diagnostics(
            "Which school has the highest average score?"
        )["abstained"])

    def test_retrieval_audit_joins_selection_and_sql_adherence(self):
        config = get_agent_config("e3-f")
        assembler = KnowledgeAssembler(
            query_pattern_mode=config.query_pattern_mode,
            offline_metadata_mode=config.offline_metadata_mode,
        )
        selection = assembler.selection_manifest(
            "What is the highest monthly consumption in 2012?",
            "debit_card_specializing",
            "",
        )
        sql = (
            "SELECT SUM(Consumption) FROM yearmonth "
            "WHERE SUBSTR(Date, 1, 4) = '2012' GROUP BY SUBSTR(Date, 5, 2) "
            "ORDER BY SUM(Consumption) DESC LIMIT 1"
        )
        rows = build_retrieval_audit_rows(
            [{
                "id": "bird_test",
                "db_id": "debit_card_specializing",
                "difficulty": "simple",
                "correct": True,
                "predicted_sql": sql,
                "gold_sql": sql,
            }],
            [{"id": "bird_test", "knowledge_selection": selection}],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["diagnostic"], "correct")
        self.assertEqual(rows[0]["gold_detail_table_misses"], [])
        self.assertIn("yearmonth", rows[0]["schema_selected_tables"])
        self.assertTrue(rows[0]["mining_abstained"])


if __name__ == "__main__":
    unittest.main()
