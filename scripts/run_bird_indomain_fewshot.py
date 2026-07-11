"""DB-RLM with in-domain BIRD few-shot retrieval (k=1).

Uses correct examples from our own v4 run (same 11 BIRD databases).
Retrieves the single most similar example, prioritizing same-database matches.
This avoids schema bloat (1 example vs 3) and domain mismatch (BIRD vs Spider).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ast
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from ours.recursive_db_rlm import DBRLM, _SYSTEM_PROMPT, _STOP_SEQUENCES, _truncate_at_fake_turn, _convert_sql_blocks
from ours.db_environment import get_db_path, DBEnvironment
from ours.bird_few_shot_retriever import get_bird_retriever
from ours.db_hints import get_db_hint
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql
from src.rlm.parser import parse_response, is_final
from src.rlm.repl import REPLError

BIRD_DB_DIR  = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"
BIRD_DATASET = PROJECT_ROOT / "data/processed/bird_dev_500.json"


class InDomainFewShotDBRLM(DBRLM):
    """DB-RLM with a single in-domain BIRD example injected per question."""

    def __init__(self, *args, retriever=None, k=1, **kwargs):
        super().__init__(*args, **kwargs)
        self._retriever = retriever
        self._k = k

    def complete_sql(self, question: str, db_path, evidence: str = "") -> str:
        self._db = DBEnvironment(db_path)
        self._evidence = evidence.strip()
        return self.complete(query=question)

    async def acomplete(self, query: str = "", context: str = "", **kwargs):
        from src.rlm.core import MaxIterationsError, MaxDepthError

        if query and not context:
            context = query
            query = ""

        if self._current_depth >= self.max_depth:
            raise MaxDepthError(f"Max recursion depth ({self.max_depth}) exceeded")

        repl_env = self._build_repl_env(query, context)
        question = query or context
        schema_str = self._db.format_schema() if hasattr(self, "_db") else "(no schema)"
        evidence = getattr(self, "_evidence", "")

        evidence_block = (
            f"\n⚠️  HINT (follow these definitions EXACTLY):\n  {evidence}\n"
            if evidence else ""
        )

        db_id = getattr(self._db, "db_path", Path("")).stem
        db_hint = get_db_hint(db_id)
        db_hint_block = (
            f"\n📌 DATABASE NOTES:\n" + "\n".join(f"  {l}" for l in db_hint.splitlines()) + "\n"
            if db_hint else ""
        )

        # Single in-domain example
        few_shot_block = ""
        if self._retriever:
            few_shot_block = "\n" + self._retriever.format_examples(question, db_id=db_id, k=self._k) + "\n"

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"QUESTION: {question}"
                    f"{evidence_block}"
                    f"{db_hint_block}"
                    f"{few_shot_block}\n"
                    f"Schema:\n{schema_str}\n\n"
                    "Follow the Hint above, explore the DB if needed, test your SQL, then FINAL(\"your sql\")."
                ),
            },
        ]

        kwargs.setdefault("stop", _STOP_SEQUENCES)
        last_exec_result = None
        repeat_count = 0
        last_was_empty = False

        for iteration in range(self.max_iterations):
            self._iterations = iteration + 1
            response = await self._call_llm(messages, **kwargs)
            response = _truncate_at_fake_turn(response)
            response = _convert_sql_blocks(response)

            has_code = bool(re.search(r'```python', response))
            if is_final(response) and not has_code:
                if last_was_empty:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": (
                        "⛔ BLOCKED: last SQL returned 0 rows. Fix before calling FINAL()."
                    )})
                    last_was_empty = False
                    continue
                answer = parse_response(response, repl_env)
                if answer is not None:
                    return answer

            response_for_repl = re.sub(r'FINAL\s*\(.*?\)', '', response, flags=re.DOTALL).strip()
            try:
                exec_result = self.repl.execute(response_for_repl, repl_env)
            except REPLError as e:
                exec_result = f"REPL Error: {e}"
            except Exception as e:
                exec_result = f"Error: {e}"

            result_data = None
            try:
                result_data = ast.literal_eval(exec_result) if isinstance(exec_result, str) else None
            except Exception:
                pass

            last_was_empty = False
            if isinstance(result_data, dict):
                if result_data.get("error"):
                    exec_result += f"\n\n⚠️ SQL ERROR: {result_data['error']} — fix your SQL."
                elif result_data.get("rows") == []:
                    exec_result += "\n\n⚠️ WARNING: 0 rows returned. Check your WHERE/JOIN."
                    last_was_empty = True
                elif (rows := result_data.get("rows")) and all(
                    all(v is None for v in row) for row in rows
                ):
                    exec_result += (
                        "\n\n⚠️ WARNING: result is all NULL — the column you selected is "
                        "empty for these rows. You likely need a JOIN to another table "
                        "instead of this column."
                    )
                    last_was_empty = True

            if exec_result == last_exec_result:
                repeat_count += 1
                if repeat_count >= 2:
                    exec_result += "\n\nYou already have this. Call FINAL(\"your sql\")."
                    repeat_count = 0
            else:
                repeat_count = 0
            last_exec_result = exec_result

            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": exec_result})

        raise MaxIterationsError("Max iterations exceeded")


def run_one(example: dict, database_dir: Path, agent: InDomainFewShotDBRLM) -> dict:
    db_path = get_db_path(database_dir, example["db_id"])
    started = time.perf_counter()
    predicted_sql = ""
    termination = "error"
    error_msg = None

    for attempt in range(3):
        try:
            predicted_sql = agent.complete_sql(
                example["question"], db_path,
                evidence=example.get("evidence", ""),
            )
            termination = "final"
            break
        except KeyboardInterrupt:
            raise
        except Exception as e:
            error_msg = str(e)
            termination = type(e).__name__
            # Retry infra failures; model failures (MaxIterations etc.) are real results
            if attempt < 2 and any(s in termination for s in ("API", "Connection", "Timeout")):
                time.sleep(5 * (attempt + 1))
                continue
            break

    predicted_exec = (
        execute_sql(db_path, predicted_sql, read_only=True)
        if predicted_sql else {"answer": None, "error": error_msg or "No SQL"}
    )
    gold_exec = execute_sql(db_path, example["gold_sql"], read_only=True)

    return {
        "id": example["id"],
        "method": "bird_indomain_fewshot_db_rlm",
        "db_id": example["db_id"],
        "question": example["question"],
        "difficulty": example.get("difficulty", "unknown"),
        "predicted_sql": predicted_sql,
        "predicted_answer": predicted_exec.get("answer"),
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec.get("answer"),
        "correct": (
            predicted_exec.get("error") is None
            and gold_exec.get("error") is None
            and is_correct(predicted_exec.get("answer"), gold_exec.get("answer"))
        ),
        "error": predicted_exec.get("error") or gold_exec.get("error"),
        "latency_seconds": round(time.perf_counter() - started, 4),
        "llm_calls": agent.stats["llm_calls"],
        "termination": termination,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset",        default=str(BIRD_DATASET))
    parser.add_argument("--database-dir",   default=str(BIRD_DB_DIR))
    parser.add_argument("--output",         default=str(PROJECT_ROOT / "results/bird_indomain_fewshot_500.json"))
    parser.add_argument("--model",          default="azure/seminar-gpt-5.4-mini")
    parser.add_argument("--api-base",       default=None)
    parser.add_argument("--limit",          type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=15)
    parser.add_argument("--k",              type=int, default=1)
    parser.add_argument("--temperature",    type=float, default=0)
    parser.add_argument("--reasoning-effort", default=None,
                        help="gpt-5 family reasoning effort: minimal/low/medium/high")
    parser.add_argument("--no-fewshot", action="store_true",
                        help="disable retrieval few-shot (static prompt examples only)")
    parser.add_argument("--sleep",          type=float, default=0)
    args = parser.parse_args()

    questions = json.loads(Path(args.dataset).read_text())
    if args.limit:
        questions = questions[:args.limit]

    if "groq" in args.model:
        api_key = os.environ.get("GROQ_API_KEY")
        api_base = args.api_base
    elif "azure" in args.model:
        api_key = os.environ.get("LLM_API_KEY")
        api_base = args.api_base or os.environ.get("LLM_BASE_URL")
    else:
        api_key = None
        api_base = args.api_base

    retriever = None if args.no_fewshot else get_bird_retriever()

    extra = {}
    if args.reasoning_effort:
        extra["reasoning_effort"] = args.reasoning_effort

    agent = InDomainFewShotDBRLM(
        model=args.model,
        api_key=api_key,
        api_base=api_base,
        max_iterations=args.max_iterations,
        temperature=args.temperature,
        retriever=retriever,
        k=args.k,
        **extra,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)

    results = []
    done_ids = set()
    if output_path.exists():
        results = json.loads(output_path.read_text())
        done_ids = {r["id"] for r in results}
        print(f"Resuming — {len(done_ids)} already done")

    questions = [q for q in questions if q["id"] not in done_ids]
    print(f"Running {len(questions)} questions with k={args.k} in-domain BIRD example(s)")

    for ex in tqdm(questions, desc="BIRD-InDomainFewShot"):
        agent._llm_calls = 0
        agent._iterations = 0
        try:
            results.append(run_one(ex, Path(args.database_dir), agent))
        except KeyboardInterrupt:
            print(f"\nInterrupted — {len(results)} saved")
            output_path.write_text(json.dumps(results, indent=2))
            break
        output_path.write_text(json.dumps(results, indent=2))
        if args.sleep > 0:
            time.sleep(args.sleep)

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    print(f"\nAccuracy: {correct}/{total} = {correct/total:.2%}")
    by_diff = {}
    for r in results:
        by_diff.setdefault(r.get("difficulty", "unknown"), []).append(r["correct"])
    for d, vals in sorted(by_diff.items()):
        print(f"  {d}: {sum(vals)}/{len(vals)} = {sum(vals)/len(vals):.2%}")


if __name__ == "__main__":
    main()
