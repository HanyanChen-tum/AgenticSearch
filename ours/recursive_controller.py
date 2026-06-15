"""Recursion limits, global budgets, and trace collection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RecursionConfig:
    max_depth: int = 2
    max_actions: int = 24
    max_actions_per_agent: int = 8
    max_children_per_agent: int = 3
    token_budget: int = 12000
    max_observation_chars: int = 5000
    max_rows: int = 20
    final_repair_attempts: int = 1

    def __post_init__(self) -> None:
        integer_fields = asdict(self)
        for name, value in integer_fields.items():
            minimum = 0 if name in {"max_depth", "final_repair_attempts"} else 1
            if value < minimum:
                raise ValueError(f"{name} must be >= {minimum}")


@dataclass
class BudgetState:
    actions_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TraceEvent:
    agent_id: str
    depth: int
    action: str
    arguments: dict[str, Any]
    observation: Any


@dataclass
class RecursiveController:
    config: RecursionConfig
    budget: BudgetState = field(default_factory=BudgetState)
    trace: list[TraceEvent] = field(default_factory=list)
    _agent_counter: int = 0

    def new_agent_id(self) -> str:
        agent_id = f"agent_{self._agent_counter}"
        self._agent_counter += 1
        return agent_id

    def can_take_action(self) -> bool:
        return (
            self.budget.actions_used < self.config.max_actions
            and self.budget.total_tokens < self.config.token_budget
        )

    def can_spawn(self, depth: int) -> bool:
        return depth < self.config.max_depth and self.can_take_action()

    def record_llm_usage(
        self,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        self.budget.llm_calls += 1
        self.budget.input_tokens += input_tokens or 0
        self.budget.output_tokens += output_tokens or 0

    def record_action(
        self,
        agent_id: str,
        depth: int,
        action: str,
        arguments: dict[str, Any],
        observation: Any,
    ) -> None:
        self.budget.actions_used += 1
        self.trace.append(
            TraceEvent(
                agent_id=agent_id,
                depth=depth,
                action=action,
                arguments=arguments,
                observation=observation,
            )
        )

    def trace_as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(event) for event in self.trace]
