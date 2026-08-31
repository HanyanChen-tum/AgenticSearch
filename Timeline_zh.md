# Recursive DB-RLM 项目时间线

## 项目目标

将 Recursive Language Model（RLM）的递归探索思想从非结构化信息检索扩展到结构化数据库环境。

系统允许模型：

1. 分步骤探索数据库 Schema。
2. 查询和采样相关表。
3. 在信息不足时创建递归子 Agent。
4. 聚合子 Agent 返回的证据。
5. 生成最终 SQL 和答案。

预期提升：

- 准确率
- 可扩展性
- Token 效率
- 可解释性

总体路线：

```text
理解和复现 RLM
  ↓
准备 Spider 和数据库环境
  ↓
完成三个 Baseline
  ↓
实现 Recursive DB-RLM
  ↓
统一实验与消融
  ↓
论文、演示和最终交付
```

---

# 团队分工

## Person A：RLM 与 Agent 系统

主要职责：

```text
设计和实现递归数据库推理框架
```

具体负责：

- 理解原始 RLM
- 根 Agent 和子 Agent 架构
- Agent 通信
- 递归控制
- Prompt 设计
- DB-RLM 实现
- 深度、动作和 Token 预算

## Person B：数据库、Baseline 与评测

主要职责：

```text
构建数据库环境并保证实验可信
```

具体负责：

- Spider 数据准备
- SQLite 工具
- 三个 Baseline
- 统一输出格式
- 评测指标
- 正式实验
- 错误分析

---

# 第 1 周：理解项目与搭建环境

## Person A

任务：

- 运行原始 RLM 仓库。
- 理解根 Agent。
- 理解子 Agent 创建过程。
- 理解递归调用和停止条件。
- 找出将搜索任务改为数据库任务的位置。

交付物：

- 可运行的原始 RLM。
- RLM 代码结构说明。
- DB-RLM 修改设计。

## Person B

任务：

- 下载和准备 Spider 1.0。
- 理解 Spider 的问题、Schema 和 SQLite 结构。
- 完成数据转换脚本。
- 构建 SQLite 访问工具。

基础工具：

```text
list_tables()
describe_table()
sample_rows()
execute_sql()
```

交付物：

- 可运行的 Spider 环境。
- 统一格式的 train/dev 数据。
- SQL 执行和结果读取流程。

验收条件：

- 可以根据 `db_id` 找到数据库。
- 可以执行 Spider gold SQL。
- 可以提取表、字段、主键和外键。

---

# 第 2–3 周：完成三个 Baseline

目标：

在构建递归方法前，先建立可信、可复现的对照组。

## Baseline 1：直接 LLM + 完整 Schema

负责人：Person B

```text
问题 + 完整 Schema
  ↓
LLM
  ↓
SQL
```

记录：

- 预测 SQL
- 执行结果
- Execution Accuracy
- 延迟
- Token
- 错误信息

限制：

- 不查看表内容。
- 不使用执行反馈。
- 不重试。
- 不递归。

## Baseline 2：一次 Schema 检索 + Text-to-SQL

负责人：Person B

```text
问题
  ↓
检索 Top-K 表和字段
  ↓
局部 Schema
  ↓
LLM
  ↓
SQL
```

限制：

- 只检索一次 Schema。
- 保留主键、外键和连接路径。
- 不查看表内容。
- 不使用执行反馈。
- 不重试。

## Baseline 3：非递归数据库 Agent

负责人：Person A + Person B

```text
问题
  ↓
非递归 Agent
  ↓
调用数据库工具
  ↓
观察 Schema、样本和 SQL 结果
  ↓
继续推理
  ↓
最终 SQL
```

允许：

- 多步工具调用
- Schema 探索
- 数据采样
- SQL 执行反馈
- SQL 修正

禁止：

- 创建子 Agent
- 递归问题分解

建议使用结构化 Action：

```json
{
  "action": "describe_table",
  "arguments": {
    "table": "singer"
  }
}
```

最终 Action：

```json
{
  "action": "final_sql",
  "sql": "SELECT COUNT(*) FROM singer"
}
```

第 3 周验收：

