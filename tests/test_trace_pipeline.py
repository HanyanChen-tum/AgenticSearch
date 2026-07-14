import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path

from ours.db_environment import DBEnvironment
from ours.recursive_db_rlm import DBRLM
from scripts.make_classification_sheet import classify_failure
from scripts.run_bird_train_fewshot import _prepare_run
from shared.trace_io import TRACE_SCHEMA_VERSION, validate_run_pair
from shared.sql_executor import DEFAULT_QUERY_TIMEOUT_SECONDS


ROOT = Path(__file__).resolve().parents[1]


class TracePipelineTests(unittest.TestCase):
    def test_evaluation_timeout_is_part_of_the_experiment_config(self):
        self.assertEqual(DEFAULT_QUERY_TIMEOUT_SECONDS, 30.0)

    def test_run_manifest_is_reused_only_for_same_config(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            manifest_path = directory / "run_manifest.json"
            output_path = directory / "results.json"
            transcript_path = directory / "transcripts.jsonl"
            run_id, _ = _prepare_run(
                manifest_path,
                output_path,
                transcript_path,
                {"model": "test"},
            )
            resumed_id, _ = _prepare_run(
                manifest_path,
                output_path,
                transcript_path,
                {"model": "test"},
            )
            self.assertEqual(run_id, resumed_id)
            with self.assertRaisesRegex(
                ValueError,
                "different configuration.*Changed fields: model",
            ):
                _prepare_run(
                    manifest_path,
                    output_path,
                    transcript_path,
                    {"model": "changed"},
                )

    def test_run_manifest_rejects_older_trace_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            manifest_path = directory / "run_manifest.json"
            manifest_path.write_text(json.dumps({
                "trace_schema_version": TRACE_SCHEMA_VERSION - 1,
                "run_id": "old-run",
                "config": {"model": "test"},
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "older schema"):
                _prepare_run(
                    manifest_path,
                    directory / "results.json",
                    directory / "transcripts.jsonl",
                    {"model": "test"},
                )

    def test_agent_snapshot_contains_final_message_and_tool_event(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("CREATE TABLE items (name TEXT)")
                connection.execute("INSERT INTO items VALUES ('alpha')")
                connection.commit()
            agent = DBRLM(model="test/model", max_iterations=3)
            responses = [
                '"""python\nprint(db.execute("SELECT name FROM items"))\n"""',
                'FINAL("SELECT name FROM items")',
            ]
            responses[0] = responses[0].replace('"""', chr(96) * 3)

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            sql = agent.complete_sql("List item names.", db_path)
            snapshot = agent.trace_snapshot()

            self.assertEqual(sql, "SELECT name FROM items")
            self.assertEqual(snapshot["events"][0]["tool"], "db.execute")
            self.assertEqual(snapshot["events"][0]["result"]["rows"], [["alpha"]])
            self.assertEqual(snapshot["messages"][-1]["role"], "assistant")
            self.assertIn("FINAL", snapshot["messages"][-1]["content"])

    def test_db_environment_emits_separate_structured_events(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "test.sqlite"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("CREATE TABLE items (id INTEGER, name TEXT)")
                connection.execute("INSERT INTO items VALUES (1, 'alpha')")
                connection.commit()
            events = []
            environment = DBEnvironment(
                db_path,
                event_sink=lambda tool, arguments, result: events.append(
                    (tool, arguments, result)
                ),
            )
            missing = environment.sample_values("items", "missing")
            selected = environment.execute("SELECT name FROM items")

            self.assertIn("not found", missing["error"])
            self.assertEqual(selected["rows"], [["alpha"]])
            self.assertEqual([event[0] for event in events], [
                "db.sample_values",
                "db.execute",
            ])
            self.assertEqual(events[1][1]["sql"], "SELECT name FROM items")

    def test_structured_events_do_not_share_one_observation(self):
        final_sql = "SELECT missing FROM items"
        transcript = {
            "messages": [
                {"role": "assistant", "content": f'FINAL("{final_sql}")'},
            ],
            "events": [
                {
                    "turn": 1,
                    "tool": "db.execute",
                    "arguments": {"sql": "SELECT name FROM items"},
                    "result": {"rows": [["alpha"]], "error": None},
                },
                {
                    "turn": 1,
                    "tool": "db.execute",
                    "arguments": {"sql": final_sql},
                    "result": {"rows": [], "error": "no such column: missing"},
                },
            ],
        }
        result = {
            "predicted_sql": final_sql,
            "gold_sql": "SELECT name FROM items",
        }
        classified = classify_failure(result, transcript)
        self.assertEqual(classified["error_class"], "SCHEMA_LINKING")

    def test_run_pair_rejects_run_id_and_sql_mismatches(self):
        result = {
            "run_id": "run-a",
            "id": "bird_1",
            "predicted_sql": "SELECT 1",
        }
        wrong_run = {
            "run_id": "run-b",
            "id": "bird_1",
            "final_sql": "SELECT 1",
        }
        with self.assertRaisesRegex(ValueError, "run_id mismatch"):
            validate_run_pair([result], [wrong_run])

        wrong_sql = {
            "run_id": "run-a",
            "id": "bird_1",
            "final_sql": "SELECT 2",
        }
        with self.assertRaisesRegex(ValueError, "final SQL mismatch"):
            validate_run_pair([result], [wrong_sql])

    def test_cli_generates_filled_csv_and_html_for_one_run(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            results_path = directory / "results.json"
            traces_path = directory / "transcripts.jsonl"
            csv_path = directory / "classification.csv"
            html_path = directory / "report.html"
            result = {
                "trace_schema_version": 2,
                "run_id": "run-test",
                "id": "bird_1",
                "db_id": "test_db",
                "difficulty": "simple",
                "question": "List the name and street.",
                "predicted_sql": "SELECT name FROM schools",
                "predicted_answer": [["A"]],
                "gold_sql": "SELECT name, street FROM schools",
                "gold_answer": [["A", "Road"]],
                "correct": False,
                "llm_calls": 2,
            }
            trace = {
                "trace_schema_version": 2,
                "run_id": "run-test",
                "id": "bird_1",
                "db_id": "test_db",
                "question": result["question"],
                "final_sql": result["predicted_sql"],
                "messages": [
                    {"role": "user", "content": "QUESTION"},
                    {"role": "assistant", "content": 'FINAL("SELECT name FROM schools")'},
                ],
                "events": [{
                    "turn": 1,
                    "tool": "db.execute",
                    "arguments": {"sql": result["predicted_sql"]},
                    "result": {"columns": ["name"], "rows": [["A"]], "error": None},
                }],
            }
            results_path.write_text(json.dumps([result]), encoding="utf-8")
            traces_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")

            subprocess.run([
                sys.executable,
                str(ROOT / "scripts/make_classification_sheet.py"),
                "--results", str(results_path),
                "--transcripts", str(traces_path),
                "--out", str(csv_path),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            subprocess.run([
                sys.executable,
                str(ROOT / "scripts/render_traces.py"),
                "--results", str(results_path),
                "--transcripts", str(traces_path),
                "--out", str(html_path),
            ], cwd=ROOT, check=True, capture_output=True, text=True)

            with csv_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["run_id"], "run-test")
            self.assertEqual(rows[0]["error_class"], "OUTPUT_CONTRACT")
            self.assertTrue(all(rows[0][field] for field in (
                "wrong_turn", "subcategory", "fix_idea", "notes",
            )))
            self.assertIn("run-test", html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
