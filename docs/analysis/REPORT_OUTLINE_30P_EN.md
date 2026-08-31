# Outline for a 30-Page Report

## Proposed Title

**The Impact of Recursive Language Model Mechanisms on Text-to-SQL**

Optional subtitle:

**A Controlled Study of Database Exploration, Programmable Context, Planning, and Recursive Delegation on BIRD**

## Correct Research Focus

The report studies what happens when mechanisms inspired by Recursive Language Models (RLMs) are introduced into a Text-to-SQL system. It should compare direct generation, non-recursive database agents, RLM component variants, and actual Root–Leaf recursion under controlled conditions.

The report should answer:

1. How much does database-grounded iterative reasoning improve Text-to-SQL over direct generation?
2. Which RLM components—offline context, controlled execution, explicit planning, programmable context access, and recursion—improve accuracy, cost, or traceability?
3. Does actual recursive delegation outperform a non-recursive Root with the same model, tools, and additional-call budget?
4. Under what task conditions does recursion have or lack leverage?

The central conclusion should be framed as an empirical answer, not assumed in advance:

> Adding RLM-style mechanisms had mixed effects on Text-to-SQL. Database-grounded iteration and question-specific Offline Schema Context improved accuracy, and the controlled environment made reasoning auditable. However, programmable context externalization, explicit QueryPlan constraints, post-answer verification, and actual Root–Leaf recursion did not provide reliable additional gains in the tested BIRD setting. The recursion experiments indicate that delegation adds little when the parent and leaf have the same tools and information, the context is already small, and the remaining evaluation failures contain few clean, decomposable reasoning problems.

## Page Budget

The following budget targets approximately 30 pages of main text, excluding references and detailed appendices.

| Section | Pages |
|---|---:|
| Abstract and Summary | 1.0 |
| 1. Introduction | 2.0 |
| 2. Background and Related Work | 2.5 |
| 3. Recursive DB-RLM Design | 4.0 |
| 4. Experimental Setup | 3.0 |
| 5. From Direct Text-to-SQL to a Database Agent | 3.0 |
| 6. Impact of Individual RLM Components | 4.0 |
| 7. Impact of Actual Recursive Delegation | 4.0 |
| 8. Error, Trajectory, and Benchmark Analysis | 2.5 |
| 9. Cost, Scalability, and Interpretability | 1.5 |
| 10. Discussion and Limitations | 1.5 |
| 11. Conclusion | 1.0 |
| **Total** | **30.0** |

---

# Abstract and Summary — 1 page

Write a 250–350 word abstract containing:

- Problem: extending RLM mechanisms from unstructured search to structured database reasoning.
- Setting: BIRD mini-dev, 500 questions across 11 databases, official execution accuracy, one frozen Azure `gpt-5.4-mini` model.
- Comparison: direct schema-to-SQL, schema-filtered generation, non-recursive ReAct, RLM components, and actual Root–Leaf variants.
- Positive results:
  - direct baseline 55.20% → database-grounded DB-RLM harness 64.20%;
  - current reproducible system 67.40%;
  - Offline Schema Context contributes +3.20 pp on all 500 and +4.82 pp on the 197-question diagnostic subset.
- Recursive result: across five Root–Leaf iterations, invocation effectiveness remained net zero even after leaf database querying reached 94%.
- Cost result: context externalization approximately doubled tokens and quadrupled latency relative to the paired prompt condition without improving the small paired sample.
- Interpretation: RLM components help only when they add useful information or observable execution; recursion itself has no advantage when delegation creates no new information or independently useful subproblem.
- Scope: this is a task- and setup-specific result, not a universal rejection of RLM.

---

# 1. Introduction — 2 pages

## 1.1 Text-to-SQL challenges

- Large schemas, ambiguous natural language, join-path selection, value formats, aggregation grain, and output conventions.
- Limitations of one-pass schema-to-SQL generation.
- Why database interaction and decomposed reasoning appear promising.

