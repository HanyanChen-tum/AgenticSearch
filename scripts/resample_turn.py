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

from ours.agent.config import get_agent_config
from ours.agent.question_analysis import parse_analysis
from ours.agent.query_plan import QueryPlanState
from ours.agent.state import AgentExecutionState
from ours.db_environment import DBEnvironment, get_db_path
from ours.recursive_db_rlm import _format_structured_observations
from scripts.capture_reasoning import RESPONSES_API_VERSION, as_responses_input, load_turns
from scripts.run_bird_indomain_fewshot import BIRD_DB_DIR, InDomainFewShotDBRLM
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


# 2026-08-24 v2 finding: marking drafts invalid (above) instead of scoring them
# was correct but exposed something bigger than bird_637 -- at k=1 (no prior
# context) the model almost never submits a clean FINAL-only response; 5-10 of
# 10 resamples across nearly all 28 Phase A questions are drafts. Discarding
# them left k=1 with 0-1 valid samples per question, nowhere near enough to
# measure anything (see the "二次更正" section of phase_a_turn_resampling_
# 2026-08-24.md). A draft is a real, informative event; the fix is not to
# throw it away but to do what the real harness does with it: execute the
# code, feed the observation back, and let the model take its real next
# turn -- then score *that*.
#
# This reuses the harness's own REPL/observation-formatting code (not a
# reimplementation): a bare InDomainFewShotDBRLM instance is built, wired with
# just enough trace state (_db, _trace_events, _execution_state,
# _query_plan_state) for `_build_repl_env` and `self.repl.execute` to behave
# exactly as ours/recursive_db_rlm.py:598-622 does mid-loop, then the same
# `_format_structured_observations` renders the feedback text. Everything
# outside that -- the LLM call itself -- still goes through one_sample(), so
# the generation path is unchanged.
_DISCARD_CONTINUE_CAP = 3  # extra LLM calls chasing a clean FINAL; the QA protocol spends one on the analysis turn


def _make_repl_agent(cfg, agent_config) -> InDomainFewShotDBRLM:
    return InDomainFewShotDBRLM(
        model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base,
        max_iterations=1, temperature=0, retriever=None, k=0,
        agent_config=agent_config,
    )


def execute_draft(agent: InDomainFewShotDBRLM, db_path, response_text: str) -> str:
    """Run a discarded draft's code for real and return the same structured
    observation text the real harness would feed back next turn."""
    agent._trace_turn = 0
    agent._trace_events = []
    agent._execution_state = AgentExecutionState()
    agent._query_plan_state = QueryPlanState()
    agent._db = DBEnvironment(str(db_path), event_sink=agent._record_tool_event)

    response_for_repl = re.sub(r'FINAL\s*\(.*?\)', '', response_text, flags=re.DOTALL).strip()
    repl_env = agent._build_repl_env(query="", context="")
    event_start = len(agent._trace_events)
    try:
        exec_result = agent.repl.execute(response_for_repl, repl_env)
    except Exception as exc:  # matches the bare except in the real loop
        exec_result = f"Unexpected error: {exc}"

    structured_events = [e for e in agent._trace_events[event_start:]
                         if str(e.get("tool", "")).startswith("db.")]
    if structured_events:
        observation = _format_structured_observations(structured_events)
        if exec_result in {"Code executed successfully (no output)", "No code to execute"}:
            exec_result = observation
        else:
            exec_result = f"{exec_result}\n\n{observation}"
    return exec_result


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


