"""Mine structural patterns straight from the real recorded trajectories.

The existing decision-point candidates (`rank_decision_points.py`) are all shaped
by the *final SQL's* syntax. Reading actual reasoning content (`capture_reasoning.py`,
the bird_959 resampling) surfaced mechanisms that live in the *conversation's
shape* instead -- e.g. the model writing a FINAL() answer in the same turn as its
first, still-unanswered tool calls. Those are cheap to detect across every
question that has a trace (no API calls, just parsing transcripts.jsonl) and
belong in the same information-gain ranking as the SQL-shape candidates.

Each function below maps one question's real message list to one categorical
value. Kept over-inclusive on purpose, same as `rank_decision_points.candidates`;
mutual information plus a correctness-rate spread decide which ones matter.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.evaluator import is_correct

CODE_BLOCK = re.compile(r"```python\s*(.*?)```", re.S)
FINAL_CALL = re.compile(r"FINAL\(")


def assistant_turns(messages: list[dict]) -> list[str]:
    return [m["content"] for m in messages if m["role"] == "assistant"]


def trajectory_features(messages: list[dict]) -> dict[str, str]:
    turns = assistant_turns(messages)
    out: dict[str, str] = {}

    out["轮数"] = ("0" if not turns else "1" if len(turns) == 1
                   else "2" if len(turns) == 2 else "3+")

    if not turns:
        out["首轮已下FINAL"] = "无轮次"
        out["首轮重复调用"] = "无轮次"
    else:
        first = turns[0]
        calls = CODE_BLOCK.findall(first)
        has_final_in_first = bool(FINAL_CALL.search(first))
        out["首轮已下FINAL"] = (
            "首轮带调用+FINAL" if calls and has_final_in_first else
            "首轮仅FINAL" if has_final_in_first else
            "首轮仅调用")
        if calls:
            counts = Counter(c.strip() for c in calls)
            max_repeat = max(counts.values())
            out["首轮重复调用"] = ("不重复" if max_repeat == 1 else
                                  "重复2次" if max_repeat == 2 else "重复3+次")
        else:
            out["首轮重复调用"] = "无调用"

    total_calls = sum(len(CODE_BLOCK.findall(t)) for t in turns)
    out["总调用次数"] = ("0" if total_calls == 0 else "1-2" if total_calls <= 2
                        else "3-5" if total_calls <= 5 else "6+")

    if len(turns) >= 2:
        last, prev = turns[-1], turns[-2]
        last_final = FINAL_CALL.search(last)
        prev_final = FINAL_CALL.search(prev)
        if last_final and prev_final:
            # crude textual overlap between the pre-observation guess and the
            # post-observation answer: did the final turn actually change?
            def norm(s):
                m = FINAL_CALL.search(s)
                return re.sub(r"\s+", " ", s[m.start():])[:200] if m else ""
            out["末轮是否改写首轮猜测"] = ("末轮与早前猜测雷同" if norm(last)[:80] == norm(prev)[:80]
                                          else "末轮已改写")
        else:
            out["末轮是否改写首轮猜测"] = "不适用"
    else:
        out["末轮是否改写首轮猜测"] = "不适用"

    return out


def result_shape(row: dict) -> str:
    gold, pred = row.get("gold_answer"), row.get("predicted_answer")
    gold_multi = isinstance(gold, list) and len(gold) > 1
    pred_single = not isinstance(pred, list) or len(pred) <= 1
    gold_single = isinstance(gold, list) and len(gold) <= 1
    pred_multi = isinstance(pred, list) and len(pred) > 1
    if gold_multi and pred_single:
        return "gold多行->pred单行"
    if gold_single and pred_multi:
        return "gold单行->pred多行"
    return "行数量级一致"


def mutual_information(values: list[str], correct: list[bool]) -> tuple[float, float]:
    n = len(values)
    base_p = sum(correct) / n

    def H(p):
        if p <= 0 or p >= 1:
            return 0.0
        return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))

    base = H(base_p)
    groups: dict[str, list[bool]] = defaultdict(list)
    for value, ok in zip(values, correct):
        groups[value].append(ok)
    conditional = sum(len(g) / n * H(sum(g) / len(g)) for g in groups.values())
    rates = [sum(g) / len(g) for g in groups.values() if len(g) >= 10]
    spread = (max(rates) - min(rates)) if len(rates) >= 2 else 0.0
    return base - conditional, spread


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--ids-filter", default=None,
                        help="optional JSON file with a list of ids to restrict to")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    rows = {r["id"]: r for r in json.loads(Path(args.results).read_text(encoding="utf-8"))}
    restrict = None
    if args.ids_filter:
        restrict = set(json.loads(Path(args.ids_filter).read_text(encoding="utf-8")))

    per_node: dict[str, list[str]] = defaultdict(list)
    correct: list[bool] = []
    ids_used = []

    with Path(args.trace).open(encoding="utf-8") as handle:
        for line in handle:
            rec = json.loads(line)
            qid = rec.get("id")
            if restrict is not None and qid not in restrict:
                continue
            row = rows.get(qid)
            if row is None:
                continue
            trace = rec.get("_trace") or rec
            messages = trace.get("messages") or []
            values = trajectory_features(messages)
            values["结果形状"] = result_shape(row)
            for name, value in values.items():
                per_node[name].append(value)
            correct.append(bool(is_correct(row.get("predicted_answer"), row.get("gold_answer"))))
            ids_used.append(qid)

    n = len(correct)
    print(f"{n} 题，答对率 {sum(correct)/n*100:.1f}%\n")
    print(f'{"节点":<20}{"信息增益":>10}{"答对率极差":>12}{"分支":>6}')
    print("-" * 52)

    ranked = []
    for name, values in per_node.items():
        mi, spread = mutual_information(values, correct)
        counts = Counter(values)
        ranked.append({
            "node": name, "mi_bits": round(mi, 4), "spread": round(spread, 3),
            "branches": len(counts),
            "values": [
                {"value": v, "n": c,
                 "rate": round(sum(1 for val, ok in zip(values, correct) if val == v and ok) / c, 3)}
                for v, c in counts.most_common()],
        })
    ranked.sort(key=lambda r: -r["mi_bits"])
    for entry in ranked:
        print(f'{entry["node"]:<20}{entry["mi_bits"]:>10.4f}{entry["spread"]:>12.1%}{entry["branches"]:>6}')
        for v in entry["values"]:
            print(f'    {v["value"]:<20} n={v["n"]:<5} 答对率 {v["rate"]*100:5.1f}%')

    if args.output:
        Path(args.output).write_text(json.dumps(ranked, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n已写入 {args.output}")