## 1.2 Why study RLM for databases?

- Original RLM motivation: allow a model to inspect, search, partition, and recursively process an environment rather than consuming one fixed prompt.
- Database adaptation: schema and data form an executable, structured environment.
- Expected benefits:
  - improved accuracy through grounded exploration;
  - better scalability on large schemas;
  - lower context cost through selective access;
  - clearer evidence and traceability;
  - decomposition of complex multi-stage queries.

## 1.3 Research questions

- **RQ1:** How much does a non-recursive database agent improve over direct Text-to-SQL?
- **RQ2:** What is the independent contribution of each RLM mechanism?
- **RQ3:** Does Root–Leaf recursion outperform matched-budget non-recursive reasoning?
- **RQ4:** How do the mechanisms affect tokens, latency, tool use, and interpretability?
- **RQ5:** What benchmark or experimental factors limit the validity of the measured effects?

## 1.4 Contributions

1. A database adaptation of the RLM idea with a controlled SQLite environment, programmatic context, and Root–Leaf delegation.
2. A staged evaluation that isolates RLM mechanisms instead of treating “RLM” as one indivisible package.
3. A direct comparison between recursive delegation and non-recursive reasoning with the same model and tools.
4. Detailed trajectory evidence explaining why individual components helped or failed.
5. A benchmark audit that defines how much clean reasoning headroom the recursion experiments could actually measure.

**Figure 1:** Research overview: Direct Text-to-SQL → Non-recursive DB Agent → RLM components → Recursive DB-RLM.

---

# 2. Background and Related Work — 2.5 pages

## 2.1 Text-to-SQL systems

- Direct schema-conditioned generation.
- Schema linking and schema retrieval.
- In-context examples and query-pattern retrieval.
- Execution-guided correction and database agents.

## 2.2 Recursive Language Models

- RLM as a model interacting with an external environment through code.
- Context inspection, partitioning, sub-calls, and aggregation.
- Difference between an iterative ReAct loop and genuine recursion:
  - ReAct repeatedly lets one Root act and observe;
  - recursion creates a separate sub-call for a bounded subproblem and returns a result to the Root.

## 2.3 RLM-to-database mapping

| General RLM concept | DB-RLM realization |
|---|---|
| External environment | SQLite database plus stored context |
| Search/slice | schema and context retrieval |
| Code execution | `db.execute`, `db.sample_values` |
| Parent reasoning | Root Text-to-SQL agent |
| Recursive sub-call | depth-1 Leaf agent |
| Subproblem result | evidence, local answer, or SQL fragment |
| Aggregation | Root integrates leaf evidence into final SQL |

## 2.4 Relevant comparison points

- Execution-guided systems and SQRL: database inspection can help, but inspection policy may need learning rather than prompting.
- Thought Anchors: planning and early problem framing may dominate later self-checking.
- Schema retrieval work: reducing context only helps when necessary information remains available.

Keep this section focused on concepts used later; do not turn it into a general survey.

---

# 3. Recursive DB-RLM Design — 4 pages

## 3.1 System objective

Define Recursive DB-RLM as a Text-to-SQL agent that can:

1. inspect schema and stored values;
2. execute intermediate SQL;
3. maintain structured context and state;
4. form or revise a query plan;
5. delegate a bounded subproblem to a leaf;
6. integrate returned evidence into final SQL.

## 3.2 Common database environment

- Read-only SQLite connection.
- `db.execute(sql)` for exploratory and candidate SQL.
- `db.sample_values(table, column)` for stored-value grounding.
- 30-second timeout, output caps, error/empty/all-NULL observations.
- Same environment for the non-recursive and recursive agents.

## 3.3 Non-recursive Root loop

Describe the Root trajectory:

`question/context → model action → database execution → observation → revised action → FINAL SQL`

Clarify that this is the non-recursive comparison condition even though the implementation file is named `recursive_db_rlm.py`.

