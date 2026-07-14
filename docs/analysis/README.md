# Agent 错误轨迹分析与实验记录

本文档用于记录 Agent 在 BIRD Text-to-SQL 实验中的运行版本、内部机制、错误轨迹和后续改动。每次加入新机制时，先复制文末的实验模板，再运行固定评测，避免只凭单条轨迹或单次 accuracy 判断改动是否有效。


## 0. 当前代码审计与本轮修改

本节记录 `ours/` 当前实现的代码问题、已经完成的修复和仍需实验验证的风险。
它描述的是 2026-07-13 重构后的代码状态；第 1 节之后的错误数量仍来自旧版 legacy
轨迹，不能把“代码已修复”直接等同于“实验已经证明有效”。

### 0.1 `ours/` 存在的问题

| 问题 | 影响 | 当前状态 |
|---|---|---|
| `DBRLM` 与 in-domain few-shot runner 曾各自维护一套完整 ReAct 循环 | 错误反馈、FINAL 判断和 trace 行为容易漂移，无法保证消融只改一个变量 | 已修复：统一由 `DBRLM.acomplete` 控制 |
| 历史 `db_hints.py` 明确依据低准确率数据库编写 | 可能使用 dev/eval 失败信息调优，不能作为 clean baseline 知识 | 已隔离：只有 `legacy-e0` 可以启用 |
| Prompt、知识注入、运行控制和实验配置曾耦合在同一文件 | 无法可靠执行 Prompt、offline、few-shot 和递归机制的添加/替换消融 | 已修复：Prompt、知识、配置、状态和能力边界已拆分 |
| 父类 REPL 默认暴露通用 `recursive_llm`，原始 DB 对象还暴露 Schema API | R0/R1 即使没有计划使用递归，也存在隐藏能力，可能污染基线 | 已为 `e4-r0` 增加运行时 gate；R0 将与 E0 固定 50 题校准 |
| 旧 FINAL 逻辑只依赖临时 `last_was_empty`，被阻断一次后状态会重置 | 重复 FINAL 可能绕过保护；最终 SQL也可能与最近执行 SQL 不同 | 已修复：改为持久化结构化执行状态 |
| 旧代码允许模型执行候选 SQL 后修改文本并直接 FINAL | 产生 `UNVERIFIED_FINAL`，数据库 observation 实际没有验证提交答案 | 已实现 E1 verified-final，尚待正式运行验证效果 |
| 旧逻辑把全 NULL 当作确定性错误 | 固定 197 题中 `bird_1526`、`bird_944` 的正确 gold 本身就是全 NULL，会造成回归 | 已修复：全 NULL 保留警告，但精确执行过的 SQL 可以提交 |
| Agent profile、能力边界和知识来源没有独立版本/哈希 | 历史结果无法证明使用了哪套 Prompt、few-shot 或隐藏工具 | 已修复：manifest 和 trace 记录配置、capability、retriever 来源与 SHA-256 |
| Runner 在检查旧 manifest 冲突前加载 embedding 模型并编码 9,428 个样例 | 明知配置不能续跑仍浪费启动时间和计算资源 | 已修复：先用轻量 retriever manifest 校验，成功后才初始化 embedding |
| `DBRLM` 默认值曾可能隐式启用 E1 | 未显式传参的旧 runner 会静默改变实验机制 | 已修复：默认是 `clean-e0`；历史 runner 显式使用 `legacy-e0` |
| 状态机、能力越权和 profile 边界缺少测试 | 后续加入 R1/R2 时容易破坏 E0/E1 单变量关系 | 已修复：包含 Prompt provenance 和轻量 retriever manifest 在内的测试覆盖已补齐 |
| 最终 predicted/gold SQL 的评测执行没有超时 | 失控 SQL 可在 Agent 已返回后无限占用 SQLite；`e0_core_run2` 因此停在 110/197 | 已修复：共享执行器固定 30 秒超时并显式关闭连接；超时值进入实验配置 |
| `clean-e0` 基础 Prompt 曾包含聚合、比例、排序和输出规则 | 若规则来自 eval 错误分析，会造成知识泄漏或高估基线 | 已修复：正式组改用 `clean-protocol-v1`，只保留工具和提交协议；旧规则仅在 legacy Prompt |
| clean baseline 没有 database notes/手工 patterns，却规划了 E2-R/E3-RP 替换组 | 替换对象不存在，无法形成可解释消融 | 已修复：删除无效组；E3-A 只添加 train-only patterns，E3-B（历史运行 profile `e3-rf`）只移除 train few-shot |
| R1-E/R1-C context store、R2 Leaf、R3 Planner 和 R4 router 尚未实现 | 当前仍是 DB CodeAct/ReAct，不是完整 RLM 架构 | 这是后续待测机制，不是当前基线缺陷；按实验顺序逐项实现 |

### 0.2 本轮做了什么修改

