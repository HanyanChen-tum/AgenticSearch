# DB-RLM 30-Minute Presentation: Outline and Sample Script

Version: 2026-08-30
Purpose: approximately 24 minutes of presentation plus 6 minutes of Q&A  
Recommended main deck: 15 slides; backup: 10 slides

## Narrative Arc

```text
Motivation & Research Question
  → System Architecture
  → Headline Results Chain
  → Error Statistics
  → Simple Counterfactual Tests
  → Concrete Cases
  → Executable Grammar as a General Framework
```

The presentation answers only three questions:

1. With a fixed small model and no fine-tuning, how much can changes to the inference-time system improve performance?
2. Of RLM's three mechanisms, which ones actually account for the gains?
3. What patterns remain in the errors, and can those patterns become a validated, executable grammar?

## Reporting Conventions for the Numbers

Accuracy and resource metrics are combined below. Layers 0–4 use the common 491 corrected-dev questions and two runs per configuration; `reasoning tokens` and `total tokens` are per-item means, while `latency` is the per-item median. MB-A/MB-B use a fixed ten-question empty-result trigger set on historical core197 with three repeats per arm.

| Layer / control | Configuration | Effect | Change from previous layer / control | Reasoning tokens / item | Total tokens / item | Agent turns / item (LLM calls) | Median latency / item | Cost record |
|---|---|---:|---|---:|---:|---:|---:|---|
| 0 | B1 one-shot | 70.67% | — | Not recorded | Not recorded | 1.00 by design | 1.25s | Monetary cost not recorded |
| 1 | + executable tool-loop bundle | 84.62% | +13.95pp | 2,891* | 8,092* | 2.14 | 15.10s | Token-workload baseline 1.00×; monetary cost not recorded |
| 2 | + offline schema retrieval | 87.17% | +2.55pp | 3,307* | 9,768* | 2.32 | 14.35s | 1.21× vs. layer 1; monetary cost not recorded |
| 3 | + output post-processing | 87.58% | +0.41pp; within noise | 3,233* | 9,561* | 2.27 | 14.36s | 0.98× vs. layer 2; monetary cost not recorded |
| 4 | + depth-1 recursion | 88.19% | +0.61pp; within noise | 4,266* | 11,870* | 2.61 | 16.41s | **1.24×** vs. layer 3; monetary cost not recorded |
| MB-A† | extra retry | Wrong → correct: 1/25 = 4.0%; net 0 | Call-matched control | Not recorded | Not recorded | **+1 turn** per triggered instance | Not recorded | Monetary cost not recorded |
| MB-B† | retry + deterministic localization | Wrong → correct: 1/23 = 4.3%; net −1 | Indistinguishable from MB-A | Not recorded | Not recorded | **+1 turn** per triggered instance | Not recorded | Monetary cost not recorded |

`Reasoning steps` cannot be counted directly because the API does not expose the model's internal step-by-step process. The table therefore reports two observable proxies: `Agent turns` for external interaction rounds and `reasoning tokens` for internal reasoning volume within model calls. They are not interchangeable.

`*` A small number of calls lack usage records, so reasoning-token and total-token means are lower bounds. `†` MB-A/MB-B are confirmed to match only the number of extra calls. The project did not preserve a reproducible Azure deployment price or per-call monetary charge, so a dollar cost cannot be reconstructed reliably; the table uses the total-token ratio as a cost proxy. The current layer-3-to-layer-4 comparison is not matched-budget: recursion increases reasoning tokens by about 32%, total tokens by about 24%, calls by about 15%, and median latency by about 14% for a 0.61pp accuracy increment that remains within noise. Historical MB-A/MB-B did not log tokens, latency, or monetary cost, so **call-matched control** is the more accurate label.

Use 1.4pp as the conservative upper bound on noise for the main chain. The 70.5 → 83.9 → 86.5 → 86.9 → 87.2 figures in older documents use the metric before timeout-misclassification correction and should not be mixed with this table.

### Attribution boundaries

- The `+13.95pp` increment belongs to the **executable tool-loop bundle**: database tools, execution observations, and observation-driven revision enter together. The existing experiments do not further separate these into independent percentage-point effects.
- The `+2.55pp` figure is the incremental effect of offline schema retrieval in the main chain. A dedicated core197 ablation measured `+4.82pp`, but it uses a different population and denominator and is supporting evidence rather than a number to combine with the main chain.
- The `+0.41pp` and `+0.61pp` increments are both below the conservative 1.4pp noise bound. They are reported as **no stable measurable effect**, not as stable improvements.
- A historical core197 E6-A/E6-B experiment was repeated three times, but only the number of extra calls was matched; tokens, latency, and monetary cost were not recorded. It compares a pure retry with text feedback containing deterministic localization evidence rather than testing the current depth-1 DB leaf.

