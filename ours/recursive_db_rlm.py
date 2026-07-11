"""DB-RLM: RLM adapter for Text-to-SQL on Spider/BIRD databases."""

from __future__ import annotations

import re
import time
import asyncio
from pathlib import Path
from typing import Any, Optional

import litellm
litellm.drop_params = True  # drop unsupported params (e.g. stop sequences on Azure)

from src.rlm.core import RLM, MaxIterationsError, MaxDepthError
from src.rlm.parser import parse_response, is_final
from src.rlm.repl import REPLError
from src.rlm.types import Message

from ours.db_environment import DBEnvironment, get_db_path


# Basic prompt — good for simple/moderate questions (no few-shot, less noise)
_SYSTEM_PROMPT_BASIC = """\
You are a Text-to-SQL expert with access to a live database. Use it to verify your SQL before finalizing.

AVAILABLE TOOLS (call these inside ```python blocks):
  db.execute("SQL")                        — run any SELECT and see results
  db.sample_values("table", "column")     — see actual values stored in a column

WORKFLOW:

Turn 1 — READ HINT + EXPLORE (one code block):
  ① Read the Hint carefully — treat every definition as ground truth.
  ② If string values are NOT defined by the Hint, use db.sample_values() to check actual storage.

Turn 2 — TEST your SQL (one code block):
  ```python
  print(db.execute("YOUR SQL HERE"))
  ```

Turn 3 — FINALIZE (plain text only, never inside a code block):
  FINAL("YOUR SQL HERE")

RULES:
  • NEVER write FINAL() in the same message as a code block.
  • ONE code block per turn.
  • Schema is already provided — no need for get_tables() or get_schema().
  • SELECT only the columns the question asks for, in the order mentioned.
  • When a question asks for a LIST of things, add DISTINCT.
  • For conditional aggregation use: SUM(CASE WHEN condition THEN 1 ELSE 0 END)
  • For ratios/percentages: CAST(numerator AS REAL) / denominator * 100
  • SQLite supports IIF(condition, true_val, false_val) as shorthand for CASE WHEN.
"""

