import sqlite3
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path

from ours.agent.capabilities import CapabilityDeniedError, GatedDBEnvironment
from ours.agent.config import agent_profile_names, get_agent_config
from ours.agent.prompts import get_system_prompt, prompt_manifest
from ours.agent.state import AgentExecutionState, ExecutionStatus
from ours.db_environment import DBEnvironment
from ours.recursive_db_rlm import DBRLM
from scripts.run_bird_indomain_fewshot import InDomainFewShotDBRLM


class AgentProfileTests(unittest.TestCase):
    def test_dbrlm_default_does_not_implicitly_enable_an_experiment_mechanism(self):
        agent = DBRLM(model="test/model")
        self.assertEqual(agent.agent_config.profile, "clean-e0")

    def test_profiles_keep_each_ablation_boundary_explicit(self):
        e0 = get_agent_config("clean-e0")
        e1 = get_agent_config("clean-e1")
        r0 = get_agent_config("e4-r0")
        e3 = get_agent_config("e3-a")
        e3_rf = get_agent_config("e3-rf")
        e3_c = get_agent_config("e3-c")
        e3_f = get_agent_config("e3-f")

        self.assertFalse(e0.use_db_hints)
        self.assertFalse(e0.verified_final)
        self.assertFalse(e0.capability_gate)
        self.assertTrue(e1.verified_final)
        self.assertFalse(e1.capability_gate)
        self.assertFalse(r0.verified_final)
        self.assertTrue(r0.capability_gate)
        self.assertEqual(e3.query_pattern_mode, "train-static-v1")
        self.assertEqual(e3.few_shot_mode, "train-retrieval")
        self.assertEqual(e3_rf.query_pattern_mode, "train-static-v1")
        self.assertEqual(e3_rf.few_shot_mode, "none")
        self.assertEqual(e3_c.query_pattern_mode, "none")
        self.assertEqual(e3_c.few_shot_mode, "train-retrieval")
        self.assertEqual(e3_c.offline_metadata_mode, "e3-f-schema-v4")
        self.assertTrue(e3_c.capability_gate)
        self.assertEqual(e3_c.schema_context_mode, "offline-retrieval")
        self.assertEqual(e3_f.query_pattern_mode, "train-mined-v2")
        self.assertEqual(e3_f.offline_metadata_mode, "e3-f-schema-v4")
        self.assertTrue(e3_f.capability_gate)
        self.assertEqual(e0.schema_context_mode, "runtime-full")
        self.assertFalse(e3.verified_final)
        self.assertFalse(e3.capability_gate)
        self.assertEqual(e0.prompt_profile, e1.prompt_profile)
        self.assertEqual(e1.prompt_profile, r0.prompt_profile)
        self.assertEqual(e1.allowed_db_methods, r0.allowed_db_methods)
        self.assertEqual(e0.verified_final, r0.verified_final)
        self.assertNotEqual(
            e1.capability_manifest()["sha256"],
            r0.capability_manifest()["sha256"],
        )
        self.assertEqual(r0.capability_manifest()["version"], 1)
        self.assertEqual(
            agent_profile_names(),
            ("clean-e0", "clean-e1", "e3-a", "e3-c", "e3-f", "e3-rf", "e4-r0", "legacy-e0"),
        )

    def test_profile_hash_is_deterministic_and_changes_with_configuration(self):
        e0 = get_agent_config("clean-e0")
        self.assertEqual(e0.sha256, get_agent_config("clean-e0").sha256)
        self.assertNotEqual(e0.sha256, get_agent_config("clean-e1").sha256)
        self.assertNotEqual(
            get_agent_config("clean-e1").sha256,
            get_agent_config("e4-r0").sha256,
        )

    def test_legacy_profile_is_the_only_profile_with_eval_tuned_hints(self):
        enabled = [
            name
            for name in agent_profile_names()
            if get_agent_config(name).use_db_hints
        ]
        self.assertEqual(enabled, ["legacy-e0"])

    def test_rejected_verified_final_is_confined_to_e1_reproduction(self):
        enabled = [
            name
            for name in agent_profile_names()
            if get_agent_config(name).verified_final
        ]
        self.assertEqual(enabled, ["clean-e1"])

    def test_clean_prompt_is_protocol_only_and_versioned(self):
        clean = get_system_prompt("basic")
        legacy = get_system_prompt("legacy")
        manifest = prompt_manifest("basic")

        self.assertNotIn("RANK()", clean)
        self.assertNotIn("DISTINCT", clean)
        self.assertNotIn("denominator", clean)
        self.assertIn("RANK()", legacy)
        self.assertFalse(manifest["contains_task_specific_sql_rules"])
        self.assertFalse(manifest["contains_examples"])
        self.assertEqual(manifest["source"], "protocol-only")
        self.assertEqual(len(manifest["sha256"]), 64)

    def test_formal_profiles_share_the_same_prompt_manifest(self):
        manifests = [
            get_agent_config(name).to_manifest()["prompt"]
            for name in ("clean-e0", "clean-e1", "e4-r0")
        ]
        self.assertEqual(manifests[0], manifests[1])
        self.assertEqual(manifests[1], manifests[2])
        self.assertNotEqual(
            manifests[0]["sha256"],
            get_agent_config("legacy-e0").to_manifest()["prompt"]["sha256"],
        )