---

# 1. Motivation & Research Question

## Slide 1 — DB-RLM for Text-to-SQL (0:30)

### Slide content

- DB-RLM: Understanding Where RLM Mechanisms Pay Off in Text-to-SQL
- Frozen generator: `gpt-5.4-mini`
- No fine-tuning

### Sample script

> Large language models can generate SQL, but generating a valid query is not enough. The model must select the correct schema, understand the requested statistical grain, use database evidence, and match the benchmark's output conventions. In this project, I ask how far a frozen small model can go when we improve only its inference-time environment.

## Slide 2 — Motivation (1:10)

### Slide content

Four types of difficulty:

- Schema selection and join paths
- Semantic reasoning: grain, aggregation, denominator, and filters
- Execution grounding
- Output conventions and reference-answer format

### Sample script

> Text-to-SQL is a useful setting for studying agentic reasoning because errors occur at several different layers. A query can be syntactically valid but use the wrong table. It can execute successfully but count rows instead of entities. It can even compute the intended value and still lose because the benchmark expects a different type, column arrangement, or tie convention.

## Slide 3 — Research Questions and Constraints (1:20)

### Slide content

**RQ1.** How much can an inference-time DB-RLM system improve a frozen small model?  
**RQ2.** Which RLM mechanisms contribute the gain?  
**RQ3.** What limits further improvement: reasoning, conventions, or measurement?

Constraints:

- The same generator throughout
- No fine-tuning
- Gold answers used only for offline scoring and post-run diagnosis
- Changes to the environment, tools, precomputed knowledge, and ablatable post-processing are allowed

### Sample script

> The constraint is part of the research question. I do not replace the model and I do not fine-tune it. I only change what the model can do at inference time: which tools it can call, which observations it receives, how schema information is organized, and whether deterministic post-processing is applied.

### Transition

> To answer these questions, I first decomposed RLM into three mechanisms, then mapped each mechanism to a concrete system intervention and ablation. Where two mechanisms enter together, I report the identification boundary instead of assigning them separate gains.

---

# 2. System Architecture

## Slide 4 — DB-RLM as Three Mechanisms (1:50)

### Slide content

In this project, RLM is not synonymous with recursion. It consists of three measurable components:

| RLM component | Capability | Where this project starts from it |
|---|---|---|
| 1. Programmatic reasoning / exploration | Search, select, and compose external context through programs | train few-shot retrieval, offline schema retrieval, and the context-store experiment |
| 2. Executable environment | Execute key actions and retain observations in a persistent REPL | Python REPL, `db.execute`, `db.sample_values`, and execution traces |
| 3. Self-improvement and divide-and-conquer | Revise candidates from observations and delegate selected subproblems | observation-driven SQL revision plus an optional depth-one DB leaf |

### Suggested visual

```text
1 PROGRAMMATIC EXPLORATION — before the first model call
Question + Evidence → top-1 train few-shot + Offline Schema V4 → assembled prompt
                                                                    ↓
2 EXECUTABLE ENVIRONMENT       Root Agent ↔ Python REPL / DB Tools ↔ Observation
                                                                    ↻
3 SELF-IMPROVEMENT             revise candidate SQL; optionally call depth-1 DB Leaf
                                                                    ↓
                                                               FINAL SQL
                                                                    ↓
                         Deterministic post-processing (not an RLM mechanism)
```

### Sample script

> I do not use RLM as a synonym for recursion. I operationalize it as three mechanisms and start from each one separately. First, programmatic exploration controls how external knowledge is selected: before the first model call, the system retrieves one semantically similar training example and a question-specific Schema V4 fragment. Second, the executable environment gives the root agent a persistent Python REPL and live database tools, so candidate SQL produces real observations. Third, self-improvement uses those observations to revise the candidate, while the divide-and-conquer extension may delegate one unresolved subproblem to a depth-one database leaf. The final deterministic SQL rewrite is outside these three RLM mechanisms and is ablated separately.

## Slide 5 — Architecture as Experimental Design (1:20)

### Slide content

