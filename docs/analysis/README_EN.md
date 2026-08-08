# Agent Error-Trajectory Analysis and Experiment Log

> English version of [README.md](README.md). The Chinese document remains the source maintained during day-to-day experimentation; this version preserves the same experiment boundaries, results, and decisions.

This document records Agent versions, internal mechanisms, error trajectories, and subsequent changes for the BIRD Text-to-SQL experiments. Whenever a new mechanism is introduced, copy the experiment template near the end of this document and run the fixed evaluation set before drawing conclusions from individual traces or a single accuracy number.

## 0. Current Code Audit and Recent Changes

This section records implementation problems in `ours/`, completed fixes, and risks that still require experimental validation. It describes the code after the 2026-07-13 refactor. Error counts after Section 1 still come from older legacy traces, so “fixed in code” must not be treated as “experimentally proven effective.”

### 0.1 Problems Found in `ours/`

| Problem | Impact | Current status |
|---|---|---|
| `DBRLM` and the in-domain few-shot runner once maintained separate ReAct loops | Error feedback, FINAL handling, and trace behavior could drift, invalidating single-variable ablations | Fixed: both now use `DBRLM.acomplete` |
| Historical `db_hints.py` was explicitly written around low-accuracy databases | It may encode dev/eval failure tuning and cannot be clean-baseline knowledge | Isolated: only `legacy-e0` may enable it |
| Prompt construction, knowledge injection, run control, and experiment configuration were coupled | Prompt, offline, few-shot, and recursion ablations could not be isolated reliably | Fixed: prompts, knowledge, configuration, state, and capability boundaries are separated |
| The parent REPL exposed generic `recursive_llm`, and the raw DB object exposed Schema APIs | R0/R1 had hidden capabilities even when recursion was not intended | A runtime gate was added for `e4-r0`; R0 was calibrated against the same first 50 E0 items |
| Old FINAL logic relied on temporary `last_was_empty` state | Repeated FINAL could bypass protection; submitted SQL could differ from the most recently executed SQL | Fixed with persistent structured execution state |
| The old code allowed the model to execute one SQL string, rewrite it, and submit the rewrite directly | Produced `UNVERIFIED_FINAL`; the DB observation did not validate the submitted answer | E1 verified-final was implemented and evaluated |
| All-NULL results were treated as deterministic errors | Correct gold results for `bird_1526` and `bird_944` are all NULL, causing regressions | Fixed: all-NULL remains a warning, but exactly executed SQL may be submitted |
| Profiles, capability boundaries, and knowledge sources lacked independent versions/hashes | Historical results could not prove which Prompt, few-shot source, or hidden tools were used | Fixed: manifests and traces record configuration, capabilities, retriever provenance, and SHA-256 |
| The runner initialized embeddings for 9,428 examples before checking manifest conflicts | Startup work was wasted even when resume was impossible | Fixed: validate a lightweight retriever manifest before loading embeddings |
| `DBRLM` defaults could implicitly enable E1 | Old runners that omitted an argument could silently change experimental behavior | Fixed: default is `clean-e0`; historical runners explicitly use `legacy-e0` |
| State-machine, capability, and profile boundaries lacked tests | R1/R2 additions could break the E0/E1 single-variable relation | Fixed with tests for Prompt provenance, lightweight manifests, state, duplicate FINAL, all-NULL, capability violations, and the shared loop |
| Final predicted/gold SQL evaluation had no timeout | A runaway query could block SQLite after the Agent returned; `e0_core_run2` stopped at 110/197 | Fixed: shared executor uses a 30-second timeout and closes connections explicitly |
| The former `clean-e0` Prompt contained aggregation, ratio, ordering, and output rules | Rules derived from eval errors could leak knowledge or inflate the baseline | Fixed: formal profiles use protocol-only `clean-protocol-v1`; old rules remain legacy-only |
| The clean baseline had no database notes/manual patterns, yet replacement groups were planned | There was no replacement target and therefore no interpretable ablation | Fixed: invalid groups removed; E3-A only adds train-only patterns, and E3-B only removes train few-shot |
| R1-E/R1-C context store, R2 Leaf, R3 Planner, and R4 router are not implemented | The current system is DB CodeAct/ReAct, not a complete RLM | These are future mechanisms to test in order, not baseline defects |

### 0.2 Changes Made in This Refactor

| Location | Change | Experimental significance |
|---|---|---|
| `ours/agent/config.py` | Added immutable `AgentConfig` profiles | E1 isolates strict final gating; E4-R0 only adds a capability gate to E0 |
| `ours/agent/state.py` | Added `AgentExecutionState` with SUCCESS/ERROR/EMPTY/ALL_NULL and last executed SQL | FINAL becomes a verifiable state transition |
| `ours/agent/capabilities.py` | Added `GatedDBEnvironment`; R0 only allows `db.execute` and `db.sample_values` | Blocks hidden Schema APIs and generic recursion; violations enter the trace |
| `ours/agent/knowledge.py` | Centralized BIRD Hint, database notes, few-shot, and provenance | Establishes knowledge boundaries for later offline ablations |
| `ours/agent/prompts.py` | Versioned prompts; formal profiles use protocol-only Prompt | Removes fixed SQL-rule contamination and records source/hash |
| `ours/recursive_db_rlm.py` | Unified the sole control loop with profiles, knowledge, state, gate, and events | Removes behavioral drift between runners |
| `ours/train_few_shot_retriever.py` | Records train pool, example count, embedding model, and file SHA-256 | Proves formal few-shot comes from train rather than dev/eval |
| `scripts/run_bird_train_fewshot.py` | Added `--agent-profile` and complete provenance in manifests | Prevents incompatible profiles from sharing result/trace directories |
| `scripts/run_bird_train_fewshot.py` | Reports changed fields and delays embedding initialization until after validation | Makes conflicts interpretable and avoids wasted initialization |
| `shared/sql_executor.py` | Added a 30-second SQLite progress-handler timeout | Prevents final evaluation from hanging indefinitely |
| `scripts/summarize_bird_runs.py` | Added explicit allowed historical configuration differences | Aggregates exploratory runs without rewriting old manifests |
| `scripts/run_bird_indomain_fewshot.py` | Removed duplicate `acomplete`; retained only a legacy thin wrapper | Dev-derived few-shot no longer masquerades as a clean entry point |
| `scripts/run_bird_ours.py` | Explicitly uses the legacy profile and writes a config hash | Prevents silent semantic changes through defaults |
| `tests/test_agent_profiles.py` | Added profile, provenance, state, FINAL, all-NULL, violation, and loop tests | Locks ablation boundaries |

