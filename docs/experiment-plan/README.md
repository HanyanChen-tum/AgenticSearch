# DB-RLM 统一实验计划

版本：v1.0  
更新日期：2026-07-14  
当前状态：E0、E1、E2-B、E3-A、E3-B 已完成；旧 E3-C run2 在 62/197 中断；旧 E3-F v1/v3 run1 在 53/197 中断且仅作诊断；E3-F Schema v4 已实现，但 Query Mining v2 的严格跨库门禁没有任何 slot 通过，因此暂停新版 E3-F 正式运行  
正式数据：`bird_cleancore_ids.json` 固定 197 题  
原则：实验顺序由每轮错误轨迹证据决定；一次只改变一个可归因机制。每次运行后先分析完整 trace、双标签语义归因和 recovered/regressed，再决定下一轮唯一变量，不预先假定最终架构。

## 0.1 为什么需要分类与消融实验

本计划的目标不是把多个模块一次性叠加到 Agent，而是逐步验证希望融合进 Agent 的三个主要机制：

1. **可编程的上下文与代码化推理**：Agent 能够把 Schema、metadata、query patterns、QueryPlan、observation 和证据引用组织成可检索、可组合的结构，而不是依赖一段不可追踪的长 Prompt。
2. **受控的执行环境**：工具、数据库访问、observation、终止原因和上下文读取都由 manifest/capability gate 约束，使结果可复现、能力边界可审计，并把运行故障与语义推理错误分开。
3. **可验证的自我改进与分而治之**：Root 先形成全局 QueryPlan，根据执行反馈修正约束；只有存在明确可独立验证的复杂 SubPlan 时，才使用受控 depth-1 Leaf，并与等预算的额外 Root 思考比较。

这三个机制不能直接作为一个整体实验，因为 E0 的失败来自不同层面。E0 的 259 条失败记录主要集中在聚合/排序（93）、过滤语义（67）、输出契约（56）和 Schema/Join（38），另有运行、解析和工具问题（5）；124 道稳定失败中有 110 道保持相同语义大类。同时，`UNVERIFIED_FINAL` 等控制流标签会遮住底层语义，且 E1 已显示 strict verified-final 增加成本却没有解决主要错误。因此必须先按错误形成机制分类，再用消融实验隔离每个改动的因果贡献。

实验顺序采用“**运行 → 轨迹分析 → 错误迁移 → 更新假设 → 下一实验**”闭环：

```text
固定 197 题运行
  ↓
读取 manifest、trace、observation、SQL 变化和 token/调用成本
  ↓
按控制流 + semantic_error_class 双标签归因
  ↓
比较目标类别、稳定失败、recovered/regressed 和非目标回退
  ↓
只选择一个由证据支持的机制增量
  ↓
冻结其余变量，运行下一阶段并更新本计划
```

因此，实验编号表示当前证据驱动的阶段，不表示预先固定的技术路线：如果某一轮错误迁移显示目标类别没有下降，后续应修正该机制或回退父配置，而不是继续叠加模块。

## 0. 实验机制大分类

| 大类 | 实验族 | 核心问题 | 包含内容 | 与其他大类的边界 |
|---|---|---|---|---|
| A. 基线与控制流 | E0、E1 | 当前 Agent 能力和 FINAL 强约束是否有效 | Clean DB ReAct 基线、strict verified-final 对照 | 不增加新知识、不改变上下文访问方式 |
| B. 基础设施与能力隔离 | E2 | trace 和工具边界是否足以支持可靠实验 | 结构化 observation、终止原因、断点续跑、capability gate | 不作为准确率机制，不提炼语义知识 |
| C. Offline Knowledge | E3 | 预先构建的知识内容是否有独立价值 | Query patterns、Offline Schema Context、Join metadata、值格式、后续 repair rules | 不增加 QueryPlan 或递归；E3-C 只做确定性片段选择，不开放模型主动搜索 |
| D. 在线题目级形式化 | E4 | 模型能否把当前问题显式转化为可检查约束 | QueryPlan、过滤结构、Output Contract | 属于当前题在线推理，不属于 Offline artifact |
| E. RLM 上下文环境 | E5 | 同样的信息是否能通过程序化访问得到更好利用 | context store、`search/slice/compose`、fragment 引用 | 信息集合保持不变，不允许 Leaf |
| F. 受控递归 | E6 | 分而治之是否优于等预算 Root 思考 | matched-budget Root 对照、depth-1 SubPlan Leaf | 只在 E5 通过后运行，不重建全局 QueryPlan |

每个大类的 A/B/C 子实验在对应阶段内定义。过滤人工审计是 E4 的支持任务，不占实验编号；trace folding 是暂缓的效率扩展。

## 1. 希望融合进 Agent 的三个主要机制

本项目不是把现有 Agent 改名为 RLM，而是验证 RLM 的三个核心能力。

### 1.1 代码化推理与上下文探索

模型不再只能被动读取完整 Prompt，而是可以在受控环境中执行：

- `search`：按表、列、概念、模式或关键词搜索；
- `slice`：只读取当前 SubPlan 所需片段；
- `compose`：组合 Schema、metadata、patterns 和 observation；
- 结构化保存 QueryPlan、候选 SQL、证据引用和执行状态。

目标是让上下文使用可追踪、可复现，并减少长 Prompt 中的信息遗漏。

### 1.2 受控代码执行环境

环境保存 Schema、Hint、PK/FK、Join path、Offline artifacts、DB observation、候选 SQL、QueryPlan 以及 Root/Leaf 的调用记录。所有实验必须使用 capability gate，只允许 manifest 声明的工具，禁止隐藏 Schema API 和通用 `recursive_llm` 污染对照。

### 1.3 自我改进与分而治之

Root 先形成全局 QueryPlan，再根据 DB observation 修正 SQL。只有计划中存在明确复杂 SubPlan 时，才允许调用一次 depth-1 Leaf。

```text
Root 全局 QueryPlan
  ↓
DB ReAct 执行与反馈
  ↓
必要时选择一个复杂 SubPlan
  ↓
Leaf 返回局部证据或 SQL 片段
  ↓
Root 按全局 grain/output contract 合并并提交
```

递归必须与“额外一次 Root 思考”的等预算对照比较，才能证明分而治之本身有效。

## 2. 研究问题与因果边界

本计划依次回答：

1. Offline artifacts（patterns、Schema/Join metadata、后续 repair rules）分别是否有独立价值，patterns 能否替代 train few-shot？
2. 题目级 QueryPlan 是否减少聚合、排序和输出契约错误？
3. Schema metadata 与 Join path 是否减少表选择和连接错误？
4. 同样的信息外部化后是否完整可达？
5. 程序化搜索、切片和组合是否优于直接 Prompt？
6. 相同额外调用预算下，受控 Leaf 是否优于 Root 自己继续思考？

以下内容不作为新贡献：已有 DB ReAct、SQL error/空结果反馈、high reasoning 模型、capability gate 本身，以及运行后使用 gold 进行错误分类。

Gold 只允许用于离线评分和运行后诊断，不得进入 Agent、Prompt、artifact、检索、QueryPlan 或在线路由。

## 3. E0 基线与错误驱动顺序

### 3.1 E0 定义

