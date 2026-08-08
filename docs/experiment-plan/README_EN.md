# Unified DB-RLM Experiment Plan

> English version of [README.md](README.md). The Chinese document remains the operational source; this version preserves the same definitions, results, gates, and run decisions.

Version: v1.0  
Updated: 2026-07-15
Current status: E4-A core197 is complete and rejected: 71/197 (36.04%), six below its E3-C parent; 3 recovered, 9 regressed, and total tokens/item rose 6.67%. The best validated configuration reverts to E3-C Schema v4. E5/E6 are paused; do not carry the failed QueryPlan into context-store or Leaf experiments. F-Audit is next. Historical E3-C run2 and E3-F v1/v3 remain diagnostic only, and E3-D/E3-F remain paused because no Query Mining v2 slot passes the cross-database gate. **2026-08-07: fixed several detection gaps in the semantic classifier and regenerated classification for all 7 completed experiments** (see `../analysis/README.md` §4.1); Schema/Join moves from the smallest error category to the largest, the E4-A reject decision is unchanged but its attribution reverses — QueryPlan made its own target category (aggregation/order) worse rather than being dragged down by Schema — see §3.3, §3.5, §7.1, §8.1.
Formal dataset: fixed 197 items from `bird_cleancore_ids.json`.  
Principle: experiment order is driven by each run’s error trajectories. Change one attributable mechanism at a time; after every run, analyze the full trace, dual-label semantic attribution, recovered/regressed IDs, and cost before selecting the next variable.

## 0.1 Why Classification and Ablation Are Necessary

The goal is not to stack modules into the Agent at once, but to validate three mechanisms incrementally:

1. **Programmable context and code-based reasoning:** organize Schema, metadata, query patterns, QueryPlan, observations, and evidence references into searchable/composable structures instead of one opaque long Prompt.
2. **Controlled execution environment:** constrain tools, DB access, observations, termination, and context reads through manifests and capability gates so runs are reproducible and runtime failures remain separate from semantic errors.
3. **Verifiable self-improvement and divide-and-conquer:** Root creates a global QueryPlan and revises constraints from DB feedback. A depth-1 Leaf is allowed only for an explicit independently verifiable complex SubPlan and must be compared with matched-budget extra Root deliberation.

These cannot be tested as one package because E0 failures arise at different layers. Across the two E0 runs, 259 failure records include (2026-08-07 corrected, see `../analysis/README.md` §4.1) Schema/Join (97), aggregation/ordering (65), output contract (56), filtering semantics (36), and runner/parser/tool failures (5) — originally reported as aggregation/ordering (93), filtering semantics (67), output contract (56), Schema/Join (38), and runner/tool (5); the pre-fix classifier never compared JOIN keys or actual GROUP BY/ORDER BY columns, only keyword presence, which systematically undercounted Schema/Join. Of 124 stable failures, 111 retain the same semantic class (originally reported as 110). Control-flow labels such as `UNVERIFIED_FINAL` mask underlying semantics, and E1 showed that strict verified-final adds cost without solving the main errors.

The direct mechanism mapping derived from all 259 failure records is (corrected):

| E0 failure attribution (corrected) | Direct mechanism | Experiment order |
|---|---|---|
| 5 runner, parser, or tool failures | Structured observations, retries, resume, and explicit termination reasons | `E2-A`, infrastructure only |
| 75 table-selection/Join-path errors (was part of 38) | Offline Schema Context, field semantics, PK/FK, relationship cardinality, and relevant-fragment selection | `E3-C` |
| 22 JOIN-key/condition errors (new subcategory, previously undetected) | Same as above, plus checking foreign-key columns used in JOIN `ON` conditions | `E3-C` |
| 36 filter-scope/expression errors (was 67) | First distinguish Agent errors from gold ambiguity; then combine value semantics with question-level condition structure | `F-Audit` → `E3-C` / `E4-A`; `E5-B` if needed |
| 43 aggregation/grouping errors (was 82) | Explicit target entity, grain, grouping keys, aggregate functions, `WHERE/HAVING`, and stage dependencies | `E4-A`; enter `E6` only when residual cases contain a separable SubPlan |
| 22 ordering errors (was 11) | Explicit ordering metric, direction, Top-K, ties, and `LIMIT` scope | `E4-A` |
| 48 output-column-count errors (unchanged) | Fix answer type, column count/order/source, and projection checks | `E4-A` |
| 8 YES/NO versus row-output errors (unchanged) | Fix boolean/scalar/rows answer form before SQL generation | `E4-A` |

These detailed classes sum to 259 (5+75+22+36+43+22+48+8). Experiment order follows post-run `semantic_error_class`, not the masking `UNVERIFIED_FINAL` control-flow label. Schema/Join (97) is now the largest of the four semantic classes, ahead of aggregation/order (65); the actual run order (E3-C before E4-A) happened to already match the corrected ranking, but F-Audit's sampling scope needs to be redefined against the corrected 36 filter records.

The evidence loop is:

```text
run the fixed 197 items
  ↓
read manifest, trace, observations, SQL changes, and token/call cost
  ↓
attribute control flow + semantic_error_class
  ↓
compare target classes, stable failures, recovered/regressed, and non-target regressions
  ↓
select one evidence-supported mechanism increment
  ↓
freeze all other variables, run the next stage, and update this plan
```

Experiment IDs denote evidence-driven stages, not a predetermined architecture. If target errors do not fall, repair or revert the mechanism rather than stacking another module.

## 0. Mechanism Taxonomy

| Category | Family | Core question | Included | Boundary |
|---|---|---|---|---|
| A. Baseline and control flow | E0, E1 | What can the current Agent do, and is strict FINAL useful? | Clean DB ReAct, strict verified-final control | No new knowledge or context-access change |
| B. Infrastructure and capability isolation | E2 | Are traces and tool boundaries reliable enough? | Structured observations, termination, resume, capability gate | Not an accuracy mechanism; no semantic knowledge |
| C. Offline Knowledge | E3 | Does prebuilt knowledge have independent value? | Query patterns, Offline Schema Context, Join metadata, value formats, later repair rules | No QueryPlan/recursion; E3-C uses pre-call deterministic selection only |
| D. Online question formalization | E4 | Can the model convert the current question into checkable constraints? | QueryPlan, filter structure, Output Contract | Online reasoning, not an Offline artifact |
| E. RLM context environment | E5 | Is the same information used better through programmatic access? | context store, `search/slice/compose`, fragment references | Same information set; no Leaf |
| F. Controlled recursion | E6 | Does decomposition beat matched-budget Root thought? | Extra-Root control and one depth-1 SubPlan Leaf | Run only after E5; Leaf cannot rebuild the global plan |

