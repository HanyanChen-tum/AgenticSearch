## Experimental Plan: Evaluating Recursive Language Model for Scalable Text-to-SQL

### 1. Research Motivation

Recent Text-to-SQL agents often perform well on small or medium databases, but their performance becomes unstable when the database schema is large, noisy, or cannot fit into the model context window. In this setting, simply providing the full schema is impractical, while aggressive schema pruning may remove necessary tables or columns.

AutoLink shows that scalable schema linking should be evaluated not only by final SQL execution accuracy, but also by whether the system can recall the necessary schema elements, control token cost, and remain robust as database size increases. AutoLink evaluates schema linking on BIRD and Spider 2.0-Lite using metrics such as Strict Recall Rate, average token consumption, downstream Execution Accuracy, scalability across database sizes, and ablation studies of different schema exploration actions.

Following this idea, our goal is not only to test whether RLM improves final accuracy, but to evaluate whether RLM improves **long-context management** in large-scale Text-to-SQL.

### 2. Main Research Questions

**RQ1: Does RLM improve Text-to-SQL robustness when the available context length is limited?**

We test whether RLM maintains higher execution accuracy and schema recall than non-recursive agents under different context budgets.

**RQ2: Does RLM scale better when database schema size increases?**

We test whether RLM degrades more slowly than baselines as the number of tables and columns increases.

**RQ3: Does RLM retrieve or maintain more complete schema information with fewer tokens?**

We test whether RLM achieves a better trade-off between schema recall, schema noise, and token cost.

**RQ4: Which part of RLM contributes most?**

We run ablation experiments on recursion depth, schema memory, retrieval, verification, and reflection.

### 3. Hypotheses

**H1:** On small databases or full-context settings, RLM may not significantly outperform strong baselines.

**H2:** Under limited context budgets, RLM will preserve more relevant schema information and degrade more slowly.

**H3:** On large-schema databases, RLM will achieve higher schema strict recall than direct prompting or non-recursive retrieval agents.

**H4:** The main contribution of RLM is not raw reasoning ability, but recursive context control: selecting, compressing, updating, and reusing schema context across steps.

### 4. Datasets

We use three levels of datasets.

#### 4.1 Spider 1.0 / Spider Dev Subset

This is used as a sanity-check dataset. Since Spider 1.0 databases are relatively small, it is not the main benchmark for proving RLM’s contribution. It is mainly used to show that RLM does not harm normal Text-to-SQL performance.

Recommended setting:

* 200 sampled examples, consistent with our current preliminary experiments.
* Full dev set if time and budget allow.
* Metrics: Execution Accuracy, Valid SQL Rate, Exact Match, token cost.

#### 4.2 BIRD Dev

BIRD is a large-scale database-grounded Text-to-SQL benchmark designed for more realistic database contents and efficient SQL generation. It contains real-world-style databases, external knowledge, and database values, making it more suitable for testing scalable Text-to-SQL systems.

Recommended setting:

* Use BIRD Dev.
* If budget is limited, sample 300–500 examples.
* Stratify examples by schema size and difficulty.
* Metrics: Execution Accuracy, Valid SQL Rate, Schema Recall, token cost.

#### 4.3 Spider 2.0-Lite or Large-Schema Subset

Spider 2.0 is designed for real-world enterprise Text-to-SQL workflows. It contains 632 tasks, and its databases often contain over 1,000 columns and require searching metadata, dialect documentation, and long context.

Recommended setting:

* Use Spider 2.0-Lite if implementation resources allow.
* If Spider 2.0-Lite is too complex, create a controlled large-schema benchmark by augmenting Spider/BIRD databases with distractor tables and columns.

This dataset is the most important for proving the long-context contribution of RLM.

### 5. Compared Methods

We should compare RLM with both simple baselines and agent baselines.

#### 5.1 Basic Baselines

**B1: Direct Full-Schema Prompting**

The full database schema is given to the LLM, if it fits into the context window.

Purpose: shows the upper-bound behavior when context is not limited.

**B2: Direct Truncated-Schema Prompting**

Only the first part of the schema is given until the context budget is reached.

Purpose: tests what happens when context is naively limited.

**B3: Embedding Retrieval + SQL Generation**

Use embedding retrieval to select top-k relevant tables/columns, then generate SQL.

Purpose: tests whether simple retrieval is enough.

