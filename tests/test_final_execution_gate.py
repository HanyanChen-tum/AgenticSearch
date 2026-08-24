import dataclasses
import sqlite3
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from ours.agent.config import get_agent_config
from ours.recursive_db_rlm import DBRLM
import ours.db_environment as db_environment


def _script(agent, responses):
    async def fake_call_llm(self, messages, **kwargs):
        self._llm_calls += 1
        return responses.pop(0)

    agent._call_llm = types.MethodType(fake_call_llm, agent)


def _blocked_events(agent):
    return [e for e in agent.trace_snapshot()["events"] if e["tool"] == "final.blocked"]


class FinalExecutionGateTests(unittest.TestCase):
    def _simple_db(self, directory: str) -> Path:
        path = Path(directory) / "agent.sqlite"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE items (name TEXT)")
            connection.execute("INSERT INTO items VALUES ('alpha')")
            connection.commit()
        return path

    def _slow_unindexed_db(self, directory: str, n_a: int = 3000, n_b: int = 300000) -> Path:
        path = Path(directory) / "slow.sqlite"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE a (id INTEGER)")
            connection.execute("CREATE TABLE b (a_id INTEGER, val INTEGER)")
            connection.executemany("INSERT INTO a VALUES (?)", [(i,) for i in range(n_a)])
            connection.executemany(
                "INSERT INTO b VALUES (?, ?)", [(i % n_a, i * 2) for i in range(n_b)]
            )
            connection.commit()
        return path

    def test_accepts_on_first_try_and_the_controller_did_the_executing(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = self._simple_db(directory)
            config = dataclasses.replace(
                get_agent_config("clean-e0"),
                profile="test-final-gate",
                final_execution_gate=True,
            )
            agent = DBRLM(model="test/model", max_iterations=3, agent_config=config)
            _script(agent, ['FINAL("SELECT name FROM items")'])

            sql = agent.complete_sql("List item names.", db_path)

        self.assertEqual(sql, "SELECT name FROM items")
        self.assertEqual(_blocked_events(agent), [])
        db_events = [e for e in agent.trace_snapshot()["events"] if e["tool"] == "db.execute"]
        self.assertEqual(len(db_events), 1)
        self.assertEqual(db_events[0]["arguments"]["sql"], "SELECT name FROM items")
        self.assertEqual(db_events[0]["result"]["rows"], [["alpha"]])

    def test_blocks_a_genuine_error_with_generic_guidance_not_timeout_wording(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = self._simple_db(directory)
            config = dataclasses.replace(
                get_agent_config("clean-e0"),
                profile="test-final-gate",
                final_execution_gate=True,
            )
            agent = DBRLM(model="test/model", max_iterations=4, agent_config=config)
            _script(agent, [
                'FINAL("SELECT * FROM does_not_exist")',
                'FINAL("SELECT name FROM items")',
            ])

            sql = agent.complete_sql("List item names.", db_path)
            snapshot = agent.trace_snapshot()

        self.assertEqual(sql, "SELECT name FROM items")
        blocked = _blocked_events(agent)
        self.assertEqual(len(blocked), 1)
        feedback = snapshot["messages"][-2]["content"]
        self.assertIn("BLOCKED FINAL", feedback)
        self.assertNotIn("did not finish in time", feedback)
        self.assertIn("execution error was", feedback)
        self.assertIn("no such table", feedback)
        self.assertIn("Fix the SQL", feedback)

    def test_blocks_a_timeout_with_redesign_guidance_and_the_model_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = self._slow_unindexed_db(directory)
            config = dataclasses.replace(
                get_agent_config("clean-e0"),
                profile="test-final-gate",
                final_execution_gate=True,
            )
            agent = DBRLM(model="test/model", max_iterations=4, agent_config=config)
            slow_sql = (
                "SELECT COUNT(*) FROM a AS t1 WHERE EXISTS "
                "(SELECT 1 FROM b AS t2 WHERE t2.a_id = t1.id AND t2.val > 0)"
            )
            _script(agent, [
                f'FINAL("{slow_sql}")',
                'FINAL("SELECT COUNT(*) FROM a")',
            ])

            with mock.patch.object(db_environment, "QUERY_TIMEOUT_S", 0.01):
                sql = agent.complete_sql("Count rows.", db_path)
            snapshot = agent.trace_snapshot()

        self.assertEqual(sql, "SELECT COUNT(*) FROM a")
        blocked = _blocked_events(agent)
        self.assertEqual(len(blocked), 1)
        feedback = snapshot["messages"][-2]["content"]
        self.assertIn("BLOCKED FINAL", feedback)
        self.assertIn("did not finish in time", feedback)
        self.assertIn("redesign", feedback)
        self.assertIn("JOIN", feedback)

    def test_off_by_default_leaves_final_unexecuted_by_the_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = self._simple_db(directory)
            agent = DBRLM(model="test/model", max_iterations=3)  # clean-e0 default
            self.assertFalse(agent.agent_config.final_execution_gate)
            _script(agent, ['FINAL("SELECT name FROM items")'])

            sql = agent.complete_sql("List item names.", db_path)

        self.assertEqual(sql, "SELECT name FROM items")
        db_events = [e for e in agent.trace_snapshot()["events"] if e["tool"] == "db.execute"]
        self.assertEqual(db_events, [])


class FinalGateProfileTests(unittest.TestCase):
    PAIRS = (
        ("e3-c-conv-rules", "e3-c-conv-rules-final-gate"),
        ("e3-c-recursive-db", "e3-c-recursive-db-final-gate"),
    )

    def test_gate_profiles_differ_from_their_base_only_by_the_gate(self):
        for base_name, gate_name in self.PAIRS:
            base, gate = get_agent_config(base_name), get_agent_config(gate_name)
            self.assertFalse(base.final_execution_gate, base_name)
            self.assertTrue(gate.final_execution_gate, gate_name)
            for field in dataclasses.fields(base):
                if field.name in ("profile", "experiment_variant", "final_execution_gate"):
                    continue
                self.assertEqual(
                    getattr(base, field.name), getattr(gate, field.name),
                    f"{gate_name}.{field.name} must match {base_name}; "
                    "only final_execution_gate may differ",
                )
            self.assertNotEqual(base.sha256, gate.sha256)

    def test_the_recommended_default_carries_the_gate(self):
        # e3-c-recursive-db is the highest-scoring chain arm (88.10% mean on
        # the corrected 498); its gate variant is what new runs should use so
        # an errored or timed-out query is returned to the model rather than
        # reaching scoring as a no_answer.
        self.assertTrue(
            get_agent_config("e3-c-recursive-db-final-gate").final_execution_gate
        )

    def test_the_two_final_gates_are_mutually_exclusive(self):
        # verified_final (clean-e1) was rejected; the two gates answer the same
        # question in incompatible ways, so a profile must not carry both.
        with self.assertRaises(ValueError):
            dataclasses.replace(
                get_agent_config("e3-c-recursive-db-final-gate"), verified_final=True
            )


if __name__ == "__main__":
    unittest.main()
