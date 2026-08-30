"""Check whether a run's tool loop was actually alive before comparing it to anything.

The agent reaches the database only through ```python blocks that the REPL
executes. When the model answers with bare SQL instead, the REPL raises
`SyntaxError`, the query never runs, and the run silently degrades into
single-shot generation -- same profile, same prompt sha, same accuracy column,
completely different system under test.

This has happened repeatedly on identical configuration, in windows that track
the calendar rather than any change in this repo (verified: prompt sha, model,
deployment, api-version, sampling params and `max_iterations` all equal across a
healthy/dead pair; the code commits in the window are renames and docs). Treat it
as a property of the run, not of the profile.

`python scripts/tool_loop_health.py --all` ranks every run; anything under
`--min-exec-rate` (db.execute per question) or `--min-block-rate` (runnable
```python blocks per question) must not be pooled with or compared against a
healthy run. Both signals are needed: a FINAL execution gate runs the SQL on the
model's behalf, so a run can post a healthy execution rate while the model never
once reached the REPL itself.
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

from shared.console import force_utf8_console

SQL_START = re.compile(r"\s*(SELECT|WITH)\b", re.IGNORECASE)


def health(stem: str) -> dict | None:
    """Per-run tool-loop vitals, or None when the run has no usable trace."""
    trace = PROJECT_ROOT / "trace" / stem / "transcripts.jsonl"
    manifest = PROJECT_ROOT / "trace" / stem / "run_manifest.json"
    if not (trace.exists() and manifest.exists()):
        return None
    m = json.loads(manifest.read_text(encoding="utf-8"))
    cfg = m.get("config", {})
    n = executes = blocks = bare = repl_errors = one_turn = straight_final = 0
    for line in trace.open(encoding="utf-8"):
        if not line.strip():
            continue
        t = json.loads(line)
        n += 1
        events = t.get("events") or []
        executes += sum(1 for e in events if e.get("tool") == "db.execute")
        messages = t.get("messages") or []
        first = next((m.get("content") or "" for m in messages
                      if m.get("role") == "assistant"), "")
        if first.strip().startswith("FINAL("):
            straight_final += 1
        assistant_turns = 0
        for msg in messages:
            content = msg.get("content") or ""
            if msg.get("role") == "assistant":
                assistant_turns += 1
                if "```python" in content:
                    blocks += 1
                elif SQL_START.match(content):
                    bare += 1
            elif msg.get("role") == "user" and "REPL Error" in content:
                repl_errors += 1
        if assistant_turns <= 1:
            one_turn += 1
    if not n:
        return None
    return {
        "run": stem,
        "date": (m.get("created_at") or "")[:10],
        "profile": cfg.get("agent_profile"),
        "effort": cfg.get("reasoning_effort"),
        "prompt_sha": (cfg.get("agent_config", {}).get("prompt", {}).get("sha256") or "")[:12],
        "questions": n,
        "db_execute": executes,
        "exec_rate": executes / n,
        "python_blocks": blocks,
        "bare_sql": bare,
        "repl_errors": repl_errors,
        "bare_sql_share": bare / (bare + blocks) if (bare + blocks) else 0.0,
        "block_rate": blocks / n,
        "one_turn_rate": one_turn / n,
        # Two different failures wear the same low block rate. A model that
        # submits FINAL on its first turn never tried to use a tool; a model
        # with bare SQL and matching REPL errors tried and was not understood.
        "straight_to_final_rate": straight_final / n,
        "mode": ("submits-without-looking" if straight_final / n > 0.5
                 else "format-rejected" if bare and repl_errors >= bare
                 else "ok"),
    }


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*", help="result file stems; omit with --all")
    ap.add_argument("--all", action="store_true", help="every run under trace/")
    ap.add_argument("--min-questions", type=int, default=100,
                    help="skip smoke runs below this size")
    ap.add_argument("--min-exec-rate", type=float, default=0.15,
                    help="db.execute per question below which the loop is dead")
    ap.add_argument("--min-block-rate", type=float, default=0.05,
                    help="runnable ```python blocks per question below which the "
                         "model never reached the REPL, even if something else "
                         "(a FINAL gate) executed SQL on its behalf")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    stems = args.runs
    if args.all or not stems:
        stems = sorted(d.name for d in (PROJECT_ROOT / "trace").iterdir() if d.is_dir())

    rows = [h for h in (health(s) for s in stems) if h]
    rows = [r for r in rows if r["questions"] >= args.min_questions]
    rows.sort(key=lambda r: (r["date"], r["run"]))

    print(f"{'date':11s} {'run':48s} {'prof':26s} {'eff':8s} {'n':>4s} "
          f"{'exec/q':>7s} {'py/q':>6s} {'bare':>5s} {'REPLerr':>8s} {'1turn':>6s} "
          f"{'FINAL@0':>8s}")
    print("-" * 140)
    dead = []
    for r in rows:
        flag = ""
        # Either signal alone is enough: a run can show executions it did not
        # ask for (the FINAL gate runs the SQL itself) while the model never
        # once produced a block the REPL could run.
        if (r["exec_rate"] < args.min_exec_rate
                or r["block_rate"] < args.min_block_rate):
            flag = "  <-- TOOL LOOP DEAD"
            dead.append(r)
        print(f"{r['date']:11s} {r['run'][:48]:48s} {str(r['profile'])[:26]:26s} "
              f"{str(r['effort']):8s} {r['questions']:4d} {r['exec_rate']:7.2f} "
              f"{r['block_rate']:6.2f} {r['bare_sql']:5d} {r['repl_errors']:8d} "
              f"{r['one_turn_rate']*100:5.0f}% {r['straight_to_final_rate']*100:7.0f}%{flag}")

    if dead:
        print(f"\n{len(dead)} run(s) below --min-exec-rate {args.min_exec_rate} or "
              f"--min-block-rate {args.min_block_rate}. These ran as single-shot "
              f"generators; do not pool or compare them with healthy runs:")
        for r in dead:
            print(f"  {r['date']}  {r['run']:50s} {r['mode']}")

    if args.output:
        Path(args.output).write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
        print(f"\n-> {args.output}")

    return 1 if dead and args.runs else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
