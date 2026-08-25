import dataclasses
import sqlite3
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path

from ours.agent.capabilities import CapabilityDeniedError, GatedDBEnvironment
from ours.agent.config import agent_profile_names, get_agent_config
from ours.agent.prompts import get_system_prompt, prompt_manifest
from ours.agent.sql_conventions import (
    VERSION as SQL_CONVENTION_VERSION,
    get_sql_convention_rewriter,
)
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
        e4_a = get_agent_config("e4-a")

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
        self.assertEqual(e4_a.planner_mode, "root-query-plan-v1")
        self.assertEqual(e4_a.prompt_profile, "query-plan-v1")
        self.assertEqual(e4_a.offline_metadata_mode, e3_c.offline_metadata_mode)
        self.assertEqual(e4_a.query_pattern_mode, "none")
        self.assertEqual(e4_a.few_shot_mode, "train-retrieval")
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
            (
                
                "clean-e0", "clean-e1",
                "e3-a", "e3-ac",
                "e3-c", "e3-c-conv",
                "e3-c-conv-rules", "e3-c-conv-rules-final-gate",
                "e3-c-conv-rules-toolconfirm", "e3-c-join-minimal",
                "e3-c-join-minimal-v2", "e3-c-literal-check",
                "e3-c-noconv", "e3-c-recursive",
                "e3-c-recursive-db", "e3-c-recursive-db-conv2",
                "e3-c-recursive-db-final-gate", "e3-c-recursive-db-keepties",
                "e3-c-recursive-db-open", "e3-c-recursive-db-reasoning",
                "e3-c-recursive-db-types", "e3-c-rules-reasoning",
                "e3-c-semantic", "e3-c-toolconfirm-reasoning",
                "e3-f", "e3-rf",
                "e4-a", "e4-r0",
                "e5-a", "legacy-e0",
            ),
        )

    def test_e3_ac_combines_e3_a_patterns_with_e3_c_schema(self):
        a, c, ac = (get_agent_config(n) for n in ("e3-a", "e3-c", "e3-ac"))
        # takes the patterns from E3-A
        self.assertEqual(ac.query_pattern_mode, a.query_pattern_mode)
        # and everything else from E3-C
        for name in (
            "prompt_profile", "use_db_hints", "verified_final", "capability_gate",
            "few_shot_mode", "offline_metadata_mode", "schema_context_mode",
            "context_mode", "reasoning_mode", "planner_mode", "allowed_db_methods",
            "literal_verification_nudge",
        ):
            self.assertEqual(getattr(ac, name), getattr(c, name))
        self.assertNotEqual(ac.sha256, a.sha256)
        self.assertNotEqual(ac.sha256, c.sha256)

    def test_join_minimal_profile_only_changes_prompt_from_e3_c(self):
        e3_c = get_agent_config("e3-c")
        join_minimal = get_agent_config("e3-c-join-minimal")
        self.assertEqual(e3_c.prompt_profile, "basic")
        self.assertEqual(join_minimal.prompt_profile, "basic-join-minimal")
        for name in (
            "use_db_hints", "verified_final", "capability_gate", "few_shot_mode",
            "query_pattern_mode", "offline_metadata_mode", "schema_context_mode",
            "context_mode", "reasoning_mode", "planner_mode", "allowed_db_methods",
            "literal_verification_nudge",
        ):
            self.assertEqual(
                getattr(e3_c, name), getattr(join_minimal, name),
                f"{name} should be identical to e3-c; only prompt_profile differs",
            )
        self.assertNotEqual(e3_c.sha256, join_minimal.sha256)

    def test_join_minimal_v2_profile_only_changes_prompt_from_e3_c(self):
        e3_c = get_agent_config("e3-c")
        v2 = get_agent_config("e3-c-join-minimal-v2")
        self.assertEqual(v2.prompt_profile, "basic-join-minimal-v2")
        for name in (
            "use_db_hints", "verified_final", "capability_gate", "few_shot_mode",
            "query_pattern_mode", "offline_metadata_mode", "schema_context_mode",
            "context_mode", "reasoning_mode", "planner_mode", "allowed_db_methods",
            "literal_verification_nudge",
        ):
            self.assertEqual(getattr(e3_c, name), getattr(v2, name))
        self.assertNotEqual(e3_c.sha256, v2.sha256)
        self.assertNotEqual(
            get_agent_config("e3-c-join-minimal").sha256, v2.sha256,
        )

    def test_literal_check_profile_only_adds_the_nudge_flag_to_e3_c(self):
        e3_c = get_agent_config("e3-c")
        literal_check = get_agent_config("e3-c-literal-check")
        self.assertFalse(e3_c.literal_verification_nudge)
        self.assertTrue(literal_check.literal_verification_nudge)
        for name in (
            "use_db_hints", "verified_final", "capability_gate", "few_shot_mode",
            "query_pattern_mode", "offline_metadata_mode", "schema_context_mode",
            "context_mode", "reasoning_mode", "planner_mode", "allowed_db_methods",
            "prompt_profile",
        ):
            self.assertEqual(
                getattr(e3_c, name), getattr(literal_check, name),
                f"{name} should be identical to e3-c; only literal_verification_nudge differs",
            )
        self.assertNotEqual(e3_c.sha256, literal_check.sha256)

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

    def test_join_minimal_prompt_extends_basic_and_stays_protocol_only(self):
        basic = get_system_prompt("basic")
        join_minimal = get_system_prompt("basic-join-minimal")
        manifest = prompt_manifest("basic-join-minimal")

        self.assertTrue(join_minimal.startswith(basic))
        self.assertIn("minimal set of tables", join_minimal)
        self.assertFalse(manifest["contains_task_specific_sql_rules"])
        self.assertFalse(manifest["contains_examples"])
        self.assertEqual(manifest["source"], "protocol-only")
        self.assertNotEqual(manifest["sha256"], prompt_manifest("basic")["sha256"])

    def test_join_minimal_v2_prompt_separates_table_count_from_join_type(self):
        v1 = get_system_prompt("basic-join-minimal")
        v2 = get_system_prompt("basic-join-minimal-v2")
        manifest = prompt_manifest("basic-join-minimal-v2")

        self.assertTrue(v2.startswith(v1))
        self.assertIn("LEFT JOIN", v2)
        self.assertIn("not which JOIN TYPE", v2)
        self.assertFalse(manifest["contains_task_specific_sql_rules"])
        self.assertFalse(manifest["contains_examples"])
        self.assertNotEqual(manifest["sha256"], prompt_manifest("basic-join-minimal")["sha256"])

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

    def test_unverified_literal_warning_fires_for_unsampled_column(self):
        state = AgentExecutionState()
        warning = state.unverified_literal_warning(
            "SELECT * FROM t WHERE status = 'active'"
        )
        self.assertIsNotNone(warning)
        self.assertIn("status", warning)
        self.assertIn("sample_values", warning)

    def test_unverified_literal_warning_is_silent_after_sample_values(self):
        state = AgentExecutionState()
        state.record_sample_values("status")
        self.assertIsNone(
            state.unverified_literal_warning("SELECT * FROM t WHERE status = 'active'")
        )

    def test_unverified_literal_warning_matches_table_qualified_column_by_bare_name(self):
        state = AgentExecutionState()
        state.record_sample_values("Status")  # case-insensitive, bare name
        self.assertIsNone(
            state.unverified_literal_warning("SELECT * FROM t AS T1 WHERE T1.status = 'active'")
        )

    def test_unverified_literal_warning_covers_in_list_but_not_in_subquery(self):
        state = AgentExecutionState()
        self.assertIsNotNone(
            state.unverified_literal_warning("SELECT * FROM t WHERE code IN ('a', 'b')")
        )
        state2 = AgentExecutionState()
        self.assertIsNone(
            state2.unverified_literal_warning(
                "SELECT * FROM t WHERE id IN (SELECT id FROM other)"
            )
        )

    def test_unverified_literal_warning_fires_once_per_column_per_trace(self):
        state = AgentExecutionState()
        first = state.unverified_literal_warning("SELECT * FROM t WHERE status = 'active'")
        second = state.unverified_literal_warning("SELECT * FROM t WHERE status = 'inactive'")
        self.assertIsNotNone(first)
        self.assertIsNone(second)


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


