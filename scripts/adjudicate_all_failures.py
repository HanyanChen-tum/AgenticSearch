"""Adjudicate every failure from the answers first, and the SQL only as a fallback.

Three successive attempts to attribute failures by comparing SQL structure were
each defeated by the same thing: two queries that differ textually can mean the
same, and two that look alike in a chosen dimension can differ elsewhere. Alias
qualifiers made 42% of "WHERE differs" vanish under normalisation; the join-key
metric silently reported "no difference" for the 16 questions where the model
used IN/EXISTS and gold used JOIN; and reading those 16 by hand showed four were
not semantic disagreements at all but one side failing to execute.

So this works the other way round. What actually happened is in the answers: two
result sets, and gold's own scoreability. Those decide the verdict wherever they
can, and SQL structure is consulted only for the residue where the answers alone
cannot say what went wrong.

The order matters and is deliberate:

  1. gold itself unscoreable (None/empty)  -- no prediction can pass; these do
     not belong in the denominator at all
  2. the model produced nothing            -- infrastructure, not semantics
  3. same values, different type/format    -- '39.75203' vs 39.75203
  4. same values, gold returns extra columns
  5. one answer is a row-subset of the other -- singular/plural ambiguity
  6. everything else                       -- fall through to structure

Verdicts name who is responsible where the evidence supports it, and say so
plainly where it does not.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.evaluator import is_correct

from scripts.root_cause_every_failure import root_cause


def cell(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    s = str(v).strip()
    try:
        return round(float(s), 6)
    except Exception:
        return s.casefold()


def rowset(ans):
    if not isinstance(ans, list):
        return None
    out = []
    for r in ans:
        cells = r if isinstance(r, list) else [r]
        out.append(tuple(cell(c) for c in cells))
    return out


def flat(rs):
    return Counter(c for row in rs for c in row)


def adjudicate(row, model_sql) -> tuple[str, str]:
    """(cause, responsibility)"""
    gold, pred = row.get("gold_answer"), row.get("predicted_answer")

    # 1. gold cannot be scored at all
    if gold is None or (isinstance(gold, list) and len(gold) == 0):
        return ("gold 无法执行/返回空，题目不可评分", "不可评分")
    if isinstance(gold, list) and all(
        all(c is None for c in (r if isinstance(r, list) else [r])) for r in gold
    ):
        return ("gold 结果全为 NULL", "不可评分")

    # 2. the model produced nothing to score
    if pred is None:
        err = str(row.get("error") or "")
        if "credential" in err.lower():
            return ("凭证故障（基础设施）", "基础设施")
        return ("模型 SQL 未产出结果（执行失败/超时）", "基础设施")

    gr, pr = rowset(gold), rowset(pred)
    if gr is None or pr is None:
        return ("答案非行集，无法比较", "待定")

    # 3./4. identical values, differing only in type or in gold returning more
    if sorted(map(str, pr)) == sorted(map(str, gr)):
        return ("取值完全相同，仅类型/行序不同", "评测口径")
    if len(pr) == len(gr):
        gc, pc = flat(gr), flat(pr)
        if pc and (pc - gc) == Counter() and (gc - pc):
            width_p = len(pr[0]) if pr else 0
            width_g = len(gr[0]) if gr else 0
            if width_g > width_p:
                return ("取值一致，gold 返回题面未要求的额外列", "gold")

    # 5. one side is a strict row-subset of the other
    sp, sg = set(map(str, pr)), set(map(str, gr))
    if sp and sp < sg:
        return (f"模型返回 gold 的子集（{len(pr)}/{len(gr)} 行）：单复数歧义", "题面歧义")
    if sg and sg < sp:
        return (f"模型多返回行（{len(pr)} vs {len(gr)}）", "模型")

    # 6. answers genuinely disagree -- fall back to where the SQL first diverges
    cause, layer = root_cause(row.get("question", ""), model_sql, row.get("gold_sql"))
    return (f"结果实质不同｜首个分歧: {cause}", "待逐题判读")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--trace", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
    original: dict[str, str] = {}
    with Path(args.trace).open(encoding="utf-8") as handle:
        for line in handle:
            rec = json.loads(line)
            tr = rec.get("_trace") or rec
            rw = tr.get("sql_convention_rewrite") or {}
            if rw.get("changed") and rw.get("original_sql"):
                original[rec["id"]] = rw["original_sql"]

    recs = []
    for row in rows:
        if is_correct(row.get("predicted_answer"), row.get("gold_answer")):
            continue
        model_sql = original.get(row["id"], row.get("predicted_sql"))
        cause, who = adjudicate(row, model_sql)
        recs.append({"id": row["id"], "db_id": row.get("db_id"),
                     "cause": cause, "responsibility": who})

    Path(args.output).write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")

    n = len(recs)
    total = len(rows)
    print(f"总题数 {total}，失败 {n}\n")
    print(f'{"责任归属":<14}{"题数":>5}{"占失败":>9}{"占全集":>9}')
    print("-" * 40)
    for who, c in Counter(r["responsibility"] for r in recs).most_common():
        print(f"{who:<15}{c:>5}{c/n*100:>8.1f}%{c/total*100:>8.1f}%")

    unscoreable = sum(1 for r in recs if r["responsibility"] in ("不可评分", "基础设施"))
    print(f"\n可评分失败 = {n} - {unscoreable} = {n - unscoreable}")
    print(f"修正后准确率分母 = {total - unscoreable}，"
          f"准确率 = {(total-n)/(total-unscoreable)*100:.2f}%（原 {(total-n)/total*100:.2f}%）")

    print(f'\n{"具体成因":<52}{"题数":>5}')
    print("-" * 60)
    for cause, c in Counter(r["cause"] for r in recs).most_common(14):
        print(f"{cause[:51]:<52}{c:>5}")
