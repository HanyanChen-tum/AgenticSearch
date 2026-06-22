"""DB-RLM: RLM adapter for Text-to-SQL on Spider/BIRD databases."""

from __future__ import annotations

import re
import time
import asyncio
from pathlib import Path
from typing import Any, Optional

from src.rlm.core import RLM, MaxIterationsError, MaxDepthError
from src.rlm.parser import parse_response, is_final
from src.rlm.repl import REPLError
from src.rlm.types import Message

from ours.db_environment import DBEnvironment, get_db_path


_SYSTEM_PROMPT = """\
You are a Text-to-SQL expert. The database schema is provided — no exploration needed.

WORKFLOW (3 steps):

Step 1 — THINK (plain text, no code block):
  Read the question. Identify: which tables, which columns, any JOIN/WHERE/GROUP BY/ORDER BY needed.

Step 2 — TEST (one code block):
  ```python
  print(db.execute("YOUR SQL HERE"))
  ```
  Check the result makes sense for the question.

Step 3 — FINALIZE (plain text, NOT inside any code or function):
  FINAL("YOUR SQL HERE")

IMPORTANT — FINAL() rules:
  • Write FINAL() as plain text on its own line — NOT inside print(), NOT inside db.execute()
  • Correct:   FINAL("SELECT count(*) FROM singer")
  • Wrong:     print(db.execute("FINAL(...)"))
  • Wrong:     db.execute("FINAL(...)")

OTHER RULES:
  - Do NOT call get_tables() or get_schema() — schema is already provided.
  - Do NOT do SELECT * for exploration — go straight to your answer SQL.
  - ONE code block per turn. Stop after it. No "Observation:" or "User:".
"""

# Stop sequences that prevent the model from hallucinating fake turns
_STOP_SEQUENCES = ["\nUser:", "\n### User", "\nObservation:", "\nSystem:"]


class DBRLM(RLM):
    """RLM subclass wired to a SQLite database for Text-to-SQL generation.

    Usage:
        agent = DBRLM(model="ollama/qwen2.5:7b", api_base="http://localhost:11434")
        sql = agent.complete_sql("How many singers do we have?", db_path)
    """

    def complete_sql(self, question: str, db_path: str | Path) -> str:
        """Synchronous entry point: question + db_path → SQL string."""
        self._db = DBEnvironment(db_path)
        return self.complete(query=question)

    # ------------------------------------------------------------------
    # Override: inject `db` into the REPL environment
    # ------------------------------------------------------------------

    def _build_repl_env(self, query: str, context: str) -> dict[str, Any]:
        env = super()._build_repl_env(query, context)
        if hasattr(self, '_db'):
            env['db'] = self._db
        return env

    # ------------------------------------------------------------------
    # Override: SQL-specific ReAct loop with DB system prompt
    # ------------------------------------------------------------------

    async def acomplete(self, query: str = "", context: str = "", **kwargs: Any) -> str:
        if query and not context:
            context = query
            query = ""

        if self._current_depth >= self.max_depth:
            raise MaxDepthError(f"Max recursion depth ({self.max_depth}) exceeded")

        repl_env = self._build_repl_env(query, context)

        # Parent RLM.complete() swaps query→context when context is empty,
        # so the actual question may arrive in either variable.
        question = query or context

        # Pre-fetch schema so the model doesn't waste turns discovering metadata
        schema_str = self._db.format_schema() if hasattr(self, '_db') else "(no schema)"

        messages: list[Message] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"QUESTION: {question}\n\n"
                    f"Schema:\n{schema_str}\n\n"
                    "Step 1: Think about what tables/columns/joins/conditions are needed.\n"
                    "Step 2: Test your SQL with db.execute().\n"
                    f"Step 3: FINAL(\"your sql\")  ← plain text, not inside any function."
                ),
            },
        ]

        # Inject stop sequences unless caller already set them
        kwargs.setdefault("stop", _STOP_SEQUENCES)

        last_exec_result = None
        repeat_count = 0

        for iteration in range(self.max_iterations):
            self._iterations = iteration + 1
            response = await self._call_llm(messages, **kwargs)
            response = _truncate_at_fake_turn(response)
            response = _convert_sql_blocks(response)

            print(f"\n{'='*80}")
            print(f"DB-RLM ITERATION {iteration}")
            print(response)
            print('='*80)

            if is_final(response):
                answer = parse_response(response, repl_env)
                if answer is not None:
                    return answer

            try:
                exec_result = self.repl.execute(response, repl_env)
            except REPLError as e:
                exec_result = f"REPL Error: {e}"
            except Exception as e:
                exec_result = f"Unexpected error: {e}"

            print("REPL OUTPUT:", exec_result)
            print('-'*80)

            # Detect looping: same output twice in a row → force FINAL
            if exec_result == last_exec_result:
                repeat_count += 1
                if repeat_count >= 2:
                    exec_result = (
                        f"{exec_result}\n\n"
                        "You already have this result. "
                        "Stop exploring. Write your best SQL and call FINAL(\"your sql\")."
                    )
                    repeat_count = 0
            else:
                repeat_count = 0
            last_exec_result = exec_result

            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": exec_result})

        raise MaxIterationsError(
            f"Max iterations ({self.max_iterations}) exceeded without FINAL()"
        )


