"""LLM client wrapper."""

from __future__ import annotations

from dataclasses import dataclass

from google import genai
from google.genai import types

from shared import config


@dataclass
class LLMResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


def generate_sql(prompt: str) -> LLMResponse:
    if config.LLM_PROVIDER != "gemini":
        raise ValueError(f"Unsupported LLM_PROVIDER: {config.LLM_PROVIDER}")

    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Add it to .env or your shell environment.")

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=config.MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are an expert text-to-SQL assistant. "
                "Only return executable SQL. Do not provide explanations."
            ),
            temperature=config.TEMPERATURE,
            max_output_tokens=config.MAX_TOKENS,
        ),
    )

    usage = getattr(response, "usage_metadata", None)
    return LLMResponse(
        text=response.text or "",
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
    )
