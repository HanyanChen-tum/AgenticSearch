"""Report reasoning cost next to accuracy, per arm, and per accuracy point bought.

Accuracy alone hides what an ablation costs. This walks the same arms the
five-layer chain uses and, for each, prints accuracy beside four cost measures,
each split all / correct / wrong:

  llm_calls        agent turns -- how often the model was asked again
  tool_actions     db.execute / db.sample_values calls
  reasoning_tokens tokens burned inside the model's own reasoning
  latency_seconds  wall clock

Two things the numbers do not say on their own, both already burned this
project once:

  1. A correct/wrong gap is not "thinking longer causes errors". Harder
     questions take more reasoning and are also likelier to be wrong, so the
     gap measures difficulty at least as much as effort. `--by-difficulty`
     stratifies it; read that, not the pooled ratio.
  2. Layer deltas inside the +-1.4pp noise band are not effects. The cost
     column is still real -- an arm can buy nothing and still charge for it,
     which is the point of printing them together.

Arms are compared on one shared question set: any id that any arm in the group
failed to score (harness crash) is dropped from every arm in that group, or the
layers are not judging the same exam. `MaxIterationsError` is kept -- running
out of iterations is an agent outcome with a real cost, not a harness fault.

Every run is first put through `scripts/tool_loop_health.py`. A run whose tool
loop was dead answered in one shot no matter what its profile says, so its cost
numbers describe a different system; those runs are dropped from the pool and
listed under the table rather than quietly averaged into it.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console
from scripts.tool_loop_health import health

HARNESS = {"UnicodeEncodeError", "AttributeError", "BadRequestError", "APIError",
           "TimeoutError", "NotFoundError", "ContentPolicyViolationError"}
MEASURES = ("llm_calls", "tool_actions", "reasoning_tokens", "total_tokens",
            "latency_seconds")
DIFFICULTIES = ("simple", "moderate", "challenging")

# label -> result stems; a pair is two independent repeats of one config
CHAIN = [
    ("L0  B1 single-shot",        ["bird_b1_corrected_run1", "bird_b1_corrected_run2"]),
    ("L0' B2 +keyword prefilter", ["bird_b2_corrected_run1", "bird_b2_corrected_run2"]),
    ("L1  clean-e0 (agent loop)", ["chain_clean_e0_corrected_run1", "chain_clean_e0_corrected_run2"]),
    ("L2  +offline schema",       ["chain_e3_c_noconv_corrected_run1", "chain_e3_c_noconv_corrected_run2"]),
    ("L3  +convention rules",     ["chain_e3_c_conv_rules_corrected_run1", "chain_e3_c_conv_rules_corrected_run2"]),
    ("L4  +RLM recursion",        ["chain_e3_c_recursive_db_corrected_run1", "chain_e3_c_recursive_db_corrected_run2"]),
]
EFFORT = [
    ("minimal", ["effort_minimal_conv_rules_run1", "effort_minimal_conv_rules_run2"]),
    ("low",     ["effort_low_conv_rules_run1", "effort_low_conv_rules_run2"]),
    ("medium",  ["effort_medium_conv_rules_run1", "effort_medium_conv_rules_run2"]),
    ("high",    ["chain_e3_c_conv_rules_corrected_run1", "chain_e3_c_conv_rules_corrected_run2"]),
]
EXTRA = [
    ("L3 baseline (conv-rules)",     ["chain_e3_c_conv_rules_corrected_run1", "chain_e3_c_conv_rules_corrected_run2"]),
    ("e3-c (schema, no conv-rules)", ["e3_c_corrected_run1", "e3_c_corrected_run2"]),
    ("e3-ac (+train patterns)",      ["e3_ac_corrected_run1", "e3_ac_corrected_run2"]),
    ("e3-c-rules-reasoning",         ["e3_c_rules_reasoning_corrected_run1", "e3_c_rules_reasoning_corrected_run2"]),
    ("L4 recursive-db",              ["chain_e3_c_recursive_db_corrected_run1", "chain_e3_c_recursive_db_corrected_run2"]),
    ("L4 +reasoning capture",        ["e3_c_recursive_db_reasoning_corrected_run1", "e3_c_recursive_db_reasoning_corrected_run2"]),
    ("L4 +final gate",               ["chain_e3_c_recursive_db_final_gate_corrected_run1"]),
    ("L4 +keep ties",                ["chain_e3_c_recursive_db_keepties_corrected_run1"]),
]
GROUPS = {"chain": CHAIN, "effort": EFFORT, "extra": EXTRA}

_CACHE: dict[str, dict] = {}
_HEALTH: dict[str, dict | None] = {}


def loop_alive(stem: str) -> bool:
    """False when the model never reached the REPL, whatever the profile claims."""
    if stem not in _HEALTH:
        _HEALTH[stem] = health(stem)
    h = _HEALTH[stem]
    if h is None:          # baselines are single-shot by design, not by failure
        return True
    return h["exec_rate"] >= 0.15 and h["block_rate"] >= 0.05


def usable(stems):
    return [s for s in stems if loop_alive(s)]


def load(stem: str) -> dict:
    """Per-question rows keyed by id, with tool_actions folded in from the trace."""
    if stem in _CACHE:
        return _CACHE[stem]
    rows = json.loads((PROJECT_ROOT / "results" / f"{stem}.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in rows}
    tr = PROJECT_ROOT / "trace" / stem / "transcripts.jsonl"
    if tr.exists():
        for line in tr.open(encoding="utf-8"):
            if not line.strip():
                continue
            t = json.loads(line)
            r = by_id.get(t.get("id"))
            if r is None:
                continue
            ev = t.get("events") or []
            r["tool_actions"] = sum(1 for e in ev if str(e.get("tool", "")).startswith("db."))
    _CACHE[stem] = by_id
    return by_id


def agg(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    ordered = sorted(vals)
    return {"n": len(vals), "mean": st.mean(vals), "median": st.median(vals),
            "p90": ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))],
            "max": ordered[-1]}


def cell(a, key, width, prec=1):
    if a is None:
        return "-".rjust(width)
    return f"{a[key]:{width}.{prec}f}"


def arm_stats(stems, ids):
    """Pool every repeat over the shared id set, then split by correctness."""
    rows = []
    for s in stems:
        by_id = load(s)
        rows += [by_id[i] for i in ids if i in by_id]
    ok = [r for r in rows if r.get("correct")]
    no = [r for r in rows if not r.get("correct")]
    out = {"n": len(rows), "n_correct": len(ok), "runs": len(stems),
           "accuracy": 100.0 * len(ok) / len(rows) if rows else 0.0}
    for m in MEASURES:
        out[m] = {"all": agg([r.get(m) for r in rows]),
                  "correct": agg([r.get(m) for r in ok]),
                  "wrong": agg([r.get(m) for r in no])}
    out["_rows"] = rows
    return out


def shared_ids(group):
    """Ids scored by every arm in the group -- drop harness crashes everywhere at once."""
    sets = []
    for _, stems in group:
        for s in usable(stems):
            sets.append({i for i, r in load(s).items()
                         if r.get("termination") not in HARNESS})
    return set.intersection(*sets)


def print_group(title, group, ids, by_difficulty=False):
    print(f"\n{'=' * 116}")
    print(f"{title.upper()}    shared scorable set: {len(ids)} questions "
          f"(pooled over repeats)")
    print("=" * 116)
    print(f"{'arm':31s} {'acc%':>6s} {'runs':>4s} |{'llm_calls (turns)':^27s}|"
          f"{'tool_actions':^27s}|{'reasoning_tokens':^28s}")
    print(f"{'':31s} {'':6s} {'':4s} |{'all':>9s}{'right':>9s}{'wrong':>9s}|"
          f"{'all':>9s}{'right':>9s}{'wrong':>9s}|{'all':>9s}{'right':>9s}{'wrong':>10s}")
    print("-" * 116)
    stats = {}
    for label, stems in group:
        s = arm_stats(usable(stems), ids)
        stats[label] = s
        line = f"{label:31s} {s['accuracy']:6.2f} {s['runs']:4d} |"
        for m, prec, last in (("llm_calls", 2, 9), ("tool_actions", 2, 9),
                              ("reasoning_tokens", 0, 10)):
            line += (cell(s[m]["all"], "mean", 9, prec)
                     + cell(s[m]["correct"], "mean", 9, prec)
                     + cell(s[m]["wrong"], "mean", last, prec) + "|")
        print(line)

    print(f"\n{'arm':31s} {'tokens/q':>10s} {'latency s/q':>12s} "
          f"{'r.tok median':>13s} {'r.tok p90':>10s} {'r.tok max':>10s}")
    print("-" * 116)
    for label, _ in group:
        s = stats[label]
        rt = s["reasoning_tokens"]["all"]
        print(f"{label:31s} {cell(s['total_tokens']['all'], 'mean', 10, 0)} "
              f"{cell(s['latency_seconds']['all'], 'mean', 12, 1)} "
              f"{cell(rt, 'median', 13, 0)} {cell(rt, 'p90', 10, 0)} "
              f"{cell(rt, 'max', 10, 0)}")

    labels = [l for l, _ in group]
    print(f"\n{'step':44s} {'d_acc pp':>9s} {'d_r.tok/q':>11s} {'d_calls':>9s} "
          f"{'d_lat s':>9s} {'r.tok per +1pp':>16s}")
    print("-" * 116)
    for a, b in zip(labels, labels[1:]):
        sa, sb = stats[a], stats[b]
        dacc = sb["accuracy"] - sa["accuracy"]
        ra, rb = sa["reasoning_tokens"]["all"], sb["reasoning_tokens"]["all"]
        drt = None if (ra is None or rb is None) else rb["mean"] - ra["mean"]
        ca, cb = sa["llm_calls"]["all"], sb["llm_calls"]["all"]
        dcall = None if (ca is None or cb is None) else cb["mean"] - ca["mean"]
        dlat = (sb["latency_seconds"]["all"]["mean"]
                - sa["latency_seconds"]["all"]["mean"])
        per = "-" if (drt is None or abs(dacc) < 1e-9) else f"{drt / dacc:,.0f}"
        short = f"{a.split('(')[0].strip()[:19]:>19s} -> {b.split('(')[0].strip()[:19]:19s}"
        print(f"{short:44s} {dacc:9.2f} "
              f"{('-'.rjust(11) if drt is None else f'{drt:11.0f}')} "
              f"{('-'.rjust(9) if dcall is None else f'{dcall:9.2f}')} "
              f"{dlat:9.1f} {per:>16s}")

    if by_difficulty:
        print(f"\ndifficulty control -- median reasoning_tokens, wrong / correct")
        print(f"{'arm':31s} " + "".join(f"{d:>26s}" for d in DIFFICULTIES))
        print("-" * 116)
        for label, _ in group:
            cells = []
            for d in DIFFICULTIES:
                sub = [r for r in stats[label]["_rows"] if r.get("difficulty") == d]
                ok = [r["reasoning_tokens"] for r in sub
                      if r.get("correct") and r.get("reasoning_tokens") is not None]
                no = [r["reasoning_tokens"] for r in sub
                      if not r.get("correct") and r.get("reasoning_tokens") is not None]
                if not ok or not no or not st.median(ok):
                    cells.append("-".rjust(26))
                    continue
                cells.append(f"{st.median(no) / st.median(ok):.2f}x "
                             f"(n_wrong={len(no)})".rjust(26))
            print(f"{label:31s} " + "".join(cells))
    return stats


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", nargs="+", default=list(GROUPS), choices=list(GROUPS))
    ap.add_argument("--by-difficulty", action="store_true")
    ap.add_argument("--output", default=None, help="write the per-arm stats as JSON")
    args = ap.parse_args()

    dump = {}
    for g in args.groups:
        group = GROUPS[g]
        # Each group uses the shared set of the arms it contains, so a crash in
        # an arm you are not looking at does not shrink your sample.
        dropped = [(label, s) for label, stems in group
                   for s in stems if not loop_alive(s)]
        group = [(label, usable(stems)) for label, stems in group if usable(stems)]
        stats = print_group(g, group, shared_ids(group), args.by_difficulty)
        if dropped:
            print("\ndropped -- tool loop dead, see scripts/tool_loop_health.py:")
            for label, s in dropped:
                h = _HEALTH[s]
                print(f"  {label:31s} {s:48s} {h['date']}  "
                      f"exec/q={h['exec_rate']:.2f} py/q={h['block_rate']:.2f}")
        dump[g] = {"arms": {k: {kk: vv for kk, vv in v.items() if kk != "_rows"}
                            for k, v in stats.items()}}

    if args.output:
        Path(args.output).write_text(json.dumps(dump, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
        print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
