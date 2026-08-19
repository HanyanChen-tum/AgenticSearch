"""Report how much work each question took, and whether that tracks being right.

Four step measures, because they answer different questions and disagree:

  llm_calls        agent turns -- how often the model was asked again
  tool_actions     db.execute / db.sample_values -- how much it looked at the data
  turns            deepest turn index reached in the trace
  reasoning_tokens tokens spent inside the model's own reasoning, the only measure
                   that moves with `reasoning_effort`

Most questions finish in one turn, so the first three are nearly constant and
`reasoning_tokens` carries the signal. Splitting by correctness is descriptive
only: a question that took more reasoning is usually a harder question, so a gap
between right and wrong answers measures difficulty at least as much as it
measures effort. Do not read it as "thinking longer causes errors" -- this
project has already been burned once by exactly that inference (the "wants to
verify" signal that turned out to be a difficulty proxy).

Harness-crashed questions are excluded: they stopped early for reasons that have
nothing to do with how much reasoning the question needed.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console

HARNESS = {"UnicodeEncodeError", "AttributeError", "BadRequestError", "APIError",
           "TimeoutError", "NotFoundError", "ContentPolicyViolationError"}
MEASURES = ("llm_calls", "tool_actions", "turns", "reasoning_tokens")


def load(stem: str):
    rows = json.loads((PROJECT_ROOT / "results" / f"{stem}.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in rows if r.get("termination") not in HARNESS}
    tr = PROJECT_ROOT / "trace" / stem / "transcripts.jsonl"
    if tr.exists():
        for line in tr.open(encoding="utf-8"):
            if not line.strip():
                continue
            t = json.loads(line)
            r = by_id.get(t.get("id"))
            if r is None:
                continue
            ev = t.get("events") or []
            r["tool_actions"] = sum(1 for e in ev if str(e.get("tool", "")).startswith("db."))
            r["turns"] = max([e.get("turn", 0) for e in ev] + [0])
    return by_id


def describe(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "—"
    vals = sorted(vals)
    p90 = vals[min(len(vals) - 1, int(len(vals) * 0.9))]
    return (f"n={len(vals):3d} 均值={st.mean(vals):8.1f} 中位={st.median(vals):7.1f} "
            f"p90={p90:8.1f} max={vals[-1]:8.1f}")


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="result file stems (without .json)")
    ap.add_argument("--by-difficulty", action="store_true")
    ap.add_argument("--output", default=None, help="write per-question rows as JSON")
    args = ap.parse_args()

    everything = []
    for stem in args.runs:
        by_id = load(stem)
        print(f"\n{'='*100}\n{stem}   可计分 {len(by_id)} 题")
        for m in MEASURES:
            ok = [r.get(m) for r in by_id.values() if r["correct"]]
            no = [r.get(m) for r in by_id.values() if not r["correct"]]
            allv = [r.get(m) for r in by_id.values()]
            print(f"  {m:17s} 全部  {describe(allv)}")
            print(f"  {'':17s} 答对  {describe(ok)}")
            print(f"  {'':17s} 答错  {describe(no)}")
        if args.by_difficulty:
            g = defaultdict(list)
            for r in by_id.values():
                g[r.get("difficulty", "unknown")].append(r)
            print(f"  {'-'*90}")
            for d in ("simple", "moderate", "challenging"):
                if d not in g:
                    continue
                rt = [r.get("reasoning_tokens") for r in g[d]]
                acc = sum(1 for r in g[d] if r["correct"]) / len(g[d]) * 100
                print(f"  {d:13s} acc={acc:5.1f}%  reasoning_tokens {describe(rt)}")
        for r in by_id.values():
            everything.append({"run": stem, "id": r["id"], "correct": r["correct"],
                               "difficulty": r.get("difficulty"),
                               **{m: r.get(m) for m in MEASURES}})

    if args.output:
        Path(args.output).write_text(json.dumps(everything, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
        print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
