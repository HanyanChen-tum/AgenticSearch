"""Compare the final_execution_gate treatment arm against its control.

Single variable between the two runs: agent_config.final_execution_gate.
Reports accuracy (overall and split by the known-stuck subset vs the random
background subset, since a gain confined to the stuck questions means
something different from a gain spread across both), cost, and -- for the
treatment arm only -- what the gate actually did: how often it fired, on a
timeout or on a genuine error, and whether the model changed its SQL in
response or resubmitted the same query.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"C:\Users\Irene\AgenticSearch")
STUCK = {"bird_346", "bird_409", "bird_415", "bird_416", "bird_480",
         "bird_518", "bird_529", "bird_584", "bird_637"}


def load(name):
    return json.loads((ROOT / "results" / name).read_text(encoding="utf-8"))


def norm(sql):
    return " ".join((sql or "").split()).rstrip(";").strip().lower()


def accuracy(rows, subset=None):
    sel = [r for r in rows if subset is None or (r["id"] in STUCK) == subset]
    scored = [r for r in sel if r.get("scored", True)]
    n = len(scored)
    c = sum(1 for r in scored if r.get("correct"))
    return c, n, (c / n if n else 0.0)


def cost(rows):
    keys = ("llm_calls", "total_tokens", "latency_seconds")
    return {k: sum(r.get(k) or 0 for r in rows) for k in keys}


def gate_activity(trace_dir: Path):
    """Per-question gate behaviour, read from the trace rather than inferred."""
    out = []
    path = trace_dir / "transcripts.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        blocked = [e for e in (rec.get("events") or [])
                   if e.get("tool") == "final.blocked"]
        if not blocked:
            continue
        # SQL submitted at each block, plus whatever was finally accepted.
        # The gate sees the model's raw FINAL string, before the convention
        # rewriter runs, so compare against that same pre-rewrite form.
        submitted = [norm(e["arguments"].get("sql")) for e in blocked]
        rewrite = rec.get("sql_convention_rewrite") or {}
        final_sql = norm(rewrite.get("original_sql") or rec.get("final_sql"))
        # A block is "timeout-driven" if the controller's own execution of the
        # submitted SQL errored with a timeout/interruption.
        reasons = []
        for e in blocked:
            r = str(e.get("result", {}).get("reason") or "")
            reasons.append(r)
        out.append({
            "id": rec.get("id"),
            "blocks": len(blocked),
            "reasons": reasons,
            "redesigned": bool(final_sql and final_sql not in submitted),
            "submitted": submitted,
            "final_sql": final_sql,
        })
    return out


def main():
    ctl = load("finalgate_ctl_sample24.json")
    trt = load("finalgate_trt_sample24.json")

    print("=" * 68)
    print("final_execution_gate: control (e3-c-conv-rules) vs treatment")
    print("=" * 68)
    for label, subset in (("overall", None), ("stuck-9", True), ("background-15", False)):
        cc, cn, ca = accuracy(ctl, subset)
        tc, tn, ta = accuracy(trt, subset)
        print(f"{label:14s}  ctl {cc:2d}/{cn:2d} = {ca:6.1%}   "
              f"trt {tc:2d}/{tn:2d} = {ta:6.1%}   delta {(ta-ca)*100:+.1f}pp")

    print("\ncost (totals over the sample):")
    c_cost, t_cost = cost(ctl), cost(trt)
    for k in c_cost:
        cv, tv = c_cost[k], t_cost[k]
        ratio = (tv / cv) if cv else float("nan")
        print(f"  {k:18s} ctl {cv:12,.0f}   trt {tv:12,.0f}   {ratio:.2f}x")

    print("\nper-question flips (ctl -> trt):")
    cbyid = {r["id"]: r for r in ctl}
    for r in trt:
        c = cbyid.get(r["id"])
        if c and bool(c.get("correct")) != bool(r.get("correct")):
            direction = "RECOVERED" if r.get("correct") else "REGRESSED"
            tag = "stuck" if r["id"] in STUCK else "background"
            print(f"  {direction:9s} {r['id']:11s} ({tag})")

    acts = gate_activity(ROOT / "trace" / "finalgate_trt_sample24")
    print(f"\ngate fired on {len(acts)} question(s):")
    for a in acts:
        print(f"  {a['id']:11s} blocks={a['blocks']} "
              f"redesigned={a['redesigned']} reasons={a['reasons']}")

    # The E1 failure mode to watch for: a gate that fires on most questions is
    # blocking normal revision, not real problems.
    scored_trt = [r for r in trt if r.get("scored", True)]
    if scored_trt:
        print(f"\ngate fire rate: {len(acts)}/{len(scored_trt)} = "
              f"{len(acts)/len(scored_trt):.1%} of scored questions "
              f"(clean-e1's rejected gate fired on 90%)")


if __name__ == "__main__":
    main()