**B4: BM25 / Keyword Retrieval + SQL Generation**

Use lexical matching to retrieve schema items.

Purpose: tests a cheap non-LLM retrieval baseline.

#### 5.2 Agent Baselines

**B5: Non-recursive Schema Agent**

The agent can inspect schema once, select relevant schema, and generate SQL, but it cannot recursively update or re-enter schema exploration.

Purpose: isolates whether recursion itself matters.

**B6: Reflection-only Agent**

The agent generates SQL, reflects on the error, and corrects SQL, but does not recursively manage schema memory.

Purpose: tests whether RLM is more than ordinary reflection.

**B7: Existing Text-to-SQL Agent**

Use one or more open-source agents if implementation time allows, such as CHESS, RSL-SQL, MAC-SQL, or Spider-Agent. AutoLink compares with several of these systems in its downstream SQL generation experiments.

Purpose: positions RLM against existing agent-style systems.

#### 5.3 Our Methods

**Ours-1: RLM-Schema**

RLM is used only during schema exploration. It recursively reads, retrieves, compresses, and updates schema context before SQL generation.

**Ours-2: RLM-Loop**

RLM is used as a full recursive agent loop:

1. Understand question.
2. Retrieve initial schema.
3. Generate tentative schema plan.
4. Explore missing schema.
5. Compress schema memory.
6. Generate SQL.
7. Verify execution.
8. If needed, recursively return to schema exploration.

**Ours-3: RLM-Loop + SQL Correction**

This adds execution-based correction after SQL generation.

This version may achieve the best final SQL accuracy, but we should report it separately because it mixes schema management with SQL correction.

### 6. Main Experimental Variables

#### 6.1 Context Budget

We test different context limits:

* 4k tokens
* 8k tokens
* 16k tokens
* 32k tokens
* full available context

The main comparison should show how each method degrades as the context budget becomes smaller.

Expected result: RLM may not be much better under full context, but should degrade more slowly under 4k/8k/16k limits.

#### 6.2 Schema Size

We test different schema sizes:

* small: fewer than 100 columns
* medium: 100–500 columns
* large: 500–1000 columns
* very large: more than 1000 columns
* extreme: more than 3000 columns, if available

If the original benchmark does not contain enough large databases, we create controlled schema expansion by adding distractor tables and columns.

Example expansion settings:

* original schema
* 2× schema size
* 5× schema size
* 10× schema size

The added distractor schema should be semantically similar enough to create noise, not just random column names.

#### 6.3 Initial Retrieval Size

Similar to AutoLink’s initial top-n experiment, we test how much initial schema is given before recursive exploration. AutoLink studies different initial retrieval sizes and shows that iterative exploration can recover missing schema beyond the initial candidate set.

Settings:

* top-5 columns
* top-10 columns
* top-20 columns
* top-50 columns
* top-100 columns

Expected result: RLM should perform better than non-recursive retrieval when initial top-k is small.

#### 6.4 Recursive Depth

We test how many recursive schema exploration rounds are useful.

Settings:

* depth 0: no recursion
* depth 1: one recursive expansion
* depth 2: two recursive expansions
* depth 3: three recursive expansions

Expected result: depth 1 or 2 may be enough. Too much recursion may increase token cost without improving accuracy.

#### 6.5 Max Agent Turns

Similar to AutoLink’s max-turn experiment, we test the maximum number of interaction turns. AutoLink reports that most gains happen in earlier turns and later turns provide smaller improvement.

Settings:

* max turns = 2
* max turns = 4
* max turns = 6
* max turns = 8
* max turns = 10

### 7. Evaluation Metrics

#### 7.1 SQL Generation Metrics

**Execution Accuracy, EX**

Whether the generated SQL returns the same result as the gold SQL.

**Valid SQL Rate**

Whether the generated SQL can be executed without syntax or runtime errors.

**Exact Match**

Whether the generated SQL structurally matches the gold SQL.

Exact Match is less important than Execution Accuracy, but it can still be reported.

#### 7.2 Schema Linking Metrics

These are central to the RLM paper.

**Table Recall**

Whether all gold tables used by the gold SQL are included in the selected schema context.

**Column Recall**

Whether all gold columns used by the gold SQL are included.

**Strict Schema Recall Rate, SRR**

An example is counted as successful only if all required schema elements are recalled.