| Layer | Added capability | Identification scope |
|---|---|---|
| B1 | One-shot SQL generation | Floor |
| Clean E0 | Executable tool-loop bundle | Tools + observations + revision jointly |
| E3-C no-convention | Offline schema retrieval | Incremental layer contrast |
| E3-C convention | Output post-processing | Deterministic, separately ablatable |
| Recursive DB | Depth-1 recursion | Treatment includes the recursion-enabling prompt |

Two levels of evidence answer two different questions:

| Method | In plain language | What does it answer? |
|---|---|---|
| System-level ablation | Add one system capability at a time and compare the same questions before and after | **Which part improves the system overall?** |
| Item-level counterfactual test | Fix part of a real trace, regenerate from different positions, and see whether the answer changes | **Why did this item fail, and where should we intervene?** |

### Sample script

> The architecture is also the experimental design. For the first RLM mechanism, I compare naive pruning, deterministic offline retrieval, and the fuller context-store form. For the second, I compare one-shot generation with an executable REPL and database tools. For the third, observation-driven revision enters with that tool loop, and depth-one decomposition is then tested as a further layer. This is a mechanism-driven design, but not every mechanism is perfectly isolated: tools, observations and root revision enter together in layer one, so I report their 13.95-point effect as a joint bundle.

> The evidence has two levels. Ablation is global: after adding one capability, how much does accuracy change across the set? The item-level counterfactual test is local: for one failed question, regenerate from different points in the trace and see whether the error changes. The first asks what works; the second asks why an item failed. Neither replaces the other.

---

# 3. Headline Results Chain

## Slide 6 — Baseline 1 and the Negative Control (1:20)

### Slide content

- B1: complete schema, one SQL answer, no database access, no revision — 70.67%
- B2: keyword-overlap top-five table pruning — 67.82%
- B2 vs. B1: −2.85pp

### Sample script

> Baseline 1 receives the schema and the benchmark evidence, but it must answer once. Baseline 2 adds a naive keyword table selector. The selector hurts by 2.85 percentage points because it removes structural information that the model later needs. This gives us a useful negative control: schema reduction is not automatically beneficial.

## Slide 7 — Five-Layer Results Chain (2:30)

### Suggested visual

Use a step chart or waterfall chart:

```text
70.67 ── +13.95 ── 84.62 ── +2.55 ── 87.17 ── +0.41 ── 87.58 ── +0.61 ── 88.19
  B1    Tool-loop bundle  Schema       Post-processing      Recursion
```

### Sample script

> This is the central result. The complete system gains 17.5 percentage points over the one-shot baseline. However, the return is extremely uneven. The executable tool-loop bundle contributes 13.95 points, which is about eighty percent of the total gain. Offline schema retrieval adds another 2.55 points. Output post-processing adds 0.41, and depth-one recursion adds 0.61. The last two increments are below the conservative 1.4-point noise bound and are therefore reported as having no stable measurable effect.

> Therefore, the result is not that RLM works or fails as a single object. The result is that its mechanisms pay off very differently.

### Evidence sources (speaker notes only)

- Main chain and repeats: [`../analysis/week_2026-08-18/README.md`](../analysis/week_2026-08-18/README.md)
- Main-chain cost: [`../analysis/week_2026-08-18/reasoning_cost_2026-08-28.md`](../analysis/week_2026-08-18/reasoning_cost_2026-08-28.md)
- 30-second-timeout correction: [`../analysis/week_2026-08-18/sql_timeout_correction_2026-08-23.md`](../analysis/week_2026-08-18/sql_timeout_correction_2026-08-23.md)
- Raw results: `../../results/bird_b1_corrected_run{1,2}.json` and `../../results/chain_*_corrected_run{1,2}.json`

## Slide 8 — Is It Worth Thinking Longer or Using a Larger Model? (1:45)

### Slide content

**Same mini model: medium to high reasoning (one paired run)**

| | Accuracy | Median reasoning tokens | Mean total tokens / item | LLM calls / item | Median latency |
|---|---:|---:|---:|---:|---:|
| Medium | 85.9% | 864 | 8,163 | 2.49 | 9.1s |
| High | 87.1% | 2,262 | 9,552 | 2.27 | 14.7s |
| Change | **+1.2pp** | **2.6x** | **1.17x** | -0.22 | **+5.6s** |

**Same harness and configuration: mini to normal (preliminary model-scale control)**

| Reasoning | GPT-5.4 mini | GPT-5.4 normal | Difference |
|---|---:|---:|---:|
| High | 70.2% | 71.0% | **+0.8pp** |
| Low | 68.0% | 71.6% | **+3.6pp** |

> Note: the two tables use different experimental settings; 70% and 87% must not be directly compared.

