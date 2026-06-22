# Spider 1.0 实验记录与结果分析

## 1. 实验目标

本实验在 Spider 1.0 的 SQLite 开发集上比较四种 Text-to-SQL 方法：完整 Schema 直接生成、检索 Schema 后直接生成、非递归数据库代理，以及带递归接口的 DB-RLM。核心问题是：数据库工具调用和递归分解能否提升 SQL 的执行准确率，并且这种提升是否值得额外的延迟、Token 和工具调用成本。

本文只描述当前仓库中的真实实现和 `results/spider1_full_dev/` 中保存的完整实验结果。当前代码中的 `RecursiveDBRLM` 是项目自研的递归数据库代理，不是 MIT RLM 类的子类，也没有使用 RestrictedPython REPL。

## 2. 数据集与实验配置

### 2.1 数据集

- 数据集：Spider 1.0
- 评测划分：完整 dev 集
- 问题数：1,034
- SQLite 数据库数：166
- 训练集：7,000 条，仅完成格式转换，没有用于本次评测
- 问题文件：`data/processed/dev_questions.json`
- 数据库目录：`data/databases/{db_id}/{db_id}.sqlite`

本实验的主要指标是执行准确率，即分别执行预测 SQL 和标准 SQL，并比较结果集合。结果比较忽略行顺序，但保留重复行数量和 SQLite 返回值类型，因此整数 `1` 与字符串 `"1"` 不会被错误地视为相同。

### 2.2 模型配置

完整实验使用本地 Ollama 的 OpenAI-compatible 接口：

```dotenv
LLM_PROVIDER=openai_compatible
MODEL=qwen2.5-coder:7b
LLM_BASE_URL=http://localhost:11434/v1
TEMPERATURE=0
MAX_TOKENS=1024
```

### 2.3 统一评测指标

- Execution Accuracy：预测 SQL 与标准 SQL 的执行结果是否相同
- SQL Valid Rate：预测 SQL 能否成功执行
- Exact Match：规范化后的预测 SQL 是否与标准 SQL 完全一致
- Component Match：表、列、Join 和聚合组件是否全部匹配
- Latency：每题平均耗时
- Token Usage：总输入和输出 Token
- Tool Calls：数据库工具调用总数与平均值
- Failure Type：`invalid_sql`、`wrong_table`、`wrong_join`、`wrong_aggregation` 或 `wrong_result`

## 3. Baseline 设计

### 3.1 Baseline 1：完整 Schema 直接生成

实现文件：`spider1_experiments/baselines/baseline_1_direct_llm_schema.py`

流程：

```text
用户问题 + 完整数据库 Schema
              ↓
          单次 LLM 调用
              ↓
           预测 SQL
```

模型可以看到当前数据库的全部表、列、主键和外键，但不能查看表内容，不能在生成阶段执行 SQL，也没有自动修复。这一方法用于衡量“一次性提供完整结构”能达到的效果。

### 3.2 Baseline 2：Schema 检索后直接生成

实现文件：`spider1_experiments/baselines/baseline_2_direct_text_to_sql.py`

该方法先根据问题与表名、列名之间的词法重合度排序，再选择最相关的 Schema：

- 最多选择 5 张表
- 每张表保留最多 8 个高相关列
- 额外保留主键和外键列，避免破坏必要的 Join 路径
- 不读取表数据
- 不执行中间 SQL
- 最终仍然只有一次 LLM 生成

流程：

```text
用户问题
   ↓
词法 Schema 检索
   ↓
相关表、列、主外键
   ↓
单次 LLM 调用
   ↓
预测 SQL
```

这一方法用于检验：减少无关 Schema 是否比把完整 Schema 全部交给模型更有效。

### 3.3 Baseline 3：非递归数据库代理

实现文件：`spider1_experiments/baselines/baseline_3_non_recursive_db_agent.py`

模型最多进行 8 步交互，每一步输出一个 JSON 动作。可用工具包括：

- `SHOW_TABLES`
- `DESCRIBE_TABLE`
- `SAMPLE_ROWS`
- `EXECUTE_SQL`
- `FINAL`

模型可以探索 Schema、查看少量数据、执行候选 SQL 并根据数据库反馈继续推理，但不能创建子代理。若达到最大步数仍未输出 `FINAL`，运行器会退回到最后一条成功执行的 SQL。

这一方法用于区分“工具探索带来的收益”和“递归分解带来的收益”。

## 4. DB-RLM 的实际实现

### 4.1 总体结构

DB-RLM 由四个主要组件组成：

```text
问题
 ↓
RecursiveDBRLM
 ↓
根 SubquestionAgent ──可选──> 子 SubquestionAgent
 ↓                              ↓
数据库观察与候选 SQL         子问题证据
 └──────────────┬───────────────┘
                ↓
          最终 SQL 合成
                ↓
          执行与一次修复
```

