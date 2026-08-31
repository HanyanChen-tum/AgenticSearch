# 30 页实验报告大纲

## 建议标题

**递归语言模型机制对 Text-to-SQL 的影响**

可选副标题：

**基于 BIRD 的数据库探索、程序化上下文、显式规划与递归委派对照研究**

## 正确的研究主线

本报告研究：将 Recursive Language Model（RLM）的机制引入 Text-to-SQL 系统后，会对准确率、推理过程、上下文使用、递归行为、成本和可解释性产生什么影响。

报告应比较：

1. 直接 Text-to-SQL；
2. 一次性 Schema 检索；
3. 非递归数据库 Agent；
4. 加入不同 RLM 组件的非递归 Agent；
5. 真正执行 Root–Leaf 委派的 Recursive DB-RLM。

核心研究问题：

1. 数据库驱动的多步推理相对直接生成能提高多少 Text-to-SQL 准确率？
2. Offline Context、受控执行、QueryPlan、程序化上下文和递归等 RLM 组件分别有什么独立作用？
3. 在模型、工具和额外调用预算相同的情况下，递归 Leaf 是否优于 Root 自己继续推理？
4. RLM 机制如何影响 token、延迟、工具使用和轨迹可解释性？
5. 哪些任务条件使递归有价值，哪些条件使递归无法产生额外收益？

建议中心结论：

> RLM 风格机制对 Text-to-SQL 的影响并不一致。数据库执行反馈和按题检索的 Offline Schema Context 明显提高了准确率，受控执行环境也使推理过程更可审计；但程序化上下文外部化、显式 QueryPlan、答案后的验证和真正的 Root–Leaf 递归，在当前 BIRD 设置下都没有产生可靠的额外收益。递归实验表明，当 Root 与 Leaf 拥有相同工具和信息、上下文规模并未形成瓶颈、剩余失败中又缺少干净且可分解的推理问题时，委派本身不会自动创造价值。

## 页数分配

以下约 30 页正文，不含参考文献和详细附录。

| 章节 | 页数 |
|---|---:|
| 摘要与结果概览 | 1.0 |
| 1. 引言 | 2.0 |
| 2. 背景与相关工作 | 2.5 |
| 3. Recursive DB-RLM 方法设计 | 4.0 |
| 4. 实验设置 | 3.0 |
| 5. 从直接 Text-to-SQL 到数据库 Agent | 3.0 |
| 6. 各 RLM 组件的独立影响 | 4.0 |
| 7. 真正递归委派的影响 | 4.0 |
| 8. 错误、轨迹与 Benchmark 分析 | 2.5 |
| 9. 成本、可扩展性与可解释性 | 1.5 |
| 10. 讨论与局限 | 1.5 |
| 11. 结论 | 1.0 |
| **合计** | **30.0** |

---

# 摘要与结果概览 — 1 页

用 250–350 词概括：

- 研究目标：将 RLM 从非结构化搜索扩展到结构化数据库推理。
- 实验设置：BIRD mini-dev 500 题、11 个数据库，官方执行准确率，同一冻结的 Azure `gpt-5.4-mini`。
- 对照方法：直接生成、Schema 过滤、非递归 ReAct、RLM 组件消融和实际 Root–Leaf 递归。
- 正面结果：
  - 直接 Baseline 55.20% → 数据库驱动 Agent 64.20%；
  - 当前可复现系统达到 67.40%；
  - Offline Schema Context 在全 500 题上 +3.20 pp，在 197 题诊断集上 +4.82 pp。
- 递归结果：五轮 Root–Leaf 迭代中，即使 Leaf 查库率达到 94%，委派题净收益仍为 0。
- 成本结果：上下文外部化在配对 smoke 中约增加 109% token 和 312% 延迟，却未提高准确率。
- 解释：能提供新数据库信息或可观察执行的 RLM 组件有价值；没有信息不对称、上下文压力或独立可验证子问题时，递归不产生额外优势。
- 边界：结论只针对当前模型、BIRD、上下文规模和工具对称设置，不外推为“RLM 普遍无效”。

