from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ours.db_environment import DatabaseEnvironment
from ours.recursive_controller import RecursionConfig
from ours.recursive_db_rlm import RecursiveDBRLM, run_one
from shared.llm_client import LLMResponse


class QueuedLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str, system_instruction: str) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(
            text=next(self.responses),
            input_tokens=10,
            output_tokens=2,
        )


class RecursiveDBRLMTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database_dir = root / "databases"
        db_dir = self.database_dir / "company"
        db_dir.mkdir(parents=True)
        self.db_path = db_dir / "company.sqlite"

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE departments (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                );
                CREATE TABLE employees (
                    id INTEGER PRIMARY KEY,
                    department_id INTEGER NOT NULL,
                    salary INTEGER NOT NULL,
                    FOREIGN KEY (department_id) REFERENCES departments(id)
                );
                INSERT INTO departments VALUES (1, 'Engineering'), (2, 'Sales');
                INSERT INTO employees VALUES
                    (1, 1, 100),
                    (2, 1, 200),
                    (3, 2, 50);
                """
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_database_environment_is_bounded_and_read_only(self) -> None:
        environment = DatabaseEnvironment(self.db_path, max_rows=2)

        self.assertEqual(
            environment.list_tables()["tables"],
            ["departments", "employees"],
        )
        description = environment.describe_table("employees")
        self.assertEqual(description["foreign_keys"][0]["to_table"], "departments")

        result = environment.execute_sql("SELECT id FROM employees ORDER BY id")
        self.assertEqual(result["rows"], [[1], [2]])
        self.assertTrue(result["truncated"])
        full_result = environment.execute_sql_full(
            "SELECT id FROM employees ORDER BY id"
        )
        self.assertEqual(full_result["rows"], [[1], [2], [3]])
        self.assertFalse(full_result["truncated"])

        rejected = environment.execute_sql("DELETE FROM employees")
        self.assertIn("read-only", rejected["error"])
        count = environment.execute_sql("SELECT COUNT(*) FROM employees")
        self.assertEqual(count["rows"], [[3]])

    def test_recursive_agent_spawns_child_and_synthesizes_sql(self) -> None:
        final_sql = (
            "SELECT d.name, AVG(e.salary) "
            "FROM departments d JOIN employees e ON d.id = e.department_id "
            "GROUP BY d.id ORDER BY AVG(e.salary) DESC LIMIT 1"
        )
        llm = QueuedLLM(
            [
                '{"action":"list_tables","arguments":{}}',
                (
                    '{"action":"spawn_subagent","arguments":'
                    '{"task":"Inspect employee salary and department linkage"}}'
                ),
                (
                    '{"action":"describe_table","arguments":'
                    '{"table":"employees"}}'
                ),
                (
                    '{"action":"finish","arguments":'
                    '{"summary":"employees.department_id links salaries to departments",'
                    '"candidate_sql":""}}'
                ),
                (
                    '{"action":"execute_sql","arguments":{"sql":'
                    + json.dumps(final_sql)
                    + "}}"
                ),
                (
                    '{"action":"finish","arguments":'
                    '{"summary":"Engineering has the highest average salary",'
                    '"candidate_sql":'
                    + json.dumps(final_sql)
                    + "}}"
                ),
                final_sql,
            ]
        )
        method = RecursiveDBRLM(
            self.db_path,
            "Choose one action.",
            recursion_config=RecursionConfig(
                max_depth=1,
                max_actions=10,
                max_actions_per_agent=6,
                max_children_per_agent=1,
                token_budget=1000,
            ),
            llm=llm,
        )

        result = method.solve("Which department has the highest average salary?")

        self.assertEqual(result["predicted_answer"], [["Engineering", 150.0]])
        self.assertEqual(result["max_depth_reached"], 1)
        self.assertEqual(result["actions_used"], 6)
        self.assertEqual(len(result["root_result"]["children"]), 1)
        self.assertTrue(
            any(event["action"] == "spawn_subagent" for event in result["trace"])
        )

    def test_run_one_matches_unified_result_format(self) -> None:
        sql = "SELECT COUNT(*) FROM employees"
        llm = QueuedLLM(
            [
                (
                    '{"action":"finish","arguments":'
                    '{"summary":"Use employees count","candidate_sql":'
                    + json.dumps(sql)
                    + "}}"
                ),
                sql,
            ]
        )
        example = {
            "id": "q1",
            "db_id": "company",
            "question": "How many employees are there?",
            "gold_sql": sql,
        }

        result = run_one(
            example,
            "Choose one action.",
            self.database_dir,
            RecursionConfig(
                max_depth=0,
                max_actions=2,
                max_actions_per_agent=2,
                token_budget=1000,
            ),
            llm=llm,
        )

        self.assertTrue(result["correct"])
        self.assertEqual(result["method"], "ours_recursive_db_rlm")
        self.assertEqual(result["predicted_answer"], [[3]])
        self.assertIn("recursive_result", result)
        self.assertIn("trace", result)


if __name__ == "__main__":
    unittest.main()
