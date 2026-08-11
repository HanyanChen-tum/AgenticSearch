"""Record the sampling parameters the provider actually receives.

A run manifest that stores the requested parameters can be wrong about what was
run. `litellm.drop_params = True` silently removes anything the provider rejects,
and gpt-5 deployments reject `temperature=0` outright -- only 1 is accepted. Every
run in this project recorded `temperature: 0` while the request carried no
temperature at all, so the provider default applied.

That mattered: the 6-question rerun variance and the 10.7% byte-identical SQL rate
were attributed to hidden reasoning varying between calls, when the simpler cause
was that sampling was never pinned.
"""

from __future__ import annotations

from typing import Any


def effective_sampling_params(
    model: str, temperature: float | None, reasoning_effort: str | None
) -> dict[str, Any]:
    """Ask litellm what it would actually send for these arguments."""
    try:
        import litellm
        from litellm.utils import get_optional_params

        provider = "azure" if str(model).startswith("azure") or "azure" in str(model) else None
        bare = str(model).split("/", 1)[-1]
        kwargs: dict[str, Any] = {"model": bare}
        if provider:
            kwargs["custom_llm_provider"] = provider
        if temperature is not None:
            kwargs["temperature"] = temperature
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        sent = get_optional_params(**kwargs)
    except Exception as exc:  # never let bookkeeping break a run
        return {"resolved": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    sent = {k: v for k, v in dict(sent).items() if v not in (None, {}, [])}
    return {
        "resolved": True,
        "drop_params_enabled": bool(getattr(__import__("litellm"), "drop_params", False)),
        "params": sent,
        "temperature_sent": "temperature" in sent,
        # Absent means the provider default applies, which for gpt-5 is 1 -- i.e.
        # sampled, not greedy. Any claim of determinism is false when this is False.
        "sampling_is_pinned": "temperature" in sent and sent.get("temperature") == 0,
    }