Filtering audit is an E4 support task without an experiment number. Trace folding is deferred efficiency work.

## 1. Three Main Mechanisms Intended for the Agent

### 1.1 Code-Based Reasoning and Context Exploration

The model should be able to execute controlled operations rather than passively read a complete Prompt:

- `search` by table, column, concept, pattern, or keyword;
- `slice` only the fragment required by a SubPlan;
- `compose` Schema, metadata, patterns, and observations;
- persist structured QueryPlan, candidate SQL, evidence references, and execution state.

The goal is traceable, reproducible context use with fewer omissions in long prompts.

### 1.2 Controlled Code Execution Environment

The environment stores Schema, Hint, PK/FK, Join paths, Offline artifacts, DB observations, candidate SQL, QueryPlan, and Root/Leaf calls. Every experiment uses a capability gate and only manifest-declared tools. Hidden Schema APIs and generic `recursive_llm` are forbidden in controls.

### 1.3 Self-Improvement and Divide-and-Conquer

```text
Root global QueryPlan
  ↓
DB ReAct execution and feedback
  ↓
optionally choose one complex SubPlan
  ↓
Leaf returns local evidence or an SQL fragment
  ↓
Root merges under the global grain/output contract and submits
```

Recursion must be compared with matched-budget extra Root deliberation to establish that decomposition itself helps.

## 2. Research Questions and Causal Boundaries

In order, this plan asks:

1. Do offline patterns, Schema/Join metadata, and later repair rules have independent value? Can patterns replace train few-shot?
2. Does a question-level QueryPlan reduce aggregation, ordering, and output errors?
3. Do Schema metadata and Join paths reduce table/join errors?
4. Is the same information fully reachable after externalization?
5. Is programmatic search/slicing/composition better than direct Prompt injection?
6. Under equal extra-call budget, is a controlled Leaf better than more Root thought?

Existing DB ReAct, SQL-error/empty feedback, the high-reasoning model, the capability gate itself, and post-run gold-based classification are not new contributions.

Gold is allowed only for offline scoring and post-run diagnosis. It must not enter the Agent, Prompt, artifact, retrieval, QueryPlan, or online routing.

## 3. E0 Baseline and Error-Driven Order

### 3.1 E0 Definition

E0 uses `clean-e0` / `clean-protocol-v1`, train-only `k=1` few-shot, direct Hint + Schema + few-shot context, `db.sample_values`, `db.execute`, and multi-turn DB ReAct. Verified-final is off. It has no patterns, legacy hints, metadata, QueryPlan, context store, or recursion.

### 3.2 Completed E0 Results

| Metric | Run1 | Run2 | Aggregate |
|---|---:|---:|---:|
| Correct | 69/197 | 66/197 | mean 67.5/197 |
| Accuracy | 35.03% | 33.50% | mean 34.26% |
| LLM calls/item | 2.76 | 2.72 | 2.74 |
| DB calls/item | 1.89 | 1.90 | 1.90 |
| Total tokens/item | 13,658.99 | 13,481.25 | 13,570.12 |

- 62 always correct, 124 always failed, 11 unstable.
- Evaluation SQL-timeout fields differ; these are not strict replications.
- Token usage is missing for 9/11 calls, so cost is a lower bound.

Detailed report: [E0 summary](../analysis/analysisDetail/e0_core_summary.md).

### 3.3 E0 Dual-Label Error Distribution (2026-08-07 corrected, see `../analysis/README.md` §4.1)

Use `semantic_error_class`, because `UNVERIFIED_FINAL` masks semantic causes. The pre-fix classifier only checked GROUP BY/ORDER BY keyword presence and never compared JOIN keys, systematically undercounting Schema/Join and overcounting the filter bucket.

| Cause | Run1 | Run2 | Total | Share of failures | Pre-fix total |
|---|---:|---:|---:|---:|---:|
| Schema/Join | 49 | 48 | 97 | 37.45% | was 38 (14.67%) |
| Aggregation and ordering | 32 | 33 | 65 | 25.10% | was 93 (35.91%) |
| Output contract | 29 | 27 | 56 | 21.62% | unchanged |
| Filter scope/expression | 17 | 19 | 36 | 13.90% | was 67 (25.87%) |
| Runner/parser/tool | 1 | 4 | 5 | 1.93% | unchanged |

| Stable-failure class (corrected) | Items | Pre-fix |
|---|---:|---:|
| Schema/Join | 42 | was 16 |
| Aggregation and ordering | 29 | was 41 |
| Output contract | 25 | unchanged |
| Filtering semantics | 14 | was 28 |
| Class changes/runtime noise | 14 | unchanged |

Of 124 stable failures, **111** (originally reported as 110) keep the same broad semantic class; the same-subcategory count (107) has not been recomputed. The composition shifted from aggregation-dominated to Schema/Join-dominated. Recovering stable structural failures is more important than raising one run's total score.

### 3.4 Interpreting `UNVERIFIED_FINAL`

There are 215 such records across E0:

| Subcategory | Count | Meaning |
|---|---:|---|
| Rewritten after an incorrect observation, not executed | 180 | Submitting the last executed SQL would still be wrong |
| Rewritten after an unparseable observation | 18 | Trace/tool observability issue |
| FINAL without DB execution | 9 | Control-flow problem |
| Regressed after a correct observation | 4 | Real loose-FINAL regression |
| Rewritten after empty result | 3 | Needs re-execution but is not the dominant source |
| Successful observation could not be aligned | 1 | Historical trace limitation |

Keep this as a control-flow diagnostic, not an experiment-priority metric. E1 showed strict verified-final should not be enabled by default.

### 3.5 Improvement Order Derived from E0 (2026-08-07 evidence corrected; order unchanged)

> The actual run order (E3-C before E4-A) already matches the corrected category sizes, so it is unchanged. Only F-Audit's sampling scope needs to shrink from the original 67 records to the corrected 36.

