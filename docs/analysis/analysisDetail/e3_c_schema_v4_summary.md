# E3-C Schema v4：完整 197 题结果

> 结论：E3-C 在当前单次完整运行中是**有效的 Schema 机制候选**。它相对 E0 两次运行均值提高 `4.82 pp`；但平均 total tokens 增加 `14.29%`，因此不能称为效率改进，也暂不能称为最终架构。
>
> **2026-08-07 分类更正**：原文档报告"把 Schema/Join 失败从 E0 平均 19 条降到 15 条"，这两个数字都来自修复前的分类器（未检测 JOIN key 差异，见 `docs/analysis/README.md` §4.1）。用修复后的分类器重新统计：E0 两次运行 Schema/Join 平均为 `48.5` 条（run1=49、run2=48），E3-C 本身为 `46` 条，降幅只有约 `-5.2%`（原报告为 `-21.05%`）。**Schema/Join 在修复后的 E3-C 失败集合里仍是最大类别（46/120=38.3%），不是 AGGREGATION_REASONING**（见下方 §5）。这说明 E3-C 的 Schema 机制方向是对的，但远没有解决 Schema/Join 问题——它甚至还是 E3-C 运行后最大的残留类别。准确率、recovered/regressed 题数不受影响，E3-C"接受"的结论不变。

## 1. 运行身份与配置边界

- 正式运行：`e3_c_schema_v4_core197_run3`
- run_id：`20260714T090249Z-4d55cdb8`
- 状态：`complete`，完成 `197/197`
- 模型：`azure/seminar-gpt-5.4-mini`
- 数据：固定 `bird_cleancore_ids.json` 197 题
- train few-shot：`k=1`
- Prompt：`clean-protocol-v1`，不含任务 SQL 规则和示例
- Query patterns / Query Mining：关闭（`query_pattern_mode=none`）
- Offline Schema：`e3-f-schema-v4`
- Schema 交付：确定性 `offline-retrieval`，替换逐题完整 Schema 注入
- capability gate：开启，只允许 `execute` 和 `sample_values`
- Schema artifact SHA-256：`ed713b0689feddead605d51f4586913a093dd30310f3f0337f670f3e92d70e80`

`e3_c_schema_v4_core197_run2` 的 197 条失败全部来自同一个 Azure deployment/API 错误，不属于模型或 E3-C 机制结果，不能与本次运行合并。

## 2. 准确率

| 指标 | E3-C |
|---|---:|
| 正确数 | 77 / 197 |
| 执行准确率 | **39.09%** |
| `both_wrong` | 25 / 137 = 18.25% |
| `canary` | 52 / 60 = 86.67% |
| simple | 29 / 50 = 58.00% |
| moderate | 31 / 96 = 32.29% |
| challenging | 17 / 51 = 33.33% |
| 正常 `final` 终止 | 197 / 197 |

| 数据库 | 正确 / 总数 |
|---|---:|
| california_schools | 5 / 15 |
| card_games | 8 / 24 |
| codebase_community | 7 / 22 |
| debit_card_specializing | 6 / 14 |
| european_football_2 | 11 / 19 |
| financial | 3 / 13 |
| formula_1 | 11 / 29 |
| student_club | 9 / 14 |
| superhero | 5 / 7 |
| thrombosis_prediction | 6 / 23 |
| toxicology | 6 / 17 |

## 3. 成本与延迟

| 指标 | 总量 | 每题平均 |
|---|---:|---:|
| LLM 调用 | 538 | 2.73 |
| prompt tokens | 1,395,178 | 7,082.12 |
| completion tokens | 1,660,283 | 8,427.83 |
| reasoning tokens | 1,543,761 | 7,836.35 |
| total tokens | 3,055,461 | 15,509.95 |
| cached prompt tokens | 676,864 | 3,435.86 |
| 延迟 | 8,616.16 s | 43.74 s |

共有 9 次 LLM 调用缺少 usage，因此 token 统计是已记录调用的下界。相对 E0 两次运行均值，E3-C 的 prompt tokens/题增加 `9.61%`，total tokens/题增加 `14.29%`，延迟/题增加 `4.63%`；LLM 调用数基本不变（`-0.28%`）。

## 4. 控制流诊断

