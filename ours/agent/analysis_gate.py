"""Check the final SQL against the model's own question analysis.

Stage one (question_analysis_stage1_2026-08-26.md) measured -3.3pp for simply
asking the model to analyse the question first, and found why: on those 46
questions the model goes system -> question -> FINAL in a single turn, 38 of 46
without touching the database. An analysis inserted into that flow is one more
paragraph of preamble; nothing makes it constrain the generation that follows.
E4-A failed the same way for the same structural reason.

So this takes the analysis the model already produced and turns it into a check
applied at FINAL -- the same place keep_ties and printf_to_round act, which are
the two changes that measured positive this week.

The first version of this gate was syntactic: analysis says entities, SQL has a
COUNT without DISTINCT, block. That fired on 21.7-26.1% of questions and most of
it was collateral -- bird_227 fails on printf's return type, bird_85 on float
ordering, bird_604 on a NULL denominator, and adding DISTINCT fixes none of them.
It did work where it was aimed (bird_416 was blocked, rewritten to
COUNT(DISTINCT cards.uuid) with a LEFT JOIN, and matched gold to the last digit),
but the collateral raised the per-question flip rate from 15% to 26%, which on a
46-question sample buries the effect.

None of the cheap syntactic proxies separate the two groups: a JOIN's presence
does not (bird_85 and bird_604 join and are still collateral; bird_1243 does not
join and is a real case), and neither does the row count.

What does separate them is the property that actually defines the failure --
whether the counted key repeats in the query's own row set. bird_416's FROM/JOIN/
WHERE yields 128,569 rows over 31,053 distinct cards, so counting rows inflates
by 4.14x. bird_604's yields 1,165 rows over 1,165 users, so it inflates by
nothing and DISTINCT is irrelevant to what it got wrong.

That test needs to know which column identifies an entity, which the query itself
does not say -- so the analysis block asks the model for it (`entity_key`), and
the gate executes the check rather than guessing.
"""

from __future__ import annotations

import re
from typing import Any, Callable

import sqlglot
from sqlglot import exp

_ENTITY_CLAIM = re.compile(
    r"entit|unique (individual|people|person|card|player|patient)"
    r"|not (raw |table )?rows|rather than (raw |table )?rows"
    r"|count(ed)? once|distinct",
    re.IGNORECASE,
)
_HEDGE = re.compile(
    r"\bthough\b|\bhowever\b|\bcould be read\b|\bunless\b|\bif the question\b"
    r"|\bambiguous\b|\bor(?: the)? hint\b|\bmight\b",
    re.IGNORECASE,
)
_COUNT_DISTINCT = re.compile(r"COUNT\s*\(\s*DISTINCT\b", re.IGNORECASE)
_COUNT_ANY = re.compile(r"\bCOUNT\s*\(", re.IGNORECASE)
_QUALIFIED_COLUMN = re.compile(r"^[A-Za-z_][\w$]*\.[A-Za-z_][\w$]*$")

# Below this, counting rows and counting entities give the same answer, so the
# analysis and the SQL do not actually disagree about anything.
INFLATION_THRESHOLD = 1.0


def claims_entity_counting(analysis: dict[str, Any] | None) -> bool:
    """Whether the analysis unambiguously committed to entity-level counting."""
    if not analysis:
        return False
    text = str(analysis.get("counting_unit") or "")
    if not text.strip() or _HEDGE.search(text):
        return False
    return bool(_ENTITY_CLAIM.search(text))


def entity_key(analysis: dict[str, Any] | None) -> str | None:
    """The model's stated entity key, if it gave a usable one."""
    if not analysis:
        return None
    key = str(analysis.get("entity_key") or "").strip().strip("`\"'")
    if not key or key.lower() in {"n/a", "na", "none", "-"}:
        return None
    return key if _QUALIFIED_COLUMN.match(key) else None


def inflation_probe(sql: str, key: str) -> str | None:
    """Build `SELECT COUNT(*), COUNT(DISTINCT key)` over the query's own rows."""
    try:
        tree = sqlglot.parse_one(sql, dialect="sqlite")
    except Exception:
        return None
    if not isinstance(tree, exp.Select):
        return None
    probe = tree.copy()
    for slot in ("order", "limit", "group", "having"):
        probe.set(slot, None)
    probe.set("expressions", [
        exp.alias_(exp.Count(this=exp.Star()), "rows"),
        exp.alias_(exp.Count(this=exp.column(*reversed(key.split(".", 1))), distinct=True), "keys"),
    ])
    try:
        return probe.sql(dialect="sqlite")
    except Exception:
        return None


def contradicts_analysis(
    sql: str,
    analysis: dict[str, Any] | None,
    execute: Callable[[str], dict[str, Any]] | None = None,
) -> str | None:
    """Return a reason to reject `sql`, or None to let it through.

    Without `execute` the check cannot run and the gate stays silent: a syntactic
    guess is what made the first version fire on collateral.
    """
    if not claims_entity_counting(analysis):
        return None
    statement = sql or ""
    if not _COUNT_ANY.search(statement) or _COUNT_DISTINCT.search(statement):
        return None
    key = entity_key(analysis)
    if key is None or execute is None:
        return None
    probe = inflation_probe(statement, key)
    if probe is None:
        return None
    result = execute(probe)
    if result.get("error") or not result.get("answer"):
        return None
    rows, keys = result["answer"][0][0] or 0, result["answer"][0][1] or 0
    if not keys or rows / keys <= INFLATION_THRESHOLD:
        return None
    return (
        f"Your own analysis said the question counts entities, not table rows "
        f"(counting_unit: {analysis.get('counting_unit')!r}), identifying them by "
        f"{key}. Executed, this query's rows contain {rows} records over only "
        f"{keys} distinct {key} values -- counting rows inflates the answer by "
        f"{rows / keys:.2f}x. Either count with COUNT(DISTINCT {key}), or, if "
        "rows really are the right unit here, resubmit the same query and say why."
    )
