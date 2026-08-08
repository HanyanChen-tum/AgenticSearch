# E3-C Schema v4 可观测轨迹与首错位置审计

> **2026-08-07 说明**：本文件由 `scripts/analyze_trajectory_audit.py` 生成，其中的 `semantic_error_class`/`semantic_subcategory` 字段直接取自 `classification_sheet.csv`。该分类表已用修复后的分类器重新生成（`docs/analysis/README.md` §4.1，Schema/Join 从 15 升为 46），但本文件本身（含其引用的 `_summary.csv`/`_steps.csv`）尚未重新运行该脚本同步，仍反映修复前的语义标签；退出/执行状态转移（recovered/regressed/adherence 等，不依赖语义分类）不受影响。引用本文件中的语义类别数字前，请改查重新生成的 `classification_sheet.csv`，或先重跑 `analyze_trajectory_audit.py`。

> 本报告分析 `e3_c_schema_v4_core197_run3` 的 120 个失败。它把 Agent 看作状态转移系统，但只审计 trace 中可观测的状态：retrieval 上下文、候选 SQL、执行 observation、SQL 改写和 FINAL。模型未输出的内部语义状态不可见，因此这里报告的是“最早可观测问题位置”，不是对隐藏 chain-of-thought 的断言。

## 1. 产物

- 题目级 120/120 摘要：[`e3_c_schema_v4_trajectory_audit_summary.csv`](e3_c_schema_v4_trajectory_audit_summary.csv)
- 逐步 285 条状态/动作：[`e3_c_schema_v4_trajectory_audit_steps.csv`](e3_c_schema_v4_trajectory_audit_steps.csv)
- 含每题完整步骤的 JSON：[`e3_c_schema_v4_trajectory_audit.json`](e3_c_schema_v4_trajectory_audit.json)
- 可复现脚本：[`../../../scripts/analyze_trajectory_audit.py`](../../../scripts/analyze_trajectory_audit.py)

逐步表中的每一行记录候选 SQL、表集合、投影列数、相对上一 SQL 的结构变化、执行结果是否与 gold answer 相同，以及本次状态转移类型。

## 2. 可观测状态定义

```text
S0: retrieved context
  → A1: candidate SQL
  → O1: execution observation
  → S1: conversation state after observation
  → A2/O2 ...
  → AF: FINAL SQL
```

当状态包含完整对话历史时，可以把外部运行近似写成马尔科夫状态转移；但 trace 没有暴露模型内部语义表示，因此从分析者视角仍是部分可观测过程。

本报告使用以下保守口径：

- `retrieval_context_risk`：gold 表或字段不在详细 Schema 上下文中。这是最早风险点，但不自动证明它导致失败。
- `first_nonmatching_execution`：第一次 `db.execute` 的结果与 gold answer 不同。这是可观测分叉点，但候选 SQL 可能是探索查询，所以置信度为中等。
- `direct_final_without_execution`：没有结构化执行事件就提交错误 FINAL，属于高置信度控制流起点。
- `unresolved_execution_or_final_rewrite`：存在执行但只能在 FINAL 改写时确认错误。

## 3. 最早可观测问题位置

| 最早位置 | 失败数 | 含义 |
|---|---:|---|
| `first_nonmatching_execution` | 91 | retrieval 完整，第一次可判定的候选执行已经与 gold 不同 |
| `retrieval_context_risk` | 13 | 详细 Schema 缺表或缺字段；是 Turn 0 风险而非已证明因果 |
| `direct_final_without_execution` | 15 | retrieval 完整，但没有任何结构化 `db.execute` 就提交错误 FINAL |
| `unresolved_execution_or_final_rewrite` | 1 | 只能在后续或 FINAL 确认错误 |
| 合计 | 120 | — |

如果只看实际出现的第一次 nonmatching execution，不覆盖 retrieval 的优先级：

| 首次 nonmatching 执行轮次 | 题数 |
|---|---:|
| Turn 1 | 81 |
| Turn 2 | 19 |
| Turn 3 | 2 |
| 从未获得可比较的 nonmatching rows | 18 |

这说明至少 `81/120` 个失败在第一次可判定执行时已经偏离；核心问题通常发生在初始问题理解或首个候选 SQL，而不是多轮运行之后才产生。

## 4. 执行轨迹长度

| `db.execute` 次数 | 失败题数 |
|---|---:|
| 0 | 17 |
| 1 | 67 |
| 2 | 20 |
| 3 | 11 |
| 4 | 2 |
| 5 | 1 |
| 6 | 2 |

