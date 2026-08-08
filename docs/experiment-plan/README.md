# DB-RLM 统一实验计划

English version: [README_EN.md](README_EN.md)

版本：v1.0  
更新日期：2026-07-15
当前状态：E4-A core197 已完成并拒绝：71/197（36.04%），相对父配置 E3-C 的 77/197 下降 6 题；恢复 3、回退 9，total tokens/题增加 6.67%。当前最佳配置回退为 E3-C Schema v4。E5/E6 暂停，不把失败的 QueryPlan 带入 context store 或 Leaf。旧 E3-C run2 和旧 E3-F v1/v3 仅作历史诊断；Query Mining v2 没有 slot 通过严格跨库门禁，因此 E3-D/E3-F 仍暂停。**2026-08-07：修复了语义分类器的多处漏检并重新生成全部 7 个已完成实验的分类结果**（见 `../analysis/README.md` §4.1）；Schema/Join 从最小错误类别变为最大类别，E4-A 拒绝的决定不变，但归因方向反转——QueryPlan 让自己的目标类别（聚合/排序）变差，而非被 Schema 拖累，详见 §3.3、§3.5、§7.1、§8.1。

**F-Audit 已完成（两轮）**：对 20 题过滤/Schema 疑似噪声样本做实际执行验证，确认 40%（8题）是 gold 本身缺陷（含跨 4 个数据库反复出现的"缺 DISTINCT"系统性 bug 模式）、30%（6题）是真实 Agent 错误、10% 是被误归类的输出契约问题、其余为歧义或轻微倾向性判断。详见 `../analysis/analysisDetail/filter_audit.md`。基于 F-Audit 发现衍生了两个候选机制并已测试：**"FINAL 前未核实字面量警告"（N=44 分层验证，净回退，已拒绝）**；**"防御性过度 JOIN 提醒"（N=26，v1净+1、v2净归零，样本太小且发现题级噪声，已暂停迭代，不作定论）**。详见 `../analysis/analysisDetail/e3_c_literal_check_smoke2.md`、`e3_c_join_minimal_v2_smoke1.md`。另有 Schema/Join 深度诊断确认 93.5% 的 Schema/Join 失败不是检索问题、是近义表/字段混淆（`../analysis/analysisDetail/schema_join_diagnosis_2026-08-07.md`），对应的消歧机制讨论后决定暂缓至 E5/E6 重启时再设计，不在当前阶段实现。**下一步优先 Query Mining（E3-D）诊断/改进跨库验证门禁为何 0 个 slot 通过，E5/E6 仍需等待 train-only 验证过的 QueryPlan 才能重新评估准入。**
正式数据：`bird_cleancore_ids.json` 固定 197 题  
原则：实验顺序由每轮错误轨迹证据决定；一次只改变一个可归因机制。每次运行后先分析完整 trace、双标签语义归因和 recovered/regressed，再决定下一轮唯一变量，不预先假定最终架构。

## 0.1 为什么需要分类与消融实验

本计划的目标不是把多个模块一次性叠加到 Agent，而是逐步验证希望融合进 Agent 的三个主要机制：

1. **可编程的上下文与代码化推理**：Agent 能够把 Schema、metadata、query patterns、QueryPlan、observation 和证据引用组织成可检索、可组合的结构，而不是依赖一段不可追踪的长 Prompt。
2. **受控的执行环境**：工具、数据库访问、observation、终止原因和上下文读取都由 manifest/capability gate 约束，使结果可复现、能力边界可审计，并把运行故障与语义推理错误分开。
3. **可验证的自我改进与分而治之**：Root 先形成全局 QueryPlan，根据执行反馈修正约束；只有存在明确可独立验证的复杂 SubPlan 时，才使用受控 depth-1 Leaf，并与等预算的额外 Root 思考比较。

这三个机制不能直接作为一个整体实验，因为 E0 的失败来自不同层面。E0 的 259 条失败记录主要集中在聚合/排序（93）、过滤语义（67）、输出契约（56）和 Schema/Join（38），另有运行、解析和工具问题（5）；124 道稳定失败中有 110 道保持相同语义大类。同时，`UNVERIFIED_FINAL` 等控制流标签会遮住底层语义，且 E1 已显示 strict verified-final 增加成本却没有解决主要错误。因此必须先按错误形成机制分类，再用消融实验隔离每个改动的因果贡献。

