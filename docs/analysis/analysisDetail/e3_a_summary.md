# E3-A 完整 197 题结果报告

## 实验目的

验证仅使用 BIRD train 的通用 SQL 模式库，作为 E0 强基线的额外上下文，是否能改善固定 197 题诊断集上的 Text-to-SQL 执行准确率。该实验只检验 Offline Query Mining 中的 pattern 内容，不检验 RLM 外部环境、程序化检索或递归分解。

## 运行范围与配置

- 运行：`e3_a_core197_run1`
- run_id：`20260713T235804Z-19152b85`
- 数据：`data/processed/bird_dev_500.json` 中由 `bird_cleancore_ids.json` 选出的 197 题
- 分组：`both_wrong` 137 题、`canary` 60 题
- 模型：`azure/seminar-gpt-5.4-mini`，`reasoning_effort=high`，`temperature=0`
- 运行参数：`k=1`、`max_iterations=8`
- Profile：`e3-a`；无 legacy DB hints、无 strict verified-final、无 capability gate

## E3-A 流程

读取 `data/train_pool.json` 的 9,428 个训练示例
  ↓
从 train SQL 构建固定的通用模式库
  ↓
读取当前评测问题
  ↓
检索 1 个 train few-shot 示例
  ↓
拼接问题、Hint、Schema、few-shot 和固定模式库
  ↓
模型调用 `db.sample_values` 或 `db.execute`
  ↓
获得数据库 observation，并在 ReAct 循环内修正 SQL
  ↓
模型输出 `FINAL(...)`
  ↓
按 E0 相同的宽松 FINAL 协议接受 SQL
  ↓
执行 predicted SQL 与 gold SQL，比较答案
  ↓
保存结果、trace、token usage 与自动错误分类

当前模式库包含聚合粒度、过滤聚合、Top-K、输出契约、条件回答、去重列表、Join 路径和窗口排名等通用模式。它对每个问题固定注入，不会根据当前问题检索模式，也不使用 eval gold、eval 正确答案或其他 eval 题目的信息。

## 结果

| 指标 | 结果 |
|---|---:|
| 正确数 | 73 / 197 |
| 执行准确率 | 37.06% |
| `both_wrong` | 22 / 137 = 16.06% |
| `canary` | 51 / 60 = 85.00% |
| simple | 27 / 50 = 54.00% |
| moderate | 31 / 96 = 32.29% |
| challenging | 15 / 51 = 29.41% |
| 正常 `final` 结束 | 195 |
| APIError | 2 |

50 题筛选运行的 44.00% 不能代表完整集表现；完整 197 题的主结果为 37.06%。这说明前 50 题筛选集偏乐观，后续机制只应以完整集或明确标注的子集结论为准。

## 成本与延迟

| 指标 | 总量 | 每题平均 |
|---|---:|---:|
| LLM 调用 | 539 | 2.74 |
| prompt tokens | 1,456,632 | 7,394.07 |
| completion tokens | 1,449,456 | 7,357.64 |
| reasoning tokens | 1,336,785 | 6,785.71 |
| total tokens | 2,906,088 | 14,751.72 |
| 延迟 | 7,487.78 s | 38.01 s |
| 缺失 usage 的调用 | 9 | - |

## 自动错误轨迹分类

共 124 个失败项。分类器输出的首要类别如下：

| 错误类别 | 数量 |
|---|---:|
| `UNVERIFIED_FINAL` | 93 |
| `AGGREGATION_REASONING` | 10 |
| `SEMANTIC_REVIEW_REQUIRED` | 10 |
| `SCHEMA_LINKING` | 4 |
| `OUTPUT_CONTRACT` | 3 |
| `RUNNER_OR_API` | 2 |
| `EMPTY_OR_NULL_RESULT` | 1 |
| `TOOL_ERROR` | 1 |


### `UNVERIFIED_FINAL` 控制流细分

分类器现已读取最终 SQL 前最近一次 `db.execute` 的结构化 observation，并在结果可比较时将该执行结果与 gold answer 对齐。

| 子类 | 数量 | 含义 |
|---|---:|---|
| `final_sql_rewritten_after_incorrect_observation` | 77 | 最近一次已执行 SQL 返回正常行，但答案仍不正确；模型尝试语义修正后未执行新 SQL |
| `final_sql_rewritten_after_correct_observation` | 1 | 最近一次已执行 SQL 已匹配 gold，最终改写反而使答案错误 |
| `final_sql_rewritten_after_successful_observation` | 1 | 返回正常行，但历史 trace 无法将该行与 gold answer 对齐 |
| `final_sql_changed_after_unparseable_observation` | 9 | 存在执行事件，但 observation 不能可靠判定状态 |
| `final_sql_changed_after_sql_error` | 1 | SQL 报错后改写并直接 FINAL |
| `final_without_db_execution` | 4 | 没有任何 `db.execute` 就 FINAL |

