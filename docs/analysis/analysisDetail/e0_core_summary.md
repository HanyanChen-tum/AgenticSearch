# E0 完整 197 题重复运行结果报告

- 运行次数：2
- 题目数：197
- 平均准确率：34.26%
- 准确率总体标准差：0.76%

> 注意：该报告包含显式允许的配置差异，只能作为探索性比较。

## 实验目的

建立不使用 query pattern library、Planner、metadata/context store、递归分解或 strict verified-final 的 Clean DB ReAct 基线，测量固定 197 题诊断集上的执行准确率、跨运行稳定性、成本和错误结构。E0 用于确定后续机制实验的父基线与错误优先级，不用于验证任何新增机制。

## 运行范围与配置

- 运行：`e0_core_run1`、`e0_core_run2`
- run_id：`20260713T072941Z-6b75f55b`、`20260713T094637Z-5caab99c`
- 数据：`data/processed/bird_dev_500.json` 中由 `bird_cleancore_ids.json` 选出的 197 题
- 分组：`both_wrong` 137 题、`canary` 60 题
- 模型：`azure/seminar-gpt-5.4-mini`，`reasoning_effort=high`，`temperature=0`
- 运行参数：`k=1`、`max_iterations=8`
- Profile：`clean-e0`；无 query patterns、legacy DB hints、strict verified-final、capability gate、Planner 或递归
- 已知配置差异：Run1 的 `evaluation_sql_timeout_seconds=None`，Run2 为 30 秒

## 流程

运行开始前
  ↓
加载 `clean-e0` 配置：`clean-protocol-v1`、`verified_final=false`、直接 context、非递归、无 Planner、无 capability gate
  ↓
加载仅来自 `data/train_pool.json` 的 train few-shot 检索池，并记录其来源与哈希
  ↓
读取固定 `both_wrong + canary` challenge set 中的一条 BIRD mini-dev 评测问题
  ↓
检索 1 条 train few-shot 示例
  ↓
拼接 Hint、Schema 和 train few-shot
  ↓
模型调用 `db.sample_values` 或 `db.execute`
  ↓
获得数据库 observation；若出现 SQL error、空结果或全 NULL，向模型返回对应反馈
  ↓
ReAct 修改 SQL（生成 SQL → 执行 → 看到结果或错误 → 修改 SQL → 再执行）
  ↓
模型调用 `FINAL`
  ↓
E0 接受可解析的 FINAL SQL，不启用 strict verified-final
  ↓
执行 predicted SQL 和 gold SQL
  ↓
比较答案
  ↓
保存结果、trace、token usage 和自动错误分类

E0 不注入 query pattern library、legacy DB hints 或 eval/dev 衍生知识；也不执行受控 context 检索、代码搜索/切片、Planner 或 Leaf 递归调用。

### FINAL 提交条件

模型输出被识别为合法 FINAL(...)
→ FINAL 中能解析出 SQL
→ 当前响应不是代码执行响应
→ E0 的 verified_final=False，因此不再检查 SQL 是否执行过
→ 接受提交

所以 E0 的控制器不会额外检查：
SQL 是否执行过；
SQL 是否执行成功；
SQL 是否返回空结果；
SQL 是否等于最近一次执行的 SQL；
SQL 是否语义正确。

## 配置差异

- `evaluation_sql_timeout_seconds`：20260713T072941Z-6b75f55b=None, 20260713T094637Z-5caab99c=30

## 结果

| Run ID | 正确数 | 准确率 | Tokens/题 | LLM 调用/题 | DB 调用/题 | 延迟/题 |
|---|---:|---:|---:|---:|---:|---:|
| 20260713T072941Z-6b75f55b | 69/197 | 35.03% | 13658.99 | 2.76 | 1.89 | 41.33 s |
| 20260713T094637Z-5caab99c | 66/197 | 33.50% | 13481.25 | 2.72 | 1.90 | 42.28 s |

