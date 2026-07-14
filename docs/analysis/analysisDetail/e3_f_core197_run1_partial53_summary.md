# E3-F core197 run1：前 53 题中断结果

> 本报告只分析已经完成的前 53/197 题。运行状态为 `interrupted`，不能作为 E3-F 的完整准确率，也不能外推到全部 11 个数据库。

## 1. 运行身份与配置边界

- 运行：`e3_f_core197_run1`
- run_id：`20260714T075259Z-f3c7e719`
- 完成时间：2026-07-14
- 完成范围：53/197；仅覆盖 4 个数据库
- 模型：`azure/seminar-gpt-5.4-mini`
- `reasoning_effort=high`，`temperature=0`，`max_iterations=8`
- train few-shot：`k=1`
- Query Mining：历史版 `train-mined-v1`，artifact SHA-256=`eddf772e51a1322e0a263f2425c89774e9984b4714aaf36c208df01920ac32ee`
- Offline Schema：历史版 `e3-f-schema-v3`，artifact SHA-256=`59975ed59948c5f47654cc0ebffbf36cebdb74df372f71dbaf81ba90a1a79bae`
- capability gate：开启

这次运行发生在 `train-mined-v2` 和 `e3-f-schema-v4` 修复之前。因此它只能记为“旧 E3-F v1/v3 的部分诊断”，不能用于评价新版 E3-F，也不能与后续 E3-C Schema v4 结果混合。

## 2. 部分结果

| 指标 | 前 53 题 |
|---|---:|
| 正确数 | 21 / 53 |
| 执行准确率 | 39.62% |
| `both_wrong` | 7 / 36 = 19.44% |
| `canary` | 14 / 17 = 82.35% |
| simple | 8 / 14 = 57.14% |
| moderate | 8 / 24 = 33.33% |
| challenging | 5 / 15 = 33.33% |
| 正常 `final` | 52 |
| Azure policy `BadRequestError` | 1 |

数据库分布并不均衡：`debit_card_specializing` 5/14、`student_club` 10/14、`thrombosis_prediction` 6/23、`european_football_2` 0/2。其余 7 个数据库尚未运行，所以 39.62% 不是 core197 的代表性估计。

## 3. 成本与延迟

| 指标 | 总量 | 每题平均 |
|---|---:|---:|
| LLM 调用 | 162 | 3.06 |
| prompt tokens | 364,337 | 6,874.28 |
| completion tokens | 506,283 | 9,552.51 |
| reasoning tokens | 466,705 | 8,805.75 |
| total tokens | 870,620 | 16,426.79 |
| cached prompt tokens | 186,624 | 3,521.21 |
| 延迟 | 2,706.39 s | 51.06 s |

有 4 次 LLM 调用缺少 usage，50/53 题的 usage 完整。因此 token 统计略有低估风险。

## 4. 自动控制流分类

32 个失败的首要自动标签如下：

| 自动标签 | 数量 |
|---|---:|
| `UNVERIFIED_FINAL` | 24 |
| `OUTPUT_CONTRACT` | 2 |
| `SEMANTIC_REVIEW_REQUIRED` | 2 |
| `AGGREGATION_REASONING` | 1 |
| `SCHEMA_LINKING` | 1 |
| `RUNNER_OR_API` | 1 |
| `TOOL_ERROR` | 1 |

24 个 `UNVERIFIED_FINAL` 中，20 个是 `final_sql_rewritten_after_incorrect_observation`，2 个没有执行 FINAL SQL，2 个在 observation 无法解析后改写 SQL。这个标签描述提交路径，不等于失败的语义根因。

## 5. 全部 32 个失败的语义归因

逐题对 question、预测 SQL、gold SQL 和 trace 复核后，主语义原因汇总为：

| 实际原因层 | 数量 | 占全部失败 |
|---|---:|---:|
| `AGGREGATION_REASONING` | 9 | 28.13% |
| `OUTPUT_CONTRACT` | 9 | 28.13% |
| `SEMANTIC_REVIEW_REQUIRED` | 7 | 21.88% |
| `SCHEMA_LINKING` | 6 | 18.75% |
| `RUNNER_OR_API` | 1 | 3.13% |

