# E4-A smoke4 run2 诊断

运行：`results/e4_a_smoke4_run2.json`；轨迹：`trace/e4_a_smoke4_run2/`；QueryPlan 协议版本：2。

## 1. 结论

run2 修复了 run1 的协议故障，但没有证明 E4-A 的语义机制有效。协议门禁通过，4 题均生成合法初始 QueryPlan、执行 SQL 并正常结束；然而准确率仍为 0/4，四题的首次执行均已错误，且运行过程中从未执行过正确 SQL。因此当前分歧起点不是 FINAL，而是初始题目形式化或更早的 Schema 语义。

不能直接启动 core197。按照实验计划的停止规则，应先修 QueryPlan schema/adherence，再用新目录运行协议 smoke。

## 2. run1 → run2

| 指标 | run1 | run2 | 解释 |
|---|---:|---:|---|
| Accuracy | 0/4 | 0/4 | 语义结果没有改善 |
| RUNNER_OR_API | 2 | 0 | 协议/运行故障已消除 |
| 轨迹 steps | 28 | 18 | 无效重试减少 |
| 首次分歧 | 3 个首次错误执行 + 1 个未执行 FINAL | 4 个首次错误执行 | 问题已从协议层收敛到计划语义层 |
| ever correct | 0/4 | 0/4 | 没有“先对后错”轨迹 |

## 3. 与 E3-C 同题配对

| ID | E3-C → E4-A | 首个错误计划位置 | E3-C tokens | E4-A tokens | 判断 |
|---|---|---|---:|---:|---|
| `bird_1166` | SQL 完全相同 | `Diagnosis` 绑定到 `Examination`，gold 使用 `Patient` | 7,034 | 10,582 | 未改善；字段来源歧义需人工复核 |
| `bird_1251` | 仅增加 alias，核心 SQL 相同 | `required tables/join path` 在计划中已遗漏 | 4,753 | 6,776 | 未改善；gold 的额外 `Examination` join 需复核 |
| `bird_1031` | 逐球员年龄 → 全局平均年龄 | `answer_type=scalar`、`AVG(age)` | 21,874 | 11,351 | 明确语义回退：计划把 rows 错写成 scalar |
| `bird_1011` | 都只返回拼接姓名 | `column_count=1`，未保留 driver identity 的原始输出契约 | 14,436 | 27,723 | 输出契约未改善，且调用从 2 增至 4 |

四题合计 tokens 从 48,097 增至 56,432，增加 8,335（+17.33%）。此成本没有换来恢复题。

## 4. 马尔可夫链式分歧定位

本轮四条轨迹都符合：

```text
question / hint / retrieved context
  → initial QueryPlan（首次语义分歧）
  → SQL 忠实执行错误计划
  → nonmatching observation
  → FINAL 保留或改写错误 SQL
```

现有 adherence 主要检查投影数和 `GROUP BY/HAVING/ORDER BY/LIMIT` 是否与计划一致。它只能回答“SQL 是否遵守计划”，不能回答“计划是否忠实于题目”。因此 3/4 adherence 通过并不代表语义正确：它恰好说明 SQL 忠实实现了错误计划。

逐题最早可见分歧：

- `bird_1031`：初始计划把逐实体 rows 改写成 global scalar，并自行引入 `AVG`；
- `bird_1011`：初始计划直接固定为一列 `full_name`，输出列数错误在 SQL 前已经形成；
- `bird_1166`：初始计划把同名字段绑定到错误所属表；
- `bird_1251`：初始计划的表集合已经只有 `Laboratory`，后续 SQL 无法恢复遗漏 join。

## 5. 修复范围

QueryPlan schema v3 只修改 E4-A 在线形式化，不改变 E3-C Offline Schema Context、few-shot、模型或预算：

1. 增加 `answer_scope`，区分 `per_entity_rows`、`single_entity_row`、`global_scalar` 和 `boolean`；
2. 将 `output_columns` 改为逐列结构，记录顺序、语义项、完整 `Table.column` 来源、SQL 表达式、来源理由和聚合；
3. 增加 `required_tables`，并把表是否出现在 SQL 纳入 adherence；
4. 增加 `aggregation_scope` 和 `aggregation_justification`，无问题文本依据时不得自行把 rows 压成全局聚合；
5. 解析器拒绝 answer type/scope、输出列数、字段所属表和聚合声明内部不一致的计划。

这能阻止“内部矛盾计划”，但不会使用 gold 在线判定计划正确。`bird_1166` 和 `bird_1251` 仍需独立人工语义审计，不能据此写入 eval-specific 规则。

## 6. 下一门禁

先运行 QueryPlan schema v3 的 smoke3，并使用新 output/trace。协议审计通过只说明机制可运行；E4-A 是否有效仍必须在固定 core197 上通过目标错误净下降和 recovered > regressed 判断。若 smoke3 仍大量产生题目范围与结构化计划一致但语义错误的情况，应停止增加 Prompt 字段，转为人工过滤/gold 审计或后续 E5 的上下文访问假设。