由全部 259 条失败得到的直接机制映射为（2026-08-07 已用修复后分类器更新，见 `../analysis/README.md` §4.1；修复前分类器不比较 GROUP BY/ORDER BY 具体字段、不检查 JOIN key，系统性低估 Schema/Join）：

| E0 失败归因（修复后） | 直接机制 | 实验顺序 |
|---|---|---|
| 5 条运行、解析或工具问题 | 结构化 observation、重试、断点续跑和终止原因 | `E2-A`，只作为基础设施 |
| 75 条表选择/Join 路径错误（原与下一行合计为 38） | Offline Schema Context、字段语义、PK/FK、关系基数和相关片段选择 | `E3-C` |
| 22 条 JOIN key/条件错误（新增子类，此前未被检出） | 同上，另需核对 JOIN 条件对应的外键列 | `E3-C` |
| 36 条过滤范围/表达式错误（原为 67 条） | 先区分 Agent 错误与 gold 歧义；再结合值语义和题目级条件结构 | `F-Audit` → `E3-C` / `E4-A`，必要时 `E5-B` |
| 43 条聚合/分组错误（原为 82 条） | 显式统计对象、grain、分组键、聚合函数、`WHERE/HAVING` 与阶段依赖 | `E4-A`；只有剩余问题存在可分 SubPlan 才进入 `E6` |
| 22 条排序错误（原为 11 条） | 显式排序指标、方向、Top-K、tie 和 `LIMIT` 层级 | `E4-A` |
| 48 条输出列数错误（不变） | 固定 answer type、列数、顺序、来源和投影检查 | `E4-A` |
| 8 条 YES/NO 与逐行输出错误（不变） | 在生成 SQL 前固定 boolean/scalar/rows 回答形式 | `E4-A` |

以上细分类合计 259 条（5+75+22+36+43+22+48+8）。实验顺序依据运行后的 `semantic_error_class`，而不是被其遮盖的 `UNVERIFIED_FINAL` 控制流标签。Schema/Join（97 条）现在是全部四个语义大类中数量最大的一类，超过聚合/排序（65 条）；执行顺序碰巧仍然正确（E3-C 已先于 E4-A 运行），但 F-Audit 的抽样范围需要按新的 36 条过滤记录重新界定。

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

### 3.3 E0 双标签错误分布（2026-08-07 已用修复后分类器更新，见 `../analysis/README.md` §4.1）

两次共有 259 条失败记录。`UNVERIFIED_FINAL` 会覆盖底层语义，因此机制规划使用 `semantic_error_class`。修复前的分类器只检查 GROUP BY/ORDER BY 关键词是否出现、不比较具体字段，也完全不检查 JOIN key，系统性低估了 Schema/Join、高估了过滤类。

| 实际原因 | Run1 | Run2 | 合计 | 占失败记录 | 原合计（供对照） |
|---|---:|---:|---:|---:|---:|
| Schema/Join | 49 | 48 | 97 | 37.45% | 原 38（14.67%） |
| 聚合与排序 | 32 | 33 | 65 | 25.10% | 原 93（35.91%） |
| 输出契约 | 29 | 27 | 56 | 21.62% | 不变 |
| 过滤范围/表达式 | 17 | 19 | 36 | 13.90% | 原 67（25.87%） |
| 运行、解析或工具 | 1 | 4 | 5 | 1.93% | 不变 |

| 稳定失败类别（修复后） | 题数 | 原题数 |
|---|---:|---:|
| Schema/Join | 42 | 原 16 |
| 聚合与排序 | 29 | 原 41 |
| 输出契约 | 25 | 不变 |
| 过滤语义 | 14 | 原 28 |
| 类别变化或运行噪声 | 14 | 不变（13 类别变化 + 1 运行问题） |

124 道稳定失败中，**111 道**（原报告 110 道，非常接近但不完全相同，因个别题目在两次运行间的归因组合刚好跨过了新旧分类边界）保持相同语义大类；107 道保持相同子类这一数字尚未用新分类器重新核算。上表显示同类别的具体构成从"聚合为主"变为"Schema/Join 为主"。后续核心指标是恢复这些稳定结构性错误，不是只提高一次总分。

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