---

# 1. 引言 — 2 页

## 1.1 Text-to-SQL 的难点

- 大型 Schema、自然语言歧义、Join 路径、值格式、聚合粒度和输出约定。
- 一次性 Schema→SQL 的局限。
- 为什么数据库交互、问题分解和递归探索值得研究。

## 1.2 为什么把 RLM 引入数据库推理？

- RLM 不要求模型一次读完固定 Prompt，而是允许其通过代码访问环境、搜索内容、切分问题并递归调用模型。
- 数据库天然提供结构化且可执行的外部环境。
- 预期收益：
  - 通过真实数据探索提高准确率；
  - 在大型 Schema 上只读取相关片段；
  - 降低长上下文成本；
  - 生成可追踪的中间证据；
  - 把复杂、多阶段查询拆成子问题。

## 1.3 研究问题

- **RQ1：** 非递归数据库 Agent 相对直接 Text-to-SQL 有多大提升？
- **RQ2：** 各 RLM 组件的独立贡献是什么？
- **RQ3：** Root–Leaf 递归是否优于等预算的非递归 Root？
- **RQ4：** RLM 对成本、工具行为和可解释性有什么影响？
- **RQ5：** Benchmark 与实验噪声如何限制这些结论？

## 1.4 主要贡献

1. 将 RLM 的环境交互、程序化上下文和递归委派映射到数据库 Text-to-SQL。
2. 将 RLM 拆成多个可单独验证的机制，而不是将其作为不可分割的整体。
3. 在相同模型和工具下直接比较 Root 继续推理与 Root–Leaf 委派。
4. 通过轨迹、工具调用和委派证据解释各组件的正负结果。
5. 审计剩余失败，确定递归实验实际能够测量的干净推理空间。

**图 1：** 从 Direct Text-to-SQL、非递归 DB Agent、RLM 组件到 Recursive DB-RLM 的研究路线。

---

# 2. 背景与相关工作 — 2.5 页

## 2.1 Text-to-SQL 方法

- 完整 Schema 条件下的直接生成。
- Schema linking 和 Schema retrieval。
- Few-shot 示例与 query pattern 检索。
- Execution-guided correction 与数据库 Agent。

## 2.2 Recursive Language Models

- RLM 将长上下文放入外部环境，由模型使用代码进行检查、切分和递归处理。
- 说明 ReAct 与真正递归的区别：
  - ReAct 是同一个 Root 多轮行动与观察；
  - 递归是为有边界的子问题发起独立模型调用，再将结果返回 Root。

## 2.3 RLM 到数据库任务的映射

| 通用 RLM 概念 | DB-RLM 实现 |
|---|---|
| 外部环境 | SQLite 数据库和上下文存储 |
| Search/Slice | Schema 与上下文检索 |
| 代码执行 | `db.execute`、`db.sample_values` |
| 父推理过程 | Root Text-to-SQL Agent |
| 递归调用 | depth-1 Leaf Agent |
| 子问题结果 | 证据、局部答案或 SQL 片段 |
| 结果聚合 | Root 将 Leaf 证据整合进最终 SQL |

## 2.4 相关研究联系

- SQRL：同样使用数据库检查，但通过训练学习何时检查，而不仅是 Prompt 提醒。
- Thought Anchors：早期问题设置和计划可能比后期自检更重要。
- Schema retrieval：缩短上下文只有在必要信息仍被保留时才有帮助。

---

# 3. Recursive DB-RLM 方法设计 — 4 页

## 3.1 系统目标

Recursive DB-RLM 应能够：

1. 检查 Schema 和实际存储值；
2. 执行中间 SQL；
3. 保存结构化上下文与状态；
4. 形成和修订 QueryPlan；
5. 将有限子问题委派给 Leaf；
6. 将 Leaf 证据整合为最终 SQL。

