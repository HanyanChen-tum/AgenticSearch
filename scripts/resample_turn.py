"""Turn-level counterfactual resampling -- the coarsest feasible analogue of
Thought Anchors' sentence-level resampling for a closed reasoning model.

Thought Anchors truncates a reasoning chain mid-sentence and resamples the
continuation, because they can see and edit the raw CoT tokens. We cannot: the
Responses API returns a compressed summary, not an editable token stream, and the
hidden reasoning state behind it cannot be intervened on mid-generation. The
coarsest point we *can* truncate at is a real turn boundary -- right after a tool
observation comes back, before the next assistant message is generated.

That boundary is genuinely load-bearing in this harness, not an arbitrary
substitute: `capture_reasoning.py` and this project's own trace reading (bird_1265,
bird_959) show the model routinely writes a provisional FINAL alongside its first
tool calls, before seeing any result, and then either revises or reproduces that
guess once the observation comes back. Resampling from right after the
observation measures how much the eventual answer actually depends on what came
back, versus how often the model just resubmits its pre-commitment -- an
observational stand-in for counterfactual importance, at turn rather than
sentence granularity.
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

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

import litellm

litellm.drop_params = True
litellm.suppress_debug_info = True

from ours.db_environment import get_db_path
from scripts.capture_reasoning import RESPONSES_API_VERSION, as_responses_input, load_turns
from scripts.run_bird_indomain_fewshot import BIRD_DB_DIR
from shared.evaluator import is_correct
from shared.llm_config import resolve_llm_config
from shared.sql_executor import execute_sql

FINAL_RE = re.compile(r'FINAL\(\s*"((?:[^"\\]|\\.)*)"\s*\)', re.S)

# The real harness (ours/recursive_db_rlm.py:507,539) only accepts a FINAL when
# `is_final(response) and not has_code` -- a response that carries both a
# ```python block and a FINAL() has its FINAL discarded, the code runs instead,
# and the loop continues. Extracting via FINAL_RE alone (as this script did
# before) scores that discarded draft as if it had been submitted, inflating
# k=1 accuracy on questions where the model writes a premature FINAL alongside
# its first tool call (bird_637: phase_a_turn_resampling_2026-08-24.md).
_HAS_CODE_RE = re.compile(r"```python")


def would_be_discarded(response_text: str) -> bool:
    is_final = "FINAL(" in (response_text or "") or "FINAL_VAR(" in (response_text or "")
    return is_final and bool(_HAS_CODE_RE.search(response_text or ""))

# The few-shot block runs from its own header to whichever section header
# follows it. Matched by exact known header text, not a generic ALL-CAPS
# pattern: "OFFLINE SCHEMA CONTEXT (SCHEMA V4, retrieved before the run):"
# (ours/agent/offline_metadata.py) has parens and lowercase before its colon,
# so a generic "[A-Z][A-Z ]+:\n" pattern skips past it and over-matches into
# "JOIN GRAPH EDGES AROUND RETRIEVED TABLES:" further down the same block --
# caught by manual inspection before this shipped, not in review.
_BLOCK_HEADERS_AFTER_FEWSHOT = (
    "\nOFFLINE SCHEMA CONTEXT",  # offline_metadata_mode != "none" (ours/agent/offline_metadata.py:425)
    "\nFollow the Hint above",   # tail sentence, when both later blocks are empty
)
FEWSHOT_BLOCK_RE = re.compile(
    r"SIMILAR SOLVED EXAMPLES.*?(?=" + "|".join(re.escape(h) for h in _BLOCK_HEADERS_AFTER_FEWSHOT) + r"|\Z)",
    re.S)


def strip_fewshot(body: list[dict]) -> list[dict]:
    """Drop the retrieved few-shot block from the first user message.

    Isolates whether a specific retrieved example is what a question's failure
    causally depends on (arm B), against the recorded run unchanged (arm A) --
    see docs/analysis/week_2026-08-18/phase_a_turn_resampling_2026-08-24.md,
    bird_637: the retrieved example's output shape (a dedicated one-tag-per-row
    join table) does not match the target question's actual shape (tags packed
    into one delimited string column), and the model's SQL follows the example.
    """
    out = []
    for m in body:
        if m["role"] == "user" and "SIMILAR SOLVED EXAMPLES" in m["content"]:
            m = {**m, "content": FEWSHOT_BLOCK_RE.sub("", m["content"])}
        out.append(m)
    return out


def extract_sql(output_text: str) -> str | None:
    m = FINAL_RE.search(output_text or "")
    if not m:
        return None
    return m.group(1).replace('\\"', '"').replace("\\n", "\n")


def one_sample(cfg, instructions: str, body: list[dict], summary: str) -> tuple[str, int]:
    response = litellm.responses(
        model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base,
        api_version=RESPONSES_API_VERSION,
        instructions=instructions, input=body,
        reasoning={"effort": "high", "summary": summary},
    )
    payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    text, section_count = [], 0
    for item in payload.get("output", []):
        if item.get("type") == "reasoning":
            section_count += len(item.get("summary") or [])
        elif item.get("type") == "message":
            for part in item.get("content") or []:
                if part.get("text"):
                    text.append(part["text"])
    return "\n".join(text), section_count


def resample_one_question(cfg, trace_path, row, resume_turn, n, summary, existing,
                           drop_fewshot=False):
    """Resample one question up to n times, resuming from `existing` samples."""
    db_path = get_db_path(BIRD_DB_DIR, row["db_id"])
    messages = load_turns(trace_path, row["id"])
    if not messages:
        print(f"  {row['id']:<12} 跳过：trace 中无该题或无消息")
        return existing
    instructions, body = as_responses_input(messages, resume_turn)
    if drop_fewshot:
        body = strip_fewshot(body)

    samples = list(existing)
    for i in range(len(samples), n):
        try:
            text, section_count = one_sample(cfg, instructions, body, summary)
        except Exception as exc:
            # A single refused or failed call must not take the batch down with it:
            # Azure's content filter rejects some BIRD prompts outright
            # (harness_defects_2026-08-18.md §五), and one such rejection used to
            # propagate out of the pool and discard every question in the k-batch,
            # including ones already paid for. Record it as an invalid sample --
            # the same shape as "no FINAL() found" -- and keep going.
            samples.append({"sample": i, "sql": None, "correct": None,
                            "error": f"{type(exc).__name__}: {exc}"[:200],
                            "section_count": 0})
            continue
        if would_be_discarded(text):
            # Same shape as "no FINAL() found" -- neither is a real submission --
            # but recorded under a distinct reason so the two can be told apart
            # when reading results: this one *did* commit to an answer, the real
            # harness just never would have accepted it this turn.
            record = {"sample": i, "sql": None, "correct": None,
                      "error": "draft FINAL discarded (response also had ```python; "
                               "real harness runs the code and continues instead)",
                      "section_count": section_count}
            samples.append(record)
            continue
        sql = extract_sql(text)
        if sql is None:
            record = {"sample": i, "sql": None, "correct": None, "error": "no FINAL() found",
                      "section_count": section_count}
        else:
            ex = execute_sql(db_path, sql, read_only=True)
            ok = ex.get("error") is None and is_correct(ex.get("answer"), row.get("gold_answer"))
            record = {"sample": i, "sql": sql, "correct": bool(ok),
                      "exec_error": ex.get("error"), "section_count": section_count}
        samples.append(record)
    n_ok = sum(1 for s in samples if s.get("correct"))
    n_valid = sum(1 for s in samples if s.get("correct") is not None)
    print(f"  {row['id']:<12} {n_ok}/{n_valid} correct across {len(samples)} resamples")
    return samples


if __name__ == "__main__":
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True)
    parser.add_argument("--results", required=True)
    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--id", help="single question id")
    id_group.add_argument("--ids", nargs="+", help="batch of question ids")
    parser.add_argument("--resume-turn", type=int, required=True,
                        help="regenerate this assistant turn (1-indexed); everything before it is fixed")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--summary", default="detailed", choices=["detailed", "auto"])
    parser.add_argument("--jobs", type=int, default=6, help="concurrent questions (batch mode only)")
    parser.add_argument("--drop-fewshot", action="store_true",
                        help="strip the retrieved SIMILAR SOLVED EXAMPLES block before resampling "
                             "(arm B of the few-shot counterfactual; see bird_637 in "
                             "phase_a_turn_resampling_2026-08-24.md)")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    cfg = resolve_llm_config("azure/seminar-gpt-5.4-mini")
    trace_path = Path(args.trace).resolve()
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.id:
        # Single-question mode keeps the flat list shape this script originally used.
        samples = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
        print(f"{args.id}: resampling turn {args.resume_turn}, already have {len(samples)}, target {args.n}")
        samples = resample_one_question(cfg, trace_path, rows[args.id], args.resume_turn,
                                         args.n, args.summary, samples,
                                         drop_fewshot=args.drop_fewshot)
        out.write_text(json.dumps(samples, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        # Batch mode: one dict keyed by id, resumable and written after every question.
        all_samples: dict[str, list] = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        todo = [i for i in args.ids if len(all_samples.get(i, [])) < args.n]
        print(f"{len(args.ids)} 题，jobs={args.jobs}，待补齐 {len(todo)} 题（目标每题 {args.n} 次）")
        lock = threading.Lock()

        def run_and_save(qid: str):
            samples = resample_one_question(cfg, trace_path, rows[qid], args.resume_turn,
                                             args.n, args.summary, all_samples.get(qid, []),
                                             drop_fewshot=args.drop_fewshot)
            with lock:
                all_samples[qid] = samples
                out.write_text(json.dumps(all_samples, ensure_ascii=False, indent=1), encoding="utf-8")

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(run_and_save, qid) for qid in todo]
            for f in as_completed(futures):
                f.result()

        print(f"\n已写入 {out}（{len(all_samples)} 题）")