| 修改位置 | 修改内容 | 实验意义 |
|---|---|---|
| `ours/agent/config.py` | 新增不可变 `AgentConfig`，定义 `legacy-e0`、`clean-e0`、`clean-e1`、`e4-r0` | E1 单独测试严格门控；E4-R0 在 E0 上只增加 capability gate |
| `ours/agent/state.py` | 新增 `AgentExecutionState`，记录 SUCCESS/ERROR/EMPTY/ALL_NULL 和最近执行 SQL | FINAL 从字符串解析变为可验证状态转换 |
| `ours/agent/capabilities.py` | 新增 `GatedDBEnvironment`，R0 只允许 `db.execute`、`db.sample_values` | 阻断隐藏 Schema API 和通用递归入口，越权进入 trace |
| `ours/agent/knowledge.py` | 统一组装 BIRD Hint、database notes 和 few-shot，并记录来源 | 为后续 offline 添加/替换消融提供知识边界 |
| `ours/agent/prompts.py` | 将 Prompt 独立版本化；正式组使用 protocol-only Prompt，legacy 保留旧强规则 Prompt | 排除固定 SQL 规则污染 E0，并记录来源和 SHA-256 |
| `ours/recursive_db_rlm.py` | 统一唯一控制循环，接入 profile、knowledge、状态机、gate 和结构化事件 | 删除 runner 间行为漂移，支持 E0/E1/R0 共用宿主 |
| `ours/train_few_shot_retriever.py` | 记录 train pool、样例数、embedding model 和文件 SHA-256 | 证明正式 few-shot 来自 train，而不是 dev/eval |
| `scripts/run_bird_train_fewshot.py` | 增加 `--agent-profile`，manifest 记录完整配置和知识 provenance | 不同 profile 不能错误续跑或混入同一结果目录 |
| `scripts/run_bird_train_fewshot.py` | 配置冲突显示具体 changed fields，并把 retriever 初始化移到 manifest 校验之后 | 失败更可解释，且冲突运行不再计算 embedding |
| `shared/sql_executor.py` | 为 predicted/gold SQL 增加 SQLite progress-handler 30 秒超时，并显式关闭连接 | 防止最终评测阶段被失控 SQL 永久阻塞 |
| `scripts/run_bird_train_fewshot.py` | 将 `evaluation_sql_timeout_seconds=30` 写入 manifest 配置 | 超时协议变化会触发配置冲突，避免新旧结果断点混跑 |
| `scripts/summarize_bird_runs.py` | 增加 `--allow-config-difference`，只允许并报告显式指定的历史配置差异 | 不篡改旧 manifest，也能生成带警告的探索性聚合报告 |
| `scripts/run_bird_indomain_fewshot.py` | 删除重复 `acomplete`，保留薄包装；默认标记为 legacy | dev-derived few-shot runner 不再冒充 clean 实验入口 |
| `scripts/run_bird_ours.py` | 显式使用 legacy profile，并写入配置哈希 | 防止旧入口因默认值变化而静默改变含义 |
| `tests/test_agent_profiles.py` | 增加 profile、Prompt provenance、状态机、重复 FINAL、全 NULL、能力越权和共享循环测试 | 锁定消融边界 |

### 0.3 当前 profile 的准确含义

| Profile | 用途 | verified-final | capability gate | legacy `db_hints` |
|---|---|---:|---:|---:|
| `legacy-e0` | 仅复现历史代码，不进入正式结论 | 否 | 否 | 是 |
| `clean-e0` | 正式强基线候选 | 否 | 否 | 否 |
| `clean-e1` | 只增加最终 SQL 状态保护 | 是 | 否 | 否 |
| `e4-r0` | 在 E0 上只增加运行时能力门控 | 否 | 是 | 否 |

`clean-e0` 已完成两次固定 197 题探索性运行，可以作为后续机制筛选基线。
两次运行的评测 SQL 超时字段不同，因此不能写成严格同协议复现。`clean-e1`
已完成前 70 题配对比较并被拒绝；`e4-r0` 仍只是“实现与测试完成”，尚不能写成“机制有效”。

### 0.4 现有能力与后续机制的重复

| E0 已有能力 | 与后续机制的交叉 | 处理方式 |
|---|---|---|
| 多轮 DB ReAct 和错误反馈 | 运行内自我修正 | 全部实验保留，不作为新增机制 |
| Python REPL、`db.execute` 和 `sample_values` | E2 受控执行环境 | E2 只增加可观测性和能力隔离，不把已有执行能力计为收益 |
| legacy Prompt 中的聚合、比例、排序规则和示例 | E3-A query patterns | 保留为历史重叠项，但不做正式 legacy 消融：来源未经审计且可能含 eval 调优；同类机制改由 train-only `train-static-v1` 在 E3-A 中合规测试 |
| legacy `db_hints` | E3-C Offline metadata | 保留为历史重叠项，但不进入正式父配置；E3-C 只使用来源可记录、可哈希的数据库级 metadata artifact |
| Train few-shot gold SQL | E3-A static patterns / E3-D Query Mining | E3-B 只证明静态 patterns 不能替代 few-shot；E3-C 保留 few-shot 且关闭 patterns，E3-D 再加入真正 Query Mining，E3-E 才做 matched few-shot 消融 |
| 完整 Schema 直接进入 Prompt | E3-C Offline Schema Context、E5 context store | E3-C 用预构建 artifact 的确定性相关片段替代 runtime full Schema；E5 再测试由模型主动 `search/slice/compose` |
| high reasoning 模型 | E4 QueryPlan、E6 分解 | 模型和 reasoning effort 固定；E6-B 必须与 E6-A 做等预算比较 |
| 通用 `recursive_llm` 实现 | E6 depth-1 Leaf | E6 前通过 capability gate 禁用，避免基线或 E3/E4/E5 污染 |