## 3.2 共享数据库环境

- 只读 SQLite。
- `db.execute(sql)` 和 `db.sample_values(table, column)`。
- 30 秒超时、行数限制、错误/空集/全 NULL 观察。
- 非递归与递归方法使用相同环境。

## 3.3 非递归 Root 循环

流程：

`问题与上下文 → 模型动作 → 数据库执行 → Observation → 修改 SQL → FINAL`

明确：即使实现文件名为 `recursive_db_rlm.py`，只要没有独立 Leaf 调用，该运行仍属于非递归对照。

## 3.4 三类 RLM 能力

### 能力 A：程序化上下文与代码化推理

- Offline Schema、PK/FK、Join metadata、值格式、Query patterns 和 few-shot。
- 比较直接 Prompt 注入和 context store 主动读取。
- `search`、`slice`、`compose` 的设计目标。

### 能力 B：受控执行环境

- 结构化 Observation 和执行状态。
- capability gate。
- manifest、trace、终止原因和 token 记录。
- 主要价值是可复现和可观测，而不是预设的准确率提升。

### 能力 C：自我改进与分而治之

- QueryPlan 与 Output Contract 是递归前的形式化步骤。
- Root 选择一个有限 SubPlan。
- Leaf 独立求解或验证。
- Root 合并证据并提交最终 SQL。
- 通过等预算额外 Root 调用控制“多一次模型调用”的收益。

## 3.5 Offline Schema Context

- 按题确定性检索相关表、字段说明。
- 提供 PK/FK 图、Join 基数、fan-out、NULL/值格式。
- 未选表保留 names-only 全局索引。
- 它是支持 RLM 的上下文机制，但不是递归本身。

## 3.6 QueryPlan 与 context store

- QueryPlan：目标实体、grain、表、Join、过滤、聚合、排序、回答范围和输出列。
- context store：将相同 Hint、few-shot 和 Offline Schema 从 Prompt 外部化，由模型通过工具读取。
- 这些实验判断递归所需的前置条件是否成立。

## 3.7 递归版本

- v1：纯文本 Leaf。
- v2：Leaf 可以访问数据库。
- v3：Prompt 要求 Leaf 查库。
- v4：向 Leaf 提供 Schema。
- v5：提供 Schema 和可直接照抄的查库代码示例。

**图 2：** Recursive DB-RLM 架构图。

**图 3：** 三类 RLM 能力与 E2–E6 实验的对应关系。

---

# 4. 实验设置 — 3 页

## 4.1 数据集

- 正式完成的实验使用 BIRD mini-dev：500 条记录、498 个唯一问题、11 个数据库。
- Train pool：9,428 条、69 个数据库。
- 诊断集 core-197：137 道 E0 两次都错的题 + 60 道 canary。
- 全 500 与 core-197 的准确率不可直接比较。
- 早期 README/Timeline 曾规划 Spider，但当前报告数字来自 BIRD，应在报告中明确这一研究路线变化。

## 4.2 模型与固定参数

- `azure/seminar-gpt-5.4-mini`。
- `temperature=0`、`reasoning_effort=high`、`max_iterations=8`。
- 除消融外使用 train-only few-shot `k=1`。
- 相同数据库超时和官方 evaluator。

## 4.3 对照方法

| 方法 | 查库 | 多轮 | 外部上下文 | Leaf 递归 |
|---|:--:|:--:|:--:|:--:|
| Baseline 1：完整 Schema 直接生成 | 否 | 否 | 否 | 否 |
| Baseline 2：关键词 Schema 过滤 | 否 | 否 | 一次检索 | 否 |
| 非递归 DB Agent / clean E0 | 是 | 是 | 直接 Prompt | 否 |
| RLM 组件配置 | 是 | 是 | Offline/context/plan | 否 |
| Recursive DB-RLM | 依版本 | 是 | 依版本 | 是 |

