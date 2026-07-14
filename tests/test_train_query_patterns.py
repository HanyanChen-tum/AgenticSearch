import json
import tempfile
import unittest
from pathlib import Path

from ours.agent.knowledge import KnowledgeAssembler
from ours.agent.query_patterns import TrainQueryPatternLibrary


class TrainQueryPatternLibraryTests(unittest.TestCase):
    def test_library_derives_only_structural_train_patterns(self):
        with tempfile.TemporaryDirectory() as directory:
            pool_path = Path(directory) / "train_pool.json"
            pool_path.write_text(json.dumps([
                {
                    "db_id": "private_train_db",
                    "question": "Unused by the pattern library",
                    "SQL": (
                        "SELECT customer_name, SUM(amount) FROM orders "
                        "WHERE status = 'paid' GROUP BY customer_name "
                        "ORDER BY SUM(amount) DESC LIMIT 1"
                    ),
                },
                {
                    "db_id": "private_train_db",
                    "question": "Unused by the pattern library",
                    "SQL": "SELECT DISTINCT city FROM customers",
                },
            ]), encoding="utf-8")

            library = TrainQueryPatternLibrary(pool_path)
            rendered = library.render()
            manifest = library.manifest()

        self.assertGreater(manifest["pattern_support"]["aggregation_grain"], 0)
        self.assertGreater(manifest["pattern_support"]["top_k"], 0)
        self.assertGreater(manifest["pattern_support"]["distinct_list"], 0)
        self.assertEqual(manifest["source_split"], "bird-train")
        self.assertEqual(len(manifest["pool_sha256"]), 64)
        self.assertEqual(len(manifest["artifact_sha256"]), 64)
        self.assertIn("Aggregate at the requested entity grain", rendered)
        self.assertNotIn("private_train_db", rendered)
        self.assertNotIn("customer_name", rendered)
        self.assertNotIn("status = 'paid'", rendered)

    def test_assembler_records_pattern_artifact_and_injects_pattern_block(self):
        assembler = KnowledgeAssembler(query_pattern_mode="train-static-v1")

        blocks = assembler.blocks("Which customer has the highest total?", "db", "")
        manifest = assembler.manifest()

        self.assertIn("TRAIN-ONLY SQL PATTERN LIBRARY", blocks["query_patterns"])
        self.assertEqual(manifest["query_pattern_mode"], "train-static-v1")
        self.assertEqual(manifest["query_patterns"]["source_split"], "bird-train")
        self.assertIsNone(manifest["retriever"])


if __name__ == "__main__":
    unittest.main()