## 稳定性

- 始终正确：62
- 始终失败：124
- 结果不稳定：11

## 自动错误轨迹分类

| 错误类别 | 数量 |
|---|---:|
| AGGREGATION_REASONING | 14 |
| OUTPUT_CONTRACT | 6 |
| RUNNER_OR_API | 4 |
| SCHEMA_LINKING | 3 |
| SEMANTIC_REVIEW_REQUIRED | 16 |
| TOOL_ERROR | 1 |
| UNVERIFIED_FINAL | 215 |

该表是两次运行共 259 条失败记录的首要标签汇总。由于 `UNVERIFIED_FINAL` 会覆盖底层语义原因，不能使用该表直接判断真正的失败分布。两次 `classification_sheet.csv` 已使用当前双标签分类器重新生成，下面同时分析控制流标签和语义标签。

## 相邻运行变化

- 20260713T072941Z-6b75f55b -> 20260713T094637Z-5caab99c: 恢复 4，退化 7

## 结果分析

### 1. 基线水平与重复运行差异

两次运行分别为 35.03% 和 33.50%，均值为 34.26%，相差 1.53 个百分点。Run2 相对
Run1 恢复 4 题、退化 7 题，净减少 3 道正确题，与总正确数从 69 降至 66 一致。
这说明当前 Agent 存在一定生成随机性，但两次结果的总体水平接近，可以作为后续
单次机制筛选的探索性基线。

这里的 0.76% 是两次运行的总体标准差，不能视为可靠的统计置信区间。此外，Run1
没有最终评测 SQL 超时，Run2 的该字段为 30 秒，因此两次运行不是严格同协议复现。

### 2. 稳定性说明主要瓶颈不是偶然波动

- 两次始终正确 62 题，占 31.47%。
- 两次始终失败 124 题，占 62.94%。
- 两次结果不稳定 11 题，占 5.58%。

稳定失败远高于不稳定题，说明大部分错误会跨运行重复，不只是采样或推理波动。
后续机制应优先检查这 124 道稳定失败题是否被恢复，而不能只观察总准确率。

### 3. 双标签错误轨迹分析

#### 3.1 全部 259 条失败的语义归因

两次运行分别有 128 和 131 条失败记录，共 259 条。不能直接使用首要 `error_class` 判断失败原因，因为其中 215 条 `UNVERIFIED_FINAL` 会遮住并行的语义标签。按 `semantic_error_class` 重新统计后，254 条可以进行结构化语义归因，另外 5 条属于运行、解析或工具问题：

| 实际原因层 | Run1 | Run2 | 合计 | 占全部失败 | 主要表现 |
|---|---:|---:|---:|---:|---|
| `AGGREGATION_REASONING` | 45 | 48 | 93 | 35.91% | 聚合/分组 82；排序方向或排序范围 11 |
| `SEMANTIC_REVIEW_REQUIRED` | 33 | 34 | 67 | 25.87% | 过滤范围或表达式，包含可能的 gold 歧义 |
| `OUTPUT_CONTRACT` | 29 | 27 | 56 | 21.62% | 输出列数 48；YES/NO 与逐行输出 8 |
| `SCHEMA_LINKING` | 20 | 18 | 38 | 14.67% | 表选择或 Join 路径不匹配 |
| 运行、解析或工具问题 | 1 | 4 | 5 | 1.93% | API、空 FINAL、observation 解析或空结果 |

更细的结构分布为：

| 语义子类 | 合计 |
|---|---:|
| 聚合或分组不匹配 | 82 |
| 过滤范围或表达式不匹配 | 67 |
| 输出列数不匹配 | 48 |
| 表选择或 Join 路径不匹配 | 38 |
| 排序方向或排序范围不匹配 | 11 |
| YES/NO 与逐行输出不匹配 | 8 |