对应文件：

- `ours/db_environment.py`：只读 SQLite 工具层
- `ours/recursive_controller.py`：递归深度、全局预算和 Trace
- `ours/subquestion_agent.py`：单个任务/子任务代理
- `ours/recursive_db_rlm.py`：根流程、SQL 合成、修复和批量评测

实际代码位于 `spider1_experiments/ours/`。

### 4.2 DatabaseEnvironment

`DatabaseEnvironment` 使用 SQLite URI 的 `mode=ro` 只读连接，暴露以下能力：

- `list_tables()`：列出业务表
- `describe_table()`：读取列、主键和外键
- `sample_rows()`：读取受限数量的样例行
- `execute_sql()`：执行中间只读 SQL，最多返回配置允许的行数
- `execute_sql_full()`：执行最终 SQL并返回完整结果

中间 SQL 只允许以 `SELECT`、`WITH` 或 `EXPLAIN` 开头。表名在执行 PRAGMA 或采样前会经过存在性检查和标识符转义。

### 4.3 RecursiveController

控制器维护所有代理共享的全局状态：

- 最大递归深度：2
- 全局最大动作数：24
- 每个代理最大动作数：8
- 每个代理最大子代理数：3
- Token 预算：12,000
- 中间观察最大长度：5,000 字符
- 中间查询最大返回行数：20
- 最终 SQL 修复次数：1

每个动作都会记录 `agent_id`、深度、动作、参数和观察结果，形成完整 Trace。父代理和所有子代理共享动作与 Token 预算，防止递归无限扩张。

### 4.4 SubquestionAgent

每个代理处理一个明确任务，并在每轮选择一个 JSON 动作：

```json
{"action":"list_tables","arguments":{}}
{"action":"describe_table","arguments":{"table":"table_name"}}
{"action":"sample_rows","arguments":{"table":"table_name","limit":5}}
{"action":"execute_sql","arguments":{"sql":"SELECT ..."}}
{"action":"spawn_subagent","arguments":{"task":"一个更窄的独立子问题"}}
{"action":"finish","arguments":{"summary":"证据总结","candidate_sql":"可选 SQL"}}
```

当模型选择 `spawn_subagent` 时，父代理先占用一次动作预算，再递归调用同一个 `SubquestionAgent.run()`。子代理获得父任务和已有观察作为上下文，结束后将摘要和候选 SQL 返回父代理。

为控制上下文长度，代理状态超过限制时只保留最近三次观察、压缩后的子代理摘要和尾部证据。

### 4.5 最终 SQL 合成与修复

根代理结束后，`RecursiveDBRLM` 将原始问题、根代理结果和完整 Trace 交给另一次 LLM 调用，要求只返回最终 SQLite SQL。然后执行该 SQL；如果执行失败且仍有 Token 预算，则将错误信息交给模型进行最多一次修复。

这里存在一个值得注意的实现选择：除非 Token 预算已经耗尽，否则即使根代理已经给出经过测试的 `candidate_sql`，系统仍会进行一次新的最终 SQL 合成。二次合成可能修正不完整 SQL，也可能破坏原本正确的候选 SQL，后续应通过消融实验验证。

### 4.6 保存与断点恢复

四个 runner 均按题目 ID 保存结果：

- 每完成一道题就写入 JSON
- 使用临时文件和 `os.replace()` 原子替换，避免中断留下半个 JSON
- 重新运行时读取已有结果并跳过已完成 ID
- 输出顺序始终与原数据集一致

## 5. 实验过程

### 5.1 环境验证

首先在 Python 虚拟环境中执行 Smoke Test：

```powershell
python -m spider1_experiments.scripts.smoke_test --limit 1 --llm
```

验证结果：成功读取 `concert_singer` 数据库和 Schema，LLM 返回 `SELECT 1;`，说明数据、SQLite、Ollama 和模型接口均正常。

随后对 DB-RLM 运行 5 题 Smoke Test，结果为 4/5，即 80%。该结果只用于检查链路，不代表完整数据集表现。

### 5.2 评估器故障与修复

第一次完整运行 Baseline 1 时，在第 434 题 `dev_000433` 崩溃。对应数据库 `wta_1` 的 `birth_date` 列同时包含字符串和整数，旧评估器直接对结果元组排序，触发：

```text
TypeError: '<' not supported between instances of 'str' and 'int'
```

修复后，执行结果使用“带类型信息的行多重集合”比较：

- 不再比较不可排序的异构 Python 值
- 行顺序不影响结果
- 重复行数量仍然影响结果
- 整数和字符串不会被错误合并

同时加入逐题原子保存和断点恢复，并增加对应单元测试。三个新增测试均通过。

### 5.3 完整运行时间线

