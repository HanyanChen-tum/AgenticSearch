# BIRD E1 verified-final 单次运行报告

- 实验：E1 strict verified-final
- Profile：`clean-e1`
- Run ID：`20260713T200839Z-23a93559`
- 比较口径：落盘 71 条中的前 70 条，第 71 条不计入本报告
- 状态：时间预算下的部分运行

## E1流程
读取问题  
  ↓  
检索一个 train few-shot 示例  
  ↓  
拼接 Hint、Schema、few-shot  
  ↓  
模型调用 `db.sample_values` 或 `db.execute`  
  ↓  
获得数据库 observation  
  ↓  
ReAct 修改 SQL（生成 SQL → 执行 → 看到错误 → 修改 SQL → 再执行 → 看到结果）  
  ↓  
模型调用 `FINAL`  
  ↓  
系统检查最终 SQL 是否执行过、执行是否成功、是否为空、是否等于最近一次成功执行的 SQL  
  ↓  
检查通过：接受最终 SQL  
  ↓  
检查失败：记录 `final.blocked`，反馈原因并继续 ReAct  
  ↓  
执行 predicted SQL 和 gold SQL  
  ↓  
比较答案  
  ↓  
保存结果、trace、token 和错误分类


## 运行结果

| 指标 | 结果 |
|---|---:|
| 正确数 | 28/70 |
| 准确率 | 40.00% |
| 正常 `final` 终止 | 65 |
| `MaxIterationsError` | 5 |

## 成本

| 指标 | 总计 | 每题 |
|---|---:|---:|
| LLM 调用 | 386 | 5.51 |
| Prompt tokens | 1,064,668 | 15,209.54 |
| Completion tokens | 819,791 | 11,711.30 |
| Reasoning tokens | 737,521 | 10,536.01 |
| Total tokens | 1,884,459 | 26,920.84 |
| DB 工具调用 | 251 | 3.59 |
| `db.execute` 调用 | 207 | 2.96 |
| 延迟（秒） | 4,426.29 | 63.23 |

存在 1 次 usage 和 reasoning usage 缺失，因此 token 数是下界。

## Verified-final 行为

- `final.blocked`：103 次。
- 至少触发一次阻断的问题：63/70（90%）。

门控不是只处理少数异常提交，而是在绝大多数题目上引入额外 ReAct 循环。这解释了
LLM 调用、DB 调用、token 和延迟的显著增长。

## 错误类别

| 错误类别 | 数量 |
|---|---:|
| `AGGREGATION_REASONING` | 13 |
| `OUTPUT_CONTRACT` | 10 |
| `SEMANTIC_REVIEW_REQUIRED` | 9 |
| `RUNNER_OR_API` | 5 |
| `SCHEMA_LINKING` | 5 |

### 错误子类别

| 子类别 | 数量 |
|---|---:|
| `aggregation_or_grouping_mismatch` | 12 |
| `filter_scope_or_expression_mismatch` | 9 |
| `output_column_count_mismatch` | 9 |
| `table_or_join_path_mismatch` | 5 |
| `missing_final_sql` | 5 |
| `sort_direction_or_order_scope_mismatch` | 1 |
| `yes_no_vs_row_output_mismatch` | 1 |


聚合或分组粒度错误：12；
过滤范围或表达式错误：9；
输出列数量错误：9；
表或连接路径错误：5；
缺少最终 SQL：5；
排序方向错误：1；
YES/NO 与行输出形式错误：1。

## 与 E0 的结论

相同前 70 题上，E0 run1/run2 为 41.43%/42.86%，均值 42.14%；E1 为 40.00%，
下降 2.14 个百分点。E1 的 LLM 调用和 token 约为 E0 的两倍，延迟约为 1.75 倍。

配对结果中，E1 没有恢复任何 E0 两次都失败的题，却让 3 道 E0 两次都正确的题退化。
`UNVERIFIED_FINAL` 标签归零只说明形式约束生效；原本被该标签覆盖的聚合、过滤、
输出和 Schema 错误仍然存在。

## 决策

拒绝 strict verified-final。后续配置不启用该门控，也不安排独立 FINAL 同步实验。
Root 仍应在正常 ReAct 中测试候选 SQL，但当前优化目标是语义构造，而不是继续增加
FINAL 控制循环。

详细配对变化见 [e1_vs_e0_first70.md](e1_vs_e0_first70.md)。

## 错误轨迹分析

E1 的主要问题不是数据库无法执行 SQL，而是执行成功后仍然产生了语义错误。典型轨迹是：

```text
生成 SQL A
  ↓
执行 SQL A，得到结果
  ↓
模型修改为 SQL B
  ↓
直接 FINAL(SQL B)
  ↓
strict verified-final 阻止提交
  ↓
反馈 BLOCKED FINAL，继续 ReAct
```

因此，E1 将原先的 `UNVERIFIED_FINAL` 现象暴露成了更具体的语义错误，但没有真正修复这些错误。

主要错误集中在：

- `AGGREGATION_REASONING`：聚合、分组或查询粒度不匹配；
- `OUTPUT_CONTRACT`：返回列数量、列顺序或 YES/NO 形式不符合问题要求；
- `SEMANTIC_REVIEW_REQUIRED`：过滤字段、过滤范围或表达式作用层级不正确；
- `SCHEMA_LINKING`：表、字段或连接路径选择错误；
- `RUNNER_OR_API`：输出缺失、运行中断或其他基础设施问题。

`UNVERIFIED_FINAL` 归零只说明最终 SQL 的执行证据链被强制建立，并不代表 SQL 语义正确。E1 没有从 E0 的稳定失败中恢复题目，且使部分 E0 稳定正确题退化，因此 strict verified-final 不应作为后续 Agent 的默认机制。

## 错误到改进机制映射

| E1 剩余错误 | 数量 | 为什么 E1 没有解决 | 后续改进 | 对应 v0.14 实验 |
|---|---:|---|---|---|
| 聚合与排序 | 13 | 门控只要求执行 SQL，不提供正确 grain 或聚合计划 | Root QueryPlan 明确粒度、聚合、排序和 Top-K | `P` |
| 输出契约 | 10 | SQL 可执行不代表列数、顺序和回答形式正确 | 把 answer type 和 output columns 纳入 QueryPlan | `P` |
| 过滤语义 | 9 | observation 不能自动判断边界和作用层级 | 结构化条件计划；低置信度样本先人工复核 | `P`，后续 `C-P` |
| Schema/Join | 5 | 重复执行错误路径不会提供正确字段来源 | metadata、PK/FK 和 Join path artifact | `M` |
| 缺失 FINAL | 5 | 额外循环耗尽迭代预算 | runner 记录终止原因；不再使用 strict gate | 基础设施 |

E1 的作用已经回答完毕：形式验证会消除 `UNVERIFIED_FINAL` 标签，但不能修复语义，且成本和回退不可接受。后续不从 E1 继续叠加机制。

当前执行顺序以 v0.14 为准：

```text
E3-RF → 选择 O* → P/M 独立消融 → R1E-S smoke
→ C-P → C-P-Budget vs C-P-Leaf
```

准确率变化小于约 2 pp 只记录为趋势；最终决策还要结合目标错误净变化、recovered/regressed、稳定失败恢复数和成本。