E0 使用 `clean-e0` / `clean-protocol-v1`、train-only `k=1` few-shot、Hint + Schema + few-shot 直接上下文、`db.sample_values`、`db.execute` 和多轮 DB ReAct。它关闭 verified-final，不使用 patterns、legacy hints、metadata、QueryPlan、context store 或递归。

### 3.2 E0 已完成结果

| 指标 | Run1 | Run2 | 聚合 |
|---|---:|---:|---:|
| 正确数 | 69/197 | 66/197 | 均值 67.5/197 |
| 准确率 | 35.03% | 33.50% | 均值 34.26% |
| LLM 调用/题 | 2.76 | 2.72 | 2.74 |
| DB 调用/题 | 1.89 | 1.90 | 1.90 |
| Total tokens/题 | 13,658.99 | 13,481.25 | 13,570.12 |

- 稳定正确 62 题，稳定失败 124 题，不稳定 11 题；
- 两次评测 SQL timeout 字段不同，不是严格同协议复现；
- token usage 分别缺失 9/11 次，成本是下界。

详细报告：[E0 summary](../analysis/analysisDetail/e0_core_summary.md)。

### 3.3 E0 双标签错误分布

两次共有 259 条失败记录。`UNVERIFIED_FINAL` 会覆盖底层语义，因此机制规划使用 `semantic_error_class`。

| 实际原因 | Run1 | Run2 | 合计 | 占失败记录 |
|---|---:|---:|---:|---:|
| 聚合与排序 | 45 | 48 | 93 | 35.91% |
| 过滤范围/表达式 | 33 | 34 | 67 | 25.87% |
| 输出契约 | 29 | 27 | 56 | 21.62% |
| Schema/Join | 20 | 18 | 38 | 14.67% |
| 运行、解析或工具 | 1 | 4 | 5 | 1.93% |

| 稳定失败类别 | 题数 |
|---|---:|
| 聚合与排序 | 41 |
| 过滤语义 | 28 |
| 输出契约 | 25 |
| Schema/Join | 16 |
| 类别变化或运行噪声 | 14 |

124 道稳定失败中，110 道保持相同语义大类，107 道保持相同子类。后续核心指标是恢复这些稳定结构性错误，不是只提高一次总分。

### 3.4 `UNVERIFIED_FINAL` 的判断

E0 两次共有 215 条：

| 子类 | 数量 | 含义 |
|---|---:|---|
| 错误 observation 后改写未执行 | 180 | 最近执行 SQL 已错，提交最后执行 SQL 也不会修复 |
| observation 不可解析后改写 | 18 | trace/工具可观测性问题 |
| 未执行 DB 就 FINAL | 9 | 控制流问题 |
| 正确 observation 后改坏 | 4 | 宽松 FINAL 的真实回退 |
| 空结果后改写 | 3 | 需要重执行，但不是主要来源 |
| 成功 observation 无法对齐 | 1 | 历史 trace 限制 |

结论：保留为控制流诊断，不作为实验排序依据。E1 已证明 strict verified-final 不值得默认启用。

### 3.5 根据 E0 错误制定的改进顺序

| 优先级 | E0 证据 | 改进机制 | 实验 |
|---:|---|---|---|
| 0 | 运行/解析/工具 5 条，observation 解析影响归因 | trace、manifest、结构化 observation | E2-A |
| 1 | Schema/Join 38 | 先独立验证 Offline metadata + PK/FK + Join path，关闭未验证的 static patterns | E3-C |
| 2 | 聚合/排序 93、输出契约 56、过滤 67；E3-A 静态规则覆盖不足 | 从 train question + SQL 做真正 Query Mining，再条件性消融 few-shot | E3-D、E3-E |
| 3 | 聚合/排序 93；输出契约 56 | Root QueryPlan + output contract | E4-A |
| 4 | 过滤 67，但置信度低 | 人工审计；QueryPlan 条件结构；必要时值检索 | F-Audit、E4-A、E5-B |
| 5 | 直接 Prompt 可能未有效使用上下文 | 同信息外部化和程序化检索 | E5-A、E5-B |
| 6 | 多阶段复杂题仍失败 | QueryPlan 驱动 depth-1 Leaf | E6-A、E6-B |

每一阶段完成后必须重新检查错误迁移；不得因为递归是最终目标就跳过 E3-C、E4-A 和 E5-B，否则无法归因。若新运行显示优先级改变，应在下一轮计划中记录证据并调整顺序。

## 4. 统一实验协议

### 4.1 固定数据与模型

| 变量 | 固定值 |
|---|---|
| 数据集 | `data/processed/bird_dev_500.json` |
| ID 文件 | `data/processed/bird_cleancore_ids.json` |
| 题组 | `both_wrong` 137 + `canary` 60，共 197 |
| train pool | `data/train_pool.json`，9,428 条 |
| 模型 | `azure/seminar-gpt-5.4-mini` |
| temperature | `0` |
| reasoning effort | `high` |
| max iterations | `8` |
| SQL timeout | `30s` |
| evaluator | 相同 BIRD execution evaluator |
| 新配置运行次数 | 时间预算下 1 次完整 197 题 |

固定 ID 顺序，不重新抽样。Smoke 只验证代码、信息等价和 trace，不用于准确率结论。

### 4.2 单变量和 Manifest

每次运行必须记录：

- `run_id`、profile、父配置和 config hash；
- 数据集、ID 文件、数据库和 SHA-256；
- Prompt 版本与哈希；
- few-shot requested/effective `k`、pool hash、retriever；
- pattern/metadata/rule artifact hash；
- context mode、capability manifest；
- QueryPlan schema version；
- Leaf 深度、次数和预算；
- planned/completed count；
- 模型参数、timeout 和 usage 完整性。

旧 trace manifest 与当前配置不同时，必须新建 output/trace，不能混跑。

### 4.3 统一输出

```text
results/<experiment>_core197_run1.json
trace/<experiment>_core197_run1/run_manifest.json
trace/<experiment>_core197_run1/transcripts.jsonl
trace/<experiment>_core197_run1/classification_sheet.csv
trace/<experiment>_core197_run1/traces_report.html
docs/analysis/analysisDetail/<experiment>_summary.md
docs/analysis/analysisDetail/<experiment>_vs_parent.md
```

### 4.4 必报指标

| 类型 | 指标 |
|---|---|
| 主指标 | 正确数、执行准确率 |
| 配对 | both correct、recovered、regressed、both wrong、ID |
| 稳定性 | E0 124 稳定失败恢复、62 稳定正确回退 |
| 错误 | 聚合/排序、过滤、输出契约、Schema/Join、运行问题 |
| 分组 | simple/moderate/challenging；both_wrong/canary |
| 成本 | Root/Leaf/LLM/DB calls；各类 tokens |
| 可靠性 | API、parse、timeout、missing FINAL、usage 缺失 |
| RLM 环境 | context reads、检索词、片段 ID/hash、可见 tokens |

### 4.5 统一错误分类

`classification_sheet.csv` 必须包含 `wrong_turn,error_class,subcategory,semantic_error_class,semantic_subcategory,fix_idea,notes`。

