# E4-A QueryPlan schema v3：完整 197 题结果

> 结论：**拒绝当前 E4-A 作为有效改进机制，回退到 E3-C。** E4-A 为 `71/197 = 36.04%`，比直接父配置 E3-C 的 `77/197 = 39.09%` 下降 `3.05 pp`。只恢复 3 题、回退 9 题；`recovered > regressed` 未满足，并新增 4 个无 FINAL 的运行失败。total tokens/题增加 `6.67%`。
>
> **2026-08-07 分类更正**：本文档原版基于修复前的语义分类器（该分类器只检查聚合/排序关键词是否出现，不比较 GROUP BY/ORDER BY 具体字段和 JOIN key，见 `docs/analysis/README.md` §4.1）。用修复后的分类器重新统计后，**聚合/排序失败净变化的方向是反的**：原文档报告"聚合/排序从 45 降到 41（-4，唯一改善的目标类）"，修复后实际是 **29 升到 33（+4，E4-A 自己的目标类别反而变差了）**；Schema/Join 则从原报告的"+1（轻微回退）"变为 **-4（实际改善）**。目标类（聚合+输出）的 recovered/regressed 也从"3:3 持平"变为 **3:5（净回退 2）**——`bird_1480`、`bird_565` 这两题此前被归为"过滤范围/表达式"回退，实际是聚合分组/LIMIT 结构错误，只是旧分类器检测不到。拒绝 E4-A 的最终结论不变（准确率、recovered=3/regressed=9 均由 correct/incorrect 原始判定得出，不受分类修复影响），但"QueryPlan 目标类净改善、只是被 Schema/过滤側效应拖累"这个归因是错的：**QueryPlan 直接在自己的目标类别上失败了。**

## 1. 运行身份与单变量边界

- 正式运行：`e4_a_core197_run1`
- run_id：`20260714T210045Z-11af1da6`
- 状态：`complete`，完成 `197/197`
- 模型：`azure/seminar-gpt-5.4-mini`
- 固定数据：`bird_cleancore_ids.json`，SHA-256 `b5f7949543409bf73d5c2fc899a23e4f7f04d39e07e77001dd1327694672b8a6`
- 父配置：正式 E3-C Schema v4 run3
- train few-shot：`k=1`
- Offline Schema：`e3-f-schema-v4`
- Schema 交付：`offline-retrieval`
- Query patterns / Query Mining：关闭
- capability gate：开启，只允许 `execute` 和 `sample_values`
- E4-A 唯一增量：同一次 Root 响应内生成 QueryPlan + Output Contract
- QueryPlan schema：v3；Prompt：`query-plan-protocol-v3`
- 独立 Planner/checker call：无
- strict verified-final：关闭，未重新引入已被 E1 拒绝的机制

运行配置与 smoke 后冻结的 E4-A 一致，没有把 Query Mining、context store 或 Leaf 混入本次结果。

## 2. 准确率

| 指标 | E4-A | E3-C 父配置 | 差异 |
|---|---:|---:|---:|
| 正确数 | 71/197 | 77/197 | -6 |
| 执行准确率 | **36.04%** | **39.09%** | **-3.05 pp** |
| `both_wrong` | 21/137 = 15.33% | 25/137 = 18.25% | -2.92 pp |
| `canary` | 50/60 = 83.33% | 52/60 = 86.67% | -3.33 pp |
| simple | 27/50 = 54.00% | 29/50 = 58.00% | -4.00 pp |
| moderate | 27/96 = 28.12% | 31/96 = 32.29% | -4.17 pp |
| challenging | 17/51 = 33.33% | 17/51 = 33.33% | 0 |
| 正常 `final` | 193/197 | 197/197 | -4 |
| `MaxIterationsError` | 4/197 | 0/197 | +4 |

E4-A 仍比 E0 两次均值 `34.26%` 高 `1.78 pp`，但这不能归因于 QueryPlan，因为其直接父配置 E3-C 已达到 `39.09%`。单变量因果比较必须使用 E3-C → E4-A，结论为负。

### 2.1 分数据库

| 数据库 | E4-A | E3-C | 差异题数 |
|---|---:|---:|---:|
| california_schools | 5/15 | 5/15 | 0 |
| card_games | 8/24 | 8/24 | 0 |
| codebase_community | 6/22 | 7/22 | -1 |
| debit_card_specializing | 4/14 | 6/14 | -2 |
| european_football_2 | 11/19 | 11/19 | 0 |
| financial | 3/13 | 3/13 | 0 |
| formula_1 | 10/29 | 11/29 | -1 |
| student_club | 7/14 | 9/14 | -2 |
| superhero | 5/7 | 5/7 | 0 |
| thrombosis_prediction | 6/23 | 6/23 | 0 |
| toxicology | 6/17 | 6/17 | 0 |

