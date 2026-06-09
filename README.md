# Recursive DB-RLM: Recursive Language Model for Structured Database Reasoning

## Overview

This project explores whether the recursive exploration paradigm of Recursive Language Models (RLMs) can be extended from unstructured information retrieval to structured database reasoning.

Instead of retrieving all database information at once, our method allows an agent to recursively explore database schemas, query relevant tables, create sub-questions, and gradually reason over structured data.

We evaluate whether recursive database exploration improves scalability, efficiency, and interpretability compared with standard Text-to-SQL approaches.

---

## Motivation

Traditional Text-to-SQL systems usually follow a direct generation pipeline:

```text
Question
    |
    v
LLM
    |
    v
SQL
```

However, complex database questions often require:

* understanding database structure
* exploring relevant tables
* performing intermediate reasoning
* decomposing complex questions

Inspired by Recursive Language Models, we introduce:

```text
Question

↓

Root Agent

↓

Explore Database

↓

Generate Sub-questions

↓

Recursive DB Agents

↓

Return Intermediate Results

↓

Final SQL / Answer
```

---

# Methods

We compare four methods:

## Baseline 1: Direct LLM + Full Schema

Standard text-to-SQL baseline.

The model receives only:

```text
User Question
+
Database Schema
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

Allowed:

* schema information

Not allowed:

* table content inspection
* SQL execution feedback
* recursive reasoning
* retry

Research question:

```text
Is full-schema, one-pass reasoning enough?
```

---

## Baseline 2: One-shot Schema Retrieval + Text-to-SQL

The model first retrieves a small schema subset, then performs ordinary
text-to-SQL generation in one pass. The retrieved column subset keeps the
top-k relevant columns and also preserves primary-key / foreign-key columns
needed for joins.

Pipeline:

```text
Question

↓

Retrieve top-k tables / columns

↓

Retrieved Schema

↓

LLM

↓

SQL
```

Allowed:

* natural language question
* one-shot schema retrieval
* retrieved top-k tables / columns
* primary-key / foreign-key columns for retrieved tables

Not allowed:

* database content inspection
* SQL execution feedback
* recursive reasoning
* retry

Research question:

```text
If the schema scope is reduced first, is ordinary text-to-SQL already enough?
```

---

## Baseline 3: Non-recursive DB Agent

A non-recursive database agent that can call database tools over multiple
steps.

Available tools:

```text
SHOW_TABLES()
DESCRIBE_TABLE()
SAMPLE_ROWS()
EXECUTE_SQL()
```

Pipeline:

```text
Question

↓

Agent

↓

Inspect Schema

↓

Sample Rows / Execute SQL

↓

Observe Result

↓

Final SQL
```

Allowed:

* schema inspection
* table content sampling
* SQL execution
* database observation
* multi-step reasoning

Not allowed:

* recursive sub-agent calls
* recursive problem decomposition

Research question:

```text
Is multi-step tool exploration alone enough?
```

---

## Ours: Recursive DB-RLM

Our method extends RLM-style recursive reasoning to databases.

Pipeline:

```text
Question

↓

Root DB Agent

↓

Schema Exploration

↓

Sub-question Generation

↓

Recursive DB Agent

↓

Return Evidence

↓

Final Reasoning

↓

SQL / Answer
```

Allowed:

* database exploration
* recursive decomposition
* sub-agent reasoning
* intermediate evidence aggregation

Research question:

```text
Is recursive decomposition with independent sub-exploration stronger than a normal multi-step agent?
```

---

# Dataset

We use the Spider Text-to-SQL benchmark.

It contains:

```text
Natural language questions

SQLite databases

Ground-truth SQL queries
```

Original structure:

```text
data/spider_data/

├── train_spider.json
├── dev.json
├── tables.json

└── database/
    ├── concert_singer/
    │   └── concert_singer.sqlite
    └── other databases
```

The Spider download is not stored in Git because it is large and contains
files above GitHub's 100 MB file-size limit. After cloning this repository,
download **Spider 1.0** from the official Yale page:

- Dataset page: https://yale-lily.github.io/spider
- Official code and evaluation repository: https://github.com/taoyds/spider

On the dataset page, use the **Spider Dataset** link in the **Getting Started**
section. It opens the official Google Drive download. This project uses Spider
1.0, not Spider 2.0.

After downloading the archive, extract it and place the extracted dataset at
`data/spider_data/`. The final layout must be:

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

Prepare all project inputs with one command:

```bash
python scripts/prepare_spider.py
```

This command:

1. Converts `train_spider.json` and `dev.json` to the unified project format.
2. Writes them to `data/processed/train_questions.json` and
   `data/processed/dev_questions.json`.
3. Creates database links under
   `data/databases/{db_id}/{db_id}.sqlite`.

Symbolic links are used by default, so preparing the data does not duplicate
the downloaded databases. To copy the databases instead, for example on a
system where symbolic links are unavailable, run:

```bash
python scripts/prepare_spider.py --database-mode copy
```

If Spider was extracted somewhere else, provide its directory:

```bash
python scripts/prepare_spider.py --spider-dir /path/to/spider
```

The source directory must contain `train_spider.json`, `dev.json`, and
`database/`. The command is safe to run again: existing prepared databases are
reused.

---

# Unified Data Format

Spider examples are converted into:

```json
{
    "id": "001",

    "db_id": "concert_singer",

    "question":
    "How many singers do we have?",

    "gold_sql":
    "SELECT count(*) FROM singer"
}
```

Mapping:

```text
Spider Field     Project Field

