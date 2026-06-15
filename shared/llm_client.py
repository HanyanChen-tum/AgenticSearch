"""LLM client wrapper."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from google import genai
from google.genai import types

from shared import config


SYSTEM_INSTRUCTION = (
    "You are an expert text-to-SQL assistant. "
    "Only return executable SQL. Do not provide explanations."
)


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

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ImportError(
            "google-genai is required for Gemini calls. "
            "Install project dependencies with: pip install -r requirements.txt"
        ) from exc

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    contents = [
        types.Content(
            role="model" if message["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=message["content"])],
        )
        for message in messages
    ]
    response = client.models.generate_content(
        model=config.MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=config.TEMPERATURE,
            max_output_tokens=max_output_tokens or config.MAX_TOKENS,
        ),
    )

    usage = getattr(response, "usage_metadata", None)
    return LLMResponse(
        text=response.text or "",
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
    )