| 方法 | 开始时间 | 结束时间 | 总耗时 |
|---|---|---|---:|
| Baseline 1 | 2026-06-22 01:25:05 | 02:15:49 | 约 50 分 44 秒 |
| Baseline 2 | 2026-06-22 02:15:49 | 03:07:41 | 约 51 分 52 秒 |
| Baseline 3 | 2026-06-22 03:07:41 | 07:21:56 | 约 4 小时 14 分 |
| DB-RLM | 2026-06-22 15:41:15 | 22:47:57 | 约 7 小时 7 分 |

运行命令的核心参数如下：

```powershell
python -m spider1_experiments.scripts.run_all_baselines `
  --dataset data\processed\dev_questions.json `
  --database-dir data\databases `
  --results-dir results\spider1_full_dev `
  --top-k-tables 5 `
  --top-k-columns 8 `
  --max-steps 8

python -m spider1_experiments.scripts.run_ours `
  --dataset data\processed\dev_questions.json `
  --database-dir data\databases `
  --output results\spider1_full_dev\ours_recursive_db_rlm.json `
  --max-depth 2 `
  --max-actions 24 `
  --max-actions-per-agent 8 `
  --max-children-per-agent 3 `
  --token-budget 12000 `
  --max-rows 20 `
  --final-repair-attempts 1
```

## 6. 完整实验结果

### 6.1 核心指标

| 方法 | 正确数 | 执行准确率 | SQL 有效率 | Exact Match | 组件全匹配 | 平均耗时/题 |
|---|---:|---:|---:|---:|---:|---:|
| Baseline 1：完整 Schema | 758/1034 | 73.31% | 93.42% | 31.14% | 41.59% | 2.79 秒 |
| Baseline 2：检索 Schema | **774/1034** | **74.85%** | 96.81% | **33.56%** | **42.46%** | 2.85 秒 |
| Baseline 3：非递归代理 | 702/1034 | 67.89% | **97.29%** | 28.82% | 41.39% | 14.49 秒 |
| DB-RLM | 671/1034 | 64.89% | 91.01% | 20.12% | 35.69% | 24.36 秒 |

Baseline 2 是本次完整实验的最佳方法，比 Baseline 1 高 1.54 个百分点，比 Baseline 3 高 6.96 个百分点，比 DB-RLM 高 9.96 个百分点。

### 6.2 成本指标

| 方法 | 输入 Token | 输出 Token | 工具调用 | 平均工具调用/题 |
|---|---:|---:|---:|---:|
| Baseline 1 | 371,834 | 30,984 | 0 | 0 |
| Baseline 2 | **290,347** | **30,451** | 0 | 0 |
| Baseline 3 | 3,388,091 | 116,918 | 4,541 | 4.39 |
| DB-RLM | 8,376,405 | 309,637 | 7,611 | 7.36 |

Baseline 2 相比 Baseline 1 减少约 21.9% 的输入 Token，同时提高了准确率。Baseline 3 的输入 Token 是 Baseline 2 的约 11.7 倍，DB-RLM 则约为 28.9 倍，但两者准确率都更低。

### 6.3 失败类型

| 方法 | Invalid SQL | Wrong Table | Wrong Join | Wrong Aggregation | Wrong Result |
|---|---:|---:|---:|---:|---:|
| Baseline 1 | 68 | 62 | 61 | 15 | 70 |
| Baseline 2 | 33 | 80 | **56** | 14 | 77 |
| Baseline 3 | **28** | 112 | 79 | 20 | 93 |
| DB-RLM | 93 | 77 | 94 | 15 | 84 |

Baseline 3 的 SQL 有效率最高、非法 SQL 最少，说明数据库执行反馈确实有助于语法和 Schema 校验；但它更容易选择错误表或构造错误 Join，因此“SQL 能执行”没有转化为更高的答案正确率。

DB-RLM 的最终非法 SQL 数量最多。56 道题触发了一次最终修复，但完整运行结束后仍有 93 道题存在执行错误，说明当前单次修复和最终合成策略不足。

## 7. 关键分析

### 7.1 Schema 检索是当前最有效的改进

Baseline 2 同时取得最高准确率、最高 Exact Match、最高组件全匹配率和最低 Token 成本。说明对 7B 模型而言，减少无关 Schema 比增加代理步骤更有效。完整 Schema 会引入额外噪声，而简单词法检索已经能在保留主外键的前提下缩小搜索空间。

### 7.2 更多工具调用没有带来更高准确率

Baseline 3 的平均耗时约为 Baseline 2 的 5.1 倍，输入 Token 约为 11.7 倍，但准确率低 6.96 个百分点。模型能够利用工具减少非法 SQL，却不能稳定地把多轮观察整合成正确的表、Join 和最终语义。

这说明当前瓶颈不是“模型完全看不到数据库”，而是小模型的规划、状态保持和最终合成能力。

