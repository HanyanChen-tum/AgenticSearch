"""A sub-agent that can query the database, for delegated sub-questions.

Recursion v1 handed sub-questions to a plain RLM: no database, no schema, no
history. Measured on dev 500, the model delegated exactly the decisions it could
not make itself -- "should this count distinct patients or laboratory rows?",
"SUM(cost) or AVG(cost)?", "which join path matches this phrase?" -- to an agent
that knew strictly less than it did. Accuracy moved 0.00pp.

The one delegation that worked was the one where the parent pasted real column
values into the sub-context. So the leaf here gets the parent's gated database
handle and answers in plain text. It is deliberately not a DBRLM: the leaf
answers a question, it does not produce the final SQL.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from src.rlm.parser import is_final, parse_response
from src.rlm.repl import REPLError, REPLExecutor


LEAF_PROMPT_VERSION = "leaf-db-v1"

_LEAF_SYSTEM_PROMPT = """\
You answer one narrow question for another agent that is writing SQL. You are not
writing the final query.

AVAILABLE TOOLS (inside ```python blocks):
  db.execute("SQL")
  db.sample_values("table", "column")

You are running inside a live Python REPL with a real connection to this database.
Queries you write will execute and return real rows. Say your first turn like this,
as a code block and nothing else:

```python
print(db.execute("SELECT DISTINCT Segment FROM customers LIMIT 5"))
```

You will then be shown the actual result. Only after that, answer.

The calling agent could not settle this question from the text it had. Guessing
again adds nothing — look it up. If the question is about which values a column
actually holds, which join path connects two tables, or how many rows a filter
matches, run a query and answer from the result.

Answer in one or two sentences, citing the values or counts you observed.
Finish with plain text FINAL("your answer") and no code block in that message.
"""


class LeafAgent:
    """One delegated sub-question, answered against the live database."""

    def __init__(
        self,
        call_llm: Callable[..., Any],
        db: Any,
        max_iterations: int = 4,
        repl_timeout: int = 10,
    ) -> None:
        self._call_llm = call_llm
        self._db = db
        self.max_iterations = max_iterations
        self._repl = REPLExecutor(timeout=repl_timeout)

    async def answer(
        self, sub_query: str, sub_context: str, schema: str = ""
    ) -> dict[str, Any]:
        env: dict[str, Any] = {"db": self._db, "context": sub_context}
        user = f"QUESTION: {sub_query}"
        # Without the schema the leaf knows it has db.execute but not what to
        # execute it against; measured on 199 questions, all 30 leaves answered
        # "I can't determine this" without ever writing a query.
        if (schema or "").strip():
            user += f"\n\nSCHEMA OF THE DATABASE YOU CAN QUERY:\n{schema}"
        if (sub_context or "").strip():
            user += f"\n\nMATERIAL SUPPLIED BY THE CALLER:\n{sub_context}"
        messages = [
            {"role": "system", "content": _LEAF_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

        turns = 0
        queried = False
        refusals = 0
        for _ in range(self.max_iterations):
            response = await self._call_llm(messages)
            turns += 1
            messages.append({"role": "assistant", "content": response})
            if is_final(response):
                # v2 measured every leaf finishing on turn 1 without touching the
                # database, so its answers were the same guesses the caller could
                # already make. Asking it to look things up did not work; refusing
                # an unsupported answer does, and costs nothing when it did query.
                if not queried and refusals < 2:
                    refusals += 1
                    messages.append({"role": "user", "content": (
                        "REJECTED: you answered without querying the database. "
                        "Run db.execute(...) or db.sample_values(...) first and "
                        "answer from what it returns."
                    )})
                    continue
                return {
                    "answer": parse_response(response, env) or "",
                    "turns": turns,
                    "queried": queried,
                    "terminated": "final" if queried else "final_without_query",
                    # Without the leaf's own turns there is no way to see why it
                    # declines to query; four iterations were spent guessing at it.
                    "transcript": [m for m in messages if m["role"] != "system"],
                }
            try:
                observation = self._repl.execute(response, env)
                queried = True
            except REPLError as exc:
                observation = f"REPL error: {exc}"
            messages.append({"role": "user", "content": f"RESULT:\n{observation}"})

        # Out of turns: say so rather than returning a confident-looking guess.
        return {
            "answer": "(no answer: the sub-agent ran out of turns)",
            "turns": turns,
            "queried": queried,
            "terminated": "max_iterations",
            "transcript": [m for m in messages if m["role"] != "system"],
        }


def run_leaf(
    call_llm: Callable[..., Any],
    db: Any,
    sub_query: str,
    sub_context: str,
    schema: str = "",
    max_iterations: int = 4,
) -> dict[str, Any]:
    """Synchronous entry point, for use from inside the parent's REPL."""
    agent = LeafAgent(call_llm, db, max_iterations=max_iterations)
    coro = agent.answer(sub_query, sub_context, schema)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # The parent loop is already running; the REPL call itself is synchronous.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result()