没有数据库出现净提升；6 题净损失集中在 4 个数据库。

## 3. 与 E3-C 的逐题迁移

E4-A 相对 E3-C：**恢复 3，回退 9，净损失 6**。

### 3.1 恢复题

| ID | E3-C 失败归因 | 数据库 | 难度 |
|---|---|---|---|
| `bird_1472` | 聚合/分组 | debit_card_specializing | moderate |
| `bird_371` | 聚合/分组 | card_games | challenging |
| `bird_83` | 输出列数 | california_schools | challenging |

这 3 题都属于 E4-A 的预注册目标类，说明显式 answer scope/output contract 对个别问题确实有效。

### 3.2 回退题

| ID | E4-A 失败归因（原） | E4-A 失败归因（2026-08-07 修复后） | 数据库 | 难度 |
|---|---|---|---|---|
| `bird_1480` | 过滤范围/表达式 | **聚合/分组不匹配** | debit_card_specializing | moderate |
| `bird_1500` | 无 FINAL / MaxIterations | 无 FINAL / MaxIterations（不变） | debit_card_specializing | simple |
| `bird_1526` | Schema/Join | Schema/Join（不变） | debit_card_specializing | challenging |
| `bird_1350` | 无 FINAL / MaxIterations | 无 FINAL / MaxIterations（不变） | student_club | moderate |
| `bird_1464` | 输出列数 | 输出列数（不变） | student_club | challenging |
| `bird_989` | 输出列数 | 输出列数（不变） | formula_1 | moderate |
| `bird_565` | 过滤范围/表达式 | **LIMIT/Top-K 不匹配** | codebase_community | moderate |
| `bird_459` | 无 FINAL / MaxIterations | 无 FINAL / MaxIterations（不变） | card_games | moderate |
| `bird_46` | 输出列数 | 输出列数（不变） | california_schools | simple |

`bird_1480` 和 `bird_565` 此前被旧分类器归为"过滤范围/表达式"（因为它们的聚合/LIMIT 结构差异没有被旧分类器检测到，参见 `docs/analysis/README.md` §4.1），修复后正确归入聚合类。目标类（聚合+输出）恢复为 3（2 聚合 + 1 输出），**目标类回退变为 5**（2 聚合 + 3 输出），不再是"持平"，而是目标类本身净回退 2；另外还有 1 个 Schema 和 3 个运行回退。这比原文档的判断更不利于 E4-A：不能用"聚合类总数下降"掩盖逐题净回退，而且这次连"聚合类总数下降"这个说法本身都不成立（聚合类实际是上升的，见 §4）。

### 3.3 E0 稳定集合

- E0 稳定失败 124 题中，E4-A 恢复 9 题；E3-C 恢复 10 题。
- E0 稳定正确 62 题中，E4-A 回退 5 题；E3-C 回退 0 题。
- E0 不稳定 11 题中，E4-A 正确 5 题。

稳定正确回退 ID：`bird_1480`、`bird_1464`、`bird_989`、`bird_459`、`bird_46`。这说明 E4-A 不只是没恢复足够失败题，还破坏了父配置原本稳定的能力。

## 4. 全部 126 条失败归因（2026-08-07 已用修复后分类器更新）

完整逐题文件：[`e4_a_core197_run1_semantic_failures.csv`](e4_a_core197_run1_semantic_failures.csv)（此 CSV 文件本身尚未随分类器一并重新导出，下表数字以重新生成的 `trace/e4_a_core197_run1/classification_sheet.csv` 为准）。

| 失败归因 | E4-A（修复后） | 占 126 失败 | E3-C（修复后） | 数量变化 | 原报告数值（供对照） |
|---|---:|---:|---:|---:|---|
| Schema/Join | 42 | 33.33% | 46 | **-4（改善）** | 原：E4-A 16 / E3-C 15 / **+1** |
| 聚合/排序 | 33 | 26.19% | 29 | **+4（变差）** | 原：E4-A 41 / E3-C 45 / **-4** |
| 输出契约 | 29 | 23.02% | 28 | +1 | 原：29 / 28 / +1（不变） |
| 过滤/低置信度 | 17 | 13.49% | 15 | +2 | 原：35 / 30 / +5（原数值偏大） |
| Runner/API | 4 | 3.17% | 0 | +4 | 原：4 / 0 / +4（不变） |
| 空结果 | 1 | 0.79% | 0 | +1 | 原：1 / 0 / +1（不变） |
| E3-C 历史 Tool 标签 | 0 | 0 | 2 | -2 | 原：0 / 2 / -2（不变） |

