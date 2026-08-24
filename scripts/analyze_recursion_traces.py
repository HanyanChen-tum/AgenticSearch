"""Split root and leaf reasoning apart on questions that invoked recursion, and
lay out the facts each failure needs to be read by hand.

Both sides share the parent's `_call_llm`, so their reasoning lands in one flat
`reasoning_capture` list tagged only with the *root's* turn counter -- a leaf
that ran 2 turns contributes 2 entries all carrying the root turn it was called
from. They are separable because the `recursive_llm` tool event records the
leaf's own turn count: within a root turn, the last `turns` entries are the
leaf's.

This script deliberately emits no verdict on *why* a question failed. An
earlier version did, classifying by token overlap between the leaf's answer and
the final SQL, and it was wrong on 5 of 6 cases when the transcripts were read
by hand: a leaf answering "Geoff Dalgas" and a SQL that correctly selects
DisplayName share no tokens, so the rule called it "leaf_unused" when the leaf
had in fact been used and the failure was a ties convention. SQL contains
column names and predicates, not answer text; surface overlap cannot stand in
for whether the delegation worked. The same mistake as this project's other
falsified mechanical rules -- see the four-times-falsified adjudication note in
the protocol, and the "non-empty result means the claim is confirmed" verifier
from this same session.

What comes out instead is, per question: the sub-questions asked, the answers
the leaf returned, whether the leaf terminated or ran out of turns, the final
SQL, and both answer sets. Reading those five things side by side is what
actually settles the question, and it is cheap at this sample size (6-9 failed
questions per run).
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


def split_root_leaf(captures: list[dict], events: list[dict]) -> dict:
    """Partition capture entries into the root's and the leaves'."""
    leaf_turns_by_root_turn: dict[int, int] = {}
    for e in events:
        if e.get("tool") != "recursive_llm":
            continue
        turn = e.get("turn", 0)
        leaf_turns_by_root_turn[turn] = (
            leaf_turns_by_root_turn.get(turn, 0) + ((e.get("result") or {}).get("turns") or 0)
        )

    by_turn: dict[int, list[dict]] = {}
    for c in captures:
        by_turn.setdefault(c.get("turn", 0), []).append(c)

    root, leaf = [], []
    for turn, entries in sorted(by_turn.items()):
        n_leaf = leaf_turns_by_root_turn.get(turn, 0)
        if n_leaf and len(entries) > n_leaf:
            root.extend(entries[: len(entries) - n_leaf])
            leaf.extend(entries[len(entries) - n_leaf :])
        else:
            root.extend(entries)
    return {"root": root, "leaf": leaf}


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    res = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    out = []
    with Path(args.trace).open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            events = row.get("events") or []
            rec_events = [e for e in events if e.get("tool") == "recursive_llm"]
            if not rec_events:
                continue
            r = res.get(row["id"])
            if r is None or not r.get("scored", True):
                continue
            captures = []
            for a in row.get("attempts") or []:
                captures.extend(a.get("reasoning_capture") or [])
            split = split_root_leaf(captures, events)
            out.append({
                "id": row["id"],
                "correct": r["correct"],
                "n_recursive_calls": len(rec_events),
                "root_capture_entries": len(split["root"]),
                "leaf_capture_entries": len(split["leaf"]),
                "calls": [
                    {
                        "sub_query": str((e.get("arguments") or {}).get("sub_query") or ""),
                        "leaf_answer": str((e.get("result") or {}).get("answer") or ""),
                        "leaf_turns": (e.get("result") or {}).get("turns"),
                        "leaf_terminated": (e.get("result") or {}).get("terminated"),
                    }
                    for e in rec_events
                ],
                "predicted_sql": r.get("predicted_sql"),
                "predicted_answer": r.get("predicted_answer"),
                "gold_sql": r.get("gold_sql"),
                "gold_answer": r.get("gold_answer"),
            })

    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    n_fail = sum(1 for r in out if not r["correct"])
    ran_out = sum(
        1 for r in out for c in r["calls"] if "ran out of turns" in c["leaf_answer"]
    )
    print(f"{len(out)} questions invoked recursion; {n_fail} of them failed")
    print(f"  leaf reasoning separated on {sum(1 for r in out if r['leaf_capture_entries'])}")
    print(f"  leaf calls that ran out of turns: {ran_out}")
    print(f"-> {args.output}   (no verdicts -- read the failed ones by hand)")


if __name__ == "__main__":
    main()
