"""Generate and automatically pre-classify failed trace rows.

Runtime/controller failures come from transcripts. Semantic classes are
deterministic candidates based on predicted/gold SQL structure. Existing
non-empty annotations are preserved unless --overwrite-analysis is passed.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.trace_io import load_jsonl, validate_run_pair


SECONDARY_FIELDS = (
    "control_flow_class",
    "control_flow_subcategory",
    "semantic_error_class",
    "semantic_subcategory",
    "sql_change_type",
    "semantic_fix_idea",
    "semantic_notes",
)
ANALYSIS_FIELDS = (
    "wrong_turn",
    "error_class",
    "subcategory",
    *SECONDARY_FIELDS,
    "fix_idea",
    "notes",
)
FIELDNAMES = ("run_id", "id", "db_id", "difficulty", *ANALYSIS_FIELDS)

SEMANTIC_ERROR_CLASSES = frozenset({
    "AGGREGATION_REASONING",
    "OUTPUT_CONTRACT",
    "SCHEMA_LINKING",
    "SEMANTIC_REVIEW_REQUIRED",
})


def norm(answer):
    if answer is None:
        return None
    return frozenset(tuple(str(value) for value in row) for row in answer)


def official(result: dict[str, Any]) -> bool:
    """Match render_traces: trust the stored official score when present."""
    if "correct" in result:
        return bool(result["correct"])
    return (
        result.get("predicted_answer") is not None
        and result.get("gold_answer") is not None
        and norm(result["predicted_answer"]) == norm(result["gold_answer"])
    )


def normalize_sql(sql: str) -> str:
    text = re.sub(r"\s+", " ", (sql or "").strip().rstrip(";"))
    text = re.sub(r"\s*([(),=<>+*/])\s*", r"\1", text)
    return text.casefold()


class _ExecuteVisitor(ast.NodeVisitor):
    def __init__(self):
        self.sql: list[str] = []

    def visit_Call(self, node):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "execute"
            and isinstance(func.value, ast.Name)
            and func.value.id == "db"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            self.sql.append(node.args[0].value)
        self.generic_visit(node)


def extract_executed_sql(content: str) -> list[str]:
    found: list[str] = []
    for block in re.findall(r"```python\s*(.*?)```", content or "", re.I | re.S):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        visitor = _ExecuteVisitor()
        visitor.visit(tree)
        found.extend(visitor.sql)
    return found


def observation_flags(content: str):
    text = content or ""
    error = None
    for pattern in (
        r"SQL ERROR:\s*([^\r\n]+)",
        r"REPL Error:\s*([^\r\n]+)",
        r"['\"]error['\"]\s*:\s*['\"]([^'\"]+)['\"]",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            error = match.group(1).strip()
            break
    has_rows = bool(re.search(r"['\"]rows['\"]\s*:", text))
    empty = bool(re.search(r"['\"]rows['\"]\s*:\s*\[\]", text)) and error is None
    all_null = bool(re.search(r"all[ -]?null", text, re.I))
    if not all_null and has_rows:
        all_null = bool(
            re.search(r"['\"]rows['\"]\s*:\s*\[\s*\[(?:\s*None\s*,?)+\]\s*\]", text)
        )
    return has_rows and not error and not empty and not all_null, empty, all_null, error


@dataclass(frozen=True)
class Event:
    turn: int
    sql: str
    success: bool
    empty: bool
    all_null: bool
    error: str | None
    rows: Any = None


def trace_events(messages):
    assistants: list[str] = []
    events: list[Event] = []
    pending: list[tuple[int, str]] = []
    for message in messages:
        role, content = message.get("role"), str(message.get("content", ""))
        if role == "assistant":
            assistants.append(content)
            pending = [(len(assistants), sql) for sql in extract_executed_sql(content)]
        elif role == "user" and pending:
            success, empty, all_null, error = observation_flags(content)
            events.extend(Event(turn, sql, success, empty, all_null, error) for turn, sql in pending)
            pending = []
    return assistants, events


def structured_trace_events(transcript):
    events = []
    for item in transcript.get("events", []):
        if item.get("tool") != "db.execute":
            continue
        result = item.get("result") or {}
        rows = result.get("rows")
        error = result.get("error")
        empty = rows == [] and error is None
        all_null = bool(rows) and all(
            all(value is None for value in row) for row in rows
        )
        events.append(Event(
            int(item.get("turn") or 0),
            str((item.get("arguments") or {}).get("sql") or ""),
            rows is not None and error is None and not empty and not all_null,
            empty,
            all_null,
            str(error) if error else None,
            rows,
        ))
    return events


def analysis(turn, error_class, subcategory, fix_idea, notes, confidence):
    rendered_notes = f"[AUTO confidence={confidence}] {notes}"
    result = {
        "wrong_turn": str(turn),
        "error_class": error_class,
        "subcategory": subcategory,
        **{field: "" for field in SECONDARY_FIELDS},
        "fix_idea": fix_idea,
        "notes": rendered_notes,
    }
    if error_class in SEMANTIC_ERROR_CLASSES:
        result.update({
            "semantic_error_class": error_class,
            "semantic_subcategory": subcategory,
            "semantic_fix_idea": fix_idea,
            "semantic_notes": rendered_notes,
        })
    return result


def outer_projection_count(sql: str) -> int | None:
    """Count outer SELECT items while ignoring commas inside expressions."""
    text, depth, quote, select_end = sql or "", 0, None, None
    i = 0
    while i < len(text):
        char = text[i]
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"', chr(96)):
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
                local_depth, local_quote, count = 0, None, 1
                for item in clause:
                    if local_quote:
                        if item == local_quote:
                            local_quote = None
                    elif item in ("'", '"', chr(96)):
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


def tables(sql: str) -> set[str]:
    return {
        match.group(1).strip('`"[]').casefold()
        for match in re.finditer(
            r"\b(?:from|join)\s+([`\"\[]?[A-Za-z_][\w.]*[`\"\]]?)", sql or "", re.I
        )
    }


def semantic_classification(result, turn):
    predicted = str(result.get("predicted_sql") or "")
    gold = str(result.get("gold_sql") or "")
    pred, ref = predicted.casefold(), gold.casefold()
    pred_yes_no = "'yes'" in pred and "'no'" in pred
    gold_yes_no = "'yes'" in ref and "'no'" in ref
    if pred_yes_no != gold_yes_no:
        return analysis(
            turn, "OUTPUT_CONTRACT", "yes_no_vs_row_output_mismatch",
            "在 FINAL 前检查应返回单个 YES/NO 还是逐行原始字段。",
            "预测与 gold 的 YES/NO 输出形式不同；可能包含 gold/Hint 冲突。", "medium",
        )
    pred_count, gold_count = outer_projection_count(predicted), outer_projection_count(gold)
    if pred_count and gold_count and pred_count != gold_count:
        return analysis(
            turn, "OUTPUT_CONTRACT", "output_column_count_mismatch",
            "生成输出契约并检查列数、顺序和每列含义。",
            f"预测列数={pred_count}，gold 列数={gold_count}；需复核 gold 合理性。", "medium",
        )
    aggregate_terms = (" group by ", " having ", "sum(", "avg(", "count(", "min(", "max(", "rank(")
    differences = [term.strip() for term in aggregate_terms if (term in pred) != (term in ref)]
    if differences:
        return analysis(
            turn, "AGGREGATION_REASONING", "aggregation_or_grouping_mismatch",
            "生成 SQL 前明确统计对象、分组键、聚合函数和聚合后的排序字段。",
            f"预测与 gold 的聚合结构不同：{', '.join(differences)}。", "medium",
        )
    pred_order = re.findall(r"\border\s+by\b[^;)]*?\b(asc|desc)\b", pred)
    gold_order = re.findall(r"\border\s+by\b[^;)]*?\b(asc|desc)\b", ref)
    if pred_order != gold_order and (pred_order or gold_order):
        return analysis(
            turn, "AGGREGATION_REASONING", "sort_direction_or_order_scope_mismatch",
            "显式记录排序指标、方向以及排序发生在聚合前还是聚合后。",
            f"排序结构不同：pred={pred_order or ['implicit']}，gold={gold_order or ['implicit']}。", "medium",
        )
    if tables(predicted) != tables(gold):
        return analysis(
            turn, "SCHEMA_LINKING", "table_or_join_path_mismatch",
            "生成 SQL 前记录表、字段来源和 JOIN 路径，并通过 Schema 校验。",
            f"表集合不同：pred={sorted(tables(predicted))}，gold={sorted(tables(gold))}；需复核 gold。", "medium",
        )
    return analysis(
        turn, "SEMANTIC_REVIEW_REQUIRED", "filter_scope_or_expression_mismatch",
        "记录过滤字段、取值、时间范围和作用层级后再生成 SQL。",
        "最终 SQL 已执行成功，但结果与 gold 不同；自动规则未发现更具体结构错误，需复核过滤范围或 gold 噪声。",
        "low",
    )


def sql_change_summary(executed_sql: str, final_sql: str) -> str:
    """Describe structural edits without exposing an entire SQL string in the sheet."""
    before, after = normalize_sql(executed_sql), normalize_sql(final_sql)
    clauses = {
        "tables": tables,
        "WHERE": lambda sql: bool(re.search(r"\bwhere\b", sql, re.I)),
        "GROUP BY": lambda sql: bool(re.search(r"\bgroup\s+by\b", sql, re.I)),
        "HAVING": lambda sql: bool(re.search(r"\bhaving\b", sql, re.I)),
        "ORDER BY": lambda sql: bool(re.search(r"\border\s+by\b", sql, re.I)),
        "LIMIT": lambda sql: bool(re.search(r"\blimit\b", sql, re.I)),
        "aggregate": lambda sql: bool(re.search(r"\b(sum|avg|count|min|max)\s*\(", sql, re.I)),
    }
    changed = [name for name, getter in clauses.items() if getter(before) != getter(after)]
    return ", ".join(changed) if changed else "expression_or_projection_only"


def unverified_final_classification(
    final_turn: int,
    events: list[Event],
    result: dict[str, Any],
):
    """Classify the observation immediately preceding an unexecuted final SQL."""
    final_sql = str(result.get("predicted_sql") or "")
    gold_answer = result.get("gold_answer")
    semantic = semantic_classification(result, final_turn)

    def finish(primary: dict[str, str], change_type: str) -> dict[str, str]:
        primary.update({
            "control_flow_class": primary["error_class"],
            "control_flow_subcategory": primary["subcategory"],
            "semantic_error_class": semantic["error_class"],
            "semantic_subcategory": semantic["subcategory"],
            "sql_change_type": change_type,
            "semantic_fix_idea": semantic["fix_idea"],
            "semantic_notes": semantic["notes"],
        })
        return primary

    if not events:
        return finish(analysis(
            final_turn, "UNVERIFIED_FINAL", "final_without_db_execution",
            "在首次 FINAL 前先执行将要提交的 SQL，并把执行状态写入 trace。",
            "最终 SQL 前没有 db.execute 记录。", "high",
        ), "no_prior_execution")

    last = events[-1]
    changed = sql_change_summary(last.sql, final_sql)
    if last.error:
        subtype = "final_sql_changed_after_sql_error"
        fix = "SQL 报错后若改写 SQL，必须执行改写后的 SQL；不要从错误 observation 直接 FINAL。"
        state = f"SQL ERROR: {last.error}"
    elif last.empty:
        subtype = "final_sql_changed_after_empty_result"
        fix = "空结果后若修改过滤、JOIN 或日期条件，执行改写后的 SQL 后再决定是否 FINAL。"
        state = "0 rows"
    elif last.all_null:
        subtype = "final_sql_changed_after_all_null_result"
        fix = "全 NULL 后若修改字段或 JOIN 路径，执行改写后的 SQL 后再决定是否 FINAL。"
        state = "all NULL"
    elif last.success:
        last_matches_gold = (
            norm(last.rows) == norm(gold_answer)
            if last.rows is not None and gold_answer is not None
            else None
        )
        if last_matches_gold is True:
            subtype = "final_sql_rewritten_after_correct_observation"
        elif last_matches_gold is False:
            subtype = "final_sql_rewritten_after_incorrect_observation"
        else:
            subtype = "final_sql_rewritten_after_successful_observation"
        fix = "成功 observation 后若为了语义改写 SQL，先执行改写版本；记录改写的是投影、过滤、聚合还是排序。"
        state = (
            "successful rows; last execution matches gold"
            if last_matches_gold is True
            else "successful rows; last execution differs from gold"
            if last_matches_gold is False
            else "successful rows; gold comparison unavailable"
        )
    else:
        subtype = "final_sql_changed_after_unparseable_observation"
        fix = "统一工具 observation 格式；无法判断执行状态时不要基于改写 SQL 直接 FINAL。"
        state = "unparseable observation"
    return finish(analysis(
        final_turn, "UNVERIFIED_FINAL", subtype, fix,
        f"最终 SQL 与最近执行 SQL 不同；最近 observation={state}；结构改写={changed}。", "high",
    ), changed)


def classify_failure(result, transcript):
    transcript = transcript or {}
    assistants, legacy_events = trace_events(transcript.get("messages", []))
    events = structured_trace_events(transcript) or legacy_events
    predicted_sql = str(result.get("predicted_sql") or "").strip()
    if not assistants:
        detail = result.get("error") or result.get("termination") or "no assistant message"
        return analysis(
            0, "RUNNER_OR_API", "no_assistant_output",
            "记录 API 异常、重试次数和终止原因，并允许断点重跑。",
            f"轨迹没有 assistant 输出；runner 信息：{detail}。", "high",
        )
    if not predicted_sql:
        return analysis(
            len(assistants), "RUNNER_OR_API", "missing_final_sql",
            "没有有效 FINAL SQL 时自动重试并记录解析错误。",
            "结果文件中的 predicted_sql 为空。", "high",
        )
    target = normalize_sql(predicted_sql)
    matching = [event for event in events if normalize_sql(event.sql) == target]
    final_turn = next(
        (index for index, content in reversed(list(enumerate(assistants, 1))) if "FINAL(" in content),
        len(assistants),
    )
    if not matching:
        return unverified_final_classification(
            final_turn,
            events,
            result,
        )
    successful = [event for event in matching if event.success]
    if successful:
        return semantic_classification(result, successful[0].turn)
    event = matching[-1]
    if event.error:
        lower = event.error.casefold()
        if "no such column" in lower or "no such table" in lower:
            return analysis(
                event.turn, "SCHEMA_LINKING", "unknown_table_or_column",
                "执行前校验表名和列名，并修复 sample_values 对未知列的假阳性。",
                f"最终 SQL 执行失败：{event.error}。", "high",
            )
        if "window function" in lower or "aggregate" in lower or "group" in lower:
            return analysis(
                event.turn, "AGGREGATION_REASONING", "invalid_aggregate_or_window_usage",
                "将窗口函数或聚合放入合法 CTE/子查询层级后再过滤。",
                f"最终 SQL 执行失败：{event.error}。", "high",
            )
        return analysis(
            event.turn, "TOOL_ERROR", "sql_execution_error",
            "根据 SQLite 错误修正 SQL，并在成功执行前禁止 FINAL。",
            f"最终 SQL 执行失败：{event.error}。", "high",
        )
    if event.all_null:
        return analysis(
            event.turn, "EMPTY_OR_NULL_RESULT", "all_null_result",
            "检查字段来源和 JOIN 路径，选择有值字段后重新执行。",
            "最终 SQL 只返回 NULL。", "high",
        )
    if event.empty:
        return analysis(
            event.turn, "EMPTY_OR_NULL_RESULT", "empty_result",
            "检查过滤值、日期格式和 JOIN 条件，得到非空结果后再提交。",
            "最终 SQL 返回 0 行。", "high",
        )
    return analysis(
        event.turn, "TOOL_ERROR", "unparseable_execution_observation",
        "将工具输出改成单一结构化 JSON，并记录每个 SQL 的执行状态。",
        "存在最终 SQL 的执行记录，但无法确认是否执行成功。", "medium",
    )


def load_existing(path: Path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle) if row.get("id")}


def build_rows(
    results,
    transcripts,
    run_id=None,
    existing=None,
    overwrite_analysis=False,
):
    by_id = {item["id"]: item for item in results}  # keep last rerun, like render_traces
    failures = sorted((item for item in by_id.values() if not official(item)), key=lambda x: x["id"])
    existing = existing or {}
    rows = []
    for item in failures:
        old = existing.get(item["id"], {})
        classified = classify_failure(item, transcripts.get(item["id"]))
        same_run = old.get("run_id", "") == (run_id or "")
        if not overwrite_analysis and same_run:
            for field in ANALYSIS_FIELDS:
                if old.get(field):
                    classified[field] = old[field]
        rows.append({
            "run_id": run_id or "",
            "id": str(item["id"]),
            "db_id": str(item.get("db_id", "")),
            "difficulty": str(item.get("difficulty", "")),
            **classified,
        })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--transcripts", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-analysis", action="store_true")
    parser.add_argument(
        "--allow-legacy",
        action="store_true",
        help="allow old artifacts without run_id; ID and final-SQL checks still apply",
    )
    args = parser.parse_args()

    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    trace_records = load_jsonl(Path(args.transcripts))
    run_id, result_map, transcripts = validate_run_pair(
        results,
        trace_records,
        allow_legacy=args.allow_legacy,
    )
    out = Path(args.out)
    rows = build_rows(
        result_map.values(),
        transcripts,
        run_id,
        load_existing(out),
        args.overwrite_analysis,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(row["error_class"] for row in rows)
    print(f"{len(rows)} failures -> {out}")
    print(f"run_id: {run_id or 'legacy'}")
    print(f"classes: {dict(sorted(counts.items()))}")


if __name__ == "__main__":
    main()