### 0.3 Exact Meaning of Current Profiles

| Profile | Purpose | verified-final | capability gate | legacy `db_hints` |
|---|---|---:|---:|---:|
| `legacy-e0` | Historical reproduction only; excluded from formal conclusions | No | No | Yes |
| `clean-e0` | Formal strong-baseline candidate | No | No | No |
| `clean-e1` | Adds only final-SQL state protection | Yes | No | No |
| `e4-r0` | Adds only runtime capability gating to E0 | No | Yes | No |

`clean-e0` completed two exploratory runs on the fixed 197 items and is the screening baseline. The two runs differ in the evaluation SQL-timeout field, so they are not strict protocol replications. `clean-e1` completed a paired first-70 comparison and was rejected. `e4-r0` has been implemented and tested; the gate itself is not claimed to improve accuracy.

### 0.4 Overlap Between Existing Capabilities and Later Mechanisms

| Capability already in E0 | Overlap | Treatment |
|---|---|---|
| Multi-turn DB ReAct and error feedback | Within-run self-correction | Retain everywhere; do not count as a new mechanism |
| Python REPL, `db.execute`, `sample_values` | E2 controlled execution | E2 adds observability/isolation only |
| Aggregation, ratio, ordering rules/examples in the legacy Prompt | E3-A query patterns | Keep as historical overlap but do not run a formal legacy ablation; test a source-compliant train-only prototype instead |
| Legacy `db_hints` | E3-C offline metadata | Exclude from formal parents; E3-C uses auditable, hashable database-level artifacts |
| Train few-shot gold SQL | E3-A static patterns / E3-D Query Mining | E3-B only rejects static-pattern replacement; E3-C keeps few-shot and disables patterns; E3-E is the matched removal |
| Full Schema injected into the Prompt | E3-C Offline Schema Context / E5 context store | E3-C replaces it with deterministic relevant fragments; E5 later tests active `search/slice/compose` |
| High-reasoning model | E4 QueryPlan / E6 decomposition | Fix model and reasoning effort; compare E6-B with matched-budget E6-A |
| Generic `recursive_llm` implementation | E6 depth-1 Leaf | Disable through the gate until E6 |

Not running a formal legacy ablation does not mean the mechanism is untested. Clean E0 already removed legacy Prompt rules and `db_hints`, so “remove them again” has no valid counterfactual. Reintroducing unaudited material would mix potential eval tuning with knowledge-source changes. `train-static-v1` is only a compliant static prototype; it lacks normalization, clustering, support, applicability boundaries, and question-level retrieval. E3-C tests auditable Schema metadata; E3-D tests formal Query Mining.

### 0.5 Aggregate E0 Results

| Metric | Result |
|---|---:|
| Run1 | 69/197 (35.03%) |
| Run2 | 66/197 (33.50%) |
| Mean accuracy | 34.26% |
| Population standard deviation | 0.76% |
| Always correct | 62 |
| Always failed | 124 |
| Unstable | 11 |
| Run1→Run2 recovered/regressed | 4/7 |
| `UNVERIFIED_FINAL` failure records | 215 |

Reports: [e0_core_summary.md](analysisDetail/e0_core_summary.md) and [e0_core_summary.json](analysisDetail/e0_core_summary.json). Run1 lacks `evaluation_sql_timeout_seconds`; Run2 uses 30 seconds and its first 110 items predate the fix. Accuracy/error distributions are usable for exploration, while token cost is a lower bound because 9/11 calls lack usage.

> **2026-08-07 correction**: the table below has been regenerated with the fixed classifier (`docs/analysis/README.md` §4.1). The pre-fix classifier only checked keyword *presence* for GROUP BY/ORDER BY/aggregate terms and never compared JOIN keys, which systematically undercounted Schema/Join and overcounted the low-confidence filter bucket. **Schema/Join goes from the smallest structured category (38) to the largest (97)**; filter/low-confidence drops from 67 to 36. The total is still 259.

The mechanism mapping derived from all 259 failure records is:

