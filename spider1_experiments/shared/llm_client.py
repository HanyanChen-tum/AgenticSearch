"""LLM client wrapper for Spider 1.0 experiments."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from spider1_experiments.shared import config


SYSTEM_INSTRUCTION = (
    "You are an expert text-to-SQL assistant. "
    "Only return executable SQLite SQL. Do not provide explanations."
)


@dataclass
class LLMResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: Any | None = None


def generate_sql(prompt: str) -> LLMResponse:
    return generate_chat(
        [{"role": "user", "content": prompt}],
        system_instruction=SYSTEM_INSTRUCTION,
    )


def generate_response(prompt: str, system_instruction: str | None = None) -> LLMResponse:
    return generate_chat(
        [{"role": "user", "content": prompt}],
        system_instruction=system_instruction or SYSTEM_INSTRUCTION,
    )


def generate_chat(
    messages: list[dict[str, str]],
    *,
    system_instruction: str | None = None,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    provider = config.LLM_PROVIDER.lower()
    if provider == "gemini":
        return _generate_gemini(
            messages,
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
        )
    if provider == "openai_compatible":
        return _generate_openai_compatible(
            messages,
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {config.LLM_PROVIDER}")


def _generate_openai_compatible(
    messages: list[dict[str, str]],
    *,
    system_instruction: str | None,
    max_output_tokens: int | None,
) -> LLMResponse:
    request_messages = list(messages)
    if system_instruction:
        request_messages = [{"role": "system", "content": system_instruction}] + request_messages

    payload = {
        "model": config.MODEL,
        "messages": request_messages,
        "temperature": config.TEMPERATURE,
        "max_tokens": max_output_tokens or config.MAX_TOKENS,
    }
    headers = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"

    request = Request(
        f"{config.LLM_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=600) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"LLM endpoint unavailable: {error}") from error

    usage = data.get("usage") or {}
    return LLMResponse(
        text=data["choices"][0]["message"]["content"] or "",
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        raw=data,
    )


def _generate_gemini(
    messages: list[dict[str, str]],
    *,
    system_instruction: str | None,
    max_output_tokens: int | None,
) -> LLMResponse:
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Add it to .env or your shell environment.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ImportError(
            "google-genai is required for Gemini calls. "
            "Install project dependencies with: pip install -r spider1_experiments/requirements.txt"
        ) from exc

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    contents = [
        types.Content(
            role="model" if message["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=message["content"])],
        )
        for message in messages
        if message["role"] != "system"
    ]
    response = client.models.generate_content(
        model=config.MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction or SYSTEM_INSTRUCTION,
            temperature=config.TEMPERATURE,
            max_output_tokens=max_output_tokens or config.MAX_TOKENS,
        ),
    )
    usage = getattr(response, "usage_metadata", None)
    return LLMResponse(
        text=response.text or "",
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
        raw=response,
    )
