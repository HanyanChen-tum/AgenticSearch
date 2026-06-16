"""Recursive DB-RLM orchestration and experiment runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from tqdm import tqdm

from ours.db_environment import DatabaseEnvironment
from ours.recursive_controller import RecursionConfig, RecursiveController
from ours.subquestion_agent import AgentResult, LLMCallable, SubquestionAgent
from shared import config
from shared.data_loader import load_questions
from shared.evaluator import build_result_evaluation
from shared.io_utils import read_text, write_json
from shared.llm_client import LLMResponse, generate_response
from shared.logging_utils import setup_logger
from shared.schema_utils import get_database_path
from shared.sql_executor import execute_sql


METHOD_NAME = "ours_recursive_db_rlm"
PROMPT_PATH = config.PROMPTS_DIR / "ours_recursive_db_rlm.txt"
OUTPUT_PATH = config.RESULTS_DIR / f"{METHOD_NAME}.json"
LOG_PATH = config.PROJECT_ROOT / "logs" / "ours_recursive_db_rlm.log"

logger = setup_logger(METHOD_NAME, LOG_PATH)


def default_llm(prompt: str, system_instruction: str) -> LLMResponse:
    return generate_response(prompt, system_instruction)


def clean_sql(text: str) -> str:
    sql = text.strip()
    if sql.startswith("```"):
        lines = sql.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines).strip()
    if sql.upper().startswith("SQL:"):
        sql = sql[4:].strip()
    return sql


class RecursiveDBRLM:
    """Run recursive exploration, synthesize SQL, and repair execution errors."""

    def __init__(
        self,
        db_path: str | Path,
        prompt_template: str,
        *,
        recursion_config: RecursionConfig | None = None,
        llm: LLMCallable = default_llm,
    ) -> None:
        self.config = recursion_config or RecursionConfig()
        self.environment = DatabaseEnvironment(db_path, max_rows=self.config.max_rows)
        self.controller = RecursiveController(self.config)
        self.llm = llm
        self.agent = SubquestionAgent(
            self.environment,
            self.controller,
            llm,
            prompt_template,
        )

    def solve(self, question: str) -> dict[str, Any]:
        root_result = self.agent.run(question)
        if (
            self.controller.budget.total_tokens >= self.config.token_budget
            and root_result.candidate_sql
        ):
            predicted_sql = root_result.candidate_sql
        else:
            predicted_sql = self._synthesize_sql(question, root_result)
        execution = self.environment.execute_sql_full(predicted_sql)
        repair_attempts = 0

        while (
            execution["error"]
            and repair_attempts < self.config.final_repair_attempts
            and self.controller.budget.total_tokens < self.config.token_budget
        ):
            predicted_sql = self._repair_sql(
                question,
                root_result,
                predicted_sql,
                execution["error"],
            )
            execution = self.environment.execute_sql_full(predicted_sql)
            repair_attempts += 1

        return {
            "predicted_sql": predicted_sql,
            "predicted_answer": execution["rows"],
            "execution_error": execution["error"],
            "root_result": root_result.to_dict(),
            "trace": self.controller.trace_as_dicts(),
            "max_depth_reached": max(
                (event.depth for event in self.controller.trace),
                default=0,
            ),
            "actions_used": self.controller.budget.actions_used,
            "llm_calls": self.controller.budget.llm_calls,
            "input_tokens": self.controller.budget.input_tokens,
            "output_tokens": self.controller.budget.output_tokens,
            "repair_attempts": repair_attempts,
        }

    def _synthesize_sql(self, question: str, root_result: AgentResult) -> str:
        evidence = {
            "question": question,
            "recursive_result": root_result.to_dict(),
            "trace": self.controller.trace_as_dicts(),
        }
        prompt = (
            "Generate the final SQLite query for the question using only the "
            "recursive exploration evidence below. Return executable SQL only. "
            "Prefer a tested candidate SQL when it answers the full question.\n\n"
            f"{self._bounded_json(evidence)}"
        )
        response = self.llm(
            prompt,
            "You are an expert SQLite text-to-SQL synthesizer. Return SQL only.",
        )
        self.controller.record_llm_usage(
            response.input_tokens,
            response.output_tokens,
        )
        return clean_sql(response.text)

    def _repair_sql(
        self,
        question: str,
        root_result: AgentResult,
        sql: str,
        error: str,
    ) -> str:
        payload = {
            "question": question,
            "failed_sql": sql,
            "sqlite_error": error,
            "recursive_result": root_result.to_dict(),
        }
        prompt = (
            "Repair the failed SQLite query. Use the supplied database evidence "
            "and error. Return executable SQL only.\n\n"
            f"{self._bounded_json(payload)}"
        )
        response = self.llm(
            prompt,
            "You repair SQLite queries. Return SQL only and no explanation.",
        )
        self.controller.record_llm_usage(
            response.input_tokens,
            response.output_tokens,
        )
        return clean_sql(response.text)

    def _bounded_json(self, value: Any) -> str:
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        limit = self.config.max_observation_chars * 3
        if len(serialized) <= limit:
            return serialized
        question = value.get("question", "") if isinstance(value, dict) else ""
        return json.dumps(
            {
                "question": question,
                "evidence_truncated": True,
                "evidence_tail": serialized[-limit:],
            },
            ensure_ascii=False,
        )


def run_one(
    example: dict[str, Any],
    prompt_template: str,
    database_dir: Path,
    recursion_config: RecursionConfig,
    *,
    llm: LLMCallable = default_llm,
) -> dict[str, Any]:
    db_path = get_database_path(database_dir, example["db_id"])
    started_at = time.perf_counter()
    generation_error: str | None = None
    solution: dict[str, Any] = {
        "predicted_sql": "",
        "predicted_answer": None,
        "execution_error": None,
        "root_result": None,
        "trace": [],
        "max_depth_reached": 0,
        "actions_used": 0,
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "repair_attempts": 0,
    }

    try:
        solution = RecursiveDBRLM(
            db_path,
            prompt_template,
            recursion_config=recursion_config,
            llm=llm,
        ).solve(example["question"])
    except Exception as exc:
        generation_error = str(exc)

    gold_exec = execute_sql(db_path, example["gold_sql"])
    predicted_error = solution["execution_error"] or generation_error
    evaluation_fields = build_result_evaluation(
        solution["predicted_sql"],
        example["gold_sql"],
        predicted_answer=solution["predicted_answer"],
        gold_answer=gold_exec["answer"],
        predicted_error=predicted_error,
        gold_error=gold_exec["error"],
    )

    return {
        "id": example["id"],
        "method": METHOD_NAME,
        "db_id": example["db_id"],
        "question": example["question"],
        "predicted_sql": solution["predicted_sql"],
        "predicted_answer": solution["predicted_answer"],
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec["answer"],
        **evaluation_fields,
        "latency_seconds": round(time.perf_counter() - started_at, 4),
        "input_tokens": solution["input_tokens"],
        "output_tokens": solution["output_tokens"],
        "tool_calls": solution["actions_used"],
        "llm_calls": solution["llm_calls"],
        "actions_used": solution["actions_used"],
        "max_depth_reached": solution["max_depth_reached"],
        "repair_attempts": solution["repair_attempts"],
        "recursive_result": solution["root_result"],
        "trace": solution["trace"],
    }


def run_method(
    dataset_path: str | Path = config.DEFAULT_DATASET_PATH,
    output_path: str | Path = OUTPUT_PATH,
    database_dir: str | Path = config.DATABASE_DIR,
    limit: int | None = None,
    recursion_config: RecursionConfig | None = None,
) -> list[dict[str, Any]]:
    questions = load_questions(dataset_path)
    if limit is not None:
        questions = questions[:limit]
    method_config = recursion_config or RecursionConfig()
    prompt_template = read_text(PROMPT_PATH)

    logger.info("Starting %s with %d examples", METHOD_NAME, len(questions))
    logger.info("Recursion config: %s", method_config)
    results = [
        run_one(
            example,
            prompt_template,
            Path(database_dir),
            method_config,
        )
        for example in tqdm(questions, desc=METHOD_NAME)
    ]
    write_json(output_path, results)

    total = len(results)
    correct = sum(1 for row in results if row["correct"])
    logger.info(
        "Finished %s: total=%d correct=%d execution_accuracy=%.4f",
        METHOD_NAME,
        total,
        correct,
        correct / total if total else 0,
    )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Recursive DB-RLM.")
    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-actions", type=int, default=24)
    parser.add_argument("--max-actions-per-agent", type=int, default=8)
    parser.add_argument("--max-children-per-agent", type=int, default=3)
    parser.add_argument("--token-budget", type=int, default=12000)
    parser.add_argument("--max-rows", type=int, default=20)
    parser.add_argument("--final-repair-attempts", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_method(
        dataset_path=args.dataset,
        output_path=args.output,
        database_dir=args.database_dir,
        limit=args.limit,
        recursion_config=RecursionConfig(
            max_depth=args.max_depth,
            max_actions=args.max_actions,
            max_actions_per_agent=args.max_actions_per_agent,
            max_children_per_agent=args.max_children_per_agent,
            token_budget=args.token_budget,
            max_rows=args.max_rows,
            final_repair_attempts=args.final_repair_attempts,
        ),
    )


if __name__ == "__main__":
    main()
