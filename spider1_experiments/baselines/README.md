# Baselines

This document defines the baseline methods, the proposed recursive DB-RLM method, and the unified standards needed to compare all methods fairly.

## Method Overview

### Baseline 1: Direct LLM + Full Schema

Standard text-to-SQL baseline.

- Input: user question + full database schema
- Output: SQL
- Evaluation: execute SQL and compare the answer

Research question:

> Is full-schema, one-pass reasoning enough?

### Baseline 2: One-shot Schema Retrieval + Text-to-SQL

- Input: user question
- Step 1: retrieve top-k relevant tables / columns
- Step 2: keep primary-key / foreign-key columns for retrieved tables
- Step 3: provide retrieved schema + question to the LLM
- Output: SQL

Research question:

> If the schema scope is reduced first, is ordinary text-to-SQL already enough?

### Baseline 3: Non-recursive DB Agent

The LLM can call database tools over multiple steps:

```text
SHOW_TABLES()
DESCRIBE_TABLE()
SAMPLE_ROWS()
EXECUTE_SQL()
```

Research question:

> Is multi-step tool exploration alone enough?

### Ours: Recursive DB-RLM

- The root RLM can decompose a question into sub-questions.
- Sub-questions can be sent to `rlm_query()`.
- Each sub-RLM can independently explore schema, tables, join paths, and SQL fragments.
- The root RLM aggregates sub-results and generates the final SQL or answer.

Research question:

> Is recursive decomposition with independent sub-exploration stronger than a normal multi-step agent?

## Experiment Metrics

- SQL execution accuracy
- Exact match / component match
- Token usage
- Number of DB tool calls
- Latency
- Failure type:
  - wrong table
  - wrong join
  - wrong aggregation
  - invalid SQL

## Benchmark

Spider Benchmark.

---

## Unified Standards for All Baselines

Before implementing different baselines, define common interfaces and rules to make sure all methods are comparable.

The following parts must be shared across:

- Baseline 1: Direct LLM + Full Schema
- Baseline 2: One-shot Schema Retrieval + Text-to-SQL
- Baseline 3: Non-recursive DB Agent
- Ours: Recursive DB-RLM

```text
Part A:
Unified Implementation Interface
(input/output, prompt, evaluator)

Part B:
Unified Data Preparation
(dataset/database/schema/gold SQL source)
```

---

## Part A: Unified Implementation Interface

### 1. Unified Input Format

All methods should read the same dataset format.

Example:

```json
{
  "id": "q001",
  "db_id": "company",
  "question": "Which department has the highest average salary?",
  "gold_sql": "SELECT ..."
}
```

Required fields:

- `id`
- `db_id`
- `question`
- `gold_sql`

Field meanings:

| Field | Meaning |
| --- | --- |
| `id` | Unique question identifier |
| `db_id` | Corresponding database |
| `question` | Natural language query |
| `gold_sql` | Ground truth SQL query |

### 2. Unified Database Path

All baselines should access databases using the same path structure:

```text
data/databases/{db_id}/{db_id}.sqlite
```

Example:

```text
data/databases/company/company.sqlite
```

The database loading logic should not be implemented separately in each baseline.

### 3. Unified Output Format

Every method should generate results using the same JSON structure.

Example:

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

Only these fields should differ between methods:

- `method`
- `predicted_sql`
- `predicted_answer`
- `correct`
- `error`
- `latency_seconds`
- `input_tokens`
- `output_tokens`

Methods may also include method-specific diagnostic metadata. For example,
Baseline 2 records the retrieved schema subset:

```json
{
  "retrieved_schema": "Table: ...",
  "top_k_tables": 5,
  "top_k_columns": 8
}
```

### 4. Unified Method Names

Use fixed method identifiers:

```text
baseline_1_direct_llm_schema
baseline_2_direct_text_to_sql
baseline_3_non_recursive_db_agent
ours_recursive_db_rlm
```

Corresponding output files:

