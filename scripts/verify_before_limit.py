"""Test a gated re-verification loop, as an alternative to both rejected
fixes for the "assumes uniqueness" bug (bird_959, bird_1092, bird_930, bird_412).

Both prior attempts failed because they let a mechanical SQL-shape check decide
the outcome: silently rewriting away LIMIT 1 broke 7 correct answers for every 3
it fixed, and a blanket "avoid boolean" rule turned out to contradict 29% of
train gold. Neither approach uses judgment about whether the ambiguity actually
matters for *this* question -- a mechanical check can't know that "who is older,
A or B" has 1000 rows in the underlying table but only 2 relevant ones.

This instead reuses the REACT observation loop that already works in this
post-processing: detect the LIMIT-1 pattern, silently execute the de-limited query
(deterministic, free, outside the model), and if it returns more than one distinct
value, hand that concrete fact back to the model as a new observation -- the
same shape as a real `db.execute` result -- and let the model decide with
evidence in hand, exactly as it already does for every other tool call. The
detector can be high-recall (over-flag) here in a way it could not for a blind
rewrite, because a false positive just asks the model a question it can dismiss
in one line, instead of silently corrupting a correct answer.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from scripts.capture_reasoning import RESPONSES_API_VERSION, load_turns
from scripts.resample_turn import extract_sql, one_sample
from scripts.run_bird_indomain_fewshot import BIRD_DB_DIR
from shared.evaluator import is_correct
from shared.llm_config import resolve_llm_config
from shared.sql_executor import execute_sql

LIMIT1 = re.compile(r"\bLIMIT\s+1\b(\s*;?\s*)$", re.I)

PROMPT_TEMPLATE = (
    "STRUCTURED TOOL OBSERVATIONS (authoritative):\n"
    "OBSERVATION_REF verify: re-executing your FINAL query with LIMIT 50 instead of "
    "LIMIT 1 returns {n_rows} rows, {n_distinct} of them distinct: {sample}\n\n"
    "Reconsider: does the question genuinely ask for a single answer, or does it ask "
    "for all matching values? If a single answer is correct, resubmit the identical "
    "FINAL. If multiple values are what the question is actually asking for, resubmit "
    "FINAL with a query that returns all of them (no LIMIT 1)."
)


def as_full_input(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "".join(m["content"] for m in messages if m["role"] == "system")
    body = [m for m in messages if m["role"] != "system"]
    return system, body


def build_verify_prompt(db_path: str, sql: str) -> str | None:
    limited = LIMIT1.sub(r"LIMIT 50\1", sql.strip())
    ex = execute_sql(db_path, limited, read_only=True)
    if ex.get("error"):
        return None
    vals = ex.get("answer") or []
    if not isinstance(vals, list) or len(vals) < 2:
        return None
    distinct = list({tuple(v) for v in vals if isinstance(v, list)})
    if len(distinct) <= 1:
        return None
    sample = distinct[:10]
    return PROMPT_TEMPLATE.format(n_rows=len(vals), n_distinct=len(distinct), sample=sample)


def process_one(cfg, trace_path: Path, row: dict) -> dict | None:
    messages = load_turns(trace_path, row["id"])
    if not messages:
        return None
    original_sql = (row.get("predicted_sql") or "").strip()
    db_path = get_db_path(BIRD_DB_DIR, row["db_id"])
    verify_msg = build_verify_prompt(db_path, original_sql)
    if verify_msg is None:
        return None

    instructions, body = as_full_input(messages)
    body = body + [{"role": "user", "content": verify_msg}]
    try:
        text, _ = one_sample(cfg, instructions, body, "detailed")
    except Exception as exc:
        return {"id": row["id"], "error": f"{type(exc).__name__}: {exc}"[:160]}

    new_sql = extract_sql(text)
    before_ok = bool(is_correct(row.get("predicted_answer"), row.get("gold_answer")))
    if new_sql is None:
        return {"id": row["id"], "before_correct": before_ok, "after_correct": None,
                "changed": None, "error": "no FINAL() found"}
    ex = execute_sql(db_path, new_sql, read_only=True)
    after_ok = ex.get("error") is None and is_correct(ex.get("answer"), row.get("gold_answer"))
    changed = new_sql.strip() != original_sql
    return {"id": row["id"], "before_correct": before_ok, "after_correct": bool(after_ok),
            "changed": changed, "new_sql": new_sql if changed else None, "error": None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results/e3_c_conv_rules_dev500_run1.json")
    parser.add_argument("--trace", default="trace/e3_c_conv_rules_dev500_run1/transcripts.jsonl")
    parser.add_argument("--targets", required=True, help="JSON file: list of {id, ...}")
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    target_ids = [t["id"] for t in json.loads(Path(args.targets).read_text(encoding="utf-8"))]

    cfg = resolve_llm_config("azure/seminar-gpt-5.4-mini")
    trace_path = Path(args.trace).resolve()
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    done = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    done_ids = {d["id"] for d in done}
    todo = [i for i in target_ids if i not in done_ids]
    print(f"{len(target_ids)} 题，已完成 {len(done_ids)}，待跑 {len(todo)}")

    lock = threading.Lock()

    def run_and_save(qid: str):
        rec = process_one(cfg, trace_path, rows[qid])
        if rec is None:
            return
        with lock:
            done.append(rec)
            out.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        tag = ("skip:" + rec["error"]) if rec.get("error") else (
            f'{rec["before_correct"]}->{rec["after_correct"]}' + (" [改写]" if rec["changed"] else ""))
        print(f"  {qid:<12} {tag}")

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_and_save, qid) for qid in todo]
        for f in as_completed(futures):
            f.result()

    valid = [d for d in done if d.get("after_correct") is not None]
    gained = sum(1 for d in valid if not d["before_correct"] and d["after_correct"])
    broken = sum(1 for d in valid if d["before_correct"] and not d["after_correct"])
    changed = sum(1 for d in valid if d["changed"])
    print(f"\n{len(valid)} 题有效 | 改写了 {changed} 题 | 恢复 {gained} | 打坏 {broken} | 净 {gained - broken:+d}")