这些数量是两次运行的失败**记录数**，不是去重题目数；同一道稳定失败题会在 Run1 和 Run2 各计一次。后续的聚合、过滤、输出契约和 Schema/Join 小节均是对这 **259 条全部失败记录** 的展开，不是只分析 `UNVERIFIED_FINAL` 或 124 道稳定失败题。

#### 3.2 `UNVERIFIED_FINAL` 控制流细分

两次运行共 215 条 `UNVERIFIED_FINAL`，进一步分为：

| 控制流子类 | 数量 | 含义 |
|---|---:|---|
| `final_sql_rewritten_after_incorrect_observation` | 180 | 最近执行 SQL 已答错，模型改写后未执行新 SQL |
| `final_sql_changed_after_unparseable_observation` | 18 | 有执行事件，但 observation 无法可靠解析 |
| `final_without_db_execution` | 9 | 没有调用 `db.execute` 就 FINAL |
| `final_sql_rewritten_after_correct_observation` | 4 | 已执行 SQL 正确，最终改写反而答错 |
| `final_sql_changed_after_empty_result` | 3 | 空结果后改写但未执行 |
| `final_sql_rewritten_after_successful_observation` | 1 | 执行成功，但历史 trace 无法与 gold 对齐 |

180/215 的旧 SQL 本身已经错误，因此“提交最后一次执行 SQL”不会修复主要问题；它只会保留错误答案。4 条正确 SQL 被改坏证明宽松 FINAL 确实存在回退风险，但占比不足以解释 E0 的整体低准确率。E1 已经验证 strict verified-final 会显著增加成本而不提高准确率，因此不再把 FINAL 控制作为当前主要实验方向。

#### 3.2.1 `final_sql_rewritten_after_incorrect_observation` 的语义与改写细分

不能把这 180 条只理解为同一种“未验证 FINAL”问题：最近一次执行的 SQL 已经返回了错误答案，模型随后试图做语义修正，但没有执行改写后的版本。按最终 SQL 相对 gold 的并行语义标签细分如下：

| 语义类别 | 数量 | 具体子类 |
|---|---:|---|
| `AGGREGATION_REASONING` | 64 | 聚合/分组不匹配 55；排序方向或排序范围不匹配 9 |
| `SEMANTIC_REVIEW_REQUIRED` | 42 | 过滤范围或表达式不匹配 42 |
| `OUTPUT_CONTRACT` | 46 | 输出列数不匹配 38；YES/NO 与逐行输出不匹配 8 |
| `SCHEMA_LINKING` | 28 | 表选择或 Join 路径不匹配 28 |

其中 67/180 的改写仅涉及表达式或投影；其余 113/180 涉及表、`WHERE`、`GROUP BY`、`HAVING`、`ORDER BY`、`LIMIT` 或聚合结构。也就是说，`final_sql_rewritten_after_incorrect_observation` 覆盖的是聚合、过滤、输出契约和 Schema/Join 四类不同的语义尝试，而不是一个能靠 FINAL 同步统一修复的故障。提交旧 SQL 会保留已知错误；提交未执行的新 SQL 又缺少执行证据。后续机制评估必须使用并行的 `semantic_error_class` 和 `semantic_subcategory`，不能只按该控制流子类计数。

#### 3.3 聚合与排序：93 条记录

其中 82 条是聚合/分组不匹配，11 条是排序方向或排序范围不匹配。可能形成机制包括：

- 没有先定义统计对象和结果粒度；
- 把全局统计写成按实体分组，或把按实体统计写成全局聚合；
- 混淆 `COUNT(*)`、`COUNT(column)` 与 `COUNT(DISTINCT column)`；
- 多阶段聚合只完成一层；
- 混淆聚合前 `WHERE` 与聚合后 `HAVING`；
- Top-K 使用错误排序字段、方向或 `LIMIT` 范围。

Run1 和 Run2 分别出现 45 和 48 条，数量接近，说明这是稳定的基线瓶颈。后续应测试题目级结构化查询计划，明确统计对象、分组键、聚合函数和排序字段，而不是只增加通用聚合提醒。

