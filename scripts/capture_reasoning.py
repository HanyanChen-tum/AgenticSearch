"""Capture the model's reasoning for questions that were already run.

The Chat Completions deployment reports `reasoning_tokens` but never the reasoning
itself, so 86% of what the model produced has been invisible for the whole
project. Azure's Responses API does return it, as summary text, given
api-version 2025-03-01-preview or later and `reasoning.summary`.

This is deliberately a diagnostic path, not an evaluation one. It replays the
exact messages a recorded run sent, so the reasoning corresponds to a generation
that actually happened, and it leaves the evaluation pipeline -- and therefore
every baseline number -- untouched.

Summaries are not the raw reasoning tokens. They arrive as several titled
sections, which is what makes them usable for sentence-level attribution in the
style of Thought Anchors: each section is one replaceable unit.
"""

from __future__ import annotations

import argparse
import json
import sys
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

# The deployment's configured api-version predates the Responses API; requesting
# it explicitly avoids editing .env and changing every other call in the project.
RESPONSES_API_VERSION = "2025-03-01-preview"


def load_turns(trace_path: Path, question_id: str) -> list[dict] | None:
    """The exact messages a recorded run sent for this question."""
    with trace_path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("id") != question_id:
                continue
            return (record.get("_trace") or record).get("messages") or []
    return None


def as_responses_input(messages: list[dict], upto_turn: int) -> tuple[str, list[dict]]:
    """Split recorded chat messages into (instructions, input) for Responses.

    `upto_turn` counts assistant turns to keep, so turn 1 reproduces the first
    generation -- the one the project's own evidence says decides the outcome.
    """
    system = "".join(m["content"] for m in messages if m["role"] == "system")
    body, seen = [], 0
    for message in messages:
        if message["role"] == "system":
            continue
        if message["role"] == "assistant":
            if seen >= upto_turn - 1:
                break
            seen += 1
        body.append({"role": message["role"], "content": message["content"]})
    return system, body


def capture(cfg, instructions: str, body: list[dict], summary: str) -> dict:
    response = litellm.responses(
        model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base,
        api_version=RESPONSES_API_VERSION,
        instructions=instructions, input=body,
        reasoning={"effort": "high", "summary": summary},
    )
    payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    sections, text = [], []
    for item in payload.get("output", []):
        if item.get("type") == "reasoning":
            for part in item.get("summary") or []:
                sections.append(part.get("text", ""))
        elif item.get("type") == "message":
            for part in item.get("content") or []:
                if part.get("text"):
                    text.append(part["text"])
    usage = payload.get("usage") or {}
    return {
        "reasoning_sections": sections,
        "section_count": len(sections),
        "output_text": "\n".join(text),
        "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


def process_one(cfg, trace_path: Path, question_id: str, turn: int, summary: str) -> dict | None:
    """One question's full capture, isolated so a thread pool can run many in parallel."""
    messages = load_turns(trace_path, question_id)
    if not messages:
        print(f"  {question_id:<12} 跳过：trace 中无该题或无消息")
        return None
    instructions, body = as_responses_input(messages, turn)
    try:
        result = capture(cfg, instructions, body, summary)
    except Exception as exc:
        print(f"  {question_id:<12} 失败：{type(exc).__name__}: {str(exc)[:120]}")
        return None
    print(f"  {question_id:<12} 推理段 {result['section_count']} 段"
          f" | reasoning_tokens {result['reasoning_tokens']}")
    return {"id": question_id, "turn": turn, **result}


if __name__ == "__main__":
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, help="path to transcripts.jsonl")
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--turn", type=int, default=1,
                        help="which assistant turn to reproduce (default: the first)")
    parser.add_argument("--summary", default="detailed", choices=["detailed", "auto"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--jobs", type=int, default=6,
                        help="concurrent API calls (I/O-bound, safe to parallelize)")
    args = parser.parse_args()

    cfg = resolve_llm_config("azure/seminar-gpt-5.4-mini")
    trace_path = Path(args.trace).resolve()
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # Resumable: a large batch that dies partway through must not lose what
    # already completed -- re-running the same command should only fill gaps.
    captured: list[dict] = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    done_ids = {c["id"] for c in captured if c.get("turn") == args.turn}
    todo = [i for i in args.ids if i not in done_ids]
    print(f"{len(args.ids)} 题，已完成 {len(done_ids)}，待抓 {len(todo)}（jobs={args.jobs}）")

    lock = threading.Lock()

    def run_and_save(question_id: str):
        record = process_one(cfg, trace_path, question_id, args.turn, args.summary)
        if record is None:
            return
        with lock:
            captured.append(record)
            out.write_text(json.dumps(captured, ensure_ascii=False, indent=1), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_and_save, qid) for qid in todo]
        for f in as_completed(futures):
            f.result()  # surface any thread exception immediately

    print(f"\n已写入 {out}（累计 {len(captured)} 题）")