### 7.3 当前完整运行实际上没有发生递归

这是本实验最重要的诊断结果：

- 1,034 道题的 `max_depth_reached` 全部为 0
- `spawn_subagent` 出现次数为 0
- 没有任何问题创建子代理
- 每题平均 7.36 个动作、8.41 次 LLM 调用都发生在根代理及最终合成/修复流程中

因此，当前标记为 DB-RLM 的 64.89% 结果，实际评测的是“根数据库代理 + 额外 SQL 合成 + 一次修复”，而不是递归分解。不能根据这一结果判断递归是否有效；只能判断当前提示词和 7B 模型没有主动选择递归动作。

### 7.4 DB-RLM 的成对比较

与同一批 1,034 道题逐题比较：

| 对比方法 | DB-RLM 独有正确 | DB-RLM 独有错误 | 净变化 |
|---|---:|---:|---:|
| Baseline 1 | 65 | 152 | -87 |
| Baseline 2 | 58 | 161 | -103 |
| Baseline 3 | 74 | 105 | -31 |

DB-RLM 确实解决了一部分其他方法失败的问题，但同时破坏了更多原本可以正确回答的问题。相对 Baseline 3 的差距最小，说明两者行为较接近；这也符合“本次没有实际递归”的观察。

### 7.5 Exact Match 不能代替执行准确率

四种方法的 Exact Match 都显著低于执行准确率。例如 Baseline 2 的 Exact Match 为 33.56%，执行准确率为 74.85%。这是因为同一个查询可以有多种语义等价的 SQL 写法。因此实验结论应以执行准确率为主，Exact Match 和组件匹配只用于辅助定位错误。

## 8. 结论

本次 Spider 1.0 完整 dev 实验不支持“当前 DB-RLM 优于 baseline”的结论。结果表明：

1. 简单的 Schema 检索是当前最有效且最经济的方法，Baseline 2 达到 74.85%。
2. 工具调用能够提高 SQL 有效率，但没有自动提高答案准确率。
3. 当前 DB-RLM 成本最高、准确率最低，并且完整运行中没有真正触发递归。
4. 5 题 Smoke Test 的 80% 不能外推到完整数据集；完整运行的 DB-RLM 准确率为 64.89%。
5. 在实现可靠的递归触发机制之前，不能评价递归分解本身对 Spider 的作用。

## 9. 下一步实验建议

### 9.1 让递归真正发生

- 不要完全依赖 7B 模型主动选择 `spawn_subagent`
- 在检测到多表、嵌套查询、集合运算、复杂聚合或多个独立约束时，由控制器强制或建议拆分
- 给出具体的递归示例，而不只是动作说明
- 记录 `spawn_attempted`、`spawn_accepted` 和各深度成功率

### 9.2 做严格消融实验

至少比较以下配置，并保持模型、题目和预算一致：

- `max_depth=0`：禁止递归
- `max_depth=1`：允许一层子代理
- `max_depth=2`：允许两层子代理
- 强制复杂题创建子代理
- 使用根代理的已测试 `candidate_sql`，不执行二次合成
- 当前的二次合成版本

只有当 `max_depth>0` 的运行确实产生子代理后，才能把差异归因于递归。

### 9.3 改进最终 SQL 选择

- 如果根代理的候选 SQL 已成功执行，优先直接使用
- 将二次合成结果与已测试候选 SQL 都执行，再根据结果和问题选择
- 将修复次数与错误类型关联，而不是固定只修复一次
- 对重复无效 SQL、空 SQL 和非 SQLite 语法增加确定性检查

### 9.4 聚焦复杂问题

Spider 中大量简单题不需要递归，递归只会增加成本。后续应按难度、表数量、Join 数、嵌套层数和聚合复杂度分组报告结果，并只对高复杂度问题启用子代理。

### 9.5 更新汇总文件

当前 `summary_metrics.json` 在 DB-RLM 完成前生成，因此其中只包含三个 baseline。需要重新执行：

```powershell
python -m spider1_experiments.scripts.evaluate_results `
  --results-dir results\spider1_full_dev `
  --output results\spider1_full_dev\summary_metrics.json
```

重新生成后，汇总文件才会包含本文使用的 DB-RLM 完整结果。

## 10. 结果文件

```text
results/spider1_full_dev/
├── baseline_1_direct_llm_schema.json
├── baseline_2_direct_text_to_sql.json
├── baseline_3_non_recursive_db_agent.json
├── ours_recursive_db_rlm.json
└── summary_metrics.json
```

每个逐题结果包含问题、预测 SQL、标准 SQL、执行结果、正确性、延迟和 Token。代理方法还包含工具 Trace；DB-RLM 额外保存递归树、最大深度、动作数、LLM 调用数和修复次数，可用于后续错误分析与消融实验。
