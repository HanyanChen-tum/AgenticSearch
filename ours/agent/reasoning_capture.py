"""Capture the model's reasoning at generation time, via the Responses API.

The Chat Completions deployment reports `reasoning_tokens` but never the reasoning,
so 86% of what the model produced has been invisible for the whole project.

Replaying a recorded prompt afterwards does not fix that. Sampling is not pinned
here (`SYNTHESIS.md` 4.5), so a replay returns *a* reasoning chain for that input,
not the one that produced the recorded answer -- measured on bird_93, where the
replay went and queried the database while the original run never did. Only
capturing during the run ties reasoning to the answer it actually produced.

This is opt-in. Switching the API path could shift the output distribution, and
every baseline in this project was measured on Chat Completions, so a profile that
turns this on is a diagnostic configuration whose accuracy is not comparable to
the others until that is checked.
"""

from __future__ import annotations

from typing import Any

# The deployment's configured api-version predates the Responses API. Requesting
# a newer one per call avoids editing .env and disturbing every other call path.
RESPONSES_API_VERSION = "2025-03-01-preview"
CAPTURE_MODE = "responses-summary-v1"


def split_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Chat messages -> (instructions, input) as the Responses API wants them."""
    instructions = "\n\n".join(
        m["content"] for m in messages if m.get("role") == "system" and m.get("content")
    )
    body = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") != "system" and m.get("content") is not None
    ]
    return instructions, body


def parse_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull the assistant text and the reasoning sections out of one response."""
    sections: list[str] = []
    text: list[str] = []
    for item in payload.get("output") or []:
        kind = item.get("type")
        if kind == "reasoning":
            for part in item.get("summary") or []:
                if part.get("text"):
                    sections.append(part["text"])
        elif kind == "message":
            for part in item.get("content") or []:
                if part.get("text"):
                    text.append(part["text"])
    usage = payload.get("usage") or {}
    details = usage.get("output_tokens_details") or {}
    return {
        "text": "\n".join(text),
        "reasoning_sections": sections,
        "section_count": len(sections),
        # Sections are a summary, not the raw chain: the token count is what the
        # model actually spent, and it is far larger than the summary.
        "reasoning_tokens": details.get("reasoning_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "input_tokens": usage.get("input_tokens"),
    }


def manifest() -> dict[str, Any]:
    return {
        "mode": CAPTURE_MODE,
        "api": "responses",
        "api_version": RESPONSES_API_VERSION,
        "summary": "detailed",
        "captures_raw_reasoning": False,
        "note": (
            "Reasoning arrives as summary sections, not the raw reasoning tokens; "
            "this deployment does not return those. Accuracy from this path is not "
            "directly comparable to Chat Completions runs."
        ),
    }
