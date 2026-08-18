"""Deterministic post-processing of final SQL toward BIRD's writing conventions.

This is a harness component, not a model instruction.  Measured on the 197-question
core set, e3-ac carries "consider whether DISTINCT is required" and "verify the
ORDER BY direction" in its prompt and violates those conventions as often as e3-c,
which carries neither (24 vs 25 violations).  Applying the same conventions here
instead moves questions.

Every rewrite is recorded with the rule that fired and the before/after SQL, so a
run's accuracy can always be decomposed into model output and harness rewriting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


VERSION = "train-conventions-v1"
DIALECT = "sqlite"
_DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "processed" / "sql_conventions_v1.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class ConventionRewrite:
    sql: str
    original_sql: str
    applied: tuple[str, ...] = ()
    parse_failed: bool = False
    notes: tuple[str, ...] = field(default=())

    @property
    def changed(self) -> bool:
        return self.sql != self.original_sql


# --------------------------------------------------------------------------
# Rewrite rules.  Each takes a parsed tree and mutates it in place, returning
# whether it fired.  They are deliberately conservative: when the shape is not
# exactly the one the convention was mined on, they decline rather than guess.
# --------------------------------------------------------------------------

def _rule_count_no_distinct(tree: exp.Expression) -> bool:
    """COUNT(DISTINCT x) -> COUNT(x), only when the query joins.

    Without a join there is no join-induced duplication, so a DISTINCT the model
    wrote is far more likely to be genuinely requested by the question.
    """
    if not list(tree.find_all(exp.Join)):
        return False
    fired = False
    for count in tree.find_all(exp.Count):
        inner = count.this
        if isinstance(inner, exp.Distinct):
            targets = inner.expressions or ([inner.this] if inner.this else [])
            if len(targets) != 1:
                continue
            count.set("this", targets[0])
            fired = True
        elif count.args.get("distinct"):
            count.set("distinct", False)
            fired = True
    return fired


def _flatten_dpipe(node: exp.Expression) -> list[exp.Expression]:
    if isinstance(node, exp.DPipe):
        return _flatten_dpipe(node.left) + _flatten_dpipe(node.right)
    return [node]


def _is_separator(node: exp.Expression) -> bool:
    return isinstance(node, exp.Literal) and node.args.get("is_string")


def _alias_is_referenced(
    select: exp.Select, alias: str, root: exp.Expression | None = None
) -> bool:
    """Is this projection alias consumed anywhere the split would break?

    Splitting `a || ' ' || b AS full_name` removes the name `full_name`, so any
    surviving reference to it stops resolving.  Two places can hold one:

    1. this SELECT's own ORDER BY / GROUP BY / HAVING;
    2. an *enclosing* query reading it off a subquery, as in
       `SELECT full_name FROM (SELECT a || ' ' || b AS full_name ...) AS t`.

    Only (1) was checked originally, so bird_1011 -- which is exactly shape (2)
    -- got split anyway and failed with `no such column: full_name`, despite
    being named here as the case this guard existed for.

    With `root`, any column of that name outside this SELECT's own projections
    counts, qualified or not.  A false positive costs one unapplied rewrite; a
    false negative costs a hard SQL error, so the check errs wide.
    """
    folded = alias.casefold()
    for key in ("order", "group", "having", "qualify", "distinct"):
        node = select.args.get(key)
        if node is None or node is False:
            continue
        for column in node.find_all(exp.Column):
            if not column.table and column.name.casefold() == folded:
                return True
    if root is not None and root is not select:
        own = {id(c) for proj in select.expressions for c in proj.find_all(exp.Column)}
        for column in root.find_all(exp.Column):
            if id(column) not in own and column.name.casefold() == folded:
                return True
    return False


def _rule_no_select_concat(tree: exp.Expression) -> bool:
    """`a || ' ' || b` in a SELECT list -> two separate projections."""
    fired = False
    for select in tree.find_all(exp.Select):
        rebuilt: list[exp.Expression] = []
        changed = False
        for projection in select.expressions:
            body = projection.this if isinstance(projection, exp.Alias) else projection
            if not isinstance(body, exp.DPipe):
                rebuilt.append(projection)
                continue
            if isinstance(projection, exp.Alias) and _alias_is_referenced(
                select, projection.alias, root=tree
            ):
                rebuilt.append(projection)
                continue
            parts = [p for p in _flatten_dpipe(body) if not _is_separator(p)]
            if len(parts) < 2:
                rebuilt.append(projection)
                continue
            rebuilt.extend(part.copy() for part in parts)
            changed = True
        if changed:
            select.set("expressions", rebuilt)
            fired = True
    return fired


def _bare_aggregate_subquery(node: exp.Expression) -> exp.Expression | None:
    """Return the MAX/MIN of `(SELECT MAX(x) FROM t)`, or None if not that shape."""
    if not isinstance(node, exp.Subquery):
        return None
    inner = node.this
    if not isinstance(inner, exp.Select):
        return None
    if any(inner.args.get(key) for key in ("where", "group", "joins", "having", "order", "limit")):
        return None
    if len(inner.expressions) != 1:
        return None
    agg = inner.expressions[0]
    if isinstance(agg, exp.Alias):
        agg = agg.this
    return agg if isinstance(agg, (exp.Max, exp.Min)) else None


def _rule_superlative_order_limit(tree: exp.Expression) -> bool:
    """`WHERE x = (SELECT MAX(x) FROM t)` -> `ORDER BY x DESC LIMIT 1`.

    Declines whenever the outer query already ranks or groups, or the subquery
    carries conditions of its own -- in those shapes the two forms are not the
    near-equivalents the convention was mined on.
    """
    if not isinstance(tree, exp.Select):
        return False
    if any(tree.args.get(key) for key in ("order", "limit", "group", "having")):
        return False
    where = tree.args.get("where")
    if not where:
        return False

    condition = where.this
    conjuncts = list(condition.flatten()) if isinstance(condition, exp.And) else [condition]

    target = None
    for conjunct in conjuncts:
        if not isinstance(conjunct, exp.EQ):
            continue
        for outer_side, sub_side in ((conjunct.left, conjunct.right), (conjunct.right, conjunct.left)):
            agg = _bare_aggregate_subquery(sub_side)
            if agg is not None:
                target = (conjunct, outer_side, agg)
                break
        if target:
            break
    if target is None:
        return False

    conjunct, outer_expr, agg = target
    remaining = [c for c in conjuncts if c is not conjunct]
    if remaining:
        rebuilt = remaining[0].copy()
        for extra in remaining[1:]:
            rebuilt = exp.And(this=rebuilt, expression=extra.copy())
        tree.set("where", exp.Where(this=rebuilt))
    else:
        tree.set("where", None)

    tree.set("order", exp.Order(expressions=[
        exp.Ordered(this=outer_expr.copy(), desc=isinstance(agg, exp.Max))
    ]))
    tree.set("limit", exp.Limit(expression=exp.Literal.number(1)))
    return True


_RULES = {
    "count_no_distinct": _rule_count_no_distinct,
    "no_select_concat": _rule_no_select_concat,
    "superlative_order_limit": _rule_superlative_order_limit,
}


class SqlConventionRewriter:
    """Applies the enabled mined conventions to a final SQL string."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self.path = Path(path).resolve()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("version") != VERSION:
            raise ValueError(f"Unsupported convention artifact: {payload.get('version')!r}")
        self._payload = payload
        self._conventions: dict[str, dict[str, Any]] = payload.get("conventions", {})
        unknown = set(self._conventions) - set(_RULES)
        if unknown:
            raise ValueError(f"Artifact declares conventions with no rewrite rule: {sorted(unknown)}")

    @property
    def enabled_conventions(self) -> tuple[str, ...]:
        return tuple(
            name for name in sorted(self._conventions)
            if self._conventions[name].get("enabled")
        )

    def rewrite(self, sql: str) -> ConventionRewrite:
        original = (sql or "").strip()
        if not original:
            return ConventionRewrite(sql=original, original_sql=original)
        try:
            tree = sqlglot.parse_one(original, read=DIALECT)
        except Exception:
            # An unparseable prediction is left exactly as the model wrote it;
            # the harness must never turn a bad SQL into a different bad SQL.
            return ConventionRewrite(
                sql=original, original_sql=original, parse_failed=True,
                notes=("sqlglot parse failed; left unmodified",),
            )

        applied: list[str] = []
        for name in self.enabled_conventions:
            try:
                if _RULES[name](tree):
                    applied.append(name)
            except Exception as exc:  # a rule bug must not lose the prediction
                return ConventionRewrite(
                    sql=original, original_sql=original,
                    notes=(f"rule {name} raised {type(exc).__name__}; left unmodified",),
                )
        if not applied:
            return ConventionRewrite(sql=original, original_sql=original)

        try:
            rewritten = tree.sql(dialect=DIALECT)
        except Exception:
            return ConventionRewrite(
                sql=original, original_sql=original,
                notes=("regeneration failed; left unmodified",),
            )
        return ConventionRewrite(
            sql=rewritten, original_sql=original, applied=tuple(applied)
        )

    def manifest(self) -> dict[str, Any]:
        return {
            "version": self._payload["version"],
            "path": str(self.path),
            "artifact_sha256": _sha256(self.path),
            "runtime_sha256": _sha256(Path(__file__)),
            "source": self._payload.get("source"),
            "source_sha256": self._payload.get("source_sha256"),
            "dialect": DIALECT,
            "train_example_count": self._payload.get("train_example_count"),
            "build_config": self._payload.get("build_config"),
            "enabled_conventions": list(self.enabled_conventions),
            "conventions": {
                name: {
                    "enabled": spec.get("enabled"),
                    "train_support": spec.get("train_support"),
                    "train_applicable": spec.get("train_applicable"),
                    "train_database_count": spec.get("train_database_count"),
                }
                for name, spec in sorted(self._conventions.items())
            },
            "application": {
                "stage": "post-model-final-sql",
                "deterministic": True,
                "uses_dev_data": False,
                "uses_gold_sql": False,
            },
        }


def get_sql_convention_rewriter(path: Path = _DEFAULT_PATH) -> SqlConventionRewriter:
    return SqlConventionRewriter(path)