## 4.4 指标

- 官方 BIRD execution accuracy。
- recovered/regressed。
- 难度和 canary/both-wrong 分组。
- Root/Leaf/LLM/DB 调用。
- prompt/completion/reasoning/total tokens 和延迟。
- 递归调用率、Leaf 查库率、委派题净收益。
- context reads、片段召回和计划 adherence。
- wrong→correct 轨迹转移。

## 4.5 公平性与可复现性

- 尽量固定模型、工具、数据、评分器和预算。
- capability gate 防止对照组获得隐藏能力。
- Artifact 仅使用 train 来源并记录哈希。
- API/runner 失败与语义结果分开统计。
- 小型触发集至少重复三次。

## 4.6 泄漏事件

- 说明旧 dev-pool retriever 的 self-hit 问题。
- 相关旧结果撤回。
- legacy 数字仅作为历史背景，不作为主要研究结论。

**表 1：** 统一实验设置。

---

# 5. 从直接 Text-to-SQL 到数据库 Agent — 3 页

本章先回答 RQ1，再进入递归分析。

## 5.1 全 500 题主要结果

| 配置 | 准确率 | 含义 |
|---|---:|---|
| Baseline 2：关键词 Schema 过滤 | 51.60% | 朴素剪枝丢失必要 Schema |
| Baseline 1：完整 Schema 直接生成 | 55.20% | 单轮 Text-to-SQL 基线 |
| DB-RLM harness v4 | 64.20% | ReAct + 活库工具；不能证明递归有效 |
| 当前可复现 RLM 增强配置 | 67.40% | Offline Schema + 约定后处理 + train 审计规则 |

## 5.2 数据库驱动多步推理的影响

- 55.20% → 64.20%，+9.0 pp。
- Root 能检查实际值、执行候选 SQL 并接收结果反馈。
- 这是 RLM 风格“外部可执行环境”的主要正面结果，但仍是非递归 Agent。

## 5.3 为什么关键词 Schema 剪枝失败？

- 缩短上下文的同时丢掉了必要表和字段。
- Offline Schema Context 则保留详细相关片段和全库 names-only fallback。

## 5.4 reasoning effort、few-shot 与 ensemble

- High reasoning 是 legacy 阶段的重要增益，但成本更高。
- `k=1` few-shot 保留；更高 k 导致明显题级波动。
- 同强度结果投票可增益，但反映重复采样，而不是递归结构。

## 5.5 本章结论

> 第一个大幅提升来自把直接生成变成具有真实数据库环境的多步 Agent。这证明了 RLM 执行环境的价值，但尚未证明递归委派的价值。

**图 4：** 全 500 题准确率演进，并标记哪些配置真正使用递归。

---

# 6. 各 RLM 组件的独立影响 — 4 页

## 6.1 受控执行与能力隔离（E2）

- 结构化 Observation、独立终止原因、trace 和 capability gate。
- E2-B 为 19/50，处于 E0 的 19/50–20/50 范围；110 个工具事件全部合规。
- 对准确率基本中性，但为递归/非递归公平比较提供基础。

## 6.2 Offline Schema Context（E3-C）

- core-197：77/197 = 39.09%，相对 E0 均值 +4.82 pp。
- 全 500：+3.20 pp。
- 表召回率 98.4%。
- token/题 +14.29%。
- 说明模型无法自行推断的数据库事实具有价值，但准确率收益伴随成本上升。

## 6.3 Static Patterns、few-shot 消融与 Query Mining

- E3-A：73/197，相对 E0 +2.79 pp，但仅是弱证据，token +8.7%。
- E3-B 去掉 few-shot：72/197，成本未下降，静态规则不能替代示例。
- 历史 E3-F 只完成 53 题，Schema 检索退化为近似全量注入，matched subset token +40.34%。
- Query Mining v2：28 个 slot 均未通过跨库门禁；最佳规则只比模型自身判断强 1.5 pp。
- 说明通用结构规则多与强模型已有能力重叠。