| 类别 | 判定依据 | 置信度 | 改进 |
|---|---|---|---|
| 聚合/排序 | GROUP BY、aggregate、HAVING、ORDER/LIMIT 结构差异 | 中 | E4-A |
| 输出契约 | 列数、顺序、boolean/rows/scalar 差异 | 中高 | E4-A |
| Schema/Join | 表集合、字段来源、Join path 差异 | 中 | E3-C |
| 过滤语义 | 运算符、值、时间、AND/OR、作用层级 | 低 | F-Audit、E4-A、E5-B |
| 控制流 | 未执行 FINAL、改写未执行、MaxIterations | 高 | 诊断/基础设施 |
| 运行工具 | API、parse、timeout、observation 不可解析 | 高 | E2-A |

Gold 差异只用于运行后归因，不可进入下一次 Agent Prompt 或 artifact。

### 4.6 判断规则

- 小于约 2 pp 的单次变化只称为趋势；
- 必须同时查看目标类别净变化和 recovered/regressed；
- 目标错误减少但其他错误大量回退，不能接受；
- API/runner 恢复不能冒充推理收益；
- 成本增加时报告单位恢复题成本；
- 未通过接受条件时停止该分支，不继续叠加。

## 5. 阶段 A：基线与控制流（E0/E1）

| 子实验 | 父配置 | 唯一变量 | 目的 | 状态 |
|---|---|---|---|---|
| E0 | 无 | Clean DB ReAct baseline | 建立准确率、成本、稳定性和错误结构基线 | 已完成，197 题两次 |
| E1 | E0 | FINAL 必须等于最近一次成功、非空且已执行 SQL | 判断 strict verified-final 是否值得继承 | 已完成并拒绝 |

### 5.1 E0：Clean DB ReAct

| 字段 | 内容 |
|---|---|
| 父配置 | 无 |
| 唯一目的 | 建立 clean baseline |
| 范围 | 197 题，两次探索性运行 |
| 结果 | 69/197、66/197，均值 34.26% |
| 决策 | 保留为历史比较中心 |

主要结论：稳定失败 124 题，语义错误远多于运行错误；后续按 3.5 节排序。

### 5.2 E1：Strict Verified-Final

| 字段 | 内容 |
|---|---|
| 父配置 | E0 |
| 唯一变量 | FINAL 必须等于最近一次成功、非空、已执行 SQL |
| 范围 | 前 70 题配对 |
| E0 配对均值 | 42.14% |
| E1 | 28/70 = 40.00% |
| 成本 | LLM calls 约 2.03 倍；tokens 约 2.00 倍；延迟约 1.75 倍 |
| 行为 | 103 次 `final.blocked`，覆盖 63/70 |
| 稳定变化 | 恢复 E0 稳定失败 0；退化 E0 稳定正确 3 |
| 决策 | 拒绝 |

E1 消除了 `UNVERIFIED_FINAL` 标签，但未修复聚合、输出、过滤或 Schema 语义。后续不继承 strict gate，不做独立 FINAL 同步。

详细报告：[E1 summary](../analysis/analysisDetail/e1_verified_summary.md)。

## 6. 阶段 B：基础设施与能力隔离（E2）

| 子实验 | 父配置 | 唯一变量 | 目的 | 状态 |
|---|---|---|---|---|
| E2-A | 与内容配置无关 | 结构化 observation、独立终止原因、断点续跑和 usage 缺失记录 | 保证 trace 可解析、可复现 | 正式实验前必须通过 |
| E2-B | E0 | capability gate，只允许声明工具 | 验证能力隔离和越权审计 | 已完成；历史结果名 E4-R0 |

### 6.1 E2-A：结构化 Observation 前置条件

这不是准确率消融。要求：

- `db.execute` 返回 `{sql,status,columns,rows,error,truncated}`；
- trace 保存原始结构化结果，不从 Markdown 反推；
- APIError、timeout、empty FINAL、parse failure 使用独立终止原因；
- 断点续跑不改变已完成题；
- usage 缺失单列。

通过条件：smoke 中所有 tool observation 可解析；正式运行不可解析率单列。基础设施修复不计为模型机制收益。

### 6.2 E2-B：Capability Gate 校准

| 字段 | 内容 |
|---|---|
| 父配置 | E0 |
| 唯一变量 | 只允许 `db.execute`、`db.sample_values`；禁止递归和隐藏 Schema API |
| 范围 | 前 50 题 |
| 结果 | 19/50 = 38.00%；E0 为 38%/40% |
| 工具审计 | 110 个事件全部在允许集合；0 越权 |
| 决策 | 接受 capability gate 作为基础设施，不作为准确率机制 |

后续 E3-C、E4-A、E5-A、E5-B 和 E6-B 都继承能力隔离原则。

详细报告：[E4-R0 summary](../analysis/analysisDetail/e4_r0_summary.md)。

## 7. 阶段 C：Offline Knowledge（E3）

### 完整 Offline 系统定义

Offline 系统不等于 query mining。它指在正式回答评测问题之前，从来源合规的数据中预先构建、审计、版本化和索引知识 artifact；运行时只读取已冻结的 artifact，不使用当前评测题的 gold、评分或错误结果更新知识。

```text
Offline System
├─ 1. Query/SQL mining
│  ├─ 聚合粒度与多阶段聚合模式
│  ├─ 过滤、Top-K、排序和 DISTINCT 模式
│  ├─ 输出契约与条件回答模式
│  └─ 通用 Join/窗口函数结构
├─ 2. Schema/metadata mining
│  ├─ 表、字段、类型、字段语义和别名
│  ├─ PK/FK、Join graph 和候选 Join path
│  ├─ 一对一/一对多/多对多关系及重复行风险
│  └─ 值类型、日期、单位、NULL、编码格式和受控样例
├─ 3. Train error/repair mining
│  ├─ 错误触发条件
│  ├─ 修复动作
│  ├─ 适用边界
│  └─ 反例与 counterexamples
└─ 4. Artifact governance
   ├─ 来源与 split
   ├─ 构建脚本和版本
   ├─ 支持度、覆盖范围和 SHA-256
   └─ 检索策略、能力边界和泄漏审计
```

Offline 系统分为三层：

| 层 | 职责 | 当前实现/实验 |
|---|---|---|
| 内容构建层 | 从 train question/SQL、数据库 Schema/描述和合规 train 轨迹提炼可复用知识 | E3-A 静态 patterns 原型；E3-C Schema/metadata；E3-D 真正 Query Mining；E3-F 集成修复后的 Schema Context 与 Query Mining |
| Artifact 管理层 | 固定来源、版本、支持度、哈希、覆盖范围和构建配置 | `train-static-v1`（历史原型）、`e3-f-schema-v4`、`train-mined-v2` 及 run manifest |
| 运行时交付层 | 决定把全部内容直接注入、确定性选择片段，还是由 Agent 主动检索 | E3-C 确定性选择 Schema 片段；E3-D Top-K 检索 mined patterns；E5 测模型主动 `search/slice/compose` |

完整 artifact 不等于把完整内容放入 Prompt。Artifact 可以保存全库信息，但单题运行只应看到完成当前问题所需的片段：

```text
预构建并冻结完整 artifact
  ↓
根据 question + evidence 选择相关表、字段和 FK 邻接
  ↓
将有限 Schema/metadata fragment 交给 Root
  ↓
Root 使用 db.sample_values / db.execute 验证不确定信息
```

