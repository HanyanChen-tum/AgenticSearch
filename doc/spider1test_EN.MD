# Spider 1.0 Experiment Report and Result Analysis

## 1. Objective

This experiment compares four Text-to-SQL approaches on the Spider 1.0 SQLite development set: direct generation with the full schema, direct generation with retrieved schema, a non-recursive database agent, and a DB-RLM with recursive interfaces.

The main research question is whether database tool use and recursive decomposition improve execution accuracy enough to justify their additional latency, token consumption, and tool calls.

This report describes the implementation currently present in the repository and the complete results stored under `results/spider1_full_dev/`. The current `RecursiveDBRLM` is a project-specific recursive database agent. It is not a subclass of the MIT RLM implementation and does not use a RestrictedPython REPL.

## 2. Dataset and Configuration

### 2.1 Dataset

- Dataset: Spider 1.0
- Evaluation split: complete development set
- Questions: 1,034
- SQLite databases: 166
- Training examples: 7,000, converted but not used in this evaluation
- Question file: `data/processed/dev_questions.json`
- Database path: `data/databases/{db_id}/{db_id}.sqlite`

The primary metric is execution accuracy. The predicted and gold SQL statements are executed independently, and their result multisets are compared. Row order is ignored, while duplicate counts and SQLite value types are preserved. Therefore, integer `1` and string `"1"` are not treated as equal.

### 2.2 Model configuration

The complete experiment used a local Qwen model through Ollama's OpenAI-compatible endpoint:

```dotenv
LLM_PROVIDER=openai_compatible
MODEL=qwen2.5-coder:7b
LLM_BASE_URL=http://localhost:11434/v1
TEMPERATURE=0
MAX_TOKENS=1024
```

### 2.3 Metrics

- Execution Accuracy: whether predicted and gold SQL return the same result
- SQL Valid Rate: whether the predicted SQL executes successfully
- Exact Match: whether normalized predicted SQL equals normalized gold SQL
- Component Match: whether tables, columns, joins, and aggregations all match
- Latency: average runtime per question
- Token Usage: total input and output tokens
- Tool Calls: total and average database tool calls
- Failure Type: `invalid_sql`, `wrong_table`, `wrong_join`, `wrong_aggregation`, or `wrong_result`

## 3. Baselines

### 3.1 Baseline 1: Direct LLM with full schema

Implementation: `spider1_experiments/baselines/baseline_1_direct_llm_schema.py`

```text
Question + complete database schema
                 ↓
            One LLM call
                 ↓
           Predicted SQL
```

The model receives every table, column, primary key, and foreign key in the current database. It cannot inspect table contents, execute SQL during generation, or repair its answer. This baseline measures the effectiveness of one-pass generation with complete structural information.

### 3.2 Baseline 2: Retrieved schema with direct generation

Implementation: `spider1_experiments/baselines/baseline_2_direct_text_to_sql.py`

The method ranks tables and columns using lexical overlap with the question, then constructs a reduced schema:

- Up to five tables
- Up to eight highly relevant columns per table
- Primary-key and foreign-key columns are retained to preserve join paths
- No table content inspection
- No intermediate SQL execution
- One final LLM generation call

```text
Question
   ↓
Lexical schema retrieval
   ↓
Relevant tables, columns, and keys
   ↓
One LLM call
   ↓
Predicted SQL
```

This baseline tests whether removing irrelevant schema is more useful than providing the complete schema.

### 3.3 Baseline 3: Non-recursive database agent

Implementation: `spider1_experiments/baselines/baseline_3_non_recursive_db_agent.py`

The model can perform up to eight interaction steps. Each step returns one JSON action:

- `SHOW_TABLES`
- `DESCRIBE_TABLE`
- `SAMPLE_ROWS`
- `EXECUTE_SQL`
- `FINAL`

The agent can inspect schema, sample data, execute candidate SQL, and continue after observing database feedback. It cannot create child agents. If it reaches the step limit without returning `FINAL`, the runner falls back to the last successfully executed SQL.

This baseline separates the effect of database interaction from the effect of recursive decomposition.

## 4. DB-RLM Implementation

### 4.1 Architecture

