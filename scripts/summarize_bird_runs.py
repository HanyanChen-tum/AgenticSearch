"""Validate and aggregate repeated traced BIRD experiment runs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.token_usage import summarize_result_usage
from shared.trace_io import load_jsonl, validate_run_pair, write_json


SUMMARY_SCHEMA_VERSION = 1
IGNORED_COMPARISON_CONFIG = {"output"}
OMITTED_REPORT_CONFIG = {"api_base", "api_key"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _comparable_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in config.items()
        if key not in IGNORED_COMPARISON_CONFIG
    }


def _reported_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in _comparable_config(config).items()
        if key not in OMITTED_REPORT_CONFIG
    }


def _mean_std(values: list[float]) -> dict[str, float]:
    return {
        "mean": round(fmean(values), 6) if values else 0,
        "population_stddev": round(pstdev(values), 6) if len(values) > 1 else 0,
    }


def _load_classification(
    path: Path,
    run_id: str,
    failed_ids: set[str],
) -> tuple[Counter, Counter]:
    if not path.exists():
        raise ValueError(f"Missing classification sheet: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row_ids = {row.get("id", "") for row in rows}
    if row_ids != failed_ids:
        raise ValueError(
            f"{path}: failed/classification ID mismatch; "
            f"missing={sorted(failed_ids - row_ids)[:10]} "
            f"extra={sorted(row_ids - failed_ids)[:10]}"
        )
    wrong_runs = sorted({row.get("run_id") for row in rows if row.get("run_id") != run_id})
    if wrong_runs:
        raise ValueError(f"{path}: classification run_id mismatch: {wrong_runs}")
    classes = Counter(row.get("error_class") or "UNCLASSIFIED" for row in rows)
    subcategories = Counter(row.get("subcategory") or "UNCLASSIFIED" for row in rows)
    return classes, subcategories


def _load_run(trace_dir: Path) -> dict[str, Any]:
    trace_dir = trace_dir.resolve()
    manifest_path = trace_dir / "run_manifest.json"
    transcript_path = trace_dir / "transcripts.jsonl"
    classification_path = trace_dir / "classification_sheet.csv"
    if not manifest_path.exists():
        raise ValueError(f"Missing run manifest: {manifest_path}")
    manifest = _read_json(manifest_path)
    if manifest.get("status") != "complete":
        raise ValueError(f"Run is not complete: {manifest_path}")
    config = manifest.get("config") or {}
    output_value = config.get("output")
    if not output_value:
        raise ValueError(f"Manifest has no config.output: {manifest_path}")
    output_path = Path(output_value)
    if not output_path.is_absolute():
        output_path = (PROJECT_ROOT / output_path).resolve()
    if not output_path.exists():
        raise ValueError(f"Missing result file declared by manifest: {output_path}")

    results = _read_json(output_path)
    if not isinstance(results, list):
        raise ValueError(f"Result file must contain a JSON list: {output_path}")
    result_ids = [item.get("id") for item in results]
    if any(not isinstance(item_id, str) for item_id in result_ids):
        raise ValueError(f"Every result requires a string id: {output_path}")
    if len(result_ids) != len(set(result_ids)):
        raise ValueError(f"Duplicate result IDs: {output_path}")
    if not transcript_path.exists():
        raise ValueError(f"Missing transcripts: {transcript_path}")
    traces = load_jsonl(transcript_path)
    run_id, _, trace_map = validate_run_pair(results, traces)
    if run_id != manifest.get("run_id"):
        raise ValueError(f"Manifest/result run_id mismatch: {trace_dir}")
    if manifest.get("completed_questions") != len(results):
        raise ValueError(f"Manifest completed_questions mismatch: {trace_dir}")
    planned = config.get("planned_question_count")
    if planned is not None and planned != len(results):
        raise ValueError(f"Run did not complete its planned question set: {trace_dir}")

    failed_ids = {item["id"] for item in results if not item.get("correct", False)}
    classes, subcategories = _load_classification(
        classification_path, run_id, failed_ids
    )
    usage = summarize_result_usage(results)
    total = len(results)
    correct = total - len(failed_ids)
    db_tool_calls = sum(
        1
        for trace in trace_map.values()
        for event in trace.get("events", [])
        if str(event.get("tool", "")).startswith("db.")
    )
    db_execute_calls = sum(
        1
        for trace in trace_map.values()
        for event in trace.get("events", [])
        if event.get("tool") == "db.execute"
    )
    latency = sum(float(item.get("latency_seconds") or 0) for item in results)
    return {
        "trace_dir": str(trace_dir),
        "result_path": str(output_path),
        "run_id": run_id,
        "config": config,
        "ids": result_ids,
        "correct_by_id": {item["id"]: bool(item.get("correct", False)) for item in results},
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0,
        "latency_seconds": latency,
        "db_tool_calls": db_tool_calls,
        "db_execute_calls": db_execute_calls,
        "token_usage": usage,
        "error_classes": dict(sorted(classes.items())),
        "subcategories": dict(sorted(subcategories.items())),
    }


def build_summary(
    trace_dirs: list[Path],
    *,
    allowed_config_differences: set[str] | None = None,
) -> dict[str, Any]:
    if len(trace_dirs) < 2:
        raise ValueError("At least two --run-dir values are required")
    loaded = [_load_run(path) for path in trace_dirs]
    run_ids = [run["run_id"] for run in loaded]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Each --run-dir must contain an independent run_id")
    expected_ids = loaded[0]["ids"]
    expected_config = _comparable_config(loaded[0]["config"])
    allowed_differences = allowed_config_differences or set()
    observed_differences: set[str] = set()
    for run in loaded[1:]:
        if run["ids"] != expected_ids:
            raise ValueError(
                f"Question IDs or order differ between runs: {run['trace_dir']}"
            )
        config = _comparable_config(run["config"])
        if config != expected_config:
            changed = {
                key
                for key in set(expected_config) | set(config)
                if expected_config.get(key) != config.get(key)
            }
            unexpected = sorted(changed - allowed_differences)
            if unexpected:
                raise ValueError(
                    "Run configurations are not comparable; "
                    f"changed keys: {unexpected}"
                )
            observed_differences.update(changed)

    config_differences = {
        key: [
            {"run_id": run["run_id"], "value": run["config"].get(key)}
            for run in loaded
        ]
        for key in sorted(observed_differences)
    }

    per_question = []
    always_correct, always_failed, unstable = [], [], []
    for item_id in expected_ids:
        outcomes = [run["correct_by_id"][item_id] for run in loaded]
        correct_runs = sum(outcomes)
        per_question.append({
            "id": item_id,
            "correct_runs": correct_runs,
            "total_runs": len(loaded),
            "outcomes": outcomes,
        })
        if correct_runs == len(loaded):
            always_correct.append(item_id)
        elif correct_runs == 0:
            always_failed.append(item_id)
        else:
            unstable.append(item_id)

    transitions = []
    for previous, current in zip(loaded, loaded[1:]):
        recovered = [
            item_id for item_id in expected_ids
            if not previous["correct_by_id"][item_id]
            and current["correct_by_id"][item_id]
        ]
        regressed = [
            item_id for item_id in expected_ids
            if previous["correct_by_id"][item_id]
            and not current["correct_by_id"][item_id]
        ]
        transitions.append({
            "from_run_id": previous["run_id"],
            "to_run_id": current["run_id"],
            "recovered_ids": recovered,
            "regressed_ids": regressed,
        })

    aggregate_classes = Counter()
    aggregate_subcategories = Counter()
    for run in loaded:
        aggregate_classes.update(run["error_classes"])
        aggregate_subcategories.update(run["subcategories"])

    run_reports = []
    for run in loaded:
        total = run["total"]
        usage = run["token_usage"]
        run_reports.append({
            "run_id": run["run_id"],
            "trace_dir": run["trace_dir"],
            "result_path": run["result_path"],
            "correct": run["correct"],
            "total": total,
            "accuracy": round(run["accuracy"], 6),
            "latency_seconds_per_question": round(run["latency_seconds"] / total, 6) if total else 0,
            "llm_calls_per_question": round(usage["llm_calls"] / total, 6) if total else 0,
            "db_tool_calls_per_question": round(run["db_tool_calls"] / total, 6) if total else 0,
            "db_execute_calls_per_question": round(run["db_execute_calls"] / total, 6) if total else 0,
            "token_usage": usage,
            "error_classes": run["error_classes"],
            "subcategories": run["subcategories"],
        })

    return {
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(loaded),
        "question_count": len(expected_ids),
        "config": _reported_config(loaded[0]["config"]),
        "config_differences": config_differences,
        "aggregate": {
            "accuracy": _mean_std([run["accuracy"] for run in loaded]),
            "total_tokens_per_question": _mean_std([
                run["token_usage"]["total_tokens"] / run["total"]
                if run["total"] else 0 for run in loaded
            ]),
            "llm_calls_per_question": _mean_std([
                run["token_usage"]["llm_calls"] / run["total"]
                if run["total"] else 0 for run in loaded
            ]),
            "db_tool_calls_per_question": _mean_std([
                run["db_tool_calls"] / run["total"] if run["total"] else 0
                for run in loaded
            ]),
            "latency_seconds_per_question": _mean_std([
                run["latency_seconds"] / run["total"] if run["total"] else 0
                for run in loaded
            ]),
        },
        "stability": {
            "always_correct_ids": always_correct,
            "always_failed_ids": always_failed,
            "unstable_ids": unstable,
            "per_question": per_question,
        },
        "transitions": transitions,
        "error_classes": {
            "aggregate": dict(sorted(aggregate_classes.items())),
            "subcategories": dict(sorted(aggregate_subcategories.items())),
        },
        "runs": run_reports,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# BIRD 重复运行聚合报告",
        "",
        f"- 运行次数：{summary['run_count']}",
        f"- 题目数：{summary['question_count']}",
        f"- 平均准确率：{summary['aggregate']['accuracy']['mean']:.2%}",
        f"- 准确率总体标准差：{summary['aggregate']['accuracy']['population_stddev']:.2%}",
        "",
    ]
    differences = summary.get("config_differences", {})
    if differences:
        lines.extend([
            "> 注意：该报告包含显式允许的配置差异，只能作为探索性比较。",
            "",
            "## 配置差异",
            "",
        ])
        for key, values in differences.items():
            rendered = ", ".join(
                f"{item['run_id']}={item['value']!r}" for item in values
            )
            lines.append(f"- `{key}`：{rendered}")
        lines.append("")
    lines.extend([
        "## 单次运行",
        "",
        "| Run ID | 正确数 | 准确率 | Tokens/题 | LLM 调用/题 | DB 调用/题 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for run in summary["runs"]:
        lines.append(
            f"| {run['run_id']} | {run['correct']}/{run['total']} | "
            f"{run['accuracy']:.2%} | "
            f"{run['token_usage']['average_per_question']['total_tokens']:.2f} | "
            f"{run['llm_calls_per_question']:.2f} | "
            f"{run['db_tool_calls_per_question']:.2f} |"
        )
    stability = summary["stability"]
    lines.extend([
        "",
        "## 稳定性",
        "",
        f"- 始终正确：{len(stability['always_correct_ids'])}",
        f"- 始终失败：{len(stability['always_failed_ids'])}",
        f"- 结果不稳定：{len(stability['unstable_ids'])}",
        "",
        "## 错误类别",
        "",
        "| 错误类别 | 数量 |",
        "|---|---:|",
    ])
    for name, count in summary["error_classes"]["aggregate"].items():
        lines.append(f"| {name} | {count} |")
    lines.extend(["", "## 相邻运行变化", ""])
    for transition in summary["transitions"]:
        lines.append(
            f"- {transition['from_run_id']} -> {transition['to_run_id']}: "
            f"恢复 {len(transition['recovered_ids'])}，"
            f"退化 {len(transition['regressed_ids'])}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown", default=None)
    parser.add_argument(
        "--allow-config-difference",
        action="append",
        default=[],
        help="Allow and report one known config key difference; repeat as needed.",
    )
    args = parser.parse_args()

    summary = build_summary(
        [Path(value) for value in args.run_dir],
        allowed_config_differences=set(args.allow_config_difference),
    )
    output_path = Path(args.output).resolve()
    write_json(output_path, summary)
    if args.markdown:
        markdown_path = Path(args.markdown).resolve()
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    accuracy = summary["aggregate"]["accuracy"]
    print(
        f"Aggregated {summary['run_count']} runs x {summary['question_count']} questions; "
        f"accuracy={accuracy['mean']:.2%} +/- {accuracy['population_stddev']:.2%}"
    )


if __name__ == "__main__":
    main()