| E0 failure attribution (corrected) | Direct mechanism | Experiment order |
|---|---|---|
| 5 runner, parser, or tool failures | Structured observations, retries, resume, and explicit termination reasons | `E2-A`, infrastructure only |
| 75 table-selection/Join-path errors | Offline Schema Context, field semantics, PK/FK, relationship cardinality, and relevant-fragment selection | `E3-C` |
| 22 JOIN-key/condition errors (new subcategory, previously undetected) | Same as above, plus checking the foreign-key columns used in JOIN `ON` conditions | `E3-C` |
| 36 filter-scope/expression errors (was 67) | First distinguish Agent errors from gold ambiguity; then combine value semantics with question-level condition structure | `F-Audit` → `E3-C` / `E4-A`; `E5-B` if needed |
| 43 aggregation/grouping errors (was 82) | Explicit target entity, grain, grouping keys, aggregate functions, `WHERE/HAVING`, and stage dependencies | `E4-A`; enter `E6` only when residual cases contain a separable SubPlan |
| 22 ordering errors (was 11) | Explicit ordering metric, direction, Top-K, ties, and `LIMIT` scope | `E4-A` |
| 48 output-column-count errors (unchanged) | Fix answer type, column count/order/source, and projection checks | `E4-A` |
| 8 YES/NO versus row-output errors (unchanged) | Fix boolean/scalar/rows answer form before SQL generation | `E4-A` |

These subcategories sum to 259 (5+75+22+36+43+22+48+8). The mapping is based on post-run `semantic_error_class` and detailed semantic attribution. `UNVERIFIED_FINAL` remains a parallel control-flow diagnostic and does not determine mechanism priority.

### 0.6 E1 Strict Verified-Final Result

| Field | Value |
|---|---|
| Experiment | `E1` |
| Profile | `clean-e1` |
| Only major change | Strict verified-final state gate on E0 |
| Model | `azure/seminar-gpt-5.4-mini` |
| Scope | 71 saved; paired analysis uses the first 70 |
| Result | `results/e1_verified_run1.json` |
| Trace | `trace/e1_verified_run1/transcripts.jsonl` |
| Report | [e1_verified_summary.md](analysisDetail/e1_verified_summary.md) |
| Comparison | [e1_vs_e0_first70.md](analysisDetail/e1_vs_e0_first70.md) |

| Configuration | Correct | Accuracy | LLM calls/item | Tokens/item | Latency/item (s) |
|---|---:|---:|---:|---:|---:|
| E0 run1 | 29/70 | 41.43% | 2.67 | 13,255.29 | 35.18 |
| E0 run2 | 30/70 | 42.86% | 2.77 | 13,598.43 | 37.20 |
| E0 mean | — | 42.14% | 2.72 | 13,426.86 | 36.19 |
| E1 | 28/70 | 40.00% | 5.51 | 26,920.84 | 63.23 |

E1 is 2.14 pp below the E0 mean. Calls, recorded tokens, and latency rise by approximately 2.03×, 2.00×, and 1.75×. There was one missing-usage call.

- E0 was correct in both runs on 27 items, wrong in both on 38, and inconsistent on 5.
- E1 recovered none of the stable E0 failures.
- E1 regressed three stable E0 successes: `bird_1169`, `bird_1171`, `bird_1103`.
- Relative to E0 run1: 2 recovered, 3 regressed; relative to run2: 2 recovered, 4 regressed.
- There were 103 `final.blocked` events across 63/70 items, so the gate became a general extra loop.

`UNVERIFIED_FINAL` fell to zero, proving the formal constraint worked, but other labels rose largely because previously masked failures were reclassified. The paired accuracy transitions do not support E1. On the common first 50 items, E0 is 38%/40% and E1 is 38%, while cost remains roughly doubled.

**Decision:** reject the current strict verified-final. If final verification is revisited, prefer a low-cost controller that automatically executes FINAL SQL rather than forcing repeated ReAct turns.

### 0.7 E3-A Train-Only Static Patterns

| Field | Value |
|---|---|
| Experiment | `E3-A` |
| Profile | `e3-a` |
| Parent | E0 |
| Only major change | Add manually distilled train-only `train-static-v1`; retain `k=1` few-shot |
| Run / run_id | `e3_a_core197_run1` / `20260713T235804Z-19152b85` |
| Scope | Fixed 197: 137 `both_wrong` + 60 `canary` |
| Model | `azure/seminar-gpt-5.4-mini`, high reasoning |

The patterns were injected globally rather than retrieved per question. This is a source-compliant static-rule prototype, not complete Query Mining: it lacks SQL-AST normalization, support, clustering, applicability boundaries, and cross-database gates.

| Metric | E3-A | Relative to E0 mean |
|---|---:|---:|
| Correct/accuracy | 73/197 = 37.06% | +2.79 pp |
| `both_wrong` | 22/137 = 16.06% | — |
| `canary` | 51/60 = 85.00% | — |
| Simple / moderate / challenging | 27/50 / 31/96 / 15/51 | Moderate improves; challenging unclear |
| Total tokens/item | 14,751.72 | +8.7% |
| LLM calls/item | 2.74 | approximately unchanged |
| Latency/item | 38.01 s | — |

E3-A recovered six items that failed in both E0 runs and regressed one item correct in both. The +2.79 pp single-run change remains weak evidence and costs more than E0.

| Reviewed cause across 124 failures (2026-08-07 corrected) | Count | Share | Pre-fix count |
|---|---:|---:|---:|
| Schema/Join | 50 | 40.32% | 20 (16.13%) |
| Output contract | 29 | 23.39% | unchanged |
| Aggregation/order | 28 | 22.58% | 47 (37.90%) |
| Filter scope/expression | 13 | 10.48% | 24 (19.35%) |
| Runtime/tool/empty | 4 | 3.23% | unchanged |

Schema/Join moves from the smallest to the largest category; aggregation/order drops from the largest to third. There were 93 primary `UNVERIFIED_FINAL` labels; 77 followed an incorrect observation — their semantic split (originally reported as 31 aggregation / 20 output / 14 Schema/Join / 12 filtering) was also computed with the pre-fix classifier and has not been individually recomputed. Static reminders therefore did not solve the main question-level construction errors, and per the corrected numbers Schema/Join — which E3-A's patterns never targeted — is now E3-A's largest residual category.