## 6.4 QueryPlan 与 Output Contract（E4-A）

- 首次 SQL 前输出结构化计划，Observation 后显式修订。
- 结果：71/197，比 E3-C 少 6 题；恢复 3、回退 9；token +6.67%。
- 82 个失败题结构上遵循了计划，说明问题是计划本身语义错误。
- 形式化提高了可追踪性，但没有保证正确分解。

## 6.5 程序化上下文外部化（E5-A）

- 将相同 Hint、few-shot、Offline Schema 移入只读 context store。
- 197/197 信息逐字节等价。
- 11 题上读取 59 次，0 题未读，0 越权。
- paired smoke 准确率 5/11 持平。
- total token +108.9%，延迟 +312.3%，LLM 调用 +100%。
- 说明接口可用，但当前上下文太小，没有“放不下”的约束。

## 6.6 与递归自我改进有关的验证实验

- E1 strict verified-final：稳定失败恢复 0，调用与 token 约翻倍。
- 字面量核实：N=44，0 恢复、4 回退。
- JOIN 精简：N=26，v1 净 +1，v2 净 0。
- E6 反馈重投：确定性事实反馈不优于等预算纯重试。

## 6.7 对 RQ2 的回答

| RLM 组件 | 准确率影响 | 成本影响 | 结论 |
|---|---|---|---|
| 受控执行环境 | 直接中性 | 必要开销 | 提供安全与可审计执行 |
| Offline Schema Context | 正向 | 中等增加 | 提供模型不可自得的数据库信息 |
| Static/Query patterns | 弱或未通过门禁 | 增加 | 多数重复模型已有结构判断 |
| QueryPlan | 负向 | 增加 | 错误计划被忠实执行 |
| Context store | smoke 持平 | 大幅增加 | 当前规模无上下文压力收益 |
| 验证 Prompt | 中性或负向 | 增加 | 无法修复早期语义承诺 |

**表 2：** RLM 组件消融汇总。

---

# 7. 真正递归委派的影响 — 4 页

这是整篇报告的核心章节，不能与一般 Prompt/harness 实验混为一谈。

## 7.1 本项目中什么才算递归？

- 为有边界的子问题发起独立 Leaf LLM 调用。
- Leaf 独立推理，并按版本访问上下文或数据库。
- Leaf 返回证据、局部答案或 SQL 片段。
- Root 将结果用于最终 SQL。
- Root 自己的一次 ReAct、QueryPlan 或工具调用不算递归。

必须说明历史审计发现：

> 早期名为“DB-RLM”的运行虽然 REPL 内已有递归原语，但 Prompt 从未告诉模型使用它，197 题中调用 0 次。因此这些运行测量的是数据库 Agent harness，而不是真正的递归委派。

## 7.2 五个递归版本

| 版本 | Leaf 配置 | Leaf 查库率 | 委派题净收益 |
|---|---|---:|---:|
| v1 | 纯文本 Leaf | — | 0 |
| v2 | Leaf 允许查库 | 0% | 0 |
| v3 | Prompt 要求查库 | 0% | −2 |
| v4 | Leaf 获得 Schema | 23% | 0 |
| v5 | Schema + 确切代码示例 | 94% | 0 |

逐步解释各版本在排除什么原因：工具不可达、缺少 Schema、Prompt 太含糊或机制未激活。

## 7.3 Leaf 是否产生了真实证据？

- v5 Leaf 实际查询并返回了 `"Business"`、`"Closed"`、`"2019-09-12"` 等真实值。
- 因此零收益不能简单归因于 Leaf 完全没有运行。
- 分析 Root 是否忽略、错误使用，或本来就不需要这些信息。

## 7.4 等预算与触发器对照