### 3.5 根据 E0 错误制定的改进顺序（2026-08-07 数字已按修复后分类器更新）

> 证据数字已更新，但下方执行顺序未变——因为实际执行顺序（E3-C 先于 E4-A）恰好与修正后的类别大小一致；唯一需要重新界定范围的是优先级 4 的 F-Audit（原按 67 条设计，现应按 36 条重新抽样）。

| 优先级 | E0 证据（修复后） | 改进机制 | 实验 |
|---:|---|---|---|
| 0 | 运行/解析/工具 5 条，observation 解析影响归因 | trace、manifest、结构化 observation | E2-A |
| 1 | Schema/Join 97（原 38） | 先独立验证 Offline metadata + PK/FK + Join path，关闭未验证的 static patterns | E3-C |
| 2 | 聚合/排序 65（原 93）、输出契约 56（不变）、过滤 36（原 67）；E3-A 静态规则覆盖不足 | 从 train question + SQL 做真正 Query Mining，再条件性消融 few-shot | E3-D、E3-E |
| 3 | 聚合/排序 65（原 93）；输出契约 56（不变） | Root QueryPlan + output contract | E4-A |
| 4 | 过滤 36（原 67），但置信度低 | 人工审计；QueryPlan 条件结构；必要时值检索 | F-Audit、E4-A、E5-B |
| 5 | 直接 Prompt 可能未有效使用上下文 | 同信息外部化和程序化检索 | E5-A、E5-B |
| 6 | 多阶段复杂题仍失败 | QueryPlan 驱动 depth-1 Leaf | E6-A、E6-B |

每一阶段完成后必须重新检查错误迁移；不得因为递归是最终目标就跳过 E3-C、E4-A 和 E5-B，否则无法归因。若新运行显示优先级改变，应在下一轮计划中记录证据并调整顺序。修复后的证据显示 Schema/Join（97）比聚合/排序（65）更大，E3-C 排在 E4-A 之前这个顺序恰好是对的，但 E4-A 面对的聚合/排序体量比原先认为的小得多，这也与 E4-A 最终被拒绝一致。

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
| E3-C | E0 | 关闭 static patterns；保留 few-shot；用 Offline Schema Context 替代 runtime full Schema Prompt | Schema linking、字段来源、Join 与 Prompt 冗余 | 已完成并接受：77/197；作为 E4-A 父配置 |
| E3-D | E3-C | 从 train question + gold SQL 自动挖掘、归一化、聚类并按题检索 Top-K patterns | 聚合、排序、过滤、输出和 Join 结构错误 | 待设计与实现 |
| E3-E | E3-D | 仅移除 train few-shot，保留 Schema Context 与 mined patterns | 判断完整 Offline 知识能否替代 few-shot | 条件实验：仅 E3-D 通过后运行 |
| E3-F | E0 协议与 `k=1` few-shot | `e3-f-schema-v4` + 具有跨库门禁和 abstain 的 `train-mined-v2`；关闭 static patterns | 完整 Offline 系统的集成效果 | 历史 v1/v3 已运行 53/197 并完成诊断；新版阻断：Query Mining v2 当前 0 个 slot 通过门禁 |

### 7.1 Offline 机制范围与错误依据