E3 与 E5 的边界是：E3 研究“Offline 中有什么内容，以及固定策略选出的内容是否有价值”；E5 研究“模型能否通过程序化接口主动搜索、切片和组合同一批内容”。E3-C 的确定性词法选择和 FK 邻接在模型调用前完成，不算模型主动 context exploration。

Train few-shot 是 E0 已有的 train-only 参考信息，不等同于 query mining artifact。E3-A 的 `train-static-v1` 是人工归纳的静态规则原型，没有完成 SQL 结构归一化、支持度统计、聚类、适用边界和按题检索，因此不能代表完整 Query Mining。E3-B 只证明该静态原型不能替代 few-shot。为避免旧 patterns 与 E3-C 的 Schema 机制混杂，E3-C 关闭 patterns、保留 few-shot；E3-D 再在 E3-C 上单独加入真正的 Query Mining；只有 E3-D 有效时，E3-E 才移除 few-shot。

Offline artifact 的统一生命周期为：

1. 冻结允许的数据源和 split；
2. 构建 artifact，并记录脚本、参数、版本、来源与 SHA-256；
3. 在不查看当前实验评分的前提下完成结构、覆盖和泄漏检查；
4. 冻结 artifact 与检索策略后运行实验；
5. 运行后分析完整 trace、semantic error、recovered/regressed、片段覆盖和成本；
6. 根据错误轨迹提出下一轮假设，但不得用固定 197 题的 gold 或失败 SQL 反向改写在线 artifact；
7. 只有来自合规 train 数据的新证据才能进入下一版 Offline artifact。

不属于 Offline 内容的机制包括：当前题 QueryPlan、DB observation、FINAL 控制、模型主动 `search/slice/compose`、Root/Leaf 路由和递归计算。它们分别由 E4、E2/E4、E5 和 E6 独立测试。

| 子实验 | 父配置 | Offline 内容增量 | 目标错误 | 状态 |
|---|---|---|---|---|
| E3-A | E0 | 人工归纳的固定 train-only static patterns，保留 few-shot | 验证静态规则原型 | 已完成；弱证据，不作为默认父配置 |
| E3-B | E3-A | 移除 train few-shot，保留相同 patterns | 判断 patterns 的替代价值和成本 | 已完成并拒绝 |
| E3-C | E0 | 关闭 static patterns；保留 few-shot；用 Offline Schema Context 替代 runtime full Schema Prompt | Schema linking、字段来源、Join 与 Prompt 冗余 | 已升级为 Schema v4，下一步先做分层 smoke |
| E3-D | E3-C | 从 train question + gold SQL 自动挖掘、归一化、聚类并按题检索 Top-K patterns | 聚合、排序、过滤、输出和 Join 结构错误 | 待设计与实现 |
| E3-E | E3-D | 仅移除 train few-shot，保留 Schema Context 与 mined patterns | 判断完整 Offline 知识能否替代 few-shot | 条件实验：仅 E3-D 通过后运行 |
| E3-F | E0 协议与 `k=1` few-shot | `e3-f-schema-v4` + 具有跨库门禁和 abstain 的 `train-mined-v2`；关闭 static patterns | 完整 Offline 系统的集成效果 | 历史 v1/v3 已运行 53/197 并完成诊断；新版阻断：Query Mining v2 当前 0 个 slot 通过门禁 |

### 7.1 Offline 机制范围与错误依据

| Offline 内容 | 对应 E0/E3-A 证据 | 为什么属于 Offline | 实验 |
|---|---|---|---|
| Query Mining / patterns | 聚合/排序 93、输出契约 56、过滤 67；E3-A 静态原型对聚合和输出没有明确改善 | 可从 train question + SQL 自动提炼结构签名、支持度、触发条件、边界与反例 | E3-A/E3-B 为历史原型；E3-D 为正式 Query Mining |
| Schema semantic metadata | Schema/Join 38 条、16 道稳定同类失败 | 表/字段描述、别名和字段语义可在答题前构建为数据库级 artifact | E3-C |
| PK/FK、Join path 与关系基数 | 多表遗漏、错误 Join 路径及重复行污染聚合 | 可从 Schema、约束和合规数据源离线生成，不需要当前题 gold | E3-C |
| 值类型、格式与受控样例 | 字符串格式、日期、单位、NULL 和过滤值错误 | 可作为数据库级 metadata 的一部分离线缓存；在线仍可用 `sample_values` 验证 | E3-C |
| Repair rules | 124 道稳定失败中 110 道保持同一语义大类，说明存在重复错误模式 | 只能从合规 train 错误轨迹提炼触发、动作、边界和反例 | 暂缓且不占当前实验编号 |

QueryPlan、context `search/slice/compose` 和 Leaf 不属于 Offline 内容：它们分别是在线题目级形式化、在线上下文访问方式和在线递归计算，必须留在 E4、E5、E6 独立测试。

### 7.2 E3-A：Train-Only Static Patterns（已完成）

| 指标 | 结果 |
|---|---|
| 父配置 | E0 |
| 唯一变量 | 增加固定 train-only pattern library，保留 `k=1` few-shot |
| 结果 | 73/197 = 37.06% |
| 相对 E0 均值 | +2.79 pp |
| Total tokens/题 | 14,751.72，相对 E0 +8.7% |
| 稳定变化 | 相对两次 E0 都恢复 6，稳定回退 1 |
| 决策 | 仅保留为静态 patterns 原型证据；不作为 E3-C 或后续实验的默认父配置 |

E3-A 对聚合、输出和 Schema 错误没有明确改善；过滤语义从 E0 的 33–34 条降至 24 条，但需要 F-Audit 复核。由于 artifact 是人工归纳的固定规则，不能把该结果解释为“Query Mining 已验证有效”。

详细报告：[E3-A summary](../analysis/analysisDetail/e3_a_summary.md)与[对比](../analysis/analysisDetail/e3_a_vs_e0.md)。

### 7.3 E3-B：Patterns 替代 Train Few-Shot

| 变量 | E3-A | E3-B |
|---|---|---|
| pattern artifact | 相同 | 相同 |
| requested `k` | 1 | 1 |
| effective `k` | 1 | 0，由 profile 强制 |
| Prompt/ReAct/FINAL | 相同 | 相同 |
| 模型/数据/参数 | 相同 | 相同 |

| 结果指标 | E3-A | E3-B | 变化 |
|---|---:|---:|---:|
| 正确数 | 73/197 | 72/197 | -1 |
| 准确率 | 37.06% | 36.55% | -0.51 pp |
| total tokens/题 | 14,751.72 | 15,421.28 | +4.54% |
| LLM 调用 | 539 | 552 | +13 |
| 配对 recovered / regressed | - | 4 / 5 | 净 -1 |

E3-B 没有降低成本，也没有保持 E3-A 的准确率，因此拒绝 patterns 以更低成本替代 few-shot 的假设。完整报告：[E3-B summary](../analysis/analysisDetail/e3_b_summary.md)；配对分析：[E3-B vs E3-A/E0](../analysis/analysisDetail/e3_b_vs_e3_a_e0.md)。

研究问题：patterns 能否替代逐题检索的 train few-shot，并降低 token？

