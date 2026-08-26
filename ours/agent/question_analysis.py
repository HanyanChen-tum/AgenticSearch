"""A required first turn that reads the question, before any SQL is written.

Motivated by the 46-question root cause pass
(docs/analysis/week_2026-08-18/flatzero_23_root_causes_2026-08-25.md). Grouping
those failures by mechanism, 18 of 46 are things the question itself states and
the model did not act on: it says "at least once" and the model counts rows
instead of entities (6), it names a filter the model never writes (4, most
starkly bird_48's "merged"), it says "percentage" and the model omits the ×100
(3), it asks two things and one is answered (2), plus outright misreadings (3).

Two prior attempts define the shape this must NOT take:

  * E4-A (root-query-plan-v1) required 20 fields before submitting, including
    joins, filters, group_by and having. That is pre-committing an
    implementation, not reading a question, and it measured -3.05pp while making
    its own target class worse (docs/analysis/analysisDetail/
    e4_a_core197_run1_vs_e3c_e0.md).
  * Five separate attempts at post-hoc verification were all net negative
    (reasoning_trace_findings_2026-08-12 §6.4). Whatever this does, it has to
    happen before the first query, not after an answer exists.

So the fields here are only about the question: what to return, what is being
counted, which conditions the question states outright, what units the answer is
in, and what the question leaves genuinely open. Nothing about tables, joins, or
SQL. Five fields, not twenty.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

QUESTION_ANALYSIS_MODE = "question-analysis-v1"
# Same analysis block, but the SQL is checked against it at FINAL. Stage one
# showed the analysis alone is inert (-3.3pp): nothing connects it to the
# generation that follows. See ours/agent/analysis_gate.py.
QUESTION_ANALYSIS_GATED_MODE = "question-analysis-gated-v1"
QUESTION_ANALYSIS_SCHEMA_VERSION = 1

_BLOCK_PATTERN = re.compile(
    r"```question-analysis\s*\n(?P<body>[\s\S]*?)\n```",
    re.IGNORECASE,
)

# Each field exists because a measured failure class needs it. Keeping the
# mapping here (rather than only in the prompt) means a later reader can tell
# what a field was for without digging through the analysis docs.
REQUIRED_FIELDS: dict[str, str] = {
    "answer_shape": "how many columns to return and what each one is",
    "counting_unit": "whether the question counts entities or table rows",
    "stated_conditions": "conditions the question states outright",
    "unit_and_scale": "units, percentage, and whether a x100 is required",
    "ambiguities": "what the question leaves genuinely open",
}
_LIST_FIELDS = {"stated_conditions", "ambiguities"}


@dataclass
class QuestionAnalysisState:
    analysis: dict[str, Any] | None = None
    attempts: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)


def protocol_manifest(mode: str = QUESTION_ANALYSIS_MODE) -> dict[str, Any]:
    return {
        "schema_version": QUESTION_ANALYSIS_SCHEMA_VERSION,
        "mode": mode,
        "required_fields": sorted(REQUIRED_FIELDS),
        "stage": "before-first-query",
        "describes": "the question only; no tables, joins or SQL",
        "gated": mode == QUESTION_ANALYSIS_GATED_MODE,
    }


def parse_analysis(response: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract and validate the analysis block. Returns (payload, errors)."""
    match = _BLOCK_PATTERN.search(response or "")
    if not match:
        return None, ["no fenced question-analysis block found"]
    try:
        payload = json.loads(match.group("body"))
    except json.JSONDecodeError as exc:
        return None, [f"question-analysis block is not valid JSON: {exc.msg}"]
    if not isinstance(payload, dict):
        return None, ["question-analysis block must be a JSON object"]

    errors: list[str] = []
    missing = sorted(set(REQUIRED_FIELDS) - set(payload))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    for name in _LIST_FIELDS & set(payload):
        if not isinstance(payload[name], list):
            errors.append(f"{name} must be a list (use [] if there are none)")
    for name in (set(REQUIRED_FIELDS) - _LIST_FIELDS) & set(payload):
        if not isinstance(payload[name], str) or not payload[name].strip():
            errors.append(f"{name} must be a non-empty string")
    unknown = sorted(set(payload) - set(REQUIRED_FIELDS))
    if unknown:
        # Not an error: extra keys are harmless and refusing them would make the
        # model retry over something that does not affect the answer.
        payload = {k: v for k, v in payload.items() if k in REQUIRED_FIELDS}
    return (None, errors) if errors else (payload, [])


def retry_instruction(errors: list[str]) -> str:
    fields = "\n".join(f'  "{name}": ...   // {why}' for name, why in REQUIRED_FIELDS.items())
    return (
        "Your question-analysis block was not accepted: "
        + "; ".join(errors)
        + "\n\nReply with only a fenced ```question-analysis block containing a JSON "
        "object with exactly these keys:\n" + fields
        + '\n\n"stated_conditions" and "ambiguities" are lists (use [] if none). '
        "Do not write any SQL or Python yet."
    )
