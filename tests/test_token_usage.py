import types
import unittest
from unittest.mock import AsyncMock, patch

from shared.token_usage import (
    aggregate_call_usage,
    extract_response_usage,
    summarize_result_usage,
)
from src.rlm.core import RLM


class TokenUsageTests(unittest.TestCase):
    def test_extracts_reasoning_and_cached_tokens_from_nested_details(self):
        response = {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 40,
                "total_tokens": 140,
                "completion_tokens_details": {"reasoning_tokens": 25},
                "prompt_tokens_details": {"cached_tokens": 60},
            },
        }

        self.assertEqual(extract_response_usage(response), {
            "usage_available": True,
            "reasoning_tokens_available": True,
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "reasoning_tokens": 25,
            "total_tokens": 140,
            "cached_prompt_tokens": 60,
        })

    def test_supports_attribute_responses_and_derives_missing_total(self):
        response = types.SimpleNamespace(
            usage=types.SimpleNamespace(
                prompt_tokens=12,
                completion_tokens=8,
                completion_tokens_details=types.SimpleNamespace(
                    reasoning_tokens=3,
                ),
            ),
        )

        usage = extract_response_usage(response)

        self.assertEqual(usage["total_tokens"], 20)
        self.assertEqual(usage["reasoning_tokens"], 3)
        self.assertTrue(usage["reasoning_tokens_available"])
        self.assertEqual(usage["cached_prompt_tokens"], 0)

    def test_empty_usage_is_not_treated_as_complete_zero_usage(self):
        usage = extract_response_usage({"usage": {}})

        self.assertFalse(usage["usage_available"])
        self.assertFalse(usage["reasoning_tokens_available"])
        self.assertEqual(usage["total_tokens"], 0)

    def test_supports_input_output_token_names(self):
        usage = extract_response_usage({
            "usage": {
                "input_tokens": 7,
                "output_tokens": 3,
                "cache_read_input_tokens": 4,
            },
        })

        self.assertTrue(usage["usage_available"])
        self.assertFalse(usage["reasoning_tokens_available"])
        self.assertEqual(usage["prompt_tokens"], 7)
        self.assertEqual(usage["completion_tokens"], 3)
        self.assertEqual(usage["cached_prompt_tokens"], 4)
        self.assertEqual(usage["total_tokens"], 10)

    def test_aggregates_calls_and_marks_missing_usage(self):
        summary = aggregate_call_usage([
            {
                "usage_available": True,
                "reasoning_tokens_available": True,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "reasoning_tokens": 2,
                "total_tokens": 15,
                "cached_prompt_tokens": 4,
            },
            {
                "usage_available": False,
                "reasoning_tokens_available": False,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 0,
                "cached_prompt_tokens": 0,
            },
        ])

        self.assertEqual(summary["llm_calls"], 2)
        self.assertEqual(summary["usage_missing_calls"], 1)
        self.assertEqual(summary["reasoning_usage_missing_calls"], 1)
        self.assertEqual(summary["total_tokens"], 15)

    def test_run_summary_treats_legacy_records_as_missing_usage(self):
        summary = summarize_result_usage([
            {
                "llm_calls": 2,
                "prompt_tokens": 30,
                "completion_tokens": 20,
                "reasoning_tokens": 8,
                "total_tokens": 50,
                "cached_prompt_tokens": 10,
                "usage_missing_calls": 0,
                "reasoning_usage_missing_calls": 0,
            },
            {"llm_calls": 1},
        ])

        self.assertEqual(summary["questions"], 2)
        self.assertEqual(summary["questions_with_complete_usage"], 1)
        self.assertEqual(summary["usage_missing_calls"], 1)
        self.assertEqual(summary["reasoning_usage_missing_calls"], 1)
        self.assertEqual(summary["average_per_question"]["total_tokens"], 25)


class RLMTokenUsageTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_llm_records_provider_usage(self):
        response = types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(
                    message=types.SimpleNamespace(content="FINAL(\"SELECT 1\")"),
                ),
            ],
            usage=types.SimpleNamespace(
                prompt_tokens=20,
                completion_tokens=10,
                total_tokens=30,
                completion_tokens_details=types.SimpleNamespace(
                    reasoning_tokens=6,
                ),
                prompt_tokens_details=types.SimpleNamespace(cached_tokens=5),
            ),
        )
        agent = RLM(model="test/model")

        with patch(
            "src.rlm.core.litellm.acompletion",
            new=AsyncMock(return_value=response),
        ):
            text = await agent._call_llm([{"role": "user", "content": "test"}])

        self.assertEqual(text, 'FINAL("SELECT 1")')
        self.assertEqual(agent.stats["llm_calls"], 1)
        self.assertEqual(agent.stats["reasoning_tokens"], 6)
        self.assertEqual(agent.stats["total_tokens"], 30)
        self.assertEqual(agent.stats["usage_missing_calls"], 0)
        self.assertEqual(agent.stats["reasoning_usage_missing_calls"], 0)
        call = agent.llm_call_usage_snapshot()[0]
        self.assertEqual(call["model"], "test/model")
        self.assertTrue(call["usage_available"])

    async def test_failed_call_is_visible_as_missing_usage(self):
        agent = RLM(model="test/model")

        with patch(
            "src.rlm.core.litellm.acompletion",
            new=AsyncMock(side_effect=TimeoutError("timeout")),
        ):
            with self.assertRaises(TimeoutError):
                await agent._call_llm([{"role": "user", "content": "test"}])

        self.assertEqual(agent.stats["llm_calls"], 1)
        self.assertEqual(agent.stats["usage_missing_calls"], 1)
        self.assertEqual(agent.stats["reasoning_usage_missing_calls"], 1)
        call = agent.llm_call_usage_snapshot()[0]
        self.assertFalse(call["usage_available"])
        self.assertEqual(call["error"], "TimeoutError")

    async def test_parent_totals_include_recursive_child_calls(self):
        parent = RLM(model="parent/model")
        child = RLM(model="child/model", _current_depth=1)
        child._llm_calls = 1
        child._record_llm_call(
            model="child/model",
            latency_seconds=0.1,
            usage={
                "usage_available": True,
                "reasoning_tokens_available": True,
                "prompt_tokens": 11,
                "completion_tokens": 4,
                "reasoning_tokens": 2,
                "total_tokens": 15,
                "cached_prompt_tokens": 3,
            },
        )

        parent._absorb_child_usage(child)

        self.assertEqual(parent.stats["llm_calls"], 1)
        self.assertEqual(parent.stats["total_tokens"], 15)
        call = parent.llm_call_usage_snapshot()[0]
        self.assertEqual(call["depth"], 1)
        self.assertEqual(call["sequence"], 1)


if __name__ == "__main__":
    unittest.main()
