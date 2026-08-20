"""Rebuild the formula-hint ablation set on the corrected dataset.

`rootcause/hint_ablation_2026-08-08.md` found evidence is net *helpful*: emptying
it on the 89 dev500 questions whose hint states an explicit formula moved 55.1%
to 41.6% (-13.5pp). That detection ran on the original evidence text. The
external correction rewrote 140 evidence fields, so the 89-question set and what
their hints say may both have changed -- the original finding cannot be assumed
to carry over without re-detecting on the corrected text.

Same detector as scripts/classify_first_draft_causes.py and
scripts/rank_decision_points.py (`=\s*(DIVIDE|MULTIPLY|...)\s*\(`), so a
question counts as "formula-hint" here exactly as it did in those two analyses.

Output: two dataset files, identical except the ablated one empties `evidence`
on the detected questions. Feed both through the same agent config and diff.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console

FORMULA = re.compile(r"=\s*(DIVIDE|MULTIPLY|SUBTRACT|SUM|COUNT|AVG|MAX|MIN)\s*\(", re.I)


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(PROJECT_ROOT / "data/processed/bird_dev_500_corrected_full.json"))
    ap.add_argument("--out-ids", default=str(PROJECT_ROOT / "data/processed/hint_ablation_corrected_ids.json"))
    ap.add_argument("--out-ablated", default=str(PROJECT_ROOT / "data/processed/bird_dev_500_corrected_hint_ablated.json"))
    args = ap.parse_args()

    rows = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    hit = [r["id"] for r in rows if FORMULA.search(r.get("evidence") or "")]

    ablated = []
    for r in rows:
        r = dict(r)
        if r["id"] in hit:
            r["evidence"] = ""
        ablated.append(r)

    Path(args.out_ids).write_text(json.dumps(sorted(hit), indent=1), encoding="utf-8")
    Path(args.out_ablated).write_text(json.dumps(ablated, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"formula-hint questions: {len(hit)} / {len(rows)}")
    print(f"-> {args.out_ids}")
    print(f"-> {args.out_ablated}")


if __name__ == "__main__":
    main()
