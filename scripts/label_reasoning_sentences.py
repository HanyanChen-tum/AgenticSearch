"""Label every reasoning sentence with the Thought Anchors taxonomy.

`build_reasoning_timeline.py` works at the section level and buckets by keyword.
Both limits matter: a titled section runs 3-10 sentences and routinely changes
what it is doing partway through, and keyword rules on this corpus have already
produced two conclusions that fell apart on inspection -- "the model abandons
verification because it thinks the tools are dead" (its tool-call rate is 96%
either way) and "wanting to verify predicts failure" (wanting to verify is a
proxy for the question being hard).

So this splits each captured section into sentences and asks the model itself to
label each one with the eight categories from Thought Anchors (Bogdan et al.
2025, arXiv 2506.19143):

  PS  problem setup           restating or interpreting the question
  PG  plan generation         deciding what to do next
  FR  fact retrieval          recalling schema, values, or SQL knowledge
  AC  active computation      writing or evaluating the actual SQL/arithmetic
  UM  uncertainty management  flagging doubt, weighing alternatives, hedging
  RC  result consolidation    combining findings into an intermediate conclusion
  SC  self checking           verifying earlier work
  FAE final answer emission   committing to the answer

One honest deviation from the paper, to be carried into any report: the sentences
are from Azure's reasoning *summaries*, not the raw CoT, which the deployment does
not return. Segmentation is therefore finer than this project's previous
section-level work but still coarser than the paper's.
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

CATEGORIES = ["PS", "PG", "FR", "AC", "UM", "RC", "SC", "FAE"]

TITLE_RE = re.compile(r"^\*\*(.+?)\*\*\s*", re.M)
SENT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"“\d])')

INSTRUCTIONS = """\
You label sentences from a text-to-SQL agent's reasoning trace, using the taxonomy \
from the Thought Anchors paper. Reply with one label per sentence, nothing else.

PS  problem setup           restating, parsing or interpreting the question/schema task
PG  plan generation         deciding what to do next, choosing an approach
FR  fact retrieval          recalling schema facts, column/value knowledge, SQL semantics
AC  active computation      writing, editing or mentally evaluating SQL or arithmetic
UM  uncertainty management  flagging doubt, weighing alternatives, hedging, guessing
RC  result consolidation    combining observations into an intermediate conclusion
SC  self checking           re-examining or verifying earlier work or an assumption
FAE final answer emission   committing to / stating the final answer

Output format: one line per input sentence, exactly `<index>: <LABEL>`.
Use only the eight labels. Do not explain."""


def split_sentences(record: dict) -> list[dict]:
    out = []
    for section_index, section in enumerate(record.get("reasoning_sections") or []):
        title_match = TITLE_RE.match(section)
        title = title_match.group(1).strip() if title_match else ""
        body = TITLE_RE.sub("", section).strip()
        for text in SENT_RE.split(body):
            text = text.strip()
            if len(text) > 3:
                out.append({"section": section_index, "section_title": title, "text": text})
    return out


def label_batch(cfg, sentences: list[str]) -> list[str]:
    numbered = "\n".join(f"{i}: {s}" for i, s in enumerate(sentences))
    response = litellm.completion(
        model=cfg.model,
        api_key=cfg.api_key,
        api_base=cfg.api_base,
        api_version=cfg.api_version,
        messages=[
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": numbered},
        ],
        temperature=0,
    )
    text = response.choices[0].message.content or ""
    labels: dict[int, str] = {}
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s*[:.)-]\s*([A-Z]{2,3})", line.strip())
        if m and m.group(2) in CATEGORIES:
            labels[int(m.group(1))] = m.group(2)
    # A sentence the labeller skipped or mislabelled is recorded as such rather
    # than guessed at, so coverage is visible in the output instead of implied.
    return [labels.get(i, "UNLABELED") for i in range(len(sentences))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", required=True, help="reasoning_capture_*.json")
    ap.add_argument("--ids", default=None, help="JSON list of ids; default: all in capture")
    ap.add_argument("--output", required=True)
    ap.add_argument("--batch", type=int, default=40, help="sentences per API call")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()

    cfg = resolve_llm_config()
    capture = {r["id"]: r for r in json.loads(Path(args.capture).read_text(encoding="utf-8"))}
    ids = json.loads(Path(args.ids).read_text(encoding="utf-8")) if args.ids else list(capture)
    ids = [q for q in ids if q in capture]

    out_path = Path(args.output)
    done: dict[str, dict] = {}
    if out_path.exists():
        done = {r["id"]: r for r in json.loads(out_path.read_text(encoding="utf-8"))}
        print(f"Resuming — {len(done)} already labelled")
    todo = [q for q in ids if q not in done]
    print(f"Labelling {len(todo)} questions ({sum(len(split_sentences(capture[q])) for q in todo)} sentences)")

    lock = threading.Lock()

    def run_one(qid: str) -> None:
        sentences = split_sentences(capture[qid])
        texts = [s["text"] for s in sentences]
        labels: list[str] = []
        for start in range(0, len(texts), args.batch):
            chunk = texts[start:start + args.batch]
            try:
                labels.extend(label_batch(cfg, chunk))
            except Exception as exc:  # a failed batch must not lose the question
                labels.extend(["ERROR"] * len(chunk))
                print(f"  {qid} batch@{start}: {type(exc).__name__}")
        for sentence, label in zip(sentences, labels):
            sentence["label"] = label
        with lock:
            done[qid] = {"id": qid, "sentence_count": len(sentences), "sentences": sentences}
            out_path.write_text(
                json.dumps(list(done.values()), ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"  {qid}: {len(sentences)} sentences ({len(done)}/{len(ids)})")

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(run_one, todo))

    total = sum(r["sentence_count"] for r in done.values())
    bad = sum(1 for r in done.values() for s in r["sentences"] if s["label"] in ("UNLABELED", "ERROR"))
    print(f"\n{len(done)} questions, {total} sentences, {bad} unlabelled ({bad/total*100:.1f}%)")


if __name__ == "__main__":
    main()