db_id        ->  db_id

question     ->  question

query        ->  gold_sql
```

---

# Project Structure

```text
AgenticSearch/

├── data/
│
├── shared/
│   ├── config.py
│   ├── data_loader.py
│   ├── schema_utils.py
│   ├── sql_executor.py
│   ├── evaluator.py
│   └── llm_client.py
│
├── baselines/
│
│   ├── baseline_1_direct_llm_schema.py
│   ├── baseline_2_direct_text_to_sql.py
│   └── baseline_3_non_recursive_db_agent.py
│
├── ours/
│
│   ├── recursive_db_rlm.py
│   ├── recursive_controller.py
│   ├── db_environment.py
│   └── subquestion_agent.py
│
├── prompts/
│
├── scripts/
│
├── results/
│
├── logs/
│
└── notebooks/
```

---

# Shared Components

All methods share the same:

## Schema Extractor

Input:

```text
SQLite Database
```

Output:

Example:

```text
Table: singer

Columns:

- singer_id INTEGER
- name TEXT
- age INTEGER
```

Used by:

* Baseline 1
* Baseline 2
* Baseline 3
* Recursive DB-RLM

Baseline 2 retrieves a top-k subset from this extracted schema instead of
passing the full schema to the LLM. It preserves primary-key and foreign-key
columns for retrieved tables so join paths remain available.

---

## SQL Executor

All generated SQL queries are executed using the same function.

Input:

```text
database path

+

SQL query
```

Output:

```json
{
    "answer": [[20]],

    "error": null
}
```

---

## Evaluation

Main metric:

## Execution Accuracy

Definition:

```text
Execute(predicted SQL)

==

Execute(gold SQL)
```

Additional metrics:

* SQL valid rate
* average latency
* token usage
* error rate

---

# Unified Output Format

Every method outputs:

```json
{
    "id": "q001",

    "method":
    "baseline_1_direct_llm_schema",

    "db_id":
    "company",

    "question":
    "...",

    "predicted_sql":
    "SELECT ...",

    "predicted_answer":
    [["HR",85000]],

    "gold_sql":
    "SELECT ...",

    "gold_answer":
    [["HR",85000]],

    "correct":
    true,

    "error":
    null,

    "latency_seconds":
    3.21
}
```

Baseline 2 may include additional retrieval metadata such as:

```json
{
    "retrieved_schema": "Table: ...",
    "top_k_tables": 5,
    "top_k_columns": 8
}
```

---

# Model Configuration

All LLM methods read the same settings from `.env`. To use Gemini:

```dotenv
LLM_PROVIDER=gemini
MODEL=gemini-2.0-flash
GEMINI_API_KEY=your_gemini_api_key_here
TEMPERATURE=0
MAX_TOKENS=1024
```

To use a locally deployed Qwen model through an OpenAI-compatible endpoint:

```dotenv
LLM_PROVIDER=openai_compatible
MODEL=Qwen/Qwen2.5-Coder-7B-Instruct
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=
TEMPERATURE=0
MAX_TOKENS=1024
```

Common endpoint values:

```text
vLLM:      http://localhost:8000/v1
Ollama:    http://localhost:11434/v1
LM Studio: http://localhost:1234/v1
```

---

# Running Experiments

Prepare dataset:

```bash
python scripts/prepare_spider.py
```

The command expects the downloaded Spider dataset in `data/spider_data/`.
See the [Dataset](#dataset) section for the required layout and alternative
options.

Run baselines:

```bash
python scripts/run_baseline_1.py

python scripts/run_baseline_2.py

python scripts/run_baseline_3.py
```

Run Recursive DB-RLM:

```bash
python scripts/run_ours.py
```

Evaluate:

```bash
python scripts/evaluate_results.py
```

---

# Experiment Results

Results are stored in:

```text
results/

├── baseline_1_direct_llm_schema.json

├── baseline_2_direct_text_to_sql.json

├── baseline_3_non_recursive_db_agent.json

└── ours_recursive_db_rlm.json
```

---

# Research Question

Can recursive exploration improve structured database reasoning compared with direct Text-to-SQL generation?

Specifically:

1. Does recursive decomposition improve complex query accuracy?

2. Does database exploration reduce hallucinated SQL?

3. Can recursive reasoning provide more interpretable intermediate steps?

---

# Status

* [ ] Dataset preparation
* [x] Baseline 1 implementation
* [x] Baseline 2 implementation
* [ ] Baseline 3 implementation
* [ ] Recursive DB-RLM implementation
* [ ] Evaluation
* [ ] Error analysis

---

# Contributors

TBD
