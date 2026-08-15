"""Check whether the string literals a prediction filters on actually exist.

Reading the filter-layer failures turned up a repeating shape: the question's
hint names a value in prose, the model writes that prose into a WHERE clause,
and the column stores something else entirely. bird_1265's hint says '-' means
negative and '+-' means zero; the column holds 'negative' and '0'. bird_1275 has
the same hint and the same mismatch. The filter matches nothing, the query
returns an empty or wrong result, and nothing in the pipeline objects.

This is mechanically checkable without gold: for every string literal compared
against a column in the prediction, ask the database whether that column
contains that value. A literal matching zero rows is either a real empty answer
or -- far more often -- a value the model transcribed from prose instead of
verifying with db.sample_values, which it had available the whole time.

Reports coverage on failures and, importantly, the false-positive rate on
questions that are currently correct. A detector that fires on correct answers
is not usable as a rewrite trigger, the same trap that sank the tie-detection
and yes/no rules.
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

import sqlglot
from sqlglot import exp

from ours.db_environment import get_db_path
from scripts.run_bird_indomain_fewshot import BIRD_DB_DIR
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql


def literal_comparisons(sql: str) -> list[tuple[str, str, str]]:
    """(table_or_alias, column, literal) for every string literal compared to a column."""
    try:
        tree = sqlglot.parse_one(sql or "", read="sqlite")
    except Exception:
        return []

    alias_to_table: dict[str, str] = {}
    for table in tree.find_all(exp.Table):
        if table.name:
            alias_to_table[(table.alias or table.name).casefold()] = table.name
    single_table = list({t.name for t in tree.find_all(exp.Table) if t.name})

    out: list[tuple[str, str, str]] = []

    def record(col: exp.Column, lit: exp.Literal):
        if not lit.args.get("is_string"):
            return
        table = alias_to_table.get((col.table or "").casefold())
        if table is None:
            if len(single_table) != 1:
                return  # ambiguous without a qualifier; skip rather than guess
            table = single_table[0]
        out.append((table, col.name, str(lit.this)))

    for eq in tree.find_all(exp.EQ):
        for a, b in ((eq.left, eq.right), (eq.right, eq.left)):
            if isinstance(a, exp.Column) and isinstance(b, exp.Literal):
                record(a, b)
    for isin in tree.find_all(exp.In):
        if isinstance(isin.this, exp.Column):
            for value in isin.expressions or []:
                if isinstance(value, exp.Literal):
                    record(isin.this, value)
    return out


def unmatched_literals(db_path: str, sql: str) -> list[tuple[str, str, str]]:
    bad = []
    for table, column, literal in literal_comparisons(sql):
        probe = f'SELECT 1 FROM "{table}" WHERE "{column}" = ? LIMIT 1'
        result = execute_sql(db_path, probe, read_only=True, params=(literal,)) \
            if _supports_params() else execute_sql(
                db_path,
                f'''SELECT 1 FROM "{table}" WHERE "{column}" = '{literal.replace("'", "''")}' LIMIT 1''',
                read_only=True)
        if result.get("error"):
            continue  # unknown column/table -- a different failure mode, not ours
        if not (result.get("answer") or []):
            bad.append((table, column, literal))
    return bad


def _supports_params() -> bool:
    import inspect
    return "params" in inspect.signature(execute_sql).parameters


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results/e3_c_conv_rules_dev500_run1.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = json.loads(Path(args.results).read_text(encoding="utf-8"))
    records = []
    for row in rows:
        db_path = get_db_path(BIRD_DB_DIR, row["db_id"])
        bad = unmatched_literals(db_path, row.get("predicted_sql") or "")
        if not bad:
            continue
        records.append({
            "id": row["id"], "db_id": row["db_id"],
            "correct": bool(is_correct(row.get("predicted_answer"), row.get("gold_answer"))),
            "unmatched": [{"table": t, "column": c, "literal": l} for t, c, l in bad],
        })

    Path(args.output).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")

    total = len(rows)
    n_correct_total = sum(1 for r in rows if is_correct(r.get("predicted_answer"), r.get("gold_answer")))
    fired_wrong = [r for r in records if not r["correct"]]
    fired_right = [r for r in records if r["correct"]]
    print(f"{total} 题中，检测器命中 {len(records)} 题")
    print(f"  命中且当前答错（潜在可修）: {len(fired_wrong)}")
    print(f"  命中但当前答对（误报）:     {len(fired_right)}")
    if records:
        print(f"  精确率 = {len(fired_wrong)}/{len(records)} = {len(fired_wrong)/len(records)*100:.1f}%")
    print(f"  覆盖率 = {len(fired_wrong)}/{total - n_correct_total} 道失败题 "
          f"= {len(fired_wrong)/(total - n_correct_total)*100:.1f}%")
    print(f"\n已写入 {args.output}")
