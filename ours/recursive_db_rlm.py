"""DB-RLM: RLM adapter for Text-to-SQL on Spider/BIRD databases."""

from __future__ import annotations

import re
import json
import time
import asyncio
import copy
from pathlib import Path
from typing import Any, Optional

import litellm
litellm.drop_params = True  # drop unsupported params (e.g. stop sequences on Azure)
litellm.suppress_debug_info = True  # keep provider diagnostics out of batch progress

from src.rlm.core import RLM, MaxIterationsError, MaxDepthError
from src.rlm.parser import parse_response, is_final
from src.rlm.repl import REPLError
from src.rlm.types import Message

from ours.db_environment import DBEnvironment, get_db_path
from ours.agent.capabilities import GatedDBEnvironment
from ours.agent.config import AgentConfig, get_agent_config
from ours.agent.context_store import (
    ContextStore,
    GatedContextStore,
    verify_information_equivalence,
)
from ours.agent.knowledge import KnowledgeAssembler
from ours.agent.prompts import get_system_prompt
from ours.agent.state import AgentExecutionState, ExecutionStatus
from ours.agent.query_plan import (
    QUERY_PLAN_MODE,
    QueryPlanState,
    parse_initial_plan,
    parse_revision,
    plan_sql_adherence,
    protocol_manifest,
)
from shared.token_usage import aggregate_call_usage


# Stop sequences that prevent the model from hallucinating fake turns
_STOP_SEQUENCES = ["\nUser:", "\n### User", "\nObservation:", "\nSystem:"]