详细的 32/32 逐题归因保存在 `e3_f_core197_run1_semantic_failures.csv`。主要表现为：

- 聚合：月度峰值误写为单行最大值、百分比基数错误、`COUNT(*)` 与 `COUNT(DISTINCT customer)` 混淆、Top customer 选择标准错误。
- 输出：多列/少列、应返回月份却返回 `YYYYMM`、YES/NO 与逐行结果不一致。
- Schema：列归属表错误、缺少 `yearmonth`/`gasstations` Join、把加油站国家误作客户币种。
- 过滤和数据语义：年龄基准日期、边界条件、值编码、布尔优先级与题目/gold 歧义。

## 6. Offline 检索审计

### 6.1 Schema v3 实际没有形成有效压缩

- 53/53 题的 gold 表和字段都出现在详细上下文中，没有 detailed table/column miss。
- 但这 53 题中，Schema v3 每题都选择了当前数据库的**全部表**：5 表、8 表、3 表或 7 表。
- 平均选择 5.00 张表；21 题还需要用 `ranked_budget_fill` 补入低相关表。

因此“零 Schema miss”不能证明检索准确，而是因为这些数据库的表数均未超过 `max_tables=10`，旧版退化成了近似完整 Schema 注入。这正是 Schema v4 删除无条件 budget fill、限制邻居并记录截断原因的原因。

### 6.2 Query Mining v1 匹配过宽

- 52/53 题使用 `positive_score_top_k`，1/53 使用支持度 fallback。
- 平均每题交付 2.85 张 pattern 卡片。
- 只有 16/53（30.19%）至少有一张选中卡片的结构 shape 与 gold 完全一致。
- shape exact-match 组为 9/16 正确，无 exact-match 组为 12/37 正确；样本很小且受题目难度混杂，只能作为相关性诊断。
- 正确题平均 2.90 张卡，失败题平均 2.81 张卡；卡片数量本身没有解释准确率。

旧 v1 以宽泛词和 intent cue 排序，并强制 Top-K/fallback，无法证明所交付结构适用于当前问题。这与后续 v2 在跨数据库门禁下 0 个 slot 通过、选择安全 abstain 的结果一致。

## 7. 同题配对比较

所有比较只使用 E3-F 已完成的相同 53 个 ID：

| 实验 | 同题正确率 | 相对 E3-F | 平均 total tokens/题 |
|---|---:|---:|---:|
| E0 run1 | 19/53 = 35.85% | E3-F +3.77 pp | 11,023.26 |
| E0 run2 | 20/53 = 37.74% | E3-F +1.89 pp | 12,385.91 |
| E0 两次均值 | 36.79% | E3-F +2.83 pp | 11,704.59 |
| E3-A | 20/53 = 37.74% | E3-F +1.89 pp | 11,565.96 |
| E3-B | 20/53 = 37.74% | E3-F +1.89 pp | 12,991.62 |
| 旧 E3-C run2 | 23/53 = 43.40% | E3-F -3.77 pp | 14,244.40 |
| 旧 E3-F v1/v3 | 21/53 = 39.62% | — | 16,426.79 |

相对 E0 两次同题均值，准确率只提高 2.83 pp，而平均 total tokens 增加 40.34%。相对旧 E3-C 的同题部分，E3-F 少 2 题且 token 增加 15.32%。旧 E3-C 配置不同且同样是中断运行，这一行只用于诊断，不能作为正式消融结论。

## 8. 结论

这 53 题没有提供“旧完整 Offline 系统有效”的证据：准确率增量小于单次运行波动能够合理解释的范围，成本明显上升，Schema v3 实际退化成全表注入，Query Mining v1 的 exact shape 覆盖仅 30.19%。

失败仍集中在聚合、输出契约、过滤语义和 Join/字段归属，说明 v1 pattern 卡并没有针对性解决 E0 的主要错误轨迹。该部分运行支持停止 v1/v3，并验证了此前升级 Schema v4、将 Query Mining v2 设为严格门禁和 abstain 的必要性；它不应继续补跑到 197 题。

