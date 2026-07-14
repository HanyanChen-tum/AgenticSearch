# E3-A 与 E0 首 50 题对比分析

## 1. 比较口径

- E3-A：`results/e3_a_run1.json`，50/50 题完整完成；
- E0：`results/e0_core_run1.json` 和 `results/e0_core_run2.json` 中相同的 50 个 ID；
- 评测数据、模型、`k=1` train few-shot、`max_iterations=8` 与 high reasoning 对齐；
- E3-A 相对 E0 的唯一预期变化是 train-only `train-static-v1` query pattern library；
- E3-A 只有一次 50 题运行，因此本报告是筛选分析，不估计 E3-A 方差，也不作机制接受结论。

## 2. 机制区别与比较目的

| 项目 | E0 | E3-A | 是否是本次变量 |
|---|---|---|---|
| 系统 Prompt | `clean-protocol-v1` | 相同 | 否 |
| BIRD Hint、Schema、评测数据库 | 相同 | 相同 | 否 |
| train few-shot | 相同的 train pool、`k=1` | 相同的 train pool、`k=1` | 否 |
| DB ReAct 与工具 | `db.execute`、`db.sample_values` | 相同 | 否 |
| `FINAL` 与 verified-final | `verified_final=false` | 相同 | 否 |
| 递归、Planner、capability gate | 均未启用 | 均未启用 | 否 |
| query pattern library | 无 | 注入 `train-static-v1` 通用结构检查 | **是** |

实际送入模型的差别可以写成：

```text
E0 Prompt
= 问题 + Hint + Schema + 检索到的 1 条 train few-shot + DB observation

E3-A Prompt
= E0 Prompt
  + 固定的 TRAIN-ONLY SQL PATTERN LIBRARY
    - 先按被问实体聚合，再排序或 LIMIT
    - 聚合前保持过滤范围一致
    - 检查 top-k 的 ORDER BY 方向与分组顺序
    - 返回题目要求的所有列、顺序正确
    - 检查 DISTINCT、JOIN 路径和窗口排序是否需要
```

也就是说，E3-A 不是换了 ReAct、工具、模型或 few-shot；它只让模型在每次生成或修改 SQL 时，多看到一份从训练集 SQL 归纳出的通用检查清单。表中其他行“相同”正是为了排除这些因素，让准确率变化能够归因到这一个新增块。

E3-A 增加的 library 在运行前由 9,428 条 BIRD train SQL 统计得到，并对每题注入相同的通用检查项：聚合粒度、过滤后聚合、top-k 排序、输出列、条件回答、`DISTINCT`、JOIN 和窗口排序。它不含 eval/dev 的 Schema、值、问题、答案或 gold SQL。

因此，这个对比要回答的是：**train-only 的通用 SQL 结构模式，是否能在不改变 E0 的 Prompt、few-shot、DB ReAct 或推理预算的前提下，减少聚合、过滤、排序和输出契约错误。**

它不用于判断 strict verified-final 是否有效、递归 Leaf 是否有效、外部 context environment 是否有效，也不用于证明 query patterns 可以替代 few-shot；后者必须由后续 E3-RF 单独测试。

## 3. 总体结果与成本

| 指标 | E0 run1 | E0 run2 | E0 首 50 均值 | E3-A | E3-A 相对均值 |
|---|---:|---:|---:|---:|---:|
| 正确数 | 19/50 | 20/50 | 19.5/50 | 22/50 | +2.5 题 |
| 准确率 | 38.00% | 40.00% | 39.00% | 44.00% | +5.00 pp |
| Prompt tokens/题 | 4,172.38 | 4,663.84 | 4,418.11 | 5,197.04 | +17.63% |
| Total tokens/题 | 10,903.32 | 12,107.40 | 11,505.36 | 12,242.32 | +6.41% |
| LLM 调用/题 | 2.66 | 2.86 | 2.76 | 2.80 | +1.45% |
| 延迟/题（秒） | 35.10 | 40.19 | 37.64 | 35.97 | -4.44% |

E3-A 比两次 E0 都多答对，但增益仅对应 2 至 3 题。由于单次 50 题筛选不能排除采样波动，完整 197 题确认是必要条件。

## 4. 逐题配对结果

### 对 E0 run1

- 两者都正确：18 题；
- E3-A 恢复：4 题，`bird_1500`、`bird_1387`、`bird_1235`、`bird_1238`；
- E3-A 退化：1 题，`bird_1169`；
- 两者都失败：27 题。

### 对 E0 run2

- 两者都正确：19 题；
- E3-A 恢复：3 题，`bird_1472`、`bird_1500`、`bird_1350`；
- E3-A 退化：1 题，`bird_1169`；
- 两者都失败：27 题。

`bird_1500` 是唯一相对两次 E0 都恢复的题；`bird_1169` 则是唯一相对两次 E0 都退化的题。其他恢复只相对其中一次 E0 出现，不能视为稳定机制收益。

## 5. 错误分布

| 错误类别 | E0 run1 | E0 run2 | E3-A |
|---|---:|---:|---:|
| `UNVERIFIED_FINAL` | 27 | 25 | 23 |
| `AGGREGATION_REASONING` | 1 | 1 | 2 |
| `SEMANTIC_REVIEW_REQUIRED` | 2 | 2 | 1 |
| `OUTPUT_CONTRACT` | 0 | 1 | 1 |
| `SCHEMA_LINKING` | 1 | 0 | 1 |
| `RUNNER_OR_API` | 0 | 1 | 0 |

E3-A 的 `UNVERIFIED_FINAL` 略少，但该标签不是本实验目标，且 strict verified-final 已在 E1 被拒绝。更重要的聚合和输出契约错误在 50 题内没有形成稳定下降，因此完整 197 题必须比较错误类别、recovered/regressed IDs 与成本，而不仅比较总准确率。

## 6. 结论与下一步

E3-A 是有前景的 Offline Mining 添加组：同题 50 题准确率高于两次 E0，成本增量有限。但目前证据不足以接受该机制，也不足以运行 E3-RF。

下一步完整运行 E3-A 的 197 题确认组。若其相对 E0 仍有可接受改善，再运行完整 197 题的 E3-RF；否则将 E3-A 记录为小样本正向、完整集未确认或被拒绝的机制。