120 个失败的首要 trace 标签如下。它们描述提交路径，不等同于语义根因。

| 首要 trace 标签 | 数量 |
|---|---:|
| `UNVERIFIED_FINAL` | 96 |
| `SEMANTIC_REVIEW_REQUIRED` | 8 |
| `AGGREGATION_REASONING` | 7 |
| `SCHEMA_LINKING` | 4 |
| `OUTPUT_CONTRACT` | 3 |
| `TOOL_ERROR` | 2 |

96 个 `UNVERIFIED_FINAL` 的细分为：

| 子类 | 数量 |
|---|---:|
| `final_sql_rewritten_after_incorrect_observation` | 79 |
| `final_sql_changed_after_unparseable_observation` | 10 |
| `final_without_db_execution` | 5 |
| `final_sql_rewritten_after_successful_observation` | 1 |
| `final_sql_rewritten_after_correct_observation` | 1 |

因此不能把 96 条统称为“FINAL 错误”。其中绝大多数最终仍由 SQL 的聚合、过滤、输出或 Schema 语义造成。

## 5. 全部 120 条失败的语义归因（2026-08-07 已用修复后分类器更新）

逐题文件为 [`e3_c_schema_v4_semantic_failures.csv`](e3_c_schema_v4_semantic_failures.csv)（此 CSV 尚未随分类器一并重新导出，下表以重新生成的 `trace/e3_c_schema_v4_core197_run3/classification_sheet.csv` 为准），覆盖 `120/120` 个失败。

| 实际失败归因 | 数量（修复后） | 占全部失败 | 细分 | 原数量 |
|---|---:|---:|---|---:|
| `SCHEMA_LINKING` | 46 | 38.33% | 表/Join 路径 33；JOIN key/条件 13（新增子类） | 原 15（12.50%） |
| `AGGREGATION_REASONING` | 29 | 24.17% | 聚合/分组 23；排序 6 | 原 45（37.50%） |
| `OUTPUT_CONTRACT` | 28 | 23.33% | 不变 | 28（23.33%） |
| `SEMANTIC_REVIEW_REQUIRED` | 15 | 12.50% | 过滤范围或表达式 15 | 原 30（25.00%） |
| `TOOL_ERROR` | 2 | 1.67% | 不变 | 2（1.67%） |

**最大类别从 `AGGREGATION_REASONING`（原 45 条）变为 `SCHEMA_LINKING`（现 46 条）**。以上语义标签由 SQL 结构差异和 trace 自动归因，仍适合做全量机制统计；其中 15 条过滤类仍应进入 `F-Audit`（原为 30 条，抽样范围需相应调整），人工区分 Agent 错误、数据值语义和 gold 歧义，不能把自动标签当作最终人工裁决。轨迹复核还发现，历史分类器会在没有结构化 `db.execute` 时退回消息文本解析，因此部分"unparseable observation"实际是多 Python block 被旧 REPL 静默丢弃，而不是数据库返回了不可解析结果（这部分与本次分类器修复无关）。

## 6. Retrieval audit

完整逐题审计：

- [`e3_c_schema_v4_core197_run3_retrieval_audit.csv`](e3_c_schema_v4_core197_run3_retrieval_audit.csv)
- [`e3_c_schema_v4_core197_run3_retrieval_audit.json`](e3_c_schema_v4_core197_run3_retrieval_audit.json)

| Retrieval 诊断 | 数量 |
|---|---:|
| 正确 | 77 |
| 所需详细 Schema 完整，但仍语义失败 | 107 |
| gold 详细字段缺失或只在 compact index 中 | 12 |
| gold 详细表缺失 | 1 |

关键解释：`107/120` 个失败的 gold 表和字段都已在详细上下文中，说明 E3-C 剩余失败主要不是检索召回问题，而是拿到正确 Schema 后仍然推理错误。13 个与详细上下文缺失相关的失败中，仅 `bird_1014` 是表级缺失，其余 12 个是字段级详细信息缺失。

检索行为统计：

- 每题选择表数：平均 `5.30`，中位数 `6`，范围 `3–8`。
- 197/197 有正 lexical seed，197/197 执行路径扩展，132/197 执行 FK 邻居扩展。
- 118/197 存在被 budget 截断的候选表。
- 79/197（40.10%）仍选择了该数据库全部表；相比旧 Schema v3 的“每题全表注入”已有实质压缩，但压缩还不充分。
- 最终 SQL 使用详细上下文外表的题目只有 4 个，其中 2 个正确、2 个失败。

