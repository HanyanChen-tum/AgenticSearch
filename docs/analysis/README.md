# Agent 错误轨迹分析与实验记录

English version: [README_EN.md](README_EN.md)

> **综合结论见 [SYNTHESIS.md](SYNTHESIS.md)**（2026-08-08）。本文档是流水记录，SYNTHESIS 是论证。三条主要结论：
>
> 1. **一个有效机制**：E3-C Offline Schema Context，`77/197 = 39.09%`，相对 E0 均值 **+4.82 pp**——把全量 Schema 换成按题确定性检索的片段。六个受测机制中唯一被接受的。
> 2. **一个结构性负面结论**：冻结商用模型上，验证类 harness 干预存在天花板——失败在验证能介入之前就已决定。四个独立机制全部失败，根因是失败题的循环恢复率精确为 0、且 99% 以上从未执行出正确结果。
> 3. **一个基准质量发现**：BIRD 困难子集可测 headroom 被显著高估——F-Audit 实测 40% 的"失败"是 gold 缺陷；+2.03 pp 只需对齐标注约定即可获得；**且在最应代表真实能力差距的"六配置全败"子集中，逐题审计后仅约 10% 是模型推理错误**（见 [`rootcause/`](rootcause/)）。

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

> **2026-08-07 更正**：下表已用 §4.1 修复后的分类器对 `e0_core_run1`/`e0_core_run2` 的 `classification_sheet.csv` 重新生成（原表由修复前的分类器产出，系统性低估 Schema/Join、高估过滤/低置信度兜底桶，详见 §4.1）。总数仍是 259 条，但 **Schema/Join 从原来的最小结构化类别（38 条）变为最大类别（97 条）**，聚合/分组从 82 条降到 43 条，过滤/低置信度从 67 条降到 36 条。下方"直接机制"和"实验顺序"列保持原判断不变，因为实际执行顺序（E3-C 先于 E4-A）恰好与修正后的类别大小一致；但过滤类的 F-Audit 抽样范围（原设计针对"67 条"）需要按新的 36 条低置信度记录重新界定。

| E0 失败归因（已按修复后分类器更新） | 直接机制 | 实验顺序 |
|---|---|---|
| 5 条运行、解析或工具问题 | 结构化 observation、重试、断点续跑和终止原因 | `E2-A`，只作为基础设施 |
| 75 条表选择/Join 路径错误 | Offline Schema Context、字段语义、PK/FK、关系基数和相关片段选择 | `E3-C` |
| 22 条 JOIN key/条件错误（新增子类，此前未被检出） | 同上，另需核对 JOIN `ON` 条件对应的外键列 | `E3-C` |
| 36 条过滤范围/表达式错误（原为 67 条） | 先区分 Agent 错误与 gold 歧义；再结合值语义和题目级条件结构 | `F-Audit` → `E3-C` / `E4-A`，必要时 `E5-B` |
| 43 条聚合/分组错误（原为 82 条） | 显式统计对象、grain、分组键、聚合函数、`WHERE/HAVING` 与阶段依赖 | `E4-A`；只有剩余问题存在可分 SubPlan 才进入 `E6` |
| 22 条排序错误（原为 11 条） | 显式排序指标、方向、Top-K、tie 和 `LIMIT` 层级 | `E4-A` |
| 48 条输出列数错误（不变） | 固定 answer type、列数、顺序、来源和投影检查 | `E4-A` |
| 8 条 YES/NO 与逐行输出错误（不变） | 在生成 SQL 前固定 boolean/scalar/rows 回答形式 | `E4-A` |

以上子类合计 259 条（5+75+22+36+43+22+48+8）。该映射依据运行后的 `semantic_error_class` 和细分语义归因制定；`UNVERIFIED_FINAL` 只保留为并行控制流诊断，不用于决定机制优先级。

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

> **2026-08-07 说明**：上表按前 70 题范围统计，未随分类器修复（§4.1）重新计算——该子集切片尚未单独重跑。已确认的是：E1 完整 71 题运行（`trace/e1_verified_run1/classification_sheet.csv`）用修复后分类器重新生成，`SCHEMA_LINKING` 从 5 升至 10、`SEMANTIC_REVIEW_REQUIRED` 从 9 降至 6（详见 [`e1_verified_summary.md`](analysisDetail/e1_verified_summary.md)）；E1 拒绝的结论（基于准确率和成本，不依赖分类器）不受影响。
关键判据仍是执行准确率和配对恢复/退化，而这两项没有支持 E1。

**固定前 50 题复核**

后续实验统一使用 `--limit 50`。在该共同子集上，E0 run1/run2 分别为 38%/40%，
E1 为 38%；E1 的调用和 token 仍约为 E0 的两倍，因此缩小到后续评测范围也不会改变结论。

**实验决策**

拒绝当前 strict verified-final：它提高了形式可验证性，但准确率下降、稳定正确题退化，
并显著增加调用、token 和延迟。后续 E2-E5 不继承该门控，`e4-r0` 已改为从 E0
只增加 capability gate。若以后重新测试最终验证，应优先采用控制器自动执行
`FINAL` SQL 的低成本方案，而不是要求模型通过多轮 ReAct 重复执行。