#### 3.4 过滤范围与表达式：67 条记录

这类 SQL 通常可以执行，但结果与 gold 不同，自动结构规则没有发现更明确的表、列数或聚合差异。可能原因包括：

- 比较运算符和区间边界错误；
- 日期、年份或时间窗口范围错误；
- 条件作用在错误层级；
- `AND`、`OR` 或括号范围错误；
- 百分比、单位换算、字符串标准化或 NULL 处理错误；
- 问题、Hint 与 gold 存在歧义或噪声。

该类别置信度最低。Run1/Run2 分别为 33/34，数量稳定，但不能将全部记录直接认定为 Agent 错误；应抽样核查问题、Hint、predicted SQL、gold SQL 和真实结果后，再决定是否需要值检索、条件计划或数据集噪声隔离。

#### 3.5 输出契约：56 条记录

48 条输出列数不匹配，8 条混淆 YES/NO 与逐行输出。可能形成机制包括：

- 生成 SQL 前没有明确输出列数、顺序和每列语义；
- 只返回统计值，遗漏名称、年份等描述列；
- 把排序或 Join 使用的辅助列放入最终输出；
- 把存在性问题回答成记录列表，或反过来；
- train few-shot 的输出形状与当前问题不一致，模型错误模仿。

该类错误不依赖递归即可检测。优先候选是生成前的结构化输出契约，以及只检查列形状和回答形式的确定性校验。

#### 3.6 Schema 与 Join：38 条记录

预测 SQL 与 gold SQL 的表集合或 Join 路径不同。可能形成机制包括：

- 选错名称相近但业务含义不同的表或字段；
- 遗漏承载实体、过滤条件或关联关系的表；
- 外键路径不完整；
- 多对多 Join 产生重复行并污染聚合；
- 当前 Schema 信息没有转化成题目级字段来源与 Join 计划。

这一类应由 metadata、Join path 检索或结构化 Schema linking 实验处理，不能用聚合模式或 FINAL 控制解决。

#### 3.7 运行、解析和工具问题：5 条

| 运行 | ID | 已确认问题 |
|---|---|---|
| Run1 | `bird_959` | `predicted_sql` 为空 |
| Run2 | `bird_1524` | `predicted_sql` 为空 |
| Run2 | `bird_189` | execution observation 无法解析 |
| Run2 | `bird_897` | Azure/LiteLLM API 错误，无 assistant 输出 |
| Run2 | `bird_959` | Azure/LiteLLM API 错误，无 assistant 输出 |

这些记录不用于证明 Prompt、Offline、Planner 或递归机制有效，但正式准确率仍保留全部题目。机制比较时可额外报告排除不可归因运行失败后的参考指标。

#### 3.8 SQL 改写行为

两次运行的 215 条 `UNVERIFIED_FINAL` 中，75 条最终 SQL 只修改表达式或投影，19 条改变表集合，其余多项同时修改 `WHERE`、`GROUP BY`、`HAVING`、`ORDER BY`、`LIMIT` 或聚合结构；9 条在没有任何先前 `db.execute` 的情况下直接提交。对 180 条“错误 observation 后改写未执行”的主要子集，67 条只修改表达式或投影，另外 113 条包含至少一种可观察的结构改写。

这说明 E0 的失败不只是“忘记执行最后 SQL”。许多轨迹已经发现旧 SQL 可能有问题并做出实质性修改，但缺少稳定的题目级约束来判断修改方向是否符合问题的聚合粒度、输出形状、Join 路径和过滤范围。数据库返回正常行只能证明 SQL 可执行，不能证明它回答了问题。

#### 3.9 稳定失败的根因

124 道题在两次运行中都失败。其中：

