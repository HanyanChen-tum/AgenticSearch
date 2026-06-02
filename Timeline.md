# timeline

### Project Goal

Extend the recursive exploration paradigm of **RLMs** from unstructured information retrieval to **structured database environments**.

Instead of providing the entire database schema to an LLM at once, our system allows the model to:

1. Explore database schemas step by step
2. Query relevant tables
3. Spawn recursive agents when additional exploration is needed
4. Aggregate information and generate the final answer

The goal is to improve:

- scalability
- efficiency
- interpretability

for complex database reasoning tasks.

- 先复现原 RLM baseline
- 搭建数据库任务环境
- 做三个普通 baseline
- 实现自己的 Recursive DB-RLM
- 实验比较

# Team Roles

## Person A — RLM / Agent System

Main responsibility:

**Design and implement the recursive reasoning framework**

Focus areas:

- Understand original RLM repository
- Recursive agent architecture
- Agent communication
- Recursion control
- Prompt design
- DB-RLM implementation

---

## Person B — Database / Baselines / Evaluation

Main responsibility:

**Build the database environment and evaluate the system**

Focus areas:

- SQL databases
- Dataset preparation
- Text-to-SQL baselines
- Database tools
- Evaluation metrics
- Experiments

---

# Week 1 — Understanding & Setup

## Person A

Tasks:

- Run the original RLM repository
- Understand:
    - root agent
    - child agent creation
    - recursive calls
    - stopping conditions

Deliverables:

- Working RLM baseline
- Code structure analysis
- Identify where to modify RLM for databases

---

## Person B

Tasks:

- Prepare database benchmark environment
- Study datasets (e.g. Spider)
- Build SQLite execution tools

Implement:

- list tables
- inspect schema
- execute SQL queries

Deliverables:

- Working database environment
- Test questions and SQL execution pipeline

---

# Week 2–3 — Build Baselines

Goal:

Create comparison methods before building DB-RLM.

---

# Baseline 1: Direct LLM + Schema

Owner: Person B

Method:

Provide:

```
Question + Full Database Schema
```

to the LLM.

LLM directly generates SQL.

Measure:

- accuracy
- token usage

---

# Baseline 2: Text-to-SQL Agent

Owner: Person B

Method:

Allow the model to:

1. Generate SQL
2. Execute SQL
3. Observe errors
4. Fix SQL

Example:

```
Generate SQL
      |
Execute
      |
Error feedback
      |
Regenerate
```

---

# Baseline 3: Non-recursive DB Agent

Owner: Person A + B

Method:

Create a database agent with tools:

- list_tables()
- describe_table()
- execute_sql()

But:

No recursive child agents.

Flow:

```
Agent
 |
Explore schema
 |
Query database
 |
Answer
```

Deliverables:

Three completed baselines:

| Method | Status |
| --- | --- |
| Direct LLM + Schema | ✓ |
| Text-to-SQL Agent | ✓ |
| Non-recursive Agent | ✓ |

---

# Week 4–6 — Build Recursive DB-RLM

Main owner:

Person A

---

## Modify RLM for Database Tasks

Original:

```
child_agent(search_task)
```

Change to:

```
child_agent(database_task)
```

Example:

Root Agent:

"I need more information about users"

creates:

```
Child Agent:
Explore user-related tables
```

Child agent:

```
list_tables()

describe_table()

execute_sql()
```

Returns findings back to root.

---

## Add Recursion Control

Implement:

Maximum recursion depth:

Example:

```
Depth 0:

Root Agent

Depth 1:

Root
 |
Child

Depth 2:

Root
 |
Child
 |
Grandchild
```

Parameters:

- max_depth
- max actions
- token budget

---

## Person B During Week 4–6

Build evaluation pipeline:

Run:

- 100–500 database questions

Record:

- generated answer
- SQL result
- accuracy
- runtime
- token usage

---

# Week 7–8 — Experiments

Compare:

## Accuracy

How many questions are answered correctly.

---

## Efficiency

Measure:

- token usage
- execution time

Example:

| Method | Tokens |
| --- | --- |
| Direct Schema | 5000 |
| DB-RLM | 2000 |

---

## Scalability Test

Increase database size:

- small database
- medium database
- large database

Expected result:

Direct LLM:

- struggles with large schemas

DB-RLM:

- explores only relevant parts

---

# Week 9–10 — Optimization

## Person A

Improve recursive decision making.

Research:

When should the model create child agents?

Possible methods:

Rule-based:

```
if uncertainty is high:
    spawn child agent
```

or prompt-based:

```
Create a child agent if more database exploration is required.
```

Test:

- recursion depth 0
- recursion depth 1
- recursion depth 2

---

## Person B

Ablation studies:

Example:

| Model | Accuracy |
| --- | --- |
| No recursion | 75% |
| Depth 1 | 82% |
| Depth 2 | 85% |

Goal:

Prove recursion improves performance.

---

# Week 11 — Paper & Documentation

Write:

## Introduction

Problem:

Large databases are difficult for LLMs because full schemas are too large.

---

## Method

Explain:

Recursive Database Exploration Framework

---

## Experiments

Compare:

| Method | Accuracy | Tokens |
| --- | --- | --- |
| Direct LLM |  |  |
| DB Agent |  |  |
| DB-RLM |  |  |

---

# Week 12 — Final Delivery

Complete:

- Clean GitHub repository
- Documentation
- Demo notebook
- Final experiments
- Presentation slides

---

# Final Contribution Split

## Person A

Main contribution:

**Recursive Agent System**

Responsible for:

- RLM implementation
- Agent framework
- Recursive exploration
- Prompting
- Depth control

---

## Person B

Main contribution:

**Database and Evaluation System**

Responsible for:

- Dataset preparation
- SQL environment
- Baselines
- Evaluation pipeline
- Experiments

---

# Expected Final Project Structure

```
DB-RLM/

├── agents/
│   └── recursive_agent.py

├── database/
│   └── sql_tools.py

├── baselines/
│   ├── direct_llm.py
│   ├── text2sql.py
│   └── db_agent.py

├── experiments/

├── results/

├── demo.ipynb

└── paper.pdf
```

Final outcome:

A working **Recursive Database Reasoning Agent** that demonstrates whether recursive exploration can improve LLM performance on large structured databases.