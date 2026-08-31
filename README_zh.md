# Recursive DB-RLM：用于结构化数据库推理的递归语言模型

## 项目简介

本项目研究如何将 Recursive Language Model（RLM）的递归探索范式从非结构化信息检索扩展到结构化数据库推理。

传统 Text-to-SQL 方法通常将自然语言问题和数据库 Schema 一次性交给大语言模型，再直接生成 SQL。本项目希望让 Agent 分步骤探索数据库、查询相关表、生成子问题，并调用子 Agent 独立解决局部任务，最后聚合证据并生成最终 SQL。

主要研究问题：

1. 递归问题分解能否提高复杂数据库问题的正确率？
2. 数据库探索能否减少虚构表名、字段名和错误连接？
3. 递归过程能否提供更清晰、可解释的中间证据？
4. 在大型 Schema 上，递归探索能否降低上下文和 Token 成本？

---

## 研究动机

传统 Text-to-SQL 流程：

```text
自然语言问题
    ↓
LLM
    ↓
SQL
```

复杂数据库问题往往还需要：

- 理解多张表之间的关系
- 找到真正相关的表和字段
- 检查数据库中的实际值和格式
- 执行中间 SQL 并观察结果
- 将复杂任务拆分成多个子问题

本项目探索以下递归流程：

```text
自然语言问题
    ↓
根 Agent
    ↓
探索数据库
    ↓
生成子问题
    ↓
递归数据库 Agent
    ↓
返回中间证据
    ↓
根 Agent 聚合证据
    ↓
最终 SQL / 答案
```

---

# 对比方法

项目比较四种方法。

## Baseline 1：直接 LLM + 完整 Schema

模型仅接收：

```text
用户问题 + 完整数据库 Schema
```

然后一次性生成 SQL。

允许：

- 使用完整 Schema

不允许：

- 查看表内容
- 使用 SQL 执行反馈
- 重试
- 递归推理

研究问题：

```text
完整 Schema 加一次推理是否已经足够？
```

## Baseline 2：一次 Schema 检索 + Text-to-SQL

系统先检索 Top-K 相关表和字段，再把缩小后的 Schema 交给模型生成 SQL。

```text
问题
  ↓
检索相关表和字段
  ↓
局部 Schema
  ↓
LLM
  ↓
SQL
```

允许：

- 一次性 Schema 检索
- 使用 Top-K 表和字段
- 保留连接所需的主键和外键

不允许：

- 查看表内容
- 使用 SQL 执行反馈
- 重试
- 递归推理

研究问题：

```text
如果先缩小 Schema，普通的一次性 Text-to-SQL 是否已经足够？
```

## Baseline 3：非递归数据库 Agent

非递归 Agent 可以多步使用数据库工具：

```text
SHOW_TABLES()
DESCRIBE_TABLE()
SAMPLE_ROWS()
EXECUTE_SQL()
```

流程：

```text
问题
  ↓
Agent
  ↓
检查 Schema
  ↓
采样表数据 / 执行 SQL
  ↓
观察结果
  ↓
最终 SQL
```

允许：

- Schema 探索
- 表内容采样
- SQL 执行和反馈
- 多步推理

不允许：

- 创建递归子 Agent
- 递归分解问题

研究问题：

```text
仅使用普通多步工具 Agent 是否足够？
```

## 本项目方法：Recursive DB-RLM

Recursive DB-RLM 允许根 Agent 将复杂问题分解为子问题，并让子 Agent 独立探索数据库。

```text
问题
  ↓
根数据库 Agent
  ↓
Schema 探索
  ↓
生成子问题
  ↓
递归子 Agent
  ↓
返回 Schema、SQL、结果和结论
  ↓
根 Agent 聚合证据
  ↓
最终 SQL / 答案
```

允许：

- 数据库探索
- 递归问题分解
- 子 Agent 独立推理
- 中间证据聚合

核心研究问题：

```text
在相同模型、工具和计算预算下，
递归子问题探索是否比普通多步 Agent 更有效？
```

---

# 数据集

项目使用 Spider 1.0 Text-to-SQL Benchmark。数据集包括：

- 自然语言问题
- SQLite 数据库
- 标准 SQL 查询

Spider 数据较大，并包含超过 GitHub 单文件限制的文件，因此不会直接存储在本仓库中。

官方资源：

- Spider 页面：https://yale-lily.github.io/spider
- 官方代码仓库：https://github.com/taoyds/spider

请在 Spider 官方页面的 **Getting Started** 部分点击 **Spider Dataset** 下载 Spider 1.0。本项目使用 Spider 1.0，不是 Spider 2.0。

下载并解压后，将数据放到：

```text
data/spider_data/
```

最终目录结构：

```text
AgenticSearch/
└── data/
    └── spider_data/
        ├── train_spider.json
        ├── dev.json
        ├── tables.json
        └── database/
            ├── concert_singer/
            │   └── concert_singer.sqlite
            └── ...
```

运行一条命令准备项目数据：

```bash
python scripts/prepare_spider.py
```

该脚本会：

1. 转换 `train_spider.json` 和 `dev.json`。
2. 生成 `data/processed/train_questions.json`。
3. 生成 `data/processed/dev_questions.json`。
4. 在 `data/databases/{db_id}/{db_id}.sqlite` 创建数据库链接。

默认使用符号链接，不会重复复制整个数据库。

如果系统不支持符号链接，可以复制数据库：

```bash
python scripts/prepare_spider.py --database-mode copy
```