### 0.7 E3-A Train-Only Static Patterns 实验结果

**实验定义**

| 字段 | 内容 |
|---|---|
| 实验 ID | `E3-A` |
| Profile | `e3-a` |
| 父配置 | E0 |
| 唯一主要改动 | 增加人工归纳的 train-only `train-static-v1` pattern library，保留 `k=1` few-shot |
| 运行 | `e3_a_core197_run1` |
| run_id | `20260713T235804Z-19152b85` |
| 范围 | 固定 197 题：`both_wrong` 137 + `canary` 60 |
| 模型 | `azure/seminar-gpt-5.4-mini`，`reasoning_effort=high` |

E3-A 的 patterns 对所有问题固定注入，不按当前题检索；它是来源合规的静态规则原型，不具备 SQL AST 归一化、支持度、聚类、适用边界或跨库门禁，因此不代表完整 Query Mining。

| 指标 | E3-A | 相对 E0 两次均值 |
|---|---:|---:|
| 正确数/准确率 | 73/197 = 37.06% | +2.79 pp |
| `both_wrong` | 22/137 = 16.06% | — |
| `canary` | 51/60 = 85.00% | — |
| simple | 27/50 = 54.00% | — |
| moderate | 31/96 = 32.29% | E0 两次均为 27/96 |
| challenging | 15/51 = 29.41% | 无明确改善 |
| total tokens/题 | 14,751.72 | +8.7% |
| LLM 调用/题 | 2.74 | 约持平 |
| 延迟/题 | 38.01 s | — |

相对两次 E0 都失败的题，E3-A 稳定恢复 6 题；相对两次 E0 都正确的题，稳定回退 1 题。但单次 +2.79 pp 仍属于弱趋势，且成本高于 E0。

**全部 124 个失败的语义归因**（2026-08-07 用修复后分类器更新，见 §4.1）

| 实际原因层 | 数量 | 占全部失败 | 原数量（供对照） |
|---|---:|---:|---:|
| Schema/Join | 50 | 40.32% | 原 20（16.13%） |
| 输出契约 | 29 | 23.39% | 不变 |
| 聚合与排序 | 28 | 22.58% | 原 47（37.90%） |
| 过滤范围/表达式 | 13 | 10.48% | 原 24（19.35%） |
| 运行、工具或空结果 | 4 | 3.23% | 不变 |

Schema/Join 从原报告最小类别变为最大类别，聚合与排序则从最大类别降到第三。首要自动标签中有 93 个 `UNVERIFIED_FINAL`；其中 77 个是在错误 observation 后改写 SQL 但未执行——这 77 项的语义拆分（原文档给出的聚合31/输出20/Schema14/过滤12）同样基于修复前的分类器，尚未用新分类器重新核算，此处不再引用具体数字。固定 patterns 已包含聚合、Top-K 和输出提醒，但按修复后的数据，Schema/Join 才是 E3-A 最大的残留问题，而 E3-A 完全没有针对 Schema 设计任何机制。

**实验决策**

E3-A 只保留为“静态 train-only rules 可能有小幅收益”的历史证据，不作为 E3-C 的默认父配置，也不作为完整 Query Mining 已有效的证据。E3-C 回到 E0 知识控制条件并关闭 patterns；真正 Query Mining 单独放在 E3-D。

- [E3-A 完整 summary](analysisDetail/e3_a_summary.md)
- [E3-A vs E0 对比](analysisDetail/e3_a_vs_e0.md)

### 0.8 E3-B Patterns 替代 Few-Shot 实验结果

**实验定义**

| 字段 | 内容 |
|---|---|
| 实验 ID | `E3-B` |
| 历史 Profile | `e3-rf` |
| 父配置 | E3-A |
| 唯一主要改动 | 保留相同 static patterns，将 effective few-shot 从 `k=1` 改为 `k=0` |
| 运行 | `e3_b_core197_run1` |
| run_id | `20260714T023630Z-7eab3a22` |
| pattern artifact | `train-static-v1`，SHA-256=`bdda5b6aa4f6d1b69f3c86d2d299e60bb1429f6c2e62b1acd58323850b34cc48` |
| 范围 | 固定 197 题 |

历史 E3-A manifest 没有保存精确 pattern artifact 哈希，因此“两组 pattern 内容逐字相同”是设计意图，无法事后严格证明；E3-B 已补齐 artifact 内容和哈希。该限制降低严格单变量归因强度，但不改变 E3-B 的观察结果。

| 指标 | E3-A | E3-B | 变化 |
|---|---:|---:|---:|
| 正确数 | 73/197 | 72/197 | -1 |
| 准确率 | 37.06% | 36.55% | -0.51 pp |
| total tokens/题 | 14,751.72 | 15,421.28 | +4.54% |
| LLM 调用 | 539 | 552 | +13 |
| DB 调用 | 397 | 403 | +6 |
| 延迟/题 | 38.01 s | 39.34 s | +1.33 s |
| recovered/regressed | — | 4/5 | 净 -1 |

