
````markdown
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
````

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

## Baseline 1: Direct LLM + Schema

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

* database content inspection
* SQL execution feedback
* recursive reasoning
* retry

---

## Baseline 2: Direct Text-to-SQL

A standard direct generation baseline.

Pipeline:

```text
Question

↓

LLM

↓

SQL
```

Allowed:

* natural language question
* minimal database information

Not allowed:

* database exploration
* execution feedback
* recursion

---

## Baseline 3: Non-recursive Database Agent

A database agent that can interact with the database.

Pipeline:

```text
Question

↓

Agent

↓

Inspect Schema

↓

Execute SQL

↓

Observe Result

↓

Final SQL
```

Allowed:

* schema inspection
* SQL execution
* iterative reasoning

Not allowed:

* recursive sub-agent calls
* recursive decomposition

---

## Proposed Method: Recursive DB-RLM

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

---

# Dataset

We use:

## Spider Text-to-SQL Dataset

Spider provides:

```text
Natural language questions

+

SQLite databases

+

Database schemas

+

Ground-truth SQL queries
```

Original structure:

```text
spider/

├── train_spider.json
├── dev.json
├── tables.json

└── database/
    |
    ├── concert_singer/
    │
    └── other databases
```

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
* Baseline 3
* Recursive DB-RLM

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

---

# Model Configuration

All LLM methods use identical settings:

```python
MODEL = "gpt-4o-mini"

TEMPERATURE = 0

MAX_TOKENS = 1024

N_ATTEMPTS = 1
```

---

# Running Experiments

Prepare dataset:

```bash
python scripts/prepare_spider.py
```

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
* [ ] Baseline 1 implementation
* [ ] Baseline 2 implementation
* [ ] Baseline 3 implementation
* [ ] Recursive DB-RLM implementation
* [ ] Evaluation
* [ ] Error analysis

---

# Contributors

TBD

