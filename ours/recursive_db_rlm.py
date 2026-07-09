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
from ours.probe_queries import ProbeQuerySummary, run_probe_queries
from ours.query_enrichment import QueryEnrichment, enrich_question
from ours.schema_memory import SchemaMemory
from ours.subquestion_agent import SubquestionAgent
from ours.workspace import EvidenceWorkspace
from shared import config
from shared.io_utils import read_text
from shared.sql_executor import normalize_sql_text


@dataclass
class DBRLMConfig:
    """Ablation switches for DB-RLM experiments."""

    use_metadata: bool = False
    use_enrichment: bool = False
    use_probe_queries: bool = False
    use_schema_memory: bool = False
    initial_top_k: int = 10
    use_recursion: bool = True
    use_workspace: bool = False
    prompt_version: str = "recursive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_metadata": self.use_metadata,
            "use_enrichment": self.use_enrichment,
            "use_probe_queries": self.use_probe_queries,
            "use_schema_memory": self.use_schema_memory,
            "initial_top_k": self.initial_top_k,
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
candidate SQL with db.execute(), use any precomputed metadata/enrichment/probe
context when provided, then finish with FINAL("your executable SQL").
Never return placeholders such as SELECT ..., <SQL>, or TODO.
"""

RECURSIVE_PROMPT = """\
You are Recursive DB-RLM, a recursive Text-to-SQL database reasoning agent.

You have a Python REPL with database tools and, when enabled, recursive helper
tools. Inspect only what is needed. For complex questions, create focused
sub-questions, call answer_subquestion(), aggregate the returned evidence, test
the final candidate SQL, and finish with FINAL("your executable SQL").
Never return placeholders such as SELECT ..., <SQL>, or TODO.
"""

WORKSPACE_PROMPT = """\
You are Recursive DB-RLM with a restricted model workspace.

Use database tools to inspect relevant schema/data. Use answer_subquestion()
when recursion is enabled. Use workspace tools to read schema snapshots, save
intermediate evidence, run small restricted Python scripts, inspect execution
results, and revise failed SQL queries. Combine any enrichment/probe results
provided up front, then synthesize one final executable SQLite query with
FINAL("SELECT ...").
Never return placeholders such as SELECT ..., <SQL>, or TODO.
"""

SCHEMA_PROMPT = """\
You are a Text-to-SQL agent operating with bounded schema memory.

