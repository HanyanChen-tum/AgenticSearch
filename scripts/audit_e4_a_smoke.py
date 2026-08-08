"""Fail-closed protocol audit for an E4-A online smoke run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.trace_io import load_jsonl


def audit(trace_dir: Path, expected_count: int) -> dict[str, Any]:
    manifest = json.loads((trace_dir / "run_manifest.json").read_text(encoding="utf-8"))
    config = manifest.get("config") or {}
    agent = config.get("agent_config") or {}
    traces = load_jsonl(trace_dir / "transcripts.jsonl")
    trace_by_id = {str(item.get("id")): item for item in traces}
    failures: list[str] = []

    expected_config = {
        "agent_profile": "e4-a",
        "effective_few_shot_k": 1,
    }
    for key, expected in expected_config.items():
        if config.get(key) != expected:
            failures.append(f"config.{key}={config.get(key)!r}; expected {expected!r}")
    agent_expected = {
        "profile": "e4-a",
        "planner_mode": "root-query-plan-v1",
        "query_pattern_mode": "none",
        "offline_metadata_mode": "e3-f-schema-v4",
        "schema_context_mode": "offline-retrieval",
        "few_shot_mode": "train-retrieval",
    }
    for key, expected in agent_expected.items():
        if agent.get(key) != expected:
            failures.append(f"agent_config.{key}={agent.get(key)!r}; expected {expected!r}")
    plan_manifest = agent.get("query_plan") or {}
    if plan_manifest.get("version") != 3:
        failures.append(
            f"agent_config.query_plan.version={plan_manifest.get('version')!r}; expected 3"
        )
    if config.get("query_pattern_library") is not None:
        failures.append("query_pattern_library must be null")
    if manifest.get("status") != "complete":
        failures.append(f"manifest status is {manifest.get('status')!r}, not 'complete'")
    if manifest.get("completed_questions") != expected_count:
        failures.append(
            f"completed_questions={manifest.get('completed_questions')!r}; expected {expected_count}"
        )
    if len(trace_by_id) != expected_count:
        failures.append(f"unique trace count={len(trace_by_id)}; expected {expected_count}")

    per_question: list[dict[str, Any]] = []
    for item_id, trace in sorted(trace_by_id.items()):
        attempts = trace.get("attempts") or []
        active_trace = attempts[-1] if attempts else trace
        events = active_trace.get("events") or trace.get("events") or []
        initial = [event for event in events if event.get("tool") == "query_plan.initial"]
        invalid_protocol = [
            event for event in events
            if event.get("tool") in {
                "query_plan.initial",
                "query_plan.revision",
                "query_plan.action_contract",
                "query_plan.final_check",
            }
            and not bool((event.get("result") or {}).get("valid"))
        ]
        executions = [event for event in events if event.get("tool") == "db.execute"]
        adherence = [event for event in events if event.get("tool") == "query_plan.adherence"]
        messages = active_trace.get("messages") or trace.get("messages") or []
        observed_refs = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "user"
        )
        missing_refs = [
            int(event.get("sequence") or 0)
            for event in executions
            if f"OBSERVATION_REF {event.get('sequence')} db.execute" not in observed_refs
        ]
        state = active_trace.get("query_plan_state") or trace.get("query_plan_state") or {}
        question_failures: list[str] = []
        if len(initial) != 1 or not bool((initial[0].get("result") or {}).get("valid")):
            question_failures.append("requires exactly one valid initial QueryPlan")
        if invalid_protocol:
            question_failures.append(
                "invalid protocol events: "
                + ", ".join(str(event.get("tool")) for event in invalid_protocol)
            )
        if not executions:
            question_failures.append("no structured db.execute event")
        if len(adherence) != len(executions):
            question_failures.append(
                f"adherence count {len(adherence)} != execution count {len(executions)}"
            )
        if missing_refs:
            question_failures.append(f"observations not returned to model: {missing_refs}")
        if not state.get("initial"):
            question_failures.append("query_plan_state.initial missing")
        if trace.get("termination") != "final":
            question_failures.append(f"termination={trace.get('termination')!r}")
        if question_failures:
            failures.extend(f"{item_id}: {message}" for message in question_failures)
        per_question.append({
            "id": item_id,
            "executions": len(executions),
            "revisions": len(state.get("revisions") or []),
            "adherence_pass": sum(
                1 for event in adherence
                if bool((event.get("result") or {}).get("passed"))
            ),
            "adherence_fail": sum(
                1 for event in adherence
                if (event.get("result") or {}).get("passed") is False
            ),
            "protocol_failures": question_failures,
        })

    required_artifacts = [
        "classification_sheet.csv",
        "retrieval_audit.csv",
        "retrieval_audit.json",
        "trajectory_audit_summary.csv",
        "trajectory_audit_steps.csv",
        "trajectory_audit.json",
    ]
    missing_artifacts = [name for name in required_artifacts if not (trace_dir / name).exists()]
    if missing_artifacts:
        failures.append("missing post-run artifacts: " + ", ".join(missing_artifacts))

    return {
        "passed": not failures,
        "trace_dir": str(trace_dir.resolve()),
        "expected_count": expected_count,
        "per_question": per_question,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=4)
    args = parser.parse_args()
    report = audit(args.trace_dir.resolve(), args.expected_count)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