### Sample script

> Accuracy is not free. Moving the same mini model from medium to high reasoning adds 1.2 points in the paired run, but median reasoning tokens rise from 864 to 2,262, or 2.6 times as much. Total tokens rise by about 17%, and median latency rises from 9.1 to 14.7 seconds. The number of calls falls slightly, which means the model is not taking more Agent turns; it is spending more computation inside each call.

> We cannot observe and count the model's real internal reasoning steps. I therefore report what we can measure: reasoning tokens, LLM calls, total tokens, and latency.

> With the larger GPT-5.4 normal model, the high-reasoning result is only 0.8 points above mini, which is within the current 1.4-point run-noise bound. At low reasoning, the gap is larger at 3.6 points. In plain language, model size matters more when reasoning compute is limited; giving mini more internal reasoning may narrow part of the gap. This is preliminary evidence, not proof that both models have exactly the same ceiling.

> The remaining failures therefore cannot all be blamed on the small model. Next, we hold the model fixed, vary the schema, loop, prompt, and output rules, and then inspect the failures directly.

### Evidence sources (speaker notes only)

- Reasoning effort and cost: [`../analysis/week_2026-08-18/five_layer_chain_results_2026-08-19.en.md`](../analysis/week_2026-08-18/five_layer_chain_results_2026-08-19.en.md); raw files `../../results/effort_medium_conv_rules_run1.json` and `../../results/chain_e3_c_conv_rules_corrected_run1.json`
- Model-scale figures come from the existing “Model Scale Comparison” slide; attach the raw result file, common denominator, and repeat count before the final deck

---

# 4. Understanding the Remaining Errors

## Slide 9 — What Were the 46 Errors? (1:20)

### Suggested visual

Use a horizontal bar chart, or show the table directly.

**Where did 46 come from?** Failures from two complete runs passed through predefined triage, retaining records with valid counterfactual curves. This is a failure-selected diagnostic set, not all failures or a random sample.

| Error type | Count | Share of 46 |
|---|---:|---:|
| Correct content, wrong type or output shape | **11** | **24%** |
| Wrong column or table | 6 | 13% |
| Wrong counting grain or missing DISTINCT | 6 | 13% |
| NULL / missing-value handling | 4 | 9% |
| Missing or extra filter | 4 | 9% |
| Wrong formula or denominator | 4 | 9% |
| Percentage missing ×100 | 3 | 7% |
| Semantic misunderstanding | 3 | 7% |
| Missing aggregation step | 2 | 4% |
| Other | 3 | 7% |

### Speaker script

> We have seen that the system reaches 88.19 percent accuracy. The next question is why the remaining cases fail. We collected failures from two complete runs, applied rules defined in advance, and retained 46 questions. They were selected for diagnosis and do not represent the natural error distribution of the full benchmark. [Pool construction](../analysis/week_2026-08-18/phase_a_turn_resampling_2026-08-24.md)

> We compared each question, database, model SQL, reference SQL, and execution result. The largest category is not complete failure: in 11 cases, the content is basically correct but the return type or shape is wrong. Six cases select the wrong table or column, six count the wrong object, and four mishandle NULL. [Root-cause table](../analysis/week_2026-08-18/flatzero_23_root_causes_2026-08-25.md)

> These are different problems, so one generic “think again” prompt is unlikely to fix them. But the table tells us what went wrong, not why. To investigate cause, we next actively change the reasoning trace.

## Slide 10 — How Did We Test an “Error Cause”? (1:25)

### Slide content

There are two dimensions: `k` is **where regeneration starts**, while `N` is **how many samples are drawn at that same starting point**.

```text
Original trace: Question ── Turn 1 / Obs. 1 ── Turn 2 / Obs. 2 ── Turn 3 / Obs. 3 ── …
                     ↑                    ↑                    ↑
                  k = 1                k = 2                k = 3
           fix no model response   fix real turn 1 first   fix real turns 1–2 first

For each k: retain exactly the same real prefix before k
                         ↓
                independently sample N = 10
                         ↓
       accuracy at k = correct FINALs / valid samples
```

| Setting | Concrete implementation |
|---|---|
| Questions | All 46 failures manually inspected on the previous slide; not a random full-dataset sample |
| `k`: regeneration point | `k=1` regenerates the first turn; `k=2` first fixes the real first turn, then regenerates; and so on. `K` depends on the number of turns in the trace, and is at most 4 in this experiment |
| `N`: samples per point | At every `k`, send `N=10` independent API requests with the same fixed prefix, model, and `reasoning_effort=high` |
| Harness-faithful continuation | If the model emits draft tool code, execute it and return the observation; allow up to two more continuations to obtain a clean FINAL |
| Accuracy at `k` | Correct FINALs divided by valid continuations at that `k`; a few points have only 4–9 valid samples |