def generate_with_continuation(cfg, agent_config, db_path, instructions, body, summary):
    """One resample, continuing past discarded drafts instead of throwing them
    away. Returns (text_or_None, total_section_count, n_drafts_seen,
    gave_up_after_cap). `text` is None only when the model never produced any
    FINAL at all, or when the cap was hit while still drafting -- the caller
    tells the two apart via `gave_up_after_cap`."""
    agent = None
    total_sections, n_drafts = 0, 0
    turn1_had_code = None
    analysis = None
    local_body = list(body)
    for attempt in range(_DISCARD_CONTINUE_CAP + 1):
        text, sections = one_sample(cfg, instructions, local_body, summary)
        total_sections += sections
        if turn1_had_code is None:
            # Health of the loop at the point this experiment intervenes: the
            # health-era traces put a python block in 93.9-95.8% of turn-1
            # messages, the dead ones in 0%. Under the question-analysis
            # protocol turn 1 is the analysis block by design, so this is only
            # comparable to those traces on arms without that protocol.
            turn1_had_code = bool(_HAS_CODE_RE.search(text or ""))

        # An analysis-only reply is not a failure to answer -- the QA protocol
        # requires turn 1 to be the fenced block and nothing else ("No Python,
        # no SQL in that reply"). Scoring it as "no FINAL() found" is what made
        # arm B return 9 valid samples out of 460. Feed it back the way the real
        # loop does and let the model take the turn it was told to take next.
        parsed, _errors = parse_analysis(text or "")
        if parsed is not None and analysis is None:
            analysis = parsed
        # Deliberately not conditioned on the analysis parsing cleanly: a reply
        # with neither code nor FINAL has not answered, whatever it contains, so
        # continuing is right either way and a malformed block does not silently
        # become "no FINAL() found".
        incomplete = (
            not _HAS_CODE_RE.search(text or "")
            and "FINAL(" not in (text or "")
            and "FINAL_VAR(" not in (text or "")
        )
        if incomplete:
            if attempt == _DISCARD_CONTINUE_CAP:
                return None, total_sections, n_drafts, True, turn1_had_code, analysis
            local_body = local_body + [
                {"role": "assistant", "content": text},
                {"role": "user", "content":
                 "Analysis accepted. Now work normally: use the tools if you need "
                 "database evidence, then submit with FINAL(\"your sql\")."},
            ]
            continue

        if not would_be_discarded(text):
            return text, total_sections, n_drafts, False, turn1_had_code, analysis
        n_drafts += 1
        if attempt == _DISCARD_CONTINUE_CAP:
            return None, total_sections, n_drafts, True, turn1_had_code, analysis
        if agent is None:
            agent = _make_repl_agent(cfg, agent_config)
        observation = execute_draft(agent, db_path, text)
        local_body = local_body + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": observation},
        ]
    return None, total_sections, n_drafts, True, turn1_had_code, analysis  # unreachable


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
                           drop_fewshot=False, system_prompt=None):
    """Resample one question up to n times, resuming from `existing` samples."""
    db_path = get_db_path(BIRD_DB_DIR, row["db_id"])
    messages = load_turns(trace_path, row["id"])
    if not messages:
        print(f"  {row['id']:<12} 跳过：trace 中无该题或无消息")
        return existing
    instructions, body = as_responses_input(messages, resume_turn)
    if drop_fewshot:
        body = strip_fewshot(body)
    if system_prompt is not None:
        # Swapping the system prompt is only a clean intervention at
        # resume_turn=1, where the prefix is system+user and carries no
        # assistant turn generated under the *other* prompt. Past that the
        # recorded turns were produced by the trace's own prompt, so the arms
        # would differ by prompt and by history at once.
        if resume_turn != 1:
            raise ValueError(
                f"--system-prompt needs --resume-turn 1 (got {resume_turn}): later "
                "turns replay assistant messages written under the recorded prompt"
            )
        instructions = system_prompt
    agent_config = get_agent_config(row["agent_profile"])

    samples = list(existing)
    for i in range(len(samples), n):
        try:
            text, section_count, n_drafts, gave_up, turn1_had_code, analysis = generate_with_continuation(
                cfg, agent_config, db_path, instructions, body, summary)
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
        if gave_up:
            # Real harness would keep looping past max_iterations; this script
            # caps continuations at _DISCARD_CONTINUE_CAP to bound cost. Distinct
            # from "no FINAL() found" -- the model did keep drafting, it just
            # never reached a clean submission within the cap.
            record = {"sample": i, "sql": None, "correct": None, "n_drafts": n_drafts,
                      "error": f"draft persisted after {_DISCARD_CONTINUE_CAP} continuations, gave up",
                      "section_count": section_count, "turn1_had_code": turn1_had_code}
            samples.append(record)
            continue
        sql = extract_sql(text)
        if sql is None:
            record = {"sample": i, "sql": None, "correct": None, "error": "no FINAL() found",
                      "n_drafts": n_drafts, "section_count": section_count,
                      "analysis": analysis, "turn1_had_code": turn1_had_code}
        else:
            ex = execute_sql(db_path, sql, read_only=True)
            ok = ex.get("error") is None and is_correct(ex.get("answer"), row.get("gold_answer"))
            record = {"sample": i, "sql": sql, "correct": bool(ok), "n_drafts": n_drafts,
                      "exec_error": ex.get("error"), "section_count": section_count,
                      "analysis": analysis, "turn1_had_code": turn1_had_code}
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
    parser.add_argument("--system-prompt", default=None,
                        help="replace the trace's system prompt with this prompt profile "
                             "(requires --resume-turn 1; the contract-vs-plain arm)")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    system_prompt = None
    if args.system_prompt:
        from ours.agent.prompts import get_system_prompt
        system_prompt = get_system_prompt(args.system_prompt)
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
                                         drop_fewshot=args.drop_fewshot,
                                         system_prompt=system_prompt)
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
                                             drop_fewshot=args.drop_fewshot,
                                             system_prompt=system_prompt)
            with lock:
                all_samples[qid] = samples
                out.write_text(json.dumps(all_samples, ensure_ascii=False, indent=1), encoding="utf-8")

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(run_and_save, qid) for qid in todo]
            for f in as_completed(futures):
                f.result()

        print(f"\n已写入 {out}（{len(all_samples)} 题）")