## 7. 判定

逐轮状态转移和首错位置另见 [`e3_c_schema_v4_trajectory_audit.md`](e3_c_schema_v4_trajectory_audit.md)。该审计覆盖全部 120 个失败、165 次结构化 `db.execute` 和 120 次 FINAL：91 个失败在 retrieval 完整时第一次可判定执行已经偏离，13 个从 retrieval 缺失风险开始，15 个在 retrieval 完整时无候选 SQL execution，1 个只能延后定位。另有 2 个 retrieval 风险项也没有执行候选 SQL，因此总计 17 题无结构化 `db.execute`。失败集合中没有一次 `wrong execution → correct execution` 恢复；只有 `bird_228` 曾执行正确后改写成错误 FINAL。

### 接受 E3-C 的证据

1. 相对 E0 两次均值，准确率从 `34.26%` 提升到 `39.09%`，提高 `4.82 pp`。
2. Schema/Join 失败从 E0 平均 `48.5` 条降到 `46` 条，减少约 `5.2%`（2026-08-07 更正：原报告 `19→15`/`-21.05%` 用的是修复前分类器，见 §5 的更正说明；修复后降幅小得多，且 Schema/Join 仍是 E3-C 本身最大的残留类别）。
3. E0 的稳定 Schema 失败中有部分在 E3-C 中恢复（原报告"16 个稳定 Schema 失败中恢复 4 个"同样来自修复前分类器，尚未用新分类器重新核算准确的稳定失败-恢复对应关系，此处不再引用旧数字）；E0 的 62 个稳定正确题没有一题在 E3-C 中退化（这一条不受分类修复影响）。
4. E0 的 124 个稳定失败中共恢复 10 个，改善不只来自不稳定题目（不受分类修复影响，恢复题数由 correct/incorrect 原始判定决定）。
5. 运行 197/197 正常结束，没有 API/runner 失败污染准确率。

### 限制

1. 目前只有一次完整 E3-C 运行，尚未测量同配置方差。
2. 准确率提升伴随 `14.29%` total-token 成本上升。
3. E3-C 同时包含 Schema v4 内容、确定性片段选择、完整 Schema 替换和 capability gate；其中 gate 已单独校准为近似中性，但仍不能从本次运行拆分 Schema 内容与检索策略各自的贡献。
4. 13 个失败仍与详细 Schema 缺失有关，79 题仍退化为全表选择，retrieval 还有明确优化空间。

最终判定：**接受 E3-C 作为后续实验的 Offline Schema 父配置；它对准确率和 Schema/Join 错误有效，但不接受“它提升效率”这一说法。** 后续机制实验应保留 E3-C，同时单独优化 retrieval budget；不要把 Query Mining 混入本次因果结论。

## 8. 根据轨迹确定的下一步

轨迹报告已经把证据映射到具体改进机制，详见 [`e3_c_schema_v4_trajectory_audit.md`](e3_c_schema_v4_trajectory_audit.md#9-轨迹证据到改进机制的映射)。执行顺序为：

1. 先修复 17 个无候选 SQL execution 暴露的工具协议问题：每轮限制一个 Python block、底层不再静默丢弃后续 block，并保证结构化 observation 可见；
2. 锁定 E3-C Schema v4 + `k=1` few-shot 为父配置；
3. 运行 E4-A，在首个 SQL 前由同一次 Root 响应生成 QueryPlan + Output Contract，不增加 Planner call；
4. QueryPlan 增加 `candidate_purpose`、`expected_result_shape`、`unresolved_assumptions` 和 observation 后的 `revision delta`，用于区分 plan 错误、SQL adherence 错误和有害改写；
5. 并行执行 F-Audit；E4-A 后重新生成语义、retrieval 与 trajectory audit。

当前证据不支持直接进入递归或只增加重试：81 个失败在 Turn 1 已经出现 nonmatching execution，而失败集合中没有一次 `wrong execution → correct execution` 恢复。strict verified-final 也不作为下一步主变量，因为 E1 已显示它只能约束错误传播，不能修复初始语义错误。