E3-B 恢复 `bird_877`、`bird_671`、`bird_587`、`bird_1387`，退化 `bird_743`、`bird_989`、`bird_189`、`bird_1238`、`bird_27`。迁移分散在聚合、输出、过滤和 Schema 四类，没有稳定的类别收益。相对 E0 两次稳定失败仍恢复 6 题，但稳定回退从 E3-A 的 1 题增加到 2 题。

| 实际原因层（2026-08-07 已更新） | E3-A | E3-B | 变化 | 原数值（供对照） |
|---|---:|---:|---:|---|
| Schema/Join | 50 | 59 | +9 | 原：20→22，+2 |
| 输出契约 | 29 | 26 | -3 | 不变 |
| 聚合与排序 | 28 | 26 | -2 | 原：47→45，-2（巧合一致） |
| 过滤范围/表达式 | 13 | 11 | -2 | 原：24→29，+5（方向相反） |
| 运行/工具/空结果 | 4 | 3 | -1 | 不变 |
| 全部失败 | 124 | 125 | +1 | 不变 |

移除 few-shot 后 Prompt 输入虽缩短，但模型产生了更多调用、推理和输出，total tokens/题反而增加。E3-B 因而同时未满足准确率保持和成本下降。

**实验决策**

拒绝“固定 static patterns 可以替代 train few-shot”的假设。E3-B 不进入后续父配置；该结论只针对 `train-static-v1`，不外推到带统计支持度、跨库验证和题目级检索的真正 Query Mining。

- [E3-B 完整 summary](analysisDetail/e3_b_summary.md)
- [E3-B vs E3-A / E0 配对分析](analysisDetail/e3_b_vs_e3_a_e0.md)

### 0.9 E4-R0 capability-gated 对照结果

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


### 0.10 旧 E3-F v1/v3 前 53 题诊断

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

### 4.1 分类器已知限制与本轮修复（2026-08-07）

本节记录对错误追踪机制本身的代码审计结果：追踪系统实际由三层构成，可靠度并不均匀，正式使用其分类结果前必须了解每层的检测方式。

| 层 | 实现位置 | 检测方式 | 可靠度 |
|---|---|---|---|
| 控制流分类 | `classify_failure()`，`scripts/make_classification_sheet.py` | 硬信号：无 assistant 输出、`predicted_sql` 为空、正则匹配 SQL error 字符串、`rows==[]`、all-null 检测 | 高，标注为 `"high"` |
| 语义分类 | `semantic_classification()`，同文件 | 正则/字符串级别的结构化启发式，比较 predicted 与 gold SQL 的列数、表集合、JOIN key、GROUP BY 字段、聚合关键字、ORDER BY 字段、LIMIT | 中，标注为 `"medium"`；无法归因时降级为 `"low"` |
| 检索审计 | `analyze_e3_f_retrieval.py` | 用 `sqlglot` 解析 gold SQL 的真实 AST，比对检索交付的表/字段集合 | 较高，属于结构化解析而非正则 |
| 轨迹审计 | `analyze_trajectory_audit.py` | 基于上述分类表和检索审计构建状态转移序列；`query_plan.adherence` 的通过/失败取自 `ours/agent/query_plan.py` 的 `plan_sql_adherence()` | 取决于其消费的上游结果 |

**审计发现的问题（修复前）：**

1. `semantic_classification()` 是"命中即返回"的级联检查，固定顺序为 YES/NO → 输出列数 → 聚合关键词存在性 → ORDER BY 方向 → 表集合 → 兜底 `SEMANTIC_REVIEW_REQUIRED`。若一条 SQL 同时选错了表**和**聚合结构，会因为聚合检查排在表检查之前而被打上 `AGGREGATION_REASONING`，掩盖真正的表选择错误。
2. 聚合检查原先只判断 `" group by "`、`"sum("` 等关键词**是否同时出现**，不比较 `GROUP BY` 的具体分组字段。predicted 和 gold 都有 `GROUP BY` 但分组列不同（文档 §3.3 反复点名的头号错误模式——"把全局统计写成按实体分组"）时，两边关键词都存在，判定无差异，直接漏检。
3. `ORDER BY` 检查原先只比较 `ASC`/`DESC` 方向关键词，不比较排序字段；两边都省略方向或方向相同、但排序列不同时同样漏检。
4. 表集合检查原先只看 `FROM`/`JOIN` 涉及哪些表名，不看 `ON` 条件里的外键列；选对表但连错 JOIN key（文档明确点名的 Schema/Join 错误子类型之一）测不出来。
5. 完全没有 `LIMIT`/Top-K 数值比较。
6. `docs/analysis/README.md` §4 定义的 `DATASET_OR_GOLD_CONFLICT` 和 `CORRECT_TRACE_MARKED_WRONG` 两个类别，在 `make_classification_sheet.py` 里**从未被任何代码路径赋值**——目前 100% 依赖人工在 CSV 里手填，而这正是 F-Audit 尚未完成的工作。这不是本轮要修的 bug（判断 gold 是否有噪声本质上需要人工判断），但必须明确标注：在 F-Audit 完成前，这两个类别的计数恒为 0，任何落入这两类的失败当前都被归到了其他结构化类别或 `SEMANTIC_REVIEW_REQUIRED` 里。

**本轮修复内容：**