77/93 是“先前 SQL 本来就错误”的情形，只有 1/93 是“正确 SQL 被 FINAL 改坏”。因此不能把“永远提交最后一次执行 SQL”当作修复方案：它最多避免 1 个已知回退，却会保留绝大多数错误答案。

### 77 项的语义根因

分类表同时保留控制流标签和最终 SQL 相对 gold SQL 的语义标签。这 77 项进一步分为：

| 语义类别 | 数量 | 具体子类 |
|---|---:|---|
| `AGGREGATION_REASONING` | 31 | 聚合/分组不匹配 28，排序方向或排序范围不匹配 3 |
| `OUTPUT_CONTRACT` | 20 | 输出列数不匹配 18，YES/NO 与逐行输出不匹配 2 |
| `SCHEMA_LINKING` | 14 | 表选择或 Join 路径不匹配 14 |
| `SEMANTIC_REVIEW_REQUIRED` | 12 | 过滤范围或表达式不匹配 12 |

SQL 改写类型中，26 项只修改表达式或投影；其余涉及表、`WHERE`、`GROUP BY`、`ORDER BY`、`LIMIT` 或聚合结构。这说明 `UNVERIFIED_FINAL` 遮住的不是一种统一错误，而是聚合、输出契约、Schema/Join 和过滤语义四类问题。

### 全部 124 个失败的语义归因

不能直接使用首要 `error_class` 判断失败原因，因为 93 个 `UNVERIFIED_FINAL` 会遮住并行的语义标签。以 `semantic_error_class` 重新统计后，124 个失败中有 120 个可以进行结构化语义归因，另外 4 个属于运行、解析或空结果问题：

| 实际原因层 | 数量 | 占全部失败 | 主要表现 |
|---|---:|---:|---|
| `AGGREGATION_REASONING` | 47 | 37.90% | 聚合/分组 42，排序方向或排序范围 5 |
| `OUTPUT_CONTRACT` | 29 | 23.39% | 输出列数 25，YES/NO 与逐行输出 4 |
| `SEMANTIC_REVIEW_REQUIRED` | 24 | 19.35% | 过滤范围、表达式或 gold 歧义 |
| `SCHEMA_LINKING` | 20 | 16.13% | 表选择或 Join 路径不匹配 |
| 运行、工具或空结果 | 4 | 3.23% | API、FINAL 解析、observation 解析、空结果 |

#### 聚合与排序：47 项

轨迹能够确认预测 SQL 与 gold SQL 在 `GROUP BY`、聚合函数、`HAVING`、排序字段、排序方向或 `LIMIT` 作用范围上存在结构差异。可能形成机制包括：

- 没有先确定统计对象和结果粒度，把“每个实体”统计写成全局统计，或反过来；
- 加入多余分组键，导致一行被拆成多组；
- 混淆 `COUNT(*)`、`COUNT(column)` 与 `COUNT(DISTINCT column)`；
- 多阶段聚合只完成一层，例如先求每组统计值、再从这些统计值中取最大值；
- 混淆聚合前 `WHERE` 与聚合后 `HAVING`；
- Top-K 按明细字段而不是聚合值排序，或错误处理升降序、并列和 `LIMIT`。

这是最大的失败来源。E3-A 的固定模式库已经包含聚合、Top-K 和排序规则，但仍出现 47 项，说明“看到通用规则”不等于模型能够把规则实例化为当前问题的统计对象、分组键和排序字段。后续若继续处理该类错误，应测试题目级结构化查询计划，而不是继续堆叠同类静态提醒。

#### 输出契约：29 项

25 项的预测列数与 gold 不同，4 项混淆 YES/NO 与逐行输出。可能形成机制包括：

- 未在生成 SQL 前明确用户要求的列数、顺序和每列语义；
- 只输出统计值，遗漏名称、年份或其他被要求的描述列；
- 把用于排序、连接或解释的辅助列也放入最终输出；
- 问题要求存在性判断，却返回原始记录，或问题要求记录列表却返回布尔值；
- train few-shot 的输出形状与当前问题不同，模型错误模仿示例。

例如 `bird_1011` 预测 1 列而 gold 为 3 列，`bird_1014` 预测 2 列而 gold 为 1 列。该类错误不需要递归才能发现，优先候选是生成 SQL 前的结构化输出契约，以及提交前仅检查列形状的确定性校验。

#### Schema 与 Join：20 项

轨迹能够确认预测 SQL 和 gold SQL 使用的表集合或 Join 路径不同。可能形成机制包括：

