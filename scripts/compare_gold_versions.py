"""Separate two things a corrected benchmark changes at once.

Running on a corrected dataset moves the score for two unrelated reasons: the
reference answers changed, and it is a fresh sample of a stochastic agent. Reading
one run against the other conflates them -- this project has already measured 32
per-question flips between two runs of the same configuration, which is larger than
most interventions it has tried.

So three columns, on the same questions:

  A  original answers  vs original gold   -- the baseline as recorded
  B  original answers  vs corrected gold  -- A/B differ only in the reference
  C  corrected-run answers vs corrected gold -- B/C differ only in the sampling

Restricted by default to questions whose text and evidence the correction left
alone. Where the question was rewritten the model was asked something else, and no
column is comparable to any other.
"""

from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.evaluator import is_correct

_DB_CACHE: dict[str, str] = {}


def execute(db_id: str, sql: str, limit_seconds: float = 60.0):
    if not sql:
        return None
    path = _DB_CACHE.setdefault(
        db_id, glob.glob(str(PROJECT_ROOT / f"data/raw/bird/**/{db_id}/{db_id}.sqlite"), recursive=True)[0]
    )
    con = sqlite3.connect(path)
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    started = time.time()
    con.set_progress_handler(lambda: 1 if time.time() - started > limit_seconds else 0, 10000)
    try:
        return [list(r) for r in con.execute(sql).fetchall()]
    except Exception:
        return None
    finally:
        con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-results", required=True, help="run on the original dataset")
    ap.add_argument("--corrected-results", required=True, help="run on the corrected dataset")
    ap.add_argument("--corrected-dataset", required=True)
    ap.add_argument("--only-unchanged", action="store_true",
                    help="keep only questions whose text and evidence were not rewritten")
    ap.add_argument("--pure-gold-only", action="store_true",
                    help="keep only questions where nothing but the gold SQL changed")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    base = {r["id"]: r for r in json.loads(Path(args.baseline_results).read_text(encoding="utf-8"))}
    corr = {r["id"]: r for r in json.loads(Path(args.corrected_results).read_text(encoding="utf-8"))}
    dataset = {r["id"]: r for r in json.loads(Path(args.corrected_dataset).read_text(encoding="utf-8"))}

    ids = sorted(set(base) & set(corr) & set(dataset))
    if args.only_unchanged or args.pure_gold_only:
        ids = [q for q in ids
               if dataset[q].get("question_unchanged") and dataset[q].get("evidence_unchanged")]
    if args.pure_gold_only:
        original = {f"bird_{r['question_id']}": r for r in json.loads(
            (PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/mini_dev_sqlite.json").read_text(encoding="utf-8"))}
        ids = [q for q in ids
               if " ".join((dataset[q]["gold_sql"] or "").split()).lower()
               != " ".join((original[q]["SQL"] or "").split()).lower()]

    a = b = c = 0
    rows = []
    for qid in ids:
        gold_new = execute(dataset[qid]["db_id"], dataset[qid]["gold_sql"], 120)
        if gold_new is None:
            continue
        col_a = bool(base[qid].get("correct"))
        col_b = bool(is_correct(base[qid].get("predicted_answer"), gold_new))
        col_c = bool(corr[qid].get("correct"))
        a, b, c = a + col_a, b + col_b, c + col_c
        rows.append({"id": qid, "A_orig_orig": col_a, "B_orig_corrected": col_b, "C_new_corrected": col_c})

    n = len(rows)
    print(f"可比题数 {n}\n")
    print(f"  A 原答案 × 原 gold      : {a:>3}/{n} = {a/n*100:.1f}%")
    print(f"  B 原答案 × 修正 gold    : {b:>3}/{n} = {b/n*100:.1f}%   （仅参考答案变化 {b-a:+d}）")
    print(f"  C 新运行 × 修正 gold    : {c:>3}/{n} = {c/n*100:.1f}%   （再加采样变化 {c-b:+d}）")
    print(f"\n  A→C 合计 {c-a:+d}，其中参考答案贡献 {b-a:+d}、重新采样贡献 {c-b:+d}")

    if args.output:
        Path(args.output).write_text(json.dumps(
            {"n": n, "A_orig_orig": a, "B_orig_corrected": b, "C_new_corrected": c, "rows": rows},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