```powershell
.\.venv\Scripts\python.exe scripts\run_bird_train_fewshot.py `
  --ids-file data\processed\bird_cleancore_ids.json `
  --id-groups both_wrong canary `
  --output results\e3_b_core197_run1.json `
  --agent-profile e3-rf `
  --model azure/seminar-gpt-5.4-mini `
  --k 1 `
  --max-iterations 8 `
  --reasoning-effort high
```

本次已按以下口径比较 E3-B vs E3-A，并参考 E0：

- 总准确率和 token；
- 197 题 recovered/regressed；
- E0 124 道稳定失败恢复；
- 四类语义错误；
- pattern artifact 内容/hash；
- effective `k=0` 是否进入 manifest。

原定判断规则与实际结论：

| 结果 | 后续 Offline 父配置 |
|---|---|
| 准确率不低于 E3-A 且 token 明显下降 | E3-B |
| 准确率回到 E0 范围但成本明显更低 | 权衡 E3-B 与 E0 |
| 准确率明显下降 | E3-A 或 E0 |
| 移除 few-shot 后 E3-A 增益消失 | patterns 不能替代 few-shot |

实际结果落入“准确率下降且成本未降低”：E3-B 被拒绝。这只否定 `train-static-v1` 对 few-shot 的替代能力，不否定后续带统计支持度和按题检索的真正 Query Mining。

### 7.4 锁定 E3-C 的控制变量

E3-C 回到 E0 的知识控制条件：保留 protocol Prompt、few-shot `k=1`、FINAL/ReAct、数据和参数，明确关闭 `train-static-v1` patterns；唯一知识机制变化是用预构建的 Offline Schema Context 替代 runtime full Schema Prompt。这样 E3-C 的结果不会与尚未验证的静态 patterns 混杂。manifest 必须记录 `query_pattern_mode=none`、artifact hash、`schema_context_mode=offline-retrieval` 和确定性检索策略。

### 7.5 E3-C：Offline Schema Context Replacement

目标：E0 Schema/Join 38 条、16 道稳定同类失败。

机制变量：将每题直接注入的 runtime full Schema 替换为来源合规、信息完整的数据库级 Offline Schema/metadata artifact，并在模型调用前通过固定词法匹配和 FK 邻接选择相关表/字段片段。模型不能主动调用搜索；程序化 `search/slice/compose` 仍属于 E5。

Artifact 包含：

- 表和字段描述；
- question/schema 常见别名与字段语义映射；
- PK/FK 图与候选 Join path；
- 一对多/多对多关系及可能造成重复行的连接；
- 值类型、格式和受控样例；
- 来源、支持度、版本和 SHA-256。

Prompt 只接收当前问题命中的表/字段、必要 FK 邻接和全库表目录，不再追加 `db.format_schema()` 的完整输出。E3-C 因而检验的是“Offline Schema Context 替代完整 Schema Prompt”的整体价值；它不能单独区分收益来自 metadata 内容还是片段选择，后续 E5 再检验模型主动上下文访问。

禁止 eval gold、根据 eval 错题手写 hints、当前题答案或其他 eval 题成功 SQL。

接受条件：

1. Schema/Join 相对第 7.4 节父配置净下降；
2. 稳定 Schema 失败 recovered > regressed；
3. 没有因 Join 重复导致聚合错误显著增加；
4. metadata token、来源、artifact hash、检索策略和选中片段完整记录；
5. Prompt tokens 不因重复 Schema 显著上升。

当前实现与运行入口：

- 旧版 full-metadata smoke：`results/e3_c_core197_run1.json`，只保留诊断，不作为正式 E3-C；
- 正式 artifact：`data/processed/e3_c_metadata_v2.json`；
- 构建命令：`.\.venv\Scripts\python.exe scripts\build_e3_c_metadata.py`；
- profile：`e3-c`，`query_pattern_mode=none`，保留 E0 的 `k=1` few-shot，启用 `e3-f-schema-v4`、`schema_context_mode=offline-retrieval` 与 capability gate；该 profile 是当前 Schema v4 单组件验证入口；
- 运行命令：

```powershell
.\.venv\Scripts\python.exe scripts\run_bird_train_fewshot.py `
  --agent-profile e3-c `
  --dataset data\processed\bird_dev_500.json `
  --ids-file data\processed\bird_cleancore_ids.json `
  --id-groups both_wrong canary `
  --database-dir data\raw\bird\minidev\MINIDEV\dev_databases `
  --output results\e3_c_core197_run2.json `
  --trace-dir trace\e3_c_core197_run2 `
  --model azure/seminar-gpt-5.4-mini `
  --k 1 `
  --max-iterations 8 `
  --reasoning-effort high
