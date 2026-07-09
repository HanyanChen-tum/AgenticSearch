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

The current experiments use BIRD Mini-Dev. Spider 1.0 is no longer part of
the project dataset or evaluation plan.

It contains:

```text
Natural language questions

SQLite databases

Ground-truth SQL queries
```

---

# Unified Data Format

BIRD examples use the following unified format:

```json
{
    "id": "bird_mini_dev_000000",

    "db_id": "debit_card_specializing",

    "question":
    "What is the ratio of customers who pay in EUR against customers who pay in CZK?",

    "gold_sql":
    "SELECT ..."
}
```

The prepared file is `data/processed/bird_mini_dev_questions.json`.

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

Prepare BIRD Mini-Dev:

```bash
python scripts/prepare_bird.py --database-mode copy
```

Run the focused bounded-schema RLM pilot:

```powershell
.\.venv\Scripts\python.exe scripts\run_rlm_schema_suite.py `
  --limit 10 `
  --top-k 5 10 20 `
  --depths 0 1 2 `
  --model "<fixed-model>" `
  --temperature 0
```

The BIRD Mini-Dev helper expects the official complete package archive at:

```text
data/raw/bird/minidev_0703.zip
```

It writes:

```text
data/processed/bird_mini_dev_questions.json
data/databases/{db_id}/{db_id}.sqlite
```

For compatibility with the current runners, the script appends BIRD `evidence`
to the natural-language `question` by default. Use `--exclude-evidence` to keep
the original question text unchanged.

The command expects the downloaded Spider dataset in `data/spider_data/`.
See the [Dataset](#dataset) section for the required layout and alternative
options.

Run baselines:

```bash
python scripts/run_baseline_1.py

python scripts/run_baseline_2.py

python scripts/run_baseline_3.py
```

Run baselines on BIRD Mini-Dev:

```bash
python scripts/run_baseline_1.py --dataset data/processed/bird_mini_dev_questions.json
python scripts/run_baseline_2.py --dataset data/processed/bird_mini_dev_questions.json
python scripts/run_baseline_3.py --dataset data/processed/bird_mini_dev_questions.json
```

Run all three baselines sequentially over the complete development set:

```bash
python scripts/run_all_baselines.py
```

For a small smoke test before the full experiment:

```bash
python scripts/run_all_baselines.py --limit 10
```

The unified runner writes all three result files and
`results/summary_metrics.json`. It also accepts `--top-k-tables`,
`--top-k-columns`, `--max-steps`, and `--results-dir`.

Baseline 3 runs a single non-recursive agent for multiple database-tool steps.
Use `--max-steps` to control its exploration budget:

```bash
python scripts/run_baseline_3.py --limit 10 --max-steps 8
```

Its result rows include `agent_steps`, `tool_calls`, `termination_reason`, and
`tool_trace` diagnostics in addition to the unified evaluation fields.

Run DB-RLM ablations:

```bash
python scripts/run_ours.py
```

The `ours` runner is designed for incremental ablations. It starts from a
simple DB agent configuration and lets you enable one feature at a time:

```bash
# DB agent without recursive sub-questions
python scripts/run_ours.py --limit 10 --no-recursion --prompt-version basic

# Add metadata extraction
python scripts/run_ours.py --limit 10 --no-recursion --prompt-version basic --use-metadata

# Add query enrichment based on schema tokens and sampled values
python scripts/run_ours.py --limit 10 --no-recursion --prompt-version basic --use-metadata --use-enrichment

# Add automatic probe queries and store their results in the context/workspace
python scripts/run_ours.py --limit 10 --no-recursion --prompt-version basic --use-metadata --use-enrichment --use-probe-queries

# Add RLM-style recursive sub-questions
python scripts/run_ours.py --limit 10 --use-metadata

# Add an evidence workspace
python scripts/run_ours.py --limit 10 --use-metadata --use-workspace --prompt-version workspace
```

Recursive DB-RLM uses the same database tools as the non-recursive DB agent.
When recursion is enabled, it also exposes this helper to the root agent:

```python
answer_subquestion("focused database sub-question")
```

When metadata is enabled, pre-extracted table, column, row-count, and foreign
key metadata is included before online schema exploration. When query
enrichment is enabled, the runner adds a separate pre-reasoning stage that
infers likely tables, likely columns, matched cell values, and numeric
mentions from the question plus sampled rows. When probe queries are enabled,
the runner executes a few exploratory read-only SQL queries up front and
injects the results into the initial context. When workspace is enabled, the
agent gets a restricted model workspace. It can store compact evidence, save
named intermediate results, read a generated schema snapshot, read non-secret
project text files, write note/script artifacts under `results/model_workspace`,
run small restricted Python scripts, inspect execution results, and revise SQL
after errors.

Workspace mode exposes these tools:

```python
workspace.add(note, data)
workspace.read()
workspace.save_result(name, data)
workspace.load_result(name)
workspace.list_files(relative_dir="")
workspace.read_file(relative_path, max_chars=4000)
workspace.read_schema_file(max_chars=6000)
workspace.write_note_file(name, content)
workspace.write_python_script(name, code)
workspace.run_python_script(name)
workspace.run_python(code)
```

The workspace is intentionally restricted: SQL is read-only, repo file reads
block secrets such as `.env`, and file writes are limited to
`results/model_workspace`.

Current `ours` ablation flags:

```text
--no-recursion
--use-metadata
--use-enrichment
--use-probe-queries
--use-workspace
--prompt-version {basic,recursive,workspace}
```

Each result row records its `ablation_config`. If `--output` is omitted, the
runner writes a variant-specific result file such as:

```text
results/ours_no_rlm_prompt_basic.json
results/ours_metadata_no_rlm_prompt_basic.json
results/ours_metadata_rlm.json
results/ours_metadata_rlm_workspace_prompt_workspace.json
```

You can still provide an explicit output path:

```bash
python scripts/run_ours.py --use-metadata --output results/ours_metadata_rlm.json
```

Evaluate:

```bash
python scripts/evaluate_results.py
```

For ablation comparisons, pass the specific result files:

```bash
python scripts/evaluate_results.py \
  --result-files \
  results/baseline_3_non_recursive_db_agent.json \
  results/ours_no_rlm_prompt_basic.json \
  results/ours_metadata_no_rlm_prompt_basic.json \
  results/ours_metadata_rlm.json
```

Analyze errors:

```bash
python scripts/analyze_errors.py
```

The error analysis script writes:

```text
results/error_analysis.json
```

For ablation runs, `scripts/run_ours.py` writes variant-specific files such as
`ours_no_rlm_prompt_basic.json`, `ours_metadata_no_rlm_prompt_basic.json`,
`ours_metadata_rlm.json`, and
`ours_metadata_rlm_workspace_prompt_workspace.json`.

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

* [x] Dataset preparation script
* [ ] Local Spider databases available in `data/databases/`
* [x] Baseline 1 implementation
* [x] Baseline 2 implementation
* [x] Baseline 3 implementation
* [x] Recursive DB-RLM implementation
* [x] DB-RLM ablation switches
* [x] Metadata extraction module
* [x] Evidence workspace module
* [x] Evaluation script
* [x] Error analysis script
* [ ] Full Recursive DB-RLM experiment run

---

# Contributors

TBD