## 3.4 Three RLM capability groups

### Capability A: programmable context and code-based reasoning

- Offline artifacts: schema descriptions, PK/FK relations, join metadata, value formats, query patterns, few-shot examples.
- Direct prompt injection versus context-store access.
- Potential `search`, `slice`, and `compose` operations.

### Capability B: controlled execution environment

- Structured observations and explicit execution state.
- Capability gates for permitted tools.
- Run manifests, trace events, termination reasons, and usage records.
- Contribution: reproducibility and observability, not necessarily higher accuracy.

### Capability C: self-improvement and divide-and-conquer

- QueryPlan and Output Contract as pre-recursion formalization.
- Root selects one bounded subproblem.
- Leaf independently solves or verifies it.
- Root integrates evidence and remains responsible for final SQL.
- Matched-budget Root retry separates recursion from the value of one extra model call.

## 3.5 Offline Schema Context

- Deterministically retrieve question-relevant table/column descriptions.
- Include PK/FK graph, join cardinality, fan-out, null/value formats, and a names-only index for unselected tables.
- Explain why this is an RLM-supporting context mechanism but not recursion itself.

## 3.6 QueryPlan and context store

- QueryPlan fields: target entity, grain, required tables, joins, filters, aggregation, sorting, answer scope, and output columns.
- Context store: externalize the same Hint, few-shot, and offline metadata; the model reads fragments through tools.
- These stages test whether the prerequisites for useful recursion exist.

## 3.7 Recursive variants

- v1: text-only leaf.
- v2: leaf permitted to query the database.
- v3: database querying required in instruction.
- v4: schema supplied to the leaf.
- v5: schema plus an exact executable database-query example.

Explain that the variants progressively test whether failure comes from tool availability, missing schema, or insufficiently explicit prompting.

**Figure 2:** Recursive DB-RLM architecture showing Root, context environment, SQLite tools, Leaf call, returned evidence, and final SQL.

**Figure 3:** Capability decomposition and corresponding experiment families E2–E6.

---

# 4. Experimental Setup — 3 pages

## 4.1 Dataset

- Current benchmark: BIRD mini-dev, 500 entries/498 unique questions, 11 databases.
- Training pool: 9,428 train examples from 69 databases.
- Diagnostic core: 197 questions = 137 failed by both E0 runs + 60 canaries.
- Explain why full-500 and core-197 numbers must never be directly compared.
- Mention that early planning documents referenced Spider, but the completed reported experiments use BIRD.

## 4.2 Model and inference controls

- `azure/seminar-gpt-5.4-mini` for all controlled comparisons.
- `temperature=0`, `reasoning_effort=high`, `max_iterations=8`, train-only few-shot `k=1` unless ablated.
- Fixed evaluator and database timeout.

## 4.3 Baselines

| Method | Database access | Multiple turns | External context | Leaf recursion |
|---|:--:|:--:|:--:|:--:|
| Baseline 1: full-schema direct generation | No | No | No | No |
| Baseline 2: keyword-filtered schema | No | No | Retrieval once | No |
| Non-recursive DB Agent / clean E0 | Yes | Yes | Direct prompt | No |
| RLM component variants | Yes | Yes | Offline/context/plan varies | No |
| Recursive DB-RLM | Root/Leaf by variant | Yes | Varies | Yes |

## 4.4 Evaluation metrics

- Official BIRD execution accuracy using set comparison.
- Recovered and regressed question counts.
- Accuracy by simple/moderate/challenging and canary/both-wrong group.
- Root/Leaf/LLM/DB calls.
- Prompt, completion, reasoning, and total tokens.
- Latency.
- Recursion invocation rate, leaf database-query rate, and net gain on delegated questions.
- Context reads and delivered fragment coverage.
- Trajectory wrong-to-correct transitions.

## 4.5 Fairness and reproducibility