# ------------------------------------------------------------------
# Evaluation harness
# ------------------------------------------------------------------

def run_one(
    example: dict[str, Any],
    database_dir: str | Path,
    model: str,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    max_iterations: int = 15,
    **llm_kwargs: Any,
) -> dict[str, Any]:
    """Run DB-RLM on one Spider example and return an evaluation record.

    Output schema is compatible with the baseline run_one() functions so
    all three baselines + ours can be compared with the same evaluator.
    """
    from shared.evaluator import is_correct
    from shared.sql_executor import execute_sql

    db_id = example["db_id"]
    db_path = get_db_path(database_dir, db_id)
    started_at = time.perf_counter()

    predicted_sql = ""
    termination_reason = "error"
    generation_error: str | None = None

    agent = DBRLM(
        model=model,
        api_base=api_base,
        api_key=api_key,
        max_iterations=max_iterations,
        **llm_kwargs,
    )

    try:
        predicted_sql = agent.complete_sql(example["question"], db_path)
        termination_reason = "final"
    except MaxIterationsError:
        termination_reason = "max_iterations"
        generation_error = "Max iterations exceeded"
    except Exception as e:
        generation_error = str(e)

    predicted_exec = (
        execute_sql(db_path, predicted_sql, read_only=True)
        if predicted_sql and generation_error is None
        else {"answer": None, "error": generation_error or "No SQL generated"}
    )
    gold_exec = execute_sql(db_path, example["gold_sql"], read_only=True)
    latency = round(time.perf_counter() - started_at, 4)
    error = predicted_exec.get("error") or gold_exec.get("error")

    return {
        "id": example["id"],
        "method": "ours_recursive_db_rlm",
        "db_id": db_id,
        "question": example["question"],
        "predicted_sql": predicted_sql,
        "predicted_answer": predicted_exec.get("answer"),
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec.get("answer"),
        "correct": (
            predicted_exec.get("error") is None
            and gold_exec.get("error") is None
            and is_correct(predicted_exec.get("answer"), gold_exec.get("answer"))
        ),
        "error": error,
        "latency_seconds": latency,
        "llm_calls": agent.stats["llm_calls"],
        "iterations": agent.stats["iterations"],
        "termination_reason": termination_reason,
    }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _strip_markdown(text: str) -> str:
    """Remove ```python / ```sql / ``` fences from LLM output."""
    return re.sub(r'```(?:python|sql)?\n?', '', text).replace('```', '').strip()


def _truncate_at_fake_turn(text: str) -> str:
    """Cut off anything after the model starts hallucinating a new turn."""
    for marker in _STOP_SEQUENCES:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text.strip()


def _convert_sql_blocks(text: str) -> str:
    """Convert ```sql blocks into db.execute() Python calls.

    The REPL only understands Python. When the model writes a raw SQL block,
    wrap it so it actually runs and the model sees the result.
    """
    def to_python(m: re.Match) -> str:
        sql = m.group(1).strip()
        escaped = sql.replace('\\', '\\\\').replace('"', '\\"')
        return f'```python\nprint(db.execute("{escaped}"))\n```'

    return re.sub(r'```sql\s*\n(.*?)\n```', to_python, text, flags=re.DOTALL)
