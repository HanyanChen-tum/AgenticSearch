import json
import tempfile
import unittest
from pathlib import Path

from ours.train_few_shot_retriever import (
    _POOL_PATH,
    _load_examples,
    get_train_retriever_manifest,
)


class TrainFewShotRetrieverTests(unittest.TestCase):
    def test_default_train_pool_exists_and_has_expected_size(self):
        examples = _load_examples(_POOL_PATH)

        self.assertEqual(len(examples), 9428)
        self.assertTrue(examples[0]["question"])
        self.assertTrue(examples[0]["gold_sql"])

    def test_load_examples_normalizes_official_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "train.json"
            path.write_text(json.dumps([{
                "db_id": "db",
                "question": "How many rows?",
                "evidence": "Use the records table.",
                "SQL": "SELECT COUNT(*) FROM records",
            }]), encoding="utf-8")

            examples = _load_examples(path)

        self.assertEqual(examples, [{
            "train_index": 0,
            "example_id": "train-0",
            "db_id": "db",
            "question": "How many rows?",
            "evidence": "Use the records table.",
            "gold_sql": "SELECT COUNT(*) FROM records",
        }])

    def test_missing_pool_has_actionable_error(self):
        with self.assertRaisesRegex(FileNotFoundError, "data/train_pool.json"):
            _load_examples(Path("missing-train-pool.json"))

    def test_manifest_does_not_require_loading_the_embedding_model(self):
        manifest = get_train_retriever_manifest()

        self.assertEqual(manifest["source_split"], "bird-train")
        self.assertEqual(manifest["example_count"], 9428)
        self.assertEqual(manifest["embedding_model"], "all-MiniLM-L6-v2")
        self.assertEqual(len(manifest["pool_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