This follows the kind of evaluation used by AutoLink, which reports strict schema linking recall together with token efficiency.

**Average Recalled Columns**

How many columns are included in the final schema context.

**Schema Precision**

Among selected schema items, how many are actually needed.

**Schema F1**

Balance between schema recall and schema precision.

#### 7.3 Context and Efficiency Metrics

**Average Input Tokens**

Total input tokens used per example.

**Average Output Tokens**

Total output tokens used per example.

**Total Tokens**

Input + output tokens.

**Latency**

Average time per query.

**Number of Tool Calls / Retrieval Calls**

How many schema exploration actions are needed.

**Performance per Token**

For example:

[
\text{EX per 10K tokens} = \frac{\text{Execution Accuracy}}{\text{Average Tokens}/10000}
]

This is important because RLM’s contribution may be efficiency rather than only accuracy.

#### 7.4 Robustness Metrics

**Accuracy Drop under Context Limit**

[
\Delta EX = EX_{\text{full context}} - EX_{\text{limited context}}
]

**Schema Recall Drop under Schema Expansion**

[
\Delta SRR = SRR_{\text{original schema}} - SRR_{\text{10x schema}}
]

If RLM has a smaller drop, it supports the long-context management claim.

### 8. Experiment 1: Main Comparison

Purpose: compare RLM with baselines under the same model and same SQL generator.

Setting:

* Dataset: Spider 1.0 subset, BIRD Dev subset, Spider 2.0-Lite if available.
* Model: same LLM for all methods.
* SQL generator prompt: fixed across methods.
* Only schema selection/context management changes.

Methods:

* Direct full schema
* Direct truncated schema
* Embedding retrieval
* Non-recursive schema agent
* Reflection-only agent
* RLM-Schema
* RLM-Loop
* RLM-Loop + SQL Correction

Report:

* EX
* Valid SQL Rate
* SRR
* average selected columns
* average tokens
* latency

Expected conclusion:

RLM may be similar to baselines on small schemas, but should show stronger robustness on large schemas and limited context.

### 9. Experiment 2: Context Budget Study

Purpose: test whether RLM is useful when the context window is constrained.

Setting:

* Fix dataset.
* Fix model.
* Vary context budget: 4k, 8k, 16k, 32k, full context.

For each method, plot:

* EX vs context budget
* SRR vs context budget
* token cost vs context budget

Expected result:

Direct full-schema prompting should fail or degrade under small budgets. Retrieval-only methods may lose necessary schema. RLM should maintain higher SRR and EX because it recursively manages and updates the schema memory.

This experiment is probably the most important one for your new direction.

### 10. Experiment 3: Schema Scale Study

Purpose: test whether RLM scales better as database schema becomes larger.

Two possible designs:

**Design A: Natural schema-size bins**

Group databases by number of columns:

* fewer than 100
* 100–500
* 500–1000
* 1000–3000
* more than 3000

This follows AutoLink’s scalability logic, where methods are compared across database sizes.

**Design B: Controlled schema expansion**

Start from the same original database and add distractor schema:

* original
* 2×
* 5×
* 10×

This is cleaner because the question difficulty stays the same while only schema noise increases.

Report:

* EX
* SRR
* average tokens
* schema precision
* selected columns

Expected result:

RLM should degrade more slowly than non-recursive methods as schema size increases.

### 11. Experiment 4: Schema Recall vs Token Trade-off

Purpose: show whether RLM gives a better balance between finding enough schema and avoiding too much noise.

For each method, plot:

* x-axis: average selected columns or average tokens
* y-axis: SRR or EX

Methods:

* embedding retrieval with different top-k
* BM25 with different top-k
* non-recursive agent
* RLM with different recursion depth
* RLM with different initial top-n

Expected result:

RLM should achieve higher SRR at the same token budget, or similar SRR with fewer tokens.

This experiment is very important because even if final EX improvement is small, better schema recall/token trade-off can still be a clear contribution.

### 12. Experiment 5: Ablation Study

Purpose: identify which RLM component matters.

Ablation variants:

**Full RLM**

Complete recursive schema exploration and memory update.

**w/o Recursion**

Only one-pass schema selection.

**w/o Schema Memory**

The agent can retrieve schema, but does not maintain a compressed schema memory.

**w/o Verification**

Remove the step that checks whether selected schema is sufficient.

**w/o Reflection**