120 个失败共有 165 个结构化 `db.execute` 步骤，加上 120 个 FINAL，共形成 285 个候选执行/提交步骤。旧版分析器曾把 `db.sample_values` 误计为 SQL execution，得到 282；该口径已修正。多次执行并不代表发生了有效纠错。

## 5. 中间恢复与退化

| 轨迹性质 | 题数 |
|---|---:|
| 从未执行出 gold-matching result | 119 |
| 曾执行出 gold-matching result | 1 |
| `wrong execution → correct execution` 恢复 | 0 |
| `correct execution → wrong FINAL` 退化 | 1 |

唯一曾到达正确执行状态的是 `bird_228`：Turn 1 执行结果与 gold answer 相同，但 Turn 2 改写 SQL 后直接提交错误 FINAL。它是高置信度的有害状态转移：

```text
correct executed candidate
    → unverified SQL rewrite
    → incorrect FINAL
```

其余 119 个失败从未在可观测执行状态中到达正确答案。因此，E3-C 当前的主要问题不是“恢复正确后又丢失”，而是初始候选错误后没有真正恢复。

## 6. FINAL 前的末端转移

| 末端转移 | 数量 |
|---|---:|
| 错误执行后改写为未验证 FINAL | 86 |
| 无候选 SQL 执行直接 FINAL | 17 |
| FINAL 与最近一次执行 SQL 相同 | 16 |
| 正确执行后有害改写为错误 FINAL | 1 |

86 个样本在 FINAL 前已经有明确 nonmatching observation，却仍然通过未验证改写结束。这不是错误的最初来源，但它使错误状态持续传播，并阻止下一次 observation 对改写进行纠正。

17 个失败没有任何结构化候选 SQL 执行。复核 trace 后发现，其中一类原因是同一响应包含多个 Python block，而历史 REPL 只执行第一个 block，后续 `db.execute` 被静默丢弃；另一类是直接 FINAL。它们不能继续统称为“observation 无法解析”。

## 7. 首错位置与最终语义类型

91 个“retrieval 完整且首次可判定执行已错”的最终语义分布为：

| 最终语义归因 | 数量 |
|---|---:|
| `AGGREGATION_REASONING` | 29 |
| `SEMANTIC_REVIEW_REQUIRED` | 24 |
| `OUTPUT_CONTRACT` | 24 |
| `SCHEMA_LINKING` | 14 |

13 个 retrieval 风险项的最终语义分布为：聚合 6、输出 3、过滤 3、Schema/Join 1。缺失上下文并不总是最终被归为 Schema/Join，说明 Schema 缺失可能通过后续聚合、投影或过滤选择传播，也可能只是非因果相关。

## 8. 对 E3-C 的新解释

轨迹审计不改变“E3-C 相对 E0 有效”的总体结论，但细化了剩余瓶颈：

1. E3-C 的 retrieval 已经不是多数失败的首要风险：91 个失败在 retrieval 完整的情况下，第一次可判定执行就错。
2. 现有多轮 ReAct 没有表现出有效恢复：失败集合中 `wrong → correct` 为 0。
3. 未验证 FINAL 主要是错误传播机制，不是最初语义根因；86 题在错误 observation 后继续改写但不再验证。
4. 后续 E4-A 应优先约束首个候选前的 answer type、统计 grain、过滤结构和表/列来源，而不只是增加更多重试。
5. E1 类 FINAL 验证仍有价值，但它主要阻止错误传播；单独启用不能修复第一次候选就错的 91 题。

## 9. 轨迹证据到改进机制的映射

