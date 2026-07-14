"""Resolve LiteLLM settings from the environment without exposing secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LLMConfig:
    model: str
    api_key: str | None
    api_base: str | None
    api_version: str | None


def _first(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = env.get(name)
        if value and value.strip():
            return value.strip()
    return None


def resolve_llm_config(
    model_override: str | None = None,
    api_base_override: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> LLMConfig:
    """Support both project-standard and legacy lowercase Azure variables."""
    env = environ if environ is not None else os.environ
    endpoint = api_base_override or _first(
        env,
        "LLM_BASE_URL",
        "AZURE_API_BASE",
        "AZURE_OPENAI_ENDPOINT",
        "azure_endpoint",
    )
    deployment = _first(env, "AZURE_DEPLOYMENT", "deployment")
    configured_model = _first(env, "MODEL", "model_name")
    model = model_override or (
        f"azure/{deployment}" if deployment else configured_model
    ) or "azure/seminar-gpt-5.4-mini"
    if "/" not in model and endpoint:
        model = f"azure/{model}"

    api_key = _first(
        env,
        "LLM_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "api_key",
    )
    api_version = _first(
        env,
        "LLM_API_VERSION",
        "AZURE_API_VERSION",
        "api_version",
    )

    if model.startswith("azure/"):
        missing = []
        if not api_key:
            missing.append(
                "LLM_API_KEY (or AZURE_OPENAI_API_KEY/api_key)"
            )
        if not endpoint:
            missing.append(
                "LLM_BASE_URL (or AZURE_OPENAI_ENDPOINT/azure_endpoint)"
            )
        if missing:
            raise ValueError(
                "Missing Azure configuration: " + ", ".join(missing)
            )

    return LLMConfig(
        model=model,
        api_key=api_key,
        api_base=endpoint,
        api_version=api_version,
    )
