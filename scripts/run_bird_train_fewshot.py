"""DB-RLM with few-shot retrieval from the BIRD TRAIN split (k=3, gold SQL).

Same agent as run_bird_indomain_fewshot; only the retrieval pool changes:
official train examples instead of our own correctly-answered dev questions.
Teaches gold SQL conventions (IIF yes/no answers, output-column choices,
multi-part SELECTs) without dev-set leakage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from scripts.run_bird_indomain_fewshot import InDomainFewShotDBRLM, run_one
from ours.train_few_shot_retriever import (
    get_train_retriever,
    get_train_retriever_manifest,
)
from ours.agent.config import agent_profile_names, get_agent_config
from ours.agent.query_patterns import get_train_query_pattern_manifest
from ours.agent.query_mining import get_mined_query_patterns
from ours.agent.offline_metadata import get_offline_metadata
from shared.trace_io import TRACE_SCHEMA_VERSION, append_jsonl, load_jsonl, write_json
from shared.token_usage import summarize_result_usage
from shared.llm_config import resolve_llm_config
from shared.sql_executor import DEFAULT_QUERY_TIMEOUT_SECONDS

BIRD_DB_DIR  = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"
BIRD_DATASET = PROJECT_ROOT / "data/processed/bird_dev_500.json"


def _dataset_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_question_ids(
    path: Path,
    groups: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Load a flat ID list or selected lists from a named-group object."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    selected_groups: list[str] = []
    if isinstance(raw, list):
        if groups:
            raise ValueError("--id-groups requires an object-valued --ids-file")
        values = raw
    elif isinstance(raw, dict):
        selected_groups = groups or list(raw)
        unknown_groups = [name for name in selected_groups if name not in raw]
        if unknown_groups:
            raise ValueError(
                f"Unknown ID groups {unknown_groups}; available groups: {list(raw)}"
            )
        values = []
        for name in selected_groups:
            group_values = raw[name]
            if not isinstance(group_values, list):
                raise ValueError(f"ID group {name!r} must be a JSON list")
            values.extend(group_values)
    else:
        raise ValueError("--ids-file must contain a JSON list or object of lists")

    invalid = [value for value in values if not isinstance(value, str) or not value]
    if invalid:
        raise ValueError(f"Question IDs must be non-empty strings: {invalid[:10]}")
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise ValueError(f"Duplicate question IDs in --ids-file: {duplicates[:10]}")
    if not values:
        raise ValueError("--ids-file selected zero question IDs")
    return values, selected_groups


def _select_questions(
    questions: list[dict],
    question_ids: list[str],
) -> list[dict]:
    """Select requested IDs while preserving canonical dataset order."""
    requested = set(question_ids)
    selected: list[dict] = []
    selected_by_id: dict[str, dict] = {}
    dataset_ids: set[str] = set()
    for index, question in enumerate(questions):
        if not isinstance(question, dict) or not isinstance(question.get("id"), str):
            raise ValueError(f"Dataset item {index} is missing a string id")
        item_id = question["id"]
        dataset_ids.add(item_id)
        if item_id not in requested:
            continue
        existing = selected_by_id.get(item_id)
        if existing is not None:
            if existing != question:
                raise ValueError(
                    f"Dataset contains conflicting records for requested ID {item_id}"
                )
            continue
        selected_by_id[item_id] = question
        selected.append(question)

    missing = sorted(requested - dataset_ids)
    if missing:
        raise ValueError(f"--ids-file contains IDs absent from dataset: {missing[:10]}")
    return selected


def _prepare_run(
    manifest_path: Path,
    output_path: Path,
    transcript_path: Path,
    config: dict,
) -> tuple[str, dict]:
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("trace_schema_version") != TRACE_SCHEMA_VERSION:
            raise ValueError(
                "Trace directory uses an older schema without complete token usage. "
                "Use a new --output or --trace-dir."
            )
        if manifest.get("config") != config:
            previous = manifest.get("config", {})
            changed = sorted({
                key
                for key in set(previous) | set(config)
                if previous.get(key) != config.get(key)
            })
            raise ValueError(
                "Trace directory belongs to a different configuration. "
                f"Changed fields: {', '.join(changed)}. "
                "Use a new --output or --trace-dir."
            )
        return manifest["run_id"], manifest

    existing_results = (
        json.loads(output_path.read_text(encoding="utf-8"))
        if output_path.exists()
        else []
    )
    if existing_results or transcript_path.exists():
        raise ValueError(
            "Existing results/transcripts have no run_manifest.json. "
            "Use a new output path; legacy artifacts are not mixed into a traced run."
        )
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    manifest = {
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "completed_questions": 0,
        "config": config,
    }
    write_json(manifest_path, manifest)
    return run_id, manifest


def _resolve_train_few_shot(
    agent_config: object,
    requested_k: int,
) -> tuple[bool, int, dict]:
    """Resolve profile-controlled train few-shot use without loading embeddings."""
    mode = getattr(agent_config, "few_shot_mode", None)
    if mode == "train-retrieval":
        return True, requested_k, {
            "enabled": True,
            "mode": mode,
            "requested_k": requested_k,
            "effective_k": requested_k,
            **get_train_retriever_manifest(),
        }
    if mode == "none":
        return False, 0, {
            "enabled": False,
            "mode": mode,
            "requested_k": requested_k,
            "effective_k": 0,
            "source_split": None,
            "pool_path": None,
            "pool_sha256": None,
        }
    raise ValueError(f"Unsupported train few-shot mode: {mode!r}")


def _query_pattern_manifest(agent_config: object) -> dict | None:
    mode = getattr(agent_config, "query_pattern_mode", None)
    if mode == "none":
        return None
    if mode == "train-static-v1":
        return get_train_query_pattern_manifest()
    if mode in {"train-mined-v1", "train-mined-v2"}:
        return get_mined_query_patterns().manifest()
    raise ValueError(f"Unsupported query pattern mode: {mode!r}")


def _offline_metadata_manifest(agent_config: object) -> dict | None:
    mode = getattr(agent_config, "offline_metadata_mode", "none")
    if mode == "none":
        return None
    if mode in {"e3-c-metadata-v1", "e3-c-metadata-v2", "e3-f-schema-v3", "e3-f-schema-v4"}:
        version = "e3-c-metadata-v2" if mode == "e3-c-metadata-v1" else mode
        return get_offline_metadata(version).manifest()
    raise ValueError(f"Unsupported offline metadata mode: {mode!r}")


def _run_trace_analysis(
    output_path: Path,
    transcript_path: Path,
    trace_dir: Path,
) -> None:
    commands = [
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/render_traces.py"),
            "--transcripts", str(transcript_path),
            "--results", str(output_path),
            "--out", str(trace_dir / "traces_report.html"),
        ],
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/make_classification_sheet.py"),
            "--transcripts", str(transcript_path),
            "--results", str(output_path),
            "--out", str(trace_dir / "classification_sheet.csv"),
            "--overwrite-analysis",
        ],
    ]
    for command in commands:
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset",        default=str(BIRD_DATASET))
    parser.add_argument("--database-dir",   default=str(BIRD_DB_DIR))
    parser.add_argument("--output",         default=str(PROJECT_ROOT / "results/bird_train_fewshot.json"))
    parser.add_argument(
        "--ids-file",
        default=None,
        help="JSON list of question IDs or object whose values are ID lists",
    )
    parser.add_argument(
        "--id-groups",
        nargs="+",
        default=None,
        help="named groups to use from an object-valued --ids-file; default: all",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LiteLLM model; default resolves from MODEL or Azure deployment",
    )
    parser.add_argument("--limit",          type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--k",              type=int, default=3)
    parser.add_argument("--temperature",    type=float, default=0)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument(
        "--agent-profile",
        choices=agent_profile_names(),
        default="clean-e0",
        help="controlled agent profile; legacy-e0 is for historical reproduction only",
    )
    parser.add_argument(
        "--trace-dir",
        default=None,
        help="default: trace/<output filename without .json>",
    )
    parser.add_argument("--skip-trace-analysis", action="store_true")
    args = parser.parse_args()

    dataset_path = Path(args.dataset).resolve()
    database_dir = Path(args.database_dir).resolve()
    output_path = Path(args.output).resolve()
    ids_path = Path(args.ids_file).resolve() if args.ids_file else None
    if args.id_groups and ids_path is None:
        parser.error("--id-groups requires --ids-file")
    questions = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(questions, list):
        raise ValueError("--dataset must contain a JSON list")
    selected_groups: list[str] = []
    if ids_path:
        question_ids, selected_groups = _load_question_ids(ids_path, args.id_groups)
        questions = _select_questions(questions, question_ids)
    selected_question_count = len(questions)
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be at least 1")
        questions = questions[:args.limit]
    trace_dir = (
        Path(args.trace_dir).resolve()
        if args.trace_dir
        else PROJECT_ROOT / "trace" / output_path.stem
    )
    transcript_path = trace_dir / "transcripts.jsonl"
    manifest_path = trace_dir / "run_manifest.json"
    llm_config = resolve_llm_config(args.model)
    agent_config = get_agent_config(args.agent_profile)
    use_train_few_shot, effective_k, retriever_manifest = _resolve_train_few_shot(
        agent_config,
        args.k,
    )
    query_pattern_manifest = _query_pattern_manifest(agent_config)
    offline_metadata_manifest = _offline_metadata_manifest(agent_config)
    config = {
        "dataset": str(dataset_path),
        "dataset_sha256": _dataset_digest(dataset_path),
        "ids_file": str(ids_path) if ids_path else None,
        "ids_file_sha256": _dataset_digest(ids_path) if ids_path else None,
        "id_groups": selected_groups,
        "selected_question_count": selected_question_count,
        "planned_question_count": len(questions),
        "database_dir": str(database_dir),
        "output": str(output_path),
        "model": llm_config.model,
        "api_base": llm_config.api_base,
        "api_version": llm_config.api_version,
        "limit": args.limit,
        "max_iterations": args.max_iterations,
        "k": args.k,
        "effective_few_shot_k": effective_k,
        "temperature": args.temperature,
        "reasoning_effort": args.reasoning_effort,
        "evaluation_sql_timeout_seconds": DEFAULT_QUERY_TIMEOUT_SECONDS,
        "agent_profile": args.agent_profile,
        "agent_config": agent_config.to_manifest(),
        "agent_config_sha256": agent_config.sha256,
        "few_shot_retriever": retriever_manifest,
        "query_pattern_library": query_pattern_manifest,
        "offline_metadata": offline_metadata_manifest,
    }
    run_id, manifest = _prepare_run(
        manifest_path,
        output_path,
        transcript_path,
        config,
    )
    retriever = get_train_retriever() if use_train_few_shot else None

    extra = {}
    if args.reasoning_effort:
        extra["reasoning_effort"] = args.reasoning_effort
    if llm_config.api_version:
        extra["api_version"] = llm_config.api_version

    agent = InDomainFewShotDBRLM(
        model=llm_config.model,
        api_key=llm_config.api_key,
        api_base=llm_config.api_base,
        max_iterations=args.max_iterations,
        temperature=args.temperature,
        retriever=retriever,
        k=effective_k,
        agent_config=agent_config,
        **extra,
    )

    results = []
    done_ids = set()
    if output_path.exists():
        results = json.loads(output_path.read_text(encoding="utf-8"))
        if any(item.get("run_id") != run_id for item in results):
            raise ValueError("Existing result records do not match run_manifest.json")
        done_ids = {r["id"] for r in results}
        print(f"Resuming — {len(done_ids)} already done")
    trace_records = load_jsonl(transcript_path) if transcript_path.exists() else []
    if any(item.get("run_id") != run_id for item in trace_records):
        raise ValueError("Existing transcript records do not match run_manifest.json")
    trace_ids = {item["id"] for item in trace_records}
    if not done_ids.issubset(trace_ids):
        raise ValueError("Results contain questions without matching transcript records")

    questions = [q for q in questions if q["id"] not in done_ids]
    if use_train_few_shot:
        print(f"Running {len(questions)} questions with k={effective_k} TRAIN examples")
    else:
        print(f"Running {len(questions)} questions without TRAIN few-shot examples")

    interrupted = False
    for ex in tqdm(questions, desc="BIRD-TrainFewShot"):
        try:
            record = run_one(ex, database_dir, agent, capture_trace=True)
        except KeyboardInterrupt:
            print(f"\nInterrupted — {len(results)} saved")
            interrupted = True
            break
        trace = record.pop("_trace")
        record["run_id"] = run_id
        record["trace_schema_version"] = TRACE_SCHEMA_VERSION
        record["agent_profile"] = args.agent_profile
        record["agent_config_sha256"] = agent_config.sha256
        trace_record = {
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "run_id": run_id,
            "id": record["id"],
            "db_id": record["db_id"],
            "question": record["question"],
            "final_sql": record["predicted_sql"],
            "termination": record["termination"],
            **trace,
        }
        # Trace first: if the process dies before results are replaced, the
        # question is rerun and the last JSONL record wins.
        append_jsonl(transcript_path, trace_record)
        results.append(record)
        write_json(output_path, results)
        manifest["completed_questions"] = len(results)
        manifest["token_usage"] = summarize_result_usage(results)
        write_json(manifest_path, manifest)

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    if total:
        print(f"\nAccuracy: {correct}/{total} = {correct/total:.2%}")
    manifest["status"] = "interrupted" if interrupted else "complete"
    manifest["completed_questions"] = total
    manifest["token_usage"] = summarize_result_usage(results)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(manifest_path, manifest)
    if total and not args.skip_trace_analysis:
        _run_trace_analysis(output_path, transcript_path, trace_dir)
        print(f"Trace artifacts: {trace_dir}")


if __name__ == "__main__":
    main()