**Decision:** retain E3-A only as historical evidence that static train-only rules may have a small effect. It is not the default E3-C parent and is not proof of Query Mining. [Summary](analysisDetail/e3_a_summary.md), [E0 comparison](analysisDetail/e3_a_vs_e0.md).

### 0.8 E3-B Patterns as a Few-Shot Replacement

| Field | Value |
|---|---|
| Experiment | `E3-B` |
| Historical profile | `e3-rf` |
| Parent | E3-A |
| Only major change | Keep static patterns; change effective few-shot from `k=1` to `k=0` |
| Run / run_id | `e3_b_core197_run1` / `20260714T023630Z-7eab3a22` |
| Pattern artifact | `train-static-v1`, SHA-256 `bdda5b6aa4f6d1b69f3c86d2d299e60bb1429f6c2e62b1acd58323850b34cc48` |

E3-A’s historical manifest lacks the exact artifact hash, so byte-identical pattern content cannot be proven retrospectively. E3-B records it; the limitation weakens strict single-variable attribution but does not change the observed result.

| Metric | E3-A | E3-B | Change |
|---|---:|---:|---:|
| Correct | 73/197 | 72/197 | -1 |
| Accuracy | 37.06% | 36.55% | -0.51 pp |
| Total tokens/item | 14,751.72 | 15,421.28 | +4.54% |
| LLM calls | 539 | 552 | +13 |
| DB calls | 397 | 403 | +6 |
| Latency/item | 38.01 s | 39.34 s | +1.33 s |
| Recovered/regressed | — | 4/5 | net -1 |

Recoveries were `bird_877`, `bird_671`, `bird_587`, and `bird_1387`; regressions were `bird_743`, `bird_989`, `bird_189`, `bird_1238`, and `bird_27`. They span aggregation, output, filtering, and Schema, with no stable class-level gain.

| Reviewed cause (2026-08-07 corrected) | E3-A | E3-B | Change | Pre-fix (for reference) |
|---|---:|---:|---:|---|
| Schema/Join | 50 | 59 | +9 | was 20→22, +2 |
| Output contract | 29 | 26 | -3 | unchanged |
| Aggregation/order | 28 | 26 | -2 | was 47→45, -2 (coincidentally same) |
| Filter scope/expression | 13 | 11 | -2 | was 24→29, +5 (opposite direction) |
| Runtime/tool/empty | 4 | 3 | -1 | unchanged |
| All failures | 124 | 125 | +1 | unchanged |

Removing few-shot shortened static input but increased calls, reasoning, and output, so end-to-end token cost rose. **Decision:** reject static-pattern replacement of train few-shot. This conclusion is limited to `train-static-v1` and does not reject statistically validated question-level Query Mining. [Summary](analysisDetail/e3_b_summary.md), [paired comparison](analysisDetail/e3_b_vs_e3_a_e0.md).

### 0.9 E4-R0 Capability-Gated Control

| Field | Value |
|---|---|
| Experiment | `E4-R0` |
| Profile | `e4-r0` |
| Only major change | Capability gate on E0; generic recursion and Schema APIs disabled |
| Scope | Fixed first 50, `both_wrong + canary` |
| Result | 19/50 (38.00%) |
| Result file | `results/e4_r0_run1.json` |
| Trace | `trace/e4_r0_run1/` |
| Reports | [summary](analysisDetail/e4_r0_summary.md), [JSON](analysisDetail/e4_r0_summary.json), [paired analysis](analysisDetail/e4_r0_vs_e0_first50.md) |

E4-R0 is consistent with E0’s 38%/40% first-50 results. It used 10,207.28 tokens/item, 2.72 calls/item, and 36.69 s/item, with no material increase. All 110 DB events were allowed (60 `db.execute`, 50 `db.sample_values`); no recursion, Schema API, or violation occurred. The gate therefore passes capability-boundary calibration, but does not itself improve accuracy. It is accepted as the parent control for later RLM/Planner ablations.

### 0.10 Historical E3-F v1/v3 First-53 Diagnostic

`e3_f_core197_run1` used `train-mined-v1 + e3-f-schema-v3 + k=1 few-shot` and stopped after 53/197. It predates Schema v4 and Query Mining v2, so it is a historical diagnostic, not a completed current E3-F.

| Metric | Result |
|---|---:|
| Accuracy | 21/53 = 39.62% |
| `both_wrong` | 7/36 = 19.44% |
| `canary` | 14/17 = 82.35% |
| Total tokens/item | 16,426.79 |
| Same-item E0 mean | 36.79%; 11,704.59 tokens/item |
| Relative to E0 | +2.83 pp; +40.34% tokens/item |
| Status | `interrupted`; only 4/11 databases |

Manual review of all 32 failures attributes 9 to aggregation, 9 to output contract, 7 to filtering/question semantics, 6 to Schema/Join, and 1 to runner/API. The 24 automatic `UNVERIFIED_FINAL` labels describe control flow rather than semantic causes.

Schema v3 delivered every table in the current database for all 53 items, so zero detailed-schema misses came from full-table injection rather than retrieval precision. Query Mining v1 delivered 2.85 cards/item on average, and only 16/53 selected sets contained a shape exactly matching gold.

**Decision:** freeze v1/v3, do not complete it to 197, do not extrapolate 39.62%, and do not use it to evaluate v2/v4.

- [Partial report](analysisDetail/e3_f_core197_run1_partial53_summary.md)
- [Same-item comparison](analysisDetail/e3_f_core197_run1_vs_e0_e3a_e3b_partial53.md)
- [32/32 semantic attributions](analysisDetail/e3_f_core197_run1_semantic_failures.csv)
- [Retrieval audit](analysisDetail/e3_f_core197_run1_retrieval_audit.csv)