```

运行前先完成 smoke，确认 manifest 中记录 `offline_metadata.artifact_sha256`，再启动完整 197 题运行。

### 7.6 E3-D：True Offline Query Mining

父配置为通过检查的 E3-C；保留 Offline Schema Context 与 `k=1` few-shot，唯一增量是真正由 train question + train gold SQL 自动构建并按题检索的 Query Mining artifact。

构建流程：

1. 解析 train SQL AST，归一化数据库标识符、字面值和别名；
2. 提取 Join、过滤、聚合、HAVING、排序、Top-K、集合操作和输出形状等结构签名；
3. 按结构签名聚类并统计 support、数据库覆盖和问题表达触发词；
4. 为每类生成适用条件、操作模板、边界和反例，不保存可直接复制的当前 eval 答案；
5. 冻结 artifact、来源、构建参数和 SHA-256；
6. 运行时根据当前 question 与 E3-C 选中的 Schema fragment 检索 Top-K patterns，并记录 pattern ID、分数、检索原因和最终 SQL adherence。

E3-D 与 E3-A 的关键区别是：E3-A 是少量人工静态规则整体注入；E3-D 是可复现的数据挖掘、支持度过滤和题目级检索。接受条件为目标语义错误净下降、recovered > regressed、检索命中可解释，且 token/延迟增量可接受。

### 7.7 E3-E：Mined Patterns 的 Few-Shot 替代消融

仅当 E3-D 被接受后运行。父配置为 E3-D，唯一变量是将 effective few-shot 从 `k=1` 改为 `k=0`，Schema Context、mined pattern artifact、Top-K 检索、模型和预算全部不变。

- 准确率保持且成本下降：接受 E3-E，说明完整 Offline 知识可替代 few-shot；
- 准确率下降或成本不降：拒绝 E3-E，保留 E3-D；
- E3-D 本身未通过：不运行 E3-E，避免重复 E3-B 的无效消融。

### 7.8 E3-F：完整 Offline 系统 + Few-Shot

#### 7.8.1 历史 v1/v3 部分运行记录

`e3_f_core197_run1` 在修复前启动，实际配置为 `train-mined-v1 + e3-f-schema-v3 + k=1 few-shot`，不是下文定义的新版 E3-F。该进程在完成 53/197 题后中断，现已冻结为历史诊断：

| 字段 | 记录 |
|---|---|
| run_id | `20260714T075259Z-f3c7e719` |
| 状态 | `interrupted`，完成 53/197；只覆盖 4/11 个数据库 |
| 结果 | 21/53 = 39.62% |
| 同题 E0 两次均值 | 36.79%；历史 E3-F 为 +2.83 pp |
| 成本 | 16,426.79 total tokens/题，比同题 E0 均值高 40.34% |
| 失败归因 | 32 项：聚合 9、输出 9、过滤/语义 7、Schema 6、Runner/API 1 |
| Schema v3 诊断 | 53/53 都交付所在数据库的全部表，退化成近似完整 Schema 注入 |
| Query Mining v1 诊断 | 平均 2.85 张卡/题；只有 16/53 至少一张卡与 gold shape 完全一致 |
| 决策 | 不续跑、不作为完整结果、不用于评价 v2/v4；回到 E3-C/E3-D 拆分验证 |

对应文件：

- [部分运行 summary](../analysis/analysisDetail/e3_f_core197_run1_partial53_summary.md)
- [同题 E0/E3-A/E3-B 比较](../analysis/analysisDetail/e3_f_core197_run1_vs_e0_e3a_e3b_partial53.md)
- [全部 32 个失败的语义归因](../analysis/analysisDetail/e3_f_core197_run1_semantic_failures.csv)
- [逐题 retrieval audit](../analysis/analysisDetail/e3_f_core197_run1_retrieval_audit.csv)

该运行只说明 v1/v3 设计存在问题：小幅准确率变化伴随显著成本增加，Schema 检索没有形成压缩，Query Mining 强制 Top-K/fallback 的适用性不足。它不是新版完整 Offline 系统的验证结果。

#### 7.8.2 新版 v2/v4 预注册定义

E3-F 是用户指定的完整集成版本，不是单变量消融。它保留 E0 的 protocol Prompt、FINAL/ReAct、模型、预算和 train few-shot `k=1`，同时启用两项修复后的 Offline artifact：

- `e3-f-schema-v4`：修复 FK 目标键；区分 declared 与高置信 inferred Join；记录 key coverage、最大 child fan-out、列 NULL 比例和范围；只给 lexical seeds、桥接路径和每个 seed 的最佳邻居详细 metadata，其余字段保留 names-only 索引；输入、builder 和运行时检索代码均记录 hash。
- `train-mined-v2`：不再返回冲突 Top-K 完整结构卡，而是从 9,428 条 train SQL 挖掘独立 plan slots；构建确定性规则，按数据库做 5 折交叉验证，只交付跨库总精度至少 0.95、验证预测不少于 50 且各有效 fold 精度不低于 0.90 的 slot；无合格 slot 时必须 abstain，不允许最常见模式 fallback。

边界：`query_pattern_mode=train-mined-v2`，不加载 `train-static-v1`；`capability_gate=true`，只允许 `db.execute` 与 `db.sample_values`；不提供 runtime full Schema，不允许主动 `get_schema/get_tables`。

每题 trace 的 `attempts[].knowledge_selection` 必须保存：few-shot 的 train ID、相似度和排名；Query Mining 各 slot 的跨库验证指标、匹配规则、选中 constraint 或 abstention 原因；Schema 的全表候选分数、lexical seeds、最短路径、受限 FK neighbour、截断原因、逐字段排名，以及实际交付 Join edge 的 provenance、coverage 和 fan-out。manifest 同时冻结 artifact、builder、runtime retriever 和 embedding model config hash。

当前运行前审计：Schema v4 的所有表/字段标识符仍可用，详细表覆盖 193/197；声明 FK 与推断 Join 分开保存，新增的缺失关系使 168/168 道多表 gold 查询都可在 Join 图中连通。Query Mining v2 的 5 折整库留出门禁结果为 **0 个 slot 通过、0 条规则交付**。因此当前 profile 会安全 abstain，但不能被称为“Query Mining 已修复”，也不能据此启动完整 E3-F。

E3-F 只有在至少一个 Query Mining slot 通过预注册跨库门禁后，才能回答“完整 Offline 系统整体是否值得进入后续 Agent”。当前先验证 Schema v4 的独立价值；Query Mining 继续停留在 E3-D 设计/验证阶段。

历史文件 `results/e3_f_core197_run1.json` 已包含 v1/v3 的 53 题中断结果，必须冻结且不得续跑或覆盖。未来 v2/v4 通过门禁后的正式输出另用 `results/e3_f_schema_v4_query_v2_core197_run1.json`，避免两种机制版本混淆。

构建命令如下；正式运行命令仅在 Query Mining 门禁通过后启用：

```powershell
.\.venv\Scripts\python.exe scripts\build_e3_f_schema_context.py
.\.venv\Scripts\python.exe scripts\build_e3_f_query_mining.py
.\.venv\Scripts\python.exe scripts\audit_e3_f_preflight.py --target schema
.\.venv\Scripts\python.exe scripts\audit_e3_f_preflight.py --target full

.\.venv\Scripts\python.exe scripts\run_bird_train_fewshot.py `
  --agent-profile e3-f `
  --dataset data\processed\bird_dev_500.json `
  --ids-file data\processed\bird_cleancore_ids.json `
  --id-groups both_wrong canary `
  --database-dir data\raw\bird\minidev\MINIDEV\dev_databases `
  --output results\e3_f_schema_v4_query_v2_core197_run1.json `
  --trace-dir trace\e3_f_schema_v4_query_v2_core197_run1 `
  --model azure/seminar-gpt-5.4-mini `
  --k 1 `
  --max-iterations 8 `
  --reasoning-effort high
```

`--target schema` 必须通过后才允许用 `--agent-profile e3-c` 做 Schema v4 smoke；`--target full` 必须通过后才允许执行上面的 E3-F 命令。当前前者通过、后者因 Query Mining 0 个合格 slot 而失败，这是预期的安全阻断，不得绕过。

启动完整运行前先加 `--limit 3`，并把 smoke 输出/trace 改为新目录；确认 manifest 中 `query_pattern_library.version=train-mined-v2`、`offline_metadata.version=e3-f-schema-v4`、`effective_few_shot_k=1`、`capability_gate=true`，且 `enabled_slot_count > 0`。当前该值为 0，因此不得启动正式 E3-F。

运行完成后生成逐题 retrieval/adherence 审计：

```powershell
.\.venv\Scripts\python.exe scripts\analyze_e3_f_retrieval.py `
  --results results\e3_f_schema_v4_query_v2_core197_run1.json `
  --transcripts trace\e3_f_schema_v4_query_v2_core197_run1\transcripts.jsonl `
  --out-json docs\analysis\analysisDetail\e3_f_schema_v4_query_v2_retrieval_audit.json `
  --out-csv docs\analysis\analysisDetail\e3_f_schema_v4_query_v2_retrieval_audit.csv
```

### 7.9 锁定 E4-A 的具体 Offline 父配置

- E3-D 有效且 E3-E 保持准确率并降低成本：E4-A 使用 E3-E；
- E3-D 有效但 E3-E 被拒绝：E4-A 使用 E3-D；
- E3-F 集成版整体有效且先于独立消融完成：可作为工程候选进入后续阶段，但报告必须注明其收益尚未拆分归因；
- E3-D 无效但 E3-C 有效：E4-A 使用 E3-C；
- E3-C 无效：E4-A 回退 E0；E3-A 只保留为历史静态原型，不自动成为父配置；

## 8. 阶段 D：在线题目级形式化（E4）