`scripts/make_classification_sheet.py` 新增 `clause_span`、`split_top_level`、`bare_column`、`group_by_columns`、`order_by_items`、`limit_value`、`join_key_columns` 七个结构化提取函数，并重写 `semantic_classification()`：

- 检查顺序调整为 YES/NO → 输出列数 → **表集合 → JOIN key**（新，仅当表集合相同时才判定，避免与表错误重复计数）→ **GROUP BY 具体字段**（新，替代原来的关键词存在性判断）→ 聚合关键词存在性（保留，用于捕捉分组字段相同但聚合函数不同的情况）→ **ORDER BY 具体字段**（扩展，不再只看方向）→ **LIMIT 数值**（新）→ 兜底 `SEMANTIC_REVIEW_REQUIRED`；表/JOIN 检查提前到聚合检查之前，因为选错表是比聚合结构差异更基础的错误。
- 新增两个更细的子类别：`join_key_or_condition_mismatch`（挂在 `SCHEMA_LINKING` 下）、`limit_or_topk_mismatch`（挂在 `AGGREGATION_REASONING` 下）。
- 从"命中即返回单一标签"改为"跑完全部检查，选第一个命中项为主标签，其余命中项写入 `semantic_notes` 供人工复核"，不再让级联顺序掩盖并行存在的其他结构差异。
- `tests/test_make_classification_sheet.py` 新增 5 个回归测试，专门锁定此前检测不到的场景（分组字段不同但关键词都存在、排序字段不同但方向相同、`LIMIT` 不同、JOIN key 不同但表集合相同、表和聚合同时出错时表错误应为主标签）。全部 83 个仓库测试通过。
- 已知局限：`clause_span` 等辅助函数仍是正则层面的启发式，不是真正的 SQL AST 解析（不同于检索审计脚本用的 `sqlglot`）；嵌套子查询/CTE 内部若含有自己的 `GROUP BY`/`ORDER BY`，可能被误判为外层子句边界，已在函数 docstring 中标注。`ours/agent/query_plan.py` 的 `plan_sql_adherence()`（E4-A 使用的"是否遵循计划"检查）是独立的、更弱的检查——只比较从句存在性、表集合和输出列数，不比较 `GROUP BY`/`ORDER BY`/`filters` 的具体内容——本轮未修改，因为 QueryPlan 机制已随 E4-A 被拒绝而暂停；若后续重启 QueryPlan 工作，需要一并用同样的结构化字段比较升级该函数，否则"是否遵循计划"的判断会重复本次发现的同类弱点。

**修复前后的实际影响（e0_core_run1，128 条失败，未覆盖正式记录，验证脚本写入 scratch 目录）：**

| `semantic_error_class` | 修复前 | 修复后 | 变化 |
|---|---:|---:|---:|
| `SCHEMA_LINKING` | 20 | 49 | +29（+145%） |
| `AGGREGATION_REASONING` | 45 | 32 | −13（−29%） |
| `OUTPUT_CONTRACT` | 29 | 29 | 不变 |
| `SEMANTIC_REVIEW_REQUIRED` | 33 | 17 | −16（−48%） |

`SCHEMA_LINKING` 大幅上升主要来自新增的 JOIN key 检查——此前"选对表、连错外键"的情况完全没有被计入 Schema/Join 错误；`SEMANTIC_REVIEW_REQUIRED` 兜底桶几乎减半，说明相当一部分此前"无法归因、需人工复核"的失败，实际结构上可以被明确定位为 Schema/Join 或聚合问题。

**这对已发布结论的影响（需要下一步决定）：** 本文档 §0.5、§3.3-3.6 以及 `docs/experiment-plan/README.md` 里引用的 E0/E3-A/E3-B/E3-C/E4-A 错误分布表，全部由修复前的分类器生成。上面单个运行的验证已经表明该分类器系统性低估 Schema/Join 错误、高估兜底桶占比。这些历史表格暂未重新生成——是否用修复后的分类器批量重跑全部已完成实验的 `classification_sheet.csv` 并更新已发布的错误分布，需要单独决策；在此之前，`docs/experiment-plan/README.md` §3.5"由 E0 错误制定的改进顺序"和 F-Audit 的抽样范围（当前只覆盖"标记为过滤类的 67 条"）都建立在可能被低估的 Schema/Join 计数之上。

## 5. 当前根因判断

当前失败不是单一问题，优先级如下：