## 1. Current Analysis Version

| Field | Value |
|---|---|
| Experiment ID | `TRACE-2026-07-11-A` |
| Nature | Error-trajectory audit of the current Agent; no recursion changes |
| Dataset | BIRD mini-dev, 500 records, 498 unique questions |
| Traces | `trace/transcripts.jsonl`, `trace/traces_report_full.html` |
| Classification | `trace/classification_sheet.csv` |
| Model | Azure `gpt-5.4-mini` |
| Scale | HTML marks 161 failures, approximately 67.8% of 500 |
| Code state | Traces predate the current profile/state/gate refactor |
| Limitation | Legacy traces are historical root-cause evidence only |
| Unified numbering | Follow `docs/experiment-plan/README.md` v1.0; old labels only explain historical artifacts |

### Trace Consistency

The old HTML contains 161 failure traces, while `classification_sheet.csv` has 158 rows: it once omitted `bird_226`, `bird_227`, `bird_228`, and `bird_255`, and included extra `bird_743`. This motivated strict shared-`run_id` validation across results, transcripts, and classifications. Legacy files are not mixed with new experiments.

## 2. Agent Mechanism: Historical Traces and Current Implementation

Both the historical Agent and current profiles are database-augmented CodeAct/ReAct agents. They have an executable REPL and DB observations, but not yet RLM-style programmatic context exploration and recursive decomposition. The control loop and capability isolation are now unified; that does not mean R1/R2/R3 are implemented.

### 2.1 Reasoning and Tool Loop

1. Formal profiles receive question, BIRD Hint, Schema, and train few-shot; only legacy profiles receive old database notes.
2. The model queries values using `db.sample_values(table, column)`.
3. It executes candidate SQL with `db.execute(sql)`.
4. SQL results, errors, empty sets, and all-NULL results are returned to the model.
5. The model submits SQL with `FINAL("sql")`.

Main locations: `ours/recursive_db_rlm.py`, `ours/agent/`, `ours/db_environment.py`, `scripts/run_bird_train_fewshot.py`, the legacy `scripts/run_bird_indomain_fewshot.py`, and `shared/evaluator.py`.

### 2.2 Existing Protection

- Read-only SQLite; 30-second timeouts for Agent tools and final predicted/gold evaluation.
- Row limits and structured SQL-error feedback.
- Empty/all-NULL feedback; all-NULL warns but does not hard-block.
- Repeated-result detection.
- Real table/column validation before `sample_values`.
- Train-set few-shot retrieval.
- `clean-e1` requires FINAL to equal a recently executed, non-error, non-empty SQL string, but this strict gate was rejected.
- `reasoning_effort=high` and multi-run voting are experiment settings, not internal reasoning modules.

### 2.3 Target RLM Architecture

Later work separates three measurable capabilities:

1. **Programmatic reasoning/exploration:** externalize Schema, descriptions, few-shot, and offline artifacts to a context store accessed through code.
2. **Executable environment:** retain fragments, plans, candidate SQL, observations, and verification state in the REPL and trace every material action.
3. **Self-improvement and divide-and-conquer:** let Root revise SQL from observations and call one depth-1 Leaf only for an independently verifiable complex SubPlan.

ReAct is the Root’s DB feedback path, not a separate loop parallel to RLM. A Root QueryPlan alone is not recursive decomposition; only C-P-Leaf tests context-driven bounded decomposition.

## 3. Current Error Results

| Metric | Result | Interpretation |
|---|---:|---|
| Failures marked in old HTML | 161 | Main historical analysis set |
| Real SQL execution errors | 2 | `bird_41`, `bird_83`; both attempted correction |
| Traces with empty results | 7 | Includes empty rows caused by SQL errors |
| Traces with all-NULL results | 5 | Often wrong column or join path |
| No assistant output | 2 | `bird_959`, `bird_598`; inspect runner/API |
| Only one assistant output | 4 | `bird_1168`, `bird_539`, `bird_604`, `bird_424` |
| Dominant failure form | Executable but semantically wrong | SQL executability is not the main bottleneck |

### 3.1 Representative Traces

#### A. Submitted Unverified SQL After Testing Another Query

In `bird_1029`, the first executed SQL returned the correct team names and speeds, but FINAL changed projection, aggregation, and ordering without re-execution. `bird_23` and `bird_83` show the same execute → rewrite → FINAL pattern. This is a controller-state problem, but E1 shows that strict synchronization alone does not solve the underlying semantics.

#### B. False Positive for a Nonexistent Column

In `bird_83`, `db.sample_values("schools", "NSLP Provision Status")` returned the literal text rather than an unknown-column error because of SQLite’s handling of quoted unknown identifiers. `sample_values` must validate table/column names against Schema first; that fix is now part of E0.

#### C. Wrong Aggregation Grain

`bird_1472` asks for minimum total 2012 consumption among LAM customers, but uses `ORDER BY y.Consumption ASC LIMIT 1`, sorting monthly rows rather than aggregating per customer with `SUM(Consumption)`.

#### D. Hint/Gold Conflict

In `bird_1338`, the Hint asks whether all expenses were approved, while gold returns each `approved` value. In `bird_1179`, the Hint points to `aCL IgM`, while gold returns `aCL IgA`, `aCL IgG`, and `aCL IgM`. These should be `DATASET_OR_GOLD_CONFLICT`, not direct mechanism failures.

#### E. Missing Output or Premature Termination

`bird_959` and `bird_598` have no assistant output; several others have only one. These require runner retry, timeout, and exception evidence and must not be classified as SQL reasoning errors.