这里“不做正式 legacy 消融”不等于不测试对应机制。原因是 clean E0 已经移除了 legacy Prompt 规则和 `db_hints`，不存在可解释的“从 E0 再移除”对照；若把这些未经来源审计的内容重新加回，会同时引入潜在 eval 调优和知识来源混杂。E3-A/E3-B 的 `train-static-v1` 仅是来源合规的静态规则原型，不具备 SQL 结构归一化、聚类、支持度和按题检索，不能代表完整 Query Mining。E3-C 独立测试来源可审计的 Schema metadata；E3-D 才测试正式 Query Mining。

### 0.5 两次 E0 聚合结果

| 指标 | 结果 |
|---|---:|
| Run1 | 69/197（35.03%） |
| Run2 | 66/197（33.50%） |
| 平均准确率 | 34.26% |
| 总体标准差 | 0.76% |
| 稳定正确 | 62 |
| 稳定失败 | 124 |
| 不稳定 | 11 |
| Run1→Run2 恢复/退化 | 4/7 |
| `UNVERIFIED_FINAL` 失败记录 | 215 |

聚合报告位于 `docs/analysis/analysisDetail/e0_core_summary.json` 与
`docs/analysis/analysisDetail/e0_core_summary.md`。
Run1 没有 `evaluation_sql_timeout_seconds`，Run2 为 30 秒且前 110 题产生于修复前，
因此报告只用于探索性机制选择。两次运行分别有 9 和 11 次 token usage 缺失，
准确率和错误分布可用，但 token 成本只能视为已记录调用的下界。

### 0.6 E1 strict verified-final 实验结果

**实验定义**

| 字段 | 内容 |
|---|---|
| 实验 ID | `E1` |
| Profile | `clean-e1` |
| 唯一主要改动 | 在 E0 上启用 strict verified-final 状态门控 |
| 模型 | `azure/seminar-gpt-5.4-mini` |
| 题目范围 | E1 文件落盘 71 条；配对比较固定使用前 70 条 |
| E1 结果 | `results/e1_verified_run1.json` |
| E1 轨迹 | `trace/e1_verified_run1/transcripts.jsonl` |
| E1 分类 | `trace/e1_verified_run1/classification_sheet.csv` |
| E1 独立报告 | `docs/analysis/analysisDetail/e1_verified_summary.md` |
| 完整比较报告 | `docs/analysis/analysisDetail/e1_vs_e0_first70.md` |

**前 70 题配对结果**

| 配置 | 正确数 | 准确率 | LLM 调用/题 | Tokens/题 | 延迟/题（秒） |
|---|---:|---:|---:|---:|---:|
| E0 run1 | 29/70 | 41.43% | 2.67 | 13,255.29 | 35.18 |
| E0 run2 | 30/70 | 42.86% | 2.77 | 13,598.43 | 37.20 |
| E0 均值 | - | 42.14% | 2.72 | 13,426.86 | 36.19 |
| E1 | 28/70 | 40.00% | 5.51 | 26,920.84 | 63.23 |

E1 相对 E0 均值下降 2.14 个百分点；LLM 调用约增至 2.03 倍，记录到的 token
约增至 2.00 倍，延迟约增至 1.75 倍。E1 有 1 次 token usage 缺失，因此成本仍是下界。

**配对变化与门控行为**

- E0 两次都正确 27 题、两次都失败 38 题、结果不一致 5 题。
- E1 从 E0 稳定失败中恢复 0 题。
- E1 使 E0 稳定正确退化 3 题：`bird_1169`、`bird_1171`、`bird_1103`。
- 相对 E0 run1，E1 恢复 2 题、退化 3 题；相对 E0 run2，恢复 2 题、退化 4 题。
- 前 70 题产生 103 次 `final.blocked`，覆盖 63/70 题，说明严格门控成为普遍额外循环。

**错误分类变化**

| Error class | E0 run1 | E0 run2 | E1 |
|---|---:|---:|---:|
| `UNVERIFIED_FINAL` | 36 | 33 | 0 |
| `AGGREGATION_REASONING` | 1 | 2 | 13 |
| `OUTPUT_CONTRACT` | 1 | 2 | 10 |
| `SCHEMA_LINKING` | 1 | 0 | 5 |
| `SEMANTIC_REVIEW_REQUIRED` | 2 | 2 | 9 |
| `RUNNER_OR_API` | 0 | 1 | 5 |

`UNVERIFIED_FINAL` 归零说明形式约束确实生效，但其他错误类别增加主要是原先被
`UNVERIFIED_FINAL` 覆盖的失败被重新分类，不能解释为语义错误本身突然增多。
关键判据仍是执行准确率和配对恢复/退化，而这两项没有支持 E1。

**固定前 50 题复核**

后续实验统一使用 `--limit 50`。在该共同子集上，E0 run1/run2 分别为 38%/40%，
E1 为 38%；E1 的调用和 token 仍约为 E0 的两倍，因此缩小到后续评测范围也不会改变结论。

**实验决策**

