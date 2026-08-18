"""Mine BIRD's SQL *writing conventions* from the train pool.

E3-F's query mining asked "what structure does this question imply?" and lost to
the model's own judgement (best slot beat it by 1.5pp, so every slot abstained).
This miner asks a different question: "when BIRD's annotators had a free choice
between two equivalent-looking spellings, which one did they write?"

Those choices are not SQL knowledge -- the model's preferred spelling is usually
the semantically defensible one -- so telling the model about them does not work
(measured: e3-ac carries the DISTINCT instruction in its prompt and violates the
convention exactly as often as e3-c, which does not).  They are applied by the
harness as deterministic rewrites of the final SQL instead.

Each convention records how often train gold conforms, over how many databases,
so the artifact carries its own evidence.  Only conventions above the gate are
enabled at runtime.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable

import sqlglot
from sqlglot import exp


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION = "train-conventions-v1"
DIALECT = "sqlite"

# A convention is only enabled if gold follows it this consistently, across at
# least this many distinct databases, on at least this many applicable queries.
MIN_SUPPORT = 0.80
MIN_APPLICABLE = 100
MIN_DATABASE_COUNT = 8

# Support measured against gold cannot tell a house style from an annotation
# defect: it only says how often the annotators wrote something, not whether
# writing it was right.  So support alone must never enable a rewrite that
# changes *what the query computes* -- only ones that change how the same values
# are shaped for comparison.
#
# `count_no_distinct` is why this exists.  It measured 0.891 support over 2377
# train queries, which looked decisive; re-scoring dev against an independently
# corrected gold (VLDB 2026 Arcwise-Plat-SQL, arXiv:2601.08778) showed the rule
# is worth -16 questions there.  The corrected gold uses DISTINCT in 130 of 498
# questions where the original used it in 83 -- the 0.891 was measuring the
# annotators' habit of omitting DISTINCT, and the rule had encoded that defect.
# `superlative_order_limit` is worth -2 and can silently drop WHERE conditions.
SEMANTICS_CHANGING = {
    "count_no_distinct": "changes what COUNT counts (entities -> rows)",
    "superlative_order_limit": "changes the computation and can drop WHERE conditions",
}

SUPERLATIVE = re.compile(
    r"\b(highest|lowest|most|least|maximum|minimum|max|min|largest|smallest"
    r"|oldest|newest|longest|shortest|top|best|worst)\b",
    re.I,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse(sql: str) -> exp.Expression | None:
    try:
        return sqlglot.parse_one(sql, read=DIALECT)
    except Exception:
        return None


# --------------------------------------------------------------------------
# Convention probes.  Each returns (applicable, conforming); `applicable` marks
# the queries where the annotator faced the choice at all, so support is a
# conditional rate rather than a corpus-wide frequency.
# --------------------------------------------------------------------------

def _has_join(tree: exp.Expression) -> bool:
    return bool(list(tree.find_all(exp.Join)))


def probe_count_no_distinct(question: str, tree: exp.Expression) -> tuple[bool, bool]:
    """Counting over a join: COUNT(x) or COUNT(DISTINCT x)?"""
    counts = list(tree.find_all(exp.Count))
    if not counts or not _has_join(tree):
        return False, False
    conforming = not any(
        isinstance(c.this, exp.Distinct) or c.args.get("distinct") for c in counts
    )
    return True, conforming


def _projection_dpipes(tree: exp.Expression) -> bool:
    for select in tree.find_all(exp.Select):
        for projection in select.expressions:
            if list(projection.find_all(exp.DPipe)):
                return True
    return False


def probe_no_select_concat(question: str, tree: exp.Expression) -> tuple[bool, bool]:
    """Emitting several attributes: separate columns or one concatenated string?"""
    if not any(isinstance(node, exp.Select) for node in tree.find_all(exp.Select)):
        return False, False
    return True, not _projection_dpipes(tree)


def _uses_order_limit(tree: exp.Expression) -> bool:
    return bool(list(tree.find_all(exp.Order))) and bool(list(tree.find_all(exp.Limit)))


def _uses_eq_max_subquery(tree: exp.Expression) -> bool:
    for eq in tree.find_all(exp.EQ):
        for side in (eq.left, eq.right):
            inner = side.this if isinstance(side, exp.Subquery) else side
            if isinstance(inner, (exp.Select, exp.Subquery)) or isinstance(side, exp.Subquery):
                target = side.find(exp.Select) if side else None
                if target and any(
                    isinstance(p, (exp.Max, exp.Min))
                    or (isinstance(p, exp.Alias) and isinstance(p.this, (exp.Max, exp.Min)))
                    for p in target.expressions
                ):
                    return True
    return False


def probe_superlative_order_limit(question: str, tree: exp.Expression) -> tuple[bool, bool]:
    """Superlative question: ORDER BY ... LIMIT 1, or WHERE x = (SELECT MAX(x))?"""
    if not SUPERLATIVE.search(question or ""):
        return False, False
    order_limit, eq_max = _uses_order_limit(tree), _uses_eq_max_subquery(tree)
    if order_limit == eq_max:  # neither form, or both -- annotator faced no clean choice
        return False, False
    return True, order_limit


PROBES: dict[str, dict[str, Any]] = {
    "count_no_distinct": {
        "probe": probe_count_no_distinct,
        "choice": "COUNT(x) vs COUNT(DISTINCT x) when the query joins",
        "gold_preference": "COUNT(x)",
        "rewrite": "strip DISTINCT from COUNT aggregates when the query contains a JOIN",
    },
    "no_select_concat": {
        "probe": probe_no_select_concat,
        "choice": "separate projected columns vs a || concatenation in the SELECT list",
        "gold_preference": "separate columns",
        "rewrite": "split `a || sep || b` in the SELECT list into separate projections",
    },
    "superlative_order_limit": {
        "probe": probe_superlative_order_limit,
        "choice": "ORDER BY ... LIMIT 1 vs WHERE x = (SELECT MAX(x) ...)",
        "gold_preference": "ORDER BY ... LIMIT 1",
        "rewrite": (
            "rewrite `WHERE x = (SELECT MAX(x) FROM t)` to `ORDER BY x DESC LIMIT 1`, "
            "only when the subquery is a bare aggregate over a single table and the "
            "outer query has no ORDER BY, LIMIT or GROUP BY of its own"
        ),
    },
}


def build(pool_path: Path, output_path: Path) -> dict[str, Any]:
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    parsed: list[tuple[str, str, exp.Expression]] = []
    parse_failures = 0
    for row in pool:
        tree = _parse(row.get("SQL", ""))
        if tree is None:
            parse_failures += 1
            continue
        parsed.append((row.get("db_id", ""), row.get("question", ""), tree))

    conventions: dict[str, Any] = {}
    for name, spec in PROBES.items():
        probe: Callable[[str, exp.Expression], tuple[bool, bool]] = spec["probe"]
        applicable = conforming = 0
        per_db: dict[str, Counter] = defaultdict(Counter)
        for db_id, question, tree in parsed:
            try:
                is_applicable, is_conforming = probe(question, tree)
            except Exception:
                continue
            if not is_applicable:
                continue
            applicable += 1
            conforming += int(is_conforming)
            per_db[db_id]["applicable"] += 1
            per_db[db_id]["conforming"] += int(is_conforming)

        support = conforming / applicable if applicable else 0.0
        # A convention that only holds in a handful of databases is a schema
        # quirk, not a house style; require it to hold broadly.
        db_supports = [
            c["conforming"] / c["applicable"] for c in per_db.values() if c["applicable"] >= 5
        ]
        db_majority = sum(1 for s in db_supports if s >= 0.5)
        gate_passed = (
            support >= MIN_SUPPORT
            and applicable >= MIN_APPLICABLE
            and len(per_db) >= MIN_DATABASE_COUNT
        )
        enabled = gate_passed and name not in SEMANTICS_CHANGING
        conventions[name] = {
            "enabled": enabled,
            "choice": spec["choice"],
            "gold_preference": spec["gold_preference"],
            "rewrite": spec["rewrite"],
            "train_applicable": applicable,
            "train_conforming": conforming,
            "train_support": round(support, 4),
            "train_database_count": len(per_db),
            "train_databases_majority_conforming": db_majority,
            "train_databases_measured": len(db_supports),
            "gate": {
                "min_support": MIN_SUPPORT,
                "min_applicable": MIN_APPLICABLE,
                "min_database_count": MIN_DATABASE_COUNT,
                "passed": gate_passed,
            },
            "disabled_reason": SEMANTICS_CHANGING.get(name),
        }

    payload = {
        "version": VERSION,
        "source": str(pool_path.relative_to(PROJECT_ROOT)) if pool_path.is_relative_to(PROJECT_ROOT) else str(pool_path),
        "source_sha256": _sha256(pool_path),
        "dialect": DIALECT,
        "train_example_count": len(pool),
        "parsed_sql_count": len(parsed),
        "parse_failure_count": parse_failures,
        "conventions": conventions,
        "enabled_convention_count": sum(1 for c in conventions.values() if c["enabled"]),
        "build_config": {
            "min_support": MIN_SUPPORT,
            "min_applicable": MIN_APPLICABLE,
            "min_database_count": MIN_DATABASE_COUNT,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="data/train_pool.json")
    parser.add_argument("--output", default="data/processed/sql_conventions_v1.json")
    args = parser.parse_args()
    built = build(Path(args.pool).resolve(), Path(args.output).resolve())
    print(
        f"wrote {args.output}: parsed={built['parsed_sql_count']}/"
        f"{built['train_example_count']} (failures={built['parse_failure_count']})"
    )
    for name, spec in sorted(built["conventions"].items()):
        flag = "ENABLED " if spec["enabled"] else "disabled"
        print(
            f"  [{flag}] {name:<26} support={spec['train_support']:.4f} "
            f"({spec['train_conforming']}/{spec['train_applicable']}) "
            f"dbs={spec['train_database_count']} "
            f"majority-conforming={spec['train_databases_majority_conforming']}"
            f"/{spec['train_databases_measured']}"
        )
