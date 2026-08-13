"""Turn each question's trajectory into a path through decision nodes.

Harshal's ask from the Praktikum session: for 90% of cases, what path does the
model take, and for the long tail, where does it branch? Each branch point is a
decision, and an error is a decision made wrong.

The nodes are not hand-picked. `rank_decision_points.py` scored fourteen
SQL-shape candidates; `mine_trajectory_patterns.py` added six more read straight
off the real conversation (call count, turn count, whether a FINAL got written
before any tool result came back, whether the last turn revises that guess,
result shape against gold). The six stages here are the merged top six by
information gain across all twenty (`decision_point_ranking_combined.json`).
That matters twice over: the first version of this chart chose five nodes by
intuition and missed the two strongest entirely; this version's previous
six-SQL-feature ranking would have missed that two trajectory-only features
(result shape, call count) outrank all but one SQL-shape feature.

Result shape needs gold to compute, same as the older result-state/result-count
nodes -- it is a diagnostic bin over the finished run, not something the model
itself could have checked. Reading the actual reasoning behind it also showed it
is not one mechanism: of twenty resampled cases, only three or four reproduce as
"never checks for ties," four don't reproduce at all, three are gold logic bugs,
the rest split across the already-known yes/no and output-width nodes (see
`reasoning_trace_findings_2026-08-12.md` for the full breakdown). The statistic
survives at this scale; treat the node as a strong, honest lead, not a single
clean bug.
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

from scripts.mine_trajectory_patterns import result_shape, trajectory_features
from scripts.rank_decision_points import candidates
from shared.evaluator import is_correct

SUPERLATIVE = re.compile(
    r"\b(highest|lowest|most|least|maximum|minimum|max|min|largest|smallest"
    r"|oldest|newest|longest|shortest|top|best|worst)\b", re.I)
MULTI_ASK = re.compile(
    r"\?.*\?|\band state\b|\band indicate\b|\band mention\b"
    r"|\balso (give|state|list|provide)\b", re.I)


def _tree(sql: str):
    try:
        return sqlglot.parse_one(sql or "", read="sqlite")
    except Exception:
        return None


def stage_grounding(events: list[dict]) -> str:
    """Did it look at the database before committing, or answer from the prompt?"""
    executed = any(e.get("tool") == "db.execute" for e in events)
    sampled = any(e.get("tool") == "db.sample_values" for e in events)
    if executed and sampled:
        return "执行+查值"
    if executed:
        return "只执行SQL"
    if sampled:
        return "只查值"
    return "未取证"


def stage_ranking(question: str, tree) -> str:
    """On a superlative question, which of the two forms did it commit to?"""
    if tree is None or not SUPERLATIVE.search(question or ""):
        return "非最值题"
    ordered = bool(list(tree.find_all(exp.Order))) and bool(list(tree.find_all(exp.Limit)))
    for eq in tree.find_all(exp.EQ):
        for side in (eq.left, eq.right):
            if isinstance(side, exp.Subquery):
                inner = side.find(exp.Select)
                if inner and any(
                    isinstance(p.this if isinstance(p, exp.Alias) else p, (exp.Max, exp.Min))
                    for p in inner.expressions
                ):
                    return "= (SELECT MAX)"
    return "ORDER BY+LIMIT" if ordered else "其他写法"


def stage_grain(tree) -> str:
    """Counting across a join: entities or rows?"""
    if tree is None:
        return "非计数题"
    counts = list(tree.find_all(exp.Count))
    if not counts:
        return "非计数题"
    if not list(tree.find_all(exp.Join)):
        return "计数无JOIN"
    distinct = any(isinstance(c.this, exp.Distinct) or c.args.get("distinct") for c in counts)
    return "计数去重" if distinct else "计数不去重"


def stage_projection(question: str, tree) -> str:
    """Did the projection width match what a single-topic question asks for?"""
    if tree is None:
        return "无法解析"
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if select is None:
        return "无法解析"
    width = len(select.expressions)
    multi = bool(MULTI_ASK.search(question or ""))
    if multi:
        return "多问句·多列" if width >= 2 else "多问句·单列"
    return "单问句·单列" if width == 1 else "单问句·多列"


def stage_result(row: dict) -> str:
    answer = row.get("predicted_answer")
    if row.get("error"):
        return "执行报错"
    empty = answer is None or (isinstance(answer, list) and len(answer) == 0)
    return "空结果" if empty else "有结果"


# The merged top six by information gain (SQL-shape + trajectory-shape),
# ordered by when the underlying choice is actually made rather than by rank,
# so the ribbon reads left-to-right as the run unfolded: exploration effort,
# then the SQL shape drafted from it, then what came back on execution, then
# how that compares to gold.
STAGES = ["总调用次数", "查询结构", "输出宽度", "结果行数", "结果状态", "结果形状"]


def build(results_path: Path, trace_path: Path) -> dict:
    rows = json.loads(results_path.read_text(encoding="utf-8"))
    events_by_id: dict[str, list[dict]] = {}
    model_sql: dict[str, str] = {}
    tables_by_id: dict[str, set] = {}
    messages_by_id: dict[str, list[dict]] = {}
    if trace_path.exists():
        with trace_path.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                trace = record.get("_trace") or record
                events_by_id[record["id"]] = trace.get("events") or []
                messages_by_id[record["id"]] = trace.get("messages") or []
                # `predicted_sql` is post-rewrite. Charting it would show the
                # harness's choices as if they were the model's -- with the
                # DISTINCT rule on, no query ends up counting distinct at all.
                rewrite = trace.get("sql_convention_rewrite") or {}
                if rewrite.get("changed") and rewrite.get("original_sql"):
                    model_sql[record["id"]] = rewrite["original_sql"]
                sel = ((trace.get("knowledge_selection") or {}).get("offline_schema") or {})
                cands = ((sel.get("table_selection") or {}).get("candidates") or [])
                tables_by_id[record["id"]] = {
                    c["table"].casefold() for c in cands if c.get("selected")}

    hints = {r["id"]: r.get("evidence") or "" for r in json.loads(
        (PROJECT_ROOT / "data/processed/bird_dev_500.json").read_text(encoding="utf-8"))}

    paths = []
    for row in rows:
        tree = _tree(model_sql.get(row["id"], row.get("predicted_sql")))
        values = candidates(row, tree, events_by_id.get(row["id"], []),
                            tables_by_id.get(row["id"], set()), hints.get(row["id"], ""))
        values.update(trajectory_features(messages_by_id.get(row["id"], [])))
        values["结果形状"] = result_shape(row)
        node_values = [values[name] for name in STAGES]
        paths.append({
            "id": row["id"],
            "db_id": row.get("db_id"),
            "difficulty": row.get("difficulty"),
            "nodes": node_values,
            "correct": bool(is_correct(row.get("predicted_answer"), row.get("gold_answer"))),
        })

    # Sankey links: consecutive stages, split by outcome so a band's colour can
    # carry success rate rather than just volume.
    links: Counter = Counter()
    for path in paths:
        chain = path["nodes"] + ["答对" if path["correct"] else "答错"]
        for depth, (src, dst) in enumerate(zip(chain, chain[1:])):
            links[(depth, src, dst, path["correct"])] += 1

    return {
        "source": {"results": str(results_path.name), "trace": str(trace_path.name)},
        "question_count": len(paths),
        "correct_count": sum(1 for p in paths if p["correct"]),
        "stages": STAGES + ["判定"],
        "paths": paths,
        "links": [
            {"depth": d, "source": s, "target": t, "correct": c, "value": v}
            for (d, s, t, c), v in sorted(links.items(), key=lambda kv: -kv[1])
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    data = build(Path(args.results).resolve(), Path(args.trace).resolve())
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    n = data["question_count"]
    print(f'{n} 题，答对 {data["correct_count"]} ({data["correct_count"]/n*100:.1f}%)\n')
    for depth, stage in enumerate(data["stages"][:-1]):
        counts: Counter = Counter()
        ok: Counter = Counter()
        for path in data["paths"]:
            value = path["nodes"][depth]
            counts[value] += 1
            ok[value] += path["correct"]
        print(f'【{stage}】')
        for value, total in counts.most_common():
            print(f'   {value:<14} {total:>4} 题 ({total/n*100:4.1f}%)   答对率 {ok[value]/total*100:5.1f}%')
        print()
    print(f'不同路径总数: {len({tuple(p["nodes"]) for p in data["paths"]})}')