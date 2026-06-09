"""LLM client wrapper."""

from __future__ import annotations

from dataclasses import dataclass
import json
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


def _generate_with_gemini(prompt: str) -> LLMResponse:
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Add it to .env or your shell environment.")

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=config.MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
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


def _generate_with_openai_compatible(prompt: str) -> LLMResponse:
    url = f"{config.LLM_BASE_URL}/chat/completions"
    payload = json.dumps(
        {
            "model": config.MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"

    request = Request(url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
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


def generate_sql(prompt: str) -> LLMResponse:
    provider = config.LLM_PROVIDER.lower()
    if provider == "gemini":
        return _generate_with_gemini(prompt)
    if provider in {"openai_compatible", "local", "qwen"}:
        return _generate_with_openai_compatible(prompt)
    raise ValueError(
        f"Unsupported LLM_PROVIDER: {config.LLM_PROVIDER}. "
        "Use 'gemini' or 'openai_compatible'."
    )