```text
Question
   ↓
RecursiveDBRLM
   ↓
Root SubquestionAgent ── optional ──> Child SubquestionAgent
   ↓                                      ↓
Database evidence and SQL              Child evidence
   └─────────────────┬────────────────────┘
                     ↓
              Final SQL synthesis
                     ↓
             Execution and repair
```

The implementation consists of four main components:

- `db_environment.py`: bounded, read-only SQLite interface
- `recursive_controller.py`: recursion limits, shared budgets, and trace collection
- `subquestion_agent.py`: one agent for one task or subtask
- `recursive_db_rlm.py`: root orchestration, SQL synthesis, repair, and evaluation

These files are located under `spider1_experiments/ours/`.

### 4.2 DatabaseEnvironment

`DatabaseEnvironment` opens SQLite with URI `mode=ro` and exposes:

- `list_tables()`
- `describe_table()`
- `sample_rows()`
- `execute_sql()` for bounded intermediate results
- `execute_sql_full()` for the final complete result

Intermediate statements must begin with `SELECT`, `WITH`, or `EXPLAIN`. Table names are validated and quoted before schema inspection or sampling.

### 4.3 RecursiveController

The controller maintains shared limits for the root and all child agents:

- Maximum recursion depth: 2
- Maximum global actions: 24
- Maximum actions per agent: 8
- Maximum children per agent: 3
- Token budget: 12,000
- Maximum observation size: 5,000 characters
- Maximum intermediate rows: 20
- Final repair attempts: 1

Each action records the agent ID, depth, action, arguments, and observation. All agents share the action and token budgets, preventing unbounded recursion.

### 4.4 SubquestionAgent

Each agent handles one task and selects exactly one JSON action per turn:

```json
{"action":"list_tables","arguments":{}}
{"action":"describe_table","arguments":{"table":"table_name"}}
{"action":"sample_rows","arguments":{"table":"table_name","limit":5}}
{"action":"execute_sql","arguments":{"sql":"SELECT ..."}}
{"action":"spawn_subagent","arguments":{"task":"A narrower independent subtask"}}
{"action":"finish","arguments":{"summary":"Evidence summary","candidate_sql":"Optional SQL"}}
```

When `spawn_subagent` is selected, the parent reserves an action and recursively calls the same `SubquestionAgent.run()` method. The child receives the parent task and observations, then returns a summary and optional candidate SQL.

If the context exceeds its character budget, the agent retains only recent observations, compressed child summaries, and the tail of the available evidence.

### 4.5 Final SQL synthesis and repair

After the root agent finishes, `RecursiveDBRLM` sends the original question, root result, and complete trace to another LLM call that returns final SQLite SQL. The SQL is executed and, if it fails and token budget remains, the model receives the error for one repair attempt.

One important design choice is that a new synthesis call is normally made even when the root agent already produced a tested `candidate_sql`. The tested candidate is used directly only when the token budget has been exhausted. The additional synthesis can improve an incomplete candidate, but it can also damage an already correct query. This should be evaluated through an ablation study.

### 4.6 Incremental saving and resume support

All four runners save results by question ID:

- Results are written after every completed question
- A temporary file and `os.replace()` provide atomic replacement
- Existing IDs are skipped when a run is restarted
- Final result order always matches dataset order

## 5. Experiment Process

### 5.1 Environment validation

The virtual environment, SQLite data, schema extraction, and LLM endpoint were checked with:

```powershell
python -m spider1_experiments.scripts.smoke_test --limit 1 --llm
```

The test loaded the `concert_singer` database and the LLM returned `SELECT 1;`, confirming that the complete execution path was available.

A five-question DB-RLM smoke test then scored 4/5, or 80%. This was only a pipeline check and was not representative of complete-dataset performance.

### 5.2 Evaluator failure and fix

The first full Baseline 1 run failed on question 434, `dev_000433`. The `birth_date` column in the `wta_1` database contains both strings and integers. The old evaluator sorted raw result tuples and raised:

```text
TypeError: '<' not supported between instances of 'str' and 'int'
```

The evaluator was changed to compare typed row multisets. The fix:

- Supports heterogeneous SQLite values
- Ignores row order
- Preserves duplicate counts
- Preserves differences between strings and integers

Incremental atomic saving and resume support were added at the same time. Three new unit tests passed.

### 5.3 Full-run timeline

| Method | Start | Finish | Total runtime |
|---|---|---|---:|
| Baseline 1 | 2026-06-22 01:25:05 | 02:15:49 | About 50 min 44 sec |
| Baseline 2 | 2026-06-22 02:15:49 | 03:07:41 | About 51 min 52 sec |
| Baseline 3 | 2026-06-22 03:07:41 | 07:21:56 | About 4 hr 14 min |
| DB-RLM | 2026-06-22 15:41:15 | 22:47:57 | About 7 hr 7 min |

The main commands were:

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

## 6. Complete Results

### 6.1 Core metrics

| Method | Correct | Execution accuracy | SQL valid | Exact match | Full component match | Avg. latency |
|---|---:|---:|---:|---:|---:|---:|
| Baseline 1: Full schema | 758/1034 | 73.31% | 93.42% | 31.14% | 41.59% | 2.79 s |
| Baseline 2: Retrieved schema | **774/1034** | **74.85%** | 96.81% | **33.56%** | **42.46%** | 2.85 s |
| Baseline 3: Non-recursive agent | 702/1034 | 67.89% | **97.29%** | 28.82% | 41.39% | 14.49 s |
| DB-RLM | 671/1034 | 64.89% | 91.01% | 20.12% | 35.69% | 24.36 s |

Baseline 2 was the best complete-run method. It exceeded Baseline 1 by 1.54 percentage points, Baseline 3 by 6.96 points, and DB-RLM by 9.96 points.

### 6.2 Cost

| Method | Input tokens | Output tokens | Tool calls | Avg. tools/question |
|---|---:|---:|---:|---:|
| Baseline 1 | 371,834 | 30,984 | 0 | 0 |
| Baseline 2 | **290,347** | **30,451** | 0 | 0 |
| Baseline 3 | 3,388,091 | 116,918 | 4,541 | 4.39 |
| DB-RLM | 8,376,405 | 309,637 | 7,611 | 7.36 |

Baseline 2 used approximately 21.9% fewer input tokens than Baseline 1 while improving accuracy. Baseline 3 used about 11.7 times as many input tokens as Baseline 2, and DB-RLM used about 28.9 times as many, while both produced lower accuracy.

### 6.3 Failure types

| Method | Invalid SQL | Wrong table | Wrong join | Wrong aggregation | Wrong result |
|---|---:|---:|---:|---:|---:|
| Baseline 1 | 68 | 62 | 61 | 15 | 70 |
| Baseline 2 | 33 | 80 | **56** | 14 | 77 |
| Baseline 3 | **28** | 112 | 79 | 20 | 93 |
| DB-RLM | 93 | 77 | 94 | 15 | 84 |

Baseline 3 had the highest SQL validity and the fewest invalid queries. Database execution feedback therefore helped syntax and schema validation. However, it selected wrong tables and joins more often, so executable SQL did not translate into higher answer accuracy.

DB-RLM ended with the largest number of invalid queries. One repair was attempted for 56 questions, but 93 questions still had execution errors after the full run. The current one-repair policy and final synthesis stage are insufficient.

## 7. Analysis

### 7.1 Schema retrieval was the most effective improvement

Baseline 2 achieved the highest execution accuracy, exact match, full component match, and the lowest token cost. For this 7B model, removing irrelevant schema was more effective than adding agent steps. The full schema introduced noise, while simple lexical retrieval reduced the search space without removing required key relationships.

### 7.2 More tool calls did not improve accuracy

Baseline 3 was approximately 5.1 times slower than Baseline 2 and used 11.7 times as many input tokens, but its accuracy was 6.96 percentage points lower. The model used tools to reduce invalid SQL but did not reliably integrate multi-step evidence into the correct tables, joins, and semantics.

The bottleneck is therefore not simply lack of database access. Planning, state retention, and final synthesis are substantial limitations for the small model.

### 7.3 No recursion occurred in the complete DB-RLM run

This is the most important diagnostic result:

- All 1,034 questions had `max_depth_reached = 0`
- `spawn_subagent` occurred zero times
- No question created a child agent
- The average 7.36 actions and 8.41 LLM calls per question occurred in the root-agent, synthesis, and repair pipeline

Therefore, the reported 64.89% DB-RLM result evaluates a root database agent with additional SQL synthesis and repair, not recursive decomposition. It cannot establish whether recursion helps or hurts. It only shows that the current prompt and 7B model did not select the recursive action.

### 7.4 Pairwise DB-RLM comparison

Comparing predictions on the same 1,034 questions:

| Compared with | Correct only for DB-RLM | Correct only for baseline | Net change |
|---|---:|---:|---:|
| Baseline 1 | 65 | 152 | -87 |
| Baseline 2 | 58 | 161 | -103 |
| Baseline 3 | 74 | 105 | -31 |

DB-RLM solved some questions missed by every baseline, but it also lost more questions that the baselines answered correctly. Its smallest gap was against Baseline 3, which is consistent with the observation that no recursive behavior occurred.

### 7.5 Exact match is not a substitute for execution accuracy

Exact-match scores were much lower than execution accuracy for every method. Baseline 2, for example, obtained 33.56% exact match but 74.85% execution accuracy. Multiple syntactically different SQL queries can be semantically equivalent. Conclusions should therefore prioritize execution accuracy, using exact and component matches only for diagnosis.

## 8. Conclusion

The complete Spider 1.0 development-set experiment does not support the claim that the current DB-RLM outperforms the baselines:

1. Retrieved-schema generation was the strongest and most efficient approach, reaching 74.85% execution accuracy.
2. Database tools improved SQL validity but did not automatically improve answer accuracy.
3. DB-RLM had the highest cost and lowest accuracy.
4. The five-question 80% smoke result did not generalize; complete DB-RLM accuracy was 64.89%.
5. Recursion itself was not evaluated because no child agent was created during the full run.

## 9. Recommended Next Experiments

### 9.1 Ensure that recursion actually occurs

- Do not rely entirely on a 7B model to select `spawn_subagent`
- Let the controller trigger decomposition for multi-table queries, nested queries, set operations, complex aggregation, or multiple independent constraints
- Add concrete decomposition examples to the prompt
- Record attempted and accepted spawn counts and success rates by depth

### 9.2 Run controlled ablations

Compare the following under the same model, questions, and budgets:

- `max_depth=0`: recursion disabled
- `max_depth=1`: one child level
- `max_depth=2`: two child levels
- Forced decomposition for complex questions
- Direct use of a tested root `candidate_sql`
- Current additional synthesis stage

Differences can only be attributed to recursion when the runs with `max_depth>0` actually create child agents.

### 9.3 Improve final SQL selection

- Prefer a root candidate that has already executed successfully
- Execute both the tested candidate and synthesized query before choosing
- Adapt repair attempts to error type instead of always allowing one
- Add deterministic rejection for empty SQL, repeated invalid SQL, and non-SQLite syntax

### 9.4 Target complex questions

Many Spider questions do not need recursion and only incur additional cost. Future results should be grouped by difficulty, table count, join count, nesting depth, and aggregation complexity. Child agents should be enabled primarily for high-complexity questions.

### 9.5 Regenerate the aggregate summary

The current `summary_metrics.json` was generated before DB-RLM completed and contains only the three baselines. Regenerate it with:

```powershell
python -m spider1_experiments.scripts.evaluate_results `
  --results-dir results\spider1_full_dev `
  --output results\spider1_full_dev\summary_metrics.json
```

## 10. Result Files

```text
results/spider1_full_dev/
├── baseline_1_direct_llm_schema.json
├── baseline_2_direct_text_to_sql.json
├── baseline_3_non_recursive_db_agent.json
├── ours_recursive_db_rlm.json
└── summary_metrics.json
```

Each result row contains the question, predicted SQL, gold SQL, execution results, correctness, latency, and token usage. Agent outputs also contain tool traces. DB-RLM additionally records the recursive tree, maximum depth, action count, LLM-call count, and repair attempts for future error analysis and ablation studies.