| 方法 | 目标状态 |
|---|---|
| Baseline 1 | 完成并验证 |
| Baseline 2 | 完成并验证 |
| Baseline 3 | 完成并验证 |

三个方法必须使用相同：

- 数据样本
- 模型
- Temperature
- 最大 Token
- 数据库
- 评测器

---

# 第 4–6 周：实现 Recursive DB-RLM

主要负责人：Person A

## 第一步：数据库环境

完成 `ours/db_environment.py`。

工具接口：

```text
list_tables()
describe_table(table)
sample_rows(table, limit)
search_value(value)
execute_sql(sql)
```

安全要求：

- 只允许只读查询。
- 禁止 INSERT、UPDATE、DELETE 和 DROP。
- 限制返回行数。
- 设置执行超时。
- 截断过长 Observation。
- 记录所有工具调用。

Baseline 3 和 Recursive DB-RLM 应使用相同工具环境。

## 第二步：单 Agent 工具循环

实现可复用的非递归工具循环：

```text
LLM 生成 Action
  ↓
执行工具
  ↓
返回 Observation
  ↓
LLM 决定下一步
  ↓
最终 SQL
```

建议参数：

```text
max_actions_per_agent = 8
max_sql_attempts = 3
max_observation_rows = 5
```

## 第三步：Subquestion Agent

完成 `ours/subquestion_agent.py`。

输入：

```text
原始问题
当前子问题
递归深度
已有证据
数据库环境
剩余预算
```

输出：

```json
{
  "subquestion": "...",
  "relevant_tables": ["employee", "department"],
  "sql": "SELECT ...",
  "result": [["Sales"]],
  "finding": "Sales 满足该条件",
  "trace": []
}
```

子 Agent 应返回证据，而不是只返回自然语言答案。

## 第四步：递归控制器

完成 `ours/recursive_controller.py`。

控制器负责：

- 判断是否需要分解问题。
- 生成子问题。
- 控制子 Agent 数量。
- 控制最大递归深度。
- 控制动作和 Token 预算。
- 防止重复问题和递归循环。
- 决定何时停止。

建议初始参数：

```text
max_depth = 2
max_children = 3
max_actions_per_agent = 8
max_total_actions = 30
max_total_tokens = 20000
```

停止条件：

- 达到最大深度。
- 达到动作或 Token 预算。
- 子问题重复。
- 没有产生新证据。
- Agent 返回最终 SQL。

## 第五步：根 Recursive Agent

完成 `ours/recursive_db_rlm.py`。

根 Agent 支持三类决策：

```json
{
  "action": "explore",
  "tool": "describe_table",
  "arguments": {}
}
```

```json
{
  "action": "spawn_children",
  "subquestions": ["...", "..."]
}
```

```json
{
  "action": "final_sql",
  "sql": "SELECT ..."
}
```

根 Agent 聚合子 Agent 返回的 Schema、SQL、结果和结论，再生成回答原始问题的最终 SQL。

## Person B 在第 4–6 周

完善评测管线，确保每条结果记录：

- 预测 SQL
- 预测执行结果
- gold SQL 和结果
- 正确性
- 延迟
- 输入和输出 Token
- 工具调用次数
- 最大递归深度
- 子 Agent 数量
- 完整 Trace
- 错误类型

---

# 第 7–8 周：正式实验

## 实验规模

按以下顺序扩大：

```text
5 条：检查基本流程
20 条：检查 Trace、预算和错误恢复
50 条：四种方法初步比较
200–500 条：确认稳定趋势
1034 条 Spider dev：最终实验
```

所有方法必须使用相同样本 ID。

## 准确率指标

主要指标：

```text
Execution Accuracy
```

辅助指标：

- SQL Valid Rate
- Schema Hallucination Rate
- Empty-result False Positive Rate
- Timeout Rate

## 效率指标

- 输入 Token
- 输出 Token
- 总 Token
- 平均延迟
- 工具调用次数
- SQL 执行次数
- 子 Agent 数量

主结果表：

| 方法 | Accuracy | Tokens | Latency | Tool Calls |
|---|---:|---:|---:|---:|
| Full Schema | | | | |
| Retrieved Schema | | | | |
| Non-recursive Agent | | | | |
| Recursive DB-RLM | | | | |

## 可扩展性实验

