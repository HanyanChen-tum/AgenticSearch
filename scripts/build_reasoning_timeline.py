"""Turn each question's captured reasoning sections into a structured timeline.

Thought Anchors builds a graph over sentences within one reasoning trace, sized by
measured (resampling-based) importance. We cannot resample mid-section -- the
hidden reasoning state behind a titled summary section is opaque and uneditable --
so this script does the cheaper half of that job: turn the sections we *did*
capture (`capture_reasoning.py`) into an ordered node sequence per question, and
flag candidate pivot points with simple keyword heuristics (reconsideration
language, phase-of-work cues from each section's bold title).

These flags are candidates, not measured importance. A section flagged here is a
suggestion of where to look, not a claim that it caused the outcome -- that claim
still needs Phase 3's turn-level resampling (`resample_turn.py`) before it goes in
a report.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TITLE_RE = re.compile(r"^\*\*(.+?)\*\*\s*\n*")

# Phase-of-work buckets, matched against each section's bold title. Order matters:
# a title can match more than one bucket, so the first match wins.
PHASE_KEYWORDS = [
    ("uncertainty", r"reconsider|rethink|wait|hmm|confus|doubt|uncertain|puzzl|worried?|nagging"),
    ("problem_setup", r"clarif|understand|pars|figur(e|ing) out|interpret"),
    ("exploration", r"invest|explor|examin|look(ing)? (at|into)|search"),
    ("value_check", r"sampl|inspect|check(ing)? (value|data|column)|verify(ing)? (value|data)"),
    ("drafting", r"formulat|craft|construct|build(ing)? (the|a) (query|sql)|writ(e|ing) (the|a)? ?sql"),
    ("self_check", r"evaluat|valid|review|confirm|assess"),
    ("finalizing", r"final(iz|is)|conclud|wrap(ping)? up|streamlin"),
]

# Sentence-level reconsideration cues, scanned across the whole section body --
# titles are often bland ("Considering X") even when the body reverses course.
PIVOT_CUES = re.compile(
    r"\b(but wait|however|actually|instead|on second thought|let me reconsider|"
    r"i (?:should|need to) reconsider|rethink|i realize(?:d)? (?:that )?i|"
    r"that('?s| is) (?:wrong|incorrect|not right)|scratch that|hold on)\b",
    re.I,
)


def split_title(section: str) -> tuple[str, str]:
    m = TITLE_RE.match(section)
    if not m:
        return "(untitled)", section.strip()
    title = m.group(1).strip()
    body = section[m.end():].strip()
    return title, body


def phase_of(title: str) -> str:
    low = title.lower()
    for phase, pattern in PHASE_KEYWORDS:
        if re.search(pattern, low):
            return phase
    return "other"


def build_timeline(record: dict) -> dict:
    nodes = []
    for i, section in enumerate(record.get("reasoning_sections") or []):
        title, body = split_title(section)
        phase = phase_of(title)
        cues = PIVOT_CUES.findall(body)
        nodes.append({
            "index": i,
            "title": title,
            "phase": phase,
            "pivot_cue_count": len(cues),
            "char_count": len(body),
        })
    candidate_pivots = [n["index"] for n in nodes if n["pivot_cue_count"] > 0]
    phase_sequence = [n["phase"] for n in nodes]
    return {
        "id": record["id"],
        "turn": record.get("turn"),
        "section_count": len(nodes),
        "reasoning_tokens": record.get("reasoning_tokens"),
        "nodes": nodes,
        "phase_sequence": phase_sequence,
        "candidate_pivots": candidate_pivots,
    }


def render_markdown(timeline: dict, sections: list[str]) -> str:
    lines = [f"## {timeline['id']}  (turn {timeline['turn']}, "
             f"{timeline['section_count']} 段, {timeline['reasoning_tokens']} reasoning tokens)", ""]
    for node in timeline["nodes"]:
        marker = " ⟵ 候选转折点" if node["index"] in timeline["candidate_pivots"] else ""
        lines.append(f"{node['index']+1}. [{node['phase']}] **{node['title']}**{marker}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, nargs="+",
                        help="one or more reasoning_capture_*.json files")
    parser.add_argument("--output", required=True, help="structured timeline JSON")
    parser.add_argument("--markdown", default=None, help="optional human-readable summary")
    args = parser.parse_args()

    records = []
    for path in args.input:
        records.extend(json.loads(Path(path).read_text(encoding="utf-8")))

    timelines = [build_timeline(r) for r in records]
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(timelines, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.markdown:
        md_path = Path(args.markdown).resolve()
        by_id = {r["id"]: r.get("reasoning_sections") or [] for r in records}
        chunks = [render_markdown(t, by_id[t["id"]]) for t in timelines]
        md_path.write_text("\n".join(chunks), encoding="utf-8")
        print(f"markdown: {md_path}")

    total_pivots = sum(len(t["candidate_pivots"]) for t in timelines)
    with_pivots = sum(1 for t in timelines if t["candidate_pivots"])
    print(f"{len(timelines)} 题，共标出 {total_pivots} 个候选转折点，"
          f"{with_pivots} 题至少有一个候选转折点")
    print(f"输出: {out}")