1. **严格 verified-final 已被拒绝。** E1 前 70 题为 40.00%，E0 配对均值为 42.14%；门控覆盖 63/70 题，调用与 token 约翻倍，稳定失败恢复 0 题、稳定正确退化 3 题。形式约束消除了 `UNVERIFIED_FINAL` 标签，但没有改善准确率。
2. **`sample_values` 的列校验问题已修复。** 当前需要通过 E0 重跑确认工具类错误是否按预期消失。
3. **成功执行不等于语义正确。** 表/Join 路径、聚合粒度、过滤范围、排序方向和多问题输出仍然是主要错误来源；2026-08-07 分类器修复后（§4.1），Schema/Join 是全部四个语义大类里数量最大的一类，优先级需要相应上调。
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
| `E3-C` | 回到 E0 知识控制条件，关闭 static patterns；用确定性检索的 Offline Schema Context 替代 runtime full Schema Prompt，保留 few-shot | 独立测量 Schema semantics、PK/FK、Join path、基数和值格式 | 正式 run3 完成：77/197（39.09%），接受为 E4-A 父配置；[summary](analysisDetail/e3_c_schema_v4_summary.md) |
| `E3-D` | 在 E3-C 上增加从 train question + SQL 自动归一化、聚类并按题 Top-K 检索的 Query Mining artifact | 减少聚合、排序、过滤、输出和 Join 结构错误 | Query Mining v2 无 slot 通过跨库门禁，暂停 |
| `E3-E` | 从通过的 E3-D 移除 train few-shot，其余完全不变 | 判断完整 Offline 知识能否替代 few-shot | 条件实验，仅 E3-D 通过后运行 |
| `E3-F` | `e3-f-schema-v4 + train-mined-v2 + k=1 few-shot`；关闭 static patterns 和 runtime full Schema，开启 capability gate | 测量修复后的完整 Offline 系统集成效果 | 历史 v1/v3 run1 在 53/197 中断：21/53=39.62%，Schema 实际全表注入且成本高，仅作[部分诊断](analysisDetail/e3_f_core197_run1_partial53_summary.md)和[同题比较](analysisDetail/e3_f_core197_run1_vs_e0_e3a_e3b_partial53.md)；新版仍因 Query Mining v2 0 个 slot 通过而暂停 |
| `E4-A` | 增加 Root 内 QueryPlan 和 Output Contract | 减少聚合、排序、过滤和输出错误 | 正式完成并拒绝：71/197（36.04%），较 E3-C -6 题；恢复 3、回退 9；tokens/题 +6.67%；[summary](analysisDetail/e4_a_core197_run1_summary.md)、[配对比较](analysisDetail/e4_a_core197_run1_vs_e3c_e0.md) |
| `E5-A` | 将选定父配置的同一信息外部化，不增加搜索或 Leaf | 验证 context store 信息等价 | 暂停：上游 E4-A 未通过，不把失败 QueryPlan 带入 |
| `E5-B` | 增加受控 search/slice/compose | 测试程序化上下文探索 | 暂停 |
| `E6-A` | E5-B + matched-budget Root deliberation | 提供递归等预算对照 | 暂停 |
| `E6-B` | E5-B + QueryPlan 驱动的一次 depth-1 Leaf | 测试分而治之的独立增益 | 暂停，不进入 Leaf |

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

当前最佳已验证配置仍为 E3-C Schema v4：77/197（39.09%）。E4-A schema v3 正式结果为 71/197（36.04%），相对 E3-C 恢复 3、回退 9、净损失 6，total tokens/题增加 6.67%。目标类恢复与目标类回退不满足预注册接受条件。

> **2026-08-07 分类更正**：本节原写"聚合/排序失败虽从 45 降至 41，但输出、过滤、Schema 和运行失败均上升"，这是基于修复前的语义分类器（未比较 GROUP BY/ORDER BY 具体字段和 JOIN key，见 §4.1）。用修复后的分类器重新统计，**方向是反的**：聚合/排序实际从 29 升到 33（**+4，E4-A 自己的设计目标变差了**），Schema/Join 反而从 46 降到 42（-4，改善）；目标类（聚合+输出）recovered/regressed 从原报告的"3:3 持平"变为 **3:5**（净回退 2），比原报告更不利于 E4-A。拒绝 E4-A、回退 E3-C 的决定不变（依据是原始 correct/incorrect 判定，与分类修复无关），但归因应更正为：**QueryPlan 直接让自己最想解决的聚合/排序问题变差了，不是"目标改善、被 Schema 等旁支拖累"**。详见 [`e4_a_core197_run1_summary.md`](analysisDetail/e4_a_core197_run1_summary.md) 和 [`e4_a_core197_run1_vs_e3c_e0.md`](analysisDetail/e4_a_core197_run1_vs_e3c_e0.md)。

轨迹进一步显示，82 个失败题的所有执行都通过结构 adherence（此为 QueryPlan 内部一致性检查的计数，不涉及语义分类器，不受本次修复影响），说明主要瓶颈是错误 QueryPlan，而不是 SQL 没有遵守计划；19 个使用合法 revision 的题只有 2 个正确，wrong → correct 恢复为 0。故拒绝当前 E4-A，回退 E3-C，并暂停 E5/E6。下一步完成 F-Audit；若重做 QueryPlan，必须先在 train-only 开发集验证计划语义，不能继续按固定 197 题 gold 调 Prompt。F-Audit 的抽样范围也应按 §4.1 更正后的过滤类计数（E0 两次合计 36 条，而非原来的 67 条）重新界定。

