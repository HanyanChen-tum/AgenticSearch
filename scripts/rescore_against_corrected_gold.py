"""Rescore a run recorded on the original dataset against the corrected gold.

Downstream trace work needs two things this produces: which questions actually
failed, and the reference SQL to show a locator. Both change under the corrected
gold -- 16 of the 74 pure-gold questions flip from wrong to right without the
model's bytes moving (failure_adjudication_final_2026-08-16.md §3.7) -- so a
failure set carried over from the original scoring points at the wrong questions.

Restricted by default to questions the correction left textually alone. Where the
question or the evidence was rewritten, the recorded answer was given to a
different prompt, and scoring it against the new reference measures nothing. The
duplicate rows in the corrected file (bird_137, bird_138 appear twice) collapse
by id.

Output keeps the input record shape, with gold_sql, gold_answer and correct
replaced, so it can be passed straight to the trace scripts as --results.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console
from shared.evaluator import is_correct
from scripts.compare_gold_versions import execute


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="run recorded on the original dataset")
    ap.add_argument("--corrected-dataset", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument(
        "--all-questions",
        action="store_true",
        help="skip the unchanged-text restriction (the numbers stop being comparable)",
    )
    args = ap.parse_args()

    runs = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    dataset = {}
    for row in json.loads(Path(args.corrected_dataset).read_text(encoding="utf-8")):
        dataset[row["id"]] = row  # later duplicate wins; the pair is identical

    ids = sorted(set(runs) & set(dataset))
    if not args.all_questions:
        ids = [
            q for q in ids
            if dataset[q].get("question_unchanged") and dataset[q].get("evidence_unchanged")
        ]

    out, ungradable = [], []
    was = now = 0
    to_right, to_wrong = [], []
    for qid in ids:
        row, gold = dict(runs[qid]), dataset[qid]
        gold_answer = execute(gold["db_id"], gold["gold_sql"], 120)
        if gold_answer is None:
            # A reference that will not execute cannot score anything; §3.7 drops
            # these rather than counting them against the model.
            ungradable.append(qid)
            continue
        before = bool(row.get("correct"))
        after = (
            row.get("predicted_answer") is not None
            and is_correct(row.get("predicted_answer"), gold_answer)
        )
        row["gold_sql"] = gold["gold_sql"]
        row["gold_answer"] = gold_answer
        row["correct"] = after
        row["correct_original_gold"] = before
        out.append(row)
        was += before
        now += after
        if after and not before:
            to_right.append(qid)
        if before and not after:
            to_wrong.append(qid)

    Path(args.output).write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    n = len(out)
    print(f"{Path(args.results).name} -> {Path(args.output).name}")
    print(f"  scored          {n} questions"
          f"{'' if args.all_questions else ' (question + evidence unchanged)'}")
    print(f"  original gold   {was}/{n} = {was/n*100:.1f}%")
    print(f"  corrected gold  {now}/{n} = {now/n*100:.1f}%   ({now-was:+d})")
    print(f"  wrong -> right  {len(to_right)}")
    print(f"  right -> wrong  {len(to_wrong)}")
    print(f"  failures now    {n - now}")
    if ungradable:
        print(f"  dropped (gold will not execute) {len(ungradable)}: {', '.join(ungradable[:8])}")


if __name__ == "__main__":
    main()
