# E4-A smoke4 run3 诊断

运行：`results/e4_a_smoke4_run3.json`；轨迹：`trace/e4_a_smoke4_run3/`；QueryPlan schema：v3。

## 1. 结论

run3 仍为 0/4，不能据此宣称 E4-A 有准确率收益；但 v3 对两条目标语义产生了可解释的局部改善。协议门禁未通过，因为 `bird_1031` 的首次计划把三个数组写成 `null`，下一次响应又遗漏 Python closing fence；系统均在 SQL 执行前拦截，第三次计划合法后才执行。

因此当前不能运行 core197。下一步只做单题协议重试，不再根据这四题的 gold 增加 Prompt 规则。

## 2. 与 run2 的变化

| ID | run2 初始计划 | run3 初始计划 | run3 剩余差异 | 判断 |
|---|---|---|---|---|
| `bird_1031` | 错误设为 global scalar，并引入 `AVG(age)` | 改为 `per_entity_rows`，无聚合，一名球员一行 | 年龄公式和额外排序与 gold 不同；adherence 捕获计划外 `ORDER BY` | 聚合/回答范围获得明确改善，但未恢复为正确题 |
| `bird_1011` | 拼接 full name，仅 1 列 | 分离 forename/surname，共 2 列 | gold 还返回 driverId，且时间表达式不同 | 输出契约部分改善，仍未完整匹配 |
| `bird_1166` | `Examination.Diagnosis` | 仍为 `Examination.Diagnosis`，并显式记录该假设 | gold 使用 `Patient.Diagnosis` | Offline 字段描述相同，需人工复核，不应写入特例规则 |
| `bird_1251` | 只使用 Laboratory | 仍只使用 Laboratory | gold 额外连接 Patient 和 Examination | 题面未明确 Examination 限制，需人工复核 gold |

run3 semantic labels 为 1 个 Output Contract、1 个 Schema/Join、2 个 Semantic Review（其中一个外层控制流标签为 `UNVERIFIED_FINAL`）。四题仍全部在首次执行偏离，`ever_correct=0`。

## 3. 成本

| 配置 | 四题 total tokens | 相对 E3-C | 相对 run2 |
|---|---:|---:|---:|
| E3-C 同题 | 48,097 | — | — |
| E4-A run2 | 56,432 | +17.33% | — |
| E4-A run3 | 73,082 | +51.95% | +29.50% |

run3 的主要额外成本来自 `bird_1031` 的两次协议修正：该题 39,795 tokens、4 次 LLM call。其余三题均为 2 次 call。

## 4. 协议门禁

`scripts/audit_e4_a_smoke.py` 的结果为 `passed=false`：

- `bird_1011`、`bird_1166`、`bird_1251`：各一个合法计划、一次执行、一次 adherence，协议通过；
- `bird_1031`：两个 initial events，其中第一个因 `group_by/aggregates/having=null` 无效，并有一个未闭合 Python fence 的 action-contract failure；最终安全恢复，但不满足严格 first-try 门禁。

Prompt 只补充通用 JSON 语法约束：所有列表字段必须用数组，空值用 `[]` 而不是 `null`，并明确闭合两个 fenced blocks。单题重试通过后，可把“run3 三题通过 + retry 一题通过”作为协议 smoke 完成；E4-A 的有效性仍只能由 core197 的 paired error migration 判断。
