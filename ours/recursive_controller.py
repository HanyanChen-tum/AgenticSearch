"""High-level controller for Recursive DB-RLM runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ours.db_environment import get_db_path
from ours.recursive_db_rlm import DBRLM
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql


@dataclass
class RecursiveDBController:
    """Coordinate one root DB-RLM run and package evaluation metadata."""

    model: str
    api_base: str | None = None
    api_key: str | None = None
    recursive_model: str | None = None
    max_depth: int = 3
    max_iterations: int = 10
    temperature: float = 0
    use_metadata: bool = False
    use_recursion: bool = True
    use_workspace: bool = False
    prompt_version: str = "recursive"

    def build_agent(self) -> DBRLM:
        return DBRLM(
            model=self.model,
            recursive_model=self.recursive_model or self.model,
            api_base=self.api_base,
            api_key=self.api_key,
            max_depth=self.max_depth,
            max_iterations=self.max_iterations,
            temperature=self.temperature,
            use_metadata=self.use_metadata,
            use_recursion=self.use_recursion,
            use_workspace=self.use_workspace,
            prompt_version=self.prompt_version,
        )

    def complete_sql(self, question: str, db_path: str | Path) -> dict[str, Any]:
        agent = self.build_agent()
        sql = agent.complete_sql(question, db_path)
        return {
            "sql": sql,
            "llm_calls": agent.stats["llm_calls"],
            "iterations": agent.stats["iterations"],
            "ablation_config": agent.experiment_config.to_dict(),
        }

    def run_one(self, example: dict[str, Any], database_dir: str | Path) -> dict[str, Any]:
        db_path = get_db_path(database_dir, example["db_id"])
        generation_error = None
        result = {"sql": "", "llm_calls": 0, "iterations": 0}

        try:
            result = self.complete_sql(example["question"], db_path)
        except Exception as error:
            generation_error = str(error)

        predicted_sql = result["sql"]
        predicted_exec = (
            execute_sql(db_path, predicted_sql, read_only=True)
            if predicted_sql and generation_error is None
            else {"answer": None, "error": generation_error or "No SQL generated"}
        )
        gold_exec = execute_sql(db_path, example["gold_sql"], read_only=True)

        return {
            "id": example["id"],
            "method": "ours_recursive_db_rlm",
            "db_id": example["db_id"],
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
            "error": predicted_exec.get("error") or gold_exec.get("error"),
            "llm_calls": result["llm_calls"],
            "iterations": result["iterations"],
            "ablation_config": result.get("ablation_config"),
        }
