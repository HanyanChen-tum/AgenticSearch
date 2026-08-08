import json
import sqlite3
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path

from ours.agent.config import get_agent_config
from ours.agent.query_plan import parse_initial_plan, parse_revision
from ours.recursive_db_rlm import DBRLM


def plan_block() -> str:
    plan = {
        "target_entity": "item",
        "grain": "one row per item",
        "schema_links": ["items.name"],
        "required_tables": ["items"],
        "joins": [],
        "filters": [],
        "group_by": [],
        "aggregates": [],
        "aggregation_scope": "none",
        "aggregation_justification": None,
        "having": [],
        "order_by": [],
        "limit": None,
        "answer_type": "rows",
        "answer_scope": "per_entity_rows",
        "output_columns": [{
            "position": 1,
            "semantic_item": "item name",
            "source_columns": ["items.name"],
            "sql_expression": "items.name",
            "source_justification": "The question asks for item names.",
            "aggregation": "none",
        }],
        "candidate_purpose": "answer",
        "expected_result_shape": {
            "answer_type": "rows",
            "column_count": 1,
            "row_grain": "one row per item",
        },
        "unresolved_assumptions": [],
        "revision": None,
    }
    return "```queryplan\n" + json.dumps(plan) + "\n```"


def revision_block(observation_ref: int) -> str:
    revision = {
        "observation_ref": observation_ref,
        "changed_constraints": [],
        "updated_fields": {},
        "reason": "The observation supports the existing answer plan.",
        "candidate_purpose": "answer",
    }
    return "```plan-revision\n" + json.dumps(revision) + "\n```"


class QueryPlanProtocolTests(unittest.TestCase):
    @staticmethod
    def make_database(directory: str) -> Path:
        path = Path(directory) / "items.sqlite"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE items (name TEXT)")
            connection.execute("INSERT INTO items VALUES ('alpha')")
            connection.commit()
        return path

    def test_initial_and_revision_schema_are_parseable(self):
        initial, errors = parse_initial_plan(plan_block())
        self.assertFalse(errors)
        self.assertEqual(initial["expected_result_shape"]["column_count"], 1)

        revision, errors = parse_revision(
            revision_block(7),
            latest_observation_ref=7,
        )
        self.assertFalse(errors)
        self.assertEqual(revision["observation_ref"], 7)

    def test_initial_plan_rejects_internal_semantic_contract_conflicts(self):
        payload = json.loads(plan_block().split("\n", 1)[1].rsplit("\n", 1)[0])
        payload["answer_type"] = "scalar"
        payload["aggregation_scope"] = "global"
        payload["aggregates"] = ["AVG(items.name)"]
        payload["aggregation_justification"] = ""
        response = "```queryplan\n" + json.dumps(payload) + "\n```"

        plan, errors = parse_initial_plan(response)

        self.assertIsNone(plan)
        self.assertIn("answer_scope is inconsistent with answer_type", errors)
        self.assertIn(
            "aggregation_justification must explain why the question requires aggregation",
            errors,
        )

    def test_initial_plan_rejects_output_count_and_source_owner_conflicts(self):
        payload = json.loads(plan_block().split("\n", 1)[1].rsplit("\n", 1)[0])
        payload["expected_result_shape"]["column_count"] = 2
        payload["output_columns"][0]["source_columns"] = ["other.name"]
        response = "```queryplan\n" + json.dumps(payload) + "\n```"

        plan, errors = parse_initial_plan(response)

        self.assertIsNone(plan)
        self.assertIn(
            "expected_result_shape.column_count must equal len(output_columns)",
            errors,
        )
        self.assertIn("output source table 'other' is absent from required_tables", errors)

    def test_initial_plan_rejects_array_limit(self):
        payload = json.loads(plan_block().split("\n", 1)[1].rsplit("\n", 1)[0])
        payload["limit"] = []
        response = "```queryplan\n" + json.dumps(payload) + "\n```"

        plan, errors = parse_initial_plan(response)

        self.assertIsNone(plan)
        self.assertIn("limit must be null or a positive integer", errors)

    def test_assignment_still_returns_authoritative_structured_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = self.make_database(directory)
            agent = DBRLM(model="test/model", max_iterations=2)
            responses = [
                '```python\nresult = db.execute("SELECT name FROM items")\n```',
                'FINAL("SELECT name FROM items")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            self.assertEqual(
                agent.complete_sql("List item names.", db_path),
                "SELECT name FROM items",
            )
            snapshot = agent.trace_snapshot()
            observation = next(
                message["content"]
                for message in snapshot["messages"]
                if message["role"] == "user"
                and "STRUCTURED TOOL OBSERVATIONS" in message["content"]
            )
            self.assertIn('"rows":[["alpha"]]', observation)
            self.assertIn("OBSERVATION_REF 1 db.execute", observation)

    def test_multiple_python_blocks_are_not_silently_discarded(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = self.make_database(directory)
            agent = DBRLM(model="test/model", max_iterations=2)
            responses = [
                '```python\nfirst = db.execute("SELECT name FROM items")\n```\n'
                '```python\nsecond = db.execute("SELECT count(*) FROM items")\n```',
                'FINAL("SELECT count(*) FROM items")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            agent.complete_sql("Count items.", db_path)
            events = [
                event for event in agent.trace_snapshot()["events"]
                if event["tool"] == "db.execute"
            ]
            self.assertEqual(len(events), 2)
            self.assertIn("count(*)", events[1]["arguments"]["sql"])

    def test_e4_a_records_initial_plan_revision_and_adherence(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = self.make_database(directory)
            agent = DBRLM(
                model="test/model",
                max_iterations=3,
                agent_config=get_agent_config("e4-a"),
            )
            responses = [
                plan_block()
                + '\n```python\nresult = db.execute("SELECT name FROM items")\n```',
                revision_block(2)
                + '\n```python\nresult = db.execute("SELECT name FROM items")\n```',
                'FINAL("SELECT name FROM items")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            sql = agent.complete_sql("List item names.", db_path)
            snapshot = agent.trace_snapshot()

            self.assertEqual(sql, "SELECT name FROM items")
            tools = [event["tool"] for event in snapshot["events"]]
            self.assertEqual(tools.count("query_plan.initial"), 1)
            self.assertEqual(tools.count("query_plan.revision"), 1)
            self.assertEqual(tools.count("query_plan.adherence"), 2)
            self.assertEqual(len(snapshot["query_plan_state"]["revisions"]), 1)
            adherence = [
                event for event in snapshot["events"]
                if event["tool"] == "query_plan.adherence"
            ]
            self.assertTrue(all(event["result"]["passed"] for event in adherence))

    def test_e4_a_blocks_code_until_initial_plan_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = self.make_database(directory)
            agent = DBRLM(
                model="test/model",
                max_iterations=3,
                agent_config=get_agent_config("e4-a"),
            )
            responses = [
                '```python\ndb.execute("SELECT name FROM items")\n```',
                plan_block()
                + '\n```python\ndb.execute("SELECT name FROM items")\n```',
                'FINAL("SELECT name FROM items")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            agent.complete_sql("List item names.", db_path)
            snapshot = agent.trace_snapshot()
            initial_events = [
                event for event in snapshot["events"]
                if event["tool"] == "query_plan.initial"
            ]
            self.assertEqual([event["result"]["valid"] for event in initial_events], [False, True])
            self.assertEqual(
                len([event for event in snapshot["events"] if event["tool"] == "db.execute"]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