| Priority | Evidence (corrected) | Mechanism | Experiment |
|---:|---|---|---|
| 0 | 5 runner/parser/tool records; observation parsing affects attribution | Trace, manifest, structured observations | E2-A |
| 1 | 97 Schema/Join records (was 38) | Independently test Offline metadata, PK/FK, Join paths; disable unvalidated static patterns | E3-C |
| 2 | 65 aggregation/order (was 93), 56 output (unchanged), 36 filtering (was 67); static E3-A coverage weak | Formal train question+SQL Query Mining, then conditional few-shot ablation | E3-D, E3-E |
| 3 | 65 aggregation/order (was 93); 56 output (unchanged) | Root QueryPlan + Output Contract | E4-A |
| 4 | 36 filtering (was 67), low confidence | Manual audit; QueryPlan condition structure; value retrieval if needed | F-Audit, E4-A, E5-B |
| 5 | Direct Prompt may underuse context | Information-equivalent externalization and programmatic retrieval | E5-A, E5-B |
| 6 | Complex multi-stage failures remain | QueryPlan-driven depth-1 Leaf | E6-A, E6-B |

Recheck error migration after every stage. Do not skip E3-C, E4-A, or E5-B merely because recursion is the eventual target. Schema/Join (97) is now larger than aggregation/order (65), consistent with the E4-A rejection: E4-A's own target category was smaller than originally believed.

## 4. Unified Experimental Protocol

### 4.1 Fixed Data and Model

| Variable | Fixed value |
|---|---|
| Dataset | `data/processed/bird_dev_500.json` |
| ID file | `data/processed/bird_cleancore_ids.json` |
| Groups | `both_wrong` 137 + `canary` 60 = 197 |
| Train pool | `data/train_pool.json`, 9,428 examples |
| Model | `azure/seminar-gpt-5.4-mini` |
| Temperature | `0` |
| Reasoning effort | `high` |
| Max iterations | `8` |
| SQL timeout | `30s` |
| Evaluator | Same BIRD execution evaluator |
| New-config repetitions | One full 197-item run under the time budget |

Keep ID order fixed. Smoke tests validate code, information equivalence, and traces; they do not support accuracy claims.

### 4.2 Single Variable and Manifest

Every run records run/profile/parent/config hashes; dataset/ID/database hashes; Prompt version/hash; requested/effective few-shot `k`, pool hash, retriever; artifact hashes; context mode and capability manifest; QueryPlan schema; Leaf depth/count/budget; planned/completed counts; model parameters, timeout, and usage completeness. If an old manifest differs from the current configuration, create new output/trace paths rather than mixing runs.

### 4.3 Unified Outputs

```text
results/<experiment>_core197_run1.json
trace/<experiment>_core197_run1/run_manifest.json
trace/<experiment>_core197_run1/transcripts.jsonl
trace/<experiment>_core197_run1/classification_sheet.csv
trace/<experiment>_core197_run1/traces_report.html
docs/analysis/analysisDetail/<experiment>_summary.md
docs/analysis/analysisDetail/<experiment>_vs_parent.md
```

### 4.4 Required Metrics

| Type | Metrics |
|---|---|
| Primary | Correct count, execution accuracy |
| Paired | both correct, recovered, regressed, both wrong, IDs |
| Stability | Recoveries among 124 stable E0 failures; regressions among 62 stable successes |
| Errors | Aggregation/order, filtering, output, Schema/Join, runtime |
| Groups | difficulty and both_wrong/canary |
| Cost | Root/Leaf/LLM/DB calls and token categories |
| Reliability | API, parse, timeout, missing FINAL, missing usage |
| RLM environment | Context reads, search terms, fragment IDs/hashes, visible tokens |

### 4.5 Unified Error Classification

The classification sheet must include `wrong_turn,error_class,subcategory,semantic_error_class,semantic_subcategory,fix_idea,notes`.

| Class | Evidence | Confidence | Target |
|---|---|---|---|
| Aggregation/order | GROUP BY, aggregate, HAVING, ORDER/LIMIT differences | Medium | E4-A |
| Output contract | Column count/order, boolean/rows/scalar differences | Medium-high | E4-A |
| Schema/Join | Table set, column owner, Join path | Medium | E3-C |
| Filtering semantics | Operator, value, time, AND/OR, scope | Low | F-Audit, E4-A, E5-B |
| Control flow | FINAL not executed, rewrite not executed, MaxIterations | High | Diagnosis/infrastructure |
| Runtime/tool | API, parse, timeout, unparseable observation | High | E2-A |

Gold differences are post-run evidence only and must not enter the next Prompt or artifact.

### 4.6 Decision Rules

- A single change below roughly 2 pp is a trend only.
- Always inspect target-class net change and recovered/regressed IDs.
- Do not accept a target-class reduction that causes major non-target regressions.
- Runner/API recovery is not reasoning gain.
- When cost rises, report cost per recovered item.
- Stop a branch when acceptance criteria fail; do not continue stacking.

## 5. Stage A: Baseline and Control Flow (E0/E1)

| Experiment | Parent | Only variable | Purpose | Status |
|---|---|---|---|---|
| E0 | None | Clean DB ReAct baseline | Accuracy, cost, stability, errors | Complete, two 197 runs |
| E1 | E0 | FINAL equals latest successful non-empty executed SQL | Test strict verified-final inheritance | Complete and rejected |

### 5.1 E0: Clean DB ReAct

| Field | Value |
|---|---|
| Parent | None |
| Purpose | Establish clean baseline |
| Scope | 197 items, two exploratory runs |
| Result | 69/197 and 66/197; mean 34.26% |
| Decision | Historical comparison center |

### 5.2 E1: Strict Verified-Final

| Field | Value |
|---|---|
| Parent | E0 |
| Only variable | FINAL equals latest successful, non-empty, executed SQL |
| Scope | Paired first 70 |
| E0 paired mean | 42.14% |
| E1 | 28/70 = 40.00% |
| Cost | Calls ≈2.03×; tokens ≈2.00×; latency ≈1.75× |
| Behavior | 103 `final.blocked` events across 63/70 |
| Stable transitions | 0 stable failures recovered; 3 stable successes regressed |
| Decision | Reject |

E1 removes the label but does not repair aggregation, output, filtering, or Schema semantics. Later stages do not inherit it. [E1 report](../analysis/analysisDetail/e1_verified_summary.md).

## 6. Stage B: Infrastructure and Capability Isolation (E2)

| Experiment | Parent | Only variable | Purpose | Status |
|---|---|---|---|---|
| E2-A | Content-independent | Structured observations, termination, resume, missing usage | Parseable/reproducible traces | Required before formal runs |
| E2-B | E0 | Capability gate, declared tools only | Capability isolation audit | Complete; historical result name E4-R0 |

### 6.1 E2-A: Structured-Observation Prerequisite