| 子实验/任务 | 父配置 | 唯一变量 | 目标 | 状态 |
|---|---|---|---|---|
| E4-A | E3 阶段锁定的具体 Offline 配置 | 同一次 Root 响应生成 QueryPlan + Output Contract | 聚合、排序、输出契约和部分过滤结构 | 待运行 |
| F-Audit | E0/E3-A/E4-A 相关样本 | 人工复核过滤边界、逻辑范围和 gold 噪声 | 确定过滤类评价集 | 支持任务，不占编号 |

### 8.1 E4-A：Root QueryPlan + Output Contract

目标：E0 聚合/排序 93 条、输出契约 56 条，并结构化过滤条件。

唯一变量：Root 第一次生成 SQL 前，在同一次模型响应中输出 QueryPlan，不增加独立 Planner LLM call。

```json
{
  target_entity: ",
  grain: ",
  schema_links: [],
  joins: [],
  filters: [
    {
      field: ",
      operator: ",
      value_or_source: ",
      scope: row|aggregate
    }
  ],
  group_by: [],
  aggregates: [],
  having: [],
  order_by: [],
  limit: null,
  answer_type: rows|scalar|boolean,
  output_columns: []
}
```

控制变量：

- 父配置为第 7.9 节锁定的具体 Offline 配置；
- 无 metadata、context store、Leaf；
- LLM 调用预算与选定父配置相同；
- DB ReAct 和 FINAL 不变。

记录 plan parse、首次内容与修订、SQL-plan adherence、output shape 和 token 增量。

接受条件：

1. 聚合/排序或输出契约至少一个类别净下降；
2. 两类合计 recovered > regressed；
3. E0 稳定目标错误有可解释恢复；
4. 不靠独立 LLM call 获益；
5. Schema/Join 和 canary 无不可接受回退。

若两个目标类别都未下降，停止递归，先修 QueryPlan schema、生成时机或 adherence。

### 8.2 F-Audit：过滤错误人工审计（支持任务）

过滤标签置信度低。固定抽样：

- E0 两次都为过滤错误的稳定失败；
- E3-A 恢复的过滤题；
- E3-A 新增/回退过滤题；
- 日期、区间、AND/OR、NULL、百分比、字符串样例。

逐题记录 question、Hint、predicted/gold SQL、执行结果、运算符、边界、时间范围、逻辑括号、作用层级、gold 噪声可能性和 E4-A 是否表达正确条件。

输出：`docs/analysis/analysisDetail/filter_audit.md`。只有确认是 Agent 错误的样本用于判断 E4-A/E5-B。

## 9. 阶段 E：RLM 上下文环境（E5）

| 子实验 | 父配置 | 唯一变量 | 目的 | 状态 |
|---|---|---|---|---|
| E5-A | 已验证的结构化配置 | 相同信息外部化到 context store | 验证信息等价、可达和能力隔离 | Smoke |
| E5-B | E5-A 通过后的同一配置 | Root 使用 `search/slice/compose`，不允许 Leaf | 检验程序化上下文访问的准确率或效率价值 | 待运行 |

### 9.1 E5-A：同信息外部化 Smoke

目的：验证第 8.2 节明确选定的结构化配置以相同信息进入 context store 后没有丢失，不用于宣称准确率提升。

固定小集合覆盖 simple/moderate/challenging、四类错误和至少一个多阶段问题。

比较：

- section 数量、顺序、内容哈希；
- Root 可达字段；
- 直接 Prompt 与环境版本的信息集合；
- capability gate；
- trace 中 context read。

通过条件：信息集合和哈希一致、可访问、无隐藏能力。失败时修 context store，不跑 197 题。

### 9.2 E5-B：Context Store + Programmatic Search + QueryPlan

父配置：E5-A 验证通过的具体结构化配置。  
唯一机制增量：同一信息从直接 Prompt 改为 context store，允许 Root `search/slice/compose`；保留全局 QueryPlan，不允许 Leaf。

研究问题：信息集合不变时，程序化上下文探索是否更准确或更高效？

必须记录：

- 搜索词和返回 fragment ID；
- fragment hash；
- 读取 bytes/tokens；
- compose 结果；
- 未命中、重复读取和越权；
- QueryPlan 如何引用片段；
- Root 可见总 tokens。

接受条件：

1. 不明显低于对应的直接 Prompt 结构化配置；
2. 目标错误或 token 至少一项明确改善；
3. context miss/parse error 可控；
4. recovered > regressed；
5. capability 审计通过。

若明显退化，停止递归，先修 context API、检索接口或 artifact 切片。

## 10. 阶段 F：受控递归（E6）

| 子实验 | 父配置 | 唯一变量 | 目的 | 状态 |
|---|---|---|---|---|
| E6-A | E5-B | 对相同触发题增加一次 Root deliberation | 测量额外计算本身的收益 | 等预算对照 |
| E6-B | E5-B | 对相同触发题允许一次 depth-1 SubPlan Leaf | 检验分而治之是否优于 E6-A | 与 E6-A 配对 |

### 10.1 递归前提

只有 E5-B 通过后才实现 Leaf。全局 QueryPlan 由 Root 创建，Leaf 不得重建全局计划。

允许触发：

- 两阶段/多阶段聚合；
- 复杂 Join 与聚合耦合；
- 条件作用层级难以单步确定；
- QueryPlan 中存在可独立验证的 SubPlan。

不允许仅因“题目很长”或“Root 不确定”就无条件递归。

### 10.2 E6-A：额外 Root 思考

父配置：E5-B。对与 Leaf 组相同的触发题，允许一次额外 Root deliberation，不调用 Leaf。

必须与 E6-B 匹配触发题、额外调用次数、输入片段、输入/输出 token 上限、模型和 reasoning effort。该组测量额外计算本身的收益。

### 10.3 E6-B：Depth-1 SubPlan Leaf

约束：

- 最大深度 1，每题最多 1 次 Leaf；
- Leaf 只接收一个 SubPlan 和相关 fragment；
- Leaf 不访问完整 context；
- Leaf 不访问 DB、不提交 FINAL、不递归；
- Leaf 返回结构化 evidence、局部结论或 SQL fragment；
- Root 负责合并、执行和提交；
- Leaf 失败只触发 Root fallback，不自动重试。

```json
{
  subplan_id: ",
  evidence_refs: [],
  local_conclusion: ",
  candidate_sql_fragment: ",
  assumptions: [],
  confidence: low|medium|high
}
```

接受递归必须同时满足：

1. E6-B 优于 E6-A，而不只是优于 E5-B；
2. complex/multi-stage 稳定恢复超过回退；
3. 目标聚合/Join 错误净下降；
4. Leaf evidence 可追踪到最终 SQL；
5. token、调用和延迟增量可接受；
6. 无输出契约或全局 grain 冲突。

## 11. 暂缓扩展

| Artifact | 内容 | 当前对应 |
|---|---|---|
| Query patterns | 聚合、过滤、Top-K、输出、Join 通用结构 | E3-A/E3-B 为静态原型；E3-D 为独立消融；E3-F 候选 `train-mined-v2` 当前因跨库门禁失败而全量 abstain |
| Metadata | 字段语义、PK/FK、Join path、基数和值格式 | E3-C 为独立消融；E3-F 使用修复后的 `e3-f-schema-v4` |
| Repair rules | 错误触发、修复动作、适用边界和反例 | 暂缓，不占当前编号 |

Repair rules 只有在获得合规 train 轨迹后才构建。不得从 197 题 gold 或评分提炼在线规则；未来启用时先做独立内容消融，再决定是否放入 E5-B 的 context store。