| Offline 内容 | 对应 E0/E3-A 证据 | 为什么属于 Offline | 实验 |
|---|---|---|---|
| Query Mining / patterns | 聚合/排序 65（原 93）、输出契约 56、过滤 36（原 67）；E3-A 静态原型对聚合和输出没有明确改善 | 可从 train question + SQL 自动提炼结构签名、支持度、触发条件、边界与反例 | E3-A/E3-B 为历史原型；E3-D 为正式 Query Mining |
| Schema semantic metadata | Schema/Join **97 条（原 38 条，2026-08-07 修复后为最大类别）**、42 道稳定同类失败（原 16 道） | 表/字段描述、别名和字段语义可在答题前构建为数据库级 artifact | E3-C |
| PK/FK、Join path 与关系基数 | 多表遗漏、错误 Join 路径及重复行污染聚合；其中 22 条是 JOIN key/条件错误（新增子类，选对表但连错外键） | 可从 Schema、约束和合规数据源离线生成，不需要当前题 gold | E3-C |
| 值类型、格式与受控样例 | 字符串格式、日期、单位、NULL 和过滤值错误 | 可作为数据库级 metadata 的一部分离线缓存；在线仍可用 `sample_values` 验证 | E3-C |
| Repair rules | 124 道稳定失败中 111 道保持同一语义大类（原报告 110 道），说明存在重复错误模式；同一大类现以 Schema/Join 为主，不是聚合 | 只能从合规 train 错误轨迹提炼触发、动作、边界和反例 | 暂缓且不占当前实验编号 |

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
| E4-A | E3 阶段锁定的具体 Offline 配置 | 同一次 Root 响应生成 QueryPlan + Output Contract | 聚合、排序、输出契约和部分过滤结构 | 已完成并拒绝：71/197；较 E3-C -6；恢复 3、回退 9 |
| F-Audit | E0/E3-A/E4-A 相关样本 | 人工复核过滤边界、逻辑范围和 gold 噪声 | 确定过滤类评价集 | 支持任务，不占编号 |

### 8.1 E4-A：Root QueryPlan + Output Contract

目标：E0 聚合/排序 93 条、输出契约 56 条，并结构化过滤条件。

唯一变量：Root 第一次生成 SQL 前，在同一次模型响应中输出 QueryPlan，不增加独立 Planner LLM call。

```json
{
  target_entity: ",
  grain: ",
  schema_links: [],
  required_tables: [],
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
  aggregation_scope: none|per_entity|global,
  aggregation_justification: null,
  having: [],
  order_by: [],
  limit: null,
  answer_type: rows|scalar|boolean,
  answer_scope: per_entity_rows|single_entity_row|global_scalar|boolean,
  output_columns: [
    {
      position: 1,
      semantic_item: "",
      source_columns: ["Table.column"],
      sql_expression: "",
      source_justification: "",
      aggregation: "none"
    }
  ],
  candidate_purpose: explore|answer,
  expected_result_shape: {
    answer_type: rows|scalar|boolean,
    column_count: 0,
    row_grain: "
  },
  unresolved_assumptions: [],
  revision: null
}
```

控制变量：

- 父配置为第 7.9 节锁定的具体 Offline 配置；
- 继承 E3-C 的 Offline Schema metadata，但不新增 Query Mining、context store 或 Leaf；
- LLM 调用预算与选定父配置相同；
- DB ReAct 和 FINAL 不变。

记录 plan parse、首次内容与修订、SQL-plan adherence、output shape 和 token 增量。若 observation 后改写 SQL，`revision` 只记录 `observation_ref`、`changed_constraints`、`updated_fields` 和 `reason` 的状态 delta，不重建一份与历史脱节的计划。第一轮只测量 adherence，不增加独立 checker LLM call。

接受条件：

1. 聚合/排序或输出契约至少一个类别净下降；
2. 两类合计 recovered > regressed；
3. E0 稳定目标错误有可解释恢复；
4. 不靠独立 LLM call 获益；
5. Schema/Join 和 canary 无不可接受回退。

若两个目标类别都未下降，停止递归，先修 QueryPlan schema、生成时机或 adherence。

#### E4-A 运行前 smoke

固定 4 题的 schema-v3 run3 已完成：3 题协议直接通过，`bird_1031` 在安全拦截两次无效响应后才执行。为避免重复消耗其余三题，只对该题进行协议重试：

```powershell
.\.venv\Scripts\python.exe scripts\run_bird_train_fewshot.py `
  --agent-profile e4-a `
  --ids-file data\processed\e4_a_protocol_retry_ids.json `
  --output results\e4_a_protocol_retry1_run2.json `
  --trace-dir trace\e4_a_protocol_retry1_run2 `
  --k 1 `
  --max-iterations 8 `
  --temperature 0 `
  --reasoning-effort high
```

runner 会自动生成 classification、retrieval audit 和 trajectory audit。随后执行 fail-closed 门禁：

```powershell
.\.venv\Scripts\python.exe scripts\audit_e4_a_smoke.py `
  --trace-dir trace\e4_a_protocol_retry1_run2 `
  --expected-count 1
```