This is not an accuracy ablation. `db.execute` returns `{sql,status,columns,rows,error,truncated}`; traces store raw structured results; APIError/timeout/empty FINAL/parse failure use distinct termination; resume does not change completed items; missing usage is separate. All smoke observations must be parseable before a formal run.

### 6.2 E2-B: Capability-Gate Calibration

| Field | Value |
|---|---|
| Parent | E0 |
| Only variable | Allow `db.execute` and `db.sample_values`; forbid recursion/hidden Schema APIs |
| Scope | First 50 |
| Result | 19/50 = 38.00%; E0 = 38%/40% |
| Audit | 110/110 events allowed; zero violations |
| Decision | Accept as infrastructure, not an accuracy mechanism |

Later E3-C, E4-A, E5, and E6 inherit capability isolation. [E4-R0 report](../analysis/analysisDetail/e4_r0_summary.md).

## 7. Stage C: Offline Knowledge (E3)

### Complete Offline-System Definition

An Offline system is not merely query mining. Before evaluation, it constructs, audits, versions, and indexes knowledge artifacts from compliant sources. Runtime reads frozen artifacts and never updates them from current eval gold, scores, or failures.

```text
Offline System
├─ Query/SQL mining
│  ├─ aggregation grain and multi-stage aggregation
│  ├─ filtering, Top-K, ordering, DISTINCT
│  ├─ output contracts and conditional answers
│  └─ generic Join/window structures
├─ Schema/metadata mining
│  ├─ tables, columns, types, semantics, aliases
│  ├─ PK/FK, Join graph, candidate paths
│  ├─ cardinality and duplicate-row risk
│  └─ value/date/unit/NULL/encoding formats and controlled samples
├─ train error/repair mining
│  ├─ triggers and repair actions
│  ├─ applicability boundaries
│  └─ counterexamples
└─ artifact governance
   ├─ source and split
   ├─ builder and version
   ├─ support, coverage, SHA-256
   └─ retrieval, capability boundary, leakage audit
```

| Layer | Responsibility | Current implementation |
|---|---|---|
| Content construction | Derive reusable knowledge from train question/SQL, database Schema/descriptions, and compliant train traces | E3-A static prototype; E3-C metadata; E3-D Query Mining; E3-F integration |
| Artifact governance | Freeze provenance, version, support, hash, coverage, and build config | `train-static-v1`, `e3-f-schema-v4`, `train-mined-v2`, manifests |
| Runtime delivery | Full injection, deterministic fragments, or active retrieval | E3-C deterministic fragments; E3-D mined retrieval; E5 active `search/slice/compose` |

A complete artifact is not a complete Prompt. Per item, only relevant tables, fields, and FK neighborhoods should be delivered. Root verifies uncertain information with `db.sample_values`/`db.execute`.

E3 asks what offline content is useful under a fixed delivery policy. E5 asks whether the model can actively search/slice/compose the same content. E3-C’s pre-call lexical/FK selection is not model-driven context exploration.

Train few-shot is an existing E0 reference, not a query-mining artifact. `train-static-v1` lacks normalization, support, clustering, boundaries, and question-level retrieval. E3-B only shows that this static prototype cannot replace few-shot. E3-C disables patterns and keeps few-shot; E3-D adds formal Query Mining; E3-E removes few-shot only if E3-D works.

Artifact lifecycle:

1. Freeze allowed sources/splits.
2. Build and record script, parameters, version, provenance, SHA-256.
3. Audit structure, coverage, and leakage without looking at current experiment scores.
4. Freeze artifact and retrieval, then run.
5. Analyze full traces, semantic errors, transitions, fragment coverage, and cost.
6. Propose the next hypothesis, but never rewrite online artifacts from the fixed 197 gold/failure SQL.
7. Only new compliant train evidence may enter the next artifact version.

QueryPlan, DB observations, FINAL control, active `search/slice/compose`, Root/Leaf routing, and recursion are not Offline content.

| Experiment | Parent | Offline increment | Target | Status |
|---|---|---|---|---|
| E3-A | E0 | Manual train-only static patterns; keep few-shot | Static prototype | Complete; weak evidence |
| E3-B | E3-A | Remove train few-shot | Replacement value/cost | Complete and rejected |
| E3-C | E0 | Disable static patterns; keep few-shot; replace runtime full Schema with Offline Schema Context | Linking, joins, Prompt redundancy | Complete and accepted: 77/197; E4-A parent |
| E3-D | E3-C | Mine/normalize/cluster/retrieve train question+gold SQL patterns | Aggregation, order, filter, output, joins | To design/implement |
| E3-E | E3-D | Remove few-shot only | Can complete Offline knowledge replace it? | Conditional |
| E3-F | E0 protocol + `k=1` | Schema v4 + gated/abstaining Query Mining v2 | Integrated system | Historical v1/v3 diagnostic complete; current v2 blocked |

### 7.1 Offline Scope and Error Evidence (2026-08-07 corrected)

| Content | Evidence (corrected) | Why Offline | Experiment |
|---|---|---|---|
| Query Mining/patterns | 65 aggregation/order (was 93), 56 output, 36 filtering (was 67); E3-A weak on aggregation/output | Derivable from train question+SQL signatures, support, triggers, boundaries | E3-A/B prototype; E3-D formal |
| Schema semantics | **97 Schema/Join (was 38, now the largest category), 42 stable (was 16)** | Database-level table/column semantics can be built before answering | E3-C |
| PK/FK, paths, cardinality | Missing tables, wrong joins, duplicate-row aggregation; 22 of the 97 are JOIN-key/condition errors (new subcategory — right tables, wrong foreign key) | Derivable from Schema/constraints/compliant sources | E3-C |
| Value types/formats/samples | String/date/unit/NULL/filter-value errors | Cacheable database metadata, verified online with samples | E3-C |
| Repair rules | 111/124 stable failures retain semantic class (was reported as 110), now Schema/Join-dominated rather than aggregation-dominated | Only from compliant train error traces | Deferred |

### 7.2 E3-A: Train-Only Static Patterns (Complete)

| Metric | Result |
|---|---|
| Parent | E0 |
| Only variable | Add fixed train-only pattern library; keep `k=1` |
| Result | 73/197 = 37.06% |
| Relative to E0 mean | +2.79 pp |
| Total tokens/item | 14,751.72; +8.7% |
| Stable transitions | 6 recovered against both E0 runs; 1 stable regression |
| Decision | Historical static-prototype evidence only; not default parent |