按数据库规模分组：

```text
Small：表和字段较少
Medium：中等 Schema
Large：表和字段较多
```

| 方法 | Small | Medium | Large |
|---|---:|---:|---:|
| Baseline 1 | | | |
| Baseline 2 | | | |
| Baseline 3 | | | |
| Recursive DB-RLM | | | |

研究假设：

```text
完整 Schema 方法在大型数据库上下降更明显，
Recursive DB-RLM 可以通过局部探索维持更好的性能。
```

---

# 第 9–10 周：优化和消融实验

## Person A：优化递归决策

研究什么时候创建子 Agent。

规则方法：

```text
if uncertainty is high:
    spawn child agent
```

Prompt 方法：

```text
当当前证据不足以生成可靠 SQL 时，创建子 Agent。
```

需要避免：

- 简单问题过度递归
- 重复创建相同子问题
- 子 Agent 返回无关信息
- Token 和工具调用失控

## Person B：消融实验

至少运行：

| 实验 | 目的 |
|---|---|
| Depth 0 | 不使用递归 |
| Depth 1 | 一层子 Agent |
| Depth 2 | 两层递归 |
| No Sampling | 测试数据采样贡献 |
| No Execution Feedback | 测试执行反馈贡献 |
| No Child Evidence | 测试证据聚合贡献 |

关键公平比较：

```text
相同模型 + 相同工具 + 相同总预算
Non-recursive Agent vs Recursive DB-RLM
```

否则准确率提升可能来自更多模型调用，而不是递归结构。

---

# 第 11 周：错误分析、论文与文档

## 错误分析

分类：

- SQL 语法错误
- 虚构表名
- 虚构字段名
- 错误表选择
- 错误 Join
- 错误聚合
- 错误过滤
- 错误排序
- 重复行处理错误
- 空结果误判
- 子问题分解错误
- 证据聚合错误
- 预算耗尽

重点比较：

```text
Baseline 3 错、Recursive 正确
Baseline 3 正确、Recursive 错
四种方法全部错误
```

## 论文结构

### Introduction

- 大型数据库 Schema 对 LLM 的挑战。
- 一次性 Text-to-SQL 的局限。
- 为什么需要递归数据库探索。

### Method

- 数据库环境
- 非递归工具 Agent
- 子问题 Agent
- 递归控制器
- 证据聚合
- 预算和停止条件

### Experiments

- 主结果
- 不同数据库规模
- 不同 SQL 难度
- 递归深度消融
- Token 和延迟
- 错误分析

---

# 第 12 周：最终交付

完成：

- 清理 GitHub 仓库
- 完善英文 README
- 完善数据准备说明
- 提供 Demo Notebook
- 运行最终实验
- 生成结果表格和图
- 完成论文
- 制作演示 Slides

验收清单：

- [ ] 新用户可以按照 README 准备 Spider。
- [ ] 四种方法可以通过统一命令运行。
- [ ] 实验配置和结果可以复现。
- [ ] 正式结果包含逐条输出。
- [ ] 评测脚本可以生成汇总指标。
- [ ] 错误分析能够解释主要失败原因。
- [ ] Recursive 方法保存完整 Trace。
- [ ] 论文中的数字能对应到结果文件。

---

# 最终贡献分工

## Person A

主要贡献：

```text
Recursive Agent System
```

负责：

- RLM 改造
- Agent 框架
- 递归探索
- 子 Agent 通信
- Prompt
- 深度和预算控制

## Person B

主要贡献：

```text
Database and Evaluation System
```

负责：

- Spider 数据准备
- SQLite 环境
- 三个 Baseline
- 统一结果格式
- 评测指标
- 正式实验
- 错误分析

---

# 预期最终结构

```text
AgenticSearch/
├── baselines/
├── ours/
│   ├── db_environment.py
│   ├── subquestion_agent.py
│   ├── recursive_controller.py
│   └── recursive_db_rlm.py
├── shared/
├── scripts/
├── experiments/
├── results/
├── docs/
├── notebooks/
└── paper/
```

最终成果：

```text
一个可运行、可复现的 Recursive Database Reasoning Agent，
并通过公平实验验证递归探索在复杂数据库推理中的实际价值。
```