## 4. Error Classification Standard

| `error_class` | Criterion | Typical direction |
|---|---|---|
| `TOOL_ERROR` | Tool error, unknown column not detected, or false positive | Schema validation and structured tool results |
| `UNVERIFIED_FINAL` | FINAL differs from the last executed SQL without re-execution | Inspect parallel semantic label; synchronization cannot replace semantic repair |
| `EMPTY_OR_NULL_RESULT` | Empty/all-NULL result not repaired correctly | Better state feedback and candidate management |
| `AGGREGATION_REASONING` | Wrong grouping, aggregation, ordering, window, or grain | Structured SQL checks and targeted examples |
| `SCHEMA_LINKING` | Wrong table, field, or join relation | Better Schema/FK context and tool lookup |
| `OUTPUT_CONTRACT` | Wrong column count/order, boolean/rows, aliases, or multi-part output | Lightweight output-contract validation |
| `DATASET_OR_GOLD_CONFLICT` | Hint/question conflicts with gold SQL | Report separately; do not drive Agent changes |
| `RUNNER_OR_API` | No output, timeout, request failure, or unsaved result | Retry, logging, and resume fixes |
| `CORRECT_TRACE_MARKED_WRONG` | Reasonable under Hint/DB evidence but gold rejects it | Dataset-quality evidence |
| `SEMANTIC_REVIEW_REQUIRED` | SQL runs but automatic rules only establish a semantic difference | Review filters, expressions, and gold noise |

The sheet retains compatible primary `error_class/subcategory` and adds `control_flow_class/subcategory`, `semantic_error_class/subcategory`, `sql_change_type`, and semantic notes/fix ideas. One failure may have both an unexecuted-rewrite control-flow label and an aggregation semantic label. Gold is used only after the run.

### Automatic Classification Pipeline

`run_bird_train_fewshot.py` writes results plus `run_manifest.json`, `transcripts.jsonl`, `traces_report.html`, and `classification_sheet.csv`. Results and transcripts share one `run_id`; mismatched IDs or final SQL abort report generation. `make_classification_sheet.py` can also run independently.

Structured tool events take precedence over parsing Markdown. High-confidence cases include no model output, unverified SQL, unknown table/column, execution error, empty, and all-NULL. Aggregation, output shape, ordering, and Schema differences are medium/low-confidence candidates. Remaining semantic differences become `SEMANTIC_REVIEW_REQUIRED`. Legacy files require `--allow-legacy` and still undergo consistency checks.

### 4.1 Known Classifier Limitations and This Round's Fix (2026-08-07)

This section records a code audit of the tracking mechanism itself: it is actually three layers with uneven reliability, and you need to know how each layer detects things before treating its output as ground truth.

| Layer | Implementation | Detection method | Reliability |
|---|---|---|---|
| Control-flow classification | `classify_failure()`, `scripts/make_classification_sheet.py` | Hard signals: no assistant output, empty `predicted_sql`, regex-matched SQL error strings, `rows==[]`, all-NULL detection | High, tagged `"high"` |
| Semantic classification | `semantic_classification()`, same file | Regex/string-level structural heuristics comparing predicted vs. gold SQL: column count, table set, JOIN keys, GROUP BY columns, aggregate keywords, ORDER BY columns, LIMIT | Medium, tagged `"medium"`; degrades to `"low"` when unattributable |
| Retrieval audit | `analyze_e3_f_retrieval.py` | Parses gold SQL's real AST with `sqlglot`, compares against the table/column set actually delivered by retrieval | Higher — structural parsing, not regex |
| Trajectory audit | `analyze_trajectory_audit.py` | Builds a state-transition sequence from the two outputs above; `query_plan.adherence` pass/fail comes from `plan_sql_adherence()` in `ours/agent/query_plan.py` | Depends on its upstream inputs |

**Problems found by the audit (pre-fix):**

1. `semantic_classification()` was a first-match-wins cascade in a fixed order: YES/NO → output column count → aggregate-keyword presence → ORDER BY direction → table set → fallback `SEMANTIC_REVIEW_REQUIRED`. A query that got both the tables *and* the aggregate structure wrong would be tagged `AGGREGATION_REASONING` because the aggregate check ran before the table check, masking the more foundational table-selection error.
2. The aggregate check only tested whether keywords like `" group by "` / `"sum("` were **present on both sides**, never comparing the actual `GROUP BY` columns. A predicted and gold query that both have `GROUP BY` but group on different columns — the single most-cited failure pattern in §3.3 ("writing a global aggregate as a per-entity group-by") — went completely undetected, since both sides trivially had the keyword.
3. The `ORDER BY` check only compared `ASC`/`DESC` direction keywords, never the sort column itself; sorting by a different column with the same (or both implicit) direction was invisible.
4. The table-set check only looked at which table names appeared after `FROM`/`JOIN`, never the join keys in the `ON` clause; selecting the right tables but joining on the wrong foreign key (one of the Schema/Join subtypes the docs explicitly name) went undetected.
5. There was no `LIMIT`/Top-K value comparison at all.
6. The `DATASET_OR_GOLD_CONFLICT` and `CORRECT_TRACE_MARKED_WRONG` categories defined in §4 are **never assigned by any code path** in `make_classification_sheet.py` — today they are 100% manual CSV edits, which is exactly the F-Audit work that has not yet happened. This is not a bug to fix in this pass (judging whether gold is noisy inherently needs a human), but it must be stated explicitly: until F-Audit is done, both categories' counts are permanently zero, and any failure that should belong to them is currently absorbed into some other structural category or into `SEMANTIC_REVIEW_REQUIRED`.

