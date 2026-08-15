"""Classify why the first drafted SQL already disagrees with gold.

Turn-by-turn replay showed 91% of failures are wrong in the model's very first
draft and never recover, so "why does a run fail" reduces to "why is the first
draft wrong". Reading first-turn reasoning on a sample surfaced six recurring
causes; this applies detectors for the ones that can be decided from the two
SQL strings plus the hint, and refuses to guess on the rest.

The detectors are deliberately conservative and ordered by how unambiguous they
are. Anything they cannot decide lands in `未分类` rather than being forced into
the nearest bucket -- the point of the exercise is a number that can be quoted,
and a bucket padded with uncertain members cannot be.

Five of the six causes describe gold or the hint under-specifying the task, not
the model reasoning badly, which is the substance of the claim this produces.
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

AGG = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)
GRAIN_FN = re.compile(r"\b(substr|substring|strftime)\s*\(", re.I)
# "two or more", "at least two" -> >= 2, while a hint may state "> 2"
ATLEAST = re.compile(r"\b(two or more|three or more|at least (two|three|\d+)|or more)\b", re.I)
HINT_GT = re.compile(r"count\s*\([^)]*\)\s*>\s*(\d+)", re.I)
FORMULA = re.compile(r"=\s*(DIVIDE|MULTIPLY|SUBTRACT|SUM|COUNT|AVG|MAX|MIN)\s*\(", re.I)


def parse(sql):
    try:
        return sqlglot.parse_one(sql or "", read="sqlite")
    except Exception:
        return None


def projection(tree) -> list[str]:
    if tree is None:
        return []
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if select is None:
        return []
    out = []
    for p in select.expressions:
        body = p.this if isinstance(p, exp.Alias) else p
        cols = [c.name.casefold() for c in body.find_all(exp.Column) if c.name]
        out.append(cols[0] if cols else body.sql(dialect="sqlite").casefold())
    return out


def counts_with_distinct(tree) -> tuple[int, int]:
    """(# of COUNT(DISTINCT ...), # of plain COUNT(...))"""
    if tree is None:
        return (0, 0)
    d = p = 0
    for c in tree.find_all(exp.Count):
        if isinstance(c.this, exp.Distinct) or c.args.get("distinct"):
            d += 1
        else:
            p += 1
    return (d, p)


def agg_multiset(tree) -> Counter:
    c: Counter = Counter()
    if tree is None:
        return c
    for A in AGG:
        for _ in tree.find_all(A):
            c[A.__name__] += 1
    return c


def classify(question: str, hint: str, pred_sql: str, gold_sql: str) -> str:
    p, g = parse(pred_sql), parse(gold_sql)
    if p is None:
        return "预测SQL无法解析"
    if g is None:
        return "gold SQL无法解析"

    pd, pp = counts_with_distinct(p)
    gd, gp = counts_with_distinct(g)
    # (1) the model counted entities, gold counted rows
    if pd > 0 and gd == 0 and gp > 0:
        return "①计数口径:模型去重/gold数行"
    if gd > 0 and pd == 0 and pp > 0:
        return "①计数口径:gold去重/模型数行"

    proj_p, proj_g = projection(p), projection(g)
    # (2) gold projects strictly more than the question's answer needs
    if proj_p and proj_g and len(proj_g) > len(proj_p) and set(proj_p) <= set(proj_g):
        return "②gold返回题面未要求的额外列"

    # (3) same column, one side reduced to a coarser grain (month from yyyymm etc.)
    if len(proj_p) == len(proj_g) == 1 and proj_p == proj_g:
        if bool(GRAIN_FN.search(gold_sql or "")) != bool(GRAIN_FN.search(pred_sql or "")):
            return "③输出粒度未指定"

    # (4) the question says "two or more" while the hint states a strict >
    m = HINT_GT.search(hint or "")
    if m and ATLEAST.search(question or ""):
        return "④hint与题面矛盾(阈值)"

    # (5)/(6) both need the hint to state a formula; separate them by who follows it
    if FORMULA.search(hint or ""):
        if agg_multiset(p) != agg_multiset(g):
            return "⑤/⑥公式类:聚合组合不同"
        return "⑤/⑥公式类:聚合相同但写法不同"

    return "未分类"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--dataset", default="data/processed/bird_dev_500.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
    hints = {q["id"]: (q.get("evidence") or "")
             for q in json.loads(Path(args.dataset).read_text(encoding="utf-8"))}

    records = []
    for row in rows:
        if is_correct(row.get("predicted_answer"), row.get("gold_answer")):
            continue
        label = classify(row.get("question", ""), hints.get(row["id"], ""),
                         row.get("predicted_sql"), row.get("gold_sql"))
        records.append({"id": row["id"], "db_id": row.get("db_id"), "cause": label})

    Path(args.output).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(records)
    print(f"失败题 {n} 道\n")
    print(f'{"成因":<34}{"题数":>5}{"占比":>9}')
    print("-" * 50)
    for cause, c in Counter(r["cause"] for r in records).most_common():
        print(f"{cause:<34}{c:>5}{c/n*100:>8.1f}%")
    print(f"\n已写入 {args.output}")