拒绝当前 strict verified-final：它提高了形式可验证性，但准确率下降、稳定正确题退化，
并显著增加调用、token 和延迟。后续 E2-E5 不继承该门控，`e4-r0` 已改为从 E0
只增加 capability gate。若以后重新测试最终验证，应优先采用控制器自动执行
`FINAL` SQL 的低成本方案，而不是要求模型通过多轮 ReAct 重复执行。

### 0.7 E4-R0 capability-gated 对照结果

**实验定义**

| 字段 | 内容 |
|---|---|
| 实验 ID | `E4-R0` |
| Profile | `e4-r0` |
| 唯一主要改动 | 在 E0 上启用 capability gate，关闭通用递归和 Schema API 能力 |
| 题目范围 | 固定 `--limit 50`，`both_wrong + canary` |
| 结果 | 19/50（38.00%） |
| 结果文件 | `results/e4_r0_run1.json` |
| 轨迹目录 | `trace/e4_r0_run1/` |
| 独立报告 | [e4_r0_summary.md](analysisDetail/e4_r0_summary.md) |
| JSON 报告 | [e4_r0_summary.json](analysisDetail/e4_r0_summary.json) |
| 配对分析 | [e4_r0_vs_e0_first50.md](analysisDetail/e4_r0_vs_e0_first50.md) |

E4-R0 与 E0 首 50 题的 38%/40% 两次结果一致，E0 均值为 39%，
E4-R0 为 38%。相对 E0 均值，E4-R0 的 tokens/题为 10,207.28，
LLM 调用/题为 2.72，延迟/题为 36.69 秒，均未出现明显增加。

trace 中 110 个数据库工具事件全部属于允许集合（60 次 `db.execute`、
50 次 `db.sample_values`），未观察到递归、Schema API 或越权调用。
因此 E4-R0 通过能力边界校准，但没有证据表明 capability gate 本身提升准确率；
它被接受为后续 RLM/Planner 消融的父对照。

E4-R0 的 31 条失败记录中有 27 条 `UNVERIFIED_FINAL`。这是因为本实验
关闭了 E1 的 strict verified-final，目的是隔离 capability gate；该标签保留是预期
现象，不应把 E4-R0 解读为最终 SQL 验证机制。


### 0.8 旧 E3-F v1/v3 前 53 题诊断

`e3_f_core197_run1` 实际使用历史配置 `train-mined-v1 + e3-f-schema-v3 + k=1 few-shot`，在完成 53/197 题后中断。它发生在 Schema v4 和 Query Mining v2 修复之前，因此单列为历史诊断，不计作新版 E3-F 完成。

| 指标 | 结果 |
|---|---:|
| 正确率 | 21/53 = 39.62% |
| `both_wrong` | 7/36 = 19.44% |
| `canary` | 14/17 = 82.35% |
| total tokens/题 | 16,426.79 |
| 同题 E0 两次均值 | 36.79%，11,704.59 tokens/题 |
| 相对 E0 | +2.83 pp，tokens/题 +40.34% |
| 运行状态 | `interrupted`；仅覆盖 4/11 个数据库 |

32 个失败经过逐题复核后，实际语义原因是聚合 9、输出契约 9、过滤/题目语义 7、Schema/Join 6、Runner/API 1。自动标签中的 24 个 `UNVERIFIED_FINAL` 只是控制流现象，不能代替上述语义根因。

Offline 检索审计进一步发现：Schema v3 在 53/53 题中都交付了所在数据库的全部表，因此零 detailed-schema miss 是全表注入造成的，不是检索精度证据；Query Mining v1 平均交付 2.85 张卡，只有 16/53 的选中集合包含与 gold 完全一致的 shape。这解释了为什么该运行只有弱准确率变化，却显著增加成本。

结论：冻结 v1/v3 运行，不继续补到 197，不把 39.62% 外推为完整结果，也不用于评价新版 v2/v4。对应材料：

- [完整部分结果](analysisDetail/e3_f_core197_run1_partial53_summary.md)
- [同题 E0/E3-A/E3-B 对比](analysisDetail/e3_f_core197_run1_vs_e0_e3a_e3b_partial53.md)
- [32/32 失败语义归因](analysisDetail/e3_f_core197_run1_semantic_failures.csv)
- [53 题 retrieval audit](analysisDetail/e3_f_core197_run1_retrieval_audit.csv)

## 1. 当前分析版本

| 字段 | 内容 |
|---|---|
| 实验编号 | `TRACE-2026-07-11-A` |
| 实验性质 | 当前 Agent 的错误轨迹审计，不包含递归机制改动 |
| 数据集 | BIRD mini-dev，500 条记录，498 个唯一问题 |
| 轨迹文件 | `trace/transcripts.jsonl`、`trace/traces_report_full.html` |
| 分类文件 | `trace/classification_sheet.csv` |
| 模型 | `gpt-5.4-mini`（Azure，依据项目 README） |
| 结果规模 | HTML 报告标记 161 条失败；约 67.8%（按 500 条计算） |
| 代码状态 | 轨迹生成时尚未进行当前 profile/状态机/能力门控重构 |
| 重要限制 | 本节分析的是旧版 legacy 轨迹；当前 runner 已补齐 run manifest、结构化事件和 token usage |
| 统一实验编号 | 以 `docs/experiment-plan/README.md` v1.0 的阶段大类和 E3-A～E6-B 顺序编号为准；旧名只用于解释历史产物 |

