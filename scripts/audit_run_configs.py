"""Check what each recorded run actually ran, field by field.

`agent_config_sha256` is not a reliable identity on its own, in either direction:

  same sha, different config  -- `max_iterations`, `k`, `temperature` and the
      dataset are command-line arguments and do not enter the agent fingerprint.
      `e3_c_conv_rules_dev500_run1` and `..._iter15` share a sha and differ 8 vs 15.

  different sha, same config  -- the fingerprint moves when a field is added to
      AgentConfig or its serialisation changes. `e3_c_semantic_dev500_run1` differs
      from today's `e3-c-semantic` only in `reasoning_capture` being `null` rather
      than the string `"none"`; the field did not exist when that run happened
      (commit d8933e6) and its traces contain no capture, so the behaviour matched.

So the only trustworthy comparison is a field-by-field diff of the recorded
`agent_config`, which is what this prints. It reports three things and judges none
of them: which runs no longer match their profile and in what fields, which runs
share a fingerprint while differing in run parameters, and where the transcript
does not cover the results.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console
from ours.agent.config import get_agent_config

RUN_PARAMS = ("dataset", "max_iterations", "k", "temperature_requested",
              "reasoning_effort", "model", "limit", "ids_file")


def _flatten(obj, prefix=""):
    """Flatten nested config dicts; drop derived sha256 keys."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "sha256":
                continue  # derived from the other fields; not an independent difference
            out.update(_flatten(v, f"{prefix}{k}."))
    else:
        out[prefix.rstrip(".")] = obj
    return out


def diff_config(was: dict, now: dict):
    """Split a config difference into fields added since the run and fields whose
    value actually changed. A key absent from the older config did not exist then,
    so it cannot have altered that run's behaviour; a key whose value moved might."""
    a, b = _flatten(was), _flatten(now)
    added = sorted(k for k in b if k not in a)
    removed = sorted(k for k in a if k not in b)
    changed = sorted(k for k in a if k in b and a[k] != b[k])
    return added, removed, changed, a, b


def load_manifests():
    out = []
    for p in sorted((PROJECT_ROOT / "trace").glob("*/run_manifest.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append((p.parent.name, m, m.get("config") or {}))
    return out


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=None, help="write the report to this markdown file")
    args = ap.parse_args()

    runs = load_manifests()
    lines = []
    def emit(s=""):
        print(s); lines.append(s)

    emit(f"扫描 {len(runs)} 个 run_manifest.json\n")

    # A. fingerprint no longer matches the profile it names
    emit("## A. manifest sha ≠ 当前同名 profile 的 sha")
    emit("")
    emit("`sha256` 是派生字段，已从比较中剔除。**新增字段**在那次运行时并不存在，")
    emit("不可能影响其行为；**值变更**才需要判读。")
    emit("")
    emit("| 运行 | profile | 值变更（需判读） | 新增字段数 |")
    emit("|---|---|---|---:|")
    drift_only, real = 0, 0
    for name, m, c in runs:
        prof, was = c.get("agent_profile"), c.get("agent_config") or {}
        if not prof or not was:
            continue
        try:
            now = get_agent_config(prof).to_manifest()
        except Exception:
            emit(f"| `{name}` | `{prof}` | **profile 已不存在于 config.py** | — |")
            real += 1
            continue
        added, removed, changed, a, b = diff_config(was, now)
        if not (added or removed or changed):
            continue
        if changed or removed:
            real += 1
            det = "; ".join(f"`{k}`: {a[k]!r} → {b.get(k)!r}" for k in (changed + removed)[:3])
            emit(f"| `{name}` | `{prof}` | {det[:120]} | {len(added)} |")
        else:
            drift_only += 1
    emit("")
    emit(f"**{real} 个运行有值变更（需人工判读），{drift_only} 个只是新增字段（纯漂移，行为未变）。**")
    emit("")

    # B. same fingerprint, different run parameters
    emit("## B. 相同 agent_config_sha256，但运行参数不同")
    emit("")
    groups = defaultdict(list)
    for name, m, c in runs:
        sha = c.get("agent_config_sha256")
        if sha:
            groups[sha].append((name, c))
    shown = 0
    for sha, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        varying = [p for p in RUN_PARAMS
                   if len({json.dumps(c.get(p), default=str) for _, c in members}) > 1]
        if not varying:
            continue
        shown += 1
        emit(f"**`{sha[:12]}`** —— 差异字段：{', '.join(f'`{v}`' for v in varying)}")
        emit("")
        emit("| 运行 | " + " | ".join(varying) + " |")
        emit("|---" * (len(varying) + 1) + "|")
        for n, c in members:
            vals = []
            for p in varying:
                v = c.get(p)
                vals.append(Path(str(v)).name if p == "dataset" and v else str(v))
            emit(f"| `{n}` | " + " | ".join(vals) + " |")
        emit("")
    if not shown:
        emit("（无）\n")

    # C. transcript does not cover the results
    emit("## C. trace 覆盖不全（transcripts 少于 results）")
    emit("")
    emit("| 运行 | results | trace | 覆盖 |")
    emit("|---|---:|---:|---:|")
    gaps = 0
    for name, m, c in runs:
        res = PROJECT_ROOT / "results" / f"{name}.json"
        tr = PROJECT_ROOT / "trace" / name / "transcripts.jsonl"
        if not res.exists() or not tr.exists():
            continue
        try:
            nres = len(json.loads(res.read_text(encoding="utf-8")))
        except Exception:
            continue
        ntr = sum(1 for line in tr.open(encoding="utf-8") if line.strip())
        if ntr >= nres:
            continue
        gaps += 1
        emit(f"| `{name}` | {nres} | {ntr} | {ntr/nres*100:.0f}% |")
    if not gaps:
        emit("| — | | | 全部覆盖 |")
    emit("")

    if args.output:
        Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