**结论方向反转**：原报告认为"聚合/排序下降 4 是唯一目标类改善；过滤、输出和 Schema 均上升"。修复后的数据显示 **Schema/Join 才是唯一净改善的类别（-4），而聚合/排序——E4-A 自己的主要设计目标——实际净上升 4**，输出契约维持不变（+1），过滤类净变化远小于原报告（+2 而非 +5）。两类主要目标"聚合/排序 + 输出契约"合计从 57 升到 62（+5），而不是原报告的"从 73 降到 70"；逐题目标 recovered/regressed 也从原报告的 3:3 变为 **3:5**（见 §3.2），同样是净回退。E4-A 未能达成其设计初衷这一点因此有了更直接、更强的证据。

## 5. QueryPlan 与 adherence 审计

| 指标 | 数量 |
|---|---:|
| 最终获得合法初始 QueryPlan | 197/197 |
| 曾产生无效初始计划的题 | 19 |
| 无效初始计划事件 | 23 |
| 有合法 revision 的题 | 19 |
| 合法 revision 事件 | 28 |
| 有无效 revision 的题 | 7 |
| 无效 revision 事件 | 31 |
| action-contract 无效事件 | 2 |
| `db.execute` | 252 |
| adherence pass | 181 |
| adherence fail | 71 |
| 至少一次 adherence fail 的题 | 44 |
| 全部执行均 adherence pass 的题 | 146 |
| 无结构化执行的题 | 7 |

### 5.1 最关键发现

- 146 题的所有 SQL 都通过结构 adherence，其中只有 64 题正确，另有 **82 题失败**。
- 44 题至少一次 adherence fail，其中 7 题正确、37 题失败。
- 7 题没有结构化 SQL 执行，全部失败。

因此当前 checker 主要能回答“SQL 是否忠实于计划中的列数、表集合和 clause presence”，不能回答“计划是否忠实于题目”。大量失败是**SQL 正确执行了错误 QueryPlan**，继续增加同类结构字段不会自动解决语义来源、过滤范围或 gold 歧义。

### 5.2 Revision 没有形成自我修复

19 题使用过合法 revision，仅 2 题最终正确；失败轨迹中 `wrong execution → correct execution` 恢复次数仍为 0。相反：

- `bird_50` 和 `bird_189` 出现 correct → wrong regression；
- `bird_671` 最后一次执行仍正确，却被未执行的错误 FINAL 改写破坏；
- 4 个 `MaxIterationsError` 中，3 个是从 E3-C 正确题回退而来。

QueryPlan revision 当前增加了协议状态和失败表面，但没有证明 observation 驱动的自我改进。

## 6. 控制流标签（2026-08-07 已用修复后分类器更新）

126 个失败的首要 trace 标签。这里的 `SCHEMA_LINKING`/`AGGREGATION_REASONING`/`OUTPUT_CONTRACT`/`SEMANTIC_REVIEW_REQUIRED` 是最终 SQL 已成功执行、由 `semantic_classification()` 直接决定首要标签的情况（`UNVERIFIED_FINAL` 覆盖的题不受本次分类修复影响，其首要标签始终是 `UNVERIFIED_FINAL`）：

| 首要标签 | 数量（修复后） | 数量（原） |
|---|---:|---:|
| `UNVERIFIED_FINAL` | 49 | 49（不变，控制流判定不受分类器修复影响） |
| `SCHEMA_LINKING` | 22 | 10 |
| `OUTPUT_CONTRACT` | 21 | 21（不变） |
| `AGGREGATION_REASONING` | 17 | 20 |
| `SEMANTIC_REVIEW_REQUIRED` | 12 | 21 |
| `RUNNER_OR_API` | 4 | 4（不变） |
| `EMPTY_OR_NULL_RESULT` | 1 | 1（不变） |

49 个 `UNVERIFIED_FINAL` 包含：错误 observation 后改写 44、无 DB execution 直接 FINAL 3、空结果后改写 1、正确 observation 后有害改写 1（不受分类修复影响）。该标签减少并没有带来准确率提升，进一步证明控制流表面改善不能代替底层语义分析。

## 7. Retrieval audit

完整文件：

- [`e4_a_core197_run1_retrieval_audit.csv`](e4_a_core197_run1_retrieval_audit.csv)
- [`e4_a_core197_run1_retrieval_audit.json`](e4_a_core197_run1_retrieval_audit.json)

| Retrieval 诊断 | 数量 |
|---|---:|
| 正确 | 71 |
| 所需详细 Schema 完整但语义失败 | 113 |
| gold 字段只在 compact index 或详细字段缺失 | 12 |
| gold 详细表缺失 | 1 |

