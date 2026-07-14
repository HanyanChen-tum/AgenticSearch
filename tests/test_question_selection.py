import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_bird_train_fewshot import _load_question_ids, _select_questions


class QuestionSelectionTests(unittest.TestCase):
    def test_grouped_ids_default_to_all_groups_and_preserve_dataset_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ids.json"
            path.write_text(json.dumps({
                "both_wrong": ["bird_3", "bird_1"],
                "canary": ["bird_2"],
            }), encoding="utf-8")

            ids, groups = _load_question_ids(path)
            selected = _select_questions([
                {"id": "bird_1"},
                {"id": "bird_2"},
                {"id": "unrelated", "value": "same"},
                {"id": "unrelated", "value": "same"},
                {"id": "bird_3"},
                {"id": "bird_4"},
            ], ids)

            self.assertEqual(groups, ["both_wrong", "canary"])
            self.assertEqual([item["id"] for item in selected], [
                "bird_1", "bird_2", "bird_3",
            ])

    def test_named_group_can_be_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ids.json"
            path.write_text(json.dumps({
                "core": ["bird_1"],
                "canary": ["bird_2"],
            }), encoding="utf-8")

            ids, groups = _load_question_ids(path, ["canary"])

            self.assertEqual(ids, ["bird_2"])
            self.assertEqual(groups, ["canary"])

    def test_invalid_ids_fail_instead_of_changing_the_experiment_set(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ids.json"
            path.write_text(json.dumps({
                "first": ["bird_1"],
                "second": ["bird_1"],
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Duplicate question IDs"):
                _load_question_ids(path)
            with self.assertRaisesRegex(ValueError, "absent from dataset"):
                _select_questions([{"id": "bird_1"}], ["bird_2"])

    def test_identical_requested_duplicates_are_selected_once(self):
        duplicate = {"id": "bird_1", "question": "same"}
        selected = _select_questions([duplicate, dict(duplicate)], ["bird_1"])
        self.assertEqual(selected, [duplicate])

        with self.assertRaisesRegex(ValueError, "conflicting records"):
            _select_questions([
                {"id": "bird_1", "question": "first"},
                {"id": "bird_1", "question": "second"},
            ], ["bird_1"])


if __name__ == "__main__":
    unittest.main()
