"""Difference-in-differences for the answer contract, plus the deterministic
checks applied offline to the same samples.

Two questions, one dataset:

1. Does the contract help *by the mechanism it claims*? The 46 questions carry a
   frozen mechanism label (phase_a_mechanism_46.json, written before either arm
   ran). 24 have a contract field that names their failure, 22 do not. If the
   contract works because it makes the requirement explicit, the lift concentrates
   in the 24:

       DiD = [P(correct|contract) - P(correct|plain)]_matched
           - [P(correct|contract) - P(correct|plain)]_unmatched

   Aggregate accuracy cannot answer this on 46 questions -- repeats of the same
   arm differ by 4 questions -- but a difference of differences cancels the noise
   both groups share.

2. What would the deterministic checks add? Every sample carries the SQL it
   submitted and the result it produced, so the checks run offline against the
   stored samples: no extra model call, and the rescue/damage split is measured
   the same way tie_rule_counterfactual_2026-08-25.md measured the tie rule.
   A violation is only counted as a rescue when applying its repair actually
   re-executes into the reference answer.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ours.agent.contract_checks import printf_to_round, violations
from ours.db_environment import get_db_path
from scripts.run_bird_indomain_fewshot import BIRD_DB_DIR
from shared.console import force_utf8_console
from shared.evaluator import is_correct
from shared.sql_executor import execute_sql

_LIMIT_ONE = re.compile(r"\bLIMIT\s+1\b\s*;?\s*$", re.IGNORECASE)


def rate(samples: list[dict]) -> tuple[int, int]:
    ok = sum(1 for s in samples if s.get("correct"))
    valid = sum(1 for s in samples if s.get("correct") is not None)
    return ok, valid


def group_rate(arm: dict, ids: list[str]) -> tuple[float | None, int, int]:
    ok = valid = 0
    for q in ids:
        a, b = rate(arm.get(q, []))
        ok += a
        valid += b
    return (ok / valid if valid else None), ok, valid


def apply_repair(sql: str, kind: str) -> str | None:
    """The mechanical repair a violation suggests, or None if not expressible."""
    if kind == "OUTPUT_TYPE":
        repaired, n = printf_to_round(sql)
        return repaired if n else None
    if kind == "TIES_TRUNCATED":
        repaired, n = _LIMIT_ONE.subn("", sql)
        return repaired.strip() if n else None
    # PERCENT_SCALE has no safe textual repair -- where the x100 belongs depends
    # on the expression, so it is reported and left to the model.
    return None


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm-a", required=True, help="plain arm samples")
    ap.add_argument("--arm-b", required=True, help="contract arm samples")
    ap.add_argument("--split", default=str(PROJECT_ROOT / "docs/analysis/analysisDetail/phase_a_did_split.json"))
    ap.add_argument("--results", default=str(PROJECT_ROOT / "results/e3_c_rules_reasoning_corrected_run1.json"))
    ap.add_argument("--output")
    args = ap.parse_args()

    A = json.loads(Path(args.arm_a).read_text(encoding="utf-8"))
    B = json.loads(Path(args.arm_b).read_text(encoding="utf-8"))
    split = json.loads(Path(args.split).read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}

    shared = sorted(set(A) & set(B))
    matched = [q for q in split["matched"] if q in shared]
    unmatched = [q for q in split["unmatched"] if q in shared]
    print(f"两臂都有样本的题：{len(shared)}（有对应字段 {len(matched)} / 无对应字段 {len(unmatched)}）\n")

    report: dict = {"n_shared": len(shared)}
    print(f'{"组":18s} {"Arm A 原样":>16s} {"Arm B 契约":>16s} {"差":>9s}')
    deltas = {}
    for label, ids in (("有对应字段", matched), ("无对应字段", unmatched), ("全部", shared)):
        ra, oka, va = group_rate(A, ids)
        rb, okb, vb = group_rate(B, ids)
        if ra is None or rb is None:
            continue
        deltas[label] = rb - ra
        print(f"{label:18s} {oka:4d}/{va:<4d} {ra:6.1%} {okb:4d}/{vb:<4d} {rb:6.1%} {rb-ra:+8.1%}")
        report[label] = {"a_ok": oka, "a_valid": va, "b_ok": okb, "b_valid": vb,
                         "a_rate": ra, "b_rate": rb, "delta": rb - ra}
    if "有对应字段" in deltas and "无对应字段" in deltas:
        did = deltas["有对应字段"] - deltas["无对应字段"]
        report["did"] = did
        print(f"\n  DiD = {deltas['有对应字段']:+.1%} - ({deltas['无对应字段']:+.1%}) = {did:+.1%}")

    # --- deterministic checks, offline on the contract arm's own samples ---
    print("\n确定性检查（离线跑在 Arm B 的样本上，不额外调用模型）")
    fired = rescued = damaged = unrepairable = 0
    by_type: dict[str, int] = {}
    detail = []
    for q in shared:
        row = rows.get(q)
        if row is None:
            continue
        db_path = get_db_path(BIRD_DB_DIR, row["db_id"])
        runner = lambda s: execute_sql(db_path, s, read_only=True)
        for s in B.get(q, []):
            sql = s.get("sql")
            if not sql or s.get("correct") is None:
                continue
            executed = execute_sql(db_path, sql, read_only=True)
            hits = violations(s.get("analysis"), sql, executed, execute=runner)
            if not hits:
                continue
            fired += 1
            for v in hits:
                by_type[v["type"]] = by_type.get(v["type"], 0) + 1
            repaired = None
            for v in hits:
                repaired = apply_repair(sql, v["type"])
                if repaired:
                    break
            if not repaired:
                unrepairable += 1
                continue
            after = execute_sql(db_path, repaired, read_only=True)
            now = after.get("error") is None and is_correct(after.get("answer"), row.get("gold_answer"))
            was = bool(s["correct"])
            if now and not was:
                rescued += 1
            elif was and not now:
                damaged += 1
            detail.append({"id": q, "sample": s.get("sample"), "types": [v["type"] for v in hits],
                           "was": was, "now": bool(now)})
    total_scored = sum(rate(B.get(q, []))[1] for q in shared)
    print(f"  触发 {fired} / {total_scored} 个样本（{fired/total_scored*100:.1f}%）  按类型 {by_type}")
    print(f"  机械修复后：救回 {rescued}  打坏 {damaged}  净 {rescued-damaged:+d}  无法机械修复 {unrepairable}")
    report["checks"] = {"fired": fired, "scored": total_scored, "by_type": by_type,
                        "rescued": rescued, "damaged": damaged, "unrepairable": unrepairable,
                        "detail": detail}

    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