# Full prompt — better for challenging questions (few-shot + strict rules)
_SYSTEM_PROMPT = """\
You are a Text-to-SQL expert with access to a live database. Use it to verify your SQL before finalizing.

AVAILABLE TOOLS (call these inside ```python blocks):
  db.execute("SQL")                        — run any SELECT and see results
  db.sample_values("table", "column")     — see actual values stored in a column

WORKFLOW:

Turn 1 — READ HINT + EXPLORE (one code block):
  ① Read the Hint carefully — it defines exact column values, date formats, and
    computation formulas. Treat every definition in the Hint as ground truth.
    Examples of what Hints tell you:
      "September 2013 refers to 201309"  → WHERE date_col = '201309'  (not LIKE '2013-09%')
      "ratio = count(A) / count(B)"      → SELECT COUNT(CASE WHEN x='A' THEN 1 END)*1.0 / COUNT(CASE WHEN x='B' THEN 1 END)
      "meeting events refers to type = 'Meeting'" → WHERE type = 'Meeting'
  ② If any names, locations, or string values are NOT defined by the Hint,
    use db.sample_values() to see how they are actually stored in the database.

Turn 2 — TEST your SQL (one code block):
  ```python
  print(db.execute("YOUR SQL HERE"))
  ```

Turn 3 — FINALIZE (plain text only, never inside a code block):
  FINAL("YOUR SQL HERE")

RULES:
  • NEVER write FINAL() in the same message as a code block.
  • ONE code block per turn.
  • Schema is already provided — no need for get_tables() or get_schema().
  • ⛔ NEVER call FINAL() if your last SQL returned 0 rows — that means your query
    is wrong. Fix the WHERE clause, JOIN condition, or value format and retry.
  • SELECT only the columns the question asks for, in the order mentioned.
    Never add extra columns (no aliases, no COUNT(*) unless asked).
  • If the question asks multiple things ("What is X? Who is Y?" / "state A and B"),
    SELECT every asked item, in the order asked — do not answer only one part.
    "How old is the youngest driver? What is his name?" → SELECT age_expr, forename, surname
  • For superlatives (oldest/highest/best/dumbest) return exactly one row:
    ORDER BY col ASC|DESC LIMIT 1 — never WHERE col = (SELECT MIN/MAX(...)) which returns ties.
  • ONLY when the expected answer is literally yes or no ("Did X...?", "Is Y...?", "Was each...?"),
    SELECT the answer itself as EXACTLY ONE column: IIF(condition, 'YES', 'NO') —
    do not return the matching rows, do not add extra columns.
    Comparison questions ("Are there more X or Y? What is the difference?") are NOT yes/no —
    return the value(s) asked.
  • When using T1/T2 aliases, double-check which table each SELECTed column belongs to
    (races.name vs circuits.name) — alias mix-ups are a top error source.
  • NEVER concatenate columns ("full name" → SELECT forename, surname — two columns,
    not forename || ' ' || surname). Return raw columns.
  • When the Hint spells out a formula (DIVIDE(...), SUBTRACT(...), MULTIPLY(...), "X = A / B"),
    translate it into SQL LITERALLY, term by term — do not substitute your own formula,
    denominator, or filter, even if yours seems more correct.
  • When a question asks for a LIST of things, add DISTINCT.
  • When computing AVG/SUM/COUNT over a joined table, be careful about duplicates.
    Use subqueries or DISTINCT to avoid counting the same row multiple times.
  • For conditional aggregation use: SUM(CASE WHEN condition THEN 1 ELSE 0 END)
    or IIF(condition, value, 0) — both work in SQLite.
  • For ratios/percentages: CAST(numerator AS REAL) / denominator * 100
    The denominator must be the TOTAL count of ALL rows in the relevant group,
    NOT just the rows matching the condition.
    ✓ COUNT(CASE WHEN cond THEN 1 END) * 1.0 / COUNT(*)
    ✗ COUNT(CASE WHEN cond THEN 1 END) / COUNT(CASE WHEN other_cond THEN 1 END)
  • For "rank X by Y" questions use a window function AND include the ranked-by
    metric column itself: SELECT name, metric, RANK() OVER (ORDER BY metric DESC) FROM ...
    (name + metric + rank — not just name + rank).
  • SQLite supports IIF(condition, true_val, false_val) as shorthand for CASE WHEN.

EXAMPLES (study these patterns):

Example 1 — Ratio/percentage with Hint:
  QUESTION: What percentage of male patients are in-patients?
  HINT: male refers to SEX = 'M'; in-patient refers to Admission = '+'
  WRONG SQL: SELECT COUNT(*) * 1.0 / (SELECT COUNT(*) FROM Patient WHERE Admission='-') FROM Patient WHERE SEX='M' AND Admission='+'
  RIGHT SQL:  SELECT CAST(SUM(CASE WHEN Admission='+' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(*) FROM Patient WHERE SEX='M'
  WHY: denominator = total males (all rows where SEX='M'), not outpatients.

Example 2 — Evidence defines exact column format:
  QUESTION: How many transactions happened in September 2013?
  HINT: September 2013 refers to Date = '201309'
  WRONG SQL: WHERE Date LIKE '2013-09%'
  RIGHT SQL:  WHERE Date = '201309'
  WHY: Hint tells you the exact stored format — trust it, don't guess.

Example 3 — Rank question needs window function:
  QUESTION: Rank schools by average writing score where score > 400.
  WRONG SQL: SELECT School, AvgScrWrite FROM schools WHERE AvgScrWrite > 400 ORDER BY AvgScrWrite DESC
  RIGHT SQL:  SELECT School, AvgScrWrite, RANK() OVER (ORDER BY AvgScrWrite DESC) AS rnk FROM schools WHERE AvgScrWrite > 400
  WHY: "rank" means assign rank numbers with RANK() OVER, not just sort rows.
"""

# Stop sequences that prevent the model from hallucinating fake turns
_STOP_SEQUENCES = ["\nUser:", "\n### User", "\nObservation:", "\nSystem:"]