**What this round fixed:**

`scripts/make_classification_sheet.py` gained seven new structural extraction helpers — `clause_span`, `split_top_level`, `bare_column`, `group_by_columns`, `order_by_items`, `limit_value`, `join_key_columns` — and `semantic_classification()` was rewritten:

- New check order: YES/NO → output column count → **table set → JOIN keys** (new; only evaluated when the table sets already match, to avoid double-counting against the table check) → **actual GROUP BY columns** (new, replaces the old keyword-presence check) → aggregate-keyword presence (kept, to catch matching group-by columns with a different aggregate function) → **actual ORDER BY columns** (extended beyond direction-only) → **LIMIT value** (new) → fallback `SEMANTIC_REVIEW_REQUIRED`. Table/JOIN checks now run before the aggregate checks, since a wrong table selection is a more foundational error than a downstream aggregate difference.
- Two new, more specific subcategories: `join_key_or_condition_mismatch` (under `SCHEMA_LINKING`) and `limit_or_topk_mismatch` (under `AGGREGATION_REASONING`).
- Changed from "return on first hit" to "run every check, use the first hit as the primary label, and record any other hits in `semantic_notes`" — so the cascade order no longer hides other structural differences that were also detected.
- `tests/test_make_classification_sheet.py` gained 5 regression tests that pin down exactly the previously-undetectable scenarios (same grouping keyword but different columns; same sort direction but different column; different `LIMIT`; same tables but different JOIN keys; table and aggregate both wrong → table must win as primary). All 83 tests in the repo pass.
- Known remaining limitations: the new helpers are still regex-level heuristics, not real SQL AST parsing (unlike `sqlglot` in the retrieval-audit script); a nested subquery/CTE with its own `GROUP BY`/`ORDER BY` can be mistaken for the outer clause's boundary — documented in the function docstrings. `plan_sql_adherence()` in `ours/agent/query_plan.py` (the "did it follow the plan" check E4-A used) is a separate, weaker check — it only compares clause presence, table set, and output column count, never the actual content of `GROUP BY`/`ORDER BY`/`filters` — and was **not** touched in this pass, since the QueryPlan mechanism is currently paused after E4-A's rejection. If QueryPlan work resumes, that function needs the same structural-field upgrade, or "did it follow the plan" will remain exactly as fragile as what this audit just found elsewhere.

**Measured before/after impact (`e0_core_run1`, 128 failures, verification run written to a scratch directory, the recorded classification sheet was not overwritten):**

| `semantic_error_class` | Before | After | Change |
|---|---:|---:|---:|
| `SCHEMA_LINKING` | 20 | 49 | +29 (+145%) |
| `AGGREGATION_REASONING` | 45 | 32 | −13 (−29%) |
| `OUTPUT_CONTRACT` | 29 | 29 | unchanged |
| `SEMANTIC_REVIEW_REQUIRED` | 33 | 17 | −16 (−48%) |

The jump in `SCHEMA_LINKING` comes mainly from the new JOIN-key check — cases where the model picked the right tables but the wrong foreign key were previously invisible to Schema/Join accounting. The `SEMANTIC_REVIEW_REQUIRED` catch-all nearly halved, meaning a good share of what used to be "unattributable, needs manual review" can now be pinned to a specific Schema/Join or aggregation cause.