| 轨迹证据 | 说明 | 下一项改进 | 所属工作 |
|---|---|---|---|
| 81 题在 Turn 1 已出现 nonmatching execution | 初始问题形式化或首个 SQL 已经偏离 | 首个 SQL 前生成结构化 QueryPlan，固定统计对象、grain、过滤、聚合、排序和输出形式 | `E4-A` |
| 最终失败为聚合/排序 45、输出 28 | 最主要目标不是继续扩展 Schema，而是约束 SQL 结构 | QueryPlan 同时包含 Output Contract；记录 plan-SQL adherence | `E4-A` |
| 30 条过滤错误仍为低置信度 | 自动结构差异不能区分 Agent 错误与 gold 歧义 | 人工审核边界、时间范围、AND/OR、NULL、值编码和作用域 | `F-Audit`，与 E4-A 并行准备 |
| 119/120 从未执行出正确结果，`wrong → correct` 为 0 | 现有多轮 ReAct 没有形成可见恢复 | 每次 observation 后记录 plan delta、保留不变量，并说明下一候选是探索还是答案 | 先作为 E4-A trace/adherence 字段；不增加独立 Planner call |
| 86 条在错误 observation 后改写且未验证 | FINAL 问题传播错误，但不是多数样本的起点 | 记录 rewrite reason 和是否重新执行；不把 strict verified-final 作为主实验 | 观测字段；E1 已拒绝，不重新包装成准确率机制 |
| 17 条没有结构化候选 SQL execution | 多 block 静默丢弃或直接 FINAL，使 Agent 缺少真实反馈 | 每轮限制一个 Python block；底层不得静默丢弃后续 block；所有工具结果结构化返回 | `E2-A` 基础设施修复，在 E4-A 前完成 smoke |
| 13 条存在 detailed Schema 缺失风险 | retrieval 仍有局部召回问题，但不是多数失败来源 | 保留缺失列表；只在计划引用 names-only 字段时做确定性扩展 | 后续 Schema retrieval 优化，不与 E4-A 混跑 |

### 9.1 E4-A 应增加的最小可观测字段

现有 QueryPlan 的语义字段保持不变，另外增加以下最小状态字段：

```json
{
  "candidate_purpose": "explore|answer",
  "expected_result_shape": {
    "answer_type": "rows|scalar|boolean",
    "column_count": 0,
    "row_grain": ""
  },
  "unresolved_assumptions": [],
  "revision": {
    "observation_ref": null,
    "changed_constraints": [],
    "updated_fields": {},
    "reason": null
  }
}
```

初始 plan 的 `revision` 为 `null`。后续若 SQL 改写，只记录相对上一状态的 delta，不重新生成一份与历史脱节的计划。这样才能分析：

```text
plan correct? → SQL follows plan? → observation supports expectation?
              → which constraint changed? → next SQL improves or regresses?
```

第一轮 E4-A 只记录并测量 adherence，不增加独立 checker LLM call，也不加入递归。否则无法区分收益来自题目形式化、额外推理预算还是强制重试。

### 9.2 下一轮的判断指标

除原有 accuracy、recovered/regressed 和语义错误类别外，E4-A 应增加配对轨迹指标：

1. Turn 1 nonmatching execution 是否从当前 `81/197` 显著下降；
2. 聚合/排序 45 条与输出契约 28 条是否至少一类净下降；
3. 正确 plan 是否被 SQL 遵守；若 plan 已错，应区分 plan 生成错误，不能归为 SQL adherence；
4. 是否首次出现可解释的 `wrong execution → corrected execution`；
5. `correct execution → wrong rewrite/FINAL` 是否仍发生；
6. Schema/Join 15 条、canary 52/60 和 token 成本是否出现不可接受回退。

若 plan 本身正确但 SQL 经常不遵守，下一步才测试确定性 adherence check；若 plan 本身已经错误，则先修改 plan schema、生成时机或字段含义。两者不能在同一轮同时修改。

## 10. 建议执行顺序

1. 修复并 smoke 工具协议：每轮一个 Python block，后续 block 不得被静默丢弃，rows/error/empty/all-null 始终结构化可见；这只作为基础设施，不申报机制收益。
2. 锁定 E3-C Schema v4 + `k=1` few-shot 为父配置，不加入 Query Mining。
3. 实现并运行 E4-A：同一次 Root 响应先生成 QueryPlan + Output Contract，再生成首个 SQL；不增加独立 Planner call。
4. 并行完成 F-Audit，但不要把 eval gold 结论写回在线 Prompt 或 Offline artifact。
5. E4-A 运行后重新生成同一套 semantic、retrieval 和 trajectory audit，再决定是修 plan、修 adherence，还是进入 E5。

当前不建议直接增加重试、重新启用 strict verified-final、加入 Query Mining 或进入 Leaf/递归。这些改动没有命中“Turn 1 已错且没有恢复”这一主要证据，并会破坏单变量归因。

## 11. 限制

- 中间 SQL 可能是探索查询，因此 `first_nonmatching_execution` 不能自动等同于隐藏语义的“第一处错误”。
- 17 个失败没有结构化候选 SQL execution；其中包含历史多 block 静默丢弃，说明旧工具协议对状态转移不完全可观测。
- 执行结果与 gold answer 不同只说明答案状态分叉，不说明 gold SQL 是唯一正确写法。
- 如果要得到更强的马尔科夫归因，未来运行应显式记录每轮结构化 `QueryPlan`、候选用途（探索/答案）、预期输出 shape 和修改原因。