### 轨迹文件一致性

旧版 HTML 报告包含 161 条失败轨迹，但 `classification_sheet.csv` 只有 158 条记录，曾缺少 `bird_226`、`bird_227`、`bird_228`、`bird_255`，同时多出 `bird_743`。该问题解释了为什么当前流水线强制使用同一个 `run_id` 校验 result、transcript 和 classification；旧文件只用于历史根因分析，不再与新实验混合。

## 2. Agent 机制：历史轨迹与当前实现

旧轨迹对应的 Agent 和当前四个 profile 都属于数据库增强的 CodeAct/ReAct Agent：
已有可执行 REPL 和数据库 observation，但尚未实现 RLM 的代码化上下文探索与递归分治。
当前版本已经统一控制循环并隔离实验能力，不代表 R1/R2/R3 已经实现。

### 2.1 推理与工具循环

1. 正式 profile 将问题、BIRD Hint、Schema 和 train few-shot 放入上下文；只有 legacy profile 额外注入旧 database notes。
2. 模型通过 `db.sample_values(table, column)` 查询真实字符串值。
3. 模型通过 `db.execute(sql)` 执行候选 SQL。
4. Agent 将 SQL 结果、SQL 错误、空结果和全 NULL 结果反馈给模型。
5. 模型通过 `FINAL("sql")` 提交最终 SQL。

主要实现位置：

- `ours/recursive_db_rlm.py`：数据库 Agent 的唯一迭代循环和终止逻辑。
- `ours/agent/`：profile、知识组装、执行状态和能力门控。
- `ours/db_environment.py`：只读 SQLite、Schema、样例值和 SQL 执行工具。
- `scripts/run_bird_train_fewshot.py`：正式 train few-shot 评测入口、manifest 和 trace 流水线。
- `scripts/run_bird_indomain_fewshot.py`：legacy dev-derived few-shot 薄包装，不用于 clean 结论。
- `shared/evaluator.py`：官方 BIRD 执行结果比较。

### 2.2 当前已有保护机制

- SQLite 只读连接；Agent 工具调用与最终 predicted/gold 评测查询均有 30 秒超时。
- 结果行数限制。
- SQL 执行错误反馈。
- 空结果和全 NULL 结果反馈。
- `clean-e1` 阻止错误或空集 SQL，并要求 FINAL 与最近一次已执行 SQL 完全一致；该严格门控已被拒绝，不进入 `e4-r0`。
- 全 NULL 只警告、不硬阻断，因为固定集合存在正确的全 NULL gold。
- 连续重复执行结果检测。
- `sample_values` 调用前校验真实表名和列名。
- 训练集 few-shot 检索。
- `reasoning_effort=high` 和多次运行投票属于实验配置，不是单次 Agent 内部的推理模块。

### 2.3 目标 RLM 架构

后续实验把 RLM 拆成三个可测量的能力：

1. **程序化推理/探索**：Schema、description、few-shot 和后续 offline artifact 外部化为 context store，模型通过代码搜索、选择和组合片段。
2. **可执行环境**：REPL 保存上下文片段、中间计划、候选 SQL、DB observation 和验证状态；所有关键动作可以执行并进入 trace。
3. **自我改进与分而治之**：Root 根据 observation 修正 SQL，并只在复杂问题上对选定片段调用 depth-1 Leaf，再组合有证据引用的局部发现。

这三个能力分别增强形式化、执行可验证性和基于真实上下文的 grounding，正对应当前“SQL 能执行但语义仍错误”难以定位和约束的问题。

ReAct 不是另一套与 RLM 平行的循环，而是 Root 在数据库环境中的执行反馈路径。Root 内 QueryPlan 本身不满足“依据上下文动态切分并组合”的递归条件，因此 P 先作为非递归形式化实验；只有 C-P-Leaf 才测试 QueryPlan 驱动的受限分而治之。

## 3. 当前错误结果

对 `transcripts.jsonl` 与 HTML 失败列表的自动统计如下：

| 指标 | 结果 | 解释 |
|---|---:|---|
| HTML 标记的失败轨迹 | 161 | 当前这次运行的主要分析对象 |
| 真实 SQL 执行错误 | 2 | `bird_41`、`bird_83`；两者都继续进行了修正 |
| 出现空结果的轨迹 | 7 | 包含 SQL 错误造成的空 rows |
| 出现全 NULL 结果的轨迹 | 5 | 说明查询列或连接路径存在问题 |
| 无 assistant 输出 | 2 | `bird_959`、`bird_598`，需检查 runner/API 记录 |
| 只有一次 assistant 输出 | 4 | `bird_1168`、`bird_539`、`bird_604`、`bird_424` |
| 主要失败形态 | 执行成功但语义错误 | 当前瓶颈不是 SQL 能否运行，而是 SQL 是否回答了问题 |

### 3.1 代表性轨迹

#### A. 已经验证后又提交了未验证 SQL

`bird_1029` 中，模型第一次执行的 SQL 返回了正确的球队名称和速度，但在 `FINAL()` 中改成了只返回速度、且聚合和排序逻辑不同的 SQL。当前控制器只检查空结果，没有检查最终 SQL 是否就是最近一次成功执行过的 SQL。

