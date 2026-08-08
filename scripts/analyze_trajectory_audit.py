"""Build an observable state-transition audit for a traced Text-to-SQL run.

This script does not claim access to the model's hidden chain of thought.  It
audits the observable process: retrieved context, executed SQL/results, SQL
rewrites, and FINAL submission.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


def canonical(value: Any) -> Any:
    if isinstance(value, list):
        rows = [canonical(item) for item in value]
        try:
            return sorted(rows, key=lambda item: json.dumps(item, sort_keys=True))
        except TypeError:
            return rows
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    if isinstance(value, float):
        return round(value, 8)
    return value


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", (sql or "").strip().rstrip(";")).casefold()


def tables(sql: str) -> list[str]:
    return sorted({
        match.group(1).strip('`"[]').casefold()
        for match in re.finditer(
            r"\b(?:from|join)\s+([`\"\[]?[A-Za-z_][\w.]*[`\"\]]?)",
            sql or "",
            re.I,
        )
    })


def projection_count(sql: str) -> int | None:
    text = sql or ""
    depth = 0
    quote: str | None = None
    select_end: int | None = None
    i = 0
    while i < len(text):
        char = text[i]
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"', "`"):
            quote = char
        elif char == "[":
            quote = "]"
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and (char.isalpha() or char == "_"):
            end = i + 1
            while end < len(text) and (text[end].isalnum() or text[end] == "_"):
                end += 1
            word = text[i:end].casefold()
            if word == "select":
                select_end = end
            elif word == "from" and select_end is not None:
                clause = text[select_end:i]
                local_depth = 0
                local_quote: str | None = None
                count = 1
                for item in clause:
                    if local_quote:
                        if item == local_quote:
                            local_quote = None
                    elif item in ("'", '"', "`"):
                        local_quote = item
                    elif item == "[":
                        local_quote = "]"
                    elif item == "(":
                        local_depth += 1
                    elif item == ")":
                        local_depth = max(0, local_depth - 1)
                    elif item == "," and local_depth == 0:
                        count += 1
                return count
            i = end - 1
        i += 1
    return None


def features(sql: str) -> dict[str, Any]:
    lowered = f" {normalize_sql(sql)} "
    return {
        "tables": tables(sql),
        "projection_count": projection_count(sql),
        "where": bool(re.search(r"\bwhere\b", lowered)),
        "group_by": bool(re.search(r"\bgroup\s+by\b", lowered)),
        "having": bool(re.search(r"\bhaving\b", lowered)),
        "order_by": bool(re.search(r"\border\s+by\b", lowered)),
        "limit": bool(re.search(r"\blimit\b", lowered)),
        "aggregate": bool(re.search(r"\b(sum|avg|count|min|max)\s*\(", lowered)),
        "distinct": bool(re.search(r"\bdistinct\b", lowered)),
    }


def sql_delta(before: str | None, after: str) -> str:
    if not before:
        return "initial_sql"
    if normalize_sql(before) == normalize_sql(after):
        return "unchanged"
    old, new = features(before), features(after)
    labels: list[str] = []
    if old["tables"] != new["tables"]:
        labels.append("tables_or_join")
    if old["projection_count"] != new["projection_count"]:
        labels.append("projection_count")
    for key in ("where", "group_by", "having", "order_by", "limit", "aggregate", "distinct"):
        if old[key] != new[key]:
            labels.append(key)
    return ",".join(labels) if labels else "expression_or_projection"


def observation_state(result: dict[str, Any], gold_answer: Any) -> tuple[str, str]:
    error = result.get("error")
    rows = result.get("rows")
    if error:
        return "execution_error", "unknown"
    if rows is None:
        return "unparseable", "unknown"
    matches = canonical(rows) == canonical(gold_answer)
    if matches:
        return "matches_gold", "true"
    if rows == []:
        return "empty_nonmatching", "false"
    if rows and all(all(value is None for value in row) for row in rows):
        return "all_null_nonmatching", "false"
    return "nonmatching", "false"


def transition(previous: str | None, current: str) -> str:
    correct = current == "matches_gold"
    known_wrong = current in {"nonmatching", "empty_nonmatching", "all_null_nonmatching"}
    if previous is None:
        if correct:
            return "initial_execution_correct"
        if known_wrong:
            return "initial_execution_nonmatching"
        return "initial_execution_unresolved"
    previous_correct = previous == "matches_gold"
    previous_wrong = previous in {"nonmatching", "empty_nonmatching", "all_null_nonmatching"}
    if previous_correct and correct:
        return "remained_correct"
    if previous_correct and not correct:
        return "regressed_after_correct_execution"
    if previous_wrong and correct:
        return "recovered_to_correct_execution"
    if previous_wrong and known_wrong:
        return "remained_nonmatching"
    if correct:
        return "resolved_to_correct_execution"
    if known_wrong:
        return "resolved_to_nonmatching_execution"
    if previous_correct:
        return "unresolved_after_correct_execution"
    if previous_wrong:
        return "unresolved_after_nonmatching_execution"
    return "remained_unresolved"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcripts", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--retrieval-audit", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()

    results = {item["id"]: item for item in load_json(args.results)}
    classifications = load_csv_by_id(args.classification)
    retrieval = load_csv_by_id(args.retrieval_audit)
    transcripts: dict[str, dict[str, Any]] = {}
    with args.transcripts.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            item = json.loads(line)
            transcripts[item["id"]] = item

    summaries: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    detailed: list[dict[str, Any]] = []

    for item_id, result in results.items():
        if result.get("correct"):
            continue
        transcript = transcripts[item_id]
        classification = classifications[item_id]
        audit = retrieval[item_id]
        gold_answer = result.get("gold_answer")
        all_events = sorted(
            transcript.get("events", []),
            key=lambda event: (event.get("sequence", 0), event.get("turn", 0)),
        )
        events = [event for event in all_events if event.get("tool") == "db.execute"]
        plan_events = [
            event for event in all_events
            if str(event.get("tool", "")).startswith("query_plan.")
        ]
        previous_state: str | None = None
        previous_sql: str | None = None
        first_nonmatching_turn: int | None = None
        first_correct_turn: int | None = None
        recoveries = 0
        regressions = 0
        event_rows: list[dict[str, Any]] = []
        first_nonmatching_seen = False

        for event in plan_events:
            tool = str(event.get("tool", ""))
            event_result = event.get("result") or {}
            if tool == "query_plan.adherence":
                state = "adherence_passed" if event_result.get("passed") else "adherence_failed"
            else:
                state = "plan_valid" if event_result.get("valid") else "plan_invalid"
            event_rows.append({
                "run_id": result.get("run_id", ""),
                "id": item_id,
                "db_id": result.get("db_id", ""),
                "difficulty": result.get("difficulty", ""),
                "step_index": 0,
                "event_sequence": event.get("sequence", 0),
                "turn": event.get("turn", 0),
                "action_type": tool,
                "sql": str((event.get("arguments") or {}).get("sql") or ""),
                "tables": "[]",
                "projection_count": "",
                "sql_delta_from_previous": "not_applicable",
                "observation_state": state,
                "result_matches_gold": "unknown",
                "transition_type": tool,
                "is_first_nonmatching_execution": "false",
                "retrieval_diagnostic": audit.get("diagnostic", ""),
                "semantic_error_class": classification.get("semantic_error_class") or classification.get("error_class", ""),
                "semantic_subcategory": classification.get("semantic_subcategory") or classification.get("subcategory", ""),
                "state_payload": json.dumps(event_result, ensure_ascii=False),
            })

        for index, event in enumerate(events, start=1):
            event_result = event.get("result") or {}
            state, matches = observation_state(event_result, gold_answer)
            change = transition(previous_state, state)
            is_first_nonmatching = matches == "false" and not first_nonmatching_seen
            if is_first_nonmatching:
                first_nonmatching_turn = int(event.get("turn") or 0)
                first_nonmatching_seen = True
            if matches == "true" and first_correct_turn is None:
                first_correct_turn = int(event.get("turn") or 0)
            if change in {"recovered_to_correct_execution", "resolved_to_correct_execution"}:
                recoveries += 1
            if change == "regressed_after_correct_execution":
                regressions += 1
            sql = str((event.get("arguments") or {}).get("sql") or "")
            row = {
                "run_id": result.get("run_id", ""),
                "id": item_id,
                "db_id": result.get("db_id", ""),
                "difficulty": result.get("difficulty", ""),
                "step_index": 0,
                "event_sequence": event.get("sequence", 0),
                "turn": event.get("turn", 0),
                "action_type": "db.execute",
                "sql": sql,
                "tables": json.dumps(tables(sql), ensure_ascii=False),
                "projection_count": projection_count(sql) or "",
                "sql_delta_from_previous": sql_delta(previous_sql, sql),
                "observation_state": state,
                "result_matches_gold": matches,
                "transition_type": change,
                "is_first_nonmatching_execution": str(is_first_nonmatching).lower(),
                "retrieval_diagnostic": audit.get("diagnostic", ""),
                "semantic_error_class": classification.get("semantic_error_class") or classification.get("error_class", ""),
                "semantic_subcategory": classification.get("semantic_subcategory") or classification.get("subcategory", ""),
                "state_payload": "",
            }
            event_rows.append(row)
            previous_state, previous_sql = state, sql

        final_sql = str(result.get("predicted_sql") or transcript.get("final_sql") or "")
        final_same = bool(previous_sql) and normalize_sql(previous_sql) == normalize_sql(final_sql)
        if not events:
            terminal = "final_without_execution"
        elif final_same:
            terminal = "final_same_as_last_execution"
        elif previous_state == "matches_gold":
            terminal = "harmful_unverified_rewrite_after_correct_execution"
        elif previous_state in {"nonmatching", "empty_nonmatching", "all_null_nonmatching"}:
            terminal = "unverified_rewrite_after_nonmatching_execution"
        else:
            terminal = "unverified_rewrite_after_unresolved_execution"

        final_row = {
            "run_id": result.get("run_id", ""),
            "id": item_id,
            "db_id": result.get("db_id", ""),
            "difficulty": result.get("difficulty", ""),
            "step_index": 0,
            "event_sequence": max(
                [int(event.get("sequence") or 0) for event in all_events] or [0]
            ) + 1,
            "turn": classification.get("wrong_turn", ""),
            "action_type": "FINAL",
            "sql": final_sql,
            "tables": json.dumps(tables(final_sql), ensure_ascii=False),
            "projection_count": projection_count(final_sql) or "",
            "sql_delta_from_previous": sql_delta(previous_sql, final_sql),
            "observation_state": "benchmark_nonmatching_final",
            "result_matches_gold": "false",
            "transition_type": terminal,
            "is_first_nonmatching_execution": "false",
            "retrieval_diagnostic": audit.get("diagnostic", ""),
            "semantic_error_class": classification.get("semantic_error_class") or classification.get("error_class", ""),
            "semantic_subcategory": classification.get("semantic_subcategory") or classification.get("subcategory", ""),
            "state_payload": "",
        }
        event_rows.append(final_row)
        event_rows.sort(key=lambda row: int(row["event_sequence"] or 0))
        for step_index, row in enumerate(event_rows, start=1):
            row["step_index"] = step_index
        steps.extend(event_rows)

        retrieval_miss = audit.get("diagnostic", "") in {
            "detailed_schema_column_miss_or_compact_index_only",
            "detailed_schema_table_miss",
        }
        if retrieval_miss:
            earliest_stage = "retrieval_context_risk"
            earliest_turn: int | str = 0
            confidence = "medium_risk_not_proven_causal"
        elif first_nonmatching_turn is not None:
            earliest_stage = "first_nonmatching_execution"
            earliest_turn = first_nonmatching_turn
            confidence = "medium_candidate_may_be_exploratory"
        elif not events:
            earliest_stage = "direct_final_without_execution"
            earliest_turn = classification.get("wrong_turn", "")
            confidence = "high"
        else:
            earliest_stage = "unresolved_execution_or_final_rewrite"
            earliest_turn = classification.get("wrong_turn", "")
            confidence = "medium"

        summary = {
            "run_id": result.get("run_id", ""),
            "id": item_id,
            "db_id": result.get("db_id", ""),
            "difficulty": result.get("difficulty", ""),
            "retrieval_diagnostic": audit.get("diagnostic", ""),
            "execution_count": len(events),
            "first_nonmatching_execution_turn": first_nonmatching_turn or "",
            "first_correct_execution_turn": first_correct_turn or "",
            "ever_executed_gold_matching_result": str(first_correct_turn is not None).lower(),
            "recovery_transition_count": recoveries,
            "regression_transition_count": regressions,
            "last_execution_state": previous_state or "none",
            "final_matches_last_executed_sql": str(final_same).lower(),
            "terminal_transition": terminal,
            "earliest_observable_problem_stage": earliest_stage,
            "earliest_observable_problem_turn": earliest_turn,
            "onset_confidence": confidence,
            "query_plan_initial_valid": str(any(
                event.get("tool") == "query_plan.initial"
                and bool((event.get("result") or {}).get("valid"))
                for event in plan_events
            )).lower(),
            "query_plan_invalid_initial_count": sum(
                1 for event in plan_events
                if event.get("tool") == "query_plan.initial"
                and not bool((event.get("result") or {}).get("valid"))
            ),
            "query_plan_revision_count": sum(
                1 for event in plan_events
                if event.get("tool") == "query_plan.revision"
                and bool((event.get("result") or {}).get("valid"))
            ),
            "query_plan_invalid_revision_count": sum(
                1 for event in plan_events
                if event.get("tool") == "query_plan.revision"
                and not bool((event.get("result") or {}).get("valid"))
            ),
            "query_plan_adherence_pass_count": sum(
                1 for event in plan_events
                if event.get("tool") == "query_plan.adherence"
                and bool((event.get("result") or {}).get("passed"))
            ),
            "query_plan_adherence_fail_count": sum(
                1 for event in plan_events
                if event.get("tool") == "query_plan.adherence"
                and (event.get("result") or {}).get("passed") is False
            ),
            "primary_trace_class": classification.get("error_class", ""),
            "primary_trace_subcategory": classification.get("subcategory", ""),
            "semantic_error_class": classification.get("semantic_error_class") or classification.get("error_class", ""),
            "semantic_subcategory": classification.get("semantic_subcategory") or classification.get("subcategory", ""),
        }
        summaries.append(summary)
        detailed.append({"summary": summary, "steps": event_rows})

    prefix = args.output_prefix
    write_csv(prefix.with_name(prefix.name + "_summary.csv"), summaries)
    write_csv(prefix.with_name(prefix.name + "_steps.csv"), steps)
    with prefix.with_suffix(".json").open("w", encoding="utf-8") as handle:
        json.dump(detailed, handle, ensure_ascii=False, indent=2)

    print(f"failures={len(summaries)} steps={len(steps)}")
    print("earliest_stage", dict(Counter(row["earliest_observable_problem_stage"] for row in summaries)))
    print("terminal", dict(Counter(row["terminal_transition"] for row in summaries)))
    print("ever_correct", dict(Counter(row["ever_executed_gold_matching_result"] for row in summaries)))


if __name__ == "__main__":
    main()
