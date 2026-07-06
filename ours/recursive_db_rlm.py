"""DB-RLM: recursive RLM adapter for Text-to-SQL on SQLite databases."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.rlm.core import MaxDepthError, MaxIterationsError, RLM
from src.rlm.parser import is_final, parse_response
from src.rlm.repl import REPLError
from src.rlm.types import Message

from ours.db_environment import DBEnvironment, get_db_path
from ours.metadata import DatabaseMetadata, extract_database_metadata
from ours.subquestion_agent import SubquestionAgent
from ours.workspace import EvidenceWorkspace
from shared import config
from shared.io_utils import read_text


@dataclass
class DBRLMConfig:
    """Ablation switches for DB-RLM experiments."""

    use_metadata: bool = False
    use_recursion: bool = True
    use_workspace: bool = False
    prompt_version: str = "recursive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_metadata": self.use_metadata,
            "use_recursion": self.use_recursion,
            "use_workspace": self.use_workspace,
            "prompt_version": self.prompt_version,
        }


BASIC_PROMPT = """\
You are a Text-to-SQL database agent.

You have a Python REPL with these tools:
- db.get_tables()
- db.get_schema(table)
- db.sample_rows(table, limit=3)
- db.execute(sql)

Inspect only the tables and columns needed for the original question. Test the
candidate SQL with db.execute(), then finish with FINAL("SELECT ...").
"""

RECURSIVE_PROMPT = """\
You are Recursive DB-RLM, a recursive Text-to-SQL database reasoning agent.

You have a Python REPL with database tools and, when enabled, recursive helper
tools. Inspect only what is needed. For complex questions, create focused
sub-questions, call answer_subquestion(), aggregate the returned evidence, test
the final candidate SQL, and finish with FINAL("SELECT ...").
"""

WORKSPACE_PROMPT = """\
You are Recursive DB-RLM with an evidence workspace.