- 110/124（88.71%）保持相同语义大类；
- 107/124（86.29%）保持相同语义子类；
- 相同大类中，聚合 41、过滤语义 28、输出契约 25、Schema/Join 16。

只有 14 道稳定失败题在两次运行间切换语义大类或包含不可归因运行错误。这说明 E0 的主要失败不是随机波动，而是会跨运行重复的结构性问题。后续实验应优先报告这 124 题中恢复了多少，并检查恢复是否集中在目标错误类别。

两次运行之间的 11 道不稳定题也有明确方向：

- Run1 错、Run2 对：4 题，原因为过滤语义 1、Schema/Join 2、输出契约 1；
- Run1 对、Run2 错：7 题，原因为聚合 4、过滤语义 3。

净退化主要来自聚合和过滤语义，说明只比较单次总分容易把生成波动误判为机制收益。

#### 3.10 E0 与 E3-A 的错误迁移

E3-A 相比 E0 Run1 恢复 8 题、回退 4 题；相比 Run2 恢复 10 题、回退 3 题。恢复题的 E0 原因主要是过滤语义（4/5 条）和聚合（3/4 条），但 E3-A 的总体失败分布为聚合 47、输出 29、过滤语义 24、Schema/Join 20。

与 E0 单次范围比较：

- 聚合：E0 为 45-48，E3-A 为 47，没有明确下降；
- 输出契约：E0 为 27-29，E3-A 为 29，没有明确下降；
- Schema/Join：E0 为 18-20，E3-A 为 20，没有明确下降；
- 过滤语义：E0 为 33-34，E3-A 为 24，出现较明显下降。

因此 E3-A 的 +2.79 pp 探索性提升不能解释为通用模式已经解决聚合、输出和 Schema 问题；当前更符合证据的解释是，它可能减少了部分过滤/表达式错误，同时对其他目标类别没有稳定净改善。该判断已由 E3-B 的逐题配对复核进一步验证：patterns 替代 few-shot 未带来收益。

#### 3.11 归因置信度与边界

| 归因 | 置信度 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| API、空 FINAL、未执行 FINAL | 高 | trace 中存在明确控制状态 | 不能说明正确 SQL 应如何构造 |
| 输出列数、表集合、聚合结构 | 中 | predicted 与 gold 存在结构差异 | 不保证 gold 是唯一合理写法 |
| 过滤范围或表达式 | 低 | 执行答案不同且没有更具体结构差异 | 不能排除 gold 噪声 |
| 模型隐藏推理原因 | 不可恢复 | 无 | trace 无法恢复模型未输出的思考 |

gold 仅用于运行后诊断，不进入 Agent、Prompt、few-shot 检索或在线决策。

### 3.12 失败形成机制与实验判断

1. **主要瓶颈是题目级语义构造，不是 FINAL 格式。** 180 条主要控制流样本中，最近一次执行的 SQL 已经答错；strict verified-final 只能要求重新执行，不能提供正确的聚合粒度、输出列、Join 路径或过滤条件。
2. **聚合、过滤和输出契约构成 E0 的主要失败。** 三类合计 216/259 条失败记录，占 83.40%；其中聚合在两次运行中分别为 45 和 48 条，说明它不是单次随机波动。
3. **同一错误会跨运行重复。** 124 道稳定失败题中有 110 道保持相同语义大类，后续机制必须优先报告这些稳定失败的 recovered、regressed 和净变化。
4. **不同错误必须匹配不同机制。** 聚合与输出优先测试题目级 QueryPlan/输出契约；Schema/Join 优先测试 metadata 与路径检索；过滤语义应先人工复核低置信度样本；运行和 observation 问题由基础设施处理。
5. **E0 只能作为探索性基线。** 两次运行存在 SQL timeout 配置差异，34.26% 均值和 0.76% 总体标准差不能当作严格统计置信区间；后续判断应同时参考单次范围和逐题配对迁移。
6. **控制流标签不作为机制接受指标。** `UNVERIFIED_FINAL` 应保留为诊断字段，但 E1 已表明强制 verified-final 会增加成本且没有恢复 E0 稳定失败，因此不安排独立 FINAL 同步实验。