retry run2 已满足最终门禁：审计 `passed=true`、`limit=null`、2 次 adherence 全部通过，详见 [retry run2 诊断](../analysis/analysisDetail/e4_a_protocol_retry1_run2_diagnostic.md)。它与 run3 其余三题的通过记录共同完成 schema-v3 协议 smoke。配置自此冻结，不再根据 smoke gold 调整；正式有效性由 core197 的目标错误净变化、recovered/regressed 和成本判断。

#### E4-A core197 正式命令

```powershell
.\.venv\Scripts\python.exe scripts\run_bird_train_fewshot.py `
  --agent-profile e4-a `
  --ids-file data\processed\bird_cleancore_ids.json `
  --id-groups both_wrong canary `
  --output results\e4_a_core197_run1.json `
  --trace-dir trace\e4_a_core197_run1 `
  --k 1 `
  --max-iterations 8 `
  --temperature 0 `
  --reasoning-effort high
```

正式结果：`71/197 = 36.04%`，低于 E3-C 的 `77/197 = 39.09%`；并新增 4 个 missing FINAL。预注册条件未通过，因此拒绝 E4-A。

> **2026-08-07 分类更正**：此段原写"聚合/排序减少4，但输出+1、过滤+5、Schema+1"，该数字来自修复前的语义分类器（未比较 GROUP BY/ORDER BY 具体字段和 JOIN key，见 `../analysis/README.md` §4.1）。用修复后的分类器重新统计，**方向相反**：聚合/排序实际 **增加 4**（E4-A 自己的设计目标变差），Schema/Join 实际 **减少 4**（改善），输出契约 +1 不变，过滤类 +2（原报告 +5 偏大）。目标类 recovered/regressed 从原报告"3:3 持平"变为 **3:5**。拒绝 E4-A 的决定不变，但正确的归因是：QueryPlan 直接让自己最想解决的聚合/排序问题变差了，不是"目标改善、被 Schema 等旁支拖累"。

详见 [summary](../analysis/analysisDetail/e4_a_core197_run1_summary.md)、[E3-C/E0 配对比较](../analysis/analysisDetail/e4_a_core197_run1_vs_e3c_e0.md)和[轨迹审计](../analysis/analysisDetail/e4_a_core197_run1_trajectory_audit.md)。

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
| E5-A | 已验证的结构化配置 | 相同信息外部化到 context store | 验证信息等价、可达和能力隔离 | 暂停：E4-A 未通过 |
| E5-B | E5-A 通过后的同一配置 | Root 使用 `search/slice/compose`，不允许 Leaf | 检验程序化上下文访问的准确率或效率价值 | 暂停 |

### 9.1 E5-A：同信息外部化 Smoke（暂停）

目的：验证第 8.2 节明确选定的结构化配置以相同信息进入 context store 后没有丢失，不用于宣称准确率提升。

固定小集合覆盖 simple/moderate/challenging、四类错误和至少一个多阶段问题。

比较：

- section 数量、顺序、内容哈希；
- Root 可达字段；
- 直接 Prompt 与环境版本的信息集合；
- capability gate；
- trace 中 context read。

通过条件：信息集合和哈希一致、可访问、无隐藏能力。失败时修 context store，不跑 197 题。

### 9.2 E5-B：Context Store + Programmatic Search + QueryPlan（暂停）

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
正式 E3-C Schema v4 run3：77/197，已接受为 Offline 父配置
  ↓
旧 E3-F v1/v3 run1：53/197 中断，分析已完成，不进入正式结果
  ↓
E2-A observation 完整性 smoke（修复多 block 静默丢弃与结构化反馈）
  ↓
已完成 E4-A：71/197，拒绝并回退 E3-C
  ↓
已完成 F-Audit（两轮）：gold 缺陷 40%、真实 Agent 错误 30%、输出契约误归类 10%、歧义/倾向性 20%
  ↓
已测试并拒绝：FINAL 前未核实字面量警告（N=44，净回退）
已测试并暂停：防御性过度 JOIN 提醒（N=26，v1净+1/v2净归零，样本太小不作定论）
Schema 消歧机制讨论后决定暂缓，留给 E5/E6 重启时设计
  ↓
下一步：Query Mining（E3-D）诊断为何 5 折跨库门禁 0 个 slot 通过
  ↓
E5/E6 暂停；QueryPlan 只有通过 train-only 语义评测后才能重新进入
```

