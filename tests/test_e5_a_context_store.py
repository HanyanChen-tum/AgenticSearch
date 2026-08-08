import sqlite3
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path

from ours.agent.config import get_agent_config
from ours.agent.context_store import (
    ContextStore,
    GatedContextStore,
    verify_information_equivalence,
)
from ours.recursive_db_rlm import DBRLM


BLOCKS = {
    "hint": "\nHINT (use these definitions exactly):\n  x refers to y\n",
    "database_notes": "",
    "few_shot": "\nSIMILAR SOLVED EXAMPLES:\n  Q: ...\n",
    "query_patterns": "",
    "offline_metadata": "\nOFFLINE SCHEMA CONTEXT:\n- TABLE items:\n",
}


def make_database(directory: str) -> Path:
    path = Path(directory) / "agent.sqlite"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE items (name TEXT)")
        connection.execute("INSERT INTO items VALUES ('alpha')")
        connection.commit()
    return path


class ContextStoreTests(unittest.TestCase):
    def test_empty_sections_are_dropped_and_content_is_byte_exact(self):
        store = ContextStore(BLOCKS)
        self.assertEqual(store.section_names(), ["hint", "few_shot", "offline_metadata"])
        for name in store.section_names():
            self.assertEqual(store.content(name), BLOCKS[name])

    def test_unknown_section_name_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            ContextStore({**BLOCKS, "smuggled": "extra"})

    def test_read_returns_full_content_and_is_logged(self):
        store = ContextStore(BLOCKS)
        result = store.read("hint")
        self.assertEqual(result["content"], BLOCKS["hint"])
        self.assertIsNone(result["error"])
        log = store.read_log()
        self.assertEqual(log["sections_opened"], ["hint"])
        self.assertEqual(
            sorted(log["sections_never_opened"]), ["few_shot", "offline_metadata"]
        )

    def test_unknown_section_read_returns_error_without_logging_a_read(self):
        store = ContextStore(BLOCKS)
        result = store.read("nonexistent")
        self.assertIsNone(result["content"])
        self.assertIn("unknown section", result["error"])
        self.assertEqual(store.read_log()["read_count"], 0)

    def test_information_equivalence_holds_for_a_faithful_store(self):
        store = ContextStore(BLOCKS)
        report = verify_information_equivalence(BLOCKS, store)
        self.assertTrue(report["equivalent"])
        self.assertEqual(report["missing_from_store"], [])
        self.assertEqual(report["extra_in_store"], [])
        self.assertEqual(report["content_mismatch"], [])

    def test_information_equivalence_detects_silent_truncation(self):
        store = ContextStore(BLOCKS)
        # Simulate a store that truncated one section.
        store._sections["hint"] = BLOCKS["hint"][:10]
        report = verify_information_equivalence(BLOCKS, store)
        self.assertFalse(report["equivalent"])
        self.assertEqual(report["content_mismatch"], ["hint"])

    def test_gated_store_hides_verification_api_from_the_model(self):
        events = []
        store = ContextStore(BLOCKS)
        gated = GatedContextStore(
            store, lambda tool, args, result: events.append((tool, args, result))
        )
        self.assertEqual(gated.read("hint")["content"], BLOCKS["hint"])
        # `content` would return section text while bypassing the read log.
        with self.assertRaises(AttributeError):
            gated.content("few_shot")
        self.assertEqual(events[-1][0], "capability.denied")
        self.assertEqual(events[-1][1]["capability"], "ctx.content")
        # The bypass attempt must not have polluted the read log.
        self.assertEqual(store.read_log()["sections_opened"], ["hint"])


class E5AProfileTests(unittest.TestCase):
    def test_e5_a_differs_from_e3_c_only_in_context_access(self):
        e3_c = get_agent_config("e3-c")
        e5_a = get_agent_config("e5-a")
        self.assertEqual(e3_c.context_mode, "direct")
        self.assertEqual(e5_a.context_mode, "store-readonly")
        self.assertEqual(e5_a.prompt_profile, "basic-context-store")
        for name in (
            "use_db_hints", "verified_final", "capability_gate", "few_shot_mode",
            "query_pattern_mode", "offline_metadata_mode", "schema_context_mode",
            "reasoning_mode", "planner_mode", "allowed_db_methods",
            "literal_verification_nudge",
        ):
            self.assertEqual(
                getattr(e3_c, name), getattr(e5_a, name),
                f"{name} must match e3-c; E5-A only changes context access",
            )

    def test_capability_manifest_records_context_store_access(self):
        self.assertFalse(
            get_agent_config("e3-c").capability_manifest()["context_store_readable"]
        )
        self.assertTrue(
            get_agent_config("e5-a").capability_manifest()["context_store_readable"]
        )


class DirectPromptRegressionTests(unittest.TestCase):
    """The context-store change must not perturb the existing direct path."""

    def _prompt_for(self, profile: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            db_path = make_database(directory)
            agent = DBRLM(
                model="test/model",
                max_iterations=1,
                agent_config=get_agent_config(profile),
            )

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return 'FINAL("SELECT name FROM items")'

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            agent.complete_sql("List names.", db_path)
            return agent.trace_snapshot()["messages"][1]["content"]

    def test_clean_e0_prompt_keeps_schema_after_offline_metadata(self):
        prompt = self._prompt_for("clean-e0")
        # clean-e0 uses runtime-full schema; it must still be present and must
        # still sit immediately before the closing instruction.
        self.assertIn("Schema:", prompt)
        self.assertLess(prompt.index("Schema:"), prompt.index("Follow the Hint above"))
        self.assertTrue(prompt.startswith("QUESTION: List names."))

    def test_store_profile_omits_knowledge_from_the_prompt_and_lists_sections(self):
        prompt = self._prompt_for("e5-a")
        self.assertIn("CONTEXT STORE SECTIONS", prompt)
        self.assertIn("ctx.read(", prompt)
        # The offline schema body must NOT be inlined in the store variant.
        self.assertNotIn("OFFLINE SCHEMA CONTEXT", prompt)


class ContextStoreLoopTests(unittest.TestCase):
    def test_reads_are_traced_and_equivalence_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = make_database(directory)
            agent = DBRLM(
                model="test/model",
                max_iterations=3,
                agent_config=get_agent_config("e5-a"),
            )
            responses = [
                '```python\nprint(ctx.read("hint"))\n```',
                'FINAL("SELECT name FROM items")',
            ]

            async def fake_call_llm(self, messages, **kwargs):
                self._llm_calls += 1
                return responses.pop(0)

            agent._call_llm = types.MethodType(fake_call_llm, agent)
            # Evidence gives the store a non-empty section; the synthetic test DB
            # has no BIRD metadata, so offline_metadata renders empty here.
            agent.complete_sql("List names.", db_path, evidence="name refers to items.name")
            snapshot = agent.trace_snapshot()

            equivalence = snapshot["context_store"]["information_equivalence"]
            self.assertTrue(equivalence["equivalent"], equivalence)

            reads = snapshot["context_store_reads"]
            self.assertIn("hint", reads["sections_opened"])
            self.assertGreaterEqual(reads["read_count"], 1)

            read_events = [
                event for event in snapshot["events"]
                if event["tool"] == "context.read"
            ]
            self.assertTrue(read_events)


if __name__ == "__main__":
    unittest.main()