- 将递归/反馈与多一次 Root 调用比较。
- 粒度不变量触发器在预筛选阶段失败：fan-out 在 BIRD gold 中不是可靠错误信号。
- 空集/错误触发器进入正式小实验。
- 三次重复中，纯重试与事实增强重试无法区分。
- 相同触发集上的确定性 SQL 改写可复现 +1，而额外模型调用不能。

## 7.5 为什么递归净收益为 0？

1. **没有信息不对称：** Root 与 Leaf 能访问同一个数据库，Leaf 没有创造新事实。
2. **没有上下文瓶颈：** context utilization 约 4%，外部化反而显著增加成本。
3. **缺少可靠路由信号：** 模型不能识别哪些错误需要额外调查，三次完整运行 wrong→correct 恢复均为 0。
4. **干净可分解靶子很少：** 115 个审计失败中只有 10 个是真正模型推理错误。

## 7.6 对准确率、成本与可解释性的影响

- 准确率：五个版本的委派题净收益均为 0。
- 行为：明确代码示例使 Leaf 查库率从 0% 提高到 94%。
- 成本：增加 Leaf/LLM 调用，没有可复现收益。
- 可解释性：Leaf trace 能表明局部证据是什么、机制是否真正激活，即使最终准确率不提升。

## 7.7 对 RQ3 的回答

> 在 Root 与 Leaf 使用相同模型、拥有近似对称的上下文和数据库工具时，depth-1 递归委派没有优于非递归推理。该结果不表示递归普遍无效，而表示递归要产生价值，必须具有信息不对称、专门化 Leaf、真实上下文压力或独立可验证的子问题。

**图 5：** Root 与 Leaf 的信息/工具对称性。

**图 6：** v1–v5 Leaf 查库率与委派题净收益。

---

# 8. 错误、轨迹与 Benchmark 分析 — 2.5 页

本章用于解释 RLM 结果和可测上限，不作为报告主题。

## 8.1 轨迹分析

- 三次完整运行中，失败题 wrong→correct 执行转移精确为 0。
- 超过 99% 的失败题全程未执行出与 gold 匹配的结果。
- 正确题与错误题的查库次数接近。
- 失败通常在问题理解或首次计划阶段已经形成，后续验证或 Leaf 很难挽救。

## 8.2 Schema/Join 失败

- E3-C 残余 Schema/Join 失败的 93.5% 已获得必要表和字段。
- 主要问题是近义表/字段混淆，而不是检索召回。
- 增加相同信息搜索或让 Leaf 读取相同上下文不会自动解决消歧。

## 8.3 115 个失败的全量审计

| 根因 | 数量 | 占比 |
|---|---:|---:|
| Gold 缺陷 | 44 | 38.3% |
| 输出约定未指定 | 22 | 19.1% |
| 指代歧义 | 18 | 15.7% |
| Hint 与 gold 矛盾 | 14 | 12.2% |
| 标注约定残留 | 7 | 6.1% |
| 模型真实推理错误 | 10 | 8.7% |

说明：该结果限定递归实验中真正可测的能力型错误密度。

## 8.4 因果验证

- 消歧实验：命中预期指代对象 1/7 → 6/7；整题正确 0/7 → 2/7。
- Hint 消融：冲突组 0/5 → 3/5；两个对照组零损害。
- 说明部分稳定错误不是可以通过递归分解解决的推理错误。

## 8.5 标注对齐

- 确定性约定后处理：core-197 +5，全 500 +6。
- 该收益属于 BIRD 标注对齐，不能报告为递归或通用 Text-to-SQL 能力提升。

**图 7：** 115 条失败的根因分布。

---

# 9. 成本、可扩展性与可解释性 — 1.5 页

## 9.1 成本

