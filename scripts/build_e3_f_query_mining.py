"""Build deterministic, train-only query-plan constraints for E3-F.

The v1 artifact clustered complete SQL signatures and always returned Top-K cards.
That produced mutually incompatible advice.  V2 mines independent plan slots,
validates each slot on a deterministic train holdout, and lets runtime retrieval
abstain when no validated rule applies.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import sqlglot
from sqlglot import exp


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION = "train-mined-v2"
VALIDATION_BUCKETS = 5
VALIDATION_BUCKET = 0
MIN_RULE_SUPPORT = 8
MIN_RULE_PRECISION = 0.92
MIN_RULE_LIFT = 1.10
MIN_RULE_DATABASE_SUPPORT = 3
MIN_VALIDATION_PRECISION = 0.95
MIN_VALIDATION_PREDICTIONS = 50
MIN_FOLD_PRECISION = 0.90
MIN_FOLD_PREDICTIONS = 5
MAX_RULES_PER_SLOT = 400

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


def _bucket(value: int) -> str:
    return "0" if value == 0 else "1" if value == 1 else "2+"


def _signature(tree: exp.Expression) -> dict[str, Any]:
    selects = list(tree.find_all(exp.Select))
    root_select = selects[0] if selects else None
    aggregates = sorted({node.key.upper() for node in tree.find_all(exp.AggFunc)})
    ordered = list(tree.find_all(exp.Ordered))
    joins = list(tree.find_all(exp.Join))
    tables = list(tree.find_all(exp.Table))
    predicate_operators = sorted({
        node.key.upper()
        for node in tree.walk()
        if isinstance(node, (
            exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
            exp.Between, exp.In, exp.Like, exp.ILike, exp.Is,
        ))
    })
    return {
        "aggregate_functions": aggregates,
        "has_group_by": any(select.args.get("group") is not None for select in selects),
        "has_having": any(select.args.get("having") is not None for select in selects),
        "has_where": any(select.args.get("where") is not None for select in selects),
        "has_order_by": any(select.args.get("order") is not None for select in selects),
        "order_directions": sorted({"DESC" if item.args.get("desc") else "ASC" for item in ordered}),
        "has_limit": any(select.args.get("limit") is not None for select in selects),
        "has_distinct": any(select.args.get("distinct") is not None for select in selects),
        "has_window": any(True for _ in tree.find_all(exp.Window)),
        "has_case": any(True for _ in tree.find_all(exp.Case)),
        "has_cte": any(True for _ in tree.find_all(exp.CTE)),
        "has_subquery": any(True for _ in tree.find_all(exp.Subquery)),
        "has_set_operation": any(True for _ in tree.find_all(exp.SetOperation)),
        "predicate_operators": predicate_operators,
        "join_count": _bucket(len(joins)),
        "table_count": _bucket(len({table.name.casefold() for table in tables})),
        "output_count": _bucket(len(root_select.expressions) if root_select else 0),
    }


def _shape(signature: dict[str, Any]) -> list[str]:
    shape = ["SELECT"]
    if signature["has_distinct"]:
        shape.append("DISTINCT")
    if signature["aggregate_functions"]:
        shape.append("AGGREGATE")
    if signature["join_count"] != "0":
        shape.append("JOIN[" + signature["join_count"] + "]")
    if signature["has_where"]:
        shape.append("WHERE")
    if signature["has_group_by"]:
        shape.append("GROUP_BY")
    if signature["has_having"]:
        shape.append("HAVING")
    if signature["has_order_by"]:
        shape.append("ORDER_BY[" + "/".join(signature["order_directions"]) + "]")
    if signature["has_limit"]:
        shape.append("LIMIT")
    if signature["has_window"]:
        shape.append("WINDOW")
    if signature["has_case"]:
        shape.append("CONDITIONAL")
    if signature["has_subquery"]:
        shape.append("SUBQUERY")
    if signature["has_cte"]:
        shape.append("CTE")
    if signature["has_set_operation"]:
        shape.append("SET_OP")
    return shape


def _slot_labels(signature: dict[str, Any]) -> dict[str, str]:
    aggregates = set(signature["aggregate_functions"])
    labels = {
        f"aggregate_{name}": "present" if name in aggregates else "absent"
        for name in ("COUNT", "SUM", "AVG", "MIN", "MAX")
    }
    labels.update({
        "group_by": "present" if signature["has_group_by"] else "absent",
        "having": "present" if signature["has_having"] else "absent",
        "order_by": "present" if signature["has_order_by"] else "absent",
        "limit": "present" if signature["has_limit"] else "absent",
        "distinct": "present" if signature["has_distinct"] else "absent",
        "window": "present" if signature["has_window"] else "absent",
        "conditional": "present" if signature["has_case"] else "absent",
        "subquery": "present" if signature["has_subquery"] else "absent",
        "cte": "present" if signature["has_cte"] else "absent",
        "order_direction": (
            signature["order_directions"][0]
            if len(signature["order_directions"]) == 1 else "abstain"
        ),
        "output_count": signature["output_count"],
        "join_count": signature["join_count"],
    })
    for operator in ("EQ", "NEQ", "GT", "GTE", "LT", "LTE", "BETWEEN", "IN", "LIKE", "IS"):
        labels[f"predicate_{operator}"] = (
            "present" if operator in signature["predicate_operators"] else "absent"
        )
    return labels


def _split_bucket(item: dict[str, Any]) -> int:
    # Hold out whole databases. Question-level splitting substantially
    # overestimates transfer because near-duplicate templates from the same
    # schema otherwise appear in both rule construction and validation.
    key = str(item.get("db_id", ""))
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % VALIDATION_BUCKETS


def _mine_rules(examples: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Counter]]:
    counts: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    databases: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    priors: dict[str, Counter] = defaultdict(Counter)
    for item in examples:
        features = _features(item["question"])
        for slot, value in item["labels"].items():
            priors[slot][value] += 1
            for feature in features:
                counts[slot][feature][value] += 1
                databases[slot][feature].add(item["db_id"])

    result: dict[str, list[dict[str, Any]]] = {}
    for slot in sorted(priors):
        total = sum(priors[slot].values())
        rules = []
        for feature, values in counts[slot].items():
            support = sum(values.values())
            value, correct = sorted(values.items(), key=lambda item: (-item[1], item[0]))[0]
            precision = correct / support
            prior = priors[slot][value] / total
            lift = precision / prior if prior else 0.0
            database_support = len(databases[slot][feature])
            if value in {"absent", "abstain", "0"}:
                continue
            if (
                support < MIN_RULE_SUPPORT
                or precision < MIN_RULE_PRECISION
                or lift < MIN_RULE_LIFT
                or database_support < MIN_RULE_DATABASE_SUPPORT
            ):
                continue
            rules.append({
                "feature": feature,
                "value": value,
                "support": support,
                "precision": round(precision, 6),
                "lift": round(lift, 6),
                "database_support": database_support,
                "specificity": len(feature.removeprefix("START:").split()),
            })
        rules.sort(key=lambda rule: (
            -rule["specificity"], -rule["precision"], -rule["support"],
            rule["feature"], rule["value"],
        ))
        result[slot] = rules[:MAX_RULES_PER_SLOT]
    return result, priors


def _predict(rules: list[dict[str, Any]], question: str) -> dict[str, Any] | None:
    features = _features(question)
    matches = [rule for rule in rules if rule["feature"] in features]
    if not matches:
        return None
    matches.sort(key=lambda rule: (
        -rule["specificity"], -rule["precision"], -rule["support"],
        rule["feature"], rule["value"],
    ))
    best = matches[0]
    peers = [
        rule for rule in matches
        if rule["specificity"] == best["specificity"]
        and rule["precision"] == best["precision"]
        and rule["support"] == best["support"]
    ]
    if len({rule["value"] for rule in peers}) > 1:
        return None
    return {**best, "matched_rule_count": len(matches)}


def _validate(
    rules: dict[str, list[dict[str, Any]]], examples: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    metrics = {}
    for slot in sorted(rules):
        predictions = []
        for item in examples:
            prediction = _predict(rules[slot], item["question"])
            if prediction is not None:
                predictions.append(prediction["value"] == item["labels"][slot])
        correct = sum(predictions)
        precision = correct / len(predictions) if predictions else 0.0
        metrics[slot] = {
            "validation_examples": len(examples),
            "prediction_count": len(predictions),
            "coverage": round(len(predictions) / len(examples), 6) if examples else 0.0,
            "correct": correct,
            "precision": round(precision, 6),
            "enabled": bool(predictions) and precision >= MIN_VALIDATION_PRECISION,
        }
    return metrics


def _cross_validate(examples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    fold_metrics: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bucket in range(VALIDATION_BUCKETS):
        build_examples = [item for item in examples if item["bucket"] != bucket]
        validation_examples = [item for item in examples if item["bucket"] == bucket]
        rules, _ = _mine_rules(build_examples)
        metrics = _validate(rules, validation_examples)
        for slot, metric in metrics.items():
            fold_metrics[slot].append({"bucket": bucket, **metric})
    combined = {}
    for slot, folds in fold_metrics.items():
        prediction_count = sum(fold["prediction_count"] for fold in folds)
        correct = sum(fold["correct"] for fold in folds)
        precision = correct / prediction_count if prediction_count else 0.0
        substantial_folds = [
            fold for fold in folds
            if fold["prediction_count"] >= MIN_FOLD_PREDICTIONS
        ]
        combined[slot] = {
            "validation_examples": len(examples),
            "prediction_count": prediction_count,
            "coverage": round(prediction_count / len(examples), 6) if examples else 0.0,
            "correct": correct,
            "precision": round(precision, 6),
            "folds": folds,
            "enabled": (
                prediction_count >= MIN_VALIDATION_PREDICTIONS
                and precision >= MIN_VALIDATION_PRECISION
                and bool(substantial_folds)
                and all(
                    fold["precision"] >= MIN_FOLD_PRECISION
                    for fold in substantial_folds
                )
            ),
        }
    return combined


def build(pool_path: Path, output: Path) -> dict[str, Any]:
    raw = json.loads(pool_path.read_text(encoding="utf-8"))
    parsed = []
    failures = []
    for index, item in enumerate(raw):
        sql = str(item.get("SQL") or "").strip()
        if not sql:
            continue
        try:
            signature = _signature(sqlglot.parse_one(sql, read="sqlite"))
        except Exception as exc:
            failures.append({"index": index, "error": type(exc).__name__})
            continue
        parsed.append({
            "db_id": str(item.get("db_id") or ""),
            "question": str(item.get("question") or ""),
            "labels": _slot_labels(signature),
            "bucket": _split_bucket(item),
        })

    validation = _cross_validate(parsed)
    final_rules, priors = _mine_rules(parsed)
    slots = {
        slot: {
            "enabled": validation[slot]["enabled"],
            "validation": validation[slot],
            "label_counts": dict(sorted(priors[slot].items())),
            "rules": final_rules[slot] if validation[slot]["enabled"] else [],
        }
        for slot in sorted(final_rules)
    }
    payload = {
        "version": VERSION,
        "source": {
            "split": "bird-train",
            "pool_path": pool_path.name,
            "pool_sha256": _sha256(pool_path),
            "builder_path": Path(__file__).relative_to(PROJECT_ROOT).as_posix(),
            "builder_sha256": _sha256(Path(__file__)),
            "contains_eval_questions": False,
            "contains_eval_sql": False,
        },
        "build_config": {
            "parser": f"sqlglot-{sqlglot.__version__}",
            "dialect": "sqlite",
            "method": "independent-high-precision-plan-slot-rules",
            "validation_split": f"{VALIDATION_BUCKETS}-fold database-level sha256 cross-validation",
            "min_rule_support": MIN_RULE_SUPPORT,
            "min_rule_precision": MIN_RULE_PRECISION,
            "min_rule_lift": MIN_RULE_LIFT,
            "min_rule_database_support": MIN_RULE_DATABASE_SUPPORT,
            "min_validation_precision": MIN_VALIDATION_PRECISION,
            "min_validation_predictions": MIN_VALIDATION_PREDICTIONS,
            "min_fold_precision": MIN_FOLD_PRECISION,
            "min_fold_predictions": MIN_FOLD_PREDICTIONS,
            "max_rules_per_slot": MAX_RULES_PER_SLOT,
            "stores_raw_sql": False,
            "stores_train_examples": False,
            "runtime_abstention": True,
        },
        "train_example_count": len(raw),
        "parsed_sql_count": len(parsed),
        "parse_failure_count": len(failures),
        "build_example_count": len(parsed),
        "validation_example_count": len(parsed),
        "enabled_slot_count": sum(slot["enabled"] for slot in slots.values()),
        "rule_count": sum(len(slot["rules"]) for slot in slots.values()),
        "slots": slots,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="data/train_pool.json")
    parser.add_argument("--output", default="data/processed/e3_f_query_mining_v2.json")
    args = parser.parse_args()
    built = build(Path(args.pool).resolve(), Path(args.output).resolve())
    print(
        f"wrote {args.output}: enabled_slots={built['enabled_slot_count']}; "
        f"rules={built['rule_count']}; parsed={built['parsed_sql_count']}; "
        f"failures={built['parse_failure_count']}"
    )
