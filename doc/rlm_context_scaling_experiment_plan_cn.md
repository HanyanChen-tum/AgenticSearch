# RLM 在大规模数据库上下文中的实验计划

## 1. 研究背景

当前项目最初研究的问题是：在 Text-to-SQL agent 中加入 RLM 式递归分解，是否能够直接提高 SQL 执行准确率。

已有 BIRD Mini-Dev 实验表明：

| 方法 | 样本数 | 正确数 | 执行准确率 | 平均延迟 |
|---|---:|---:|---:|---:|
| metadata + enrichment + probe，no-RLM | 50 | 31 | 62% | 2.4938 秒 |
| metadata + enrichment + probe，RLM | 50 | 29 | 58% | 3.2419 秒 |

逐题配对结果为：

| 配对结果 | 样本数 |
|---|---:|
| 两种方法都正确 | 29 |
| 仅 no-RLM 正确 | 2 |
| 仅 RLM 正确 | 0 |
| 两种方法都错误 | 19 |

在当前小规模数据库场景下，RLM 没有表现出准确率收益，反而增加了模型调用次数和延迟。这并不能证明 RLM 在所有 Text-to-SQL 场景中无效，但说明“加入递归后是否普遍提高 agent 准确率”不是合适的主要研究问题。

RLM 更核心的价值在于通过递归调用、局部读取和中间结果聚合管理超长上下文。与此同时，AutoLink 将大规模 schema linking 建模为 agent 驱动的迭代探索过程，并在不同数据库规模上比较 schema recall、SQL 执行准确率和 token 消耗。其结果表明，方法间的差异主要在大型 schema 中出现，而普通 BIRD 数据库平均规模较小。因此，本项目后续应将实验重点转向上下文规模，而不是继续增加普通 agent 功能。

参考资料：