class AgentExecutionStateTests(unittest.TestCase):
    def test_e0_accepts_final_without_adding_e1_state_protection(self):
        state = AgentExecutionState()
        state.record("SELECT missing", {"rows": [], "error": "no such column"})
        allowed, reason = state.validate_final(
            "SELECT something_else",
            require_verified=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_e1_requires_final_to_match_the_last_successful_execution(self):
        state = AgentExecutionState()
        record = state.record(" SELECT name FROM items; ", {
            "rows": [["alpha"]],
            "error": None,
        })
        self.assertEqual(record.status, ExecutionStatus.SUCCESS)
        self.assertEqual(
            state.validate_final(
                "SELECT name FROM items",
                require_verified=True,
            ),
            (True, ""),
        )
        allowed, reason = state.validate_final(
            "SELECT upper(name) FROM items",
            require_verified=True,
        )
        self.assertFalse(allowed)
        self.assertIn("differs", reason)

    def test_e1_invalid_execution_cannot_be_bypassed_by_repeating_final(self):
        state = AgentExecutionState()
        state.record("SELECT name FROM items WHERE 0", {"rows": [], "error": None})
        first = state.validate_final(
            "SELECT name FROM items WHERE 0",
            require_verified=True,
        )
        second = state.validate_final(
            "SELECT name FROM items WHERE 0",
            require_verified=True,
        )
        self.assertEqual(first, second)
        self.assertFalse(first[0])
        self.assertIn("empty", first[1])

    def test_e1_allows_an_executed_all_null_result(self):
        state = AgentExecutionState()
        record = state.record("SELECT NULL", {"rows": [[None]], "error": None})
        self.assertEqual(record.status, ExecutionStatus.ALL_NULL)
        self.assertEqual(
            state.validate_final("SELECT NULL", require_verified=True),
            (True, ""),
        )


class CapabilityGateTests(unittest.TestCase):
    @staticmethod
    def make_database(directory: str) -> Path:
        path = Path(directory) / "agent.sqlite"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE items (name TEXT)")
            connection.execute("INSERT INTO items VALUES ('alpha')")
            connection.commit()
        return path

    def test_gate_allows_manifest_methods_and_traces_denied_methods(self):
        with tempfile.TemporaryDirectory() as directory:
            events = []
            environment = DBEnvironment(self.make_database(directory))
            gated = GatedDBEnvironment(
                environment,
                ("execute", "sample_values"),
                lambda tool, arguments, result: events.append(
                    (tool, arguments, result)
                ),
            )

            self.assertEqual(
                gated.execute("SELECT name FROM items")["rows"],
                [["alpha"]],
            )
            with self.assertRaises(CapabilityDeniedError):
                gated.get_schema("items")
            self.assertEqual(events[0][0], "capability.denied")
            self.assertEqual(events[0][1]["capability"], "db.get_schema")

    def test_r0_removes_generic_recursive_llm_from_repl_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = self.make_database(directory)
            r0 = DBRLM(
                model="test/model",
                agent_config=get_agent_config("e4-r0"),
            )
            r0._prepare_trace("List names", db_path, "")
            r0_env = r0._build_repl_env("List names", "")
            self.assertNotIn("recursive_llm", r0_env)
            self.assertIsInstance(r0_env["db"], GatedDBEnvironment)

    def test_indomain_wrapper_does_not_duplicate_the_agent_loop(self):
        self.assertIs(InDomainFewShotDBRLM.acomplete, DBRLM.acomplete)


class VerifiedFinalLoopTests(unittest.TestCase):
    def test_e1_blocks_changed_final_until_exact_sql_is_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = CapabilityGateTests.make_database(directory)
            agent = DBRLM(
                model="test/model",
                max_iterations=4,
                agent_config=get_agent_config("clean-e1"),
            )
            responses = [
                '```python\nprint(db.execute("SELECT name FROM items"))\n```',
                'FINAL("SELECT upper(name) FROM items")',
                '```python\nprint(db.execute("SELECT upper(name) FROM items"))\n```',
                'FINAL("SELECT upper(name) FROM items")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            sql = agent.complete_sql("List upper-case item names.", db_path)
            snapshot = agent.trace_snapshot()

            self.assertEqual(sql, "SELECT upper(name) FROM items")
            blocked = [
                event for event in snapshot["events"]
                if event["tool"] == "final.blocked"
            ]
            self.assertEqual(len(blocked), 1)
            self.assertIn("differs", blocked[0]["result"]["reason"])
            self.assertEqual(
                snapshot["execution_state"]["last_execution"]["normalized_sql"],
                sql,
            )


if __name__ == "__main__":
    unittest.main()
