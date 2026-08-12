"""Rank candidate decision points by how much they determine the outcome.

The first version of the Sankey hand-picked five nodes. That is the inductive
bias Harshal flagged in the Praktikum session -- Thought Anchors' contribution is
not the notion of a branch point but a *measure* for finding which steps carry
the outcome, so the selection stops being the analyst's intuition.

The paper's measure is counterfactual: resample a step, see how far the final
answer distribution moves. That needs generation. The observational analogue here
is how much knowing a decision reduces uncertainty about correctness -- mutual
information between the decision and the outcome, plus the spread in success rate
across its branches. It ranks the same way when a decision genuinely determines
the result, and unlike the causal version it costs nothing and covers all 500
questions rather than a sampled subset.

Correlation is not causation and this measure cannot separate "this decision
caused the failure" from "this decision marks the hard questions". The causal
version belongs on the shortlist this produces, not on every candidate.
"""

from __future__ import annotations

import argparse
import json
import math
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

SUPERLATIVE = re.compile(
    r"\b(highest|lowest|most|least|maximum|minimum|max|min|largest|smallest"
    r"|oldest|newest|longest|shortest|top|best|worst)\b", re.I)
MULTI_ASK = re.compile(
    r"\?.*\?|\band state\b|\band indicate\b|\band mention\b"
    r"|\balso (give|state|list|provide)\b", re.I)
YESNO = re.compile(r"^\s*(did|is|are|was|were|does|do|has|have|can|could|should)\b", re.I)
FORMULA_HINT = re.compile(
    r"=\s*(DIVIDE|MULTIPLY|SUBTRACT|SUM|COUNT|AVG|MAX|MIN)\s*\("
    r"|\b(percentage|proportion|rate|calculation)\s*=", re.I)


def _select(tree):
    if tree is None:
        return None
    return tree if isinstance(tree, exp.Select) else tree.find(exp.Select)


# Each candidate maps a question's record to one categorical value. They are
# deliberately over-inclusive; the ranking decides which survive.
def candidates(row, tree, events, selected_tables, hint) -> dict[str, str]:
    question = row.get("question", "") or ""
    select = _select(tree)
    joins = list(tree.find_all(exp.Join)) if tree is not None else []
    counts = list(tree.find_all(exp.Count)) if tree is not None else []
    executed = [e for e in events if e.get("tool") == "db.execute"]
    sampled = [e for e in events if e.get("tool") == "db.sample_values"]
    used_tables = (
        {t.name.casefold() for t in tree.find_all(exp.Table) if t.name}
        if tree is not None else set()
    )
    for cte in (tree.find_all(exp.CTE) if tree is not None else []):
        used_tables.discard(cte.alias_or_name.casefold())

    out: dict[str, str] = {}

    out["取证方式"] = (
        "执行+查值" if executed and sampled else
        "只执行SQL" if executed else "只查值" if sampled else "未取证")
    out["执行轮数"] = ("0 次" if not executed else "1 次" if len(executed) == 1
                       else "2 次" if len(executed) == 2 else "3+ 次")
    out["越出检索范围"] = (
        "无法判定" if not used_tables or not selected_tables
        else "只用检索选中的表" if used_tables <= selected_tables
        else "引入未选中的表")
    out["JOIN 数量"] = ("无 JOIN" if not joins else "1 个" if len(joins) == 1
                        else "2 个" if len(joins) == 2 else "3+ 个")
    out["查询结构"] = (
        "含 CTE" if tree is not None and list(tree.find_all(exp.CTE))
        else "含子查询" if tree is not None and list(tree.find_all(exp.Subquery))
        else "平铺")

    if not SUPERLATIVE.search(question):
        out["最值写法"] = "非最值题"
    else:
        eqmax = False
        for eq in (tree.find_all(exp.EQ) if tree is not None else []):
            for side in (eq.left, eq.right):
                if isinstance(side, exp.Subquery):
                    inner = side.find(exp.Select)
                    if inner and any(
                        isinstance(p.this if isinstance(p, exp.Alias) else p,
                                   (exp.Max, exp.Min)) for p in inner.expressions):
                        eqmax = True
        ordered = (tree is not None and list(tree.find_all(exp.Order))
                   and list(tree.find_all(exp.Limit)))
        out["最值写法"] = ("= (SELECT MAX)" if eqmax
                           else "ORDER BY+LIMIT" if ordered else "其他写法")

    if not counts:
        out["计数粒度"] = "非计数题"
    elif not joins:
        out["计数粒度"] = "计数无JOIN"
    else:
        distinct = any(isinstance(c.this, exp.Distinct) or c.args.get("distinct")
                       for c in counts)
        out["计数粒度"] = "计数去重" if distinct else "计数不去重"

    width = len(select.expressions) if select is not None else 0
    multi = bool(MULTI_ASK.search(question))
    out["输出宽度"] = (
        "无法解析" if select is None else
        ("多问句·多列" if width >= 2 else "多问句·单列") if multi else
        ("单问句·单列" if width == 1 else "单问句·多列"))

    out["拼接输出"] = "无法解析" if select is None else (
        "有 || 拼接" if any(list(p.find_all(exp.DPipe)) for p in select.expressions)
        else "无拼接")

    if YESNO.match(question):
        body = tree.sql(dialect="sqlite").upper() if tree is not None else ""
        out["是非题形式"] = ("YES/NO 字面量" if ("'YES'" in body or "IIF(" in body
                                                or "CASE WHEN" in body) else "返回匹配行")
    else:
        out["是非题形式"] = "非是非题"

    out["Hint 类型"] = "无公式" if not FORMULA_HINT.search(hint or "") else "含显式公式"
    out["排序方向"] = "未排序" if tree is None or not list(tree.find_all(exp.Order)) else (
        "含 DESC" if "DESC" in tree.sql(dialect="sqlite").upper() else "仅 ASC")

    answer = row.get("predicted_answer")
    out["结果状态"] = (
        "执行报错" if row.get("error") else
        "空结果" if answer is None or (isinstance(answer, list) and not answer)
        else "有结果")
    out["结果行数"] = (
        "非行集" if not isinstance(answer, list) else
        "0 行" if not answer else "1 行" if len(answer) == 1
        else "2-10 行" if len(answer) <= 10 else "10+ 行")
    return out