Trace folding 只属于效率优化：可压缩已完成历史，但不得删除当前 QueryPlan、最近 observation、未解决约束和 evidence refs。主架构确定前不运行独立 folding 实验。

## 12. 实验依赖与执行顺序

```text
已完成：E0
          ├─ E1（拒绝）
          ├─ E2-B（能力基础设施；历史结果名 E4-R0）
          └─ E3-A（静态 patterns 历史原型，不作为默认父配置）

前置：E2-A
  ↓
已完成：E3-B（拒绝 patterns 替代 few-shot）
  ↓
旧 E3-C run2：62/197 中断诊断，不进入正式结果
  ↓
旧 E3-F v1/v3 run1：53/197 中断，分析已完成，不进入正式结果
  ↓
下一步 E3-C：Schema v4 + few-shot 的单组件 smoke 与归因
  ↓
E3-D：继续设计并验证真正 Query Mining；必须先通过跨库门禁
  ↓
E3-E：仅在 E3-D 有效后做 matched few-shot 消融
  ↓
E3-F：仅在 Schema 与 Query Mining 均通过门禁后做完整集成
  ↓
E4-A：在线 QueryPlan + Output Contract
  ↓
E5-A：context store 信息等价 smoke
  ↓
E5-B：程序化上下文访问
  ↓
E6-A：等预算 Root 对照 ↔ E6-B：受控 Leaf
```

执行清单：

1. 确认 E2-A 的结构化 observation 和 trace 完整。
2. E3-B 197 题、summary 和 vs E3-A/E0 对比已完成。
3. 旧 E3-C run2 在 62/197 中断，保留为 `patterns + metadata + few-shot` 诊断，不作为正式结果。
4. 旧 E3-F v1/v3 run1 在 53/197 中断；summary、同题比较、32/32 失败语义归因和 retrieval audit 已完成，结论为停止该历史配置。
5. 构建并审计 E3-F 的 `e3-f-schema-v4` 与 `train-mined-v2`；当前 Schema 通过结构门禁，Query Mining 未通过。
6. 先做 Schema v4 单组件 smoke/归因并继续设计 E3-D；只有 Query Mining 出现通过预注册跨库门禁的 slot 后才正式运行 E3-F。
7. 根据集成结果和独立归因锁定 Offline 配置，再实现、smoke、运行 E4-A。
8. 完成 F-Audit。
9. 完成 E5-A 信息等价 smoke。
10. 实现并运行 E5-B。
11. 固定触发集和预算，运行 E6-A。
12. 运行 E6-B。
13. 根据 paired error migration、成本和证据决定最终架构。

## 13. 停止与回退规则

| 阶段 | 未通过时 |
|---|---|
| E2-A | 不运行新机制，先修 trace/observation |
| E3-B | 已拒绝；结论仅限 static patterns 不能替代 few-shot |
| E3-C | 回退 E0，不把 metadata 带入 E3-D 或 E4-A |
| E3-D | 不运行 E3-E；若 E3-C 有效则保留 E3-C，否则回退 E0 |
| E3-E | 拒绝移除 few-shot，保留 E3-D |
| E3-F | 完整系统未通过时不得直接判断 Query Mining 或 Schema 单组件无效；回到 E3-C/E3-D 做拆分诊断 |
| E4-A | 修 QueryPlan schema/adherence；不进入 Leaf |
| E5-A | 修外部化信息一致性 |
| E5-B | 修检索、切片和 context API；停止递归 |
| E6-B ≤ E6-A | 拒绝递归增益，保留 E5-B 或 E6-A |

当前不执行：

- strict verified-final 或独立 FINAL 同步；
- 无 QueryPlan 裸递归、full-context Leaf、无限深度递归；
- 独立 Planner call 或完整 Router；
- Offline artifacts 全交叉矩阵；
- 使用 eval 错误构建 repair rules；
- 主架构未确定前优化 trace folding。

这些不是永久删除。只有出现与当前错误证据不同的新现象时，才建立新假设并加入。

## 14. 每次实验的统一分析模板

### 14.1 配置

| 字段 | 内容 |
|---|---|
| 实验名 | |
| 父配置 | |
| 唯一变量 | |
| 目标错误 | |
| 固定变量 | |
| 模型/参数 | |
| 数据与哈希 | |
| Prompt/artifact/config 哈希 | |
| capability manifest | |
| 结果与 trace 路径 | |

### 14.2 结果

| 指标 | 父配置 | 新配置 | 差异 |
|---|---:|---:|---:|
| 正确数/准确率 | | | |
| 聚合与排序 | | | |
| 输出契约 | | | |
| 过滤语义 | | | |
| Schema/Join | | | |
| 运行/解析 | | | |
| recovered/regressed | | | |
| E0 稳定失败恢复 | | | |
| E0 稳定正确回退 | | | |
| LLM/Root/Leaf/DB calls | | | |
| total tokens/题 | | | |
| 延迟/题 | | | |

### 14.3 错误迁移

- 目标类别恢复 ID：
- 目标类别回退 ID：
- 非目标类别新增错误：
- 运行噪声：
- 代表性轨迹：
- 自动分类置信度与人工复核：

### 14.3.1 Offline / Retrieval 逐题审计

每题从 `attempts[].knowledge_selection` 汇总：

| 字段 | 内容 |
|---|---|
| Query Mining 候选 | intent cues、候选 rank/score/support/shape、入选 ID、cutoff 与落选原因 |
| Schema 表候选 | lexical score、matched tokens、seed/path/FK-neighbour/fill 来源 |
| Schema 字段候选 | score、matched tokens、PK/FK/lexical 保留原因、截断原因 |
| Join 证据 | path expansions、交付 FK edges、关系基数、是否两端都在详细片段 |
| 截断 | 表/字段预算、被截断对象、完整紧凑索引是否仍提供标识符 |
| SQL adherence | 最终 SQL 使用了哪些选中表/字段/Join，以及是否遵循 mined card |

对每条失败必须另外回答：必要表/字段是否进入详细片段；若未进入，是否只存在于紧凑索引；正确候选排第几、为何被截断；错误来自 retrieval miss、错误 pattern adherence，还是检索正确但 SQL 推理失败。不得只写最终语义类别而不检查 retrieval 路径。

### 14.4 结论

- 机制假设是否被支持：
- 目标错误是否净下降：
- 稳定恢复是否超过稳定回退：
- 成本是否可接受：
- 是否存在数据/gold/运行混杂：
- 接受、修复后重测或拒绝：
- 下一步及唯一变量：

## 15. 当前下一步

当前下一步不是直接运行 E3-F。先以 `e3-f-schema-v4 + k=1 few-shot` 完成 Schema 单组件 smoke/归因，同时继续 E3-D 的 Query Mining 设计。`train-mined-v2` 已消除冲突 Top-K 和 fallback，但严格 5 折整库验证后没有 slot 通过，因此当前运行时全部 abstain。只有出现 `enabled_slot_count > 0` 且重新通过分层 smoke 后，才运行 `e3-f-schema-v4 + train-mined-v2 + k=1 few-shot` 的完整 E3-F；在此之前不得把 Schema-only 结果解释为完整 Offline 系统收益。
