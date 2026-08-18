"""Locate the first reasoning sentence that commits to the error, with a checkable claim.

Thought Anchors measures a sentence's importance by resampling from it a hundred
times and watching the answer distribution move. That needs the raw CoT put back in
to continue from; this deployment returns only summaries and accepts no partial
reasoning chain, so the paper's measurement is not available here (the plan
document says the same, and settles for turn-level).

What is available is weaker but checkable. Ask which sentence first commits to the
error, and require the answer to name a claim in that sentence that can be tested
against the database. bird_48 is the shape this is after: sentence 2 says "there
isn't a specific flag for that in the schema ... I might need to ignore it" and
drops the question's "merged" -- and `schools.StatusType = 'Merged'` exists, so the
claim is false and the location is not a matter of opinion.

The verification is what makes this worth running: a located sentence whose claim
turns out to be true means the location is wrong, and the script says so rather
than reporting a confident index. Output is a candidate plus its test, never a
measured importance -- do not write it up as one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

import litellm

litellm.drop_params = True
litellm.suppress_debug_info = True

from shared.llm_config import resolve_llm_config

INSTRUCTIONS = """\
You are given a text-to-SQL question, the reference SQL, the SQL an agent finally \
submitted, and the agent's numbered reasoning sentences from its first turn.

Find the EARLIEST sentence at which the agent commits to what makes its SQL wrong: \
the sentence where it adopts the wrong column, drops a condition the question asks \
for, fixes on a wrong literal, or settles a formula the wrong way. Ignore sentences \
that merely restate the question or express general uncertainty.

Answer as JSON, no prose:
{"index": <sentence index>,
 "commitment": "<what it commits to, one line>",
 "claim": "<a factual claim in that sentence that could be checked against the database, or null>",
 "check_sql": "<a SELECT that would test that claim, or null>",
 "confidence": "high" | "medium" | "low"}

If no single sentence commits to the error -- the SQL is wrong for a reason never \
articulated -- return index -1 and say so in `commitment`."""


def build_prompt(question: str, evidence: str, gold: str, pred: str, sentences: list[dict]) -> str:
    numbered = "\n".join(f"{i}: {s['text']}" for i, s in enumerate(sentences))
    return (
        f"QUESTION: {question}\n"
        f"EVIDENCE: {evidence}\n"
        f"REFERENCE SQL: {gold}\n"
        f"AGENT'S SQL: {pred}\n\n"
        f"REASONING SENTENCES:\n{numbered}"
    )


def locate(cfg, prompt: str) -> dict:
    response = litellm.completion(
        model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base,
        api_version=cfg.api_version, temperature=0,
        messages=[{"role": "system", "content": INSTRUCTIONS},
                  {"role": "user", "content": prompt}],
    )
    text = (response.choices[0].message.content or "").strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {"index": None, "error": "unparseable", "raw": text[:300]}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"index": None, "error": "bad json", "raw": text[:300]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True, help="sentence_labels_*.json")
    ap.add_argument("--results", required=True)
    ap.add_argument("--dataset", default=str(PROJECT_ROOT / "data/processed/bird_dev_500.json"))
    ap.add_argument("--output", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only-ids", default=None, help="JSON list of ids to restrict to")
    ap.add_argument("--jobs", type=int, default=3)
    args = ap.parse_args()

    cfg = resolve_llm_config()
    labels = {r["id"].split("@")[0]: r["sentences"]
              for r in json.loads(Path(args.labels).read_text(encoding="utf-8"))}
    results = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    data = {r["id"]: r for r in json.loads(Path(args.dataset).read_text(encoding="utf-8"))}

    failed = [q for q in labels if q in results and not results[q].get("correct")]
    if args.only_ids:
        keep = set(json.loads(Path(args.only_ids).read_text(encoding="utf-8")))
        failed = [q for q in failed if q in keep]
    if args.limit:
        failed = failed[:args.limit]

    out_path = Path(args.output)
    done = {}
    if out_path.exists():
        done = {r["id"]: r for r in json.loads(out_path.read_text(encoding="utf-8"))}
        print(f"Resuming — {len(done)} already located")
    todo = [q for q in failed if q not in done]
    print(f"Locating on {len(todo)} failed questions")

    lock = threading.Lock()

    def run_one(qid: str) -> None:
        row, sentences = results[qid], labels[qid]
        found = locate(cfg, build_prompt(
            row["question"], (data.get(qid) or {}).get("evidence") or "",
            row.get("gold_sql") or "", row.get("predicted_sql") or "", sentences,
        ))
        index = found.get("index")
        record = {
            "id": qid, "sentence_count": len(sentences), **found,
            "sentence_text": (sentences[index]["text"]
                              if isinstance(index, int) and 0 <= index < len(sentences) else None),
            "sentence_label": (sentences[index]["label"]
                               if isinstance(index, int) and 0 <= index < len(sentences) else None),
            "position_pct": (round(index / len(sentences) * 100, 1)
                             if isinstance(index, int) and 0 <= index < len(sentences) else None),
        }
        with lock:
            done[qid] = record
            out_path.write_text(json.dumps(list(done.values()), ensure_ascii=False, indent=1),
                                encoding="utf-8")
            print(f"  {qid}: idx={index} ({record['position_pct']}%) [{record['sentence_label']}]")

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(run_one, todo))
    print(f"\n{len(done)} located -> {out_path}")


if __name__ == "__main__":
    main()
