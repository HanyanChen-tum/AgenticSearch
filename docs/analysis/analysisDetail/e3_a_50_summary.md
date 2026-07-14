# BIRD E3-A 50 题筛选运行报告

- 实验：E3-A train-only query patterns 添加实验
- Profile：`e3-a`
- Run ID：`20260713T230734Z-57339b35`
- 题目：`bird_cleancore_ids.json` 的 `both_wrong + canary`，按数据集顺序前 50 题
- 状态：历史筛选报告；完整 197 题已完成，应以 `e3_a_summary.md` 为主

## 机制与配置

E3-A 以 clean E0 为父配置，只增加 `train-static-v1` query pattern library：

- 来源仅为 `data/train_pool.json` 的 9,428 条 BIRD train SQL；
- 向 Prompt 注入通用结构检查：聚合粒度、过滤后聚合、top-k 排序、输出列契约、条件回答、`DISTINCT`、JOIN 路径和窗口排序；
- library 不包含 eval/dev Schema、取值、问题、答案或 SQL 示例；
- 保留 `clean-protocol-v1`、train-only `k=1` few-shot、`max_iterations=8` 和 high reasoning；
- 保持 `verified_final=false`、直接 context、非递归、无 Planner 和无 capability gate。

因此，本实验检验的是“通用 train SQL 结构提示”的增量，而不是 strict verified-final、递归、DB hints 或额外模型调用的效果。

## 流程

运行开始前
  ↓
读取 `data/train_pool.json` 的 9,428 条 train SQL
  ↓
统计 8 类 SQL 结构是否在训练集出现，生成固定的 train-only pattern library
（聚合粒度、过滤后聚合、top-k、输出列、条件回答、DISTINCT、JOIN、窗口排序）
  ↓
读取一条 BIRD mini-dev 评测问题
  ↓
检索 1 条 train few-shot 示例
  ↓
拼接 Hint、Schema、train few-shot 和同一份通用 pattern library
  ↓
模型调用 `db.sample_values` 或 `db.execute`
  ↓
获得数据库 observation
  ↓
ReAct 修改 SQL（生成 SQL → 执行 → 看到结果或错误 → 修改 SQL → 再执行）
  ↓
模型调用 `FINAL`
  ↓
E3-A 沿用 E0：接受可解析的 FINAL，不启用 strict verified-final
  ↓
执行 predicted SQL 和 gold SQL，比较答案
  ↓
保存结果、trace、token usage 和自动错误分类

pattern library 对所有评测题相同，只包含从 train SQL 归纳出的通用文字检查项；它不按当前 eval 题检索 train SQL，也不包含 dev/eval 的 Schema、值、问题、答案或 gold SQL。

## 运行结果

| 指标 | 结果 |
|---|---:|
| 正确数 | 22/50 |
| 准确率 | 44.00% |
| 终止方式 `final` | 50/50 |
| `MaxIterationsError` | 0 |
| `both_wrong` | 8/33（24.24%） |
| `canary` | 14/17（82.35%） |

| 难度 | 正确数 | 准确率 |
|---|---:|---:|
| simple | 9/14 | 64.29% |
| moderate | 9/22 | 40.91% |
| challenging | 4/14 | 28.57% |

## 成本

| 指标 | 总计 | 每题 |
|---|---:|---:|
| LLM 调用 | 140 | 2.80 |
| Prompt tokens | 259,852 | 5,197.04 |
| Completion tokens | 352,264 | 7,045.28 |
| Reasoning tokens | 322,404 | 6,448.08 |
| Total tokens | 612,116 | 12,242.32 |
| DB 工具调用 | 114 | 2.28 |
| `db.execute` 调用 | 73 | 1.46 |
| `db.sample_values` 调用 | 41 | 0.82 |
| 延迟（秒） | 1,798.49 | 35.97 |

所有 50 题的 usage 完整记录；没有 usage 缺失调用。

## 错误类别

| 错误类别 | 数量 | 占失败记录 |
|---|---:|---:|
| `UNVERIFIED_FINAL` | 23 | 82.14% |
| `AGGREGATION_REASONING` | 2 | 7.14% |
| `SCHEMA_LINKING` | 1 | 3.57% |
| `SEMANTIC_REVIEW_REQUIRED` | 1 | 3.57% |
| `OUTPUT_CONTRACT` | 1 | 3.57% |

| 子类别 | 数量 |
|---|---:|
| `final_sql_changed_after_test` | 22 |
| `final_without_db_execution` | 1 |
| `aggregation_or_grouping_mismatch` | 2 |
| `table_or_join_path_mismatch` | 1 |
| `filter_scope_or_expression_mismatch` | 1 |
| `output_column_count_mismatch` | 1 |

`UNVERIFIED_FINAL` 仍然是主要自动标签，因为 E3-A 与 E0 一样关闭 strict verified-final。它说明模型仍会在执行后改写 SQL；不说明 query patterns 本身失效，也不构成重新启用已被 E1 拒绝的硬门控的证据。

## 初步分析

1. E3-A 为 44.00%，高于同一 50 题上的 E0 run1 `38.00%` 和 E0 run2 `40.00%`。它首先提供了继续运行完整 197 题的筛选信号。
2. 聚合错误没有在小样本中明显消失：E3-A 有 2 条，E0 两次各有 1 条。因此不能仅凭 50 题宣称 pattern library 已解决聚合粒度问题。
3. E3-A 的 Prompt tokens/题高于 E0（5,197 对 4,172/4,664），符合增加结构提示的预期；总 tokens/题接近 E0 run2，尚未显示不可接受的成本放大。
4. 当前恢复题并不完全稳定，且仍有 `bird_1169` 对两次 E0 都发生退化。收益是否稳定、是否集中改善目标错误类别，需要完整 197 题的 paired analysis 才能判断。

## 错误到改进机制映射

该 50 题报告使用旧首要分类，`UNVERIFIED_FINAL` 遮住了底层语义，不再单独用于决定机制。改进方向以完整 197 题双标签结果为准：

| 错误方向 | 50 题可见信号 | 完整集后的改进 | 对应 v0.14 实验 |
|---|---|---|---|
| 聚合/排序 | 小样本仍有聚合错误 | 用 Root QueryPlan 明确 grain、aggregate、order/limit | `P` |
| 输出契约 | 存在列数错误 | 将列数、顺序、类型和回答形式纳入 QueryPlan | `P` |
| Schema/Join | 存在表/路径错误 | metadata + PK/FK + Join path | `M` |
| 过滤语义 | 小样本不足以确认 | 完整集显示可能改善；先人工复核，再测试条件计划 | `P`/`C-P` |
| 未验证 FINAL | 旧标签占多数 | 只做控制流诊断，不恢复 E1，不做 FINAL 同步 | 无独立实验 |

## 结论

E3-A 的完整 197 题运行已经完成，为 73/197（37.06%）。本文件只保留为“前 50 题筛选偏乐观”的历史证据，不再驱动后续实验。当前下一步是完成 E3-RF，并在 E0/E3-A/E3-RF 中选择 Offline 父配置 O*。

详细逐题比较见 [e3_a_50_vs_e0_first50.md](e3_a_50_vs_e0_first50.md)。