```text
results/
├── baseline_1_direct_llm_schema.json
├── baseline_2_direct_text_to_sql.json
├── baseline_3_non_recursive_db_agent.json
└── ours_recursive_db_rlm.json
```

### 5. Unified Model Configuration

All LLM-based methods should use the same settings.

Example:

```python
MODEL = "gpt-4o-mini"
TEMPERATURE = 0
MAX_TOKENS = 1024
N_ATTEMPTS = 1
```

Rules:

- Same model
- Same temperature
- Same token limit
- Same number of attempts
- No additional retry unless explicitly allowed

### 6. Unified SQL Executor

All methods must use the same SQL execution function.

Example:

```python
import sqlite3


def execute_sql(db_path, sql):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql)
        result = cursor.fetchall()
        conn.close()

        return {
            "answer": result,
            "error": None,
        }

    except Exception as e:
        return {
            "answer": None,
            "error": str(e),
        }
```

This ensures execution errors are measured consistently.

### 7. Unified Evaluation Function

All methods should use the same evaluator.

Example:

```python
def normalize_answer(answer):
    if answer is None:
        return None

    return sorted(
        [
            tuple(row)
            for row in answer
        ]
    )


def is_correct(pred_answer, gold_answer):
    return (
        normalize_answer(pred_answer)
        ==
        normalize_answer(gold_answer)
    )
```

Primary metric:

```text
Execution Accuracy
```

Meaning:

```text
predicted SQL result == gold SQL result
```

### 8. Unified Schema Format

All methods using schema information should use the same schema extractor.

Example schema format:

```text
Table: employees

Columns:
- id INTEGER
- name TEXT
- department_id INTEGER
- salary REAL

Table: departments

Columns:
- id INTEGER
- name TEXT
```

Avoid different formats such as:

- JSON schema
- Natural language descriptions
- Custom table formats

### 9. Unified Prompt Output Requirement

Each baseline may use a different strategy, but the output rule must be the same:

```text
You are an expert text-to-SQL assistant.

Given the available database information and the user question,
generate the SQL query.

Only return the SQL query.
Do not provide explanations.
```

The final output must always be executable SQL.

### 10. Unified Baseline Constraints

#### Baseline 1: Direct LLM + Full Schema

Allowed:

```text
Question
+
Database schema
```

Not allowed:

```text
Database queries
Table content inspection
Intermediate exploration
Self-correction
Retry
```

Pipeline:

```text
Question
  |
Schema
  |
LLM
  |
SQL
```

#### Baseline 2: One-shot Schema Retrieval + Text-to-SQL

Allowed:

```text
Question
+
Retrieved top-k tables / columns
```

Not allowed:

```text
Database content inspection
SQL execution feedback
Recursive reasoning
Retry
```

Pipeline:

```text
Question
  |
Schema retrieval
  |
Retrieved schema
  |
LLM
  |
SQL
```

#### Baseline 3: Non-recursive DB Agent

Allowed:

```text
Schema inspection
Table content sampling
SQL execution
Database observation
Multi-step reasoning
```

Not allowed:

```text
Recursive sub-agents
Recursive problem decomposition
```

Example:

```text
Question
  |
Agent
  |
Explore table
  |
Run SQL
  |
Observe result
  |
Final SQL
```

#### Ours: Recursive DB-RLM

Allowed:

```text
Schema exploration
Database queries
Recursive reasoning
Sub-question decomposition
Sub-agent calls
```

Pipeline:

```text
Question
  |
Root Agent
  |
Explore database
  |
Create sub-question
  |
Recursive Agent
  |
Return result
  |
Final reasoning
  |
SQL / Answer
```

---

## Part B: Unified Data Preparation

### 11. Unified Data Source and Preparation

To make all baselines comparable, all methods should use the same benchmark dataset and database resources.

Recommended benchmark:

```text
Spider Text-to-SQL Dataset
```

The dataset provides:

- Natural language questions
- SQLite databases
- Gold SQL queries
- Database schema information

### 11.1 Dataset Source

We use the Spider dataset as the shared benchmark.

Downloaded structure:

```text
spider/
├── train_spider.json
├── dev.json
├── database/
│   ├── concert_singer/
│   │   └── concert_singer.sqlite
│   └── other databases...
└── tables.json
```

### 11.2 Question and Gold SQL

Questions and gold SQL queries are obtained from:

```text
train_spider.json
or
dev.json
```

Original Spider format:

```json
{
  "db_id": "concert_singer",
  "question": "How many singers do we have?",
  "query": "SELECT count(*) FROM singer"
}
```

Converted unified format:

```json
{
  "id": "001",
  "db_id": "concert_singer",
  "question": "How many singers do we have?",
  "gold_sql": "SELECT count(*) FROM singer"
}
```

Mapping:

| Spider field | Our field |
| --- | --- |
| `db_id` | `db_id` |
| `question` | `question` |
| `query` | `gold_sql` |

### 11.3 Database Source

SQLite databases are directly provided by Spider.

Example:

```text
database/
└── concert_singer/
    └── concert_singer.sqlite
```

All methods access databases using:

```text
data/databases/{db_id}/{db_id}.sqlite
```

Example:

```text
data/databases/concert_singer/concert_singer.sqlite
```

### 11.4 Schema Source

Schema should be extracted automatically from the SQLite database.

All methods must use the same schema extraction function.

Example input:

```text
concert_singer.sqlite
```

Extractor:

```sql
PRAGMA table_info(table_name);
```

Output:

```text
Table: singer

Columns:
- singer_id INTEGER
- name TEXT
- age INTEGER

Table: concert

Columns:
- concert_id INTEGER
- concert_name TEXT
- singer_id INTEGER
```

This generated schema is used by:

- Baseline 1
- Baseline 2
- Baseline 3
- Recursive DB-RLM

Baseline 2 retrieves a top-k subset from this generated schema before
prompting the LLM. It preserves primary-key and foreign-key columns for
retrieved tables so join paths remain available.

Do not manually write schema descriptions.

### 11.5 Gold Answer Generation

Gold answers are not directly stored in the dataset.

They are generated by executing the gold SQL.

Process:

```text
gold_sql
  |
SQLite execution
  |
gold_answer
```

Example gold SQL:

```sql
SELECT count(*)
FROM singer;
```

Execution result:

```json
{
  "gold_answer": [
    [20]
  ]
}
```

The same SQL executor should be used for both:

- `gold_sql` execution
- `predicted_sql` execution

### 11.6 Final Data Flow

All methods follow the same pipeline:

```text
Spider Dataset
  |
  v
question
db_id
gold_sql
  |
  +----------------+
  |                |
  v                v
SQLite DB      Schema Extractor
  |
  v
Baseline 1
Baseline 2
Baseline 3
Recursive DB-RLM
  |
  v
predicted_sql
  |
  v
Execute SQL
  |
  v
predicted_answer
  |
  v
Compare with gold_answer
  |
  v
Execution Accuracy
```

---

## Recommended Project Structure

```text
project/
├── data/
├── baselines/
│   ├── baseline_1_direct_llm_schema.py
│   ├── baseline_2_direct_text_to_sql.py
│   └── baseline_3_non_recursive_db_agent.py
├── ours/
│   └── recursive_db_rlm.py
├── shared/
│   ├── config.py
│   ├── schema_utils.py
│   ├── sql_executor.py
│   ├── evaluator.py
│   └── io_utils.py
├── results/
└── prompts/
```

## Shared Configuration Example

`shared/config.py`

```python
MODEL = "gpt-4o-mini"
TEMPERATURE = 0
MAX_TOKENS = 1024
N_ATTEMPTS = 1

DATASET_PATH = "data/questions.json"
DATABASE_DIR = "data/databases"
RESULTS_DIR = "results"
```

## Most Important Things to Agree on First

Before implementation, we must agree on:

1. Dataset input format
2. Database directory structure
3. Output JSON format
4. SQL execution function
5. Evaluation metric

If these five components are shared, all baselines and our Recursive DB-RLM method can be compared fairly.