- [AutoLink: Autonomous Schema Exploration and Expansion for Scalable Schema Linking in Text-to-SQL at Scale](https://ojs.aaai.org/index.php/AAAI/article/download/40672/44633)
- [AutoLink 代码仓库](https://github.com/wzy416/AutoLink)

## 2. 新的研究问题

主研究问题调整为：

> 当数据库 schema 规模增长或模型上下文预算受限时，RLM 式递归上下文分解是否比非递归 agent 更能保持 Text-to-SQL 的准确率，并降低一次性输入完整上下文的成本？

该问题进一步拆分为：

1. 数据库 schema 规模增大时，RLM 和 no-RLM 的执行准确率分别如何变化？
2. 在相同初始 schema retrieval 结果下，RLM 能否找回遗漏的必要表和列？
3. 在固定 token 或上下文预算下，RLM 是否具有更好的准确率—成本权衡？
4. RLM 的收益是否只出现在大型 schema、低 `top-k` 或复杂 SQL 中？
5. RLM 的递归分解是否优于非递归 agent 的迭代 schema exploration？

## 3. 研究假设

### H1：低上下文压力下无收益

在小型 schema 或初始检索已经覆盖全部必要字段时，RLM 不会显著提高准确率，并可能增加延迟和 token 消耗。

### H2：高上下文压力下退化更慢

随着 schema 列数增加，full-schema 和普通 retrieval 方法的准确率会下降；RLM 的准确率下降速度应更慢。

### H3：初始召回不足时收益更明显

当初始 `top-k` 较小时，RLM 可通过递归探索找回遗漏的相关表和列，因此提升 Strict Schema Recall 和 Execution Accuracy。

### H4：收益存在成本边界

如果 RLM 只能通过显著增加 token、模型调用和延迟换取很小的准确率提升，则不能认为其具有实际优势。

## 4. 与 AutoLink 的关系及差异

AutoLink 已经研究了 agent 驱动的 schema 检索、探索和验证，不能简单重复“agent 按需探索大型 schema 是否有效”。

本项目应突出以下差异：

| 方面 | AutoLink | 本项目 |
|---|---|---|
| 核心对象 | 迭代式 schema linking agent | RLM 递归上下文分解 |
| 主要对照 | 不同 schema linking 方法 | 同一 agent 的 no-RLM 与 RLM |
| 唯一核心变量 | action 组合、初始 top-n | 是否允许递归子问题调用 |
| 重点 | 找到高召回、低噪声 schema | 递归是否改善上下文规模扩展能力 |
| 结论目标 | agent exploration 可扩展 | recursion 相对非递归 exploration 的增量价值 |

为了建立有效贡献，实验必须包含“非递归迭代探索 agent”这一强基线。否则，RLM 的效果可能只是工具探索带来的，而不是递归机制本身带来的。

## 5. 数据集与上下文规模

### 5.1 数据集

实验分两个阶段：

| 阶段 | 数据集 | 用途 |
|---|---|---|
| Pilot | BIRD Mini-Dev | 验证代码、指标和小规模负结果 |
| Main | BIRD-Dev、Spider 2.0-Lite | 验证真实大型 schema 下的可扩展性 |

BIRD 可用于保持与已有结果连续，但主结论不能只依赖 BIRD Mini-Dev。大型 schema 实验应优先使用 Spider 2.0-Lite 或其他真实企业级 Text-to-SQL 数据集。

### 5.2 Schema 规模定义

数据库规模以 schema 中的列数作为主变量，表数和 schema token 数作为辅助变量。建议沿用便于和 AutoLink 比较的分桶：

| 规模组 | 列数 |
|---|---:|
| S1 | `<100` |
| S2 | `100–500` |
| S3 | `500–1500` |
| S4 | `1500–3000` |
| S5 | `>3000` |

每个样本必须记录：

- 数据库表数；
- 数据库列数；
- 完整 schema 的 token 数；
- 问题 token 数；
- gold SQL 涉及的表数和列数；
- SQL 难度或结构特征。

如果某个规模组样本不足，应合并相邻分桶或补充数据集，不能依靠复制无关 schema 文本制造大量伪样本。

### 5.3 受限上下文实验

除真实 schema 规模外，再设置固定上下文预算：

```text
2K / 4K / 8K / 16K tokens
```

这里的预算应约束所有进入模型的 schema、工具观察和递归返回内容。不能只截断初始 prompt，却允许 RLM 通过工具无限读取，否则比较不公平。

## 6. 实验方法

### 6.1 核心对照组

| 编号 | 方法 | 描述 |
|---|---|---|
| M1 | Full Schema | 将可容纳的完整 schema 一次性提供给 SQL generator |
| M2 | Top-k Retrieval | 检索相关表列后直接生成 SQL |
| M3 | Non-recursive Exploration | agent 可检索、查 schema、采样和执行 SQL，但不能创建递归子问题 |
| M4 | RLM Exploration | 与 M3 使用相同工具和预算，额外允许递归子问题调用 |
| M5 | Oracle Schema | 仅提供 gold SQL 所需 schema，作为 SQL generator 上限 |

M3 与 M4 是回答核心研究问题的严格配对实验。两者必须固定：

- 相同数据及样本顺序；
- 相同主模型；
- 相同 prompt family；
- 相同 temperature；
- 相同初始 retrieval；
- 相同 metadata、enrichment 和 probe；
- 相同最大交互轮数；
- 相同总 token 或模型调用预算；
- 相同 SQL generator 和 evaluator；
- 唯一变量为 recursion 开关。

### 6.2 上下文规模矩阵

主实验采用以下因子设计：

```text
方法：
M1 / M2 / M3 / M4 / M5

Schema 规模：
S1 / S2 / S3 / S4 / S5

初始 retrieval top-k：
5 / 20 / 50 / 100

上下文预算：
2K / 4K / 8K / 16K
```

完整笛卡尔积成本较高，因此分阶段执行：

1. 固定 8K 上下文，比较所有 schema 规模和方法；
2. 在 S1、S3、S5 中比较不同上下文预算；
3. 在 M3、M4 中比较不同 `top-k`；
4. 只对出现明显差异的配置扩展到完整数据。

### 6.3 RLM 子问题设计

RLM 子问题应围绕上下文拆分，而不是笼统要求子 agent 重新解决整道题。允许的典型任务包括：

- 找出与实体或指标相关的候选表；
- 验证候选列的真实值格式；
- 查找两个候选表之间的 join path；
- 独立分析一个聚合或时间条件；
- 对局部 schema 生成结构化证据。

子 agent 返回内容应结构化并限制长度，例如：

```json
{
  "relevant_tables": [],
  "relevant_columns": [],
  "join_evidence": [],
  "value_evidence": [],
  "confidence": 0.0
}
```

根 agent 负责合并证据并生成最终 SQL。必须记录递归深度、子问题数量、每个子问题的输入输出 token 和实际使用情况。

## 7. 评价指标

### 7.1 主要指标

| 指标 | 含义 |
|---|---|
| Execution Accuracy（EX） | 预测 SQL 与 gold SQL 执行结果是否一致 |
| Strict Schema Recall（SRR） | 返回 schema 是否完整覆盖 gold SQL 所需表和列 |
| Average Total Tokens | 每题所有主调用和递归调用的输入、输出 token 总和 |

### 7.2 辅助指标

- Table Recall、Column Recall；
- 最终 linked schema 的列数；
- schema 压缩率；
- 平均延迟和 P95 延迟；
- LLM 调用次数；
- DB 工具调用次数；
- 递归调用次数和最大深度；
- 无效递归率；
- SQL 语法错误率；
- 每正确一题的平均 token 成本。

Schema 压缩率定义为：

```text
1 - linked_schema_columns / full_schema_columns
```

### 7.3 可扩展性指标

对每种方法绘制三条主要曲线：

1. Schema 列数与 EX；
2. Schema 列数与 SRR；
3. Schema 列数与平均 token。

主要关注 RLM 相对 no-RLM 的性能退化斜率，而不仅是总体平均准确率。

## 8. 统计分析

所有方法必须在相同样本上配对比较。

对于 M3 与 M4，报告：

- 两者都正确；
- 仅 no-RLM 正确；
- 仅 RLM 正确；
- 两者都错误；
- 准确率绝对差和相对差；
- McNemar 检验；
- paired bootstrap 95% 置信区间。

对每个 schema 规模分桶分别报告上述指标。主结论应基于完整测试集和置信区间，不能只根据 50 条 pilot 的百分比作出。

若模型输出存在随机性，正式实验建议至少运行 3 个随机种子；如果成本不足，则使用 temperature 0、固定样本顺序，并明确实验是单次确定性评估。

## 9. 消融实验

在确认 M4 至少一个大型 schema 分组优于 M3 后，再进行以下消融：

| 消融 | 目的 |
|---|---|
| 去掉 recursive schema retrieval | 判断收益是否来自递归检索 |
| 去掉 join-path 子问题 | 判断 join 推理贡献 |
| 去掉 value probe 子问题 | 判断真实值验证贡献 |
| 限制递归深度为 1/2/3 | 确定深度—成本关系 |
| 限制子问题数为 1/2/4 | 确定调用预算 |
| 改变返回证据长度 | 判断上下文压缩效果 |
| 相同调用预算下的 no-RLM | 排除“只是多调用模型”的解释 |

不要在主效应尚未出现前继续堆叠大量功能消融。

## 10. 错误分析

错误类型至少包括：

- 必要表遗漏；
- 必要列遗漏；
- 引入过多无关 schema；
- join path 错误；
- value grounding 错误；
- aggregation 错误；
- filter/time condition 错误；
- SQL 方言或语法错误；
- 子 agent 返回错误证据；
- 根 agent 未使用正确子证据；
- 递归调用浪费或重复。

重点比较以下两类样本：

1. no-RLM 错、RLM 对：确认 RLM 是否通过上下文探索找回了必要信息；
2. no-RLM 对、RLM 错：确认递归是否引入错误证据、覆盖正确判断或造成上下文噪声。

## 11. 实施计划

### 阶段 A：补齐测量基础

1. 为所有 LLM 调用统一记录 input/output token；
2. 为结果增加表数、列数、schema token 数；
3. 从 gold SQL 提取 gold tables 和 gold columns；
4. 实现 SRR、Table Recall、Column Recall；
5. 记录递归调用轨迹和累计成本；
6. 实现按 schema 规模分桶的评估脚本。

验收条件：任意结果文件都能生成 EX、SRR、token 和规模分桶报告。

### 阶段 B：BIRD Pilot

1. 复现现有 50 条 no-RLM/RLM 对照；
2. 增加 Full Schema、Top-k Retrieval 和 Oracle Schema；
3. 测试 `top-k = 5/20/50`；
4. 验证预算控制和报告格式。

验收条件：严格对照除 recursion 外无其他配置差异，逐题配对结果可复查。

### 阶段 C：大型 Schema 主实验

1. 准备 Spider 2.0-Lite；
2. 统计数据库规模分布；
3. 先在每个分桶抽取少量样本做 smoke test；
4. 运行 M1–M5 的主实验；
5. 绘制 EX、SRR 和 token 的规模曲线。

验收条件：每个有效规模组都有足够样本，且不存在大规模系统性执行失败。

### 阶段 D：针对性消融与错误分析

仅在主实验发现 RLM 在某些规模或预算下有收益时进行。根据收益所在区域选择递归深度、子问题类型和证据长度消融。

### 阶段 E：最终验证

1. 对关键配置运行完整测试集；
2. 计算置信区间和显著性；
3. 复查失败样本；
4. 固化环境、模型、prompt 和结果；
5. 整理论文表格与图。

## 12. 预期论文表格与图

### 表 1：总体结果

| Method | EX | SRR | Avg. Linked Columns | Avg. Tokens | Avg. Calls | Latency |
|---|---:|---:|---:|---:|---:|---:|

### 表 2：严格 RLM 配对结果

| Schema Size | no-RLM EX | RLM EX | no-RLM Only | RLM Only | ΔEX | 95% CI |
|---|---:|---:|---:|---:|---:|---:|

### 表 3：固定预算结果

| Budget | Method | EX | SRR | Tokens | Budget Violations |
|---:|---|---:|---:|---:|---:|

### 图 1：Schema 规模—EX 曲线

横轴为 schema 列数分桶，纵轴为 EX，绘制 M1–M4。

### 图 2：Schema 规模—SRR 曲线

横轴为 schema 列数分桶，纵轴为 SRR。

### 图 3：准确率—成本 Pareto 图

横轴为平均 token，纵轴为 EX，判断 RLM 是否位于更优的 Pareto 前沿。

## 13. 成功标准与停止条件

### 支持 RLM 的结果

满足以下条件时，可认为 RLM 在大型数据库上下文中具有价值：

1. 在 S4/S5 或受限预算下，RLM 的 EX 或 SRR 明显优于 no-RLM；
2. 配对差异置信区间不跨 0，或在多个规模组中趋势一致；
3. 提升不能仅由更多模型调用解释；
4. token 和延迟成本处于可接受范围；
5. 错误分析证明收益来自找回必要上下文。

### 不支持 RLM 的结果

出现以下结果时，应接受负结论并停止继续增加递归模块：

1. 大型 schema 下 RLM 仍无准确率或 SRR 提升；
2. 收益完全可以由相同预算的非递归 agent 复现；
3. 极小提升需要数倍 token 或延迟；
4. 递归主要增加错误传播和无效探索。

对应的有效负结论是：

> 在 Text-to-SQL schema exploration 中，递归本身不提供稳定增益；有效因素是检索质量、数据库 grounding 和迭代验证。

## 14. 风险与控制

| 风险 | 控制措施 |
|---|---|
| 与 AutoLink 研究问题重复 | 聚焦 recursion 相对 non-recursive exploration 的增量价值 |
| BIRD schema 太小 | 使用 Spider 2.0-Lite 作为主实验 |
| 人工扩展 schema 不真实 | 优先真实大型数据库；人工扩展只作为受控压力测试 |
| RLM 获得更多调用预算 | 增加相同 token/调用预算的 no-RLM 对照 |
| Prompt 不一致 | 两组使用同一 prompt family，仅动态暴露递归工具 |
| API 随机性 | temperature 0、固定模型版本、记录种子和运行时间 |
| Token 统计缺失 | 在正式实验前统一所有调用的 usage 记录 |
| 成本过高 | 先分桶 pilot，再扩展显著配置 |

## 15. 最小可行实验

若时间和预算有限，最少完成以下实验：

1. BIRD 小规模组和 Spider 2.0-Lite 大规模组；
2. Top-k Retrieval、Non-recursive Exploration、RLM Exploration；
3. `top-k = 5/50`；
4. 固定相同模型和总调用预算；
5. 报告 EX、SRR、token 和 paired comparison；
6. 绘制 schema 规模—EX 与 schema 规模—SRR 两张图。

这个最小实验已经能够回答：

> RLM 的价值是否只在上下文压力增大时出现，以及该价值是否来自递归机制而非一般的 agent exploration。

## 16. 当前下一步

在继续调用模型之前，应按以下顺序推进：

1. 完成 gold schema 提取和 SRR evaluator；
2. 为现有结果补充 schema 规模与 token 统计；
3. 评估 Spider 2.0-Lite 的获取、数据库执行和方言兼容成本；
4. 实现相同预算的 no-RLM/RLM runner；
5. 每个 schema 分桶先运行 10–20 条；
6. 根据 pilot 决定正式实验矩阵。

现有 50 条严格对照保留为 S1/低上下文压力下的 pilot 负结果，不再把它解释为对 RLM 普遍有效性的最终判断。
