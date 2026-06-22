"""LLM wrappers used by Spider2-Snow baselines."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from spider2_snow_experiments import config


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: Any | None = None


def chat(
    messages: list[dict[str, str]],
    *,
    system_instruction: str | None = None,
    settings: config.Settings | None = None,
    max_tokens: int | None = None,
) -> LLMResponse:
    active_settings = settings or config.get_settings()
    provider = active_settings.llm_provider.lower()
    if provider == "openai_compatible":
        return _chat_openai_compatible(
            messages,
            system_instruction=system_instruction,
            settings=active_settings,
            max_tokens=max_tokens,
        )
    if provider == "gemini":
        return _chat_gemini(
            messages,
            system_instruction=system_instruction,
            settings=active_settings,
            max_tokens=max_tokens,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {active_settings.llm_provider}")


def generate_sql(
    prompt: str,
    *,
    system_instruction: str,
    settings: config.Settings | None = None,
) -> LLMResponse:
    return chat(
        [{"role": "user", "content": prompt}],
        system_instruction=system_instruction,
        settings=settings,
    )


def _chat_openai_compatible(
    messages: list[dict[str, str]],
    *,
    system_instruction: str | None,
    settings: config.Settings,
    max_tokens: int | None,
) -> LLMResponse:
    request_messages = list(messages)
    if system_instruction:
        request_messages = [{"role": "system", "content": system_instruction}] + request_messages

    payload = {
        "model": settings.model,
        "messages": request_messages,
        "temperature": settings.temperature,
        "max_tokens": max_tokens or settings.max_tokens,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    request = Request(
        f"{settings.llm_base_url}/chat/completions",
        data=body,
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

    choice = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return LLMResponse(
        text=choice or "",
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        raw=data,
    )


def _chat_gemini(
    messages: list[dict[str, str]],
    *,
    system_instruction: str | None,
    settings: config.Settings,
    max_tokens: int | None,
) -> LLMResponse:
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ImportError("Install google-genai to use LLM_PROVIDER=gemini.") from exc

    client = genai.Client(api_key=settings.gemini_api_key)
    contents = [
        types.Content(
            role="model" if message["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=message["content"])],
        )
        for message in messages
        if message["role"] != "system"
    ]
    response = client.models.generate_content(
        model=settings.model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=settings.temperature,
            max_output_tokens=max_tokens or settings.max_tokens,
        ),
    )
    usage = getattr(response, "usage_metadata", None)
    return LLMResponse(
        text=response.text or "",
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
        raw=response,
    )

