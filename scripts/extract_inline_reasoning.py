"""Pull inline-captured reasoning out of a run's transcripts, one record per turn.

`capture_reasoning.py` replays a recorded prompt afterwards, and because sampling
is not pinned that returns *a* reasoning chain for the prompt rather than the one
behind the recorded answer -- on bird_93 the replay queried the database while the
original run never did. A profile with `reasoning_capture` set records the chain
during the generation that produced the answer, which is what this reads.

Records come out one per (question, turn) with a composite id `bird_93@turn1`, so
`label_reasoning_sentences.py` works on them unchanged and the turn stays legible
in the output. Turn 1 is the one to look at first: this project's own replay
evidence puts 91% of failures as already wrong in the first draft.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True, help="transcripts.jsonl from a reasoning_capture run")
    ap.add_argument("--output", required=True)
    ap.add_argument("--turn", type=int, default=None, help="keep only this turn (1-based)")
    args = ap.parse_args()

    records, empty, questions = [], 0, 0
    with Path(args.trace).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            captures = []
            for attempt in row.get("attempts") or []:
                captures.extend(attempt.get("reasoning_capture") or [])
            if not captures:
                empty += 1
                continue
            questions += 1
            for index, capture in enumerate(captures, start=1):
                if args.turn is not None and index != args.turn:
                    continue
                sections = capture.get("reasoning_sections") or []
                if not sections:
                    continue
                records.append({
                    "id": f"{row['id']}@turn{index}",
                    "question_id": row["id"],
                    "turn": index,
                    "reasoning_sections": sections,
                    "section_count": capture.get("section_count", len(sections)),
                    "reasoning_tokens": capture.get("reasoning_tokens"),
                })

    Path(args.output).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{questions} questions with reasoning ({empty} without) -> {len(records)} turn records")
    print(f"  {sum(r['section_count'] for r in records)} sections -> {args.output}")


if __name__ == "__main__":
    main()
