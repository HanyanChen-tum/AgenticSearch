"""Select among existing Text-to-SQL candidates with execution-aware verification.

This script is intentionally a thin layer over already generated result files.
It reuses strong direct Text-to-SQL output as a default candidate, adds our
metadata/probe candidates, executes every candidate SQL, and asks a verifier to
choose only when the executable answers disagree.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ours.db_environment import DBEnvironment, get_db_path
from shared import config
from shared.data_loader import load_questions
from shared.evaluator import is_correct
from shared.llm_client import generate_chat
from shared.sql_executor import execute_sql, normalize_sql_text


METHOD_NAME = "bird_ours_candidate_ensemble"
DEFAULT_CANDIDATE_FILES = [
    config.RESULTS_DIR / "bird_b2_500.json",
    config.RESULTS_DIR / "bird_ours_metadata_enrichment_500.json",
    config.RESULTS_DIR / "bird_ours_metadata_enrichment_probe_500.json",
]


def load_rows_by_id(paths: list[Path]) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str]]:
    rows_by_id: dict[str, dict[str, dict[str, Any]]] = {}
    labels: list[str] = []
    for path in paths:
        if not path.exists():
            print(f"Warning: candidate file not found, skipping: {path}")
            continue
        label = path.stem
        labels.append(label)
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError(f"Expected list in candidate file: {path}")
        for row in rows:
            example_id = str(row.get("id"))
            rows_by_id.setdefault(example_id, {})[label] = row
    return rows_by_id, labels


def compact_answer(answer: Any, max_chars: int = 1200) -> str:
    text = json.dumps(answer, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "... [truncated]"
    return text


def answer_key(answer: Any) -> str:
    return json.dumps(answer, ensure_ascii=False, sort_keys=True, default=str)


def is_empty_answer(answer: Any) -> bool:
    return answer in (None, [], ())


def build_repair_prompt(
    question: str,
    schema_text: str,
    sql: str,
    error: str | None,
    answer: Any,
) -> str:
    failure = error or "SQL executed successfully but returned an empty result."
    return (
        "Question:\n"
        f"{question}\n\n"
        "Database schema:\n"
        f"{schema_text[:12000]}\n\n"
        "The following SQLite SQL candidate failed or looks invalid for the question.\n"
        "Original SQL:\n"
        f"{sql}\n\n"
        "Observed failure:\n"
        f"{failure}\n\n"
        "Observed answer preview:\n"
        f"{compact_answer(answer, max_chars=800)}\n\n"
        "Repair the SQL. Return only one executable SQLite SELECT/WITH query. "
        "Do not explain. Do not use markdown."
    )


def repair_sql_candidate(
    question: str,
    db_path: Path,
    schema_text: str,
    sql: str,
    error: str | None,
    answer: Any,
    allow_empty_candidates: bool,
    repair_attempts: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    current_sql = sql
    current_error = error
    current_answer = answer
    repair_input_tokens: list[int] = []
    repair_output_tokens: list[int] = []
    repair_latency_seconds = 0.0
    repair_trace: list[dict[str, Any]] = []

    for attempt in range(1, repair_attempts + 1):
        started = time.perf_counter()
        response = generate_chat(
            [
                {
                    "role": "user",
                    "content": build_repair_prompt(
                        question,
                        schema_text,
                        current_sql,
                        current_error,
                        current_answer,
                    ),
                }
            ],
            system_instruction=(
                "You are a SQL repair assistant. Return only executable SQLite SQL."
            ),
        )
        repair_latency_seconds += time.perf_counter() - started
        if isinstance(response.input_tokens, int):
            repair_input_tokens.append(response.input_tokens)
        if isinstance(response.output_tokens, int):
            repair_output_tokens.append(response.output_tokens)

        repaired_sql = normalize_sql_text(response.text)
        execution = execute_sql(db_path, repaired_sql, read_only=True)
        repaired_error = execution.get("error")
        repaired_answer = execution.get("answer")
        repaired_usable = repaired_error is None and (
            allow_empty_candidates or not is_empty_answer(repaired_answer)
        )
        repair_trace.append(
            {
                "attempt": attempt,
                "sql": repaired_sql,
                "answer_preview": compact_answer(repaired_answer, max_chars=800),
                "error": repaired_error,
                "usable": repaired_usable,
            }
        )

        if repaired_usable:
            return (
                {
                    "sql": repaired_sql,
                    "answer": repaired_answer,
                    "answer_preview": compact_answer(repaired_answer),
                    "error": repaired_error,
                    "usable": True,
                },
                {
                    "repair_attempted": True,
                    "repair_success": True,
                    "repair_attempts_used": attempt,
                    "repair_latency_seconds": round(repair_latency_seconds, 4),
                    "repair_input_tokens": sum(repair_input_tokens) if repair_input_tokens else None,
                    "repair_output_tokens": sum(repair_output_tokens) if repair_output_tokens else None,
                    "repair_trace": repair_trace,
                },
            )

        current_sql = repaired_sql
        current_error = repaired_error
        current_answer = repaired_answer

    return (
        None,
        {
            "repair_attempted": True,
            "repair_success": False,
            "repair_attempts_used": repair_attempts,
            "repair_latency_seconds": round(repair_latency_seconds, 4),
            "repair_input_tokens": sum(repair_input_tokens) if repair_input_tokens else None,
            "repair_output_tokens": sum(repair_output_tokens) if repair_output_tokens else None,
            "repair_trace": repair_trace,
        },
    )


def make_candidates(
    example: dict[str, Any],
    db_path: Path,
    rows_by_label: dict[str, dict[str, Any]],
    labels: list[str],
    allow_empty_candidates: bool,
    repair_attempts: int,
    repair_empty_results: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_sql: set[str] = set()
    schema_text: str | None = None

    for label in labels:
        row = rows_by_label.get(label)
        if not row:
            continue
        sql = normalize_sql_text(row.get("predicted_sql") or "")
        if not sql or sql in seen_sql:
            continue
        seen_sql.add(sql)

        execution = execute_sql(db_path, sql, read_only=True)
        error = execution.get("error")
        answer = execution.get("answer")
        usable = error is None and (allow_empty_candidates or not is_empty_answer(answer))
        candidate = {
            "label": label,
            "sql": sql,
            "answer": answer,
            "answer_preview": compact_answer(answer),
            "error": error,
            "usable": usable,
            "source_correct": row.get("correct"),
            "source_latency_seconds": row.get("latency_seconds"),
            "source_input_tokens": row.get("input_tokens"),
            "source_output_tokens": row.get("output_tokens"),
            "repair_attempted": False,
            "repair_success": False,
            "repair_attempts_used": 0,
            "repair_latency_seconds": 0.0,
            "repair_input_tokens": None,
            "repair_output_tokens": None,
            "repair_trace": [],
        }
        candidates.append(candidate)

        should_repair = repair_attempts > 0 and not usable and (
            error is not None or (repair_empty_results and is_empty_answer(answer))
        )
        if not should_repair:
            continue

        if schema_text is None:
            schema_text = DBEnvironment(db_path).format_schema()
        repaired, repair_info = repair_sql_candidate(
            example["question"],
            db_path,
            schema_text,
            sql,
            error,
            answer,
            allow_empty_candidates,
            repair_attempts,
        )
        candidate.update(repair_info)
        if repaired is None:
            continue
        repaired_sql = repaired["sql"]
        if not repaired_sql or repaired_sql in seen_sql:
            continue
        seen_sql.add(repaired_sql)
        candidates.append(
            {
                "label": f"{label}__repair",
                "sql": repaired_sql,
                "answer": repaired["answer"],
                "answer_preview": repaired["answer_preview"],
                "error": repaired["error"],
                "usable": repaired["usable"],
                "source_correct": None,
                "source_latency_seconds": None,
                "source_input_tokens": None,
                "source_output_tokens": None,
                "created_by_repair": True,
                "repair_parent_label": label,
                "repair_attempted": False,
                "repair_success": False,
                "repair_attempts_used": 0,
                "repair_latency_seconds": 0.0,
                "repair_input_tokens": None,
                "repair_output_tokens": None,
                "repair_trace": repair_info["repair_trace"],
            }
        )

    return candidates


def build_verifier_prompt(question: str, candidates: list[dict[str, Any]]) -> str:
    candidate_blocks = []
    for index, candidate in enumerate(candidates):
        candidate_blocks.append(
            "\n".join(
                [
                    f"Candidate {index}",
                    f"Source: {candidate['label']}",
                    "SQL:",
                    candidate["sql"],
                    "Execution result preview:",
                    candidate["answer_preview"],
                ]
            )
        )
    return (
        "Question:\n"
        f"{question}\n\n"
        "Choose the SQL candidate that most likely answers the question correctly. "
        "Use the execution result preview, not SQL style, as the main evidence. "
        "If candidates look equally plausible, prefer Candidate 0 because it is the "
        "fast direct text-to-SQL baseline.\n\n"
        + "\n\n".join(candidate_blocks)
        + '\n\nReturn only JSON like {"choice": 0, "reason": "short reason"}.'
    )


def parse_choice(text: str, candidate_count: int) -> tuple[int | None, str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None, cleaned
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None, cleaned

    choice = parsed.get("choice")
    reason = str(parsed.get("reason", ""))
    if isinstance(choice, int) and 0 <= choice < candidate_count:
        return choice, reason
    return None, reason or cleaned


def choose_candidate(
    question: str,
    candidates: list[dict[str, Any]],
) -> tuple[int | None, dict[str, Any]]:
    usable = [candidate for candidate in candidates if candidate["usable"]]
    if not usable:
        return None, {
            "verifier_called": False,
            "selection_reason": "no usable candidate; falling back to first candidate",
            "verifier_response": None,
            "verifier_input_tokens": None,
            "verifier_output_tokens": None,
            "verifier_latency_seconds": 0.0,
        }

    usable_indices = [candidates.index(candidate) for candidate in usable]
    answer_keys = {answer_key(candidate["answer"]) for candidate in usable}
    if len(usable) == 1 or len(answer_keys) == 1:
        return usable_indices[0], {
            "verifier_called": False,
            "selection_reason": "single usable answer or all usable answers agree",
            "verifier_response": None,
            "verifier_input_tokens": None,
            "verifier_output_tokens": None,
            "verifier_latency_seconds": 0.0,
        }

    started = time.perf_counter()
    verifier_candidates = usable
    response = generate_chat(
        [{"role": "user", "content": build_verifier_prompt(question, verifier_candidates)}],
        system_instruction=(
            "You are a careful SQL result verifier. Return only JSON. "
            "Do not reveal hidden reasoning."
        ),
    )
    verifier_latency = round(time.perf_counter() - started, 4)
    local_choice, reason = parse_choice(response.text, len(verifier_candidates))
    if local_choice is None:
        return usable_indices[0], {
            "verifier_called": True,
            "selection_reason": "verifier parse failed; fell back to first usable candidate",
            "verifier_response": response.text,
            "verifier_input_tokens": response.input_tokens,
            "verifier_output_tokens": response.output_tokens,
            "verifier_latency_seconds": verifier_latency,
        }

    return usable_indices[local_choice], {
        "verifier_called": True,
        "selection_reason": reason,
        "verifier_response": response.text,
        "verifier_input_tokens": response.input_tokens,
        "verifier_output_tokens": response.output_tokens,
        "verifier_latency_seconds": verifier_latency,
    }


def numeric_sum(values: list[Any]) -> int | None:
    numeric = [value for value in values if isinstance(value, (int, float))]
    if not numeric:
        return None
    return int(sum(numeric))


def latency_sum(candidates: list[dict[str, Any]], verifier_latency: float) -> float:
    values = [
        candidate.get("source_latency_seconds")
        for candidate in candidates
        if isinstance(candidate.get("source_latency_seconds"), (int, float))
    ]
    repair_values = [
        candidate.get("repair_latency_seconds")
        for candidate in candidates
        if isinstance(candidate.get("repair_latency_seconds"), (int, float))
    ]
    return round(sum(values) + sum(repair_values) + verifier_latency, 4)


def run_one(
    example: dict[str, Any],
    database_dir: Path,
    rows_by_id: dict[str, dict[str, dict[str, Any]]],
    labels: list[str],
    allow_empty_candidates: bool,
    repair_attempts: int,
    repair_empty_results: bool,
) -> dict[str, Any]:
    db_path = get_db_path(database_dir, example["db_id"])
    candidate_rows = rows_by_id.get(str(example["id"]), {})
    candidates = make_candidates(
        example,
        db_path,
        candidate_rows,
        labels,
        allow_empty_candidates,
        repair_attempts,
        repair_empty_results,
    )
    selected_index, decision = choose_candidate(example["question"], candidates)

    if selected_index is None:
        selected = candidates[0] if candidates else {
            "label": "none",
            "sql": "",
            "answer": None,
            "error": "No candidates available",
        }
    else:
        selected = candidates[selected_index]

    gold_exec = execute_sql(db_path, example["gold_sql"], read_only=True)
    predicted_answer = selected.get("answer")
    predicted_error = selected.get("error")
    correct = (
        predicted_error is None
        and gold_exec.get("error") is None
        and is_correct(predicted_answer, gold_exec.get("answer"), gold_sql=example["gold_sql"])
    )

    verifier_input_tokens = decision.get("verifier_input_tokens")
    verifier_output_tokens = decision.get("verifier_output_tokens")
    input_tokens = numeric_sum(
        [candidate.get("source_input_tokens") for candidate in candidates]
        + [candidate.get("repair_input_tokens") for candidate in candidates]
        + [verifier_input_tokens]
    )
    output_tokens = numeric_sum(
        [candidate.get("source_output_tokens") for candidate in candidates]
        + [candidate.get("repair_output_tokens") for candidate in candidates]
        + [verifier_output_tokens]
    )

    return {
        "id": example["id"],
        "method": METHOD_NAME,
        "db_id": example["db_id"],
        "question": example["question"],
        "predicted_sql": selected.get("sql", ""),
        "predicted_answer": predicted_answer,
        "gold_sql": example["gold_sql"],
        "gold_answer": gold_exec.get("answer"),
        "correct": correct,
        "error": predicted_error or gold_exec.get("error"),
        "latency_seconds": latency_sum(candidates, decision["verifier_latency_seconds"]),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "selected_candidate_index": selected_index,
        "selected_candidate_label": selected.get("label"),
        "candidate_count": len(candidates),
        "usable_candidate_count": sum(1 for candidate in candidates if candidate.get("usable")),
        "repair_attempted_count": sum(1 for candidate in candidates if candidate.get("repair_attempted")),
        "repair_success_count": sum(1 for candidate in candidates if candidate.get("repair_success")),
        "candidates": candidates,
        **decision,
        "ablation_config": {
            "candidate_files": labels,
            "allow_empty_candidates": allow_empty_candidates,
            "repair_attempts": repair_attempts,
            "repair_empty_results": repair_empty_results,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run candidate ensemble verifier.")
    parser.add_argument("--dataset", default=str(config.DEFAULT_DATASET_PATH))
    parser.add_argument("--database-dir", default=str(config.DATABASE_DIR))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", default=str(config.RESULTS_DIR / "bird_ours_candidate_ensemble_500.json"))
    parser.add_argument(
        "--candidate-files",
        nargs="+",
        default=[str(path) for path in DEFAULT_CANDIDATE_FILES],
        help="Existing result JSON files to use as SQL candidates, in priority order.",
    )
    parser.add_argument(
        "--allow-empty-candidates",
        action="store_true",
        help="Allow empty-result SQL candidates to be selected by the verifier.",
    )
    parser.add_argument("--model", default=None, help="Override shared.config.MODEL for verifier calls.")
    parser.add_argument(
        "--repair-attempts",
        type=int,
        default=1,
        help="Maximum SQL repair attempts for each unusable candidate. Use 0 to disable.",
    )
    parser.add_argument(
        "--repair-empty-results",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also repair candidates that execute successfully but return an empty result.",
    )
    parser.add_argument("--sleep", type=float, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.model:
        config.MODEL = args.model

    questions = load_questions(args.dataset)
    if args.limit is not None:
        questions = questions[: args.limit]

    candidate_paths = [Path(path) for path in args.candidate_files]
    rows_by_id, labels = load_rows_by_id(candidate_paths)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    done_ids: set[str] = set()
    if output_path.exists():
        results = json.loads(output_path.read_text(encoding="utf-8"))
        done_ids = {str(row["id"]) for row in results}
        print(f"Resuming: {len(done_ids)} already done")

    pending = [question for question in questions if str(question["id"]) not in done_ids]
    print(f"Running {METHOD_NAME} on {len(pending)} questions")
    print(f"Candidate files: {labels}")
    print(f"Output: {output_path}")

    for example in tqdm(pending, desc=METHOD_NAME):
        try:
            results.append(
                run_one(
                    example,
                    Path(args.database_dir),
                    rows_by_id,
                    labels,
                    args.allow_empty_candidates,
                    args.repair_attempts,
                    args.repair_empty_results,
                )
            )
        except KeyboardInterrupt:
            output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\nInterrupted; saved {len(results)} rows to {output_path}")
            raise
        output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.sleep > 0:
            time.sleep(args.sleep)

    total = len(results)
    correct = sum(1 for row in results if row.get("correct") is True)
    accuracy = correct / total if total else 0
    verifier_calls = sum(1 for row in results if row.get("verifier_called"))
    repair_attempts = sum(row.get("repair_attempted_count", 0) for row in results)
    repair_successes = sum(row.get("repair_success_count", 0) for row in results)
    print(f"\nAccuracy: {correct}/{total} = {accuracy:.2%}")
    print(f"Verifier calls: {verifier_calls}/{total}")
    print(f"Repair attempts: {repair_attempts}; repair successes: {repair_successes}")
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
