"""Deterministic post-processing of final SQL toward BIRD's writing conventions.

This is a post-processing stage of the system under test, not a model
instruction -- it changes the prediction, so it must be ablatable. (It is not
part of the evaluation harness, which only observes and scores.)  Measured on the 197-question
core set, e3-ac carries "consider whether DISTINCT is required" and "verify the
ORDER BY direction" in its prompt and violates those conventions as often as e3-c,
which carries neither (24 vs 25 violations).  Applying the same conventions here
instead moves questions.

Every rewrite is recorded with the rule that fired and the before/after SQL, so a
run's accuracy can always be decomposed into model output and post-processing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


VERSION = "train-conventions-v1"
# v2 differs from v1 in exactly one enabled rule: keep_ties. It is a separate
# artifact rather than a flag on the profile because enablement lives in the
# artifact, and a new AgentConfig field would change agent_config_sha256 for
# every profile at once -- which is how the sha compatibility was lost when
# final_execution_gate was added (see docs/analysis/week_2026-08-18/
# tie_rule_counterfactual_2026-08-25.md).
VERSION_TIES = "train-conventions-v2-ties"
# v3 isolates printf_to_round so the type fix and the tie fix can be
# attributed separately; v4 is the two together, for the shipping profile.
VERSION_TYPES = "train-conventions-v3-types"
VERSION_BOTH = "train-conventions-v4-ties-types"
DIALECT = "sqlite"
_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "data" / "processed"
_PATHS = {
    VERSION: _ARTIFACT_ROOT / "sql_conventions_v1.json",
    VERSION_TIES: _ARTIFACT_ROOT / "sql_conventions_v2_ties.json",
    VERSION_TYPES: _ARTIFACT_ROOT / "sql_conventions_v3_types.json",
    VERSION_BOTH: _ARTIFACT_ROOT / "sql_conventions_v4_ties_types.json",
}
KNOWN_VERSIONS = frozenset(_PATHS)
_DEFAULT_PATH = _PATHS[VERSION]


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


def _resolve_projection_alias(tree: exp.Select, key: exp.Expression) -> exp.Expression:
    """`ORDER BY some_alias` -> the expression that alias was defined as.

    SQLite lets ORDER BY name a projection alias, and the rewrite below lifts the
    sort key into a subquery where that alias does not exist. Without this the
    generated condition silently binds to nothing (measured: bird_12 returned 749
    rows instead of 1).
    """
    if isinstance(key, exp.Column) and not key.table:
        for projection in tree.args.get("expressions", []):
            if isinstance(projection, exp.Alias) and projection.alias == key.name:
                return projection.this.copy()
    return key


def _rule_keep_ties(tree: exp.Expression) -> bool:
    """`ORDER BY x DESC LIMIT 1` -> `WHERE x = (SELECT MAX(x) FROM <same query>)`.

    The exact inverse of `superlative_order_limit`, and mutually exclusive with it.
    Rationale: BIRD scores by set comparison (shared/evaluator.py), so when the
    extremum is unique both forms return the same set and this rewrite is free;
    when the data ties, `LIMIT 1` keeps one arbitrary row and loses the rest.
    Measured on three runs: +5 / +5 / +4 questions.

    Known cost: when every candidate value is NULL, MAX returns NULL and the
    rewritten `x = NULL` matches nothing, while `LIMIT 1` still returned a row
    (bird_633). Detecting that needs execution, which this layer deliberately
    does not do, so the rule accepts it.
    """
    if not isinstance(tree, exp.Select):
        return False
    limit = tree.args.get("limit")
    order = tree.args.get("order")
    if not limit or not order or tree.args.get("offset"):
        return False
    if not isinstance(limit.expression, exp.Literal) or limit.expression.this != "1":
        return False
    if len(order.expressions) != 1:
        # A second sort key means the query already breaks ties deliberately.
        return False

    ordered = order.expressions[0]
    key = _resolve_projection_alias(tree, ordered.this)
    aggregate = exp.Max if ordered.args.get("desc") else exp.Min

    inner = tree.copy()
    inner.set("order", None)
    inner.set("limit", None)
    inner.set("expressions", [exp.alias_(key.copy(), "k")])
    extremum = exp.select(aggregate(this=exp.column("k"))).from_(
        exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier("t")))
    )
    condition = exp.EQ(this=key.copy(), expression=exp.Subquery(this=extremum))

    # An extremum over groups is a property of the group, so it belongs in
    # HAVING; gold writes it that way too (HAVING COUNT(x) = (SELECT MAX(...))).
    grouped = tree.args.get("group") is not None or bool(list(key.find_all(exp.AggFunc)))
    clause = "having" if grouped else "where"
    existing = tree.args.get(clause)
    merged = exp.And(this=existing.this, expression=condition) if existing else condition
    tree.set(clause, (exp.Having if grouped else exp.Where)(this=merged))

    tree.set("order", None)
    tree.set("limit", None)
    return True


_PRINTF_FLOAT_FORMAT = re.compile(r"^%\.(\d+)f$")


def _rule_printf_to_round(tree: exp.Expression) -> bool:
    """`printf('%.Nf', x)` -> `ROUND(x, N)`.

    Not a style preference -- a type fix. In SQLite `printf` returns TEXT while
    `ROUND` returns REAL, and BIRD scores by comparing result tuples, so
    `'3.84615' != 3.84615` and an otherwise perfect answer is marked wrong.

    The trigger is the model doing exactly what the question asks: four dev
    questions say "provide your answer as a percentage with N decimal places"
    and the model reaches for printf, which is the most direct reading of that
    instruction (bird_226/227/228/255 -- see
    docs/analysis/week_2026-08-18/flatzero_23_root_causes_2026-08-25.md, where
    type/format is the single largest failure class at 24%).

    Deliberately narrow: only a lone `%.Nf` format with exactly two arguments.
    A format string carrying any other literal text is a genuine string result
    the model meant to build, and rewriting it would change the answer rather
    than its type.
    """
    if not isinstance(tree, exp.Expression):
        return False
    fired = False
    for node in list(tree.find_all(exp.Anonymous)):
        if (node.name or "").lower() != "printf":
            continue
        args = node.expressions
        if len(args) != 2:
            continue
        fmt = args[0]
        if not (isinstance(fmt, exp.Literal) and fmt.is_string):
            continue
        match = _PRINTF_FLOAT_FORMAT.match(fmt.this or "")
        if not match:
            continue
        node.replace(exp.Round(
            this=args[1].copy(),
            decimals=exp.Literal.number(match.group(1)),
        ))
        fired = True
    return fired


_RULES = {
    "count_no_distinct": _rule_count_no_distinct,
    "no_select_concat": _rule_no_select_concat,
    "superlative_order_limit": _rule_superlative_order_limit,
    "keep_ties": _rule_keep_ties,
    "printf_to_round": _rule_printf_to_round,
}

# These two are exact inverses; enabling both would make the pipeline's output
# depend on rule ordering rather than on the conventions.
_MUTUALLY_EXCLUSIVE = (("superlative_order_limit", "keep_ties"),)


class SqlConventionRewriter:
    """Applies the enabled mined conventions to a final SQL string."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self.path = Path(path).resolve()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("version") not in KNOWN_VERSIONS:
            raise ValueError(f"Unsupported convention artifact: {payload.get('version')!r}")
        self._payload = payload
        self._conventions: dict[str, dict[str, Any]] = payload.get("conventions", {})
        unknown = set(self._conventions) - set(_RULES)
        if unknown:
            raise ValueError(f"Artifact declares conventions with no rewrite rule: {sorted(unknown)}")
        enabled = set(self.enabled_conventions)
        for pair in _MUTUALLY_EXCLUSIVE:
            if enabled.issuperset(pair):
                raise ValueError(f"Conventions {pair} are inverses and cannot both be enabled")

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
            # post-processing must never turn a bad SQL into a different bad SQL.
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


def get_sql_convention_rewriter(mode: str = VERSION) -> SqlConventionRewriter:
    """Resolve a convention artifact by the profile's `sql_convention_mode`."""
    try:
        return SqlConventionRewriter(_PATHS[mode])
    except KeyError:
        raise ValueError(f"Unknown SQL convention mode: {mode!r}") from None