Aggregation, output, and Schema errors show no clear improvement. Filtering falls to 24 from E0’s 33–34 but requires F-Audit. This does not prove Query Mining. [Summary](../analysis/analysisDetail/e3_a_summary.md), [comparison](../analysis/analysisDetail/e3_a_vs_e0.md).

### 7.3 E3-B: Replace Train Few-Shot with Patterns

| Metric | E3-A | E3-B | Change |
|---|---:|---:|---:|
| Effective `k` | 1 | 0 | profile-enforced |
| Correct | 73/197 | 72/197 | -1 |
| Accuracy | 37.06% | 36.55% | -0.51 pp |
| Total tokens/item | 14,751.72 | 15,421.28 | +4.54% |
| LLM calls | 539 | 552 | +13 |
| Recovered/regressed | — | 4/5 | net -1 |

Reject: removing few-shot did not lower cost or preserve accuracy. This rejects only `train-static-v1` replacement, not formal statistically supported retrieval. [Summary](../analysis/analysisDetail/e3_b_summary.md), [paired analysis](../analysis/analysisDetail/e3_b_vs_e3_a_e0.md).

### 7.4 Lock E3-C Controls

Return to E0 knowledge controls: keep protocol Prompt, `k=1`, FINAL/ReAct, data, and parameters; disable `train-static-v1`. The only knowledge change is replacing runtime full Schema with prebuilt Offline Schema Context. Manifest must show `query_pattern_mode=none`, artifact hash, `schema_context_mode=offline-retrieval`, and deterministic retrieval.

### 7.5 E3-C: Offline Schema Context Replacement

Target: 38 E0 Schema/Join records and 16 stable same-class failures.

Replace per-item runtime full Schema with a source-compliant database-level artifact. Before the model call, fixed lexical matching and FK adjacency select relevant table/field fragments. Active search remains E5.

Artifact content: table/column descriptions, aliases and semantics, PK/FK graph and candidate paths, cardinality/duplicate risk, value types/formats/samples, and complete provenance/version/hash.

The Prompt receives matched tables/fields, necessary FK neighbors, and a database table directory, not another full `db.format_schema()`. This tests the combined value of content plus deterministic fragment selection; E5 later isolates active access.

Acceptance:

1. Net Schema/Join reduction versus the locked parent.
2. Stable Schema recovered > regressed.
3. No material aggregation increase from duplicate joins.
4. Complete token/provenance/hash/retrieval/selection records.
5. Prompt tokens do not rise materially through duplicated Schema.

Current entry:

- historical full-metadata smoke `results/e3_c_core197_run1.json` is diagnostic only;
- profile `e3-c` disables patterns, keeps `k=1`, enables `e3-f-schema-v4`, offline retrieval, and the capability gate;
- run a smoke first and verify `offline_metadata.artifact_sha256` before a full 197-item run.

```powershell
.\.venv\Scripts\python.exe scripts\run_bird_train_fewshot.py `
  --agent-profile e3-c `
  --dataset data\processed\bird_dev_500.json `
  --ids-file data\processed\bird_cleancore_ids.json `
  --id-groups both_wrong canary `
  --database-dir data\raw\bird\minidev\MINIDEV\dev_databases `
  --output results\e3_c_schema_v4_core197_run3.json `
  --trace-dir trace\e3_c_schema_v4_core197_run3 `
  --model azure/seminar-gpt-5.4-mini `
  --k 1 `
  --max-iterations 8 `
  --reasoning-effort high
```

Historical `e3_c_schema_v4_core197_run2` is invalid: all 197 calls failed with the same nonexistent Azure deployment and must not enter accuracy analysis.

### 7.6 E3-D: True Offline Query Mining

Parent: accepted E3-C. Keep Offline Schema Context and `k=1`; add only a reproducible Query Mining artifact built from train questions and train gold SQL.

Build process:

1. Parse train SQL AST and normalize database identifiers, literals, and aliases.
2. Extract structural signatures for joins, filters, aggregation, HAVING, order, Top-K, set operations, and output shape.
3. Cluster signatures and record support, database coverage, and linguistic triggers.
4. Generate applicability conditions, operation templates, boundaries, and counterexamples without storing copyable eval answers.
5. Freeze artifact, provenance, build parameters, and SHA-256.
6. At runtime, retrieve patterns using the question and E3-C Schema fragment; log pattern IDs, scores, reasons, and final-SQL adherence.

Unlike E3-A’s globally injected hand-written rules, E3-D requires reproducible mining, support filtering, and question-level retrieval. Accept only if target semantic errors fall, recovered > regressed, retrieval is interpretable, and token/latency cost is acceptable.

### 7.7 E3-E: Few-Shot Replacement Ablation for Mined Patterns

Run only if E3-D is accepted. Keep Schema Context, mined artifact, retrieval, model, and budget fixed; change effective few-shot from `k=1` to `k=0`.

- Preserve accuracy and lower cost: accept E3-E; complete Offline knowledge can replace few-shot.
- Accuracy falls or cost does not fall: reject E3-E and retain E3-D.
- E3-D fails: do not run E3-E.

### 7.8 E3-F: Complete Offline System + Few-Shot

#### 7.8.1 Historical v1/v3 Partial Run

`e3_f_core197_run1` started before the repairs with `train-mined-v1 + e3-f-schema-v3 + k=1 few-shot`. It stopped at 53/197 and is frozen as a historical diagnostic.

| Field | Record |
|---|---|
| run_id | `20260714T075259Z-f3c7e719` |
| Status | `interrupted`; 53/197; only 4/11 databases |
| Result | 21/53 = 39.62% |
| Same-item E0 mean | 36.79%; historical E3-F +2.83 pp |
| Cost | 16,426.79 tokens/item; +40.34% over E0 |
| Failure attribution | Aggregation 9, output 9, filtering/semantics 7, Schema 6, runner/API 1 |
| Schema v3 | Delivered every table in the current DB on 53/53 items |
| Query Mining v1 | 2.85 cards/item; exact gold shape present on only 16/53 |
| Decision | Do not resume or treat as complete; do not use to evaluate v2/v4 |

- [Partial summary](../analysis/analysisDetail/e3_f_core197_run1_partial53_summary.md)
- [Same-item E0/E3-A/E3-B comparison](../analysis/analysisDetail/e3_f_core197_run1_vs_e0_e3a_e3b_partial53.md)
- [All 32 semantic attributions](../analysis/analysisDetail/e3_f_core197_run1_semantic_failures.csv)
- [Per-item retrieval audit](../analysis/analysisDetail/e3_f_core197_run1_retrieval_audit.csv)

The run shows that v1/v3 had design problems: a weak accuracy movement with much higher cost, no effective Schema compression, and overly broad forced Top-K/fallback Query Mining. It is not evidence about the repaired complete Offline system.

#### 7.8.2 Preregistered v2/v4 Definition

E3-F is an integrated engineering experiment rather than a single-variable ablation. It retains E0 protocol Prompt, FINAL/ReAct, model, budget, and train few-shot `k=1`, and enables:

- `e3-f-schema-v4`: repaired FK targets; separate declared/high-confidence inferred joins; key coverage, child fan-out, NULL fractions, ranges; detailed lexical seeds, bridge paths, and at most the best neighbor per seed; remaining identifiers names-only; hashes for inputs, builder, and runtime retriever.
- `train-mined-v2`: independent plan slots mined from 9,428 train SQL strings rather than conflicting complete-shape cards; deterministic rules; database-level five-fold validation; cross-database precision ≥0.95, at least 50 validation predictions, and effective-fold precision ≥0.90; abstain if no slot qualifies and never use a most-common fallback.

Boundaries: `query_pattern_mode=train-mined-v2`, no `train-static-v1`; `capability_gate=true`; only `db.execute` and `db.sample_values`; no runtime full Schema and no active `get_schema/get_tables`.

Each `attempts[].knowledge_selection` must record few-shot train ID/similarity/rank; Query Mining validation, matches, selected constraint or abstention; Schema candidate scores, seeds, shortest paths, bounded neighbors, truncation, field ranks, and delivered Join provenance/coverage/fan-out. The manifest freezes artifact, builder, runtime retriever, and embedding-model configuration hashes.

Current preflight:

- Schema v4 detailed-table coverage: 193/197.
- Multi-table gold queries connected in the declared+inferred Join graph: 168/168.
- Query Mining v2: **0 enabled slots and 0 delivered rules** after strict database-held-out validation.

The current profile safely abstains, but Query Mining is not “repaired” and formal E3-F must not start. At least one slot must pass the preregistered gate first. Validate Schema v4 independently through E3-C while Query Mining remains an E3-D design task.

Freeze `results/e3_f_core197_run1.json` as the historical v1/v3 partial run. A future eligible v2/v4 run must use `results/e3_f_schema_v4_query_v2_core197_run1.json`.

```powershell
.\.venv\Scripts\python.exe scripts\build_e3_f_schema_context.py
.\.venv\Scripts\python.exe scripts\build_e3_f_query_mining.py
.\.venv\Scripts\python.exe scripts\audit_e3_f_preflight.py --target schema
.\.venv\Scripts\python.exe scripts\audit_e3_f_preflight.py --target full