`bird_23` 和 `bird_83` 也出现了类似的“执行候选 SQL → 修改候选 SQL → 未重新执行就 FINAL”的模式。

**判断：** 这是 Agent 状态控制问题，优先级高于增加更多 Prompt 规则。

#### B. 工具对不存在的列返回了假阳性

`bird_83` 中，模型调用：

```text
db.sample_values("schools", "NSLP Provision Status")
```

返回了 `NSLP Provision Status` 这个字符串，而不是明确的列不存在错误。SQLite 对双引号未知标识符的兼容行为使工具误认为该列存在，模型因此继续沿着错误的表进行推理。

**判断：** `sample_values` 必须先通过 Schema 校验表名和列名；未知列应返回结构化错误。该修复现已进入当前 E0 基线，本轨迹保留为修复动机。

#### C. 聚合粒度错误

`bird_1472` 的问题要求找出 2012 年 LAM 客户的最少总消费。模型使用了：

```sql
ORDER BY y.Consumption ASC LIMIT 1
```

这实际上按单个月份记录排序，而不是先按客户聚合后按 `SUM(Consumption)` 排序。

**判断：** 这是执行成功后的语义推理错误，单纯增加 SQL 语法重试不会解决。

#### D. Hint 与 gold SQL 不一致

`bird_1338` 中，Hint 明确要求判断所有费用是否 approved，模型执行后得到 `YES`；但 gold SQL 要求返回每一笔 `approved` 字段。`bird_1179` 中，Hint 指定 anti-Cardiolipin 对应 `aCL IgM`，而 gold SQL 要求同时返回 `aCL IgA`、`aCL IgG` 和 `aCL IgM`。

**判断：** 这类轨迹应标记为 `DATASET_OR_GOLD_CONFLICT`，不能直接用来证明 Agent 机制失败。

#### E. 无输出或过早结束

`bird_959` 和 `bird_598` 没有 assistant 输出，`bird_1168` 等问题只产生一次 assistant 输出。这些轨迹需要结合 runner 的 API 重试、超时和异常日志判断，不能归类为 SQL 推理错误。

## 4. 错误分类标准

在 `classification_sheet.csv` 中使用以下固定分类，避免每次分析采用不同标准：

| `error_class` | 判断标准 | 典型修复方向 |
|---|---|---|
| `TOOL_ERROR` | 工具返回错误、错误列未被识别或工具产生假阳性 | 修复 Schema 校验和工具返回结构 |
| `UNVERIFIED_FINAL` | 最终 SQL 与最近一次执行的 SQL 不同，且没有重新执行 | 先查看并行的语义标签；FINAL 同步只能修复控制流，不能替代语义修正 |
| `EMPTY_OR_NULL_RESULT` | 查询返回空结果或全 NULL，模型未能正确修复 | 改善反馈状态和候选 SQL 管理 |
| `AGGREGATION_REASONING` | 分组、聚合、排序、窗口函数粒度错误 | 增加结构化 SQL 检查和针对性示例 |
| `SCHEMA_LINKING` | 选错表、字段或连接关系 | 改进 Schema/外键提示和工具查询 |
| `OUTPUT_CONTRACT` | 列数、列顺序、yes/no、别名或多问题输出不符合要求 | 建立轻量输出契约检查 |
| `DATASET_OR_GOLD_CONFLICT` | Hint、问题语义与 gold SQL 不一致 | 单独统计，不用来驱动 Agent 改动 |
| `RUNNER_OR_API` | 没有模型输出、超时、请求失败或结果未保存 | 修复重试、日志和断点续跑 |
| `CORRECT_TRACE_MARKED_WRONG` | 按 Hint 和真实数据库结果合理，但被 gold 判错 | 记录证据，纳入数据集质量分析 |
| `SEMANTIC_REVIEW_REQUIRED` | SQL 已成功执行，但自动规则只能确认存在语义差异 | 复核过滤范围、表达式或 gold 噪声 |

分类表保留 `error_class/subcategory` 作为兼容的主标签，同时新增以下运行后诊断字段：

| 字段 | 含义 |
|---|---|
| `control_flow_class/control_flow_subcategory` | FINAL 未执行、报错后提交等控制流现象 |
| `semantic_error_class/semantic_subcategory` | 最终 SQL 相对 gold SQL 的聚合、输出、Schema/Join 或过滤语义差异 |
| `sql_change_type` | 最后执行 SQL 到 FINAL SQL 之间修改的表、WHERE、GROUP BY、ORDER BY、LIMIT、聚合或投影结构 |
| `semantic_fix_idea/semantic_notes` | 与语义标签对应的修复方向和自动诊断依据 |

同一失败可以同时拥有控制流和语义标签。例如：主标签为 `UNVERIFIED_FINAL`，控制流子类为“错误 observation 后改写未执行”，语义类别为 `AGGREGATION_REASONING`。gold 只用于运行后分类，不进入 Agent 在线推理。

### 自动生成分类表

`run_bird_train_fewshot.py` 默认完成整条流水线：

```powershell
.\.venv\Scripts\python.exe scripts/run_bird_train_fewshot.py `
  --output results/e0_trainfs.json `
  --agent-profile clean-e0 `
  --k 1 --max-iterations 8 --reasoning-effort high