Use database tools to inspect relevant schema/data. Use answer_subquestion()
when recursion is enabled. Store important evidence with workspace.add(note,
data), review it with workspace.read(), and synthesize one final executable
SQLite query with FINAL("SELECT ...").
"""

PROMPT_BY_VERSION = {
    "basic": BASIC_PROMPT,
    "recursive": RECURSIVE_PROMPT,
    "workspace": WORKSPACE_PROMPT,
}

_STOP_SEQUENCES = ["\nUser:", "\n### User", "\nObservation:", "\nSystem:"]


def load_system_prompt(prompt_version: str = "recursive") -> str:
    if prompt_version in {"basic", "workspace"}:
        return PROMPT_BY_VERSION[prompt_version]

    prompt_path = config.PROMPTS_DIR / "ours_recursive_db_rlm.txt"
    try:
        prompt = read_text(prompt_path).strip()
    except FileNotFoundError:
        return RECURSIVE_PROMPT
    return prompt or RECURSIVE_PROMPT


class DBRLM(RLM):
    """RLM subclass wired to a SQLite database and recursive DB sub-agents."""

    def __init__(
        self,
        *args: Any,
        use_metadata: bool = False,
        use_recursion: bool = True,
        use_workspace: bool = False,
        prompt_version: str = "recursive",
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.experiment_config = DBRLMConfig(
            use_metadata=use_metadata,
            use_recursion=use_recursion,
            use_workspace=use_workspace,
            prompt_version=prompt_version,
        )

    def complete_sql(self, question: str, db_path: str | Path) -> str:
        """Synchronous entry point: question + db_path -> SQL string."""
        self._db = DBEnvironment(db_path)
        self._db_path = Path(db_path)
        self._metadata: DatabaseMetadata | None = None
        self._workspace: EvidenceWorkspace | None = None
        if self.experiment_config.use_metadata:
            self._metadata = extract_database_metadata(db_path)
        if self.experiment_config.use_workspace:
            self._workspace = EvidenceWorkspace()
        return self.complete(query=question)

    def _build_repl_env(self, query: str, context: str) -> dict[str, Any]:
        env = super()._build_repl_env(query, context)
        if hasattr(self, "_db"):
            env["db"] = self._db
        if self.experiment_config.use_recursion and hasattr(self, "_db_path"):
            env["answer_subquestion"] = self._answer_subquestion
        if self.experiment_config.use_metadata and self._metadata is not None:
            env["metadata"] = self._metadata.to_dict()
        if self.experiment_config.use_workspace and self._workspace is not None:
            env["workspace"] = self._workspace
        return env

    def _answer_subquestion(self, question: str) -> dict[str, Any]:
        child = SubquestionAgent(
            model=self.model,
            recursive_model=self.recursive_model,
            api_base=self.api_base,
            api_key=self.api_key,
            max_depth=self.max_depth,
            max_iterations=max(3, min(self.max_iterations, 6)),
            current_depth=self._current_depth,
            use_metadata=self.experiment_config.use_metadata,
            use_workspace=self.experiment_config.use_workspace,
            prompt_version=self.experiment_config.prompt_version,
            llm_kwargs=self.llm_kwargs,
        )
        result = child.answer(question, self._db_path)
        self._llm_calls += int(result.get("llm_calls") or 0)
        return result

    async def acomplete(self, query: str = "", context: str = "", **kwargs: Any) -> str:
        if query and not context:
            context = query
            query = ""

        if self._current_depth >= self.max_depth:
            raise MaxDepthError(f"Max recursion depth ({self.max_depth}) exceeded")

        repl_env = self._build_repl_env(query, context)
        question = query or context
        run_context = self._build_user_context(question)

        messages: list[Message] = [
            {
                "role": "system",
                "content": self._build_system_prompt(),
            },
            {
                "role": "user",
                "content": run_context,
            },
        ]

        kwargs.setdefault("stop", _STOP_SEQUENCES)
        last_exec_result = None
        repeat_count = 0

        for iteration in range(self.max_iterations):
            self._iterations = iteration + 1
            response = await self._call_llm(messages, **kwargs)
            response = _truncate_at_fake_turn(response)
            response = _convert_sql_blocks(response)

            print(f"\n{'=' * 80}")
            print(f"DB-RLM DEPTH {self._current_depth} ITERATION {iteration}")
            print(response)
            print("=" * 80)

            if is_final(response):
                answer = parse_response(response, repl_env)
                if answer is not None:
                    return answer

            try:
                exec_result = self.repl.execute(response, repl_env)
            except REPLError as error:
                exec_result = f"REPL Error: {error}"
            except Exception as error:
                exec_result = f"Unexpected error: {error}"

            print("REPL OUTPUT:", exec_result)
            print("-" * 80)

            if exec_result == last_exec_result:
                repeat_count += 1
                if repeat_count >= 2:
                    exec_result = (
                        f"{exec_result}\n\n"
                        'You already have this result. Return FINAL("your sql").'
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

    def _build_system_prompt(self) -> str:
        prompt_version = self.experiment_config.prompt_version
        if not self.experiment_config.use_recursion and prompt_version == "recursive":
            prompt_version = "basic"
        prompt = load_system_prompt(prompt_version)
        available_tools = [
            "- db.get_tables()",
            "- db.get_schema(table)",
            "- db.sample_rows(table, limit=3)",
            "- db.execute(sql)",
        ]
        if self.experiment_config.use_recursion:
            available_tools.append("- answer_subquestion(question)")
        if self.experiment_config.use_metadata:
            available_tools.append("- metadata (pre-extracted database metadata dict)")
        if self.experiment_config.use_workspace:
            available_tools.extend(["- workspace.add(note, data)", "- workspace.read()"])

        rules = [
            "Use at most one Python code block per assistant turn.",
            "Do not write fake observations or fake user messages.",
            "Only read-only SQLite queries are allowed.",
            'Finish with FINAL("SELECT ...") for the original question.',
        ]
        return (
            f"{prompt.strip()}\n\n"
            "Available tools in this run:\n"
            + "\n".join(available_tools)
            + "\n\nRules:\n"
            + "\n".join(f"- {rule}" for rule in rules)
        )

    def _build_user_context(self, question: str) -> str:
        db_summary = self._db.describe() if hasattr(self, "_db") else "(no database)"
        parts = [f"QUESTION: {question}", db_summary]

        if self.experiment_config.use_metadata and self._metadata is not None:
            parts.append(self._metadata.to_prompt())
        else:
            parts.append("No pre-extracted metadata is provided in this run.")

        enabled = self.experiment_config.to_dict()
        parts.append(f"ABLATION CONFIG: {enabled}")
        return "\n\n".join(parts)


def run_one(
    example: dict[str, Any],
    database_dir: str | Path,
    model: str,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    max_iterations: int = 15,
    use_metadata: bool = False,
    use_recursion: bool = True,
    use_workspace: bool = False,
    prompt_version: str = "recursive",
    **llm_kwargs: Any,
) -> dict[str, Any]:
    """Run DB-RLM on one Spider example and return an evaluation record."""
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
        use_metadata=use_metadata,
        use_recursion=use_recursion,
        use_workspace=use_workspace,
        prompt_version=prompt_version,
        **llm_kwargs,
    )

    try:
        predicted_sql = agent.complete_sql(example["question"], db_path)
        termination_reason = "final"
    except MaxIterationsError:
        termination_reason = "max_iterations"
        generation_error = "Max iterations exceeded"
    except Exception as error:
        generation_error = str(error)

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
            and is_correct(
                predicted_exec.get("answer"),
                gold_exec.get("answer"),
                gold_sql=example["gold_sql"],
            )
        ),
        "error": error,
        "latency_seconds": latency,
        "llm_calls": agent.stats["llm_calls"],
        "iterations": agent.stats["iterations"],
        "termination_reason": termination_reason,
        "ablation_config": agent.experiment_config.to_dict(),
    }


def _truncate_at_fake_turn(text: str) -> str:
    for marker in _STOP_SEQUENCES:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text.strip()


def _convert_sql_blocks(text: str) -> str:
    """Convert ```sql blocks into db.execute() Python calls."""

    def to_python(match: re.Match[str]) -> str:
        sql = match.group(1).strip()
        escaped = sql.replace("\\", "\\\\").replace('"', '\\"')
        return f'```python\nprint(db.execute("{escaped}"))\n```'

    return re.sub(r"```sql\s*\n(.*?)\n```", to_python, text, flags=re.DOTALL)
