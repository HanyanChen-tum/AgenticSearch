"""Compare two arms of a prompt experiment at the reasoning level, not just on score.

Accuracy alone cannot say whether an intervention did what it was meant to do. This
puts the two arms' first-turn reasoning side by side: how long it is, how it splits
across the Thought Anchors categories, and -- for the questions both arms answered
-- which way each one moved.

Both arms run the Responses API path, so they are comparable to each other and to
nothing else; no Chat Completions baseline belongs in this table.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

CATEGORIES = ["PS", "PG", "FR", "AC", "UM", "RC", "SC", "FAE"]


def load_labels(path: Path) -> dict[str, list[dict]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {r["id"].split("@")[0]: r["sentences"] for r in rows}


def load_results(path: Path) -> dict[str, dict]:
    return {r["id"]: r for r in json.loads(path.read_text(encoding="utf-8"))}


def share(sentences: list[dict]) -> Counter:
    counts = Counter(s["label"] for s in sentences)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels-a", required=True)
    ap.add_argument("--labels-b", required=True)
    ap.add_argument("--results-a", required=True)
    ap.add_argument("--results-b", required=True)
    ap.add_argument("--name-a", default="A")
    ap.add_argument("--name-b", default="B")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    la, lb = load_labels(Path(args.labels_a)), load_labels(Path(args.labels_b))
    ra, rb = load_results(Path(args.results_a)), load_results(Path(args.results_b))

    shared = sorted(set(la) & set(lb) & set(ra) & set(rb))
    print(f"两臂都有第一轮推理且都有结果的题: {len(shared)}\n")

    ca = sum((share(la[q]) for q in shared), Counter())
    cb = sum((share(lb[q]) for q in shared), Counter())
    na, nb = sum(ca.values()), sum(cb.values())
    print(f"{'类别':<6}{args.name_a + ' 句数':>10}{'占比':>8}{args.name_b + ' 句数':>10}{'占比':>8}{'差':>8}")
    print("-" * 52)
    for cat in CATEGORIES:
        pa, pb = ca[cat] / na * 100, cb[cat] / nb * 100
        print(f"{cat:<6}{ca[cat]:>10}{pa:>7.1f}%{cb[cat]:>10}{pb:>7.1f}%{pb - pa:>+7.1f}")
    print(f"{'合计':<6}{na:>10}{'':>8}{nb:>10}")
    print(f"\n每题句数: {args.name_a} {na/len(shared):.1f}   {args.name_b} {nb/len(shared):.1f}")

    acc_a = sum(bool(ra[q].get("correct")) for q in shared)
    acc_b = sum(bool(rb[q].get("correct")) for q in shared)
    print(f"\n同题准确率（原始 gold）: {args.name_a} {acc_a}/{len(shared)} = {acc_a/len(shared)*100:.1f}%"
          f"   {args.name_b} {acc_b}/{len(shared)} = {acc_b/len(shared)*100:.1f}%   {acc_b-acc_a:+d}")
    flips_to_b = [q for q in shared if not ra[q].get("correct") and rb[q].get("correct")]
    flips_to_a = [q for q in shared if ra[q].get("correct") and not rb[q].get("correct")]
    print(f"  翻转: {args.name_a}错→{args.name_b}对 {len(flips_to_b)}，"
          f"{args.name_a}对→{args.name_b}错 {len(flips_to_a)}")

    # Whether the arms differ on reasoning length is separable from whether they
    # differ on score; a prompt can move one without moving the other.
    if args.output:
        Path(args.output).write_text(json.dumps({
            "shared_questions": shared,
            "counts": {args.name_a: dict(ca), args.name_b: dict(cb)},
            "accuracy": {args.name_a: acc_a, args.name_b: acc_b, "n": len(shared)},
            "flips": {f"{args.name_a}_wrong_to_{args.name_b}_right": flips_to_b,
                      f"{args.name_a}_right_to_{args.name_b}_wrong": flips_to_a},
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
