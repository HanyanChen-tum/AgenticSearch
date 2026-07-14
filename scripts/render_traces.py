"""Render ReAct transcripts into a readable HTML report for trace analysis.

Joins transcripts.jsonl with the result file, renders each question as a
collapsible story (question → hint → turns → final vs gold), failures first.

Usage:
  python scripts/render_traces.py \
    --transcripts transcripts/rhigh_500/transcripts.jsonl \
    --results results/bird_traced_rhigh_500.json \
    --out transcripts/rhigh_500/traces_report.html [--failures-only]
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.trace_io import load_jsonl, validate_run_pair


def esc(s) -> str:
    return html.escape(str(s))


def render_question(rec: dict, res: dict) -> str:
    ok = res.get("correct")
    badge = ("<span style='color:#2e7d32'>✔ correct</span>" if ok
             else "<span style='color:#c62828'>✘ WRONG</span>")
    parts = [f"<details><summary><b>{esc(rec['id'])}</b> "
             f"[{esc(res.get('db_id','?'))} / {esc(res.get('difficulty','?'))}] {badge} "
             f"— {esc(res.get('question','')[:110])}</summary>"]
    parts.append("<div style='margin:0.5em 1em; padding:0.5em; border-left:3px solid #999'>")
    msgs = rec.get("messages", [])
    for i, m in enumerate(msgs):
        role = m.get("role")
        content = str(m.get("content", ""))
        if role == "system":
            parts.append(f"<details><summary><i>system prompt ({len(content)} chars)</i></summary>"
                         f"<pre style='white-space:pre-wrap'>{esc(content[:4000])}</pre></details>")
        elif role == "user" and i <= 1:
            parts.append(f"<details open><summary><b>task prompt</b> ({len(content)} chars)</summary>"
                         f"<pre style='white-space:pre-wrap'>{esc(content[:6000])}</pre></details>")
        elif role == "assistant":
            parts.append(f"<p><b>🤖 model turn:</b></p>"
                         f"<pre style='background:#f0f4ff;white-space:pre-wrap'>{esc(content[:5000])}</pre>")
        else:
            parts.append(f"<p><b>⚙️ observation:</b></p>"
                         f"<pre style='background:#f7f7f7;white-space:pre-wrap'>{esc(content[:3000])}</pre>")
    if rec.get("events"):
        parts.append("<details><summary><b>structured tool events</b></summary>")
        for event in rec["events"]:
            parts.append(
                f"<pre style='background:#fff8e1;white-space:pre-wrap'>"
                f"{esc(json.dumps(event, ensure_ascii=False, indent=2)[:5000])}</pre>"
            )
        parts.append("</details>")
    parts.append(f"<p><b>FINAL SQL:</b> <code>{esc(res.get('predicted_sql',''))}</code></p>")
    parts.append(f"<p><b>PRED result:</b> {esc(str(res.get('predicted_answer'))[:300])}</p>")
    parts.append(f"<p><b>GOLD SQL:</b> <code>{esc(res.get('gold_sql',''))}</code></p>")
    parts.append(f"<p><b>GOLD result:</b> {esc(str(res.get('gold_answer'))[:300])}</p>")
    parts.append(
        f"<p><i>tokens: {res.get('prompt_tokens')}p / "
        f"{res.get('completion_tokens')}c / {res.get('reasoning_tokens')}r / "
        f"{res.get('total_tokens')} total / {res.get('cached_prompt_tokens')} cached "
        f"· {res.get('llm_calls')} calls "
        f"· {res.get('usage_missing_calls', 0)} missing usage "
        f"· {res.get('reasoning_usage_missing_calls', 0)} missing reasoning usage"
        "</i></p>"
    )
    parts.append("</div></details><hr>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--failures-only", action="store_true")
    ap.add_argument("--allow-legacy", action="store_true")
    args = ap.parse_args()

    result_records = json.loads(Path(args.results).read_text(encoding="utf-8"))
    trace_records = load_jsonl(args.transcripts)
    run_id, results, traces = validate_run_pair(
        result_records,
        trace_records,
        allow_legacy=args.allow_legacy,
    )
    recs = list(traces.values())

    def key(r):
        res = results.get(r["id"], {})
        return (res.get("correct", True), r["id"])  # failures first
    recs.sort(key=key)

    n_fail = sum(1 for r in recs if not results.get(r["id"], {}).get("correct", True))
    body = [f"<h1>Trace report — {len(recs)} questions ({n_fail} failures, listed first)</h1>",
            f"<p><b>run_id:</b> {esc(run_id or 'legacy')}</p>",
            "<p>For each failure: find the <b>wrong turn</b> and classify "
            "<b>KNOWLEDGE</b> (model lacked a fact) vs <b>REASONING</b> (had it, misused it).</p>"]
    for r in recs:
        res = results.get(r["id"])
        if not res:
            continue
        if args.failures_only and res.get("correct"):
            continue
        body.append(render_question(r, res))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("<meta charset='utf-8'><body style='font-family:sans-serif;max-width:1100px;margin:auto'>"
                   + "\n".join(body) + "</body>", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
