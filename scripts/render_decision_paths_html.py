"""Render `decision_paths_*.json` as a self-contained Sankey HTML page.

The previous `decision_paths.html` was hand-authored once against an earlier
version of the data -- there was no generator, so every time the underlying
stages changed (as they just did: two trajectory-derived nodes replaced two
weaker SQL-shape ones) the SVG had to be redrawn by hand, node by node. That is
exactly the "analyst intuition" this project has been trying to remove from the
decision-point selection itself; leaving it in the rendering step just moves the
same problem one layer down. This script computes node positions and band paths
from the JSON directly, so a changed ranking regenerates a correct chart with no
manual coordinate editing.

Layout is a standard Sankey stacking: nodes in a column ordered by descending
volume, band thickness proportional to path count, bands split top-to-bottom by
outcome so a glance shows whether a heavy band is mostly green or mostly red.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

WIDTH = 1160
NODE_W = 10
COL_GAP = 150
TOP_MARGIN = 46
BAND_GAP = 3          # vertical gap between stacked bands inside one node
NODE_GAP = 10          # vertical gap between distinct nodes in one column
CHART_H = 620

GOOD = "#0ca30c"
CRITICAL = "#d03b3b"


def node_order(paths: list[dict], stages: list[str], depth: int) -> list[str]:
    counts = Counter(p["nodes"][depth] if depth < len(stages) - 1 else
                      ("答对" if p["correct"] else "答错") for p in paths)
    return [v for v, _ in counts.most_common()]


def build_layout(data: dict):
    stages = data["stages"]
    paths = data["paths"]
    n_cols = len(stages)
    chain_of = lambda p: p["nodes"] + ["答对" if p["correct"] else "答错"]

    orders = [node_order(paths, stages, d) for d in range(n_cols)]
    totals = []
    for d in range(n_cols):
        c = Counter(chain_of(p)[d] for p in paths)
        totals.append(c)

    n = len(paths)
    scale = (CHART_H - NODE_GAP * max(len(o) for o in orders)) / n

    node_pos = {}  # (depth, name) -> (y0, height)
    for d in range(n_cols):
        y = 0.0
        for name in orders[d]:
            h = totals[d][name] * scale
            node_pos[(d, name)] = (y, h)
            y += h + NODE_GAP

    # links, grouped by (depth, source) and (depth+1, target) for stacking order
    link_rows = defaultdict(list)  # depth -> list of link dicts
    for link in data["links"]:
        link_rows[link["depth"]].append(link)

    out_offset = defaultdict(float)  # (depth, source) -> used height so far
    in_offset = defaultdict(float)   # (depth+1, target) -> used height so far
    bands = []
    for d in range(n_cols - 1):
        links = sorted(link_rows[d], key=lambda l: (
            orders[d].index(l["source"]), orders[d + 1].index(l["target"])))
        for link in links:
            h = link["value"] * scale
            sy0, _ = node_pos[(d, link["source"])]
            ty0, _ = node_pos[(d + 1, link["target"])]
            sy = sy0 + out_offset[(d, link["source"])]
            ty = ty0 + in_offset[(d + 1, link["target"])]
            out_offset[(d, link["source"])] += h
            in_offset[(d + 1, link["target"])] += h
            bands.append({"depth": d, "sy": sy, "sh": h, "ty": ty, "th": h,
                           "correct": link["correct"], "value": link["value"],
                           "source": link["source"], "target": link["target"]})

    return stages, orders, node_pos, bands, scale


def band_path(x0: float, sy: float, sh: float, x1: float, ty: float, th: float) -> str:
    mx = (x0 + x1) / 2
    return (f"M{x0:.1f},{sy:.1f} C{mx:.1f},{sy:.1f} {mx:.1f},{ty:.1f} {x1:.1f},{ty:.1f} "
            f"L{x1:.1f},{ty + th:.1f} C{mx:.1f},{ty + th:.1f} {mx:.1f},{sy + sh:.1f} {x0:.1f},{sy + sh:.1f} Z")


def render_svg(data: dict) -> str:
    stages, orders, node_pos, bands, scale = build_layout(data)
    n_cols = len(stages)
    col_x = [i * ((WIDTH - NODE_W) / (n_cols - 1)) for i in range(n_cols)]

    parts = [f'<svg viewBox="0 0 {WIDTH} {CHART_H + TOP_MARGIN + 20}" width="{WIDTH}" '
             f'height="{CHART_H + TOP_MARGIN + 20}">']

    for band in bands:
        x0, x1 = col_x[band["depth"]] + NODE_W, col_x[band["depth"] + 1]
        d = band_path(x0, band["sy"] + TOP_MARGIN, band["sh"], x1, band["ty"] + TOP_MARGIN, band["th"])
        cls = "band ok" if band["correct"] else "band bad"
        tip = f'{band["source"]} → {band["target"]}：{band["value"]} 题（{"答对" if band["correct"] else "答错"}）'
        parts.append(f'<path class="{cls}" d="{d}" data-t="{tip}"></path>')

    for d, x in enumerate(col_x):
        parts.append(f'<text class="stage" x="{x:.1f}" y="{TOP_MARGIN - 20}">{stages[d]}</text>')
        for name in orders[d]:
            y0, h = node_pos[(d, name)]
            y0 += TOP_MARGIN
            parts.append(f'<rect class="node" x="{x:.1f}" y="{y0:.1f}" width="{NODE_W}" height="{h:.1f}" '
                         f'data-t="{name}：{int(h/scale)} 题"></rect>')
            label_x = x + NODE_W + 4 if d < n_cols - 1 else x - 4
            anchor = "start" if d < n_cols - 1 else "end"
            parts.append(f'<text class="nlab" x="{label_x:.1f}" y="{y0 + h/2 + 4:.1f}" '
                         f'text-anchor="{anchor}">{name}</text>')
            parts.append(f'<text class="nsub" x="{label_x:.1f}" y="{y0 + h/2 + 16:.1f}" '
                         f'text-anchor="{anchor}">{int(h/scale)} 题</text>')

    parts.append("</svg>")
    return "\n".join(parts)


def render_top_paths(data: dict, top_n: int = 20) -> str:
    paths = data["paths"]
    n = len(paths)
    grouped: dict[tuple, list] = defaultdict(list)
    for p in paths:
        grouped[tuple(p["nodes"])].append(p["correct"])
    rows = sorted(grouped.items(), key=lambda kv: -len(kv[1]))
    cum = 0
    out = []
    for i, (nodes, outcomes) in enumerate(rows[:top_n], 1):
        cum += len(outcomes)
        rate = sum(outcomes) / len(outcomes) * 100
        cls = "hi" if cum / n <= 0.90 else ""
        out.append(f'<tr class="{cls}"><td class="num">{i}</td><td class="num">{len(outcomes)}</td>'
                   f'<td class="num">{cum/n*100:.1f}%</td><td class="num rate">{rate:.0f}%</td>'
                   f'<td>{" → ".join(nodes)}</td></tr>')
    covered = sum(len(o) for _, o in rows[:top_n])
    return "\n".join(out), len(rows), covered / n * 100


def render_html(data: dict) -> str:
    svg = render_svg(data)
    top_rows, n_distinct_paths, covered_pct = render_top_paths(data)
    n = data["question_count"]
    acc = data["correct_count"] / n * 100
    top_node = max(
        (json.loads(Path(__file__).resolve().parents[1]
                    .joinpath("docs/analysis/analysisDetail/decision_point_ranking_combined.json")
                    .read_text(encoding="utf-8"))),
        key=lambda e: e["mi_bits"])

    return f"""<title>决策路径 Sankey</title>
