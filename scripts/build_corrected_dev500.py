"""Build a dev500 dataset from the externally corrected BIRD Mini-Dev annotations.

Source: uiuc-kang-lab/text_to_sql_benchmarks (VLDB 2026, arXiv:2601.08778), which
re-annotated the same 498 unique Mini-Dev questions and reports 52.8% of the
originals as carrying an annotation error.

Read the file names carefully before using either variant. `arcwise_plat_sql_only`
is not SQL-only: measured against BIRD's own `mini_dev_sqlite.json` it rewrites 81
questions and 68 evidence strings, and some of those rewrites change what is being
asked (`bird_1500` September 2013 -> August 2012; `bird_1501` June 2013 -> August
2012). `arcwise_plat_full` rewrites 147 questions and 140 evidence strings.

That matters twice over. Scoring answers written for the original question against
the rewritten question's gold is simply a mismatch -- so any cross-run comparison
has to be restricted to the subset where question and evidence are untouched, which
`--emit-valid-subset` writes out. And a run *on* this dataset is not a rerun of the
same benchmark: the model is being asked partly different questions, so its score
is not comparable to any number measured on the original.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BIRD_SOURCE = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/mini_dev_sqlite.json"


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrected", required=True, help="arcwise_plat_*_with_diff.json")
    ap.add_argument("--output", required=True)
    ap.add_argument("--emit-valid-subset", default=None,
                    help="write the ids whose question+evidence are unchanged")
    args = ap.parse_args()

    source = {f"bird_{r['question_id']}": r
              for r in json.loads(BIRD_SOURCE.read_text(encoding="utf-8"))}
    corrected = {f"bird_{r['question_id']}": r
                 for r in json.loads(Path(args.corrected).read_text(encoding="utf-8"))}

    rows, unchanged = [], []
    q_changed = e_changed = sql_changed = 0
    for qid, rec in corrected.items():
        origin = source.get(qid)
        if origin is None:
            continue
        same_q = norm(rec["question"]) == norm(origin["question"])
        same_e = norm(rec.get("evidence")) == norm(origin.get("evidence"))
        q_changed += not same_q
        e_changed += not same_e
        sql_changed += norm(rec["SQL"]).lower() != norm(origin["SQL"]).lower()
        if same_q and same_e:
            unchanged.append(qid)
        rows.append({
            "id": qid,
            "db_id": rec["db_id"],
            "question": rec["question"],
            "evidence": rec.get("evidence"),
            "gold_sql": rec["SQL"],
            "difficulty": rec.get("difficulty") or origin.get("difficulty"),
            "source": f"arcwise-corrected:{Path(args.corrected).name}",
            # Kept per row so a later comparison never has to re-derive which
            # questions are answerable-as-originally-asked.
            "question_unchanged": same_q,
            "evidence_unchanged": same_e,
        })

    rows.sort(key=lambda r: r["id"])
    Path(args.output).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} questions -> {args.output}")
    print(f"  rewritten vs BIRD source: question {q_changed}, evidence {e_changed}, SQL {sql_changed}")
    print(f"  question+evidence untouched: {len(unchanged)} "
          f"({len(unchanged)/len(rows)*100:.1f}%) -- the only ids comparable across datasets")
    if args.emit_valid_subset:
        Path(args.emit_valid_subset).write_text(json.dumps(sorted(unchanged)), encoding="utf-8")
        print(f"  ids written to {args.emit_valid_subset}")


if __name__ == "__main__":
    main()
