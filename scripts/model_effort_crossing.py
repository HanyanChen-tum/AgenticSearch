"""Separate the model's contribution from the harness's: gpt-5.4-mini vs gpt-5.4, low vs high effort.

The supervisor's question is whether the plateau near 88% is the small model's
capability ceiling or something outside the model -- benchmark, architecture,
schema, reasoning strategy. One model at one effort setting cannot answer it. A
2x2 crossing can, because it puts two contrasts on the same 498 questions:

  model effect     normal - mini, held at one effort
  effort effect    high - low, held at one model
  interaction      does the bigger model still gain from more reasoning, or
                   have both arms run into the same wall?

Two arms landing on the same accuracy from opposite directions is the finding
that matters. If normal-high and mini-high agree inside the noise band, the
ceiling is not model capability, and the remaining suspects are all on our side.

Everything except the varied factor is pinned: one agent profile across all four
cells, `max_iterations=8`, `k=1`, the corrected 498, and the same wall-clock
window -- the last one because response-format behaviour drifts between days
(see `scripts/tool_loop_health.py`), which would otherwise be confounded with
model. The health block below the table is part of the result, not a footnote:
read it before the accuracies, because a cell whose loop died was a different
system from one whose loop ran.

Reported per cell: accuracy, and the cost it took (`llm_calls`,
`reasoning_tokens`, latency), because a bigger model that ties on accuracy while
spending 3x the reasoning is not the same result as one that ties cheaply.

Paired comparisons use McNemar's exact test on the discordant questions: with
run-to-run noise near 1.4pp, an unpaired difference of 1-2pp says nothing, but
the same questions flipping in one direction can still be significant.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from math import comb
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console
from scripts.tool_loop_health import health

HARNESS = {"UnicodeEncodeError", "AttributeError", "BadRequestError", "APIError",
           "TimeoutError", "NotFoundError", "ContentPolicyViolationError"}

# Two crossings of the same 2x2. `single-shot` ran on 2026-08-28 with the tool
# loop dead in every cell -- valid as a model comparison, but of generators, not
# agents. `liveloop` re-runs it on the repaired loop (see
# docs/analysis/week_2026-08-18/dead_loop_root_cause_2026-08-30.md). Pick with
# --crossing; never mix cells across the two, the system under test differs.
CROSSINGS = {
    # The repaired loop: REPL input recovery plus the toolconfirm prompt, which
    # is what it takes to get the model calling tools again. Three cells run as
    # agents (mini x low 1.60, mini x high 0.81, normal x high 0.88 db.execute
    # per question); normal x low sits at 0.19 with 81% submitting on turn 1
    # under both prompts tried, so that cell is the model declining to explore
    # on a low reasoning budget, not a harness failure. Read the health block.
    #
    # Not comparable to the chain's 87.58%: the prompt differs from layer 3.
    "healthy": {
        ("mini", "low"): "ll2_mini_low_run1",
        ("mini", "high"): "ll2_mini_high_run1",
        ("normal", "low"): "ll2_normal_low_run1",
        ("normal", "high"): "ll2_normal_high_run1",
    },
    # Layer 3 plus the REPL repair and nothing else -- same prompt, so these
    # would sit next to the chain's 87.58%. Abandoned mid-run on 2026-08-30:
    # keeping layer 3's prompt leaves the loop dead in three of four cells
    # (85%/59%/82% submitting on turn 1), because the repair fixes the shapes
    # the REPL rejected and not the model's belief that the tools are not real.
    # Chain-comparability and a live loop cannot both be had from this model.
    "l3-recovery": {
        ("mini", "low"): "l3rec_mini_low_run1",
        ("mini", "high"): "l3rec_mini_high_run1",
        ("normal", "low"): "l3rec_normal_low_run1",
        ("normal", "high"): "l3rec_normal_high_run1",
    },
    # Abandoned: also swaps in the toolconfirm prompt, so it is a different
    # system from layer 3 and not comparable to the chain. Kept only so the
    # 2026-08-30 partial runs are explicable.
    "liveloop": {
        ("mini", "low"): "liveloop_mini_low_run1",
        ("mini", "high"): "liveloop_mini_high_run1",
        ("normal", "low"): "liveloop_normal_low_run1",
        ("normal", "high"): "liveloop_normal_high_run1",
    },
    "single-shot": {
        ("mini", "low"): "modelcmp_mini_low_run1",
        ("mini", "high"): "modelcmp_mini_run1",
        ("normal", "low"): "modelcmp_normal_low_run1",
        ("normal", "high"): "modelcmp_normal_run1",
    },
}
CELLS = CROSSINGS["healthy"]
MODELS = ("mini", "normal")
EFFORTS = ("low", "high")


def load(stem: str) -> dict:
    rows = json.loads((PROJECT_ROOT / "results" / f"{stem}.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in rows}
    tr = PROJECT_ROOT / "trace" / stem / "transcripts.jsonl"
    if tr.exists():
        for line in tr.open(encoding="utf-8"):
            if not line.strip():
                continue
            t = json.loads(line)
            r = by_id.get(t.get("id"))
            if r is not None:
                ev = t.get("events") or []
                r["tool_actions"] = sum(1 for e in ev
                                        if str(e.get("tool", "")).startswith("db."))
    return by_id


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact p over the discordant pairs; 1.0 when there are none."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def mean(rows, key):
    vals = [r.get(key) for r in rows if r.get(key) is not None]
    return st.mean(vals) if vals else None


def fmt(v, width, prec=1):
    return "-".rjust(width) if v is None else f"{v:{width}.{prec}f}"


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--crossing", choices=list(CROSSINGS), default="healthy")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    global CELLS
    CELLS = CROSSINGS[args.crossing]
    print(f"crossing: {args.crossing}")

    data, missing = {}, []
    for cell, stem in CELLS.items():
        if not (PROJECT_ROOT / "results" / f"{stem}.json").exists():
            missing.append((cell, stem))
            continue
        data[cell] = load(stem)
    if missing:
        print("not yet available:")
        for cell, stem in missing:
            print(f"  {cell[0]:7s} x {cell[1]:5s}  results/{stem}.json")
        if not data:
            return
        print()

    ids = set.intersection(*[{i for i, r in d.items()
                              if r.get("termination") not in HARNESS}
                             for d in data.values()])
    print(f"shared scorable set: {len(ids)} questions\n")

    print("tool-loop health (a dead loop makes the cell a single-shot generator, "
          "not an agent):")
    print(f"  {'cell':16s} {'date':11s} {'exec/q':>7s} {'py/q':>6s} {'FINAL@0':>8s}  mode")
    for cell in CELLS:
        if cell not in data:
            continue
        h = health(CELLS[cell])
        if h is None:
            print(f"  {cell[0] + ' x ' + cell[1]:16s} (no trace)")
            continue
        print(f"  {cell[0] + ' x ' + cell[1]:16s} {h['date']:11s} {h['exec_rate']:7.2f} "
              f"{h['block_rate']:6.2f} {h['straight_to_final_rate']*100:7.0f}%  {h['mode']}")

    print(f"\n{'cell':16s} {'acc%':>7s} {'n_ok':>6s} {'llm_calls':>10s} {'tool_act':>9s} "
          f"{'r.tok':>8s} {'r.tok med':>10s} {'tot.tok':>9s} {'lat s':>7s}")
    print("-" * 96)
    acc, stats = {}, {}
    for cell in CELLS:
        if cell not in data:
            continue
        rows = [data[cell][i] for i in ids]
        ok = sum(1 for r in rows if r.get("correct"))
        acc[cell] = 100.0 * ok / len(rows)
        rt = [r["reasoning_tokens"] for r in rows if r.get("reasoning_tokens") is not None]
        stats[cell] = {"accuracy": acc[cell], "n_correct": ok, "n": len(rows),
                       "llm_calls": mean(rows, "llm_calls"),
                       "tool_actions": mean(rows, "tool_actions"),
                       "reasoning_tokens": mean(rows, "reasoning_tokens"),
                       "reasoning_tokens_median": st.median(rt) if rt else None,
                       "total_tokens": mean(rows, "total_tokens"),
                       "latency_seconds": mean(rows, "latency_seconds")}
        s = stats[cell]
        print(f"{cell[0] + ' x ' + cell[1]:16s} {acc[cell]:7.2f} {ok:6d} "
              f"{fmt(s['llm_calls'], 10, 2)} {fmt(s['tool_actions'], 9, 2)} "
              f"{fmt(s['reasoning_tokens'], 8, 0)} {fmt(s['reasoning_tokens_median'], 10, 0)} "
              f"{fmt(s['total_tokens'], 9, 0)} {fmt(s['latency_seconds'], 7, 1)}")

    print(f"\npaired contrasts (McNemar exact on discordant questions):")
    print(f"{'contrast':38s} {'d_acc pp':>9s} {'a_only':>7s} {'b_only':>7s} {'p':>9s} "
          f"{'d_r.tok':>9s}")
    print("-" * 96)

    def contrast(a, b, label):
        if a not in data or b not in data:
            return None
        ra, rb = data[a], data[b]
        a_only = sum(1 for i in ids if ra[i].get("correct") and not rb[i].get("correct"))
        b_only = sum(1 for i in ids if rb[i].get("correct") and not ra[i].get("correct"))
        p = mcnemar_exact(a_only, b_only)
        d = acc[b] - acc[a]
        dr = (stats[b]["reasoning_tokens"] or 0) - (stats[a]["reasoning_tokens"] or 0)
        print(f"{label:38s} {d:9.2f} {a_only:7d} {b_only:7d} {p:9.4f} {dr:9.0f}")
        return {"delta_accuracy_pp": d, "a_only": a_only, "b_only": b_only,
                "mcnemar_p": p, "delta_reasoning_tokens": dr}

    out = {"shared_question_count": len(ids), "contrasts": {},
           "cells": {f"{m}_x_{e}": s for (m, e), s in stats.items()}}
    for e in EFFORTS:
        r = contrast(("mini", e), ("normal", e), f"model effect @ {e}: mini -> normal")
        if r:
            out["contrasts"][f"model_effect_at_{e}"] = r
    for m in MODELS:
        r = contrast((m, "low"), (m, "high"), f"effort effect @ {m}: low -> high")
        if r:
            out["contrasts"][f"effort_effect_at_{m}"] = r

    if all(c in acc for c in CELLS):
        mini_gain = acc[("mini", "high")] - acc[("mini", "low")]
        normal_gain = acc[("normal", "high")] - acc[("normal", "low")]
        print(f"\ninteraction: effort gain is {mini_gain:+.2f}pp on mini and "
              f"{normal_gain:+.2f}pp on normal (difference {normal_gain - mini_gain:+.2f}pp)")
        print("Read against the +-1.4pp noise band. Two arms meeting at the same "
              "accuracy from opposite\ndirections is evidence the ceiling is not "
              "model capability.")
        out["interaction"] = {"effort_gain_mini_pp": mini_gain,
                              "effort_gain_normal_pp": normal_gain,
                              "difference_pp": normal_gain - mini_gain}

    if args.output:
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
        print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