def mutual_information(values: list[str], correct: list[bool]) -> tuple[float, float]:
    """Bits about correctness gained by knowing this decision, and success spread."""
    n = len(values)
    base_p = sum(correct) / n
    def H(p):
        if p <= 0 or p >= 1:
            return 0.0
        return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))
    base = H(base_p)
    groups: dict[str, list[bool]] = defaultdict(list)
    for value, ok in zip(values, correct):
        groups[value].append(ok)
    conditional = sum(len(g) / n * H(sum(g) / len(g)) for g in groups.values())
    rates = [sum(g) / len(g) for g in groups.values() if len(g) >= 10]
    spread = (max(rates) - min(rates)) if len(rates) >= 2 else 0.0
    return base - conditional, spread


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--dataset", default="data/processed/bird_dev_500.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
    hints = {r["id"]: r.get("evidence") or "" for r in
             json.loads(Path(args.dataset).read_text(encoding="utf-8"))}
    events_by_id, model_sql, tables_by_id = {}, {}, {}
    with Path(args.trace).open(encoding="utf-8") as handle:
        for line in handle:
            rec = json.loads(line)
            trace = rec.get("_trace") or rec
            events_by_id[rec["id"]] = trace.get("events") or []
            rewrite = trace.get("sql_convention_rewrite") or {}
            if rewrite.get("changed") and rewrite.get("original_sql"):
                model_sql[rec["id"]] = rewrite["original_sql"]
            sel = ((trace.get("knowledge_selection") or {}).get("offline_schema") or {})
            cands = ((sel.get("table_selection") or {}).get("candidates") or [])
            tables_by_id[rec["id"]] = {
                c["table"].casefold() for c in cands if c.get("selected")}

    per_node: dict[str, list[str]] = defaultdict(list)
    correct: list[bool] = []
    for row in rows:
        try:
            tree = sqlglot.parse_one(
                model_sql.get(row["id"], row.get("predicted_sql")) or "", read="sqlite")
        except Exception:
            tree = None
        values = candidates(row, tree, events_by_id.get(row["id"], []),
                            tables_by_id.get(row["id"], set()), hints.get(row["id"], ""))
        for name, value in values.items():
            per_node[name].append(value)
        correct.append(bool(is_correct(row.get("predicted_answer"), row.get("gold_answer"))))

    ranked = []
    for name, values in per_node.items():
        mi, spread = mutual_information(values, correct)
        counts = Counter(values)
        informative = sum(1 for v in counts.values() if v >= 10)
        ranked.append({
            "node": name, "mi_bits": round(mi, 4), "spread": round(spread, 3),
            "branches": len(counts), "branches_ge10": informative,
            "values": [
                {"value": v, "n": c,
                 "rate": round(sum(1 for val, ok in zip(values, correct) if val == v and ok) / c, 3)}
                for v, c in counts.most_common()],
        })
    ranked.sort(key=lambda r: -r["mi_bits"])

    print(f'{len(rows)} 题，答对率 {sum(correct)/len(correct)*100:.1f}%')
    print(f'\n候选决策点按信息增益排序（bits）：\n')
    print(f'{"节点":<16}{"信息增益":>10}{"答对率极差":>12}{"分支":>6}')
    print('-' * 48)
    for entry in ranked:
        print(f'{entry["node"]:<16}{entry["mi_bits"]:>10.4f}{entry["spread"]:>12.1%}'
              f'{entry["branches"]:>6}')
    if args.output:
        Path(args.output).write_text(
            json.dumps(ranked, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f'\n已写入 {args.output}')
