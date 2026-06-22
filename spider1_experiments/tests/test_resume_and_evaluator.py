from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spider1_experiments.baselines import baseline_1_direct_llm_schema as baseline_1
from spider1_experiments.shared.evaluator import is_correct
from spider1_experiments.shared.io_utils import read_json, write_json


class MixedTypeEvaluatorTest(unittest.TestCase):
    def test_row_order_is_ignored_for_mixed_sqlite_types(self) -> None:
        answer = [["Alice", "19800101"], ["Bob", 19791231]]

        self.assertTrue(is_correct(answer, list(reversed(answer))))

    def test_value_types_and_duplicate_counts_are_preserved(self) -> None:
        self.assertFalse(is_correct([[1]], [["1"]]))
        self.assertFalse(is_correct([[1]], [[1], [1]]))


class ResumeTest(unittest.TestCase):
    def test_baseline_resumes_by_id_and_saves_each_new_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "questions.json"
            output_path = root / "results.json"
            questions = [
                {
                    "id": f"q{index}",
                    "db_id": "db",
                    "question": "question",
                    "gold_sql": "SELECT 1",
                }
                for index in range(3)
            ]
            write_json(dataset_path, questions)
            write_json(output_path, [{"id": "q0", "correct": True}])
            processed_ids: list[str] = []

            def fake_run_one(example, prompt_template, database_dir):
                processed_ids.append(example["id"])
                return {"id": example["id"], "correct": True}

            with patch.object(baseline_1, "run_one", side_effect=fake_run_one):
                results = baseline_1.run_baseline(
                    dataset_path,
                    output_path,
                    root,
                )

            self.assertEqual(processed_ids, ["q1", "q2"])
            self.assertEqual(
                [row["id"] for row in results],
                ["q0", "q1", "q2"],
            )
            self.assertEqual(read_json(output_path), results)
            self.assertFalse(
                output_path.with_name(f".{output_path.name}.tmp").exists()
            )


if __name__ == "__main__":
    unittest.main()