<style>
.viz-root {{
  color-scheme: light;
  --surface-1:#fcfcfb; --surface-2:#f4f3f0; --border:#dedcd6;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#7a7873;
  --good:#0ca30c; --critical:#d03b3b;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  background:var(--surface-1); color:var(--text-primary);
  max-width:1220px; margin:0 auto; padding:26px 20px 40px;
}}
@media (prefers-color-scheme:dark) {{
  :root:where(:not([data-theme="light"])) .viz-root {{
    color-scheme:dark; --surface-1:#1a1a19; --surface-2:#232322; --border:#3a3a37;
    --text-primary:#fff; --text-secondary:#c3c2b7; --text-muted:#8e8d85;
  }}
}}
:root[data-theme="dark"] .viz-root {{
  color-scheme:dark; --surface-1:#1a1a19; --surface-2:#232322; --border:#3a3a37;
  --text-primary:#fff; --text-secondary:#c3c2b7; --text-muted:#8e8d85;
}}
.viz-root h1 {{ font-size:20px; margin:0 0 4px; letter-spacing:-.01em; }}
.viz-root .sub {{ color:var(--text-secondary); font-size:13px; margin:0 0 18px; line-height:1.55; }}
.tiles {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:18px; }}
.tile {{ background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  padding:10px 14px; min-width:120px; }}
.tile .v {{ font-size:22px; font-weight:600; letter-spacing:-.02em; }}
.tile .k {{ font-size:11px; color:var(--text-muted); margin-top:2px; }}
.chartwrap {{ overflow-x:auto; border:1px solid var(--border); border-radius:10px;
  background:var(--surface-1); }}