class LiteralVerificationNudgeLoopTests(unittest.TestCase):
    def test_nudge_appears_in_transcript_for_unsampled_literal_and_clears_after_sample_values(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = CapabilityGateTests.make_database(directory)
            config = dataclasses.replace(
                get_agent_config("clean-e0"),
                profile="test-literal-nudge",
                literal_verification_nudge=True,
            )
            agent = DBRLM(model="test/model", max_iterations=4, agent_config=config)
            responses = [
                '```python\nprint(db.execute("SELECT name FROM items WHERE name = \'alpha\'"))\n```',
                '```python\nprint(db.sample_values("items", "name"))\n```',
                'FINAL("SELECT name FROM items WHERE name = \'alpha\'")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            agent.complete_sql("Find alpha.", db_path)
            snapshot = agent.trace_snapshot()

            first_observation = snapshot["messages"][3]["content"]
            self.assertIn("sample_values", first_observation)
            self.assertIn("name", first_observation)
            self.assertEqual(snapshot["execution_state"]["sampled_columns"], ["name"])

    def test_nudge_is_silent_when_flag_is_off(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = CapabilityGateTests.make_database(directory)
            config = dataclasses.replace(
                get_agent_config("clean-e0"),
                profile="test-literal-nudge-off",
                literal_verification_nudge=False,
            )
            agent = DBRLM(model="test/model", max_iterations=4, agent_config=config)
            responses = [
                '```python\nprint(db.execute("SELECT name FROM items WHERE name = \'alpha\'"))\n```',
                'FINAL("SELECT name FROM items WHERE name = \'alpha\'")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            agent.complete_sql("Find alpha.", db_path)
            snapshot = agent.trace_snapshot()

            first_observation = snapshot["messages"][3]["content"]
            self.assertNotIn("sample_values was never called", first_observation)


class SqlConventionRewriteTests(unittest.TestCase):
    """The mined conventions are applied by the harness, never by the prompt."""

    def setUp(self):
        self.rewriter = get_sql_convention_rewriter()

    def test_enabled_conventions_carry_train_support_in_the_manifest(self):
        manifest = self.rewriter.manifest()
        self.assertEqual(manifest["version"], SQL_CONVENTION_VERSION)
        self.assertFalse(manifest["application"]["uses_dev_data"])
        self.assertFalse(manifest["application"]["uses_gold_sql"])
        for name in manifest["enabled_conventions"]:
            self.assertGreaterEqual(manifest["conventions"][name]["train_support"], 0.80)

    def test_count_distinct_is_stripped_only_when_the_query_joins(self):
        joined = self.rewriter.rewrite(
            "SELECT COUNT(DISTINCT a.id) FROM a JOIN b ON a.id = b.id"
        )
        self.assertEqual(joined.applied, ("count_no_distinct",))
        self.assertNotIn("DISTINCT", joined.sql.upper())
        # Without a join there is no join-induced duplication, so a DISTINCT the
        # model wrote is far more likely to be genuinely requested.
        single = self.rewriter.rewrite("SELECT COUNT(DISTINCT a.id) FROM a")
        self.assertEqual(single.applied, ())
        self.assertFalse(single.changed)

    def test_select_concat_splits_into_separate_projections(self):
        result = self.rewriter.rewrite(
            "SELECT f || ' ' || l FROM t JOIN u ON t.id = u.id"
        )
        self.assertEqual(result.applied, ("no_select_concat",))
        self.assertEqual(result.sql, "SELECT f, l FROM t JOIN u ON t.id = u.id")

    def test_select_concat_declines_when_its_alias_is_referenced(self):
        # Splitting removes the alias, so an ORDER BY on it stops resolving.
        # Observed on bird_1011, where the split produced a hard SQL error.
        result = self.rewriter.rewrite(
            "SELECT f || ' ' || l AS full_name FROM t JOIN u ON t.id = u.id "
            "ORDER BY full_name ASC"
        )
        self.assertEqual(result.applied, ())
        self.assertFalse(result.changed)

    def test_superlative_rewrite_only_fires_on_the_mined_shape(self):
        simple = self.rewriter.rewrite(
            "SELECT name FROM players WHERE height = (SELECT MAX(height) FROM players)"
        )
        self.assertEqual(simple.applied, ("superlative_order_limit",))
        self.assertIn("ORDER BY", simple.sql.upper())
        self.assertIn("LIMIT 1", simple.sql.upper())
        # A subquery carrying its own conditions is not the near-equivalent form.
        conditional = self.rewriter.rewrite(
            "SELECT name FROM p WHERE h = (SELECT MAX(h) FROM p WHERE t = 'A')"
        )
        self.assertEqual(conditional.applied, ())

    def test_unparseable_sql_is_returned_untouched(self):
        result = self.rewriter.rewrite("SELECT COUNT(DISTINCT FROM JOIN ((")
        self.assertEqual(result.sql, result.original_sql)
        self.assertEqual(result.applied, ())

    def test_profile_without_the_mode_never_rewrites(self):
        agent = DBRLM(
            model="test/model", agent_config=get_agent_config("e3-c")
        )
        self.assertIsNone(agent._sql_conventions)
        self.assertEqual(agent._apply_sql_conventions("SELECT 1"), "SELECT 1")

    def test_profile_with_the_mode_rewrites_and_records_the_change(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = CapabilityGateTests.make_database(directory)
            agent = DBRLM(
                model="test/model", max_iterations=4,
                agent_config=get_agent_config("e3-c-conv"),
            )
            responses = [
                'FINAL("SELECT COUNT(DISTINCT i.name) FROM items AS i '
                'JOIN items AS j ON i.id = j.id")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            final_sql = agent.complete_sql("How many items?", db_path)

            self.assertNotIn("DISTINCT", final_sql.upper())
            rewrite = agent.trace_snapshot()["sql_convention_rewrite"]
            self.assertTrue(rewrite["changed"])
            self.assertEqual(rewrite["applied"], ["count_no_distinct"])
            self.assertIn("DISTINCT", rewrite["original_sql"].upper())


class TrainAuditedConventionPromptTests(unittest.TestCase):
    """Only the legacy-prompt rules that train data supports may be restated."""

    def test_prompt_states_the_supported_rules_and_omits_the_refuted_ones(self):
        prompt = get_system_prompt("basic-conventions-v1")
        self.assertIn("ORDER BY col ASC|DESC LIMIT 1", prompt)
        self.assertIn("projects exactly one column", prompt)
        # Train contradicts both of these, so restating them would import the
        # legacy prompt's eval tuning along with its useful parts.
        self.assertNotIn("YES", prompt)
        self.assertNotIn("every asked item", prompt)

    def test_provenance_declares_the_train_split(self):
        manifest = prompt_manifest("basic-conventions-v1")
        self.assertEqual(manifest["source_split"], "train")
        self.assertEqual(manifest["source"], "train-mined-conventions")
        self.assertFalse(manifest["contains_examples"])

    def test_isolates_the_prompt_against_e3_c_conv(self):
        base, rules = (get_agent_config(n) for n in ("e3-c-conv", "e3-c-conv-rules"))
        differing = [
            f.name for f in dataclasses.fields(rules)
            if getattr(rules, f.name) != getattr(base, f.name)
        ]
        self.assertEqual(
            differing, ["profile", "experiment_variant", "prompt_profile"]
        )
        self.assertEqual(rules.sql_convention_mode, base.sql_convention_mode)


class RecursionExposureTests(unittest.TestCase):
    """The recursion primitive was present but unnamed, so it was never invoked."""

    def test_only_the_recursive_profile_puts_the_primitive_in_the_repl(self):
        for profile, expected in (("e3-c", False), ("e3-c-recursive", True)):
            agent = DBRLM(model="test/model", agent_config=get_agent_config(profile))
            env = agent._build_repl_env("q", "ctx")
            self.assertEqual("recursive_llm" in env, expected, profile)
            # The db gate stays on in both, so recursion is the only variable.
            self.assertEqual(
                agent.agent_config.allowed_db_methods, ("execute", "sample_values")
            )

    def test_the_prompt_names_the_tool_and_its_limits(self):
        prompt = get_system_prompt("basic-recursive-v1")
        self.assertIn("recursive_llm(", prompt)
        # The child is a plain RLM: no database, no schema, no history. Saying so
        # matters, otherwise the model spends calls on things the leaf cannot do.
        self.assertIn("no database access", prompt)
        self.assertNotIn("recursive_llm", get_system_prompt("basic"))

    def test_recursion_mode_requires_the_prompt_that_documents_it(self):
        with self.assertRaises(ValueError):
            dataclasses.replace(
                get_agent_config("e3-c-recursive"), prompt_profile="basic"
            )

    def test_capability_manifest_records_exposure_separately_from_the_gate(self):
        recursive = get_agent_config("e3-c-recursive").capability_manifest()
        plain = get_agent_config("e3-c").capability_manifest()
        self.assertTrue(recursive["recursion_exposed"])
        self.assertFalse(plain["recursion_exposed"])
        self.assertTrue(recursive["gate_enabled"])

    def test_leaf_db_mode_gives_the_child_the_gated_database(self):
        from ours.agent.leaf import LeafAgent

        calls = []

        async def fake_llm(messages):
            calls.append(messages)
            if len(calls) == 1:
                return '```python\nprint(db.sample_values("items", "name"))\n```'
            return 'FINAL("the column holds the value alpha")'

        with tempfile.TemporaryDirectory() as directory:
            db_path = CapabilityGateTests.make_database(directory)
            db = GatedDBEnvironment(
                DBEnvironment(db_path), ("execute", "sample_values"), lambda *a: None
            )
            import asyncio
            result = asyncio.run(
                LeafAgent(fake_llm, db).answer("which values?", "some material")
            )

        self.assertEqual(result["terminated"], "final")
        self.assertIn("alpha", result["answer"])
        # v1's leaf could not do this: the child now reaches the database.
        self.assertIn("db.sample_values", calls[1][2]["content"]
                      if len(calls[1]) > 2 else str(calls[1]))

    def test_leaf_reports_running_out_of_turns_instead_of_guessing(self):
        from ours.agent.leaf import LeafAgent
        import asyncio

        async def never_finishes(messages):
            return '```python\nprint(1)\n```'

        result = asyncio.run(
            LeafAgent(never_finishes, None, max_iterations=2).answer("q", "")
        )
        self.assertEqual(result["terminated"], "max_iterations")
        self.assertIn("no answer", result["answer"])

    def test_every_recursive_call_is_recorded_in_the_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = CapabilityGateTests.make_database(directory)
            agent = DBRLM(
                model="test/model", max_iterations=4,
                agent_config=get_agent_config("e3-c-recursive"),
            )
            agent._make_recursive_fn = lambda: (lambda q, c: f"leaf saw {len(c)} chars")
            responses = [
                '```python\nprint(recursive_llm("which column?", "name, id"))\n```',
                'FINAL("SELECT name FROM items")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            agent.complete_sql("Find alpha.", db_path)

            events = [e for e in agent.trace_snapshot()["events"]
                      if e["tool"] == "recursive_llm"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["arguments"]["sub_query"], "which column?")
            self.assertEqual(events[0]["arguments"]["sub_context_chars"], 8)


class ReasoningCaptureTests(unittest.TestCase):
    """Reasoning must be captured during the run that produced the answer."""

    def test_only_the_capture_profile_changes_the_api_path(self):
        base, cap = (get_agent_config(n) for n in ("e3-c-conv-rules", "e3-c-rules-reasoning"))
        differing = [
            f.name for f in dataclasses.fields(cap)
            if getattr(cap, f.name) != getattr(base, f.name)
        ]
        self.assertEqual(differing, ["profile", "experiment_variant", "reasoning_capture"])

    def test_manifest_states_that_summaries_are_not_the_raw_chain(self):
        from ours.agent.reasoning_capture import manifest
        m = manifest()
        self.assertEqual(m["api"], "responses")
        # The deployment does not return raw reasoning tokens; a run that implied
        # otherwise would misrepresent what was captured.
        self.assertFalse(m["captures_raw_reasoning"])

    def test_system_messages_become_instructions(self):
        from ours.agent.reasoning_capture import split_messages
        instructions, body = split_messages([
            {"role": "system", "content": "S"},
            {"role": "user", "content": "U"},
            {"role": "assistant", "content": "A"},
        ])
        self.assertEqual(instructions, "S")
        self.assertEqual([m["role"] for m in body], ["user", "assistant"])

    def test_reasoning_sections_and_text_are_separated(self):
        from ours.agent.reasoning_capture import parse_response
        parsed = parse_response({
            "output": [
                {"type": "reasoning", "summary": [
                    {"text": "**Plan** first"}, {"text": "**Check** second"}]},
                {"type": "message", "content": [{"text": 'FINAL("SELECT 1")'}]},
            ],
            "usage": {"input_tokens": 10, "output_tokens": 90,
                      "output_tokens_details": {"reasoning_tokens": 80}},
        })
        self.assertEqual(parsed["section_count"], 2)
        self.assertIn("SELECT 1", parsed["text"])
        self.assertEqual(parsed["reasoning_tokens"], 80)


if __name__ == "__main__":
    unittest.main()