- 选择名称相近但业务含义不同的字段或表；
- 遗漏承载实体身份、过滤条件或关联关系的表；
- 没有沿外键完成 Join 路径；
- 多对多 Join 引入重复行，随后污染聚合结果；
- 通用模式只提醒“检查 Join”，但没有提供当前 Schema 下的字段来源和路径。

例如部分 `thrombosis_prediction` 问题只查询 `laboratory`，而 gold 还连接 `patient` 或 `examination`。这一类应由 Schema metadata、Join path 检索或题目级 Schema linking 实验处理，不能用更多聚合模式解释。

#### 过滤范围与表达式：24 项

这类 SQL 通常能够执行，但结果与 gold 不同，自动结构规则没有发现更明确的表、列数或聚合差异。可能原因包括：

- `>`、`>=`、等值或区间边界理解错误；
- 日期、年份或时间窗口范围错误；
- 条件作用在错误层级，例如应过滤明细却过滤聚合结果；
- `AND`、`OR` 或括号范围错误；
- 百分比、单位换算、字符串标准化或 NULL 处理错误；
- 问题、Hint 与 gold 存在歧义或数据集噪声。

该类别的自动归因置信度最低。后续不能把 24 项全部当作 Agent 回归，应人工抽样比较问题、Hint、predicted SQL、gold SQL 和真实结果，再决定是否需要值检索、条件计划或数据集噪声隔离。

#### 运行、工具和空结果：4 项

| ID | 类别 | 已确认原因 | 处理方式 |
|---|---|---|---|
| `bird_1168` | `RUNNER_OR_API` | Azure/LiteLLM API 错误，没有 assistant 输出 | 单独统计 API 失败并允许断点重跑 |
| `bird_959` | `RUNNER_OR_API` | `predicted_sql` 为空，没有解析出 FINAL SQL | 记录解析失败并进行受控重试 |
| `bird_963` | `TOOL_ERROR` | observation 不可解析，无法确认执行状态 | 统一工具结构化 JSON |
| `bird_529` | `EMPTY_OR_NULL_RESULT` | 最终 SQL 返回 0 行 | 检查过滤值、日期和 Join 条件 |

这 4 项不应计入模式库、Planner 或递归机制的语义收益。比较实验时应同时报告原始准确率和排除不可归因运行失败后的参考准确率，但正式主指标仍保留全部题目。

### SQL 改写行为

在完整分类表中，29 项只改变表达式或投影，10 项改变表集合，另有多项同时修改 `WHERE`、`GROUP BY`、`ORDER BY`、`LIMIT` 或聚合结构；4 项在没有任何先前执行的情况下直接提交。对 77 个“错误 observation 后改写未执行”的子集，26 项只修改表达式或投影。

这说明失败不只是“模型忘记执行最后 SQL”。很多轨迹中，模型已经识别到旧 SQL 可能有问题并进行实质性改写，但缺少稳定的题目级约束来判断改写方向是否正确。数据库返回正常行只能证明 SQL 可执行，不能证明它回答了问题。

### 归因置信度与边界

| 归因 | 置信度 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| API、空 FINAL、空结果、未执行 FINAL | 高 | trace 中存在明确状态或错误 | 不能解释语义 SQL 应如何修正 |
| 输出列数、表集合、聚合结构差异 | 中 | predicted 与 gold 存在可观察结构差异 | 不保证 gold 是唯一合理写法 |
| 过滤范围或表达式不匹配 | 低 | 执行答案不同且未找到更具体差异 | 不能排除 gold 噪声或等价表达 |
| “模型为什么这样想” | 不可恢复 | 无 | trace 不能恢复未输出的隐藏推理 |

这些语义标签来自运行后比较最终 SQL 与 gold SQL，只用于实验诊断。它们能够定位可观察的结构差异，但不能恢复模型未输出的隐藏推理过程；gold 不进入 Agent、Prompt、pattern artifact 或在线决策。

### 失败形成机制与实验判断

1. **主要瓶颈是题目级语义构造，不是 FINAL 格式。** 77 项在提交前执行过的 SQL 已经答错，strict verified-final 只能要求重试，不能告诉模型正确的聚合粒度、输出列、Join 路径或过滤范围。
2. **固定通用模式没有稳定转化为当前问题的约束。** 全部失败中聚合和输出契约共 76 项，占 61.29%。可能原因是模式没有按问题检索、缺少对当前 Schema 的实例化，或与 train few-shot 信息重复。
3. **E3-RF 只回答模式库能否替代 few-shot。** 若 E3-RF 准确率基本保持且 token 降低，说明模式库具有替代价值；若明显下降，说明 E3-A 的增益依赖 few-shot 与模式库组合。E3-RF 本身不能证明聚合、输出或 Schema 错误已经被修复。
4. **后续实验必须按错误类型匹配机制。** 聚合与输出优先测试结构化查询计划/输出契约；Schema/Join 优先测试 metadata 与路径检索；过滤语义先人工抽样，再决定值检索或条件计划；运行错误由 runner 和 trace 修复。
5. **比较时要看配对错误迁移，而不只看总准确率。** 对每个新机制分别统计四个语义类别在固定 197 题上的 recovered、regressed 和净变化，避免一种错误减少但另一种错误增加后被总分掩盖。
6. **数据库分布只能用于定位，不可直接解释难度。** 当前失败较多的数据库包括 `formula_1` 20、`card_games` 17、`thrombosis_prediction` 17 和 `codebase_community` 16；由于各数据库在 197 题中的题量不同，未计算分母前不能声称这些 Schema 更难。

