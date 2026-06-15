"""Recursive database exploration agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from ours.db_environment import DatabaseEnvironment
from ours.recursive_controller import RecursiveController
from shared.llm_client import LLMResponse


class LLMCallable(Protocol):
    def __call__(self, prompt: str, system_instruction: str) -> LLMResponse: ...


@dataclass
class AgentResult:
    agent_id: str
    depth: int
    task: str
    summary: str
    candidate_sql: str = ""
    children: list["AgentResult"] = field(default_factory=list)
    stopped_reason: str = "finish"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "depth": self.depth,
            "task": self.task,
            "summary": self.summary,
            "candidate_sql": self.candidate_sql,
            "stopped_reason": self.stopped_reason,
            "children": [child.to_dict() for child in self.children],
        }


class SubquestionAgent:
    """Explore one database sub-question and optionally create child agents."""

    VALID_ACTIONS = {
        "list_tables",
        "describe_table",
        "sample_rows",
        "execute_sql",
        "spawn_subagent",
        "finish",
    }

    def __init__(
        self,
        environment: DatabaseEnvironment,
        controller: RecursiveController,
        llm: LLMCallable,
        prompt_template: str,
    ) -> None:
        self.environment = environment
        self.controller = controller
        self.llm = llm
        self.prompt_template = prompt_template

    def run(
        self,
        task: str,
        *,
        depth: int = 0,
        parent_context: str = "",
    ) -> AgentResult:
        agent_id = self.controller.new_agent_id()
        observations: list[dict[str, Any]] = []
        children: list[AgentResult] = []
        candidate_sql = ""
        summary = ""
        stopped_reason = "per_agent_action_limit"
        child_count = 0

        for _ in range(self.controller.config.max_actions_per_agent):
            if not self.controller.can_take_action():
                stopped_reason = "global_budget_exhausted"
                break

            prompt = self._build_prompt(
                agent_id=agent_id,
                task=task,
                depth=depth,
                parent_context=parent_context,
                observations=observations,
                children=children,
            )
            response = self.llm(prompt, self._system_instruction())
            self.controller.record_llm_usage(
                response.input_tokens,
                response.output_tokens,
            )

            try:
                decision = parse_json_object(response.text)
                action = str(decision.get("action", "")).strip()
                arguments = decision.get("arguments") or {}
                if action not in self.VALID_ACTIONS:
                    raise ValueError(f"Unknown action: {action}")
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be a JSON object")
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                observation = {"error": f"Invalid agent response: {exc}"}
                self.controller.record_action(
                    agent_id, depth, "invalid_response", {}, observation
                )
                observations.append(
                    {"action": "invalid_response", "observation": observation}
                )
                continue

            if action == "finish":
                summary = str(arguments.get("summary", "")).strip()
                candidate_sql = str(arguments.get("candidate_sql", "")).strip()
                observation = {
                    "summary": summary,
                    "candidate_sql": candidate_sql,
                }
                self.controller.record_action(
                    agent_id, depth, action, arguments, observation
                )
                stopped_reason = "finish"
                break

            if action == "spawn_subagent":
                if child_count >= self.controller.config.max_children_per_agent:
                    observation = {"error": "Per-agent child limit reached"}
                elif not self.controller.can_spawn(depth):
                    observation = {"error": "Maximum recursion depth or budget reached"}
                else:
                    child_task = str(arguments.get("task", "")).strip()
                    if not child_task:
                        observation = {"error": "spawn_subagent requires task"}
                    else:
                        # Reserve the parent's spawn action before the child can
                        # consume the remainder of the shared global budget.
                        trace_index = len(self.controller.trace)
                        self.controller.record_action(
                            agent_id,
                            depth,
                            action,
                            arguments,
                            {"status": "running"},
                        )
                        child = self.run(
                            child_task,
                            depth=depth + 1,
                            parent_context=self._child_context(task, observations),
                        )
                        children.append(child)
                        child_count += 1
                        observation = child.to_dict()
                        self.controller.trace[trace_index].observation = observation
                        observations.append(
                            {"action": action, "observation": observation}
                        )
                        continue
            else:
                observation = self._execute_tool(action, arguments)

            self.controller.record_action(
                agent_id, depth, action, arguments, observation
            )
            observations.append({"action": action, "observation": observation})

        if not summary:
            summary = self._fallback_summary(observations, children)

        return AgentResult(
            agent_id=agent_id,
            depth=depth,
            task=task,
            summary=summary,
            candidate_sql=candidate_sql,
            children=children,
            stopped_reason=stopped_reason,
        )

    def _execute_tool(self, action: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if action == "list_tables":
                return self.environment.list_tables()
            if action == "describe_table":
                return self.environment.describe_table(str(arguments.get("table", "")))
            if action == "sample_rows":
                return self.environment.sample_rows(
                    str(arguments.get("table", "")),
                    int(arguments.get("limit", 5)),
                )
            if action == "execute_sql":
                return self.environment.execute_sql(str(arguments.get("sql", "")))
        except (TypeError, ValueError) as exc:
            return {"error": str(exc)}
        return {"error": f"Unsupported tool action: {action}"}

    def _build_prompt(
        self,
        *,
        agent_id: str,
        task: str,
        depth: int,
        parent_context: str,
        observations: list[dict[str, Any]],
        children: list[AgentResult],
    ) -> str:
        state = {
            "agent_id": agent_id,
            "task": task,
            "depth": depth,
            "max_depth": self.controller.config.max_depth,
            "parent_context": parent_context,
            "observations": observations,
            "child_results": [child.to_dict() for child in children],
            "remaining_global_actions": (
                self.controller.config.max_actions
                - self.controller.budget.actions_used
            ),
            "remaining_token_budget": (
                self.controller.config.token_budget
                - self.controller.budget.total_tokens
            ),
        }
        limit = self.controller.config.max_observation_chars
        serialized = json.dumps(state, ensure_ascii=False, default=str)
        if len(serialized) > limit:
            compact_state = {
                **state,
                "parent_context": parent_context[-1000:],
                "observations": observations[-3:],
                "child_results": [
                    {
                        "agent_id": child.agent_id,
                        "task": child.task,
                        "summary": child.summary[-1000:],
                        "candidate_sql": child.candidate_sql,
                    }
                    for child in children
                ],
                "context_truncated": True,
            }
            serialized = json.dumps(
                compact_state,
                ensure_ascii=False,
                default=str,
            )
        if len(serialized) > limit:
            serialized = json.dumps(
                {
                    "agent_id": agent_id,
                    "task": task,
                    "depth": depth,
                    "context_truncated": True,
                    "recent_evidence": serialized[-max(1, limit // 2) :],
                },
                ensure_ascii=False,
            )
        return f"{self.prompt_template.strip()}\n\nCURRENT STATE:\n{serialized}"

    @staticmethod
    def _system_instruction() -> str:
        return (
            "You are a recursive database exploration agent. Return exactly one "
            "JSON object and no Markdown. Choose one action at a time. Do not invent "
            "schema or query results."
        )

    def _child_context(
        self,
        task: str,
        observations: list[dict[str, Any]],
    ) -> str:
        context = json.dumps(
            {"parent_task": task, "parent_observations": observations},
            ensure_ascii=False,
            default=str,
        )
        return context[-self.controller.config.max_observation_chars :]

    @staticmethod
    def _fallback_summary(
        observations: list[dict[str, Any]],
        children: list[AgentResult],
    ) -> str:
        payload = {
            "observations": observations[-3:],
            "child_summaries": [child.summary for child in children],
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating a surrounding Markdown fence."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:] if lines else lines
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(stripped[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed
