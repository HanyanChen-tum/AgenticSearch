"""Assign a root cause to every failure, with no unclassified bucket.

Earlier passes left 46% of failures uncharacterised because they differ from
gold in several places at once and there was no principled way to say which
difference was the cause rather than a consequence. Construction order supplies
that rule: a query is built tables -> joins -> filters -> grouping -> aggregates
-> projection -> ordering, and once the wrong table is chosen every downstream
difference follows from it. So the *first* layer that genuinely diverges is the
root cause and the rest is fallout.

"Genuinely" is the load-bearing word, and the reason this file exists rather
than reusing the first pass. Comparing raw SQL text counts `T1.Currency` against
`Currency`, and `SUBSTR(d,1,4)` against `STRFTIME('%Y',d)`, as differences; 19 of
45 supposed WHERE divergences evaporated once those were normalised. Every
comparison here therefore runs on canonical forms, and the SQL read for the model
is `sql_convention_rewrite.original_sql` where post-processing rewrote it, so
its own DISTINCT stripping is not attributed to the model.

Each layer, once it is identified as the first to diverge, is then described
concretely -- which table was swapped, whether the model added or dropped a
filter the question mentions, whether counting is by entity or by row -- so the
output is a cause rather than a coordinate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlglot
from sqlglot import exp

from shared.evaluator import is_correct

AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)


def parse(sql: str):
    try:
        return sqlglot.parse_one(sql or "", read="sqlite")
    except Exception:
        return None


def canon(text: str) -> str:
    """Strip alias qualifiers and unify spellings that mean the same thing."""
    s = re.sub(r"\s+", " ", text).strip().lower()
    s = re.sub(r"\b[a-z_][a-z0-9_]*\.(?=[a-z_\"\[])", "", s)
    s = re.sub(r'substr(?:ing)?\("?\[?([a-z0-9_ \-]+)\]?"?,\s*1,\s*4\)', r"year(\1)", s)
    s = re.sub(r"strftime\(\s*'%y'\s*,\s*\"?\[?([a-z0-9_ \-]+)\]?\"?\)", r"year(\1)", s)
    s = re.sub(r"\bcast\(([^)]+) as (real|float|integer|int)\)", r"\1", s)
    s = re.sub(r"\biif\(", "case_when(", s)
    return s.replace('"', "").replace("`", "").replace("[", "").replace("]", "")


def tables(tree) -> set[str]:
    if tree is None:
        return set()
    ctes = {c.alias_or_name.casefold() for c in tree.find_all(exp.CTE)}
    return {t.name.casefold() for t in tree.find_all(exp.Table)
            if t.name and t.name.casefold() not in ctes}


def join_keys(tree) -> set[frozenset]:
    if tree is None:
        return set()
    out = set()
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            continue
        for eq in on.find_all(exp.EQ):
            if isinstance(eq.left, exp.Column) and isinstance(eq.right, exp.Column):
                out.add(frozenset({eq.left.name.casefold(), eq.right.name.casefold()}))
    return out


def predicates(tree) -> set[str]:
    out = set()
    if tree is None:
        return out
    for where in tree.find_all(exp.Where):
        stack = [where.this]
        while stack:
            node = stack.pop()
            if isinstance(node, (exp.And, exp.Or)):
                stack += [node.left, node.right]
            elif node is not None:
                out.add(canon(node.sql(dialect="sqlite")))
    return out


def group_cols(tree) -> set[str]:
    if tree is None:
        return set()
    return {canon(c.sql(dialect="sqlite"))
            for g in tree.find_all(exp.Group) for c in g.expressions}


def agg_profile(tree) -> Counter:
    c: Counter = Counter()
    if tree is None:
        return c
    for A in AGGS:
        for node in A and tree.find_all(A):
            distinct = isinstance(node.this, exp.Distinct) or bool(node.args.get("distinct"))
            c[f"{A.__name__}{'_D' if distinct else ''}"] += 1
    return c


def projection(tree) -> list[str]:
    if tree is None:
        return []
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if select is None:
        return []
    return [canon((p.this if isinstance(p, exp.Alias) else p).sql(dialect="sqlite"))
            for p in select.expressions]


def order_limit(tree):
    if tree is None:
        return (False, None)
    has_order = bool(list(tree.find_all(exp.Order)))
    limit = tree.args.get("limit") if isinstance(tree, exp.Select) else None
    value = None
    if limit is not None:
        try:
            value = int(limit.expression.this)
        except Exception:
            value = -1
    return (has_order, value)


def mentioned(question: str, predicate: str) -> bool:
    """Does the question name a literal that this predicate filters on?"""
    lits = re.findall(r"'([^']{3,})'", predicate)
    q = (question or "").casefold()
    return any(l.casefold() in q for l in lits)


def root_cause(question: str, model_sql: str, gold_sql: str) -> tuple[str, str]:
    p, g = parse(model_sql), parse(gold_sql)
    if p is None:
        return ("模型SQL无法解析", "解析")
    if g is None:
        return ("gold SQL无法解析", "解析")

    tp, tg = tables(p), tables(g)
    if tp != tg:
        miss, extra = sorted(tg - tp), sorted(tp - tg)
        if miss and not extra:
            return (f"表层:gold多连表 {','.join(miss)}", "表")
        if extra and not miss:
            return (f"表层:模型多连表 {','.join(extra)}", "表")
        return (f"表层:换错表 {','.join(extra)}→{','.join(miss)}", "表")

    if join_keys(p) != join_keys(g):
        return ("JOIN层:连接键不同", "JOIN")

    pp, gp = predicates(p), predicates(g)
    if pp != gp:
        only_g, only_p = gp - pp, pp - gp
        if only_p and not only_g:
            tag = "题面提到但gold未过滤" if any(mentioned(question, x) for x in only_p) else "gold未过滤"
            return (f"过滤层:模型多加条件({tag})", "过滤")
        if only_g and not only_p:
            return ("过滤层:模型漏了gold的条件", "过滤")
        return ("过滤层:同一条件取值/写法不同", "过滤")

    if group_cols(p) != group_cols(g):
        return ("分组层:分组键不同", "分组")

    ap, ag = agg_profile(p), agg_profile(g)
    if ap != ag:
        pd = sum(v for k, v in ap.items() if k.endswith("_D"))
        gd = sum(v for k, v in ag.items() if k.endswith("_D"))
        if pd and not gd:
            return ("聚合层:计数口径-模型按实体去重/gold按行", "聚合")
        if gd and not pd:
            return ("聚合层:计数口径-gold去重/模型按行", "聚合")
        return ("聚合层:聚合函数组合不同", "聚合")

    prp, prg = projection(p), projection(g)
    if prp != prg:
        if len(prg) > len(prp) and set(prp) <= set(prg):
            return ("投影层:gold返回题面未要求的额外列", "投影")
        if len(prp) > len(prg) and set(prg) <= set(prp):
            return ("投影层:模型多返回列", "投影")
        return ("投影层:投影表达式不同", "投影")

    if order_limit(p) != order_limit(g):
        return ("排序层:ORDER/LIMIT不同", "排序")

    return ("全部结构等价:差异在取值类型/行序/列序", "等价")


if __name__ == "__main__":
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--results", required=True)
    ap_.add_argument("--trace", required=True)
    ap_.add_argument("--output", required=True)
    args = ap_.parse_args()

    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
    original: dict[str, str] = {}
    with Path(args.trace).open(encoding="utf-8") as handle:
        for line in handle:
            rec = json.loads(line)
            trace = rec.get("_trace") or rec
            rw = trace.get("sql_convention_rewrite") or {}
            if rw.get("changed") and rw.get("original_sql"):
                original[rec["id"]] = rw["original_sql"]

    records = []
    for row in rows:
        if is_correct(row.get("predicted_answer"), row.get("gold_answer")):
            continue
        model_sql = original.get(row["id"], row.get("predicted_sql"))
        cause, layer = root_cause(row.get("question", ""), model_sql, row.get("gold_sql"))
        records.append({"id": row["id"], "db_id": row.get("db_id"),
                        "layer": layer, "cause": cause})

    Path(args.output).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")

    n = len(records)
    print(f"失败 {n} 道，全部已归因（无未分类）\n")
    print(f'{"首个分歧层":<8}{"题数":>5}{"占比":>8}')
    print("-" * 26)
    for layer, c in Counter(r["layer"] for r in records).most_common():
        print(f"{layer:<9}{c:>5}{c/n*100:>7.1f}%")
    print(f"\n{'具体根因':<44}{'题数':>5}{'占比':>8}")
    print("-" * 60)
    for cause, c in Counter(r["cause"] for r in records).most_common():
        print(f"{cause:<44}{c:>5}{c/n*100:>7.1f}%")