**2026-08-07 F-Audit（两轮）与"FINAL 前未核实字面量警告"机制（已拒绝）**：F-Audit（[`filter_audit.md`](analysisDetail/filter_audit.md)）对20题过滤/Schema疑似噪声样本做实际执行验证。第一轮：只有35%是干净的真实Agent错误，5题确认gold缺陷、2题被误归类为输出契约问题。**第二轮**对首轮标"混合/真实歧义/待核实"的6题逐一量化验证，`bird_1265`/`963`/`1252`三题从"不确定"升级为确认gold缺陷（`bird_963`/`1252`都是"缺DISTINCT"模式，与`bird_672`同类——**这是跨4个数据库反复出现的系统性gold编写bug，不是随机噪声**），`bird_937`靠数据库自带字段说明确认gold把"圈速名次"和"完赛名次"两个近义列搞混（与Schema诊断发现的近义表模式同源）。两轮汇总：**gold缺陷升至8题（40%），真实Agent错误降至6题（30%）**，比首轮更极端。基于F-Audit发现的"字面量未经sample_values核实"模式，实现并测试了一个新的软提示机制（`ours/agent/state.py`的`literal_verification_nudge`，新profile`e3-c-literal-check`）：N=8初测显示混合信号，**N=44分层扩测（覆盖全部11个数据库）显示净回退**（0恢复、4回退，50.0%→40.9%），且4条回退全部与字面量无关，指向"扩展上下文本身有副作用"。**已拒绝**，详见[`e3_c_literal_check_smoke2.md`](analysisDetail/e3_c_literal_check_smoke2.md)。机制一（近义表结构提醒）按讨论暂缓，留给E5/E6递归计划重启时再设计。

**2026-08-08 Hint 消融实验（BIRD 的 evidence 字段是致败原因之一）** → [`rootcause/hint_ablation_2026-08-08.md`](rootcause/hint_ablation_2026-08-08.md)：机械扫描发现 197 题中 **29 题的 Hint 声明了 gold 实际未使用的聚合公式**。三臂消融（只删 evidence 字段，其余不变）：**A 组（公式矛盾且原本失败）0/5 → 3/5**；**B 组（同签名但原本正确）5/5 → 5/5**；**C 组（值编码型 Hint、原本正确）5/5 → 5/5**。**删除 Hint 修好 3 题、零破坏。** 机制确认：`bird_604` 的 Hint 写 `Divide(Sum(UpVotes), Count(UserId))`，模型严格照做写 `SUM/COUNT`，gold 却用 `AVG`（NULL 处理不同）；删掉 Hint 后模型自行写出 `AVG`，与 gold 一致——**模型因忠实执行给定指令而被判错**。C 组无损害提示 E3-C 的 Schema artifact 已携带 `value_description` 使 Hint 冗余，这与 `findings.md` 中 legacy"Hint 为 large positive"不矛盾（那是无 Schema Context 时测的）。边界：定向抽样非随机，每组 n=5，不可外推为全集提升。**建议后续在完整 197 题上做 Hint 消融——这是当前唯一有干预性预实验支持、单变量、无需新代码，且可能产出真正可报告准确率改进的候选实验**（删除误导源不同于复现 gold 缺陷）。

**2026-08-08 反事实消歧实验（因果验证）** → [`rootcause/disambiguation_experiment_2026-08-08.md`](rootcause/disambiguation_experiment_2026-08-08.md)：对 7 条指代歧义题**只改写那一个歧义名词**（不出现表名/列名、不透露输出结构、Hint 不变），其余配置完全相同，两臂对照。**命中预期指代对象 1/7 → 6/7**，整题正确 0/7 → 2/7。指代歧义被证实为**真实因果原因**——改一个名词即纠正 5 条指代错误，说明模型不是"选不对表"，而是题面没给出选择所需的信息。未能整题转正的 4 条，在指代纠正后撞上了同一题并存的其它数据集侧问题（`bird_145` gold 返回重复行而模型用了 DISTINCT、`bird_465` 是非题 gold 返回 YES 而模型返回翻译文本、`bird_584` gold 结果含空字符串行）。**这把结论三从观测性证据提升为干预性证据。** 边界：n=7、仅覆盖指代歧义子类、改写在已知 gold 下完成故为上界，属诊断工具而非机制。

**2026-08-08 稳定失败逐题根因审计（推翻"能力缺陷"定性）** → 新目录 [`rootcause/`](rootcause/)：对 77 条"六配置全败"的稳定失败分层抽样 31 条逐题人工判定，关键判定均执行验证。结果**推翻了"稳定能力缺陷"这一表述**——仅约 **10%（3 条）** 是模型真实推理错误；**32%（10 条）是可执行验证的 gold 缺陷**（`bird_1029` gold 用 `ASC` 回答"最高"、`bird_879` 对 text 列字符串排序把 `'91.610'` 当成大于 `'257.320'`、`bird_218` 百分比逻辑与题意不符，三条均已执行确认）；**29%（9 条）是输出约定未指定**（返回 id 还是 name、gold 常多返回未被问及的列）；**13%（4 条）是指代歧义**（两表/两列同名，如 `DOC` vs `DOCType`）；另有 6% 是 Hint 与 gold 自相矛盾（模型严格照 Hint 实现，gold 违背自己的 Hint）。**"64% 的失败对整类 harness 干预免疫"结论仍成立，但原因是这些题的正确答案本身无法从题面推导**，而非模型能力不足。详见 [`rootcause/stable_failure_audit_2026-08-08.md`](rootcause/stable_failure_audit_2026-08-08.md)。