如果 Spider 位于其他位置：

```bash
python scripts/prepare_spider.py --spider-dir /path/to/spider
```

脚本可重复执行，已有数据库会被复用。

---

# 统一数据格式

Spider 样本被转换为：

```json
{
  "id": "dev_000001",
  "db_id": "concert_singer",
  "question": "How many singers do we have?",
  "gold_sql": "SELECT count(*) FROM singer"
}
```

字段映射：

```text
Spider 字段       项目字段
db_id         -> db_id
question      -> question
query         -> gold_sql
```

---

# 项目结构

```text
AgenticSearch/
├── baselines/
│   ├── baseline_1_direct_llm_schema.py
│   ├── baseline_2_direct_text_to_sql.py
│   └── baseline_3_non_recursive_db_agent.py
├── ours/
│   ├── recursive_db_rlm.py
│   ├── recursive_controller.py
│   ├── db_environment.py
│   └── subquestion_agent.py
├── shared/
│   ├── config.py
│   ├── data_loader.py
│   ├── schema_utils.py
│   ├── sql_executor.py
│   ├── evaluator.py
│   └── llm_client.py
├── prompts/
├── scripts/
├── data/
├── results/
├── logs/
└── notebooks/
```

---

# 共享组件

所有方法应尽量使用相同的基础组件，以保证比较公平。

## Schema 提取器

输入 SQLite 数据库，输出表、字段、主键和外键描述。

```text
Table: singer

Columns:
- singer_id INTEGER PRIMARY KEY
- name TEXT
- age INTEGER
```

## SQL 执行器

输入：

```text
数据库路径 + SQL
```

输出：

```json
{
  "answer": [[20]],
  "error": null
}
```

正式实现应限制为只读 SQL，并设置执行超时和最大返回行数。

## 评测器

主要指标为 Execution Accuracy：

```text
Execute(predicted_sql) == Execute(gold_sql)
```

还应记录：

- SQL 有效率
- 平均延迟
- 输入和输出 Token
- 错误率
- 工具调用次数
- 最大递归深度
- 子 Agent 数量

---

# 环境配置

安装依赖：

```bash
pip install -r requirements.txt
```

创建环境变量文件：

```bash
cp .env.example .env
```

根据所用 Provider 配置模型和 API Key，例如：

```text
LLM_PROVIDER=gemini
MODEL=gemini-2.5-flash
GEMINI_API_KEY=your_key
TEMPERATURE=0
MAX_TOKENS=1024
```

实际支持的 Provider 以 `shared/llm_client.py` 为准。

---

# 运行实验

准备数据：

```bash
python scripts/prepare_spider.py
```

先运行少量样本：

```bash
python scripts/run_baseline_1.py --limit 5
python scripts/run_baseline_2.py --limit 5
python scripts/run_baseline_3.py --limit 5
python scripts/run_ours.py --limit 5
```

运行完整实验：

```bash
python scripts/run_baseline_1.py
python scripts/run_baseline_2.py
python scripts/run_baseline_3.py
python scripts/run_ours.py
```

汇总结果：

```bash
python scripts/evaluate_results.py
```

结果保存在：

```text
results/
├── baseline_1_direct_llm_schema.json
├── baseline_2_direct_text_to_sql.json
├── baseline_3_non_recursive_db_agent.json
└── ours_recursive_db_rlm.json
```

---

# 统一输出格式

每个方法至少输出：

```json
{
  "id": "dev_000001",
  "method": "baseline_1_direct_llm_schema",
  "db_id": "concert_singer",
  "question": "...",
  "predicted_sql": "SELECT ...",
  "predicted_answer": [[6]],
  "gold_sql": "SELECT ...",
  "gold_answer": [[6]],
  "correct": true,
  "error": null,
  "latency_seconds": 1.23,
  "input_tokens": 500,
  "output_tokens": 40
}
```

Agent 方法还应保存：

```text
agent_trace
tool_call_count
attempts
recursion_depth
child_agent_count
```

---

# 实验设计

四种方法必须使用：

- 相同的 Spider 样本
- 相同的模型
- 相同的 Temperature
- 相同的最大输出 Token
- 相同的数据库
- 相同的 SQL 执行器
- 相同的评测标准

建议实验规模：

```text
开发调试：5–20 条
初步对比：固定 50 条
中等规模：200–500 条
最终实验：完整 Spider dev 1034 条
```

递归方法应进行消融实验：

```text
Depth 0：不递归
Depth 1：一层子 Agent
Depth 2：两层递归
No Sampling：禁用数据采样
No Execution Feedback：禁用执行反馈
```

最重要的公平比较：

```text
相同模型 + 相同工具 + 相同计算预算
非递归 Agent vs Recursive DB-RLM
```

---

# 当前状态

- [x] 项目基础结构
- [x] Spider 自动准备脚本
- [x] Baseline 1
- [x] Baseline 2
- [ ] Baseline 3 正式实现与验证
- [ ] 只读数据库工具环境
- [ ] Recursive DB-RLM
- [ ] 深度和预算控制
- [ ] 统一正式评测
- [ ] 消融实验
- [ ] 错误分析
- [ ] 最终论文和演示

---

# 最终目标

构建一个可运行、可复现的 Recursive Database Reasoning Agent，并通过公平实验回答：

```text
递归数据库探索能否在复杂问题和大型 Schema 上，
以可接受的 Token 和时间成本，
取得比直接 Text-to-SQL 和普通多步 Agent 更好的结果？
```