执行清单：

1. 确认 E2-A 的结构化 observation 和 trace 完整。
2. E3-B 197 题、summary 和 vs E3-A/E0 对比已完成。
3. 旧 E3-C run2 保留为无效 API/历史诊断；正式 E3-C Schema v4 run3 已完成 197 题、语义归因、retrieval audit 和 trajectory audit，并被接受为 E4-A 父配置。
4. 旧 E3-F v1/v3 run1 在 53/197 中断；summary、同题比较、32/32 失败语义归因和 retrieval audit 已完成，结论为停止该历史配置。
5. 构建并审计 E3-F 的 `e3-f-schema-v4` 与 `train-mined-v2`；当前 Schema 通过结构门禁，Query Mining 未通过。
6. 修复历史多 Python block 静默丢弃、重复执行和结构化 observation 可见性，并完成基础设施 smoke；不把该修复申报为准确率机制。
7. E4-A 已完成并拒绝；正式父配置回退 E3-C。
8. F-Audit 已完成（两轮，`../analysis/analysisDetail/filter_audit.md`）；衍生的两个候选机制已测试完毕（一拒绝一暂停，见上）。
9. 暂停 E5-A/E5-B/E6-A/E6-B；只有新的 train-only QueryPlan 语义门禁通过后再修订计划。**优先级上 Query Mining（E3-D）诊断先于 E5/E6**——E3-D 是独立轨道，卡在验证门禁本身；E5/E6 的准入前提（train-only 验证过的 QueryPlan）目前完全不存在，跳过 E3-D 直接做递归会重复 E4-A"在 197 题 gold 上迭代"的错误。
10. 根据 paired error migration、成本和证据决定最终架构。

## 13. 停止与回退规则

| 阶段 | 未通过时 |
|---|---|
| E2-A | 不运行新机制，先修 trace/observation |
| E3-B | 已拒绝；结论仅限 static patterns 不能替代 few-shot |
| E3-C | 回退 E0，不把 metadata 带入 E3-D 或 E4-A |
| E3-D | 不运行 E3-E；若 E3-C 有效则保留 E3-C，否则回退 E0 |
| E3-E | 拒绝移除 few-shot，保留 E3-D |
| E3-F | 完整系统未通过时不得直接判断 Query Mining 或 Schema 单组件无效；回到 E3-C/E3-D 做拆分诊断 |
| E4-A | 当前 schema-v3 已正式拒绝；回退 E3-C，完成 F-Audit；不得进入 Leaf或按 eval gold 继续调 Prompt |
| E5-A | 修外部化信息一致性 |
| E5-B | 修检索、切片和 context API；停止递归 |
| E6-B ≤ E6-A | 拒绝递归增益，保留 E5-B 或 E6-A |
| **E6 整体（2026-08-08 新增前提）** | **在"模型能自适应判断何时需要额外验证"这一前提被证据支持之前，E6 不运行。** 当前证据（`../analysis/analysisDetail/react_loop_efficacy_2026-08-08.md`）显示该前提不成立：失败题的循环恢复率精确为 0，模型探索强度与是否将要出错无关。触发依据不成立时，Leaf 机制无法被公平评估，跑了也无法归因。 |

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

> 本节此前停留在"F-Audit 尚未开始"的状态，与实际进度不同步。现更新为 2026-08-07/08 的最新状态。

E3-C Schema v4 仍是当前最佳父配置（77/197=39.09%）；E4-A 已拒绝并回退（详见 §8.1，归因已修正——QueryPlan 让自己的目标类别聚合/排序变差，不是被 Schema 拖累）。

**F-Audit 已完成（两轮）**：`docs/analysis/analysisDetail/filter_audit.md`。20 题实际执行验证结果：40%（8题）确认是 gold 本身缺陷（含跨 4 个数据库反复出现的"缺 DISTINCT"系统性 bug 模式）、30%（6题）是真实 Agent 错误、10% 是被误归类的输出契约问题、其余 20% 是歧义或轻微倾向性判断。8 题 gold 缺陷已写回 `classification_sheet.csv` 标记为 `DATASET_OR_GOLD_CONFLICT`。

**基于 F-Audit 衍生的两个候选机制已测试完毕**：