class DBRLM(RLM):
    """RLM subclass wired to a SQLite database for Text-to-SQL generation.

    Usage:
        agent = DBRLM(model="ollama/qwen2.5:7b", api_base="http://localhost:11434")
        sql = agent.complete_sql("How many singers do we have?", db_path)
    """

    def complete_sql(self, question: str, db_path: str | Path, evidence: str = "") -> str:
        """Synchronous entry point: question + db_path → SQL string.
        evidence: BIRD-style hint string (definitions of column values, formulas, etc.)
        """
        self._db = DBEnvironment(db_path)
        self._evidence = evidence.strip()
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

        evidence = getattr(self, "_evidence", "")
        evidence_block = (
            f"\n⚠️  HINT (follow these definitions EXACTLY — they define exact values/formats/formulas):\n"
            f"  {evidence}\n"
            if evidence else ""
        )

        from ours.db_hints import get_db_hint
        db_id = getattr(self._db, "db_path", Path("")).stem if hasattr(self, "_db") else ""
        db_hint = get_db_hint(db_id)
        db_hint_block = (
            f"\n📌 DATABASE NOTES (structural facts about this specific database):\n"
            + "\n".join(f"  {line}" for line in db_hint.splitlines())
            + "\n"
            if db_hint else ""
        )

        messages: list[Message] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"QUESTION: {question}"
                    f"{evidence_block}"
                    f"{db_hint_block}\n"
                    f"Schema:\n{schema_str}\n\n"
                    "Follow the Hint above, explore the DB if needed, test your SQL, then FINAL(\"your sql\")."
                ),
            },
        ]

        # Inject stop sequences unless caller already set them
        kwargs.setdefault("stop", _STOP_SEQUENCES)

        last_exec_result = None
        repeat_count = 0
        last_was_empty = False  # track if previous SQL returned 0 rows

        for iteration in range(self.max_iterations):
            self._iterations = iteration + 1
            response = await self._call_llm(messages, **kwargs)
            response = _truncate_at_fake_turn(response)
            response = _convert_sql_blocks(response)

            print(f"\n{'='*80}")
            print(f"DB-RLM ITERATION {iteration}")
            print(response)
            print('='*80)

            has_code = bool(re.search(r'```python', response))

            # Only accept FINAL if there's no untested code block in the same turn.
            # Also block FINAL if the last SQL returned 0 rows — the answer is wrong.
            if is_final(response) and not has_code:
                if last_was_empty:
                    # Inject a hard block: force model to fix the query
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": (
                        "⛔ BLOCKED: Your last SQL returned 0 rows. A correct answer cannot be empty. "
                        "You MUST fix your query before calling FINAL(). "
                        "Check the Hint, verify column values with db.sample_values(), and try again."
                    )})
                    last_was_empty = False
                    continue
                answer = parse_response(response, repl_env)
                if answer is not None:
                    return answer

            # Strip inline FINAL so REPL doesn't choke on it, then execute the code
            response_for_repl = re.sub(r'FINAL\s*\(.*?\)', '', response, flags=re.DOTALL).strip()
            try:
                exec_result = self.repl.execute(response_for_repl, repl_env)
            except REPLError as e:
                exec_result = f"REPL Error: {e}"
            except Exception as e:
                exec_result = f"Unexpected error: {e}"

            # Enrich feedback so the model knows when something is wrong
            result_data = None
            try:
                import ast
                result_data = ast.literal_eval(exec_result) if isinstance(exec_result, str) else None
            except Exception:
                pass

            last_was_empty = False
            if isinstance(result_data, dict):
                if result_data.get("error"):
                    exec_result += f"\n\n⚠️ SQL ERROR: {result_data['error']} — fix your SQL and try again."
                elif result_data.get("rows") == []:
                    exec_result += "\n\n⚠️ WARNING: Query returned 0 rows. This is likely wrong. Check your JOIN conditions, WHERE clause, or column names and try a different approach."
                    last_was_empty = True

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
