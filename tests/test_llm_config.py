import unittest

from shared.llm_config import resolve_llm_config


class LLMConfigTests(unittest.TestCase):
    def test_resolves_legacy_lowercase_azure_environment(self):
        config = resolve_llm_config(environ={
            "azure_endpoint": "https://example.openai.azure.com/",
            "api_version": "2025-04-01-preview",
            "api_key": "secret",
            "model_name": "gpt-5.4-mini",
            "deployment": "seminar-gpt-5.4-mini",
        })

        self.assertEqual(config.model, "azure/seminar-gpt-5.4-mini")
        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.api_base, "https://example.openai.azure.com/")
        self.assertEqual(config.api_version, "2025-04-01-preview")

    def test_project_standard_environment_is_supported(self):
        config = resolve_llm_config(environ={
            "LLM_API_KEY": "secret",
            "LLM_BASE_URL": "https://example.openai.azure.com/",
            "MODEL": "azure/deployment",
            "LLM_API_VERSION": "2025-04-01-preview",
        })

        self.assertEqual(config.model, "azure/deployment")
        self.assertEqual(config.api_version, "2025-04-01-preview")

    def test_cli_model_override_wins(self):
        config = resolve_llm_config(
            "azure/override",
            environ={
                "api_key": "secret",
                "azure_endpoint": "https://example.openai.azure.com/",
                "deployment": "environment-deployment",
            },
        )

        self.assertEqual(config.model, "azure/override")

    def test_missing_azure_credentials_fail_before_a_run(self):
        with self.assertRaisesRegex(ValueError, "Missing Azure configuration"):
            resolve_llm_config("azure/deployment", environ={})


if __name__ == "__main__":
    unittest.main()