`113/126 = 89.68%` 的失败已经拿到所需详细 Schema，因此 E4-A 的负结果不能主要归咎于 Offline retrieval 召回。13 个 retrieval 风险与 E3-C 的固定检索策略一致，QueryPlan 没有修复它们，也没有改变 Offline 因果边界。

## 8. 成本与延迟

| 指标 | E4-A 总量 | E4-A/题 | E3-C/题 | 相对变化 |
|---|---:|---:|---:|---:|
| LLM calls | 505 | 2.56 | 2.73 | -6.13% |
| prompt tokens | 1,904,734 | 9,668.70 | 7,082.12 | +36.52% |
| completion tokens | 1,354,593 | 6,876.11 | 8,427.83 | -18.41% |
| reasoning tokens | 1,094,794 | 5,557.33 | 7,836.35 | -29.08% |
| total tokens | 3,259,327 | 16,544.81 | 15,509.95 | **+6.67%** |
| cached prompt tokens | 928,512 | 4,713.26 | 3,435.86 | +37.18% |
| latency | 6,922.71 s | 35.14 s | 43.74 s | -19.65% |

QueryPlan 降低了平均调用和延迟，但结构化计划显著增大输入，最终 total tokens 仍增加 203,866。由于准确率净下降，不能把延迟下降解释为有效效率收益。

工具调用方面，E4-A 为 252 次 `db.execute` + 74 次 `sample_values`，E3-C 为 259 + 173。E4-A 明显减少值抽样，但过滤错误从 30 增至 35；这提示模型可能过早把未经验证的值/范围写入计划。

## 9. 马尔可夫链式轨迹定位

详细报告：[`e4_a_core197_run1_trajectory_audit.md`](e4_a_core197_run1_trajectory_audit.md)。失败的最早可观察阶段：

| 最早阶段 | 数量 |
|---|---:|
| 首次 nonmatching execution | 106 |
| retrieval context risk | 13 |
| 无执行直接 FINAL | 6 |
| 无法在 execution 与 FINAL rewrite 间进一步定位 | 1 |

终态：错误执行后未验证改写 61、FINAL 与最后执行一致 57、无执行 FINAL 7、正确执行后有害改写 1。123/126 个失败从未执行正确结果；另 3 个曾正确，但没有任何 wrong → correct 恢复。

## 10. 预注册接受条件检查（2026-08-07 已用修复后分类器更新）

| 条件 | 结果（修复后） | 是否通过 | 原结果（供对照） |
|---|---|---|---|
| 聚合/排序或输出至少一类净下降 | 聚合/排序 **+4（不通过）**；输出 +1 | **不通过** | 原：聚合/排序 -4；输出 +1 → 部分通过 |
| 两目标类 combined recovered > regressed | 目标恢复 3，目标回退 **5** | **不通过** | 原：目标恢复 3，目标回退 3 → 不通过（结论相同，幅度更差） |
| E0 稳定目标错误有可解释恢复 | 有个别恢复，但稳定正确回退 5 | **不通过** | 不变 |
| 不依赖独立 checker call | 没有独立 call | 通过 | 不变 |
| Schema/Join 和 canary 无不可接受回退 | Schema **-4（改善，非回退）**；canary -2 题（不受分类修复影响） | 部分不通过（仅 canary） | 原：Schema +1；canary -2 题 → 不通过（Schema 结论方向错误） |
| 总体准确率相对父配置不下降 | -6 题，-3.05 pp（不受分类修复影响） | **不通过** | 不变 |
| 成本可接受 | total tokens +6.67%，且准确率下降（不受分类修复影响） | **不通过** | 不变 |

七项条件里，准确率、成本、稳定正确回退、独立 call 四项完全不受分类修复影响，本来就已经不通过或通过；分类修复改变了"聚合/排序""目标类 recovered/regressed""Schema/canary"三项的具体数值和论证方向，但七项综合结论没有变化——**修复前后都是全面不通过，拒绝 E4-A 的决定不需要重新评估**，只是"为什么拒绝"的解释更准确了：核心问题是 QueryPlan 直接让自己的目标类别（聚合/排序）变差，而不是"目标改善、旁支代价"。

## 11. 最终判定与下一步

**拒绝当前 E4-A，保留 E3-C 作为最佳已验证配置。** 不进入 E5/E6，也不把 QueryPlan schema v3 带入递归实验。

下一步应是：

1. 完成 `F-Audit`，人工复核过滤、字段来源和 gold 歧义；
2. 不再使用这 197 题的 gold 继续微调 QueryPlan Prompt，避免 eval-specific overfitting；
3. 若仍研究 QueryPlan，应在 train-only 开发集上建立“问题 → answer scope/output/source/grain”计划正确性评测，先验证计划语义，再预注册新的机制实验；
4. 正式架构暂时回退到 E3-C；E5/E6 保持暂停。

