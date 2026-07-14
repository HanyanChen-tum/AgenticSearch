import unittest

from ours.agent.config import get_agent_config
from scripts.run_bird_train_fewshot import _query_pattern_manifest, _resolve_train_few_shot


class E3RFSetupTests(unittest.TestCase):
    def test_e3_rf_disables_train_retrieval_without_losing_pattern_artifact(self):
        enabled, effective_k, retriever_manifest = _resolve_train_few_shot(
            get_agent_config("e3-rf"),
            requested_k=1,
        )

        self.assertFalse(enabled)
        self.assertEqual(effective_k, 0)
        self.assertFalse(retriever_manifest["enabled"])
        self.assertEqual(retriever_manifest["mode"], "none")
        self.assertIsNone(retriever_manifest["pool_sha256"])

        pattern_manifest = _query_pattern_manifest(get_agent_config("e3-rf"))
        self.assertEqual(pattern_manifest["source_split"], "bird-train")
        self.assertEqual(len(pattern_manifest["artifact_sha256"]), 64)
        self.assertTrue(pattern_manifest["pattern_support"])


if __name__ == "__main__":
    unittest.main()