```

运行结果会写入 `results/e0_trainfs.json`，对应的
`trace/e0_trainfs/` 包含 `run_manifest.json`、`transcripts.jsonl`、
`traces_report.html` 和 `classification_sheet.csv`。results 与 transcript
共享同一个 `run_id`，ID 或最终 SQL 不一致时，报告和分类脚本会直接拒绝写出。

`scripts/make_classification_sheet.py` 也可以单独执行：

```powershell
python scripts/make_classification_sheet.py `
  --results results/bird_traced_rhigh_500.json `
  --transcripts trace/e0_trainfs/transcripts.jsonl `
  --out trace/e0_trainfs/classification_sheet.csv
```

脚本优先使用结构化工具事件，不再从一个 turn 的 Markdown 猜测多个 SQL 对应的
结果。高置信度分类包括无模型输出、SQL 未验证、未知表/列、执行错误、空结果和
全 NULL；聚合、输出结构、排序和 Schema 差异是候选分类，在 `notes` 中标记
`AUTO confidence=medium/low`。无法可靠确定根因的语义差异统一标记为
`SEMANTIC_REVIEW_REQUIRED`。旧版无 `run_id` 文件必须显式添加
`--allow-legacy`，并仍需通过 ID 和最终 SQL 一致性检查。

## 5. 当前根因判断

当前失败不是单一问题，优先级如下：

1. **严格 verified-final 已被拒绝。** E1 前 70 题为 40.00%，E0 配对均值为 42.14%；门控覆盖 63/70 题，调用与 token 约翻倍，稳定失败恢复 0 题、稳定正确退化 3 题。形式约束消除了 `UNVERIFIED_FINAL` 标签，但没有改善准确率。
2. **`sample_values` 的列校验问题已修复。** 当前需要通过 E0 重跑确认工具类错误是否按预期消失。
3. **成功执行不等于语义正确。** 聚合粒度、过滤范围、排序方向和多问题输出仍然是主要错误来源。
4. **数据集 gold 噪声较大。** 这部分必须单独统计，否则会把不可修复的问题误认为 Agent 回归。
5. **runner/API 失败必须与模型推理错误分离。** 当前 trace schema v3、run manifest 和 token usage 已具备该能力，E0 将验证完整性。
6. **clean Prompt 来源问题已修复。** `clean-protocol-v1` 不含任务特定 SQL 规则或示例，Prompt provenance 与哈希进入 manifest。
7. **静态 patterns 的结论已收窄。** E3-A 添加人工归纳的 train-only static patterns；E3-B 的唯一变量是移除 train few-shot。E3-B 已因准确率下降、成本未降低而拒绝，但该结论不外推到后续真正 Query Mining。

因此，当前阶段不应绕过基线直接叠加递归，也不应继续增加未经来源审计的 Prompt 规则。
E0 已完成，严格 E1 已拒绝，E4-R0 已接受为 capability-gated 父对照；后续从 E0 分别测量 offline knowledge、capability-gated
RLM context externalization、depth-1 分治和 one-shot Planner 的独立增益。

## 6. 后续实验计划

所有正式实验使用同一批 197-question core + canary、同一模型和运行参数，并保存完整 manifest。路线已按 E0/E3-A 双标签错误分析精简，不再运行旧 E4/E5 全组合矩阵。

| 实验编号 | 改动 | 目标指标 | 当前状态 |
|---|---|---|---|
| `E0` | `clean-e0` 完成 2 次探索性运行；使用 `clean-protocol-v1`、`sample_values` 校验和 trace schema v3 | 建立 baseline、成本和错误分类 | 已完成；均值 34.26%，协议差异已记录 |
| `E1` | 切换为 `clean-e1`；FINAL 只能提交最近一次无错误、非空集且精确执行过的 SQL | 减少 `UNVERIFIED_FINAL` | 前 70 题已完成；准确率下降且成本约翻倍，拒绝 |
| `E3-A` | 在 E0 上添加人工归纳的 train-only static patterns，保留 few-shot | 测量静态规则原型的价值，不代表完整 Query Mining | 已完成：73/197=37.06%；弱证据，不作为默认父配置；见[完整结果](analysisDetail/e3_a_summary.md)和[对比](analysisDetail/e3_a_vs_e0.md) |
| `E3-B` | 从 E3-A 移除 train few-shot，保留 patterns；历史运行 profile 为 `e3-rf` | 判断 patterns 能否替代 few-shot 并降低成本 | 已完成并拒绝：72/197=36.55%，较 E3-A 恢复 4、退化 5，tokens/题增加 4.54%；见[完整结果](analysisDetail/e3_b_summary.md)和[对比](analysisDetail/e3_b_vs_e3_a_e0.md) |
| `E3-C` | 回到 E0 知识控制条件，关闭 static patterns；用确定性检索的 Offline Schema Context 替代 runtime full Schema Prompt，保留 few-shot | 独立测量 Schema semantics、PK/FK、Join path、基数和值格式 | 旧 run2 在 62/197 中断且混入 static patterns，仅作诊断；新版 profile 使用 `e3-f-schema-v4`、`query_pattern_mode=none` 和 capability gate，下一步分层 smoke |
| `E3-D` | 在 E3-C 上增加从 train question + SQL 自动归一化、聚类并按题 Top-K 检索的 Query Mining artifact | 减少聚合、排序、过滤、输出和 Join 结构错误 | 等待 E3-C |
| `E3-E` | 从通过的 E3-D 移除 train few-shot，其余完全不变 | 判断完整 Offline 知识能否替代 few-shot | 条件实验，仅 E3-D 通过后运行 |
| `E3-F` | `e3-f-schema-v4 + train-mined-v2 + k=1 few-shot`；关闭 static patterns 和 runtime full Schema，开启 capability gate | 测量修复后的完整 Offline 系统集成效果 | 历史 v1/v3 run1 在 53/197 中断：21/53=39.62%，Schema 实际全表注入且成本高，仅作[部分诊断](analysisDetail/e3_f_core197_run1_partial53_summary.md)和[同题比较](analysisDetail/e3_f_core197_run1_vs_e0_e3a_e3b_partial53.md)；新版仍因 Query Mining v2 0 个 slot 通过而暂停 |
| `E4-A` | 增加 Root 内 QueryPlan 和 Output Contract | 减少聚合、排序、过滤和输出错误 | 等待 E3-C |
| `E5-A` | 将选定父配置的同一信息外部化，不增加搜索或 Leaf | 验证 context store 信息等价 | 只做 smoke |
| `E5-B` | 增加受控 search/slice/compose | 测试程序化上下文探索 | 等待 E4-A/E5-A |
| `E6-A` | E5-B + matched-budget Root deliberation | 提供递归等预算对照 | 等待 E5-B |
| `E6-B` | E5-B + QueryPlan 驱动的一次 depth-1 Leaf | 测试分而治之的独立增益 | 等待 E6-A |