### 3.13 错误到改进机制映射

本表只使用两次 E0 的全部 259 条失败记录及其互斥 `semantic_error_class + semantic_subcategory`。各行计数总和为 `82 + 11 + 67 + 48 + 8 + 38 + 5 = 259`。124 道稳定失败及其中 110 道同大类重复用于后续实验的二级接受指标，不与 259 条运行级记录混在“当前证据”列中。

| 语义分类 | 具体归因 | 数量 | 占 259 | 主要改进机制 | 对应实验 | 接受条件 |
|---|---|---:|---:|---|---|---|
| `AGGREGATION_REASONING` | `aggregation_or_grouping_mismatch`：统计对象、grain、`GROUP BY`、聚合函数、聚合前后过滤或多阶段聚合错误 | 82 | 31.66% | Root 在生成 SQL 前显式记录统计对象、粒度、分组键、aggregate、`WHERE/HAVING` 和阶段依赖 | `E4-A`；只有仍存在可独立 SubPlan 时才进入 `E6-A/E6-B` | 该子类净下降；目标 recovered > regressed；稳定聚合失败有可解释恢复，且不增加 Schema/输出回退 |
| `AGGREGATION_REASONING` | `sort_direction_or_order_scope_mismatch`：排序字段、方向、Top-K 范围或 `LIMIT` 作用阶段错误 | 11 | 4.25% | QueryPlan 明确排序对象、指标、方向、tie 和 `LIMIT` 应在聚合后的哪一层执行 | `E4-A` | 该 11 条对应结构的回退少于恢复；不能通过改变输出粒度制造表面改善 |
| `SEMANTIC_REVIEW_REQUIRED` | `filter_scope_or_expression_mismatch`：比较符、边界、日期范围、AND/OR、NULL、单位、值格式或作用层级不一致；包含潜在 gold 歧义 | 67 | 25.87% | 先人工区分 Agent 错误与 gold/问题歧义；再用 Offline 值语义与题目级条件结构明确字段、运算符、值、范围和层级 | `F-Audit` → `E3-C` / `E4-A`；必要时 `E5-B` 按需查值 | 只在人工确认的 Agent 错误上计算净变化；疑似 gold 噪声单列，不能计作机制收益 |
| `OUTPUT_CONTRACT` | `output_column_count_mismatch`：缺少请求列、增加辅助列、多问题只回答一部分或列顺序/含义错误 | 48 | 18.53% | 在 QueryPlan 中冻结 answer type、列数、列顺序、来源与含义，并检查最终投影是否一致 | `E4-A` | 该子类净下降且 recovered > regressed；不得以牺牲聚合粒度或 Schema 正确性换取列数匹配 |
| `OUTPUT_CONTRACT` | `yes_no_vs_row_output_mismatch`：条件标量与记录列表相互混淆 | 8 | 3.09% | 在生成 SQL 前分类回答形式：boolean/scalar/rows，并固定 YES/NO 与逐行输出边界 | `E4-A` | 8 条目标结构恢复多于回退，且不把普通比较题错误转换为 YES/NO |
| `SCHEMA_LINKING` | `table_or_join_path_mismatch`：表选择、字段归属、直接/多跳 Join path 或 Join 重复行风险错误 | 38 | 14.67% | 用 Offline Schema Context 提供字段语义、PK/FK、关系基数、候选路径和值格式，并只交付当前题相关片段 | `E3-C` | 该子类净下降；稳定 Schema 失败 recovered > regressed；不能因 Join 重复显著增加聚合错误，片段覆盖与 artifact hash 完整记录 |
| 无可用语义标签 | 运行、解析或工具失败：API、空 FINAL、observation 不可解析或空结果，无法可靠归因到 SQL 语义 | 5 | 1.93% | 结构化 observation、受控重试、断点续跑、终止原因和运行/语义错误分离 | `E2-A`（基础设施） | 运行失败减少且 trace 可完整归因；这类恢复单独报告，不计作推理机制收益 |

