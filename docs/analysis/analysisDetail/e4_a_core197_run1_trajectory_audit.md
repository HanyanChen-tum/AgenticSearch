# E4-A core197：QueryPlan 与轨迹审计

> **2026-08-07 说明**：本文件由 `scripts/analyze_trajectory_audit.py` 生成，其中的 `semantic_error_class`/`semantic_subcategory` 字段直接取自 `classification_sheet.csv`。该分类表已用修复后的分类器重新生成（`docs/analysis/README.md` §4.1；E4-A 的聚合/排序从 41 升为 33、Schema/Join 从 16 降为 42 中的相对关系已反转，详见 [`e4_a_core197_run1_summary.md`](e4_a_core197_run1_summary.md)），但本文件（含其引用的 `.json`/`_summary.csv`/`_steps.csv`）尚未重新运行该脚本同步。QueryPlan adherence pass/fail、执行状态转移（recovered/regressed/首次分歧轮次等）不依赖语义分类器，不受本次修复影响；涉及具体语义类别的数字请改查重新生成的 `classification_sheet.csv`。

本报告使用 `transcripts.jsonl`、`classification_sheet.csv`、retrieval audit 和执行结果，对全部 126 个失败按”retrieval → initial QueryPlan → SQL execution → observation/revision → FINAL”定位最早可观察分歧。

机器可读文件：

- [`e4_a_core197_run1_trajectory_audit.json`](e4_a_core197_run1_trajectory_audit.json)
- [`e4_a_core197_run1_trajectory_audit_summary.csv`](e4_a_core197_run1_trajectory_audit_summary.csv)
- [`e4_a_core197_run1_trajectory_audit_steps.csv`](e4_a_core197_run1_trajectory_audit_steps.csv)

## 1. 状态链

```text
S0 question / hint
 → S1 Offline retrieval
 → S2 initial QueryPlan
 → S3 candidate SQL
 → S4 db observation
 → S5 optional plan revision
 → S6 later SQL
 → S7 FINAL
```

最早分歧不是由最终分类标签决定，而是取能够被 trace 直接观察的第一个状态。Gold 只用于运行后比较，不进入在线链。

## 2. 最早问题阶段

| 阶段 | 数量 | 含义 |
|---|---:|---|
| `first_nonmatching_execution` | 106 | retrieval 详细上下文完整或未证明缺失，但第一个可比较 SQL 已错 |
| `retrieval_context_risk` | 13 | gold 表/字段详细上下文存在缺失风险，不能把后续错误全归给计划 |
| `direct_final_without_execution` | 6 | 没有结构化候选执行，直接进入 FINAL/终止 |
| `unresolved_execution_or_final_rewrite` | 1 | 执行正确但 FINAL 改写错误，分歧位于 execution 后 |

106 个首次错误执行说明 QueryPlan 没有把问题语义在首次 SQL 前可靠固定。相比“FINAL 错误”标签，这一位置更接近真实起因。

## 3. 执行状态迁移

| 指标 | 数量 |
|---|---:|
| 失败题 | 126 |
| 失败题中的 `db.execute` | 173 |
| 从未执行正确结果 | 123 |
| 曾执行正确结果 | 3 |
| wrong → correct recovery | 0 |
| correct → wrong regression | 2 |

三个 ever-correct 题：

- `bird_671`：两次执行都匹配 gold，随后未执行的错误 FINAL 造成 harmful rewrite；
- `bird_50`：首次执行正确，revision 后转为错误执行并错误 FINAL；
- `bird_189`：同一早期阶段出现正确与错误候选，最后错误改写获胜。

所以 observation/revision 没有救回任何错误轨迹，反而产生两次显式 correct → wrong 退化和一次正确执行后的有害 FINAL。

## 4. QueryPlan 协议

197/197 最终都获得合法初始计划，但协议不是零成本：

- 19 题出现过无效 initial，共 23 次；
- 19 题出现合法 revision，共 28 次；
- 7 题出现无效 revision，共 31 次；
- 2 次 action-contract failure；
- 4 题达到 MaxIterations，均无 FINAL。

31 个 invalid revision 集中在 7 题，说明 observation_ref、delta 字段和代码块共同约束在复杂轨迹中仍不稳定。三个 MaxIterations 回退题原本在 E3-C 正确，协议复杂度直接影响准确率。

## 5. Adherence 的能力边界

252 次执行对应 181 pass、71 fail；44 题至少一次 fail。

| 题组 | 正确 | 失败 | 合计 |
|---|---:|---:|---:|
| 所有执行均 adherence pass | 64 | 82 | 146 |
| 至少一次 adherence fail | 7 | 37 | 44 |
| 无执行 | 0 | 7 | 7 |

adherence fail 与较低准确率相关，但 82 个“全 pass 仍失败”证明结构一致性不是充分条件。当前检查只覆盖：投影列数、GROUP/HAVING/ORDER/LIMIT presence、required tables presence。它不能验证：

- answer scope 是否忠实于自然语言；
- 同名字段来源是否语义正确；
- filter 的值、边界和 AND/OR 范围；
- grain 与实体去重是否正确；
- gold/Hint 是否存在歧义。

## 6. 终态

| terminal transition | 数量 |
|---|---:|
| 错误 execution 后未验证改写 FINAL | 61 |
| FINAL 与最后执行一致 | 57 |
| 无 execution 的 FINAL/终止 | 7 |
| 正确 execution 后有害改写 | 1 |

即便完全解决 62 个 rewrite 类控制流问题，也不能假设 SQL 会正确：其中大多数上游计划或执行已经错误。E1 已证明 strict verified-final 会增加成本而不解决主要语义，因此本报告不建议把它重新混入 E4-A。

## 7. 机制含义

E4-A 的失败不是“没有记录计划”，而是“计划缺少独立的正确性来源”。模型根据同一 question/context 先写计划、再写 SQL，二者相关错误很强；adherence 只能保证后者忠实于前者。

若未来继续研究 QueryPlan，必须在 train-only 数据上单独评估 plan semantic accuracy，至少包括 answer scope、输出项、字段 owner、grain、aggregation scope 和 required tables。只有 plan 本身相对无计划父配置被证明更准确，才值得重新进入正式 eval；否则不应在 E4-A 上叠加 Leaf。