1. "FINAL 前未核实字面量警告"（`e3-c-literal-check` profile）：N=8 混合信号 → N=44 分层验证（覆盖全部11数据库）净回退（0恢复/4回退），且回退原因与机制无关，指向"扩展上下文本身有副作用"。**已拒绝**，详见 `../analysis/analysisDetail/e3_c_literal_check_smoke2.md`。
2. "防御性过度 JOIN 提醒"（`e3-c-join-minimal`/`-v2` profile）：N=26 v1 净+1（2恢复/1回退，回退可解释为提示语泛化）→ v2 收紧措辞后目标问题修复但新增2个无关回退，净效果归零，且发现同一道题（`bird_1480`）在两个完全不同机制下都以相同方式回退，指向样本内"脆弱题"噪声。**暂停迭代，不作定论**，详见 `../analysis/analysisDetail/e3_c_join_minimal_v2_smoke1.md`。两个新 profile 的代码保留在库中（默认关闭，不影响任何现有 profile），不删除。

Schema 消歧机制（近义表/字段，如 `formula_1` 的 results/driverStandings）讨论后决定暂缓，留给 E5/E6 重启时按"运行时动态检测"的方向重新设计，本阶段不实现静态硬编码版本（避免用 eval 集失败案例反推消歧内容）。

### 15.1 2026-08-08 更新：ReAct 循环有效性测量改变了优先级

对全部 197 题（不只失败题）重测执行状态转移后，得到三条结构性结果（详见 `../analysis/analysisDetail/react_loop_efficacy_2026-08-08.md` 与综合论证 `../analysis/SYNTHESIS.md`）：

1. 循环有效但极端二值：正确题恢复率 4–14%，**错误题恢复率三次运行精确为 0**，且 99% 以上的失败题全程从未执行出匹配 gold 的结果——循环没有可救的对象。
2. 模型不会自适应增加探索：正确题与错误题的执行次数（1.2–1.6/题）与多次执行占比（27–38%）几乎相同，8 轮预算实际只用 1–2 轮。
3. 约 2/3 的正确答案，其提交的 FINAL SQL 从未被执行验证过。

**这为 E1、E4-A、字面量核实、JOIN 精简四个机制的失败提供了统一解释**：它们都在强化 SC（自我检查）环节，而该环节对失败题的边际价值≈0。由此产生两条硬约束：

- **不再设计强化自我检查/验证的机制。** 四次失败已有共同原因，第五次没有理由不同。
- **E6（受控递归）有原则地暂缓**，理由比原来的"E4-A 未通过"更根本：分而治之要求模型可靠判断"哪个 SubPlan 需要独立验证"，而数据显示模型连单步自检都不产生因果影响、也不会在即将出错时增加探索。**触发依据不成立，因此 E6 无法被公平评估**——这不是排期问题，是前提问题。若未来该前提改变（例如换用可训练模型，或出现证据表明模型能自适应判断不确定性），应重新评估。

### 15.2 E5-A 已完成并通过（2026-08-08）

E5-A 解除暂停并运行完毕（此前暂停理由"不把失败的 QueryPlan 带入 context store"经复核不适用于 E5-A 本身——它只做信息外部化与等价性验证，不需要 QueryPlan，父配置直接用已验证的 E3-C）。

- **通过条件一（信息等价）**：全部 197 题离线逐字节比对，197/197 一致、0 失败，无 LLM 成本。
- **通过条件二（可达性与能力边界）**：11 题覆盖全部数据库，模型主动读取 59 次（5.36 次/题，0 题未读），事件日志仅含 `context.list`/`context.read`/`db.execute`，无越权。

详见 `../analysis/analysisDetail/e5_a_context_store_smoke1.md`。

### 15.3 E5-B 不建议作为准确率实验运行

E5-A 的成本测量改变了 E5-B 的前景。同 11 题配对：外部化带来 **+108.9% total token、+312.3% 延迟、+100% LLM 调用，准确率持平（5/11）**；prompt token 虽降 17.5%，但推理 token 增长 283%（多轮读取，每轮携带完整隐藏推理，且观察到大量重复读取）。

