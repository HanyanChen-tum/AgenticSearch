"""LLM client wrapper."""

from __future__ import annotations

from dataclasses import dataclass

from shared import config


@dataclass
class LLMResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


def generate_sql(prompt: str) -> LLMResponse:
    if config.LLM_PROVIDER == "gemini":
        return _generate_sql_gemini(prompt)

    if config.LLM_PROVIDER == "groq":
        return _generate_sql_groq(prompt)
    if config.LLM_PROVIDER == "ollama":
        return _generate_sql_ollama(prompt)
    raise ValueError(f"Unsupported LLM_PROVIDER: {config.LLM_PROVIDER}")


def _generate_sql_gemini(prompt: str) -> LLMResponse:
    from google import genai
    from google.genai import types

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


def _generate_sql_groq(prompt: str) -> LLMResponse:
    import os
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise ValueError("GROQ_API_KEY is not set. Add it to .env or your shell environment.")

    client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model=config.MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert text-to-SQL assistant. "
                    "Only return executable SQLite SQL. "
                    "Do not provide explanations. Do not use Markdown."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
    )

    usage = getattr(response, "usage", None)

    return LLMResponse(
        text=response.choices[0].message.content or "",
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
    )
def _generate_sql_ollama(prompt: str) -> LLMResponse:
    import json
    import os
    import urllib.request

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    url = f"{base_url}/api/chat"

    payload = {
        "model": config.MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert text-to-SQL assistant. "
                    "Only return executable SQLite SQL. "
                    "Do not provide explanations. Do not use Markdown."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "options": {
            "temperature": config.TEMPERATURE,
            "num_predict": config.MAX_TOKENS,
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=600) as response:
        data = json.loads(response.read().decode("utf-8"))

    text = data.get("message", {}).get("content", "")

    return LLMResponse(
        text=text,
        input_tokens=data.get("prompt_eval_count"),
        output_tokens=data.get("eval_count"),
    )