- Same model, tools, data, evaluator, and budget wherever the comparison permits.
- Capability gates prevent hidden access in control groups.
- Train-only artifact provenance and leakage audit.
- Run manifests and hashes.
- API/runner failures separated from semantic results.
- Trigger-set experiments repeated three times.

## 4.6 Leakage incident

- Disclose the historical dev-pool self-hit issue.
- Retract affected pre-fix results.
- Explain why legacy results are historical context only.

**Table 1:** Complete experimental protocol.

---

# 5. From Direct Text-to-SQL to a Database Agent — 3 pages

This section answers RQ1 before analyzing recursion.

## 5.1 Full-500 baseline results

| Configuration | Accuracy | Interpretation |
|---|---:|---|
| Baseline 2: keyword schema filter | 51.60% | Naive pruning loses required schema |
| Baseline 1: direct full schema | 55.20% | One-pass Text-to-SQL baseline |
| DB-RLM harness v4 | 64.20% | ReAct loop + live database tools; not proof of recursion |
| Current reproducible RLM-enhanced stack | 67.40% | Offline Schema Context + convention post-processing + train-audited rules |

## 5.2 Impact of database-grounded iteration

- Improvement from 55.20% to 64.20%: +9.0 pp.
- The Root can inspect stored values, run candidate SQL, and use observations.
- Explain why this is a major RLM-style environment benefit but remains non-recursive.

## 5.3 Why keyword schema pruning failed

- It reduces context without reliable recall or fallback.
- Contrast with Offline Schema Context, which provides detailed selected fragments plus a names-only global index.

## 5.4 Role of reasoning effort, few-shot, and ensembles

- High reasoning effort: major legacy gain but higher token/latency cost.
- Train few-shot `k=1`: retained in the clean baseline; higher k destabilized results.
- Similar-strength result-vote ensembles can add accuracy but measure repeated sampling, not RLM structure.
- Keep these as controls or context, not the main RLM contribution.

## 5.5 Key interpretation

Use careful terminology:

> The first large gain comes from turning direct Text-to-SQL into an environment-grounded database agent. It establishes the value of the RLM execution setting, but not the value of recursive delegation.

**Figure 4:** Accuracy progression on the full 500, visually marking non-recursive and recursive mechanisms.

---

# 6. Impact of Individual RLM Components — 4 pages

This section answers which prerequisites or components of RLM help before testing actual recursion.

## 6.1 Controlled execution and capability isolation (E2)

- Structured tool observations, explicit termination causes, continuation, trace recording, and capability gates.
- E2-B: 19/50, within E0's 19/50 and 20/50 range; 110 tool events, zero unauthorized access.
- Impact: accuracy-neutral but essential for a fair recursive/non-recursive comparison and interpretable traces.

## 6.2 Offline Schema Context (E3-C)

- Mechanism and retrieval design.
- Core-197: 77/197 = 39.09%, +4.82 pp over E0 mean.
- Full-500: +3.20 pp.
- Table recall: 98.4%.
- Token cost: +14.29% per question.
- Interpretation: supplying database facts that the model cannot infer is useful; the gain is accuracy, not efficiency.

## 6.3 Static patterns, few-shot replacement, and Query Mining (E3-A/B/D/F)

- E3-A static patterns: 73/197, +2.79 pp over E0 mean, weak evidence and +8.7% tokens.
- E3-B without few-shot: 72/197; no cost reduction; fixed patterns do not replace examples.
- Historical E3-F v1/v3: only 53 questions completed, schema retrieval degenerated into almost full-schema delivery, +40.34% tokens on the matched subset.
- Query Mining v2: 0/28 slots passed cross-database gates; best structural rule exceeded the model's own judgment by only 1.5 pp.
- Impact: generic structural patterns largely duplicate model knowledge and do not create a strong RLM context advantage.

## 6.4 Explicit QueryPlan and Output Contract (E4-A)