# Execute only after --target full passes.
.\.venv\Scripts\python.exe scripts\run_bird_train_fewshot.py `
  --agent-profile e3-f `
  --dataset data\processed\bird_dev_500.json `
  --ids-file data\processed\bird_cleancore_ids.json `
  --id-groups both_wrong canary `
  --database-dir data\raw\bird\minidev\MINIDEV\dev_databases `
  --output results\e3_f_schema_v4_query_v2_core197_run1.json `
  --trace-dir trace\e3_f_schema_v4_query_v2_core197_run1 `
  --model azure/seminar-gpt-5.4-mini `
  --k 1 `
  --max-iterations 8 `
  --reasoning-effort high
```

`--target schema` must pass before E3-C Schema-v4 smoke. `--target full` must pass before the E3-F command. Add `--limit 3` and new smoke paths before a full run, and verify `train-mined-v2`, `e3-f-schema-v4`, `effective_few_shot_k=1`, `capability_gate=true`, and `enabled_slot_count > 0` in the manifest.

After an eligible full run:

```powershell
.\.venv\Scripts\python.exe scripts\analyze_e3_f_retrieval.py `
  --results results\e3_f_schema_v4_query_v2_core197_run1.json `
  --transcripts trace\e3_f_schema_v4_query_v2_core197_run1\transcripts.jsonl `
  --out-json docs\analysis\analysisDetail\e3_f_schema_v4_query_v2_retrieval_audit.json `
  --out-csv docs\analysis\analysisDetail\e3_f_schema_v4_query_v2_retrieval_audit.csv
```

### 7.9 Lock the Offline Parent for E4-A

- E3-D accepted and E3-E preserves accuracy while lowering cost: use E3-E.
- E3-D accepted but E3-E rejected: use E3-D.
- An integrated E3-F succeeds before attribution is complete: it may be an engineering candidate, but report that gains are not decomposed.
- E3-D fails but E3-C succeeds: use E3-C.
- E3-C fails: return to E0; E3-A remains historical only.

## 8. Stage D: Online Question-Level Formalization (E4)

| Task | Parent | Only variable | Target | Status |
|---|---|---|---|---|
| E4-A | Locked E3 parent | QueryPlan + Output Contract in the same Root response | Aggregation, ordering, output, some filter structure | Complete and rejected: 71/197; six below E3-C; 3 recovered, 9 regressed |
| F-Audit | Relevant E0/E3-A/E4-A samples | Manual filter-boundary, logic, and gold-noise review | Trusted filtering subset | Support task |

### 8.1 E4-A: Root QueryPlan + Output Contract

Target E0’s 93 aggregation/order and 56 output records while structuring filters. Before first SQL, Root emits a QueryPlan in the same model response; no separate Planner call.

```json
{
  "target_entity": "",
  "grain": "",
  "schema_links": [],
  "required_tables": [],
  "joins": [],
  "filters": [{"field": "", "operator": "", "value_or_source": "", "scope": "row|aggregate"}],
  "group_by": [],
  "aggregates": [],
  "aggregation_scope": "none|per_entity|global",
  "aggregation_justification": null,
  "having": [],
  "order_by": [],
  "limit": null,
  "answer_type": "rows|scalar|boolean",
  "answer_scope": "per_entity_rows|single_entity_row|global_scalar|boolean",
  "output_columns": [{
    "position": 1,
    "semantic_item": "",
    "source_columns": ["Table.column"],
    "sql_expression": "",
    "source_justification": "",
    "aggregation": "none"
  }],
  "candidate_purpose": "explore|answer",
  "expected_result_shape": {
    "answer_type": "rows|scalar|boolean",
    "column_count": 0,
    "row_grain": ""
  },
  "unresolved_assumptions": [],
  "revision": null
}
```

