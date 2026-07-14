"""Runtime retrieval for deterministic train-only query-plan constraints."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


VERSION = "train-mined-v2"
_DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "processed" / "e3_f_query_mining_v2.json"
)
_NORMALIZE = {
    "annually": "year", "daily": "day", "monthly": "month", "yearly": "year",
    "averaged": "average", "averages": "average", "counted": "count",
    "percentages": "percentage", "ratios": "ratio", "ranked": "rank",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tokens(text: str) -> list[str]:
    return [
        _NORMALIZE.get(token, token)
        for token in re.findall(r"[a-z0-9]+", text.casefold())
    ]


def _features(text: str) -> set[str]:
    tokens = _tokens(text)
    features = set(tokens)
    for size in (2, 3, 4):
        features.update(
            " ".join(tokens[index:index + size])
            for index in range(max(0, len(tokens) - size + 1))
        )
    if tokens:
        features.add("START:" + tokens[0])
    return features


def _predict(rules: list[dict[str, Any]], features: set[str]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    matches = [rule for rule in rules if rule["feature"] in features]
    matches.sort(key=lambda rule: (
        -int(rule["specificity"]), -float(rule["precision"]),
        -int(rule["support"]), str(rule["feature"]), str(rule["value"]),
    ))
    if not matches:
        return None, []
    best = matches[0]
    peers = [
        rule for rule in matches
        if rule["specificity"] == best["specificity"]
        and rule["precision"] == best["precision"]
        and rule["support"] == best["support"]
    ]
    if len({rule["value"] for rule in peers}) > 1:
        return None, matches
    return {**best, "matched_rule_count": len(matches)}, matches


def _constraint_text(slot: str, value: str) -> str:
    if slot.startswith("aggregate_"):
        return f"Aggregation function: {slot.removeprefix('aggregate_')}."
    if slot == "order_direction":
        return f"Ordering direction: {value}."
    if slot == "output_count":
        label = "at least 2" if value == "2+" else value
        return f"Final SELECT projection count: {label}."
    if slot.startswith("predicate_"):
        return f"Filter operator includes: {slot.removeprefix('predicate_')}."
    if slot == "subquery":
        return "A subquery is likely required by the question form."
    return f"Plan slot {slot}: {value}."


class MinedQueryPatterns:
    """Compatibility name for the v2 mined plan-constraint retriever."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self.path = Path(path).resolve()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("version") != VERSION:
            raise ValueError(f"Unsupported Query Mining artifact: {payload.get('version')!r}")
        self._payload = payload
        self._slots: dict[str, dict[str, Any]] = payload.get("slots", {})

    def retrieve(self, question: str, evidence: str = "") -> list[dict[str, Any]]:
        # Question wording selects plan constraints. Evidence remains authoritative
        # input for SQL generation but is excluded here because it often contains
        # implementation phrases that are not the requested answer structure.
        features = _features(question)
        selected = []
        for slot in sorted(self._slots):
            spec = self._slots[slot]
            if not spec.get("enabled"):
                continue
            prediction, _ = _predict(spec.get("rules", []), features)
            if prediction is None:
                continue
            selected.append({
                "constraint_id": f"{slot}:{prediction['feature']}",
                "slot": slot,
                "value": prediction["value"],
                "matched_feature": prediction["feature"],
                "train_support": prediction["support"],
                "train_precision": prediction["precision"],
                "train_lift": prediction["lift"],
                "validation_precision": spec["validation"]["precision"],
                "validation_coverage": spec["validation"]["coverage"],
                "matched_rule_count": prediction["matched_rule_count"],
                "text": _constraint_text(slot, str(prediction["value"])),
            })
        return selected

    def retrieval_diagnostics(
        self, question: str, evidence: str = "", candidate_limit: int = 5
    ) -> dict[str, Any]:
        features = _features(question)
        selected = self.retrieve(question, evidence)
        selected_by_slot = {item["slot"]: item for item in selected}
        slots = []
        for slot in sorted(self._slots):
            spec = self._slots[slot]
            prediction, matches = _predict(spec.get("rules", []), features)
            if not spec.get("enabled"):
                reason = "failed_train_holdout_precision_gate"
            elif prediction is None and matches:
                reason = "conflicting_equal_rank_rules"
            elif prediction is None:
                reason = "no_validated_rule_match"
            else:
                reason = None
            slots.append({
                "slot": slot,
                "enabled": bool(spec.get("enabled")),
                "validation": spec.get("validation", {}),
                "selected": slot in selected_by_slot,
                "abstention_reason": reason,
                "matching_rule_count": len(matches),
                "top_matching_rules": [
                    {
                        "feature": rule["feature"],
                        "value": rule["value"],
                        "support": rule["support"],
                        "precision": rule["precision"],
                        "lift": rule["lift"],
                    }
                    for rule in matches[:candidate_limit]
                ],
            })
        return {
            "version": VERSION,
            "selection_mode": "independent_validated_slots_with_abstention",
            "question_features": sorted(features),
            "evidence_used_for_retrieval": False,
            "selected_constraint_ids": [item["constraint_id"] for item in selected],
            "selected_constraints": selected,
            "selected_constraint_count": len(selected),
            "abstained": not selected,
            "slots": slots,
        }

    def render(self, question: str, evidence: str = "") -> str:
        selected = self.retrieve(question, evidence)
        if not selected:
            return ""
        lines = [
            "",
            "TRAIN-ONLY MINED PLAN CONSTRAINTS (E3-F V2):",
            "Only high-precision slots that passed a held-out train gate are shown. The current question and Hint remain authoritative.",
        ]
        for item in selected:
            lines.append(
                f"- {item['text']} [matched={item['matched_feature']!r}; "
                f"train support={item['train_support']}; "
                f"held-out precision={item['validation_precision']:.3f}]"
            )
        return "\n".join(lines) + "\n"

    def manifest(self) -> dict[str, Any]:
        return {
            "version": self._payload["version"],
            "path": str(self.path),
            "artifact_sha256": _sha256(self.path),
            "runtime_sha256": _sha256(Path(__file__)),
            "source": self._payload.get("source"),
            "build_config": self._payload.get("build_config"),
            "train_example_count": self._payload.get("train_example_count"),
            "parsed_sql_count": self._payload.get("parsed_sql_count"),
            "build_example_count": self._payload.get("build_example_count"),
            "validation_example_count": self._payload.get("validation_example_count"),
            "enabled_slot_count": self._payload.get("enabled_slot_count"),
            "rule_count": self._payload.get("rule_count"),
            "retrieval": {
                "mode": "independent-validated-plan-slots-with-abstention",
                "conflicting_complete_cards": False,
                "forced_fallback": False,
            },
        }


def get_mined_query_patterns(path: Path = _DEFAULT_PATH) -> MinedQueryPatterns:
    return MinedQueryPatterns(path)
