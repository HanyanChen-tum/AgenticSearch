"""Normalize and aggregate token usage across LiteLLM providers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable


TOKEN_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "total_tokens",
    "cached_prompt_tokens",
)


def empty_token_usage() -> dict[str, int]:
    return {field: 0 for field in TOKEN_FIELDS}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _token_count(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def extract_response_usage(response: Any) -> dict[str, int | bool]:
    """Return one normalized usage record from a LiteLLM response.

    Reasoning tokens are a subset of completion tokens for OpenAI-compatible
    responses and therefore are not added again when deriving total_tokens.
    """
    usage = _get(response, "usage")
    raw_prompt_tokens = _token_count(_get(usage, "prompt_tokens"))
    if raw_prompt_tokens is None:
        raw_prompt_tokens = _token_count(_get(usage, "input_tokens"))
    raw_completion_tokens = _token_count(_get(usage, "completion_tokens"))
    if raw_completion_tokens is None:
        raw_completion_tokens = _token_count(_get(usage, "output_tokens"))

    prompt_tokens = raw_prompt_tokens or 0
    completion_tokens = raw_completion_tokens or 0

    completion_details = _get(usage, "completion_tokens_details")
    if completion_details is None:
        completion_details = _get(usage, "output_tokens_details")
    raw_reasoning_tokens = _token_count(
        _get(completion_details, "reasoning_tokens")
    )
    if raw_reasoning_tokens is None:
        raw_reasoning_tokens = _token_count(_get(usage, "reasoning_tokens"))
    reasoning_tokens = raw_reasoning_tokens or 0

    prompt_details = _get(usage, "prompt_tokens_details")
    if prompt_details is None:
        prompt_details = _get(usage, "input_tokens_details")
    cached_prompt_tokens = _token_count(_get(prompt_details, "cached_tokens"))
    if cached_prompt_tokens is None:
        cached_prompt_tokens = _token_count(_get(usage, "cached_prompt_tokens"))
    if cached_prompt_tokens is None:
        cached_prompt_tokens = _token_count(_get(usage, "cache_read_input_tokens"))
    if cached_prompt_tokens is None:
        cached_prompt_tokens = _token_count(_get(usage, "prompt_cache_hit_tokens"))
    cached_prompt_tokens = cached_prompt_tokens or 0

    raw_total_tokens = _token_count(_get(usage, "total_tokens"))
    available = usage is not None and any(value is not None for value in (
        raw_prompt_tokens,
        raw_completion_tokens,
        raw_total_tokens,
        raw_reasoning_tokens,
    ))
    total_tokens = raw_total_tokens
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens

    return {
        "usage_available": available,
        "reasoning_tokens_available": raw_reasoning_tokens is not None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "cached_prompt_tokens": cached_prompt_tokens,
    }


def aggregate_call_usage(
    calls: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    records = list(calls)
    totals = empty_token_usage()
    for call in records:
        for field in TOKEN_FIELDS:
            totals[field] += _token_count(call.get(field)) or 0
    return {
        **totals,
        "llm_calls": len(records),
        "usage_missing_calls": sum(
            1 for call in records if not call.get("usage_available", False)
        ),
        "reasoning_usage_missing_calls": sum(
            1 for call in records
            if not call.get("reasoning_tokens_available", False)
        ),
    }


def summarize_result_usage(
    results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a run-level summary from per-question result records."""
    records = list(results)
    totals = empty_token_usage()
    llm_calls = 0
    missing_calls = 0
    reasoning_missing_calls = 0
    complete_questions = 0

    for record in records:
        for field in TOKEN_FIELDS:
            totals[field] += _token_count(record.get(field)) or 0
        question_calls = _token_count(record.get("llm_calls")) or 0
        question_missing = _token_count(record.get("usage_missing_calls"))
        if question_missing is None:
            question_missing = question_calls
        question_reasoning_missing = _token_count(
            record.get("reasoning_usage_missing_calls")
        )
        if question_reasoning_missing is None:
            question_reasoning_missing = question_calls
        llm_calls += question_calls
        missing_calls += question_missing
        reasoning_missing_calls += question_reasoning_missing
        if question_calls > 0 and question_missing == 0:
            complete_questions += 1

    question_count = len(records)
    averages = {
        field: round(totals[field] / question_count, 2) if question_count else 0
        for field in TOKEN_FIELDS
    }
    return {
        **totals,
        "llm_calls": llm_calls,
        "usage_missing_calls": missing_calls,
        "reasoning_usage_missing_calls": reasoning_missing_calls,
        "questions": question_count,
        "questions_with_complete_usage": complete_questions,
        "average_per_question": averages,
    }