旧的无 QueryPlan R2、full-context Leaf、独立 Planner call、R4 Router、E5 全组合和 E6 trace folding 已删除或推迟。每个实验至少记录总准确率、双标签错误净变化、recovered/regressed、E0 稳定失败恢复数、Root/Leaf/DB 调用、tokens、context 读取和 API/解析失败。受时间预算限制，每个新配置先运行一次完整 197 题；小于约 2 pp 的变化只能记为趋势。

## 7. 新实验记录模板

复制下面的模板追加到本文档末尾：

```markdown
## 实验 E? — 简短机制名称

| 字段 | 内容 |
|---|---|
| 实验编号 | `E?` |
| 基线版本 | `E?` |
| 机制版本 | 例如 `tool-schema-check-v1` |
| 修改文件 | `path/to/file.py:line` |
| 修改内容 | 一句话说明行为变化 |
| 是否使用递归 | 否 |
| 模型与参数 | model / reasoning_effort / temperature / k / max_iterations |
| 数据集 | 数据集版本、题数、去重规则 |
| 输出文件 | `results/...json` |

### 机制假设

该机制预期解决哪一类错误？为什么？

### 实验结果

| 指标 | 基线 | 当前实验 | 变化 |
|---|---:|---:|---:|
| 总准确率 |  |  |  |
| `TOOL_ERROR` |  |  |  |
| `UNVERIFIED_FINAL` |  |  |  |
| `AGGREGATION_REASONING` |  |  |  |
| `DATASET_OR_GOLD_CONFLICT` |  |  |  |
| 平均迭代数 |  |  |  |
| 平均 LLM 调用数 |  |  |  |

### 代表性轨迹

- 改善：`bird_...`，说明什么变化？
- 未改善：`bird_...`，剩余根因是什么？可能可以通过什么机制或者实验解决？
- 可能回归：`bird_...`，新增机制造成了什么副作用？

### 结论

- [ ] 机制有效，可以保留
- [ ] 机制只改善特定错误，需要限制适用范围
- [ ] 机制无效或引入回归，撤销
- [ ] 需要更多运行确认

### 下一步

明确下一次只改一个机制，并说明对照组和验证指标。
```

## 8. 当前结论

E3-B 已完成：72/197（36.55%），比 E3-A 少 1 题，total tokens/题反而增加 4.54%；
因此只拒绝 `train-static-v1` 替代 few-shot。旧 E3-C run2 在 62/197 中断且混入 static patterns，只保留为诊断。旧 E3-F v1/v3 run1 也已完成 53/197 的中断分析：21/53（39.62%），相对同题 E0 均值仅 +2.83 pp，但 tokens/题 +40.34%，且 Schema 对 53/53 题交付全部表，因此停止该历史配置。当前先用新版 E3-C 独立验证 `e3-f-schema-v4 + k=1 few-shot`，并继续 E3-D 的 Query Mining 设计；`train-mined-v2` 尚无 slot 通过跨库门禁，所以不能启动或解读为完整 E3-F。只有 Query Mining 门禁通过后，才运行 `Schema v4 + Query Mining v2 + k=1 few-shot` 的 E3-F 集成实验。锁定 Offline 配置后依次测试 E4-A 的在线 QueryPlan、E5-A/E5-B
的 context externalization 与检索，再用 E6-A matched-budget 对照 E6-B depth-1 Leaf。
当前不做无 QueryPlan 递归、full-context Leaf、独立 Planner call、Router、完整组合矩阵、
trace folding 或 FINAL 同步。所有编号与基线关系以
`docs/experiment-plan/README.md` v1.0 为准。