svg {{ display:block; }}
.band {{ opacity:.34; transition:opacity .12s; }}
.band.ok {{ fill:var(--good); }}
.band.bad {{ fill:var(--critical); }}
.band:hover {{ opacity:.78; }}
.node {{ fill:var(--text-secondary); }}
.node:hover {{ fill:var(--text-primary); }}
.nlab {{ font-size:11px; fill:var(--text-primary); }}
.nsub {{ font-size:10px; fill:var(--text-muted); }}
.stage {{ font-size:11px; font-weight:600; fill:var(--text-secondary);
  text-transform:uppercase; letter-spacing:.07em; }}
.legend {{ display:flex; gap:16px; align-items:center; font-size:12px;
  color:var(--text-secondary); margin:10px 2px 0; }}
.sw {{ display:inline-block; width:11px; height:11px; border-radius:3px;
  margin-right:5px; vertical-align:-1px; }}
table {{ border-collapse:collapse; width:100%; font-size:12.5px; margin-top:8px; }}
th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--text-muted); padding:7px 9px; border-bottom:1px solid var(--border); }}
td {{ padding:6px 9px; border-bottom:1px solid var(--border); color:var(--text-secondary); }}
td:last-child {{ color:var(--text-primary); font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:11.5px; }}
tr.hi {{ background:color-mix(in srgb, var(--good) 6%, transparent); }}
#tip {{ position:fixed; opacity:0; pointer-events:none; background:var(--text-primary);
  color:var(--surface-1); font-size:11px; padding:5px 8px; border-radius:5px; z-index:9;
  transition:opacity .08s; max-width:280px; }}
</style>
<div class="viz-root">
<h1>决策路径：模型在哪里分岔，分岔之后对错各占多少</h1>
<p class="sub">节点不是手挑的——二十个候选（十四个 SQL 表面特征 + 六个从真实推理/对话内容挖出的轨迹结构特征）按信息增益排序后取前六。
数据源：{data['source']['results']}，{n} 题，答对 {data['correct_count']}（{acc:.1f}%）。</p>
<div class="tiles">
  <div class="tile"><div class="v">{n}</div><div class="k">题目总数</div></div>
  <div class="tile"><div class="v">{acc:.1f}%</div><div class="k">答对率</div></div>
  <div class="tile"><div class="v">{n_distinct_paths}</div><div class="k">不同路径总数</div></div>
  <div class="tile"><div class="v">{top_node['node']}</div><div class="k">信息增益最高（{top_node['mi_bits']:.4f} bits）</div></div>
</div>
<div class="chartwrap">
{svg}
</div>
<div class="legend">
  <span><span class="sw" style="background:var(--good)"></span>答对</span>
  <span><span class="sw" style="background:var(--critical)"></span>答错</span>
  <span style="color:var(--text-muted)">悬停查看具体题数</span>
</div>
<table>
<thead><tr><th>#</th><th>题数</th><th>累计占比</th><th>该路径答对率</th><th>路径</th></tr></thead>
<tbody>{top_rows}</tbody>
</table>
<p class="note">前 20 条路径覆盖 {covered_pct:.0f}% 的题目，其余为长尾。
最强的分支点是<strong>{top_node['node']}</strong>（{top_node['mi_bits']:.4f} bits，
答对率极差 {top_node['spread']*100:.1f} 个百分点）——"结果形状"是本轮新加入的轨迹结构特征，
细分解读见 <code>reasoning_trace_findings_2026-08-12.md</code>：统计上强，但不是单一机制。</p>
<div id="tip"></div>
<script>
(function(){{
  const tip = document.getElementById('tip');
  document.querySelectorAll('[data-t]').forEach(el => {{
    el.addEventListener('mousemove', e => {{
      tip.textContent = el.getAttribute('data-t');
      tip.style.opacity = 1;
      tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 10) + 'px';
      tip.style.top = (e.clientY + 16) + 'px';
    }});
    el.addEventListener('mouseleave', () => {{ tip.style.opacity = 0; }});
  }});
}})();
</script>
</div>
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    html = render_html(data)
    out = Path(args.output).resolve()
    out.write_text(html, encoding="utf-8")
    print(f"written: {out}")