`UNVERIFIED_FINAL` 的 215 条是与上述语义分类并行的控制流标签，其中 180 条最近执行 SQL 已经错误；若把它加入本表会与 259 条语义记录重复计数。因此它只保留为控制流诊断，不安排独立 FINAL 同步实验，也不作为机制成功指标。

由全部 259 条归因得到的直接顺序是：先用 `E2-A` 保证 5 条运行问题可观测；用 `E3-C` 处理 38 条 Schema/Join 及部分值语义；用 `F-Audit` 澄清 67 条低置信度过滤归因；再用 `E4-A` 直接处理 82 条聚合/分组、11 条排序、48 条输出列和 8 条回答形式错误。E5/E6 只有在前述直接机制完成后、剩余轨迹显示信息访问或可分解 SubPlan 是瓶颈时才启用，不能直接从 E0 的 259 条计数宣称有效。

### 4. 成本与延迟基线

两次平均约为 13,570 tokens/题、2.74 次 LLM 调用/题、1.90 次 DB 调用/题和 41.80 秒/题。
Run1/Run2 分别存在 9/11 次 usage 缺失，因此 token 均值是已记录调用的下界。
后续机制除了比较准确率，也要报告相对这些成本指标的变化。

## 结论

E0 可以作为探索性 Root 基线，但不能宣称是严格同协议的稳定最终结果。后续完整实验使用相同 197 题，并同时比较：

1. 总准确率相对 E0 两次均值 34.26% 和单次范围 33.50%-35.03% 的变化；
2. 124 道稳定失败题的恢复数量；
3. 259 条失败的 7 个互斥语义子类分别发生多少 recovered、regressed 与净变化：聚合/分组 82、排序 11、过滤 67、输出列数 48、YES/NO 形式 8、Schema/Join 38、运行问题 5；
4. token、LLM 调用、DB 调用和延迟成本；
5. API、解析和 trace 问题是否被错误计入机制收益。

由全部 259 条失败得到的机制映射为：

| E0 失败归因 | 直接机制 | 实验顺序 |
|---|---|---|
| 5 条运行、解析或工具问题 | 结构化 observation、重试、断点续跑和终止原因 | `E2-A`，只作为基础设施 |
| 38 条 Schema/Join 错误 | Offline Schema Context、字段语义、PK/FK、关系基数和相关片段选择 | `E3-C` |
| 67 条过滤范围/表达式错误 | 先区分 Agent 错误与 gold 歧义；再结合值语义和题目级条件结构 | `F-Audit` → `E3-C` / `E4-A`，必要时 `E5-B` |
| 82 条聚合/分组错误 | 显式统计对象、grain、分组键、聚合函数、`WHERE/HAVING` 与阶段依赖 | `E4-A`；只有剩余问题存在可分 SubPlan 才进入 `E6` |
| 11 条排序错误 | 显式排序指标、方向、Top-K、tie 和 `LIMIT` 层级 | `E4-A` |
| 48 条输出列数错误 | 固定 answer type、列数、顺序、来源和投影检查 | `E4-A` |
| 8 条 YES/NO 与逐行输出错误 | 在生成 SQL 前固定 boolean/scalar/rows 回答形式 | `E4-A` |

E3-B 已完成对 train-only patterns 替代 train few-shot 的判断，结果为负，因此它只作为消融证据，不改变上述错误到机制的映射。`UNVERIFIED_FINAL` 是与 259 条语义分类并行的控制流标签，不单独驱动实验。E5/E6 只有在 E3-C、F-Audit 和 E4-A 后的剩余轨迹分别证明“上下文访问”或“可分解子计划”是瓶颈时才启用。