- High reasoning 和多轮调用是主要 token 来源。
- Offline Schema Context：token/题 +14.29%，同时获得准确率提升。
- QueryPlan：token +6.67%，准确率下降。
- Context store：token +108.9%，延迟 +312.3%。
- Recursive Leaf：增加调用，但委派题净收益为 0。

## 9.2 可扩展性

- 原始假设：大型 Schema 下选择性/递归探索更有优势。
- 实际 BIRD 知识载荷只有 726–2,572 tokens，Prompt 约 5,171 tokens。
- 当前实验没有形成 RLM 分块上下文预期解决的强压力条件。
- 结论应为“在当前规模下未证明”，而不是“一般情况下无效”。

## 9.3 可解释性与可观测性

- Trace 记录上下文选择、SQL 执行、计划修订、Leaf 调用、返回证据和终止原因。
- QueryPlan 与 Leaf 即使不提分，也提高了诊断能力。
- 区分“可观察的外部动作”和“不可见的隐藏推理”。

---

# 10. 讨论与局限 — 1.5 页

## 10.1 RLM 对 Text-to-SQL 的总体影响

- 可执行数据库环境有价值。
- 相关 Offline 数据库知识有价值。
- 程序化上下文只有在上下文压力真实存在时才有价值。
- 错误 QueryPlan 不会因结构化而自动变正确。
- 递归只有在子调用带来 Root 不具备的信息、专门能力、验证或并行性时才可能有优势。

## 10.2 哪些条件下递归可能有效？

- 更大 Schema 或更长证据。
- Leaf 拥有专门工具、不同模型或不同数据源。
- 可独立执行并具有清晰组合规则的子查询。
- 经过训练的路由与不确定性估计。
- 含有更多真实多阶段推理错误的干净评测集。

## 10.3 局限

- 主要使用一个模型和一个 Benchmark。
- 正式结果使用 BIRD，而非最初规划的 Spider。
- 未进行领域微调或强化学习。
- 只测试 depth-1 递归，且委派题规模有限。
- 上下文规模不足以检验 RLM 在超长上下文中的优势。
- 隐藏 reasoning token 无法做 CoT 级因果分析。
- 部分分数增益来自标注对齐。
- core-197 同配置重跑方差约 6 题。

---

# 11. 结论 — 1 页

按研究问题组织：

1. 数据库驱动的多步 Agent 相对直接 Text-to-SQL 有显著提升。
2. RLM 组件中，Offline Schema Context 提高了准确率，受控执行提高了可观测性；QueryPlan 与上下文外部化没有带来收益。
3. 真正的 Root–Leaf 递归成功激活，但委派题净收益为 0。
4. 原因是工具与信息对称、没有上下文压力、缺少可靠路由信号，以及干净可分解错误太少。
5. 后续研究应在 Leaf 具有专门信息/工具、任务具有可验证子目标的条件下测试递归。

建议结尾：

> 对 Text-to-SQL 而言，系统能够再次调用模型并不等于递归会自动有益；只有当子调用相对 Root 创造了真实的信息或计算优势时，递归才具有独立价值。

---

# 实验覆盖表

