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


def _generate_with_gemini(
    messages: list[dict[str, str]],
    system_instruction: str,
) -> LLMResponse:
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Add it to .env or your shell environment.")

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
            max_output_tokens=config.MAX_TOKENS,
        ),
    )

    usage = getattr(response, "usage_metadata", None)
    return LLMResponse(
        text=response.text or "",
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
    )


def _generate_with_openai_compatible(
    messages: list[dict[str, str]],
    system_instruction: str,
) -> LLMResponse:
    url = f"{config.LLM_BASE_URL}/chat/completions"
    request_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_instruction},
        *messages,
    ]
    payload = json.dumps(
        {
            "model": config.MODEL,
            "messages": request_messages,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "OpenAI/Python 1.0.0",
    }
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"

    request = Request(url, data=payload, headers=headers, method="POST")
    import time as _time
    for attempt in range(5):
        try:
            with urlopen(request, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as error:
            if error.code == 429 and attempt < 4:
                wait = 2 ** attempt * 10  # 10, 20, 40, 80s
                _time.sleep(wait)
                continue
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Local LLM request failed ({error.code}): {details}") from error
        except URLError as error:
            raise RuntimeError(
                f"Cannot connect to local LLM at {config.LLM_BASE_URL}. "
                "Check that the server is running and LLM_BASE_URL is correct."
            ) from error

    try:
        text = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"Unexpected local LLM response: {result}") from error

    usage = result.get("usage", {})
    return LLMResponse(
        text=text or "",
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
    )


def generate_chat(
    messages: list[dict[str, str]],
    system_instruction: str = SYSTEM_INSTRUCTION,
) -> LLMResponse:
    provider = config.LLM_PROVIDER.lower()
    if provider == "gemini":
        return _generate_with_gemini(messages, system_instruction)
    if provider in {"openai_compatible", "local", "qwen"}:
        return _generate_with_openai_compatible(messages, system_instruction)
    raise ValueError(
        f"Unsupported LLM_PROVIDER: {config.LLM_PROVIDER}. "
        "Use 'gemini' or 'openai_compatible'."
    )


def generate_sql(prompt: str) -> LLMResponse:
    return generate_chat(
        [{"role": "user", "content": prompt}],
        system_instruction=SYSTEM_INSTRUCTION,
    )