**2026-08-08 失败原因机械分解（剥离数据集问题后剩下什么）**：对 E3-C 的 120 条失败按结果集关系归类，并用 4 个检测器（AND/OR 优先级、计数问题非标量 gold、DISTINCT 可修、JOIN 后不去重计数）剥离 gold 缺陷——**对 F-Audit 8 条人工验证缺陷召回 8/8**；D4 经"加 DISTINCT 是否改变 gold 结果"精度过滤后，27 条原始标记中仅 4 条有强证据、13 条为误报。机械可确证的数据集问题约 9–13 条。**剩余 88 条中，77 条（87.5%）在全部六个配置下无一例外失败**（涵盖不同 Prompt、知识注入、有无 QueryPlan、有无 Schema 检索）——即 **64% 的失败对整类 harness 干预免疫**。最大类别内部：39 条为单数字答案，其中 24 条差 2 倍以上（数量级偏差而非边界问题），**整数倍 0 条**（否定"JOIN 行膨胀致计数放大"假设）。性质是：模型不是算错某一步，而是从一开始就在计算另一个量。可修上限：采样/集成至多 11 条，其余干预接近 0。详见 [`failure_decomposition_2026-08-08.md`](analysisDetail/failure_decomposition_2026-08-08.md)。

**2026-08-08 标注约定挖掘可行性（DISTINCT 案例，可行但性质需澄清）**：E3-D 诊断提出的替代方向——挖掘模型不可自得的**数据集标注约定**而非"问题→SQL结构"。以 F-Audit 发现的"缺 DISTINCT"模式为例量化：约定真实且稳定可迁移（train 85.9% 不用 DISTINCT，eval core197 83.9%，几乎相同）；**模型系统性违反且方向完全一致**（23 道可比题中 9 道不一致，9/9 全是"模型用了 DISTINCT、gold 没用"，0 反向）；机械移除 DISTINCT 后 **4 题转正 = +2.03pp**，成本近乎为零。**但转正题目中包含 F-Audit 经执行验证判定为 `DATASET_OR_GOLD_CONFLICT` 的 gold 缺陷题**——该机制提分的原理是让模型复现标注缺陷，而非改善推理。来源完全合规（train-only），但若报告为"提升 Text-to-SQL 准确率"则具误导性。建议作为可关闭的独立机制单列报告。**这条发现本身的价值可能高于那 2pp**：它量化了 benchmark 分数中有多少来自标注对齐而非查询能力，与 F-Audit 的"40% 失败是 gold 缺陷"互相印证。详见 [`annotation_convention_mining_2026-08-08.md`](analysisDetail/annotation_convention_mining_2026-08-08.md)。

**2026-08-08 E3-D Query Mining 诊断（判定不可行）**：`train-mined-v2` 长期 `enabled_slot_count=0`，此前未诊断是门禁过严还是方法不足。直接运行 builder 逐 slot 检查（9,428 条 train SQL，解析 0 失败）：**28 个 slot 无一接近门禁**，最高精度 `predicate_GT` 0.928（覆盖率仅 2.6%），最高覆盖 `output_count` 40.9%（精度 0.906），`join_count` 仅 0.610、`predicate_LIKE` 仅 0.084。**决定性检验**：`output_count` 是唯一可直接对照基线的高覆盖 slot，实测模型自己判定输出列数桶的准确率是 **89.1%**，挖掘规则 90.6%——**仅强 1.5 pp**，按覆盖率折算期望收益约 +0.6pp（197 题约 1 道），**低于本项目实测的 Prompt 扰动噪声（±4 道）**。根因：n-gram 特征做"问题表述→SQL 结构"预测，与强模型已有能力重叠。**门禁设计正确**——它在拒绝交付不优于模型现有判断的建议。E3-D 判定不可行，E3-F 随之继续暂停。详见 [`e3_d_query_mining_diagnosis_2026-08-08.md`](analysisDetail/e3_d_query_mining_diagnosis_2026-08-08.md)。

**2026-08-08 E5-A 同信息外部化（通过）**：把 `hint`/`few_shot`/`offline_metadata` 从 Prompt 移入只读 context store（`ctx.list()`/`ctx.read()`），父配置 E3-C，不涉及被拒绝的 QueryPlan。**通过条件一（信息等价）**：全部 197 题离线逐字节比对，197/197 一致、0 失败，无 LLM 成本。**通过条件二（可达性）**：11 题覆盖全部数据库，模型主动读取 59 次（5.36 次/题，0 题未读），无越权。**一个预测被推翻**——基于 ReAct 循环测量我曾预期模型懒得读，实测相反：模型为"获取信息"调用 5.36 次工具，却只为"验证 SQL"调用 1.6 次，且 store 模式下 `sample_values` 降至 0，印证"验证行为不是工具可达性问题"。准确率同 11 题 5/11 持平（非通过条件），回退的 `bird_92` 是唯一只读 hint、从未读 schema 的题——"信息可达但模型未取用"是外部化引入的新失败模式。**但成本测量是决定性的**：外部化带来 **+108.9% total token、+312.3% 延迟、+100% LLM 调用**（prompt token 降 17.5%，推理 token 涨 283%，且大量重复读取）。根因结构性：**本任务知识载荷仅 726–2,572 tokens、prompt 约 5,171 tokens，上下文利用率约 4%**——context store 针对的"上下文装不下"约束在此不存在，外部化只剩开销。据此 **E5-B 不建议作为准确率实验运行**（两条接受轴先验都差：89–93% 的残留失败本已具备所需信息，查找不是瓶颈；而 E5-B 会进一步增加调用轮次）。详见 [`e5_a_context_store_smoke1.md`](analysisDetail/e5_a_context_store_smoke1.md)。