Remove the step that reasons about missing schema after failed SQL generation.

**w/o Retrieval**

The agent can only use initially provided schema.

**w/o Compression**

The agent keeps raw retrieved schema without summarizing or organizing it.

Report:

* EX
* SRR
* tokens
* selected columns
* error categories

Expected result:

If RLM is truly useful, removing recursion, memory, or verification should hurt performance most under large-schema or limited-context settings.

### 13. Experiment 6: Recursive Depth and Max-Turn Analysis

Purpose: understand how much recursion is useful.

Settings:

* recursion depth: 0, 1, 2, 3
* max turns: 2, 4, 6, 8, 10

Report:

* EX
* SRR
* token cost
* latency

Expected result:

Depth 1 or 2 may provide most of the gain. Too many turns may increase cost and sometimes introduce noise.

This helps avoid the criticism that RLM only improves because it spends more tokens.

### 14. Experiment 7: Error Analysis

Purpose: show what types of errors RLM fixes and what it still cannot fix.

Manually analyze 50–100 failed examples.

Error categories:

1. Missing table.
2. Missing column.
3. Wrong join path.
4. Wrong aggregation.
5. Wrong filter condition.
6. Wrong value grounding.
7. SQL syntax error.
8. Execution error.
9. Over-retrieval of irrelevant schema.
10. Context overflow or truncation.
11. Wrong reasoning despite correct schema.

Compare error distributions between:

* direct prompting
* retrieval-only
* non-recursive agent
* RLM

Expected result:

RLM should mainly reduce missing-table, missing-column, and context-overflow errors. It may not strongly reduce pure logical reasoning errors.

This would support the claim that RLM is a context-management contribution, not a general SQL reasoning improvement.

### 15. Experiment 8: Case Studies

Select 3–5 representative examples.

Case types:

**Case 1: RLM succeeds because it recursively finds a missing table.**

Show that initial retrieval missed a required table, but RLM detected the missing relation and retrieved it later.

**Case 2: RLM succeeds under limited context.**

Show that direct full-schema prompting cannot fit the schema, while RLM keeps only useful schema memory.

**Case 3: RLM fails because schema is correct but reasoning is wrong.**

This is useful because it honestly separates schema management from SQL reasoning.

**Case 4: RLM over-explores and adds noise.**

This shows limitations and motivates future work.

### 16. Recommended Result Tables

#### Table 1: Main Results

Columns:

* Method
* Dataset
* EX
* Valid SQL Rate
* SRR
* Avg. selected columns
* Avg. tokens
* Latency

#### Table 2: Context Budget Results

Columns:

* Method
* 4k EX / SRR
* 8k EX / SRR
* 16k EX / SRR
* 32k EX / SRR
* Full EX / SRR

#### Table 3: Schema Size Results

Columns:

* Method
* small schema EX / SRR
* medium schema EX / SRR
* large schema EX / SRR
* very large schema EX / SRR
* extreme schema EX / SRR

#### Table 4: Ablation Results

Columns:

* Variant
* EX
* SRR
* Avg. tokens
* Avg. selected columns
* Main failure type

#### Figure 1: EX vs Context Budget

Shows whether RLM degrades more slowly.

#### Figure 2: SRR vs Schema Size

Shows whether RLM scales better.

#### Figure 3: SRR vs Token Cost

Shows whether RLM has a better recall-cost trade-off.

#### Figure 4: Error Type Distribution

Shows what RLM actually improves.

### 17. Final Experimental Claim

The final paper should not claim:

“RLM significantly improves Text-to-SQL accuracy in all settings.”

Instead, the claim should be:

“RLM improves scalable context management for Text-to-SQL. While it may not significantly improve accuracy on small databases or full-context settings, it maintains higher schema recall, lower accuracy degradation, and better token-efficiency under large-schema and limited-context conditions.”

This claim is safer, more realistic, and more aligned with the actual contribution of RLM.

### 18. Minimal Version If Time Is Limited

If time is limited, we should prioritize five experiments:

1. Main comparison on Spider 1.0 subset and BIRD subset.
2. Context budget experiment: 4k, 8k, 16k, full.
3. Schema expansion experiment: original, 2×, 5×, 10×.
4. Ablation: full RLM, w/o recursion, w/o memory, w/o verification.
5. Error analysis on 50 failed cases.

This minimal version is enough to support the new research direction.
