"""Locate where in SQL construction a failing prediction first diverges from gold.

Every prior failure audit on this project classified errors by *what the wrong
answer looked like* -- output contract, aggregation, schema/join. That labels the
symptom. This asks a different question: walking the query from the tables
inward, which is the *first* layer where prediction and gold stop agreeing?
Everything downstream of a wrong table choice is unfixable-by-construction, so
the first divergence is the only layer worth intervening on.

The layers are ordered by construction dependency, not by importance:

    tables -> join keys -> filters -> grouping -> aggregation -> projection
    -> ordering/limit -> pure formatting

The second half matters more than the first. For each failure this also asks
whether the model's captured reasoning ever *mentioned* the thing gold used and
the prediction missed. That splits every error into two kinds with opposite
remedies:

    never considered  -> the right option was not in front of the model
                         (a retrieval/context problem -- and pre-commitment
                         context work is the one intervention class with a
                         positive track record here: +3.2pp from schema context)
    considered, rejected -> the option was visible and judged wrong
                         (a judgment problem; five post-commitment
                         interventions have now failed to move these)

Nothing here uses an LLM to judge. Table and column sets come from sqlglot,
mention-checking is literal string search over the reasoning text.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlglot
from sqlglot import exp

from shared.evaluator import is_correct


def _parse(sql: str):
    try:
        return sqlglot.parse_one(sql or "", read="sqlite")
    except Exception:
        return None


def tables_of(tree) -> set[str]:
    if tree is None:
        return set()
    ctes = {c.alias_or_name.casefold() for c in tree.find_all(exp.CTE)}
    return {t.name.casefold() for t in tree.find_all(exp.Table)
            if t.name and t.name.casefold() not in ctes}


def columns_of(tree) -> set[str]:
    if tree is None:
        return set()
    return {c.name.casefold() for c in tree.find_all(exp.Column) if c.name}


def join_keys_of(tree) -> set[frozenset]:
    """Column pairs equated inside ON clauses -- the join graph, alias-insensitive."""
    if tree is None:
        return set()
    keys = set()
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            continue
        for eq in on.find_all(exp.EQ):
            left, right = eq.left, eq.right
            if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                keys.add(frozenset({left.name.casefold(), right.name.casefold()}))
    return keys


def filter_columns_of(tree) -> set[str]:
    if tree is None:
        return set()
    cols = set()
    for where in tree.find_all(exp.Where):
        cols |= {c.name.casefold() for c in where.find_all(exp.Column) if c.name}
    return cols


def filter_literals_of(tree) -> set[str]:
    if tree is None:
        return set()
    lits = set()
    for where in tree.find_all(exp.Where):
        for lit in where.find_all(exp.Literal):
            if lit.args.get("is_string"):
                lits.add(str(lit.this).casefold())
    return lits


def group_columns_of(tree) -> set[str]:
    if tree is None:
        return set()
    cols = set()
    for group in tree.find_all(exp.Group):
        cols |= {c.name.casefold() for c in group.find_all(exp.Column) if c.name}
    return cols


AGG_TYPES = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)


def aggregates_of(tree) -> Counter:
    if tree is None:
        return Counter()
    c: Counter = Counter()
    for agg in AGG_TYPES:
        for node in tree.find_all(agg):
            distinct = isinstance(node.this, exp.Distinct) or bool(node.args.get("distinct"))
            c[f"{agg.__name__.lower()}{'_distinct' if distinct else ''}"] += 1
    return c


def projection_width(tree) -> int | None:
    if tree is None:
        return None
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    return len(select.expressions) if select is not None else None


def order_limit_of(tree) -> tuple[bool, bool, int | None]:
    if tree is None:
        return (False, False, None)
    has_order = bool(list(tree.find_all(exp.Order)))
    limit_node = tree.args.get("limit") if isinstance(tree, exp.Select) else None
    limit_val = None
    if limit_node is not None:
        try:
            limit_val = int(limit_node.expression.this)
        except Exception:
            limit_val = -1
    return (has_order, limit_val is not None, limit_val)


def first_divergence(pred_tree, gold_tree, pred_ans, gold_ans) -> str:
    """The earliest construction layer where the two queries stop agreeing."""
    if pred_tree is None:
        return "预测SQL无法解析"
    if gold_tree is None:
        return "gold SQL无法解析"

    pt, gt = tables_of(pred_tree), tables_of(gold_tree)
    if pt != gt:
        return "表选择" if (gt - pt) else "多用了表"

    if join_keys_of(pred_tree) != join_keys_of(gold_tree):
        return "JOIN 键"

    pf, gf = filter_columns_of(pred_tree), filter_columns_of(gold_tree)
    if pf != gf:
        return "过滤列"
    if filter_literals_of(pred_tree) != filter_literals_of(gold_tree):
        return "过滤字面量"

    if group_columns_of(pred_tree) != group_columns_of(gold_tree):
        return "分组"

    if aggregates_of(pred_tree) != aggregates_of(gold_tree):
        return "聚合函数"

    if projection_width(pred_tree) != projection_width(gold_tree):
        return "投影列数"

    if order_limit_of(pred_tree) != order_limit_of(gold_tree):
        return "排序/LIMIT"

    # Structurally indistinguishable at every layer above, yet scored wrong:
    # the difference lives in value formatting, column order, or row order.
    return "纯格式/列序"


def missed_terms(pred_tree, gold_tree) -> set[str]:
    """What gold references that the prediction never touched."""
    gold_terms = tables_of(gold_tree) | columns_of(gold_tree)
    pred_terms = tables_of(pred_tree) | columns_of(pred_tree)
    return {t for t in (gold_terms - pred_terms) if len(t) > 2}


def distinctive(term: str, question: str) -> bool:
    """Is finding this term in the reasoning evidence of a *schema* reference?

    A first pass counted any literal hit, which made "patient", "team" and
    "category" look like the model had considered those tables when it had only
    used the English words the question itself supplied. A term earns a mention
    only if it is shaped like an identifier (underscore, digit, camelCase, or an
    unusual abbreviation) or does not already appear in the question.
    """
    if re.search(r"[_\d]", term) or re.search(r"[a-z][A-Z]", term):
        return True
    return term.casefold() not in (question or "").casefold()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results/e3_c_conv_rules_dev500_run1.json")
    parser.add_argument("--reasoning", default="docs/analysis/analysisDetail/reasoning_capture_dev500.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
    reasoning = {r["id"]: r for r in json.loads(Path(args.reasoning).read_text(encoding="utf-8"))}

    records = []
    for row in rows:
        if is_correct(row.get("predicted_answer"), row.get("gold_answer")):
            continue
        pred_tree = _parse(row.get("predicted_sql"))
        gold_tree = _parse(row.get("gold_sql"))
        layer = first_divergence(pred_tree, gold_tree,
                                 row.get("predicted_answer"), row.get("gold_answer"))

        missed = missed_terms(pred_tree, gold_tree)
        question = row.get("question") or ""
        # Only identifier-shaped terms can testify that the model considered a
        # schema element; bare English words the question already contains cannot.
        checkable = {t for t in missed if distinctive(t, question)}
        cap = reasoning.get(row["id"])
        considered = None
        mentioned: set[str] = set()
        if cap and checkable:
            blob = " ".join(cap.get("reasoning_sections") or []).casefold()
            mentioned = {t for t in checkable if t in blob}
            considered = "推理中提到过" if mentioned else "推理中从未提到"
        elif cap and missed and not checkable:
            considered = "无法判定(仅通用词)"
        elif cap and not missed:
            considered = "无遗漏项"

        records.append({
            "id": row["id"], "db_id": row.get("db_id"), "layer": layer,
            "missed_terms": sorted(missed), "checkable_terms": sorted(checkable),
            "mentioned_terms": sorted(mentioned), "considered": considered,
            "reasoning_sections": (cap or {}).get("section_count"),
        })

    Path(args.output).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")

    n = len(records)
    print(f"失败题总数: {n}\n")
    print(f'{"最先出错的层":<16}{"题数":>6}{"占比":>9}   推理是否提到过 gold 用的东西')
    print("-" * 78)
    by_layer: dict[str, list] = defaultdict(list)
    for r in records:
        by_layer[r["layer"]].append(r)
    for layer, items in sorted(by_layer.items(), key=lambda kv: -len(kv[1])):
        cons = Counter(i["considered"] for i in items)
        detail = "  ".join(f"{k}={v}" for k, v in cons.most_common() if k)
        print(f'{layer:<16}{len(items):>6}{len(items)/n*100:>8.1f}%   {detail}')

    print()
    never = [r for r in records if r["considered"] == "推理中从未提到"]
    saw = [r for r in records if r["considered"] == "推理中提到过"]
    print(f"gold 用到、但预测漏掉的东西 —— 推理中从未提到过: {len(never)} 题")
    print(f"                              推理中提到过却没用: {len(saw)} 题")
    print(f"\n已写入 {args.output}")