根本原因是结构性的：**本任务完整知识载荷仅 726–2,572 tokens，prompt 约 5,171 tokens，上下文利用率约 4%**。context store 针对"上下文装不下、须外部化按需取用"的约束，该约束在此不存在，因此外部化没有可兑现的收益。这不是实现问题——把 store 做得更快也无法创造本来不存在的收益。

对照计划 §9.2 给 E5-B 的两条接受轴：

- **目标错误**：`schema_join_diagnosis_2026-08-07.md` 与 `e3_c_schema_v4_summary.md` 已确认 E3-C 残留失败中 **89–93% 所需的 gold 表/字段本已完整出现在上下文中**——瓶颈是"拿到正确信息仍推理错误"，而 E5-B 增强的是**查找**能力。先验差。
- **token**：E5-B 在 E5-A 之上增加 search/slice/compose，方向是**更多**调用轮次；要回到 E3-C 水平需削减一半以上成本。先验差。

因此 E5-B 暂缓，理由与 E6 同类（前提/约束不成立，而非排期靠后）。若日后在上下文确实紧张的场景（更大 schema、更长证据、需保留长历史）重启，E5-A 的机制与验证脚本可直接复用。

### 15.4 当前下一步

三个 RLM 能力至此各有有原则的结论（详见 `../analysis/SYNTHESIS.md` §2.4）：能力一的约束在本任务不存在；能力二按定义不提分；能力三前提不成立。

**E3-D Query Mining 亦已诊断为不可行**（2026-08-08）：28 个 slot 全部未通过跨库门禁，且决定性检验显示最佳 slot（`output_count`，覆盖 40.9%）精度 0.906 仅比模型自身判断的 0.891 高 1.5 pp，期望收益约 +0.6pp（197 题约 1 道）低于实测 Prompt 扰动噪声（±4 道）。根因是 n-gram → SQL 结构预测与强模型已有能力重叠。门禁设计本身正确。E3-F 随之继续暂停。详见 `../analysis/analysisDetail/e3_d_query_mining_diagnosis_2026-08-08.md`。

**至此全部计划中的机制方向均已有结论。**

### 项目三条主要结论

原定的 RLM 三能力验证未取得正面结果，但项目产出了三条相互独立、各自成立的结论（完整论证见 `../analysis/SYNTHESIS.md` §0）：

| # | 结论 | 核心数字 |
|---|---|---|
| 一 | **一个有效机制**：E3-C Offline Schema Context——全量 Schema 换成按题确定性检索的片段 | `77/197 = 39.09%`，**+4.82 pp**；六个受测机制中唯一被接受 |
| 二 | **一个结构性负面结论**：冻结商用模型上验证类干预有天花板，失败在验证能介入前已决定 | 4 个机制全败；失败题循环恢复率**精确为 0**（三次运行）；>99% 失败题从未执行出正确结果 |
| 三 | **一个基准质量发现**：BIRD 困难子集可测 headroom 被显著高估 | F-Audit 实测 **40%** 的失败是 gold 缺陷；另有 **+2.03 pp** 只需对齐标注约定即可获得 |

结论二与结论三都依赖本项目建立的 error tracking 基础设施（结构化 trace、双标签分类、逐题执行验证）才能得出，属于方法论层面的产出。

### 剩余工作

1. **论文化**：材料集中于 `../analysis/SYNTHESIS.md`，三条结论各有独立证据链与边界条件。
2. **可选的补充实验**：把 E3-C 跑一次完整 500 题（当前所有 clean 数字都在 197 题对抗性子集上，无法与已发表结果比较）；标注约定机制的可开关实现与实测。
2. **可选的重启条件**（均需外部条件改变，非当前可推进项）：能力一需上下文确实紧张的场景；能力三需可训练模型或模型具备可靠的不确定性自评；E3-D 需把挖掘目标从"问题→结构"改为"数据集书写约定"。

**Query Mining（E3-D）** 属于 Offline 内容侧，独立于上述论点，可并行推进：诊断 `train-mined-v2` 为何 5 折跨库门禁 0 个 slot 通过（`enabled_slot_count=0`），是验证标准过严还是挖掘方法需返工。只有出现 `enabled_slot_count > 0` 且重新通过分层 smoke 后，才运行完整 E3-F；在此之前不得把 Schema-only 结果解释为完整 Offline 系统收益。
