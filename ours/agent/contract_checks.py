"""Deterministic checks: the model's own answer contract against what its SQL
actually returned.

Every check here reads the *executed result*, never the SQL text alone. That is
not a style preference -- analysis_gate.py's first version was syntactic
("analysis says entities, SQL has COUNT without DISTINCT, block"), fired on
21.7-26.1% of questions, and most of it was collateral: bird_227 fails on
printf's return type, bird_85 on float ordering, bird_604 on a NULL denominator,
and the rewrite it proposed fixes none of them. A check that cannot tell those
apart raises the flip rate without raising accuracy.

Each check below is aimed at a mechanism counted in the 46-question read
(flatzero_23_root_causes_2026-08-25.md §三) and fires only on evidence that the
mechanism is present in this particular result:

  output_type      contract says numeric, the value came back a str -- the
                   printf('%.Nf') family, 4 of 46, digits identical to gold
  percent_scale    contract says a x100 is required, the value is in [0, 1] --
                   3 of 46, 0.0314 against 3.14
  ties_truncated   contract says every tied row belongs, the query ends in
                   LIMIT 1, and re-running it without the limit puts more than
                   one row at the extreme -- 9 of the 38 no configuration moves

Counting grain stays in analysis_gate.py: it needs an inflation probe rather
than the result, so it does not share this signature.

Each check returns a violation dict or None. Nothing here rewrites SQL -- the
caller decides what a violation is worth, and `repair` is only a suggestion.
"""

from __future__ import annotations

import re
from typing import Any

_LIMIT_ONE = re.compile(r"\bLIMIT\s+1\b\s*;?\s*$", re.IGNORECASE)
_NUMERIC_CLAIM = re.compile(r"\bnumeric\b|\bnumber\b|\bfloat\b|\bint", re.IGNORECASE)
_TEXT_CLAIM = re.compile(r"\btext\b|\bstring\b|\bvarchar\b", re.IGNORECASE)
_SCALE_CLAIM = re.compile(r"x\s*100|\*\s*100|times 100|multiply.*100|percentage", re.IGNORECASE)
_NO_SCALE = re.compile(r"no x100|not a percentage|already.*percent|no multipl", re.IGNORECASE)
_TIES_ALL = re.compile(r"\ball\b|\bevery\b|\bties\b", re.IGNORECASE)


def _field(analysis: dict[str, Any] | None, name: str) -> str:
    if not isinstance(analysis, dict):
        return ""
    value = analysis.get(name)
    return value if isinstance(value, str) else ""


def _first_scalar(result: dict[str, Any] | None):
    """The single returned value, or None when the shape is not one cell."""
    if not isinstance(result, dict) or result.get("error"):
        return None
    rows = result.get("answer") or result.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        return None
    row = rows[0]
    if not isinstance(row, (list, tuple)) or len(row) != 1:
        return None
    return row[0]


def check_output_type(analysis, sql: str, result) -> dict | None:
    claim = _field(analysis, "output_type")
    if not _NUMERIC_CLAIM.search(claim) or _TEXT_CLAIM.search(claim):
        return None
    value = _first_scalar(result)
    if not isinstance(value, str):
        return None
    # A string that is not even numeric is a different failure; this check is
    # only for the case where the digits are right and the type is not.
    try:
        float(value)
    except ValueError:
        return None
    return {
        "type": "OUTPUT_TYPE",
        "expected": "numeric",
        "observed": f"text {value!r}",
        "repair": "return the value with ROUND(x, N) instead of printf('%.Nf', x)",
    }


def check_percent_scale(analysis, sql: str, result) -> dict | None:
    claim = _field(analysis, "unit_and_scale")
    if not _SCALE_CLAIM.search(claim) or _NO_SCALE.search(claim):
        return None
    value = _first_scalar(result)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    # 0 and 1 are legitimate percentages; only the open interval is evidence
    # that the x100 the contract asked for never happened.
    if not (0 < value < 1):
        return None
    return {
        "type": "PERCENT_SCALE",
        "expected": "a percentage (x100 applied)",
        "observed": f"{value!r}, which is in (0, 1)",
        "repair": "multiply the ratio by 100",
    }


def check_ties_truncated(analysis, sql: str, result, execute=None) -> dict | None:
    """Needs `execute` to tell a real tie from a query that returns one row
    because only one row qualifies. Without it the check stays silent."""
    if not _TIES_ALL.search(_field(analysis, "tie_policy")):
        return None
    statement = (sql or "").strip()
    if not _LIMIT_ONE.search(statement) or execute is None:
        return None
    widened = _LIMIT_ONE.sub("LIMIT 50", statement)
    if widened == statement:
        return None
    widened_result = execute(widened)
    if widened_result.get("error"):
        return None
    rows = widened_result.get("answer") or widened_result.get("rows") or []
    distinct = {tuple(r) if isinstance(r, (list, tuple)) else (r,) for r in rows}
    if len(distinct) <= 1:
        return None
    return {
        "type": "TIES_TRUNCATED",
        "expected": "every row tied at the extreme",
        "observed": f"LIMIT 1 kept 1 of {len(distinct)} distinct rows",
        "repair": "drop LIMIT 1 and keep every row at the extreme value",
    }


# Only the head is matched: printf's argument runs to its *matching* paren, and
# a regex cannot find that. `(.+?)\)` stops at the first ')' instead, which on
# real SQL -- printf('%.5f', CAST(SUM(CASE ... END) AS REAL) * 100.0 / COUNT(x))
# -- lands inside SUM() and yields ROUND(CAST(SUM(CASE ... END, 5) AS REAL) ...):
# syntactically live, silently wrong, and it scored 0 rescues where the correct
# rewrite scores 13. Lives here rather than in the scoring script so the agent
# and the offline measurement cannot drift apart on it.
_PRINTF_HEAD = re.compile(r"printf\s*\(\s*'%\.(\d+)f'\s*,\s*", re.IGNORECASE)


def printf_to_round(sql: str) -> tuple[str, int]:
    """Rewrite printf('%.Nf', expr) -> ROUND(expr, N), balancing parens."""
    out, pos, changed = [], 0, 0
    while True:
        m = _PRINTF_HEAD.search(sql, pos)
        if not m:
            out.append(sql[pos:])
            return "".join(out), changed
        depth, i = 1, m.end()
        while i < len(sql) and depth:
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
            i += 1
        if depth:  # unbalanced; leave the remainder untouched
            out.append(sql[pos:])
            return "".join(out), changed
        out.append(sql[pos:m.start()])
        out.append(f"ROUND({sql[m.end():i - 1].strip()}, {m.group(1)})")
        pos, changed = i, changed + 1


def violations(analysis, sql: str, result, execute=None) -> list[dict]:
    """All violations this contract and result support. Empty means let it pass."""
    found = []
    for check in (check_output_type, check_percent_scale):
        hit = check(analysis, sql, result)
        if hit:
            found.append(hit)
    hit = check_ties_truncated(analysis, sql, result, execute=execute)
    if hit:
        found.append(hit)
    return found
