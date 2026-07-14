# E3-B 完整 197 题结果报告

> 实验设计更新（2026-07-14）：本报告的数值与当时结论保留不变，但“E3-A 作为 E3-C 父配置”的建议已被后续设计取代。`train-static-v1` 现在定义为静态规则原型，而非完整 Query Mining；E3-C 回到 E0 知识控制条件并关闭 patterns，E3-D 才测试真正 Query Mining。

## 实验目的

检验固定 train-only query pattern library 能否替代逐题检索的 train few-shot。E3-B 保留 E3-A 的 Prompt、patterns、DB ReAct、FINAL 协议、模型、数据和参数，只把 effective few-shot `k` 从 1 改为 0。

运行产物已统一命名为 `e3_b_core197_run1`。manifest 中的 `agent_profile=e3-rf` 和 `experiment_variant=e3-rf` 是本次已完成运行的历史实现标识，为保持可追溯性不做事后篡改。

## 运行范围与配置

- 运行：`e3_b_core197_run1`
- run_id：`20260714T023630Z-7eab3a22`
- 数据：`bird_cleancore_ids.json` 固定 197 题
- 模型：`azure/seminar-gpt-5.4-mini`，`reasoning_effort=high`，`temperature=0`
- requested `k=1`，effective `k=0`
- query patterns：`train-static-v1`
- pattern artifact SHA-256：`bdda5b6aa4f6d1b69f3c86d2d299e60bb1429f6c2e62b1acd58323850b34cc48`
- train pool SHA-256：`80c0326216d775eff04ae46d5656a452d741d09993d93d527b02848451ee443f`
- 无 legacy DB hints、strict verified-final、capability gate、metadata、QueryPlan、context store 或递归

历史 E3-A manifest 没有保存精确 pattern artifact 内容哈希，因此无法事后严格证明 E3-A 与 E3-B 注入的 pattern 内容逐字一致。E3-B 已补全 artifact 内容、支持数和哈希；本报告将两者视为设计上相同，但保留该复现限制。

## 结果

| 指标 | E3-B |
|---|---:|
| 正确数 | 72 / 197 |
| 执行准确率 | 36.55% |
| `both_wrong` | 20 / 137 = 14.60% |
| `canary` | 52 / 60 = 86.67% |
| simple | 28 / 50 = 56.00% |
| moderate | 30 / 96 = 31.25% |
| challenging | 14 / 51 = 27.45% |
| 正常 `final` 结束 | 195 |
| MaxIterationsError | 1 |
| APIError | 1 |

E3-B 比 E3-A 少 1 道正确题，差值为 -0.51 pp；相对 E0 两次均值 34.26% 高 2.29 pp，但仍处于单次探索性趋势范围。

## 成本与延迟

| 指标 | 总量 | 每题平均 |
|---|---:|---:|
| LLM 调用 | 552 | 2.80 |
| prompt tokens | 1,450,604 | 7,363.47 |
| completion tokens | 1,587,388 | 8,057.81 |
| reasoning tokens | 1,464,969 | 7,436.39 |
| total tokens | 3,037,992 | 15,421.28 |
| DB 调用 | 403 | 2.05 |
| `db.execute` | 322 | 1.63 |
| 延迟 | 7,750.89 s | 39.34 s |
| 缺失 usage 的调用 | 6 | - |

移除 few-shot 后 total tokens/题没有下降，反而比 E3-A 增加 669.56（+4.54%）；LLM 调用从 539 增至 552，延迟从 38.01 s/题增至 39.34 s/题。因此 E3-B 没有实现预期的成本替代收益。

## 自动错误轨迹分类

共 125 个失败项。首要类别如下：

| 错误类别 | 数量 |
|---|---:|
| `UNVERIFIED_FINAL` | 103 |
| `SEMANTIC_REVIEW_REQUIRED` | 8 |
| `AGGREGATION_REASONING` | 7 |
| `SCHEMA_LINKING` | 2 |
| `OUTPUT_CONTRACT` | 2 |
| `RUNNER_OR_API` | 2 |
| `EMPTY_OR_NULL_RESULT` | 1 |

### `UNVERIFIED_FINAL` 控制流细分

