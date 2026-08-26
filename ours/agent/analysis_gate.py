"""Check the final SQL against the model's own question analysis.

Stage one (question_analysis_stage1_2026-08-26.md) measured -3.3pp for simply
asking the model to analyse the question first, and found why: on those 46
questions the model goes system -> question -> FINAL in a single turn, 38 of 46
without touching the database. An analysis inserted into that flow is one more
paragraph of preamble; nothing makes it constrain the generation that follows.
E4-A failed the same way for the same structural reason.

So this does not ask the model to try harder. It takes the analysis the model
already produced, turns one field of it into a decidable check, and applies that
check at FINAL -- the same place keep_ties and printf_to_round act, which are the
two changes that did measure positive this week.

Only `counting_unit` is checked, and only when the model stated it unambiguously.
Across 92 analyses from stage one, 65% say entity-level in so many words, 1% say
row-level, and 34% are too hedged to decide ("patients, though the wording could
be read as lab records"). Firing on a hedge would be inventing a requirement the
model never committed to, so hedges are left alone.

Relation to E1 `verified_final`, which was rejected: E1 required the model to
have already executed the identical string and fired on ~90% of questions,
blocking mostly harmless revisions. This fires only on one specific
contradiction -- the analysis says entities, the SQL counts rows -- so its
trigger rate is bounded by how often that contradiction actually occurs.
"""

from __future__ import annotations

import re
from typing import Any

# "entities, not rows", "unique patients", "counted once", "distinct cards"
_ENTITY_CLAIM = re.compile(
    r"entit|unique (individual|people|person|card|player|patient)"
    r"|not (raw |table )?rows|rather than (raw |table )?rows"
    r"|count(ed)? once|distinct",
    re.IGNORECASE,
)
# Hedging that withdraws the claim: the model is unsure, so we hold no claim.
_HEDGE = re.compile(
    r"\bthough\b|\bhowever\b|\bcould be read\b|\bunless\b|\bif the question\b"
    r"|\bambiguous\b|\bor(?: the)? hint\b|\bmight\b",
    re.IGNORECASE,
)
_COUNT_DISTINCT = re.compile(r"COUNT\s*\(\s*DISTINCT\b", re.IGNORECASE)
# A count is only at stake if the query counts at all.
_COUNT_ANY = re.compile(r"\bCOUNT\s*\(", re.IGNORECASE)


def claims_entity_counting(analysis: dict[str, Any] | None) -> bool:
    """Whether the analysis unambiguously committed to entity-level counting."""
    if not analysis:
        return False
    text = str(analysis.get("counting_unit") or "")
    if not text.strip() or _HEDGE.search(text):
        return False
    return bool(_ENTITY_CLAIM.search(text))


def contradicts_analysis(sql: str, analysis: dict[str, Any] | None) -> str | None:
    """Return a reason to reject `sql`, or None to let it through.

    Conservative by construction: silent unless the analysis made a clear
    entity-level claim and the SQL counts something without a DISTINCT.
    """
    if not claims_entity_counting(analysis):
        return None
    statement = sql or ""
    if not _COUNT_ANY.search(statement):
        return None
    if _COUNT_DISTINCT.search(statement):
        return None
    return (
        "Your own analysis said the question counts entities, not table rows "
        f"(counting_unit: {analysis.get('counting_unit')!r}), but this query "
        "counts rows -- COUNT(...) without DISTINCT. If one entity can appear on "
        "several rows here, the count is inflated. Either use COUNT(DISTINCT "
        "<entity key>), or, if rows really are the right unit for this question, "
        "resubmit the same query and say why."
    )