### 错误到改进机制映射

| E3-A 剩余错误 | 数量 | 具体改进 | 对应 v0.14 实验 | 接受条件 |
|---|---:|---|---|---|
| 聚合与排序 | 47 | Root 内 QueryPlan 明确统计对象、grain、group by、aggregate、having、order/limit | `P` | 相对 O* 净下降；稳定恢复超过回退；不增加独立 LLM call |
| 输出契约 | 29 | 将 answer type、列数、列顺序、类型和含义合并进 QueryPlan | `P` | 输出错误净下降，且不靠 gold 在线判断 |
| 过滤范围/表达式 | 24 | 先人工复核低置信度样本；再结构化字段、运算符、值、时间范围和作用层级，必要时查询样例值 | `P`，后续 `C-P` | 人工确认的 Agent 错误减少，疑似 gold 噪声单列 |
| Schema/Join | 20 | metadata、PK/FK 图、Join path、关系基数和样例格式合并为 artifact | `M` | Schema/Join 净下降，且不引入 Join 重复导致的聚合回退 |
| observation 不可解析 | 9 个控制流样本 | 统一结构化工具结果，保留 SQL、status、rows/error | 基础设施 | 可解析率提高，不计为模型推理收益 |
| API、空 FINAL、空结果 | 4 条无语义标签记录 | API 重试、终止原因、断点续跑和空结果诊断 | 基础设施 | 运行失败下降 |
| `UNVERIFIED_FINAL` | 93 条控制流标签 | 只保留诊断，不恢复 strict gate，不做独立 FINAL 同步 | 无独立实验 | 不作为机制接受指标 |

P 和 M 必须从同一个 O* 独立运行。P/M 都有效时才增加一次组合确认；后续 C-P-Leaf 只处理 QueryPlan 中被判定为复杂的一个 SubPlan。

## 结论

E3-A 在完整固定集上得到 73/197（37.06%），高于 E0 两次运行均值 34.26%，差值为 +2.79 pp。逐题比较中，有 6 题相对两次 E0 都稳定恢复、1 题稳定回退；收益主要出现在 moderate 题（31/96，E0 两次均为 27/96），challenging 题没有明确改善。与此同时，E3-A 每题 total tokens 为 14,751.72，比 E0 均值约高 8.7%。因此，现有证据支持“固定 train-only pattern library 可能带来小幅增益”，但不足以证明稳定显著提升或更高效率。

错误轨迹进一步限制了这一结论：77 个主要 `UNVERIFIED_FINAL` 样本的根因仍集中在聚合、输出契约、Schema/Join 和过滤语义，说明模式库尚未解决它所针对的核心错误。E3-A 可以暂时作为 E3-RF 的父配置，但不能作为最终接受的 Offline Query Mining 方案。

下一步按以下顺序执行：

1. **先运行 E3-RF 单变量消融。** 保留同一模式库、模型、197 题、ReAct 和运行参数，只移除 train few-shot，判断模式库能否替代 few-shot，而不是仅靠额外 Prompt 长度获得小幅收益。
2. **E3-RF 期间不修改 FINAL 逻辑。** 否则无法区分 few-shot 消融与控制流修复的作用。
3. **不安排独立 FINAL 同步实验。** 当前证据中只有 1/93 是“正确 SQL 被最终改坏”，而执行 SQL 只能验证可运行性，不能验证聚合、输出、Join 或过滤语义。Root 仍应在正常 ReAct 协议中执行最终候选 SQL，但不把额外控制器同步作为 baseline 或新机制；只有后续再次观察到大量可由执行反馈直接恢复的样本时才重新评估。
4. **修复 9 条不可解析 observation。** 这是 trace/工具状态可观测性问题，不应混入语义机制结论。

历史 E3-A 的 `run_manifest.json` 只记录了 `query_pattern_mode=train-static-v1`，没有保存精确 pattern artifact 哈希，因此无法事后严格证明其内容与 E3-RF 完全一致。当前 runner 已为后续运行补充 pattern artifact 内容、支持数和哈希记录；E3-RF 必须使用该记录，报告中也要保留这一历史可复现性限制。