| 子类 | 数量 | 含义 |
|---|---:|---|
| `final_sql_rewritten_after_incorrect_observation` | 96 | 最近执行 SQL 已答错，改写后未执行最终版本 |
| `final_without_db_execution` | 3 | 没有任何 `db.execute` 就 FINAL |
| `final_sql_changed_after_unparseable_observation` | 2 | observation 无法可靠解析 |
| `final_sql_changed_after_empty_result` | 1 | 空结果后改写但未执行 |
| `final_sql_rewritten_after_successful_observation` | 1 | 成功 observation 无法与 gold answer 对齐 |

96/103 的主要控制流样本中，旧 SQL 本身已经错误，因此强制提交最后一次执行 SQL 不能修复主要问题。

### 96 项主要控制流样本的语义根因

| 语义类别 | 数量 | 具体子类 |
|---|---:|---|
| `AGGREGATION_REASONING` | 35 | 聚合/分组 31；排序方向或范围 4 |
| `OUTPUT_CONTRACT` | 21 | 输出列数 18；YES/NO 与逐行输出 3 |
| `SCHEMA_LINKING` | 20 | 表选择或 Join 路径 20 |
| `SEMANTIC_REVIEW_REQUIRED` | 20 | 过滤范围或表达式 20 |

其中 34 项只修改表达式或投影，其余 62 项涉及表、过滤、分组、HAVING、排序、LIMIT 或聚合结构。该标签覆盖的是多类语义修正尝试，不是单一 FINAL 格式错误。

## 全部 125 个失败的语义归因

不能使用首要 `error_class` 直接判断失败根因，因为 103 个 `UNVERIFIED_FINAL` 会遮住并行语义标签。按 `semantic_error_class` 汇总后，122 项可结构化归因，3 项属于运行或空结果问题：

| 实际原因层 | 数量 | 占全部失败 | 主要表现 |
|---|---:|---:|---|
| `AGGREGATION_REASONING` | 45 | 36.00% | 聚合/分组 40；排序方向或范围 5 |
| `SEMANTIC_REVIEW_REQUIRED` | 29 | 23.20% | 过滤范围、表达式或 gold 歧义 |
| `OUTPUT_CONTRACT` | 26 | 20.80% | 输出列数 22；YES/NO 与逐行输出 4 |
| `SCHEMA_LINKING` | 22 | 17.60% | 表选择或 Join 路径不匹配 |
| 运行或空结果 | 3 | 2.40% | 1 个 MaxIterations、1 个 APIError、1 个空结果 |

### 运行和空结果项

| ID | 类别 | 原因 |
|---|---|---|
| `bird_1179` | `RUNNER_OR_API` | Max iterations (8) exceeded without FINAL |
| `bird_595` | `RUNNER_OR_API` | Azure/LiteLLM APIError |
| `bird_529` | `EMPTY_OR_NULL_RESULT` | 最终 SQL 返回 0 行 |

## 失败形成机制与判断

1. 移除 few-shot 没有减少聚合、输出、过滤或 Schema/Join 错误；全部失败仍以聚合 45 项为首。
2. E3-B 的 96 个主要 `UNVERIFIED_FINAL` 样本中，旧 SQL 已经错误，FINAL 同步不是替代 few-shot 的解决方案。
3. patterns 单独存在时仍缺少当前问题的题目级实例化和 Schema grounding；这与后续 E3-C metadata、E4-A QueryPlan 的动机一致。
4. E3-B 未实现成本下降，说明移除 few-shot 后模型生成了更多推理和重试，静态 Prompt 缩短没有转化为端到端 token 节省。

## 结论

E3-B 得到 72/197（36.55%），低于 E3-A 的 73/197（37.06%），且 total tokens/题高 4.54%。配对比较恢复 4 题、退化 5 题。由此拒绝“固定 patterns 可以以更低成本替代 train few-shot”的假设。

E3-B 不应作为后续 Offline 文本父配置。当前证据支持保留 E3-A 作为 E3-C 的候选父配置，同时明确其增益较小、成本高于 E0，且 pattern artifact 与 E3-B 的逐字一致性受历史 manifest 限制。后续 E3-C 必须从明确记录的具体父配置运行，并单独检验 Schema/Join metadata。