Start from SCHEMA MEMORY in the user context. When required schema is missing,
use schema_memory.search() to retrieve a small number of additional columns.
Inspect retrieved tables with db.get_schema() or db.sample_rows() only when
needed. If answer_subquestion() is available, use it only for a focused missing
schema or evidence question. Test the final SQL and finish with
FINAL("your executable SQL").
Never return placeholders such as SELECT ..., <SQL>, or TODO.
"""

PROMPT_BY_VERSION = {
    "basic": BASIC_PROMPT,
    "recursive": RECURSIVE_PROMPT,
    "workspace": WORKSPACE_PROMPT,
    "schema": SCHEMA_PROMPT,
}

_STOP_SEQUENCES = ["\nUser:", "\n### User", "\nObservation:", "\nSystem:"]


def load_system_prompt(prompt_version: str = "recursive") -> str:
    if prompt_version in {"basic", "workspace", "schema"}:
        return PROMPT_BY_VERSION[prompt_version]

    prompt_path = config.PROMPTS_DIR / "ours_recursive_db_rlm.txt"
    try:
        prompt = read_text(prompt_path).strip()
    except FileNotFoundError:
        return RECURSIVE_PROMPT
    return prompt or RECURSIVE_PROMPT


def model_supports_stop(model_name: str) -> bool:
    return not model_name.startswith("azure/")


class DBRLM(RLM):
    """RLM subclass wired to a SQLite database and recursive DB sub-agents."""

    def __init__(
        self,
        *args: Any,
        use_metadata: bool = False,
        use_enrichment: bool = False,
        use_probe_queries: bool = False,
        use_schema_memory: bool = False,
        initial_top_k: int = 10,
        use_recursion: bool = True,
        use_workspace: bool = False,
        prompt_version: str = "recursive",
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.experiment_config = DBRLMConfig(
            use_metadata=use_metadata,
            use_enrichment=use_enrichment,
            use_probe_queries=use_probe_queries,
            use_schema_memory=use_schema_memory,
            initial_top_k=max(1, int(initial_top_k)),
            use_recursion=use_recursion,
            use_workspace=use_workspace,
            prompt_version=prompt_version,
        )
        self._recursion_trace: list[dict[str, Any]] = []

    def complete_sql(self, question: str, db_path: str | Path) -> str:
        """Synchronous entry point: question + db_path -> SQL string."""
        self._db = DBEnvironment(db_path)
        self._db_path = Path(db_path)
        self._metadata: DatabaseMetadata | None = None
        self._enrichment: QueryEnrichment | None = None
        self._probe_summary: ProbeQuerySummary | None = None
        self._schema_memory: SchemaMemory | None = None
        self._workspace: EvidenceWorkspace | None = None
        self._recursion_trace = []
        needs_metadata = (
            self.experiment_config.use_metadata
            or self.experiment_config.use_enrichment
            or self.experiment_config.use_probe_queries
            or self.experiment_config.use_schema_memory
        )
        if needs_metadata:
            self._metadata = extract_database_metadata(db_path)
        if self.experiment_config.use_schema_memory and self._metadata is not None:
            self._schema_memory = SchemaMemory(self._metadata)
            self._schema_memory.search(
                question,
                top_k=self.experiment_config.initial_top_k,
                source="initial_retrieval",
            )
        if self.experiment_config.use_workspace:
            schema_text = (
                self._metadata.to_prompt(max_chars=12000)
                if self._metadata is not None
                else self._db.format_schema()
            )
            self._workspace = EvidenceWorkspace(
                project_root=config.PROJECT_ROOT,
                schema_text=schema_text,
            )
        if self.experiment_config.use_enrichment:
            self._enrichment = enrich_question(question, self._db, metadata=self._metadata)
            if self._workspace is not None:
                self._workspace.add("query enrichment", self._enrichment.to_dict())
        if self.experiment_config.use_probe_queries:
            if self._enrichment is None:
                self._enrichment = enrich_question(
                    question,
                    self._db,
                    metadata=self._metadata,
                )
            self._probe_summary = run_probe_queries(
                self._db,
                self._enrichment,
                workspace=self._workspace,
            )
        return normalize_sql_text(self.complete(query=question))

    def _build_repl_env(self, query: str, context: str) -> dict[str, Any]:
        env = super()._build_repl_env(query, context)
        if hasattr(self, "_db"):
            env["db"] = self._db
        if self.experiment_config.use_recursion and hasattr(self, "_db_path"):
            env["answer_subquestion"] = self._answer_subquestion
        if self.experiment_config.use_metadata and self._metadata is not None:
            env["metadata"] = self._metadata.to_dict()
        if self.experiment_config.use_enrichment and self._enrichment is not None:
            env["enrichment"] = self._enrichment.to_dict()
        if self.experiment_config.use_probe_queries and self._probe_summary is not None:
            env["probe_results"] = self._probe_summary.to_dict()
        if self.experiment_config.use_schema_memory and self._schema_memory is not None:
            env["schema_memory"] = self._schema_memory
        if self.experiment_config.use_workspace and self._workspace is not None:
            env["workspace"] = self._workspace
            self._workspace.set_runtime_env(env)
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
            use_enrichment=self.experiment_config.use_enrichment,
            use_probe_queries=self.experiment_config.use_probe_queries,
            use_schema_memory=self.experiment_config.use_schema_memory,
            initial_top_k=self.experiment_config.initial_top_k,
            use_workspace=self.experiment_config.use_workspace,
            prompt_version=self.experiment_config.prompt_version,
            llm_kwargs=self.llm_kwargs,
        )
        result = child.answer(question, self._db_path)
        self._llm_calls += int(result.get("llm_calls") or 0)
        self._input_tokens += int(result.get("input_tokens") or 0)
        self._output_tokens += int(result.get("output_tokens") or 0)
        self._recursion_trace.append(result)
        if self._schema_memory is not None:
            child_stats = result.get("db_stats") or {}
            self._schema_memory.merge_columns(
                child_stats.get("inspected_columns") or {},
                source="recursive_db_inspection",
            )
            child_memory = child_stats.get("schema_memory") or {}
            child_columns: dict[str, list[str]] = {}
            for item in child_memory.get("columns") or []:
                child_columns.setdefault(str(item["table"]), []).append(
                    str(item["column"])
                )
            self._schema_memory.merge_columns(
                child_columns,
                source="recursive_schema_memory",
            )
        return result

    @property
    def experiment_stats(self) -> dict[str, Any]:
        db_stats = self._db.stats() if hasattr(self, "_db") else {}
        if self._schema_memory is not None:
            self._schema_memory.merge_columns(
                db_stats.get("inspected_columns") or {},
                source="root_db_inspection",
            )
        preloaded_columns = (
            {
                table.name: [column["name"] for column in table.columns]
                for table in self._metadata.tables
            }
            if self._metadata is not None and self.experiment_config.use_metadata
            else {}
        )
        schema_memory = (
            self._schema_memory.snapshot()
            if self._schema_memory is not None
            else {
                "tables": [],
                "columns": [],
                "selected_table_count": 0,
                "selected_column_count": 0,
            }
        )
        enrichment_tables = (
            [
                str(item["table"])
                for item in self._enrichment.candidate_tables
            ]
            if self._enrichment is not None
            and self.experiment_config.use_enrichment
            else []
        )
        enrichment_columns = (
            [
                {
                    "table": str(item["table"]),
                    "column": str(item["column"]),
                }
                for item in self._enrichment.candidate_columns
            ]
            if self._enrichment is not None
            and self.experiment_config.use_enrichment
            else []
        )
        return {
            **self.stats,
            **db_stats,
            "preloaded_tables": sorted(preloaded_columns),
            "preloaded_columns": preloaded_columns,
            "schema_memory": schema_memory,
            "schema_memory_events": (
                self._schema_memory.events()
                if self._schema_memory is not None
                else []
            ),
            "enrichment_tables": enrichment_tables,
            "enrichment_columns": enrichment_columns,
            "recursion_calls": len(self._recursion_trace),
            "recursion_used": bool(self._recursion_trace),
            "recursion_trace": [dict(item) for item in self._recursion_trace],
            "db_trace": self._db.trace() if hasattr(self, "_db") else [],
        }

    async def acomplete(self, query: str = "", context: str = "", **kwargs: Any) -> str:
        if query and not context:
            context = query
            query = ""

        if self._current_depth > self.max_depth:
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

        if model_supports_stop(self.model):
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
        if self.experiment_config.use_enrichment:
            available_tools.append("- enrichment (precomputed query-enrichment hints)")
        if self.experiment_config.use_probe_queries:
            available_tools.append("- probe_results (pre-run exploratory SQL results)")
        if self.experiment_config.use_schema_memory:
            available_tools.extend(
                [
                    "- schema_memory.search(query, top_k=10)",
                    "- schema_memory.add_table(table)",
                    "- schema_memory.add_column(table, column)",
                    "- schema_memory.snapshot()",
                ]
            )
        if self.experiment_config.use_workspace:
            available_tools.extend(
                [
                    "- workspace.add(note, data)",
                    "- workspace.read()",
                    "- workspace.save_result(name, data)",
                    "- workspace.load_result(name)",
                    "- workspace.list_files(relative_dir='')",
                    "- workspace.read_file(relative_path, max_chars=4000)",
                    "- workspace.read_schema_file(max_chars=6000)",
                    "- workspace.write_note_file(name, content)",
                    "- workspace.write_python_script(name, code)",
                    "- workspace.run_python_script(name)",
                    "- workspace.run_python(code)",
                ]
            )

        rules = [
            "Use at most one Python code block per assistant turn.",
            "Do not write fake observations or fake user messages.",
            "Only read-only SQLite queries are allowed.",
            "Use SQLite-compatible SQL only; do not use COUNT(DISTINCT ...) OVER (...) or other window-function DISTINCT forms.",
            "The final SELECT must return only the columns requested by the question, with no helper columns used only for sorting or calculation.",
            "When a question asks for least/most/highest/lowest over an entity within a year or period, aggregate over that entity and period before sorting.",
            "Avoid correlated subqueries that rescan large tables; for per-group minima/maxima, pre-aggregate in CTEs and then rank or join those CTEs.",
            "Workspace writes are limited to results/model_workspace.",
            "Do not try to read secrets such as .env files.",
            "When schema_memory is available, start from its selected columns and expand it only when evidence is missing.",
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
        if self.experiment_config.use_schema_memory and hasattr(self, "_db"):
            db_summary = (
                f"Database: {self._db_path.stem} | bounded schema memory enabled; "
                "use schema_memory.search() for controlled expansion"
            )
        else:
            db_summary = self._db.describe() if hasattr(self, "_db") else "(no database)"
        parts = [f"QUESTION: {question}", db_summary]

        if self.experiment_config.use_metadata and self._metadata is not None:
            parts.append(self._metadata.to_prompt())
        else:
            parts.append("No pre-extracted metadata is provided in this run.")

        if self.experiment_config.use_enrichment and self._enrichment is not None:
            parts.append(self._enrichment.to_prompt())
        else:
            parts.append("No query enrichment is provided in this run.")

        if self.experiment_config.use_probe_queries and self._probe_summary is not None:
            parts.append(self._probe_summary.to_prompt())
        else:
            parts.append("No probe-query results are provided in this run.")

        if self.experiment_config.use_schema_memory and self._schema_memory is not None:
            parts.append(self._schema_memory.to_prompt())
        else:
            parts.append("No bounded schema memory is provided in this run.")

        if self.experiment_config.use_workspace and self._workspace is not None:
            parts.append(f"WORKSPACE SNAPSHOT:\n{self._workspace.summary()}")

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
    use_enrichment: bool = False,
    use_probe_queries: bool = False,
    use_schema_memory: bool = False,
    initial_top_k: int = 10,
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
        use_enrichment=use_enrichment,
        use_probe_queries=use_probe_queries,
        use_schema_memory=use_schema_memory,
        initial_top_k=initial_top_k,
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