**2026-08-08 ReAct 循环有效性测量（关键结构性发现）**：此前所有轨迹审计只统计失败题，"0 次 wrong→correct 恢复"带循环论证性质。本次在全部 197 题上重测（纯离线，无 LLM 成本），得到三条一致结果：(1) 循环**有效但极端二值**——正确题恢复率 4-14%（E3-C 4/77、E0 3/69 和 9/66），错误题恢复率**三次运行精确为 0**，且 99% 的失败题全程从未执行出过匹配 gold 的结果，**循环没有可救的东西**；(2) 模型**不会自适应增加探索**——正确题与错误题的执行次数（1.2-1.6/题）和多次执行占比（27-38%）几乎相同，8 轮预算实际只用 1-2 轮；(3) **约 2/3 的正确答案，其提交的 FINAL SQL 从未被执行验证过**（正确题仅 31-36% 验证过，9-20% 甚至全程未调用 `db.execute`），顶层 README"test its query, see real results, and only then submit"的描述只覆盖约三分之一的正确答案。**这为本项目四个失败机制（E1、E4-A、字面量核实、JOIN 精简）提供了统一解释**——它们全在强化"自我检查"这一环，而该环对失败题的边际价值接近零，因为失败题没有可供检查的正确候选。在动作层独立复现了 Thought Anchors 的结论（PS/PG 是 anchor，SC 因果影响≈0），并与 SQRL 的论证吻合（inspection 决策需训练习得，非指令可及）。详见 [`react_loop_efficacy_2026-08-08.md`](analysisDetail/react_loop_efficacy_2026-08-08.md)。

**2026-08-07 防御性过度 JOIN 提醒（初步正向，样本太小，未定论）**：源自 Schema/Join 诊断 §3.3 的另一独立模式——模型不确定时倾向多连表兜底。实现为固定静态协议文字（`ours/agent/prompts.py` 的 `basic-join-minimal`，新 profile `e3-c-join-minimal`），架构上刻意区别于已拒绝的机制二（不随trace累积文本）。客观筛选 e3-c 全部120条失败里"预测表集合是gold真超集"的12题为目标，配14题防回归对照，N=26 smoke：**恢复2、回退1，净+1（53.8%→57.7%）**。2次恢复直接命中机制设计意图（改INNER为LEFT JOIN避免丢行、去掉多余表连带修正了输出列选择）；1次回退可解释为提示语被泛化（"精简JOIN数量"被误套用到"JOIN类型选择"）而非无关噪声，与机制二"回退跟机制无关"的证据结构不同。**样本太小不足以下结论**，详见[`e3_c_join_minimal_smoke1.md`](analysisDetail/e3_c_join_minimal_smoke1.md)。

**2026-08-07 v2 复测（同批26题，净效果归零，不再迭代措辞）**：把"精简表数量"和"不要改变JOIN类型"拆开说明后，`bird_27`确认修复，但新增2个无关回退（`bird_1480`、`bird_877`，均为输出契约问题），净变化归零（14/26=53.8%，等于baseline）。其中`bird_1480`在机制二（已拒绝）的N=44测试里也以相同症状回退过——两次完全不同的机制改动都在同一题上出同一种错，指向这批小样本里存在对任何Prompt扰动都不稳定的"脆弱题"，N=26不足以把题级噪声和机制真实效应分开。**决定不再在这个小样本上继续手调提示措辞**（避免陷入用固定样本反复调参的方法论红线），详见[`e3_c_join_minimal_v2_smoke1.md`](analysisDetail/e3_c_join_minimal_v2_smoke1.md)。下一步：要么把v1一次性扩大到N=44级别的分层样本做正式判定，要么搁置转向其他方向。

**2026-08-07 Schema/Join 深度诊断**（详见 [`schema_join_diagnosis_2026-08-07.md`](analysisDetail/schema_join_diagnosis_2026-08-07.md)）：对 E3-C 残留的 46 条 Schema/Join 失败逐题核对 retrieval audit 后发现，93.5%（43/46）发生在检索已经完整交付所需表/字段的情况下——瓶颈不是检索召回，是模型在近义表/字段之间选错。具体定位到三个可枚举、可直接修复的混淆点：`formula_1` 的 `results` 与 `driverStandings`、`codebase_community` 的 `comments` 表与 `postHistory.Comment` 字段、`european_football_2` 里 `Player` 表的两个候选连接键（`player_api_id`/`player_fifa_api_id`）。另发现 `thrombosis_prediction` 的部分失败可能是 gold 侧"必经 `Patient` 中转表"的书写惯例而非 Agent 错误，需要并入 F-Audit 复核。建议先给这几个具体表/字段补充 Offline Schema metadata 消歧说明，做最小可行验证，而不是直接扩大检索范围或等 Query Mining。