- Pre-SQL structured plan and observation-linked revisions.
- Result: 71/197 = 36.04%, six below E3-C; recovered 3, regressed 9; +6.67% tokens.
- 82 failures followed the plan structurally, showing that the plan itself was semantically wrong.
- Impact: formalizing reasoning makes it traceable but does not guarantee a correct decomposition.

## 6.5 Programmable context externalization (E5-A)

- Move identical Hint, few-shot, and Offline Schema Context into a read-only context store.
- Information equivalence: 197/197 exact.
- Access test: 59 reads on 11 questions, 0 questions without a read, 0 unauthorized actions.
- Accuracy on the paired 11-question smoke: unchanged at 5/11.
- Cost: +108.9% total tokens, +312.3% latency, +100% LLM calls.
- Impact: programmatic access works, but the context bottleneck is absent because the payload is already small.

## 6.6 Verification-oriented supporting experiments

Summarize briefly because they test self-improvement behavior relevant to recursion:

- E1 strict verified-final: no stable-failure recovery; doubled calls/tokens.
- Literal-verification reminder: 0 recovered, 4 regressed on N=44.
- JOIN-minimization v1/v2: net +1 then net 0 on N=26.
- E6 feedback retry: deterministic evidence did not outperform a matched-budget retry.

## 6.7 Component-level answer to RQ2

| RLM component | Accuracy impact | Cost impact | Main conclusion |
|---|---|---|---|
| Controlled environment | Neutral directly | Small/necessary | Enables safe and auditable execution |
| Offline Schema Context | Positive | Moderate increase | Adds missing database knowledge |
| Static/queried patterns | Weak or blocked | Increase | Mostly duplicates model knowledge |
| QueryPlan | Negative | Increase | Wrong plans are followed faithfully |
| Context store | Neutral in smoke | Large increase | No context-pressure benefit at this scale |
| Verification prompts | Null/negative | Increase | Do not repair semantic commitment |

**Table 2:** RLM component ablation summary.

---

# 7. Impact of Actual Recursive Delegation — 4 pages

This is the core section of the report and must not be merged with generic harness experiments.

## 7.1 What counts as recursion in this project?

- A separate leaf LLM call receives a bounded subproblem.
- The leaf performs independent reasoning and may access selected context/tools according to the variant.
- The leaf returns evidence or a local answer.
- The Root incorporates it into the final SQL.
- A ReAct step, QueryPlan, or tool call by the Root alone is not recursion.

State the historical audit result:

> Earlier “DB-RLM” runs contained the recursion primitive in the REPL, but no prompt told the model to use it; invocation was 0/197. Those runs test the database-agent harness, not recursive delegation.

## 7.2 Recursive variant progression

| Version | Leaf configuration | Leaf DB-query rate | Net gain on delegated questions |
|---|---|---:|---:|
| v1 | Text-only leaf | — | 0 |
| v2 | Leaf allowed to query DB | 0% | 0 |
| v3 | Prompt requires DB query | 0% | −2 |
| v4 | Leaf receives schema | 23% | 0 |
| v5 | Leaf receives schema and exact code example | 94% | 0 |

Explain the purpose of each transition and why v5 demonstrates end-to-end mechanism activation.

## 7.3 Did the leaf produce useful evidence?

- v5 leaves executed real queries and returned correct values such as `"Business"`, `"Closed"`, and `"2019-09-12"`.
- Therefore, the null result is not explained by a completely broken leaf implementation.
- Analyze whether the Root ignored, misused, or simply did not need the leaf evidence.

## 7.4 Matched-budget and trigger controls

- Compare recursive feedback/delegation against one additional Root call.
- Grain-invariant trigger failed pre-screening: fan-out was not a reliable error signal in BIRD gold SQL.
- Empty/error-result trigger entered the experiment.
- Extra Root retry and evidence-enriched retry remained statistically indistinguishable across three repetitions.
- Deterministic SQL rewriting gave a reproducible +1 on the same trigger set, while another model call did not.

