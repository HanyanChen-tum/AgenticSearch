"""Recursive sub-question agent for DB-RLM."""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.sql_executor import execute_sql


@dataclass
class SubquestionAgent:
    """Run an independent child DB-RLM call for a focused database question."""

    model: str
    recursive_model: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    max_depth: int = 5
    max_iterations: int = 6
    current_depth: int = 0
    use_metadata: bool = False
    use_workspace: bool = False
    prompt_version: str = "recursive"
    llm_kwargs: dict[str, Any] | None = None

    def answer(self, question: str, db_path: str | Path) -> dict[str, Any]:
        """Return child-agent evidence for a sub-question.

        The child agent produces SQL with its own DB exploration loop. We then
        execute that SQL in read-only mode so the parent receives compact,
        structured evidence instead of another long conversation.
        """
        if self.current_depth + 1 >= self.max_depth:
            return {
                "subquestion": question,
                "sql": "",
                "answer": None,
                "error": f"Max recursion depth ({self.max_depth}) reached",
                "llm_calls": 0,
                "iterations": 0,
            }

        return self._run_child(question, Path(db_path))

    def _run_child(self, question: str, db_path: Path) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return self._run_child_sync(question, db_path)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._run_child_sync, question, db_path)
            return future.result()

    def _run_child_sync(self, question: str, db_path: Path) -> dict[str, Any]:
        from ours.recursive_db_rlm import DBRLM

        agent = DBRLM(
            model=self.recursive_model or self.model,
            recursive_model=self.recursive_model or self.model,
            api_base=self.api_base,
            api_key=self.api_key,
            max_depth=self.max_depth,
            max_iterations=self.max_iterations,
            _current_depth=self.current_depth + 1,
            use_metadata=self.use_metadata,
            use_recursion=True,
            use_workspace=self.use_workspace,
            prompt_version=self.prompt_version,
            **(self.llm_kwargs or {}),
        )

        try:
            sql = agent.complete_sql(question, db_path)
            execution = execute_sql(db_path, sql, read_only=True)
            return {
                "subquestion": question,
                "sql": sql,
                "answer": execution.get("answer"),
                "error": execution.get("error"),
                "llm_calls": agent.stats["llm_calls"],
                "iterations": agent.stats["iterations"],
            }
        except Exception as error:
            return {
                "subquestion": question,
                "sql": "",
                "answer": None,
                "error": str(error),
                "llm_calls": agent.stats["llm_calls"],
                "iterations": agent.stats["iterations"],
            }