**Update (2026-08-07): this bulk regeneration has now been done.** All 7 completed experiments' `classification_sheet.csv` were regenerated with the fixed classifier (all were 100% auto-generated with no manual annotations at risk), and §0.5, §0.7, §0.8, §5, §8 of this document plus the corresponding sections of `docs/experiment-plan/README.md` (and both EN mirrors) have been updated with the corrected distributions. The most consequential single finding: **E4-A's own rejection rationale flips sign for its two primary categories** — the original report said aggregation/order improved (-4) while Schema/Join regressed slightly (+1); the corrected numbers show the opposite, aggregation/order actually got worse (+4, E4-A's own design target backfired) while Schema/Join improved (-4). The reject decision itself is unchanged (it rests on raw correct/incorrect counts, unaffected by classification), but the *reason* for rejection is now understood correctly. See §8 below and [`e4_a_core197_run1_summary.md`](analysisDetail/e4_a_core197_run1_summary.md).

## 5. Current Root-Cause Assessment

1. **Strict verified-final was rejected.** E1 is 40.00% versus a 42.14% paired E0 mean, approximately doubles calls/tokens, recovers zero stable failures, and regresses three stable successes.
2. **`sample_values` column validation is fixed**, pending confirmation through the clean baseline.
3. **Successful execution is not semantic correctness.** Table/Join path, aggregation grain, filter scope, ordering direction, and multi-part output dominate. Since the 2026-08-07 classifier fix (§4.1), Schema/Join is the single largest of the four semantic categories, and its priority should be raised accordingly.
4. **Gold noise is material** and must be separated from fixable Agent failures.
5. **Runner/API failures must remain separate** from reasoning failures.
6. **Clean Prompt provenance is fixed.** `clean-protocol-v1` has no task-specific SQL rules/examples, and its source/hash enter the manifest.
7. **The static-pattern conclusion is narrow.** E3-B rejects replacing few-shot with `train-static-v1`; it does not reject formal Query Mining.

Do not bypass the baseline and stack recursion, or add unaudited Prompt rules. E0 is complete, E1 rejected, and E4-R0 accepted as the capability-gated parent control. Later experiments isolate offline knowledge, context externalization, depth-1 decomposition, and one-response QueryPlan gains.

## 6. Subsequent Experiment Plan

All formal runs use the same 197 core+canary items, model, parameters, and complete manifest.

| Experiment | Change | Target | Status |
|---|---|---|---|
| `E0` | Two `clean-e0` exploratory runs | Baseline, cost, error structure | Complete; mean 34.26% |
| `E1` | Strict verified-final | Reduce `UNVERIFIED_FINAL` | First 70 complete; rejected |
| `E3-A` | Add train-only static patterns; keep few-shot | Static-rule prototype value | 73/197; weak evidence; [report](analysisDetail/e3_a_summary.md) |
| `E3-B` | Remove train few-shot from E3-A | Replacement value and cost | 72/197; rejected; [comparison](analysisDetail/e3_b_vs_e3_a_e0.md) |
| `E3-C` | Disable static patterns; replace runtime full Schema with deterministic Offline Schema Context; keep few-shot | Schema semantics, PK/FK, joins, values | Formal run3 complete: 77/197 (39.09%); accepted as the E4-A parent |
| `E3-D` | Add train question+SQL mined/retrieved patterns to E3-C | Aggregation, ordering, filtering, output, joins | Paused: no Query Mining v2 slot passes the cross-database gate |
| `E3-E` | Remove few-shot from an accepted E3-D | Can full offline knowledge replace few-shot? | Conditional |
| `E3-F` | Schema v4 + Query Mining v2 + few-shot | Repaired integrated offline system | Historical v1/v3 stopped at 53; current v2 has zero enabled slots and is paused |
| `E4-A` | Root QueryPlan + Output Contract | Aggregation/order/output/filter structure | Formal run complete and rejected: 71/197 (36.04%), six below E3-C; 3 recovered, 9 regressed; tokens/item +6.67%. [Summary](analysisDetail/e4_a_core197_run1_summary.md) |
| `E5-A` | Externalize identical information | Information equivalence | Paused: do not carry the rejected QueryPlan forward |
| `E5-B` | Controlled `search/slice/compose` | Programmatic context exploration | Paused |
| `E6-A` | Matched-budget extra Root deliberation | Compute control | Paused |
| `E6-B` | One QueryPlan-driven depth-1 Leaf | Divide-and-conquer gain | Paused; do not enter Leaf |

Each new configuration first receives one full 197-item run under the time budget. Changes below roughly 2 pp are trends only. Always report paired transitions, stable-failure recovery, semantic error migration, calls/tokens, context reads, and API/parse failures.

## 7. New Experiment Record Template

```markdown
## Experiment E? — Short Mechanism Name

| Field | Value |
|---|---|
| Experiment ID | `E?` |
| Baseline | `E?` |
| Mechanism version | e.g. `tool-schema-check-v1` |
| Modified files | `path/to/file.py:line` |
| Behavioral change | One sentence |
| Recursion used | No |
| Model/parameters | model / reasoning_effort / temperature / k / max_iterations |
| Dataset | version / item count / deduplication |
| Output | `results/...json` |

### Mechanism Hypothesis

Which error class should this solve, and why?

### Results

| Metric | Baseline | Experiment | Change |
|---|---:|---:|---:|
| Overall accuracy | | | |
| `TOOL_ERROR` | | | |
| `UNVERIFIED_FINAL` | | | |
| `AGGREGATION_REASONING` | | | |
| `DATASET_OR_GOLD_CONFLICT` | | | |
| Mean iterations | | | |
| Mean LLM calls | | | |

### Representative Traces

- Improved: `bird_...`
- Not improved: `bird_...`
- Possible regression: `bird_...`

### Conclusion

- [ ] Keep: mechanism effective
- [ ] Restrict: only improves a specific class
- [ ] Revert: ineffective or regressive
- [ ] More runs required

### Next Step

State the next single variable, control, and validation metric.
```

## 8. Current Conclusion

The best validated configuration remains E3-C Schema v4 at 77/197 (39.09%). Formal E4-A schema-v3 reached 71/197 (36.04%): 3 recoveries, 9 regressions, a net loss of 6, and +6.67% total tokens/item. The preregistered acceptance criteria fail.

> **2026-08-07 correction**: this section originally read "aggregation/order failures fell from 45 to 41, but output, filtering, Schema, and runner failures rose" — computed with the pre-fix classifier (§4.1). With the fixed classifier, **the direction reverses**: aggregation/order actually rose from 29 to 33 (**+4 — E4-A's own design target got worse**), while Schema/Join fell from 46 to 42 (-4, an improvement). The target-category (aggregation+output) recovered/regressed also moves from the original "3:3 tie" to **3:5** (a net regression), which is more unfavorable to E4-A than originally reported. The reject/revert decision is unchanged (it rests on raw correct/incorrect counts, unaffected by classification), but the attribution should read: **QueryPlan directly made its own primary target worse — this was not "target improved, dragged down by side effects elsewhere."** See [`e4_a_core197_run1_summary.md`](analysisDetail/e4_a_core197_run1_summary.md) and [`e4_a_core197_run1_vs_e3c_e0.md`](analysisDetail/e4_a_core197_run1_vs_e3c_e0.md).

The trajectory audit also found 82 failed items whose executions passed every structural adherence check (this count comes from QueryPlan's internal consistency checker, not the semantic classifier, so it is unaffected by the fix). The dominant issue is a semantically wrong QueryPlan, not SQL failing to follow the plan. Only 2 of 19 items with valid revisions were correct, with zero wrong-to-correct recovery transitions. Reject E4-A, revert to E3-C, and pause E5/E6. Complete F-Audit next; any QueryPlan redesign must first be evaluated on train-only development data rather than tuned against the fixed 197 gold answers. F-Audit's sampling scope should also be redefined against the corrected filter-category count (36 combined across the two E0 runs, not the original 67).