Controls: use E3-C as the locked parent; do not add Query Mining, context store, or Leaf; preserve LLM budget, DB ReAct, and FINAL. Record parse success, initial/revised plan, SQL-plan adherence, output shape, and token increment. After an observation, `revision` records only the `observation_ref`, `changed_constraints`, `updated_fields`, and `reason` state delta. The first run measures adherence without adding a separate checker LLM call.

Accept when at least one target class falls, combined recovered > regressed, stable E0 target failures recover interpretably, no separate call causes the gain, and Schema/Join/canary do not regress unacceptably. If neither target class falls, repair the QueryPlan schema, timing, or adherence before considering recursion.

The final core197 result is 71/197 (36.04%), below E3-C's 77/197 (39.09%); four missing-FINAL failures appeared. Reject E4-A under the preregistered criteria.

> **2026-08-07 correction**: this paragraph originally read "aggregation/order fell by four, but output rose by one, filtering by five, Schema by one" — computed with the pre-fix classifier (see `../analysis/README.md` §4.1). With the fixed classifier, **the direction reverses**: aggregation/order actually **rose by four** (E4-A's own design target got worse), Schema/Join actually **fell by four** (improved), output is unchanged (+1), and filtering rose by 2 (not 5). The target-category recovered/regressed moves from the original "3:3 tie" to **3:5**. The reject decision is unchanged, but the correct attribution is: QueryPlan directly made its own primary target worse, not "target improved, dragged down by side effects."

See the [summary](../analysis/analysisDetail/e4_a_core197_run1_summary.md), [paired comparison](../analysis/analysisDetail/e4_a_core197_run1_vs_e3c_e0.md), and [trajectory audit](../analysis/analysisDetail/e4_a_core197_run1_trajectory_audit.md).

### 8.2 F-Audit: Manual Filtering Audit

Sample stable E0 filtering failures, E3-A filtering recoveries/regressions, and date/range/AND-OR/NULL/percentage/string cases. Record question, Hint, predicted/gold SQL, execution, operators, boundaries, time range, parentheses, scope, possible gold noise, and whether E4-A expressed the right condition. Output: `docs/analysis/analysisDetail/filter_audit.md`. Only confirmed Agent errors evaluate E4-A/E5-B.

## 9. Stage E: RLM Context Environment (E5)

| Experiment | Parent | Only variable | Purpose | Status |
|---|---|---|---|---|
| E5-A | Validated structured configuration | Externalize identical information | Information equivalence, reachability, isolation | Paused: E4-A failed |
| E5-B | Same configuration after E5-A | Root uses `search/slice/compose`; no Leaf | Programmatic access value | Paused |

### 9.1 E5-A: Information-Equivalent Externalization Smoke (Paused)

This verifies that the exact selected structured information reaches a context store without loss; it is not an accuracy claim. Use a small fixed set spanning difficulty, four error classes, and a multi-stage case. Compare section count/order/hash, Root-visible fields, direct-Prompt versus environment information sets, gate, and context-read trace. If hashes/reachability/isolation fail, repair the store rather than running 197.

### 9.2 E5-B: Context Store + Programmatic Search + QueryPlan (Paused)

Keep the information set fixed; change direct Prompt delivery to a context store with Root `search/slice/compose`. Keep the global QueryPlan and forbid Leaf.

Record search queries and fragment IDs, hashes, bytes/tokens read, compose outputs, misses/repeats/violations, QueryPlan fragment references, and total Root-visible tokens.

Accept when it is not materially worse than the corresponding direct structured configuration, improves target errors or tokens, has controlled miss/parse rates, recovered > regressed, and passes capability audit. If it regresses, repair context API, retrieval, or slicing before recursion.

## 10. Stage F: Controlled Recursion (E6)

| Experiment | Parent | Only variable | Purpose | Status |
|---|---|---|---|---|
| E6-A | E5-B | One extra Root deliberation on the same triggered items | Measure extra compute itself | Matched-budget control |
| E6-B | E5-B | One depth-1 SubPlan Leaf on the same items | Test decomposition over E6-A | Paired |

### 10.1 Recursion Prerequisites

Implement Leaf only after E5-B passes. Root creates the global plan; Leaf must not rebuild it. Allow triggers for multi-stage aggregation, complex Join+aggregation coupling, ambiguous condition scope, or an independently verifiable SubPlan. Do not recurse merely because the question is long or Root is uncertain.

### 10.2 E6-A: Extra Root Deliberation

Match E6-B on triggered items, extra-call count, input fragments, token limits, model, and reasoning effort. This measures the value of additional compute.

### 10.3 E6-B: Depth-1 SubPlan Leaf

- Maximum depth 1 and one Leaf call/item.
- Leaf receives one SubPlan plus relevant fragments only.
- No full context, DB access, FINAL, or recursion.
- Return structured evidence, local conclusion, or SQL fragment.
- Root merges, executes, and submits.
- Leaf failure triggers Root fallback without automatic retry.

```json
{
  "subplan_id": "",
  "evidence_refs": [],
  "local_conclusion": "",
  "candidate_sql_fragment": "",
  "assumptions": [],
  "confidence": "low|medium|high"
}
```

Accept recursion only if E6-B beats E6-A, stable complex recoveries exceed regressions, target aggregation/Join errors fall, evidence is traceable to final SQL, cost is acceptable, and no global grain/output conflicts appear.

## 11. Deferred Extensions

| Artifact | Content | Current mapping |
|---|---|---|
| Query patterns | Aggregation, filters, Top-K, output, joins | E3-A/B static prototype; E3-D ablation; E3-F v2 currently abstains entirely |
| Metadata | Field semantics, PK/FK, paths, cardinality, formats | E3-C ablation; E3-F uses Schema v4 |
| Repair rules | Triggers, repairs, boundaries, counterexamples | Deferred, no current ID |

Repair rules require compliant train traces. Never derive online rules from the 197 eval gold/scores. Trace folding is efficiency-only and must preserve the active QueryPlan, latest observation, unresolved constraints, and evidence references; do not test it before the main architecture is fixed.

## 12. Dependencies and Execution Order

```text
complete: E0
          ├─ E1 (rejected)
          ├─ E2-B (capability infrastructure; historical name E4-R0)
          └─ E3-A (historical static prototype; not default parent)

prerequisite: E2-A
  ↓
complete: E3-B (reject pattern replacement of few-shot)
  ↓
historical E3-C run2: stopped at 62/197; diagnostic only
  ↓
historical E3-F v1/v3: stopped at 53/197; analysis complete; not formal
  ↓
next E3-C: Schema v4 + few-shot component smoke and attribution
  ↓
E3-D: design and validate true Query Mining; cross-DB gate required
  ↓
E3-E: matched few-shot ablation only if E3-D works
  ↓
E3-F: integrate only after both Schema and Query Mining gates pass
  ↓
E4-A complete: 71/197, rejected; revert to E3-C
  ↓
F-Audit next
  ↓
E5/E6 paused until a train-only QueryPlan semantic gate passes
```

Checklist:

1. Confirm E2-A structured observations and trace completeness.
2. E3-B full run, summary, and E3-A/E0 comparison are complete.
3. Keep historical E3-C run2 diagnostic-only.
4. Historical E3-F v1/v3 summary, comparison, 32/32 attribution, and retrieval audit are complete; stop it.
5. Schema v4 passes structural preflight; Query Mining v2 does not.
6. Run Schema v4 component smoke/attribution and continue E3-D design.
7. E4-A is complete and rejected; revert the formal parent to E3-C.
8. Complete F-Audit.
9. Pause E5-A/E5-B/E6-A/E6-B until a new train-only QueryPlan semantic gate passes.
10. Select the architecture from paired migration, cost, and evidence.

## 13. Stop and Rollback Rules

| Stage | If it fails |
|---|---|
| E2-A | Stop new mechanisms and repair trace/observation |
| E3-B | Already rejected; conclusion only concerns static replacement |
| E3-C | Return to E0; do not carry metadata into E3-D/E4-A |
| E3-D | Do not run E3-E; keep E3-C if valid, otherwise E0 |
| E3-E | Reject few-shot removal; keep E3-D |
| E3-F | Do not infer which component failed; return to E3-C/E3-D |
| E4-A | Schema v3 is formally rejected; revert to E3-C, complete F-Audit, and do not enter Leaf or tune against eval gold |
| E5-A | Repair information equivalence |
| E5-B | Repair retrieval/slicing/context API; stop recursion |
| E6-B ≤ E6-A | Reject recursion gain; keep E5-B or E6-A |

Currently excluded: strict verified-final/independent FINAL synchronization; QueryPlan-free recursion, full-context Leaf, unlimited depth; separate Planner or full Router; full Offline cross-product; eval-derived repair rules; early trace-folding optimization.

## 14. Unified Per-Experiment Analysis Template

### 14.1 Configuration

| Field | Value |
|---|---|
| Experiment | |
| Parent | |
| Only variable | |
| Target error | |
| Fixed variables | |
| Model/parameters | |
| Data/hashes | |
| Prompt/artifact/config hashes | |
| Capability manifest | |
| Result/trace paths | |

### 14.2 Results

| Metric | Parent | New | Difference |
|---|---:|---:|---:|
| Correct/accuracy | | | |
| Aggregation/order | | | |
| Output contract | | | |
| Filtering | | | |
| Schema/Join | | | |
| Runtime/parse | | | |
| Recovered/regressed | | | |
| Stable E0 failures recovered | | | |
| Stable E0 successes regressed | | | |
| LLM/Root/Leaf/DB calls | | | |
| Total tokens/item | | | |
| Latency/item | | | |

### 14.3 Error Migration

- Target-class recovered IDs:
- Target-class regressed IDs:
- New non-target errors:
- Runtime noise:
- Representative traces:
- Automatic confidence and manual review:

### 14.3.1 Per-Item Offline/Retrieval Audit

Summarize from `attempts[].knowledge_selection`:

| Field | Content |
|---|---|
| Query Mining candidates | Intent cues, rank/score/support/shape, selected IDs, cutoff, exclusion reason |
| Schema table candidates | Lexical score, matched tokens, seed/path/FK-neighbor/fill source |
| Schema column candidates | Score, matches, PK/FK/lexical retention, truncation |
| Join evidence | Path expansion, delivered FK edges, cardinality, endpoint detail |
| Truncation | Budgets, omitted items, compact-index availability |
| SQL adherence | Selected tables/fields/joins used and mined-card adherence |

For every failure, answer whether necessary tables/fields entered the detailed fragment; if not, whether they remained in names-only context; where the correct candidate ranked and why it was truncated; and whether the cause was retrieval miss, wrong-pattern adherence, or correct retrieval followed by SQL reasoning failure.

### 14.4 Conclusion

- Is the hypothesis supported?
- Did target errors fall net?
- Do stable recoveries exceed stable regressions?
- Is cost acceptable?
- Is there data/gold/runtime confounding?
- Accept, repair/retest, or reject?
- Next single variable?

## 15. Current Next Step

> This section had been stuck describing "E3-C Schema smoke not yet done," out of sync with Section 12's actual progress. Updated to match Section 12 and `docs/analysis/README.md`.

E3-C Schema v4 has completed and been accepted (77/197 = 39.09%, current best parent config); E4-A (Root QueryPlan + Output Contract) then ran on top of it and was **rejected** (71/197 = 36.04%, recovered 3 / regressed 9 vs. E3-C), and the pipeline has rolled back to E3-C. Trajectory audit shows 82 of 126 failures had every execution pass QueryPlan adherence, and across all 197 questions there were zero wrong→correct execution recoveries — the bottleneck is that the QueryPlan itself is wrong, not that the model failed to follow it.

**The current next step is F-Audit** (Section 8.2): manually review filter-scope failures (`filter_scope_or_expression_mismatch`, **36** records across the two E0 runs after the 2026-08-07 classifier fix — originally reported as 67, see §4.1 in `docs/analysis/README.md`, the lowest-confidence category) and possible gold ambiguity, producing `docs/analysis/analysisDetail/filter_audit.md`. That file does not exist yet. After F-Audit, any renewed QueryPlan work (or other mechanism targeting aggregation/output/filter directly) must first pass a train-only semantic gate — it must not be tuned again against the fixed 197-question gold, which is exactly what E4-A did and why it failed.

Query Mining (E3-D/E3-F) can proceed in parallel with F-Audit but remains blocked on the five-fold cross-database gate: `train-mined-v2` removed conflicting Top-K complete cards and fallback, but no slot passes strict validation (`enabled_slot_count=0`), so the runtime abstains entirely. Run the integrated `e3-f-schema-v4 + train-mined-v2 + k=1 few-shot` E3-F only after `enabled_slot_count > 0` and a new stratified smoke passes. Until then, never interpret a Schema-only result as a complete Offline-system gain.

E5 (context store) / E6 (depth-1 Leaf) remain paused; only revisit once a new QueryPlan passes the train-only semantic gate.
