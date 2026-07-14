import unittest

from ours.agent.config import get_agent_config
from ours.agent.knowledge import KnowledgeAssembler
from scripts.run_bird_train_fewshot import _offline_metadata_manifest


class E3CSetupTests(unittest.TestCase):
    def test_e3_c_replaces_runtime_full_schema_with_offline_retrieval(self):
        config = get_agent_config("e3-c")
        self.assertEqual(config.schema_context_mode, "offline-retrieval")
        self.assertEqual(config.offline_metadata_mode, "e3-f-schema-v4")
        self.assertTrue(config.capability_gate)

        assembler = KnowledgeAssembler(
            query_pattern_mode=config.query_pattern_mode,
            offline_metadata_mode=config.offline_metadata_mode,
        )
        blocks = assembler.blocks(
            "What is the average math score for each school?",
            "california_schools",
            "",
        )
        self.assertEqual(blocks["query_patterns"], "")
        context = blocks["offline_metadata"]
        self.assertIn("OFFLINE SCHEMA CONTEXT", context)
        self.assertIn("RETRIEVED TABLES", context)
        self.assertIn("lower-relevance columns names only", context)
        self.assertLess(len(context), 12_000)

    def test_manifest_records_artifact_and_retrieval_policy(self):
        manifest = _offline_metadata_manifest(get_agent_config("e3-c"))
        self.assertEqual(manifest["version"], "e3-f-schema-v4")
        self.assertEqual(len(manifest["artifact_sha256"]), 64)
        self.assertEqual(
            manifest["retrieval"]["mode"],
            "deterministic-lexical-plus-bidirectional-fk-shortest-path",
        )


if __name__ == "__main__":
    unittest.main()