## 7.5 Why recursion produced no net gain

Develop four evidence-based explanations:

1. **No information asymmetry:** Root and leaf have access to the same database, so delegation does not create new facts.
2. **No context bottleneck:** context utilization is about 4%; externalization already increased cost without benefit.
3. **No reliable routing signal:** the Root did not recognize which failures needed additional investigation, and wrong-to-correct recovery was zero in three full-run audits.
4. **Few clean decomposable targets:** only 10 of 115 audited failures on the adversarial subset were genuine model reasoning errors.

## 7.6 Accuracy, cost, and interpretability impact

- Accuracy: net zero on delegated questions across all five variants.
- Tool behavior: improved from no DB use to 94% DB use with exact instructions.
- Cost: extra leaf/model calls without reproducible gain.
- Interpretability: leaf traces expose local evidence and whether the mechanism activated, even when the final answer does not improve.

## 7.7 Answer to RQ3

Use a bounded conclusion:

> Under equal model capability and largely symmetric access to context and database tools, depth-1 recursive delegation did not outperform non-recursive reasoning. This does not show that recursion is generally ineffective; it shows that recursion needs either information asymmetry, specialized sub-agents, real context pressure, or independently verifiable subproblems to create value.

**Figure 5:** Root and Leaf information-flow diagram illustrating tool symmetry.

**Figure 6:** Leaf DB-query rate versus net delegated-question gain across v1–v5.

---

# 8. Error, Trajectory, and Benchmark Analysis — 2.5 pages

This section explains what the measured RLM effects mean and how much room the benchmark offered for recursion.

## 8.1 Trajectory analysis

- In three full runs, failed questions had exactly zero wrong-to-correct execution transitions.
- More than 99% of failed questions never produced a gold-matching intermediate execution.
- Correct and incorrect cases used similar numbers of database calls.
- Interpretation: failures were usually determined during problem interpretation or initial planning, before later verification or a leaf could rescue them.

## 8.2 Schema and join failures

- 93.5% of E3-C's residual Schema/Join failures already received the required tables and fields.
- Main issue: confusing semantically similar tables or columns, not retrieval recall.
- Relevance to RLM: more search or a leaf with identical context does not solve semantic disambiguation automatically.

## 8.3 Full audit of 115 failures

| Root cause | Count | Share |
|---|---:|---:|
| Defective gold answer | 44 | 38.3% |
| Unspecified output convention | 22 | 19.1% |
| Referential ambiguity | 18 | 15.7% |
| Hint–gold contradiction | 14 | 12.2% |
| Residual annotation convention | 7 | 6.1% |
| Genuine model reasoning error | 10 | 8.7% |

Explain that this is not the paper's main topic; it defines the evaluation ceiling and target density for the RLM experiments.

## 8.4 Causal checks

- Disambiguation: intended referent 1/7 → 6/7; complete correctness 0/7 → 2/7.
- Hint ablation: contradictory-Hint group 0/5 → 3/5; no control damage.
- These findings show why some apparently stable Text-to-SQL failures are not decomposable reasoning failures.

## 8.5 Annotation-alignment effects

- Deterministic convention post-processing improves official accuracy (+5 on core-197; +6 on full-500).
- Separate this from RLM capability improvement because it aligns outputs with BIRD conventions, including some defective gold behavior.

**Figure 7:** Failure-cause distribution for the 115 audited failures.

---

# 9. Cost, Scalability, and Interpretability — 1.5 pages

## 9.1 Cost

- High reasoning and iterative calls dominate token use.
- Offline Schema Context: +14.29% tokens per question for measurable accuracy gain.
- QueryPlan: +6.67% tokens with lower accuracy.
- Context store: +108.9% tokens and +312.3% latency in the paired smoke.
- Recursive leaves: additional calls with zero net delegated-question gain.

Discuss accuracy–cost trade-offs rather than accuracy alone.

