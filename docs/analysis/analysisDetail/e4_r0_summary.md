# BIRD E4-R0 单次运行报告

- 实验：E4-R0 capability-gated 直接 Prompt/ReAct 对照
- Profile：`e4-r0`
- Run ID：`20260713T213358Z-8603f18a`
- 题目：固定 `bird_cleancore_ids.json` 的 `both_wrong + canary`，前 50 题
- 状态：完整运行

## 机制与配置

E4-R0 从 E0 出发，只增加运行时 capability gate：

- `verified_final=false`，不继承 E1 的 strict verified-final；
- `capability_gate=true`；
- 允许的数据库工具为 `db.execute` 和 `db.sample_values`；
- `generic_recursive_llm=false`；
- `context_mode=direct`、`reasoning_mode=none`、`planner_mode=none`；
- 继续使用 clean Prompt、train-only few-shot、`k=1`、`max_iterations=8` 和 high reasoning。

该实验的目的不是直接提升准确率，而是确认后续 RLM/Planner 实验拥有一个没有隐藏递归或 Schema API 能力污染的参考组。
capability gate 主要用于实验隔离和防止隐藏能力污染，并不是直接提升 SQL 准确率的机制。

## 运行结果

| 指标 | 结果 |
|---|---:|
| 正确数 | 19/50 |
| 准确率 | 38.00% |
| 终止方式 `final` | 50/50 |
| `MaxIterationsError` | 0 |

## 成本

| 指标 | 总计 | 每题 |
|---|---:|---:|
| LLM 调用 | 136 | 2.72 |
| Prompt tokens | 201,308 | 4,026.16 |
| Completion tokens | 309,056 | 6,181.12 |
| Reasoning tokens | 282,493 | 5,649.86 |
| Total tokens | 510,364 | 10,207.28 |
| DB 工具调用 | 110 | 2.20 |
| `db.execute` 调用 | 60 | 1.20 |
| `db.sample_values` 调用 | 50 | 1.00 |
| 延迟（秒） | 1,834.47 | 36.69 |

存在 3 次 usage 缺失，因此 token 数是已记录调用的下界。

## Capability 审计

trace 共记录 110 个数据库工具事件，其中 60 次 `db.execute`、50 次
`db.sample_values`。所有观察到的工具都属于 manifest 声明的允许集合，未发现
递归调用、Schema API 调用或越权工具事件。

因此，E4-R0 满足“能力边界有效”的校准条件，可以作为后续 RLM/Planner 消融的父对照。

## 错误类别

| 错误类别 | 数量 | 占失败记录 |
|---|---:|---:|
| `UNVERIFIED_FINAL` | 27 | 87.10% |
| `AGGREGATION_REASONING` | 1 | 3.23% |
| `OUTPUT_CONTRACT` | 1 | 3.23% |
| `SEMANTIC_REVIEW_REQUIRED` | 1 | 3.23% |
| `TOOL_ERROR` | 1 | 3.23% |

### 错误子类别

| 子类别 | 数量 |
|---|---:|
| `final_sql_changed_after_test` | 25 |
| `final_without_db_execution` | 2 |
| `aggregation_or_grouping_mismatch` | 1 |
| `filter_scope_or_expression_mismatch` | 1 |
| `output_column_count_mismatch` | 1 |
| `unparseable_execution_observation` | 1 |

`UNVERIFIED_FINAL` 在 E4-R0 中仍然较多，说明 capability gate 与最终 SQL
验证门是两个不同机制。E4-R0 没有启用 E1 的 strict verified-final，因此该标签
保留是预期现象，不能据此判断 E4-R0 失败。

## 错误到改进机制映射

E4-R0 的 50 题运行只验证能力边界，错误数量不用于替代 E0/E3-A 的完整 197 题统计。后续改进继承完整集结论：

| 可见问题 | capability gate 为什么不解决 | 应采用的改进 | 对应 v0.14 实验 |
|---|---|---|---|
| 聚合、排序和输出 | gate 只限制工具能力，不改变语义规划 | Root QueryPlan + 输出契约 | `P` |
| Schema/Join | gate 不提供字段来源或连接路径 | metadata + PK/FK + Join path | `M` |
| 过滤范围 | gate 不判断条件边界和作用层级 | QueryPlan 条件结构；后续环境样例值检查 | `P`/`C-P` |
| `UNVERIFIED_FINAL` | gate 与 FINAL 状态机独立 | 保留诊断，不恢复 strict gate | 无独立实验 |
| observation 解析 | gate 只审计调用权限 | 统一结构化工具事件 | 基础设施 |

capability gate 本身不作为准确率改进。它在 R1E-S、C-P、C-P-Budget 和 C-P-Leaf 中作为强制实验基础设施，确保未声明的 Schema API 和通用 `recursive_llm` 不可达。

## 结论

1. E4-R0 为 38.00%，与 E0 首 50 题的 38.00% 和 40.00% 基线范围一致。
2. 没有观察到 capability 越权或隐藏递归调用，能力边界校准通过。
3. capability gate 没有改变基础 DB ReAct 的主要推理路径，也没有单独解决
   `UNVERIFIED_FINAL`、聚合、过滤或输出契约问题。
4. E4-R0 证明 capability gate 可用于后续机制隔离，不应宣称它带来准确率提升；v0.14 后续实验使用选定 O* 作为内容父配置，同时继承该能力门控原则。

详细逐题比较见 [e4_r0_vs_e0_first50.md](e4_r0_vs_e0_first50.md)。