| 实验/结果 | 报告位置 | 与 RLM 主题的关系 |
|---|---|---|
| Baseline 1 直接生成 | §5 | 一次性 Text-to-SQL 基线 |
| Baseline 2 Schema 过滤 | §5 | 非 Agent 检索基线 |
| clean E0 / 非递归 ReAct | §5 | 主要 Root 对照 |
| legacy DB-RLM v4 | §5 | 历史数据库 Agent，不是递归证据 |
| reasoning effort / few-shot | §5 | 模型与上下文控制 |
| E1 strict verified-final | §6 | 自我改进前提实验 |
| E2 结构化执行与 capability gate | §3、§6 | 受控环境能力 |
| E3-A/B Static Patterns | §6 | Offline Context 原型与消融 |
| E3-C Offline Schema Context | §6 | 正向 RLM 上下文组件 |
| E3-D Query Mining | §6 | Offline Pattern 门禁结果 |
| E3-E | 附录 | 因前置失败未运行 |
| E3-F 历史集成 | §6/附录 | RLM 上下文集成诊断 |
| E4-A QueryPlan | §6 | 递归前的显式形式化 |
| 字面量核实、JOIN 精简 | §6 | 自检行为实验 |
| E5-A context store | §6、§9 | 程序化上下文实验 |
| E5-B search/slice/compose | §6/附录 | 因收益前提不成立未运行 |
| E6 等预算重投/反馈 | §7 | 额外计算和触发对照 |
| Recursive Leaf v1–v5 | §7 | 真正递归的核心结果 |
| 粒度/空集触发器 | §7 | 递归路由实验 |
| ReAct 轨迹分析 | §8 | 解释 RLM 作用时机 |
| Schema/Join 深度诊断 | §8 | 区分检索与推理问题 |
| 115 题全量失败审计 | §8 | 限定递归可测空间 |
| 消歧与 Hint 消融 | §8 | Benchmark 因果诊断 |
| 标注约定后处理 | §8 | 标注对齐，不是递归收益 |
| 重跑方差与分类器修复 | §4/附录 | 结果有效性 |

---

# 建议图表

## 图

1. 从直接 Text-to-SQL 到 Recursive DB-RLM 的研究路线。
2. Recursive DB-RLM 架构图。
3. 三类 RLM 能力与 E2–E6 的映射。
4. 全 500 题准确率演进。
5. Root–Leaf 信息与工具对称性。
6. v1–v5 Leaf 查库率与委派题净收益。
7. 115 个失败的审计分布。

## 表

1. 数据、模型和统一实验协议。
2. Baseline 与总体结果。
3. RLM 组件消融。
4. 递归版本与等预算对照。
5. 准确率、token、延迟和工具使用权衡。
6. 研究问题与最终答案。

---

# 附录

## 附录 A：完整运行登记

列出 profile、父配置、唯一变量、数据集、run ID、结果/trace、准确率、成本、递归调用和决定。

## 附录 B：Prompt 与能力定义

收录 clean Root Prompt、QueryPlan schema、context store 工具、Leaf v1–v5 Prompt、capability gate 和等预算对照 Prompt。

## 附录 C：Offline Artifacts

记录 Schema metadata、检索策略、表召回率、静态 patterns、Query Mining slots、跨库门禁和约定规则。

## 附录 D：详细错误与轨迹

列出 recovered/regressed ID、wrong→correct 转移、完整失败分类和代表性 Root–Leaf trace。

## 附录 E：复现与有效性威胁

记录模型配置、评分器、manifest、哈希、重试/超时、泄漏修复、分类器修复和重跑方差。

---

# 写作材料索引

- 当前项目与历史结果：[`../../README.md`](../../README.md)
- 原始 Recursive DB-RLM 目标：[`../../README_zh.md`](../../README_zh.md)
- 原始项目计划：[`../../Timeline_zh.md`](../../Timeline_zh.md)
- 统一实验计划：[`../experiment-plan/README.md`](../experiment-plan/README.md)
- Agent 机制与实验账本：[`README.md`](README.md)
- 当前全量结果报告：[`REPORT_2026-08-11.md`](REPORT_2026-08-11.md)
- 综合证据：[`SYNTHESIS.md`](SYNTHESIS.md)
- 根因调查：[`rootcause/README.md`](rootcause/README.md)
- E6 与等预算实验：[`rootcause/e6_recursion_2026-08-09.md`](rootcause/e6_recursion_2026-08-09.md)

# 建议写作顺序

1. 第 3 章方法。
2. 第 4 章实验设置。
3. 第 5–7 章结果，最后写真正递归。
4. 第 8–9 章解释机制为什么产生这些影响。
5. 第 10 章局限和递归成立条件。
6. 引言和结论。
7. 最后写摘要。