## 9.2 Scalability

- Original hypothesis: selective/recursive exploration should help on large schemas.
- Actual BIRD context payload was only 726–2,572 tokens and total prompt around 5,171 tokens.
- Therefore, this experiment did not create the severe context-pressure condition under which RLM context partitioning is expected to help.
- Conclude “not demonstrated in this setting,” not “disproved in general.”

## 9.3 Interpretability and observability

- Controlled traces expose selected context, SQL executions, plan revisions, leaf invocation, evidence, and termination reason.
- QueryPlan and Leaf traces improved diagnosis even when they did not improve accuracy.
- Distinguish interpretability of recorded actions from correctness of hidden reasoning.

---

# 10. Discussion and Limitations — 1.5 pages

## 10.1 What the experiments say about RLM for Text-to-SQL

- The execution environment is valuable.
- Relevant offline database information is valuable.
- Programmatic context access has value only when context pressure exists.
- Explicit decomposition does not help if its plan is wrong.
- Recursive delegation needs a subproblem that adds information, specialization, verification, or parallelism beyond what the Root already has.

## 10.2 When recursion may help

- Much larger schemas or long external evidence.
- Specialized leaf tools or models.
- Different databases or sources assigned to different leaves.
- Independently executable subqueries with clear composition rules.
- Learned routing or calibrated uncertainty.
- Evaluation sets rich in genuine multi-stage reasoning errors.

## 10.3 Limitations

- One primary model and one benchmark.
- BIRD rather than the originally planned Spider evaluation.
- No domain-specific training or reinforcement learning.
- Depth-1 recursion and small targeted invocation sets.
- Actual context was not large enough to stress RLM memory advantages.
- Hidden reasoning tokens prevent chain-of-thought-level causal analysis.
- Some full-set gains are annotation alignment rather than semantic capability.
- Same-configuration rerun variance was about six questions on core-197.

---

# 11. Conclusion — 1 page

Organize the conclusion around the research questions:

1. Converting direct generation into a database-grounded agent substantially improved Text-to-SQL.
2. Among RLM components, Offline Schema Context improved accuracy and controlled execution improved observability; QueryPlan and context externalization did not improve the tested system.
3. Actual Root–Leaf recursion activated successfully but produced zero net gain on delegated questions.
4. The negative recursive result is explained by symmetric tools/information, low context pressure, weak routing signals, and few clean decomposable failures.
5. Future RLM-for-Text-to-SQL work should test recursion where sub-agents have specialized information or tools and where the benchmark contains verifiable multi-stage reasoning targets.

Suggested final sentence:

> In Text-to-SQL, recursion is not beneficial merely because a system can call another model; it becomes useful only when the recursive call creates a meaningful informational or computational advantage over the Root agent.

---

# Experiment-to-Section Coverage Map

| Experiment or result | Report section | Role in the RLM question |
|---|---|---|
| Baseline 1 direct schema-to-SQL | §5 | Direct generation baseline |
| Baseline 2 keyword schema filtering | §5 | Non-agent retrieval baseline |
| clean E0 / non-recursive DB ReAct | §5 | Primary non-recursive Root baseline |
| DB-RLM v4 legacy harness | §5 | Historical database-agent result, not recursion evidence |
| Reasoning effort and train few-shot | §5 | Model/context controls |
| E1 strict verified-final | §6 | Self-improvement prerequisite test |
| E2-A structured execution | §3, §6 | Controlled-environment capability |
| E2-B capability gate | §4, §6 | Fairness and isolation |
| E3-A static patterns | §6 | Offline context prototype |
| E3-B no-few-shot ablation | §6 | Pattern replacement test |
| E3-C Offline Schema Context | §6 | Positive programmable-context component |
| E3-D Query Mining v2 | §6 | Offline pattern-gate result |
| E3-E | Appendix | Not run because E3-D prerequisite failed |
| E3-F historical partial integration | §6 / Appendix | Diagnostic RLM-context integration |
| E4-A QueryPlan | §6 | Explicit problem-formalization prerequisite |
| Literal verification and JOIN minimization | §6 | Self-checking behavior tests |
| E5-A context store | §6, §9 | Programmable context test |
| E5-B search/slice/compose | §6 / Appendix | Not run because benefit precondition was absent |
| E6 matched-budget retry/feedback | §7 | Extra-compute control and routing evidence |
| Recursive Leaf v1–v5 | §7 | Actual recursion result |
| Grain and empty-result triggers | §7 | Recursive routing tests |
| ReAct trajectory efficacy | §8 | Explains timing of RLM effects |
| Schema/Join diagnosis | §8 | Distinguishes retrieval from reasoning |
| Full 115-failure audit | §8 | Defines clean recursion headroom |
| Disambiguation and Hint ablation | §8 | Causal benchmark diagnosis |
| Convention post-processing | §8 | Annotation alignment, not recursion gain |
| Rerun variance and classifier repair | §4 / Appendix | Validity and reproducibility |