### Speaker script

> We use turn-level counterfactual resampling. We keep the same question and history, but change where the model starts answering again. In the diagram, `k` is that starting point. At `k=1`, it restarts from the question. At `k=2`, we keep the original first turn and tool result, then continue. At `k=3`, we keep one more turn. The longest trace reaches `k=4`.

> At every starting point, we generate ten independent continuations—`N=10`. They receive the same question, schema, and prefix. Tool calls are really executed and returned to the model. We then calculate the correct-answer rate at each point.

> Only if fixing a turn changes later success do we treat that position as possible causal evidence. Reading a trace alone can make a suspicious sentence look like the cause; counterfactual testing requires it to change the result. This follows the intervention idea in Thought Anchors and addresses concerns about trace faithfulness. [Bogdan et al., 2025](https://arxiv.org/abs/2506.19143); [Turpin et al., 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract.html)

### Evidence source (speaker notes only)

- [Phase A turn-resampling experiment](../analysis/week_2026-08-18/phase_a_turn_resampling_2026-08-24.md)

## Slide 11 — What Happens When We Regenerate from Different Positions? (1:35)

### Slide content

```text
x-axis: regeneration point `k=1,2,…,K` moves forward, fixing more original turns
y-axis: correct FINALs / valid samples among N=10 resamples at each `k`
```

| Type | Count | What does the accuracy curve mean? | Meaning for system improvement |
|---|---:|---|---|
| Flat-zero (near zero throughout) | **23 / 46 (50%)** | Every checkpoint is below about 15%: even an early restart almost never succeeds | Same-model rethinking has limited value; new information, training, or rules are needed |
| Non-monotonic (moves up and down) | **14 / 46 (30%)** | The curve rises and falls or recovers later: there is no unique breakpoint | A reliable verifier is needed, not only more candidates |
| Locked-in (collapses after one step) | **5 / 46 (11%)** | Early accuracy is at least about 30%, then falls below 15% after one step and does not recover | Suitable for targeted A/B before commitment |
| High-band (consistently high) | **4 / 46 (9%)** | Every checkpoint is above about 50%: the recorded failure is a low-probability event | Try repeated sampling or equal-strength voting |

### Speaker script

> Each question produces an accuracy curve, and we see four patterns. Flat-zero contains 23 questions—half the set. The model is almost always wrong from every restart point, so repeated attempts have limited value. Fourteen questions are Non-monotonic: they move between correct and incorrect without one clear breakpoint, suggesting a need for a better selector.

> Only five are Locked-in. They can succeed early, but remain wrong after one original decision is fixed, making an intervention before that decision plausible. The last four are High-band: they are often correct from every point, so retry or voting makes more sense.

> The key result is that only five of 46 questions support one clear commitment point. A reasoning trace can suggest a cause, but cannot prove it. [Turn-resampling results](../analysis/week_2026-08-18/phase_a_turn_resampling_2026-08-24.md) The next example shows how a plausible explanation can reverse under intervention.

## Slide 12 — Example: Was Few-Shot Really the Cause? (1:15)

### Slide content

Case: `bird_637`

| Question | Evidence |
|---|---|
| Query | “What are the tags of Mark Meckes's posts that have no comments?” |
| Stored value | `posts.Tags = '<books>'`; comment count is zero |
| Model error | Splits one stored string into `books` |
| Initial hypothesis | The few-shot example misled the model |
| Test | Keep everything else fixed; compare with and without few-shot |
| Result | Keep: **10/13 correct (77%)**; remove: **2/13 correct (15%)** |

### Speaker script

> This question asks for the tags of Mark Meckes's posts with no comments. The stored string is `<books>`, but the model returns `books`. Because the retrieved few-shot uses a different tag structure, we initially suspected that it misled the model.

> We kept everything else fixed and removed only the few-shot. The result is the opposite of our intuition: with it, ten of thirteen valid answers are correct; without it, only two are correct. String-splitting errors rise from two to nine. [`bird_637` A/B](../analysis/week_2026-08-18/phase_a_turn_resampling_2026-08-24.md)

> Something that looks causal in a trace is therefore still only a hypothesis. We must change it and observe the result. We next move beyond one example and look for decisions that recur across questions.

## Slide 13 — Recurring Decision Patterns (0:50)

### Slide content

| Decision recurring across questions | How it appears in failed outputs |
|---|---|
| Return a number, text, one row, or many rows? | Type or output-shape mismatch |
| Which table and column contain the information? | Wrong source selection |
| Count entities or records? | Counting-grain or `DISTINCT` error |
| Are NULL, zero, or other special values valid? | Missing-value error |
| What are the numerator, denominator, and filters? | Formula or scope error |

### Speaker script

> Across different databases, the same five decisions recur: output shape, data source, counting unit, NULL handling, and formula or filter scope. [Root-cause table](../analysis/week_2026-08-18/flatzero_23_root_causes_2026-08-25.md)

> The errors therefore contain reusable structure. But we have found recurring decision patterns, not a complete state machine. Counterfactual resampling tells us when to intervene; these patterns tell us what to check. Combining them leads to the next experiment.

---

# 5. Discussion and Future Work

## Slide 14 — From Diagnosis to Full-Agent Validation (1:10)

### Slide content

**From diagnosis to intervention:** counterfactual resampling suggests that generic retry is not the main answer. For errors that may lock in after an early decision, we place an Answer Contract before SQL generation.

```text
Counterfactual diagnosis → pre-commitment Answer Contract → full-agent A/B/C
```

> **Layout placeholder: the values below are forecasts, not experimental results. Replace them after the complete 498-item runs and repeats.**

| Full-agent arm | Forecast accuracy | vs. A | Forecast reasoning cost |
|---|---:|---:|---:|
| A — No pre-read | ≈ **87.9%** | — | baseline |
| B — Generic pre-read | ≈ **88.1%** | ≈ +0.2pp | +5% to 8% |
| C — Structured Contract | ≈ **88.4%** | ≈ +0.5pp | +8% to 12% |

**Forecast interpretation:** `A ≈ B ≈ C`. The Contract may be directionally higher, but likely remains within the 1.4pp noise bound; use it selectively rather than by default.

**Existing supporting evidence**

| Preserve tied rows | Numeric rounding |
|---:|---:|
| **Net +5** | **Net +2 to +3** |

**Final principle:** forecasts do not enter the final claim; full-agent accuracy, rescue/damage, and cost decide whether the intervention stays.

### Speaker script

> The counterfactual analysis suggests that generic retry is not the main answer, so we move the intervention to before SQL generation. The Answer Contract asks the model to specify the output shape, data source, counting unit, NULL handling, and formula. The full experiment compares direct generation, a budget-matched generic analysis, and the structured Contract. The middle arm separates the effect of reading the question again from the effect of the Contract structure.

> These numbers are currently layout forecasts, not final results. If the completed experiment has this shape, the three accuracies are not stably different, while the Contract adds reasoning cost. It should therefore be selective rather than a default stage. As supporting evidence, two precise output rules already give net gains of five and two to three. [Bidirectional rule replay](../analysis/week_2026-08-18/rootcause_58_2026-08-27.md) The final decision must come from full-agent accuracy and cost.

## Slide 15 — Conclusion & Future Work (1:10)

### Slide content

**What did we learn?**

- Agent architecture matters: accuracy improved from **70.67% to 88.19%**.
- The executable tool loop contributed the largest gain: **+13.95 percentage points**.
- More reasoning is not always better: recursion used **32% more reasoning tokens**, but added only **0.61 percentage points**, within experimental noise.

**Broader outlook**

- Recurring reasoning patterns suggest that parts of reasoning may become **executable and verifiable knowledge**.
- Cross-database generalization and smaller-model execution are potential extensions of the framework, **not results established by this project**.

**Takeaway:** DB-RLM is our first test case toward a general framework for reusable, efficient, and verifiable reasoning.

### Speaker script

> Let me finish with three conclusions. First, without changing the model, agent architecture raises accuracy from 70.67 to 88.19 percent. Second, the executable tool loop contributes the largest gain—13.95 points. Querying the database, observing the result, and revising the answer matters more than simply extending internal reasoning. Third, recursion uses 32 percent more reasoning tokens but adds only 0.61 points, still within noise.

> These results also suggest a broader possibility: reasoning does not always have to remain a one-off, lengthy trace. If patterns such as source selection, counting units, and NULL handling can be validated repeatedly across tasks, they may become executable and auditable knowledge, with some stable steps potentially handled by smaller models. This project does not establish that cross-task generalization. DB-RLM provides a first executable and verifiable test case, and preliminary evidence for a more general reasoning framework.

---

# Suggested Backup Slides

## Backup 1 — Baseline Provenance

- Legacy B1 stored strict score: 52.40%
- Official set-comparison rescore: 55.20%
- Corrected dev498 reruns: 70.68% / 70.48%
- Do not present 55.20 → 70.67 as a method gain, because the question/evidence versions differ

## Backup 2 — Why 491, 496, and 498 Differ

- 491: questions jointly scoreable across all main-chain arms; used for causal layer-by-layer comparisons
- 496: configuration-specific scoreable denominator for some of the best arms; used to describe absolute performance
- 498: total number of unique questions in corrected dev

## Backup 3 — Clean E-Series Ledger

- E0: 34.26% on adversarial core197
- E1 strict final: rejected
- E3-A static patterns: directional only
- E3-B patterns replace few-shot: rejected
- E3-C schema: accepted
- E4-A QueryPlan: rejected
- E5-A context store: accurate but costly
- E6: no stable recursion effect

## Backup 4 — Reasoning-Effort Repeats

| Effort | Two-run mean | Same-set difference |
|---|---:|---:|
| minimal | 69.45% | 5.4pp |
| low | 82.60% | 2.2pp |
| medium | 84.80% | 2.2pp |
| high | 87.0% | 0.2pp |

## Backup 5 — Triggered-Subset Details for Recursion

- Run 1: 74 triggered questions
- Run 2: 64 triggered questions
- The conditional effects have opposite signs
- Overlap of recursion calls is unstable

## Backup 6 — Budget Audit and Call-Matched Control

Scope: historical core197; fixed ten-question empty-result trigger set; same model and parameters; one additional call per arm; three repeats.

| Treatment | Extra calls / trigger | Tokens | Latency | Monetary cost | Wrong → correct | Net |
|---|---:|---:|---:|---:|---:|---:|
| Deterministic rewrite | 0 | 0 | Offline only | 0 API cost | 1 | +1 |
| E6-A extra retry | +1 | Not recorded | Not recorded | Not recorded | 1/25 = 4.0% | 0 |
| E6-B retry + deterministic localization | +1 | Not recorded | Not recorded | Not recorded | 1/23 = 4.3% | −1 |

- E6-A and E6-B are statistically indistinguishable
- Their only recoveries occurred on different questions and in only one of three repeats
- E6-A and E6-B match additional call count, but exact token, latency, and monetary budgets cannot be verified
- It does **not** constitute a strict matched-budget test of the current depth-1 DB leaf

## Backup 7 — Causal Literature and Evidence Matrix

| Purpose | Literature | Use in this project |
|---|---|---|
| Potential outcomes / treatment definition | [Rubin, 2005](https://doi.org/10.1198/016214504000001880) | Define unit, treatment, outcome, and population first |
| NLP significance testing | [Dror et al., 2018](https://aclanthology.org/P18-1128/) | Same-item pairing, repeats, and a reported noise bound |
| Compute and run reporting | [Dodge et al., 2019](https://aclanthology.org/D19-1224/) | Report tokens, calls, and latency with performance |
| Counterfactual trace intervention | [Bogdan et al., 2025](https://arxiv.org/abs/2506.19143) | Fix a turn prefix and resample continuations |
| CoT faithfulness limitation | [Turpin et al., 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract.html) | Use traces to generate hypotheses, not prove causes |
| Recursive inference | [Zhang et al., 2025](https://arxiv.org/abs/2512.24601) | Report depth-1 effect, heterogeneity, and budget together |
| Execution-aware feedback | [ReEx-SQL, 2026](https://aclanthology.org/2026.acl-long.35/) | Validate corrections through executable outcomes |
| Reasoning distillation | [Hsieh et al., 2023](https://aclanthology.org/2023.findings-acl.507/) | Supports the future direction of transferring reasoning information from a large model to a smaller model |
| Model routing / cascade | [RouteLLM, 2024](https://arxiv.org/abs/2406.18665); [FrugalGPT, 2023](https://arxiv.org/abs/2305.05176) | Existing complementary approach; selects a model rather than compiling structural error rules |

## Backup 8 — Deterministic Rule Evaluation

| Rule | Rescue | Damage | Status |
|---|---:|---:|---|
| keep_ties | 7 / run | 2 / run | Positive offline evidence |
| printf_to_round | 2–3 / run | 0 | Positive offline evidence |

## Backup 9 — Limitations

- Sampling parameters were not fully fixed in historical runs
- Aggregate stability does not imply item-level stability
- core197 and Phase A are selected, failure-heavy populations
- The failure taxonomy lacks independent second-reviewer calibration
- Rule generalization has not been tested on a second split
- Recent online runs are affected by response-format drift
- The current depth-1 DB leaf lacks a full-set token- and cost-matched Extra-Root control; the historical core197 E6 experiment matches only the number of extra calls
- Automatic grammar mining and small-model offloading are untested; current evidence supports only two manually discovered, counterfactually validated executable rules

## Backup 10 — How Do We Distinguish Model, System, and Benchmark Limitations?

| What happens after an intervention? | More likely source |
|---|---|
| The architecture is fixed, and only normal consistently solves mini's failures | **Model-capability limitation** |
| The model is fixed, and changing only the schema, loop, or prompt solves the failure | **External system / architecture limitation** |
| Both models and several configurations fail, and the gold is ambiguous or wrong | **Benchmark / evaluation limitation** |
| Everything fails, but the gold has been verified | **Unresolved**; possibly a shared reasoning blind spot |

This is an **attribution guide for Q&A**, not an experimental result with measured category counts. A reasoning trace alone cannot establish the source. Use traces to propose hypotheses, then test them with A/B, resampling, or database execution. [Turpin et al., 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract.html)

# Key Answers for Q&A

## “Why not simply say recursion failed?”

> The measured increment is inside the noise band and the triggered-subset effect changes sign between runs. The evidence supports “no stable effect is measurable in this setting,” not a universal claim that recursion cannot work.

## “Did you control for recursion simply adding another model call?”

> Only at the call-count level. In the historical core197 experiment, E6-A and E6-B used the same trigger set, model and parameters, and both added one call per triggered instance. A pure retry recovered 1 of 25 wrong cases, or 4.0 percent; deterministic predicate-localization feedback recovered 1 of 23, or 4.3 percent. But token usage, latency and monetary cost were not logged, so I call this call-matched rather than strictly matched-budget. The current depth-one leaf itself uses about 24 percent more tokens, 15 percent more calls and 14 percent more median latency than its parent.

## “Is the +13.95pp caused by tools or by more reasoning?”

> The layer jointly introduces the executable environment and observation-driven revision, so the two cannot be fully separated. The reasoning-effort sweep suggests substitution between internal reasoning and external trial, but Baseline 1 does not record explicit reasoning effort. I therefore present this as a mechanistic clue rather than a complete causal decomposition.

## “Is post-processing cheating?”

> Any post-processing that changes predictions is part of the system under test and must be separately ablated. I distinguish shape normalization from semantic rewriting and report both rescue and damage on the full set.

## “Why call these effects causal rather than correlations?”

> Treatment and outcome are defined before a paired comparison on the same questions under the same corrected gold and evaluator. Rule- and item-level mechanisms additionally use replay, A/B, or executable counterfactuals. However, sampling was not fully pinned, repeats are limited, and recursion is not strictly budget matched, so I say “causally credible under this harness” rather than claim a universal causal law.

## “Can a reasoning trace prove the cause?”

> No. A trace only proposes a falsifiable hypothesis. The trace hypothesis for `bird_637` is rejected by targeted A/B, while the NULL claim for `bird_928` is supported by different executable outcomes from the original and counterfactual SQL. The causal evidence is the outcome under intervention, not the explanation text itself.

## “If you found the problems, why did you not keep fixing them?”

> We did continue testing, but we did not turn every failed item into a patch. After resampling all 46 items, 23 remained near zero from every regeneration point, and removing few-shot also overturned the initial explanation. Only patterns that recur across items and can be defined precisely become candidate rules, and each rule must show positive rescue minus damage on the full set. `keep_ties` and `printf_to_round` pass that test; ideas without positive net value do not enter the system.

## “Why not simply use a large/small model cascade?”

> It is a valid and well-studied engineering solution. Model routing asks which model should answer the whole question; our framework asks whether recurring, measurable structural errors can be compiled into deterministic rules. A validated rule adds no inference-time model call, and its rescue, damage, and scope are auditable. The two approaches can be combined, but this project has not tested small-model offloading, so it is not presented as a demonstrated benefit.

## “What is the strongest contribution?”

> The strongest completed result is still the mechanism decomposition: most of the measured gain comes from the executable tool-loop bundle and schema retrieval. The broader research significance comes from the error analysis: recurring output, counting, NULL, and filtering differences can be abstracted into candidate rules and validated by full-set counterfactual replay. The project has validated two manually discovered executable rules; automatic grammar mining remains future work.
