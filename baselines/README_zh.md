# Baseline 与统一实验规范

本文档定义三个 Baseline、Recursive DB-RLM，以及保证所有方法能够公平比较的统一标准。

## 目录

- [方法概览](#方法概览)
  - [Baseline 1：直接 LLM + 完整 Schema](#baseline-1直接-llm--完整-schema)
  - [Baseline 2：一次 Schema 检索 + Text-to-SQL](#baseline-2一次-schema-检索--text-to-sql)
  - [Baseline 3：非递归数据库 Agent](#baseline-3非递归数据库-agent)
  - [Recursive DB-RLM](#本项目方法recursive-db-rlm)
- [实验指标](#实验指标)
- [shared 目录文件说明](#shared-目录文件说明)
  - [shared/config.py：统一配置](#sharedconfigpy统一配置)
  - [shared/data_loader.py：数据集加载](#shareddataloaderpy数据集加载)
  - [shared/schema_utils.py：数据库路径与 Schema](#sharedschema_utilspy数据库路径与-schema)
  - [shared/sql_executor.py：SQL 执行](#sharedsql_executorpySQL-执行)
  - [shared/evaluator.py：答案评测](#sharedevaluatorpy答案评测)
  - [shared/llm_client.py：模型调用](#sharedllm_clientpy模型调用)
  - [shared/io_utils.py：文件读写](#sharedio_utilspy文件读写)
  - [shared/logging_utils.py：日志](#sharedlogging_utilspy日志)
- [Part A：统一实现接口](#part-a统一实现接口)
  - [1. 统一输入格式](#1-统一输入格式)
  - [2. 统一数据库路径](#2-统一数据库路径)
  - [3. 统一输出格式](#3-统一输出格式)
  - [4. 统一方法名称](#4-统一方法名称)
  - [5. 统一模型配置](#5-统一模型配置)
  - [6. 统一 SQL 执行器](#6-统一-sql-执行器)
  - [7. 统一评测函数](#7-统一评测函数)
  - [8. 统一 Schema 格式](#8-统一-schema-格式)
  - [9. 统一 Prompt 输出要求](#9-统一-prompt-输出要求)
  - [10. 方法约束](#10-方法约束)
- [Part B：统一数据准备](#part-b统一数据准备)
  - [11. 数据来源](#11-数据来源)
  - [11.1 Spider 原始结构](#111-spider-原始结构)
  - [11.2 问题与 Gold SQL](#112-问题与-gold-sql)
  - [11.3 数据库来源](#113-数据库来源)
  - [11.4 Schema 来源](#114-schema-来源)
  - [11.5 Gold Answer 生成](#115-gold-answer-生成)
  - [11.6 最终数据流](#116-最终数据流)
- [推荐项目结构](#推荐项目结构)
- [实验前必须统一的事项](#实验前必须统一的事项)

---

## 方法概览

### Baseline 1：直接 LLM + 完整 Schema

标准的一次性 Text-to-SQL Baseline。

- 输入：用户问题 + 完整数据库 Schema
- 输出：SQL
- 评测：执行预测 SQL，并与 gold SQL 的执行结果比较

研究问题：

```text
完整 Schema 加一次推理是否足够？
```

### Baseline 2：一次 Schema 检索 + Text-to-SQL

流程：

1. 根据用户问题检索 Top-K 相关表和字段。
2. 为已选表保留主键和外键字段，避免丢失连接路径。
3. 将检索后的 Schema 和问题交给 LLM。
4. LLM 一次性生成 SQL。

研究问题：

```text
如果先缩小 Schema，普通 Text-to-SQL 是否已经足够？
```

### Baseline 3：非递归数据库 Agent

LLM 可以多步调用数据库工具：

```text
SHOW_TABLES()
DESCRIBE_TABLE()
SAMPLE_ROWS()
EXECUTE_SQL()
```

允许多步 Schema 探索、数据采样、SQL 执行和结果观察，但不允许创建递归子 Agent。

研究问题：

```text
仅使用普通多步工具探索是否足够？
```

### 本项目方法：Recursive DB-RLM

- 根 RLM 可以将问题拆分成多个子问题。
- 子问题可以交给独立的递归 Agent。
- 每个子 Agent 可以独立探索 Schema、表、连接路径和 SQL 片段。
- 根 Agent 聚合子结果，再生成最终 SQL 或答案。

研究问题：

```text
递归分解和独立子探索是否比普通多步 Agent 更有效？
```

---

## 实验指标

主要指标：

- SQL Execution Accuracy

辅助指标：

- Exact Match / Component Match
- 输入和输出 Token
- 数据库工具调用次数
- SQL 执行次数
- 平均延迟
- SQL 有效率
- 最大递归深度
- 子 Agent 数量

错误类型：

- 错误表选择
- 虚构表或字段
- 错误 Join
- 错误聚合
- 错误过滤
- 错误排序
- 无效 SQL
- 预算耗尽

Benchmark：

```text
Spider 1.0 Text-to-SQL Benchmark
```

---

# shared 目录文件说明

`shared/` 存放四种方法共同使用的基础组件。它的作用是避免每个 Baseline 分别实现数据读取、数据库定位、Schema 提取、模型调用和评测逻辑，从而保证实验具有可比性。

整体对应关系：

```text
config.py
  ↓
统一路径和模型参数
  ↓
data_loader.py ──读取问题──┐
schema_utils.py ─提取 Schema├─→ Baseline / Recursive 方法
llm_client.py ───调用模型───┤
sql_executor.py ─执行 SQL───┘
  ↓
evaluator.py 比较预测结果和 gold 结果
  ↓
io_utils.py 保存逐条结果
  ↓
logging_utils.py 记录运行过程
```

| 文件 | 对应的实验环节 | 主要使用者 |
|---|---|---|
| `config.py` | 路径、模型和生成参数 | 所有方法与脚本 |
| `data_loader.py` | 加载统一格式的问题 | Baseline 1–3、Recursive DB-RLM |
| `schema_utils.py` | 定位数据库、列出表、提取 Schema | 所有需要数据库结构的方法 |
| `sql_executor.py` | 执行预测 SQL 和 gold SQL | 所有方法与评测流程 |
| `evaluator.py` | 比较预测答案和 gold 答案 | 所有方法 |
| `llm_client.py` | 调用 LLM 生成 SQL | 所有 LLM 方法 |
| `io_utils.py` | 读取 Prompt/JSON，保存结果 | 数据准备、方法运行和评测脚本 |
| `logging_utils.py` | 输出终端日志和日志文件 | 所有运行脚本 |
| `__init__.py` | 将 `shared` 标记为 Python 包 | Python 导入系统 |

## shared/config.py：统一配置

对应：

```text
实验路径配置 + 模型配置
```

主要内容：

```python
PROJECT_ROOT
DATA_DIR
PROCESSED_DATA_DIR
DATABASE_DIR
RESULTS_DIR
PROMPTS_DIR
DEFAULT_DATASET_PATH
```

模型参数：

```python
LLM_PROVIDER
MODEL
GEMINI_API_KEY
TEMPERATURE
MAX_TOKENS
N_ATTEMPTS
```

它还会读取项目根目录中的 `.env`。

所有方法都应该从这里读取路径和模型参数，不能在各自文件中写不同的默认配置。

实验对应关系：

```text
config.py
  ├── 决定从哪里读取 dev_questions.json
  ├── 决定数据库目录
  ├── 决定 Prompt 和结果目录
  └── 保证四种方法使用相同模型参数
```

## shared/data_loader.py：数据集加载

对应：

```text
统一实验输入
```

核心函数：

```python
load_questions(path)
```

它读取 JSON，并检查每条样本是否包含：

```text
id
db_id
question
gold_sql
```

如果文件不是列表、样本不是对象或缺少字段，会直接报错。

调用流程：

```text
data/processed/dev_questions.json
  ↓
load_questions()
  ↓
Baseline 1 / 2 / 3 / Recursive DB-RLM
```

## shared/schema_utils.py：数据库路径与 Schema

对应：

```text
数据库定位 + Schema 获取
```

核心函数：

```python
get_database_path(database_dir, db_id)
list_tables(db_path)
extract_schema_text(db_path)
```

功能：

- 根据 `db_id` 生成 SQLite 路径。
- 从 `sqlite_master` 中列出用户表。
- 使用 `PRAGMA table_info` 提取字段。
- 使用 `PRAGMA foreign_key_list` 提取外键。
- 将 Schema 格式化为统一文本。

调用关系：

```text
Baseline 1
  └── extract_schema_text() 获取完整 Schema

Baseline 2
  └── 使用相同数据库结构，再检索 Top-K 子集

Baseline 3
  └── 用于列出表和检查相关 Schema

Recursive DB-RLM
  └── 作为数据库探索工具的底层实现
```

统一使用该模块可以避免不同方法看到不同格式的 Schema。

## shared/sql_executor.py：SQL 执行

对应：

```text
预测 SQL 执行 + gold SQL 执行
```

核心函数：

```python
execute_sql(db_path, sql)
```

成功返回：

```json
{
  "answer": [[6]],
  "error": null
}
```

失败返回：

```json
{
  "answer": null,
  "error": "SQLite error message"
}
```

使用位置：

```text
predicted_sql ─┐
               ├─→ execute_sql() ─→ 答案比较
gold_sql ──────┘
```

当前实现直接通过 SQLite 执行传入语句。正式 Agent 实验中还应增加只读限制、超时和最大返回行数，防止模型修改数据库或执行过大的查询。

## shared/evaluator.py：答案评测

对应：

```text
Execution Accuracy
```

核心函数：

```python
normalize_answer(answer)
is_correct(pred_answer, gold_answer)
```

当前逻辑会把结果行转换为 tuple 并排序，然后比较：

```text
normalize(predicted_answer) == normalize(gold_answer)
```

优点：

- SQL 写法可以不同。
- 只要执行结果相同，就可判定正确。

当前限制：

- 所有结果都会排序。
- 对明确要求 `ORDER BY` 的问题，错误顺序也可能被判正确。

正式评测应区分：

```text
无顺序要求：按多重集合比较
有顺序要求：按原始顺序比较
```

## shared/llm_client.py：模型调用

对应：

```text
Prompt → LLM → SQL
```

核心数据结构：

```python
LLMResponse(
    text,
    input_tokens,
    output_tokens,
)
```

核心函数：

```python
generate_sql(prompt)
```

它负责：

- 从 `config.py` 读取 Provider 和模型。
- 检查 API Key。
- 设置 system instruction。
- 设置 Temperature 和最大输出 Token。
- 调用模型。
- 返回生成文本及 Token 使用量。

当前 `Irene` 分支的实现只支持：

```text
Gemini
```

如果以后增加 Groq、OpenAI 或 Ollama，应继续保持相同的 `LLMResponse` 接口，这样 Baseline 代码不需要修改。

## shared/io_utils.py：文件读写

对应：

```text
读取数据与 Prompt + 保存结果
```

核心函数：

```python
read_json(path)
write_json(path, data)
read_text(path)
```

使用场景：

- `prepare_spider.py` 读取 Spider JSON。
- `data_loader.py` 读取统一数据集。
- Baseline 读取 Prompt 模板。
- Baseline 将逐条结果写入 `results/`。
- `evaluate_results.py` 读取结果并写入汇总指标。

`write_json()` 会自动创建父目录，并使用 UTF-8 和缩进格式保存。

## shared/logging_utils.py：日志

对应：

```text
实验运行记录
```

核心函数：

```python
setup_logger(name, log_path=None)
```

它可以同时：

- 将日志输出到终端。
- 将日志写入指定文件。
- 统一时间、日志级别和模块名格式。

示例：

```text
2026-06-09 02:59:27 | INFO | baseline_1_direct_llm_schema | Starting ...
```

日志用于确认：

- 实际运行了多少样本。
- 使用了哪个数据集和数据库目录。
- 输出文件写到了哪里。
- 最终正确数和准确率。

## shared/__init__.py：Python 包入口

该文件目前为空，主要作用是让 Python 将 `shared/` 识别为可导入包。

因此其他模块可以使用：

```python
from shared import config
from shared.data_loader import load_questions
```

---

# Part A：统一实现接口

在实现不同方法之前，必须先固定公共接口和规则。

以下内容必须由四种方法共享：

```text
Baseline 1
Baseline 2
Baseline 3
Recursive DB-RLM
```

包括：

```text
统一输入
统一数据库路径
统一输出
统一模型配置
统一 SQL 执行器
统一评测器
统一 Schema 格式
```

---

## 1. 统一输入格式

所有方法读取相同的数据格式：

```json
{
  "id": "q001",
  "db_id": "company",
  "question": "Which department has the highest average salary?",
  "gold_sql": "SELECT ..."
}
```

必需字段：

| 字段 | 含义 |
|---|---|
| `id` | 问题唯一标识 |
| `db_id` | 对应数据库 |
| `question` | 自然语言问题 |
| `gold_sql` | 标准 SQL |

所有方法必须使用相同的样本 ID，不能分别抽取自己的测试集。

---

## 2. 统一数据库路径

所有方法必须使用相同的数据库目录结构：

```text
data/databases/{db_id}/{db_id}.sqlite
```

示例：

```text
data/databases/company/company.sqlite
```

数据库查找逻辑应放在共享模块中，不能在每个 Baseline 中分别实现。

---

## 3. 统一输出格式

每个方法使用相同的 JSON 结构：

```json
{
  "id": "q001",
  "method": "baseline_1_direct_llm_schema",
  "db_id": "company",
  "question": "Which department has the highest average salary?",
  "predicted_sql": "SELECT ...",
  "predicted_answer": [
    ["HR", 85000]
  ],
  "gold_sql": "SELECT ...",
  "gold_answer": [
    ["HR", 85000]
  ],
  "correct": true,
  "error": null,
  "latency_seconds": 3.21,
  "input_tokens": 1200,
  "output_tokens": 80
}
```

公共字段必须保持一致。

方法可以增加自己的诊断字段。例如 Baseline 2：

```json
{
  "retrieved_schema": "Table: ...",
  "top_k_tables": 5,
  "top_k_columns": 8
}
```

Agent 方法可以增加：

```json
{
  "agent_trace": [],
  "tool_call_count": 8,
  "attempts": 2,
  "recursion_depth": 0,
  "child_agent_count": 0
}
```

---

## 4. 统一方法名称

固定方法标识：

```text
baseline_1_direct_llm_schema
baseline_2_direct_text_to_sql
baseline_3_non_recursive_db_agent
ours_recursive_db_rlm
```

对应结果文件：

```text
results/
├── baseline_1_direct_llm_schema.json
├── baseline_2_direct_text_to_sql.json
├── baseline_3_non_recursive_db_agent.json
└── ours_recursive_db_rlm.json
```

---

## 5. 统一模型配置

所有 LLM 方法必须使用相同配置。

示例：

```python
MODEL = "gpt-4o-mini"
TEMPERATURE = 0
MAX_TOKENS = 1024
N_ATTEMPTS = 1
```

统一要求：

- 相同模型
- 相同 Temperature
- 相同最大 Token
- 相同样本
- 相同重试规则
- 相同随机种子（如果 Provider 支持）

除非方法定义明确允许，否则不能额外重试。

正式实验必须记录实际配置，不能只依赖代码中的默认值。

---

## 6. 统一 SQL 执行器

所有方法必须使用相同的 SQL 执行函数。

基本接口：

```python
def execute_sql(db_path, sql):
    ...
    return {
        "answer": result,
        "error": None,
    }
```

执行失败：

```json
{
  "answer": null,
  "error": "error message"
}
```

推荐安全要求：

- 只允许 `SELECT`、`WITH` 和只读 `PRAGMA`
- 禁止 `INSERT`、`UPDATE`、`DELETE`、`DROP`
- 设置执行超时
- 限制最大返回行数
- 数据库使用只读连接

预测 SQL 和 gold SQL 必须使用同一个执行器。

---

## 7. 统一评测函数

主要指标：

```text
Execution Accuracy
```

定义：

```text
Execute(predicted_sql) == Execute(gold_sql)
```

基础示例：

```python
def normalize_answer(answer):
    if answer is None:
        return None
    return sorted(tuple(row) for row in answer)


def is_correct(pred_answer, gold_answer):
    return normalize_answer(pred_answer) == normalize_answer(gold_answer)
```

注意：

- 对没有顺序要求的问题，可以按多重集合比较。
- 对包含 `ORDER BY` 或明确排序要求的问题，必须保留顺序。
- 不能简单地将所有结果排序，否则错误顺序也可能被判正确。
- 空结果需要谨慎处理，错误 SQL 和 gold SQL 都返回空结果时可能造成假阳性。

---

## 8. 统一 Schema 格式

所有使用 Schema 的方法都应使用同一个提取器。

格式示例：

```text
Table: employees

Columns:
- id INTEGER PRIMARY KEY
- name TEXT
- department_id INTEGER
- salary REAL

Foreign keys:
- department_id -> departments.id
```

不要让不同方法分别使用：

- JSON Schema
- 自然语言描述
- 不同字段命名
- 手工编写的 Schema

Baseline 2 可以从统一 Schema 中检索子集，但基础信息来源必须一致。

---

## 9. 统一 Prompt 输出要求

各方法可以使用不同策略，但最终输出要求一致：

```text
根据可用的数据库信息和用户问题生成 SQL。

只返回可执行 SQL。
不要解释。
不要使用 Markdown 代码块。
```

最终结果必须是可以交给 SQLite 执行器的 SQL。

Agent 的中间 Action 可以使用 JSON，但最终 Action 必须包含 SQL。

---

## 10. 方法约束

### Baseline 1：直接 LLM + 完整 Schema

允许：

```text
用户问题
+
完整数据库 Schema
```

禁止：

```text
数据库查询
表内容检查
中间探索
Self-check
重试
递归
```

流程：

```text
问题
  ↓
完整 Schema
  ↓
LLM
  ↓
SQL
```

### Baseline 2：一次 Schema 检索 + Text-to-SQL

允许：

```text
用户问题
+
检索后的 Top-K 表和字段
```

检索时可以保留：

- 主键
- 外键
- 连接所需字段

禁止：

```text
查看数据库内容
SQL 执行反馈
递归推理
重试
```

流程：

```text
问题
  ↓
一次 Schema 检索
  ↓
局部 Schema
  ↓
LLM
  ↓
SQL
```

### Baseline 3：非递归数据库 Agent

允许：

```text
Schema 探索
表内容采样
SQL 执行
数据库 Observation
多步推理
SQL 错误修正
```

禁止：

```text
递归子 Agent
递归问题分解
```

流程：

```text
问题
  ↓
Agent
  ↓
探索表和 Schema
  ↓
执行 SQL
  ↓
观察结果
  ↓
继续探索或修正
  ↓
最终 SQL
```

推荐使用结构化 Action：

```json
{
  "action": "describe_table",
  "arguments": {
    "table": "employees"
  }
}
```

最终 Action：

```json
{
  "action": "final_sql",
  "sql": "SELECT ..."
}
```

### Recursive DB-RLM

允许：

```text
Schema 探索
数据库查询
递归推理
子问题分解
子 Agent 调用
证据聚合
```

流程：

```text
问题
  ↓
根 Agent
  ↓
探索数据库
  ↓
创建子问题
  ↓
递归 Agent
  ↓
返回证据
  ↓
根 Agent 聚合
  ↓
最终 SQL / 答案
```

Recursive 方法必须记录：

- 子问题
- 父子关系
- 每层 Trace
- 最大递归深度
- 子 Agent 数量
- 总工具调用
- 总 Token

---

# Part B：统一数据准备

## 11. 数据来源

所有方法使用相同的 Spider 1.0：

- 自然语言问题
- SQLite 数据库
- gold SQL
- Schema 信息

官方页面：

```text
https://yale-lily.github.io/spider
```

项目中的下载目录：

```text
data/spider_data/
```

准备命令：

```bash
python scripts/prepare_spider.py
```

---

## 11.1 Spider 原始结构

```text
data/spider_data/
├── train_spider.json
├── dev.json
├── tables.json
└── database/
    ├── concert_singer/
    │   └── concert_singer.sqlite
    └── ...
```

Spider 原始数据不存入 Git，因为体积大且包含超过 GitHub 限制的文件。

---

## 11.2 问题与 Gold SQL

问题和 gold SQL 来自：

```text
train_spider.json
dev.json
```

Spider 原始格式：

```json
{
  "db_id": "concert_singer",
  "question": "How many singers do we have?",
  "query": "SELECT count(*) FROM singer"
}
```

转换后的统一格式：

```json
{
  "id": "dev_000001",
  "db_id": "concert_singer",
  "question": "How many singers do we have?",
  "gold_sql": "SELECT count(*) FROM singer"
}
```

字段映射：

| Spider 字段 | 项目字段 |
|---|---|
| `db_id` | `db_id` |
| `question` | `question` |
| `query` | `gold_sql` |

---

## 11.3 数据库来源

SQLite 数据库由 Spider 提供。

原始路径：

```text
data/spider_data/database/concert_singer/concert_singer.sqlite
```

项目统一访问路径：

```text
data/databases/concert_singer/concert_singer.sqlite
```

`prepare_spider.py` 默认创建符号链接，避免重复复制数据库。

---

## 11.4 Schema 来源

Schema 必须直接从 SQLite 自动提取。

示例：

```sql
PRAGMA table_info("singer");
PRAGMA foreign_key_list("singer");
```

输出：

```text
Table: singer

Columns:
- singer_id INTEGER PRIMARY KEY
- name TEXT
- age INTEGER
```

统一 Schema 用于：

- Baseline 1
- Baseline 2
- Baseline 3
- Recursive DB-RLM

不要手工编写 Schema 描述。

---

## 11.5 Gold Answer 生成

Spider 不直接提供 gold answer。

Gold answer 通过执行 gold SQL 生成：

```text
gold_sql
  ↓
SQLite 执行
  ↓
gold_answer
```

示例：

```sql
SELECT count(*)
FROM singer;
```

结果：

```json
{
  "gold_answer": [
    [6]
  ]
}
```

Gold SQL 和预测 SQL 必须使用相同 SQL 执行器。

---

## 11.6 最终数据流

```text
Spider Dataset
  ↓
question + db_id + gold_sql
  ↓
SQLite DB + Schema Extractor
  ↓
Baseline 1 / Baseline 2 / Baseline 3 / Recursive DB-RLM
  ↓
predicted_sql
  ↓
执行 SQL
  ↓
predicted_answer
  ↓
与 gold_answer 比较
  ↓
Execution Accuracy
```

---

# 推荐项目结构

```text
AgenticSearch/
├── data/
├── baselines/
│   ├── baseline_1_direct_llm_schema.py
│   ├── baseline_2_direct_text_to_sql.py
│   └── baseline_3_non_recursive_db_agent.py
├── ours/
│   ├── db_environment.py
│   ├── subquestion_agent.py
│   ├── recursive_controller.py
│   └── recursive_db_rlm.py
├── shared/
│   ├── config.py
│   ├── schema_utils.py
│   ├── sql_executor.py
│   ├── evaluator.py
│   └── io_utils.py
├── scripts/
├── prompts/
└── results/
```

---

# 实验前必须统一的事项

开始正式实验前，两人必须确认：

1. 数据集输入格式
2. 固定样本 ID
3. 数据库目录结构
4. 输出 JSON 格式
5. 模型和生成参数
6. SQL 执行器
7. 评测指标
8. 重试和预算规则

只要这些组件保持一致，三个 Baseline 和 Recursive DB-RLM 才能进行公平比较。