class DBRLM(RLM):
    """RLM subclass wired to a SQLite database for Text-to-SQL generation.

    Usage:
        agent = DBRLM(model="ollama/qwen2.5:7b", api_base="http://localhost:11434")
        sql = agent.complete_sql("How many singers do we have?", db_path)
    """

    def __init__(
        self,
        *args: Any,
        retriever: Any = None,
        k: int = 0,
        agent_config: AgentConfig | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.agent_config = agent_config or get_agent_config("clean-e0")
        self._knowledge = KnowledgeAssembler(
            retriever=retriever,
            k=k,
            use_db_hints=self.agent_config.use_db_hints,
            query_pattern_mode=self.agent_config.query_pattern_mode,
            offline_metadata_mode=self.agent_config.offline_metadata_mode,
        )
        self._execution_state = AgentExecutionState()
        self._query_plan_state = QueryPlanState()

    def _prepare_trace(self, question: str, db_path: str | Path, evidence: str) -> None:
        self._trace_turn = 0
        self._trace_usage_start = len(self._llm_call_usage)
        self._trace_messages: list[Message] = []
        self._trace_events: list[dict[str, Any]] = []
        self._execution_state = AgentExecutionState()
        self._query_plan_state = QueryPlanState()
        self._context_store = None
        self._trace_context = {
            "question": question,
            "db_path": str(Path(db_path).resolve()),
            "evidence": evidence.strip(),
            "agent_config": self.agent_config.to_manifest(),
            "agent_config_sha256": self.agent_config.sha256,
            "knowledge_manifest": self._knowledge.manifest(),
            "query_plan_protocol": (
                protocol_manifest()
                if self.agent_config.planner_mode == QUERY_PLAN_MODE
                else None
            ),
        }
        self._db = DBEnvironment(db_path, event_sink=self._record_tool_event)
        self._evidence = evidence.strip()

    def _record_tool_event(
        self,
        tool: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        event = {
            "sequence": len(self._trace_events) + 1,
            "turn": self._trace_turn,
            "tool": tool,
            "arguments": copy.deepcopy(arguments),
            "result": copy.deepcopy(result),
        }
        self._trace_events.append(event)
        if tool == "db.sample_values":
            self._execution_state.record_sample_values(str(arguments.get("column", "")))
        if tool == "db.execute":
            sql = str(arguments.get("sql", ""))
            self._execution_state.record(sql, result)
            current_plan = self._query_plan_state.current_plan
            if current_plan is not None:
                self._trace_events.append({
                    "sequence": len(self._trace_events) + 1,
                    "turn": self._trace_turn,
                    "tool": "query_plan.adherence",
                    "arguments": {
                        "sql": sql,
                        "candidate_purpose": self._query_plan_state.current_candidate_purpose,
                        "observation_ref": event["sequence"],
                    },
                    "result": plan_sql_adherence(current_plan, sql),
                })

    def trace_snapshot(self) -> dict[str, Any]:
        calls = self._llm_call_usage[getattr(self, "_trace_usage_start", 0):]
        return {
            **copy.deepcopy(getattr(self, "_trace_context", {})),
            "messages": copy.deepcopy(getattr(self, "_trace_messages", [])),
            "events": copy.deepcopy(getattr(self, "_trace_events", [])),
            "llm_call_usage": copy.deepcopy(calls),
            "token_usage": aggregate_call_usage(calls),
            "execution_state": self._execution_state.to_dict(),
            "query_plan_state": self._query_plan_state.to_dict(),
            "context_store_reads": (
                self._context_store.read_log()
                if getattr(self, "_context_store", None) is not None
                else None
            ),
        }

    def _latest_observation_ref(self) -> int | None:
        for event in reversed(self._trace_events):
            if str(event.get("tool", "")).startswith("db."):
                return int(event["sequence"])
        return None

    def _record_query_plan_event(
        self,
        tool: str,
        payload: dict[str, Any] | None,
        errors: list[str],
    ) -> None:
        self._trace_events.append({
            "sequence": len(self._trace_events) + 1,
            "turn": self._trace_turn,
            "tool": tool,
            "arguments": {},
            "result": {
                "valid": not errors,
                "payload": copy.deepcopy(payload),
                "errors": list(errors),
            },
        })

    def _accept_query_plan_for_action(self, response: str) -> tuple[bool, str]:
        if self.agent_config.planner_mode != QUERY_PLAN_MODE:
            return True, ""
        python_block_count = len(re.findall(
            r"```python\s*\n[\s\S]*?\n```",
            response or "",
            flags=re.IGNORECASE,
        ))
        if python_block_count < 1:
            errors = [
                "each E4-A action must contain at least one Python block; "
                "found none"
            ]
            self._record_query_plan_event("query_plan.action_contract", None, errors)
            return False, "Action contract invalid: " + errors[0]
        if self._query_plan_state.initial is None:
            plan, errors = parse_initial_plan(response)
            self._record_query_plan_event("query_plan.initial", plan, errors)
            if errors:
                return False, "Initial QueryPlan invalid: " + "; ".join(errors)
            self._query_plan_state.initial = plan
            return True, ""

        observation_ref = self._latest_observation_ref()
        if observation_ref is None:
            errors = ["no structured observation is available for a revision"]
            self._record_query_plan_event("query_plan.revision", None, errors)
            return False, "Plan revision invalid: " + errors[0]
        revision, errors = parse_revision(
            response,
            latest_observation_ref=observation_ref,
        )
        self._record_query_plan_event("query_plan.revision", revision, errors)
        if errors:
            return False, "Plan revision invalid: " + "; ".join(errors)
        self._query_plan_state.revisions.append(revision)
        return True, ""

    def complete_sql(self, question: str, db_path: str | Path, evidence: str = "") -> str:
        """Synchronous entry point: question + db_path → SQL string.
        evidence: BIRD-style hint string (definitions of column values, formulas, etc.)
        """
        self._prepare_trace(question, db_path, evidence)
        return self.complete(query=question)

    # ------------------------------------------------------------------
    # Override: inject `db` into the REPL environment
    # ------------------------------------------------------------------

    def _build_repl_env(self, query: str, context: str) -> dict[str, Any]:
        if self.agent_config.capability_gate:
            env: dict[str, Any] = {
                "context": context,
                "query": query,
                "re": re,
            }
            if hasattr(self, "_db"):
                env["db"] = GatedDBEnvironment(
                    self._db,
                    self.agent_config.allowed_db_methods,
                    self._record_tool_event,
                )
            return env

        env = super()._build_repl_env(query, context)
        if hasattr(self, "_db"):
            env["db"] = self._db
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

        if self.agent_config.schema_context_mode == "runtime-full":
            schema_str = self._db.format_schema() if hasattr(self, "_db") else "(no schema)"
        else:
            schema_str = ""
        evidence = getattr(self, "_evidence", "")
        db_id = (
            getattr(self._db, "db_path", Path("")).stem
            if hasattr(self, "_db")
            else ""
        )
        blocks = self._knowledge.blocks(question, db_id, evidence)
        if schema_str:
            blocks = {**blocks, "schema": f"Schema:\n{schema_str}\n\n"}
        if hasattr(self, "_trace_context"):
            self._trace_context["knowledge_selection"] = self._knowledge.selection_manifest(
                question, db_id, evidence
            )
        system_prompt = get_system_prompt(self.agent_config.prompt_profile)

        if self.agent_config.context_mode == "store-readonly":
            self._context_store = ContextStore(blocks, event_sink=self._record_tool_event)
            repl_env["ctx"] = GatedContextStore(
                self._context_store, self._record_tool_event
            )
            if hasattr(self, "_trace_context"):
                self._trace_context["context_store"] = {
                    "manifest": self._context_store.manifest(),
                    "information_equivalence": verify_information_equivalence(
                        blocks, self._context_store
                    ),
                }
            directory = "\n".join(
                f"  - {row['section']} ({row['chars']} chars)"
                for row in self._context_store.list()
            )
            user_content = (
                f"QUESTION: {question}\n\n"
                "CONTEXT STORE SECTIONS (read with ctx.read(\"name\")):\n"
                f"{directory}\n\n"
                "Read what you need, explore the DB if needed, test your SQL, "
                "then FINAL(\"your sql\")."
            )
        else:
            # Order is load-bearing: it defines the prompt hash recorded in every
            # historical run's manifest. Do not reorder.
            user_content = (
                f"QUESTION: {question}"
                f"{blocks['hint']}"
                f"{blocks['database_notes']}"
                f"{blocks['few_shot']}\n"
                f"{blocks['query_patterns']}"
                f"{blocks['offline_metadata']}"
                f"{blocks.get('schema', '')}"
                + "Follow the Hint above, explore the DB if needed, test your SQL, then FINAL(\"your sql\")."
            )

        messages: list[Message] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        self._trace_messages = messages

        # Inject stop sequences unless caller already set them
        kwargs.setdefault("stop", _STOP_SEQUENCES)

        last_exec_result = None
        repeat_count = 0

        for iteration in range(self.max_iterations):
            self._iterations = iteration + 1
            self._trace_turn = iteration + 1
            response = await self._call_llm(messages, **kwargs)
            response = _truncate_at_fake_turn(response)
            response = _convert_sql_blocks(response)

            print(f"\n{'='*80}")
            print(f"DB-RLM ITERATION {iteration}")
            print(response)
            print('='*80)

            has_code = bool(re.search(r'```python', response))

            if self.agent_config.planner_mode == QUERY_PLAN_MODE:
                if has_code:
                    accepted, plan_error = self._accept_query_plan_for_action(response)
                    if not accepted:
                        messages.append({"role": "assistant", "content": response})
                        latest_ref = self._latest_observation_ref()
                        required_block = (
                            "a fenced queryplan JSON block"
                            if self._query_plan_state.initial is None
                            else (
                                "a fenced plan-revision JSON block with integer "
                                f"observation_ref={latest_ref}"
                            )
                        )
                        messages.append({"role": "user", "content": (
                            f"BLOCKED ACTION: {plan_error}. "
                            f"Return {required_block} and one or more Python tool blocks "
                            "in the same response. Do not repeat a queryplan after it has been accepted."
                        )})
                        continue
                elif is_final(response) and self._query_plan_state.initial is None:
                    errors = ["FINAL is not allowed before a valid initial QueryPlan"]
                    self._record_query_plan_event("query_plan.final_check", None, errors)
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": (
                        "BLOCKED FINAL: create the required QueryPlan and execute a candidate SQL first."
                    )})
                    continue

            # FINAL is a state transition, not a string-only parser action.
            if is_final(response) and not has_code:
                answer = parse_response(response, repl_env)
                if answer is not None:
                    valid, reason = self._execution_state.validate_final(
                        answer,
                        require_verified=self.agent_config.verified_final,
                    )
                    if valid:
                        messages.append({"role": "assistant", "content": response})
                        return answer
                    self._record_tool_event(
                        "final.blocked",
                        {"sql": answer},
                        {"allowed": False, "reason": reason},
                    )
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": (
                        f"BLOCKED FINAL: {reason}. "
                        "Execute the exact SQL you intend to submit, inspect the result, "
                        "then call FINAL with that same SQL."
                    )})
                    continue

            # Strip inline FINAL so REPL doesn't choke on it, then execute the code
            response_for_repl = re.sub(r'FINAL\s*\(.*?\)', '', response, flags=re.DOTALL).strip()
            previous_execution = self._execution_state.last_execution
            event_start = len(self._trace_events)
            try:
                exec_result = self.repl.execute(response_for_repl, repl_env)
            except REPLError as e:
                exec_result = f"REPL Error: {e}"
            except Exception as e:
                exec_result = f"Unexpected error: {e}"

            structured_events = [
                event
                for event in self._trace_events[event_start:]
                if str(event.get("tool", "")).startswith("db.")
            ]
            if structured_events:
                structured_observation = _format_structured_observations(structured_events)
                if exec_result in {
                    "Code executed successfully (no output)",
                    "No code to execute",
                }:
                    exec_result = structured_observation
                else:
                    exec_result = f"{exec_result}\n\n{structured_observation}"

            current_execution = self._execution_state.last_execution
            if current_execution is not None and current_execution is not previous_execution:
                if current_execution.status is ExecutionStatus.ERROR:
                    error = current_execution.result.get("error")
                    exec_result += f"\n\nSQL ERROR: {error} - fix the SQL and execute it again."
                elif current_execution.status is ExecutionStatus.EMPTY:
                    exec_result += (
                        "\n\nWARNING: Query returned 0 rows. Check JOIN conditions, "
                        "filters, column names, and stored value formats."
                    )
                elif current_execution.status is ExecutionStatus.ALL_NULL:
                    exec_result += (
                        "\n\nWARNING: Result is all NULL. Check whether the selected "
                        "column or JOIN path answers the question."
                    )
                if self.agent_config.literal_verification_nudge:
                    literal_warning = self._execution_state.unverified_literal_warning(
                        current_execution.sql
                    )
                    if literal_warning:
                        exec_result += f"\n\n{literal_warning}"

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
        "prompt_tokens": agent.stats["prompt_tokens"],
        "completion_tokens": agent.stats["completion_tokens"],
        "reasoning_tokens": agent.stats["reasoning_tokens"],
        "total_tokens": agent.stats["total_tokens"],
        "cached_prompt_tokens": agent.stats["cached_prompt_tokens"],
        "usage_missing_calls": agent.stats["usage_missing_calls"],
        "reasoning_usage_missing_calls": agent.stats["reasoning_usage_missing_calls"],
        "agent_profile": agent.agent_config.profile,
        "agent_config_sha256": agent.agent_config.sha256,
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


def _format_structured_observations(events: list[dict[str, Any]]) -> str:
    """Return authoritative tool results even when REPL stdout is empty."""
    rendered = ["STRUCTURED TOOL OBSERVATIONS (authoritative):"]
    for event in events:
        payload = json.dumps(
            event.get("result") or {},
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        if len(payload) > 4000:
            payload = payload[:4000] + "...[observation display truncated; trace retains full result]"
        rendered.append(
            f"OBSERVATION_REF {event['sequence']} {event['tool']}: {payload}"
        )
    return "\n".join(rendered)