---

# Recommended Figures and Tables

## Figures

1. Study progression from direct Text-to-SQL to actual recursive DB-RLM.
2. Recursive DB-RLM architecture.
3. Mapping of three RLM capabilities to E2–E6 experiments.
4. Full-500 accuracy progression.
5. Root–Leaf information symmetry.
6. Leaf DB-query rate and net gain across recursive v1–v5.
7. Audited failure composition and remaining clean recursion targets.

## Tables

1. Experimental protocol and datasets.
2. Baseline and headline results.
3. Individual RLM component ablations.
4. Recursive variants and matched-budget controls.
5. Accuracy, token, latency, and tool-use trade-offs.
6. Research questions and final empirical answers.

---

# Appendices

## Appendix A. Complete Run Registry

List profile, parent, intended difference, dataset, run ID, result path, trace path, accuracy, cost, recursion calls, and decision.

## Appendix B. Prompt and Capability Definitions

Include the clean Root prompt, QueryPlan schema, context-store tools, Leaf prompts v1–v5, capability gates, and matched-budget control prompt.

## Appendix C. Offline Artifacts

Document schema metadata fields, retrieval policy, table recall, static patterns, Query Mining slots, cross-database gates, and convention rules.

## Appendix D. Detailed Error and Trajectory Results

Include paired recovered/regressed IDs, wrong-to-correct transitions, full failure taxonomy, and representative Root–Leaf traces.

## Appendix E. Reproducibility and Threats to Validity

Include model configuration, evaluator, manifests, hashes, retry/timeout rules, leakage correction, classifier repair, and rerun variance.

---

# Primary Sources for Drafting

- Project motivation and current results: [`../../README.md`](../../README.md)
- Original Recursive DB-RLM goal: [`../../README_zh.md`](../../README_zh.md)
- Original project and comparison plan: [`../../Timeline_zh.md`](../../Timeline_zh.md)
- Unified experiment plan: [`../experiment-plan/README.md`](../experiment-plan/README.md)
- Experiment ledger and agent mechanism: [`README.md`](README.md)
- Current full-set summary: [`REPORT_2026-08-11_EN.md`](REPORT_2026-08-11_EN.md)
- Overall evidence synthesis: [`SYNTHESIS.md`](SYNTHESIS.md)
- Root-cause investigation: [`rootcause/README.md`](rootcause/README.md)
- Recursive trigger and matched-budget experiments: [`rootcause/e6_recursion_2026-08-09.md`](rootcause/e6_recursion_2026-08-09.md)

# Recommended Writing Order

1. §3 Recursive DB-RLM Design.
2. §4 Experimental Setup.
3. §5–§7 Results, ending with actual recursion.
4. §8–§9 analysis of why the measured effects occurred.
5. §10 limitations and conditions for useful recursion.
6. Introduction and conclusion.
7. Abstract last.
