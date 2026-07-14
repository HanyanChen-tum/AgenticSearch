import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_bird_runs import build_summary, render_markdown


CLASSIFICATION_FIELDS = (
    "run_id", "id", "db_id", "difficulty", "wrong_turn",
    "error_class", "subcategory", "fix_idea", "notes",
)


class SummarizeBirdRunsTests(unittest.TestCase):
    def _write_run(self, root, name, outcomes, *, k=1):
        trace_dir = root / name
        trace_dir.mkdir()
        output_path = root / f"{name}.json"
        run_id = f"run-{name}"
        results = []
        traces = []
        failed = []
        for index, (item_id, correct) in enumerate(outcomes.items(), 1):
            sql = f"SELECT {index}"
            results.append({
                "run_id": run_id,
                "id": item_id,
                "predicted_sql": sql,
                "correct": correct,
                "latency_seconds": index,
                "llm_calls": 2,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "reasoning_tokens": 2,
                "total_tokens": 15,
                "cached_prompt_tokens": 0,
                "usage_missing_calls": 0,
                "reasoning_usage_missing_calls": 0,
            })
            traces.append({
                "run_id": run_id,
                "id": item_id,
                "final_sql": sql,
                "events": [{"tool": "db.execute"}],
            })
            if not correct:
                failed.append({
                    "run_id": run_id,
                    "id": item_id,
                    "db_id": "db",
                    "difficulty": "simple",
                    "wrong_turn": "1",
                    "error_class": "CLASS_A" if item_id == "bird_1" else "CLASS_B",
                    "subcategory": "subcategory",
                    "fix_idea": "fix",
                    "notes": "note",
                })
        output_path.write_text(json.dumps(results), encoding="utf-8")
        (trace_dir / "transcripts.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in traces),
            encoding="utf-8",
        )
        with (trace_dir / "classification_sheet.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=CLASSIFICATION_FIELDS)
            writer.writeheader()
            writer.writerows(failed)
        manifest = {
            "run_id": run_id,
            "status": "complete",
            "completed_questions": len(results),
            "config": {
                "output": str(output_path.resolve()),
                "dataset_sha256": "dataset-hash",
                "ids_file_sha256": "ids-hash",
                "planned_question_count": len(results),
                "model": "test/model",
                "k": k,
                "api_base": "https://not-written-to-summary.example",
            },
        }
        (trace_dir / "run_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return trace_dir

    def test_aggregates_accuracy_stability_transitions_and_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = [
                self._write_run(root, "one", {"bird_1": True, "bird_2": False}),
                self._write_run(root, "two", {"bird_1": False, "bird_2": False}),
                self._write_run(root, "three", {"bird_1": True, "bird_2": True}),
            ]

            summary = build_summary(runs)

            self.assertEqual(summary["run_count"], 3)
            self.assertEqual(summary["question_count"], 2)
            self.assertEqual(summary["aggregate"]["accuracy"], {
                "mean": 0.5,
                "population_stddev": 0.408248,
            })
            self.assertEqual(summary["stability"]["unstable_ids"], [
                "bird_1", "bird_2",
            ])
            self.assertEqual(summary["transitions"][0]["regressed_ids"], ["bird_1"])
            self.assertEqual(summary["transitions"][1]["recovered_ids"], [
                "bird_1", "bird_2",
            ])
            self.assertEqual(summary["error_classes"]["aggregate"], {
                "CLASS_A": 1,
                "CLASS_B": 2,
            })
            self.assertNotIn("api_base", summary["config"])
            self.assertIn("平均准确率：50.00%", render_markdown(summary))

    def test_rejects_changed_experiment_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._write_run(root, "one", {"bird_1": True})
            second = self._write_run(root, "two", {"bird_1": True}, k=3)

            with self.assertRaisesRegex(ValueError, "changed keys: .*k"):
                build_summary([first, second])
            with self.assertRaisesRegex(ValueError, "independent run_id"):
                build_summary([first, first])

    def test_allows_and_reports_explicit_config_difference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._write_run(root, "one", {"bird_1": True})
            second = self._write_run(root, "two", {"bird_1": False})
            manifest_path = second / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["config"]["evaluation_sql_timeout_seconds"] = 30.0
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            summary = build_summary(
                [first, second],
                allowed_config_differences={"evaluation_sql_timeout_seconds"},
            )

            self.assertEqual(
                summary["config_differences"]["evaluation_sql_timeout_seconds"],
                [
                    {"run_id": "run-one", "value": None},
                    {"run_id": "run-two", "value": 30.0},
                ],
            )
            self.assertIn("只能作为探索性比较", render_markdown(summary))


if __name__ == "__main__":
    unittest.main()
