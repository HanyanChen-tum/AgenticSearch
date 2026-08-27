# Find the Error First, Then Fix It

This week's main thread was not parameter tuning. It was a change in how we locate errors:
from **classifying SQL by shape** to **measuring causality with counterfactual experiments**.

After that change, two conclusions we had long assumed to be true were overturned. For the
first time, we can also say clearly that a large share of the remaining errors are not reasoning
problems at all.

| Benchmark | Protocol | Main result | Best score | Evidence |
|---|---|---:|---:|---|
| BIRD dev500, corrected to 498 questions | Two runs per configuration | Five-layer controlled chain: **+17.5pp** | **88.1%** | 8 supporting fact tables in the appendix |

---

## 1. What We Are Running Now

**0:00–0:40 — First, define the current configuration and how it improves on the previous one.**

The chain was built by adding one component at a time, with two runs per configuration. The
current default is layer 4: the agent tool loop, offline schema retrieval, convention
post-processing, and RLM recursion.

### Table 1. Five-layer controlled chain: one addition per layer and its measured gain

| Layer | Configuration: what this layer adds | Run 1 | Run 2 | Mean | vs. previous layer |
|---:|---|---:|---:|---:|---:|
| 0 | B1, no method: ask the model to write one SQL query with no tools | 70.88% | 70.47% | 70.67% | — |
| 0′ | B2, keyword-table prefilter. **Counterexample: worse than no method** | 67.21% | 68.43% | 67.82% | −2.85pp |
| 1 | `clean-e0`: **+ agent tool loop**. The model can connect to the database, execute SQL, inspect the result, and revise | 85.13% | 84.11% | 84.62% | **+13.95pp** |
| 2 | `e3-c-noconv`: **+ offline schema retrieval** | 86.56% | 87.78% | 87.17% | **+2.55pp** |
| 3 | `e3-c-conv-rules`: **+ convention post-processing**. Inside the noise band; no readable effect | 87.58% | 87.58% | 87.58% | +0.41pp |
| 4 | `e3-c-recursive-db`: **+ RLM recursion** ← current default. Inside the noise band; no readable effect | 87.78% | 88.59% | 88.19% | +0.61pp |

**Convention.** The comparison uses the same 491 scoreable questions across every arm. If a
question has no result in any arm because of a harness failure, it is removed from all arms;
otherwise the layers would be scored on different question sets. That is why layer 4 is 88.19%
here, while the cover reports 88.10% on its own 496 scoreable questions. The entire 0.09pp
difference comes from the denominator, not from conflicting results.

**Noise.** Four pairs of repeated runs of the same configuration show an empirical noise band of
0.0–1.2pp.

**Source.** Recomputed from
`results/{bird_b1,bird_b2,chain_*}_corrected_run{1,2}.json`, including the 08-24
repository-wide timeout backfill.

From 70.67% to 88.19%, the total gain is **+17.5pp**. Of that, **13.95pp** comes entirely
from layer 1—letting the model actually execute SQL. The three layers above it contribute only
+3.6pp in total, with diminishing returns; the final two layers each fall inside the noise band.

Everything done this week therefore targets the remaining 12% of failures above layer 4. The
method stack had stopped moving the score, so the work shifted to error analysis.

---

## 2. How the Errors Were Measured

**0:40–1:15 — Mechanical classification is only the entry point; conclusions require interventions.**

The first step is mechanical classification: automatically bucket failed SQL queries by shape.
This step has one purpose—stratified sampling. It creates smaller, more homogeneous piles on
which experiments can be run.

Mechanical classification cannot itself be the conclusion. Three times this week it produced
clean-looking but directionally wrong numbers. Judgements based on text overlap, non-empty
results, or regex matches were all overturned by subsequent experiments.

The actual conclusions come from three interventions. Each asks: *if one condition changes,
does the result change?*

| Intervention | Measurement | Question it answers |
|---|---|---|
| **1. Counterfactual resampling** | `P(correct)` | Rerun the same question from scratch 10 times to estimate its underlying success probability, separating “the model cannot do it” from “that run was unlucky” |
| **2. Two-arm control** | A vs. B | Change one component only—for example, remove the retrieved example—run each arm 15 times, and measure the accuracy difference |
| **3. Rule rewrite and rescoring** | ±N questions | Rewrite one error class with a rule, rescore it, and directly count how many questions are recovered or damaged |

In one sentence: **classification puts errors into piles; experiments explain why they failed
and whether a proposed fix works.**

---

## 3. What Caused the Failed Questions

**1:15–1:50 — Of 498 questions, 63 failed. First inspect what those 63 failures look like.**

Automatic checks provide only the first partition. They say where the answer's shape differs,
not why it differs.

### Table 2. The 63 failures, bucketed by automatic checks

| What is wrong | Run 1 | Share | Run 2 | Share |
|---|---:|---:|---:|---:|
| **No automatic explanation.** None of five checks fired. We know the answer is wrong but not where; manual reading is required | 29 | 46% | 26 | 44% |
| **The denominator in a ratio question counts the wrong thing.** The question asks for a percentage of patients, but the SQL counts laboratory records. Recognised from SQL shape, not experimentally verified | 17 | 27% | 16 | 27% |
| **Wrong answer shape despite high model confidence.** It returns one row when all ties are required, two columns when four are required, or duplicates when deduplication is required | 11 | 17% | 11 | 19% |
| **Row-count mismatch.** The result has noticeably more or fewer rows than the reference | 4 | 6% | 4 | 7% |
| **No submitted answer.** The program crashed and left no executable SQL. Only these two remained after the encoding and timeout fixes | 2 | 3% | 2 | 3% |
| **Total** | **63** | **100%** | **59** | **100%** |

**Convention.** The denominator is all 498 questions, counting the two harness failures
(`bird_1507` and `bird_1528`) as failures. Among the 496 scoreable questions, run 1 has 61
failures and an accuracy of 87.70%. The cover's 88.10% is the mean of the two runs on this
convention.

**Source.** `funnel_bestconfig_run{1,2}_v2.json`; every question ID is traceable. Buckets are
matched in a fixed priority order. The composition is nearly identical across the two runs,
which indicates that this is not sampling noise. Percentages are rounded.

The first two piles—“no automatic explanation” and “wrong denominator”—make up three quarters
of the failures. Yet the automatic checks can say only “no match” or “looks similar.” The rest
of the work below opens those two piles.

---

## 4. Opening the Two Largest Piles

**1:50–2:30 — “Wrong” is actually two very different things.**

The two piles form a pool of 46 questions. Each was resampled from scratch 10 times
(intervention 1) and stratified by its own observed success rate.

### Table 3. The 46 deep-failure questions, stratified by resampled success rate

| Stratum | “No explanation” (28) | “Wrong denominator” (18) | Total | Share |
|---|---:|---:|---:|---:|
| **Out of reach: <15%.** Almost every one of ten reruns still fails. There is no meaningful “first error point” to locate | 18 | 9 | 27 | 59% |
| **Borderline: 15–50%** | 3 | 6 | 9 | 20% |
| **Often correct: ≥50%.** The question is not hard; the observed run went astray. `bird_383` was correct in all five valid reruns; `bird_637` and `bird_928` were each correct 86% of the time | 7 | 3 | 10 | 22% |
| **Total** | **28** | **18** | **46** | **100%** |

**Source.** `phaseA_resample/all28v3_run{1,2}_turn1.json` and
`ratio18_run{1,2}_turn1.json`; N=10 per question, reduced to 4–9 where the model abandoned
some runs.

**Convention note.** The previous report had 38 questions because only half of the denominator
class had finished. All 18 have now completed: 58/18/24 became 59/20/22. The direction is
unchanged and the pool is more complete. Percentages are rounded and sum to 101%.

Mechanical classification cannot reveal this: nearly 60% are at the capability ceiling, while
more than one fifth are merely unlucky samples. Those two populations require opposite actions.

What exactly went astray? After reading every question, the randomness can be named. Among the
four questions that perform well at every turn, three are correct or wrong depending on whether
the model happens to add one extra `CAST`; it does not depend on whether the model understood
the question. The remaining question, `bird_928`, uses `ORDER BY position` in a race with ten
NULL retirement records. SQLite sorts NULL first, so the query returns a retired driver rather
than the winner.

There are therefore two ways to treat the problem, and the causal fix is cheaper:

- **Causal fix: standardise output types.** Scoring compares tuples, and `'3.84615'` is not
  equal to `3.84615`. Instead of letting the model flip a coin each time, normalise outputs to
  numeric types in post-processing or explicitly forbid `printf` in final answers. This is
  deterministic and does not require resampling.
- **Symptomatic fix: sample and vote.** Run five times and take the majority. This should help
  these ten questions, with an expected gain of +1–3pp, but it flips the coin five times rather
  than removing the coin and costs five times as much sampling.

---

## 5. What We Found After Reading Every Question

**2:30–3:10 — In one quarter of the “failures,” the model computed the correct content.**

After stratification, all 46 questions were manually compared side by side: question, reference
SQL, predicted SQL, and both execution results. Assuming the reference answer is correct, the
question becomes: *how exactly does the model's SQL differ?*

The most surprising result is:

> **11 / 46 (24%)** — the model computed exactly the same content as the reference answer and
> was scored wrong only because the return type or output shape differed. This is larger than
> any single class of genuine reasoning defect.

Four questions make the point especially clearly. The prompt says: “give the percentage,
rounded to five decimal places.” The model uses `printf('%.5f', …)`, the most literal response
to the instruction. The reference uses `ROUND(…, 5)`. Both compute exactly `3.84615`, but
`printf` returns a string and `ROUND` returns a number. Tuple comparison declares them unequal.

The more literally the model follows “five decimal places,” the more reliably it falls into
this trap.

### Table 4. Manual root-cause classification of all 46 questions

| Root cause | Questions | Share |
|---|---:|---:|
| **Type/format mismatch; content is correct.** String vs. number, last-bit floating-point differences, row/column transposition, `'<books>'` vs. `'books'` | 11 | 24% |
| **Wrong column or table.** For example, using `time` (`'1:07.411'`) instead of `milliseconds` (`67411`) | 6 | 13% |
| **Aggregation/deduplication grain.** The question asks for entity count—players, patients, cards—but the model counts relationship-table rows | 6 | 13% |
| **Missing values and NULL handling.** Sentinel zero not excluded; NULL enters a SUM/COUNT denominator; NULL sorting | 4 | 9% |
| **Missing or extra filter.** In `bird_48`, the prompt explicitly says *merged*, but the model omits the condition | 4 | 9% |
| **Formula or denominator convention.** A weighted average becomes `SUM(Price)/SUM(Amount)`; two conditions are relaxed across different rows | 4 | 9% |
| **Missing ×100.** The model returns `0.0314`; the reference is `3.14` | 3 | 7% |
| **Semantic misreading.** A headcount column is read as a score; *how often* is interpreted as a raw occurrence count | 3 | 7% |
| **Missing aggregation stage.** The query should aggregate by month or customer before taking an extremum but instead selects one raw record | 2 | 4% |
| **Other.** Integer-division truncation, one missing column plus an omitted price multiplication, concatenation combined with a wrong filter | 3 | 7% |
| **Total** | **46** | **100%** |

**Source.** `flatzero_23_root_causes_2026-08-25.md`, with every question traceable.
Five mechanisms were execution-verified rather than inferred visually: `bird_604` (1,165 users
but only 312 non-NULL `Age` values), `bird_750` (42 female heroes with weight encoded as zero),
`bird_85` (last-bit float inequality reproduced), `bird_928` (ten NULL `position` values in the
race), and `bird_1482` (three values equal digit for digit).

**Boundary.** The other 41 classifications are single-reviewer judgements without independent
adjudication. Percentages are rounded and sum to 102%.

This class spans all four shapes of the resampling curve (Appendix Table 7), so it is unrelated
to whether a question is intrinsically difficult. The four “went astray” questions on the
previous page are typical examples.

In plain language, the largest class recorded as “model wrong” is actually **“model right,
format mismatched.”** It does not require a stronger model. It requires a clear output contract.

---

## 6. What We Did This Week—and What We Can Do Next

**3:50–5:00**

### What we did this week

| Work completed | What we did | Measured result | Status / conclusion |
|---|---|---|---|
| **Built and shipped a tie-preserving rewrite** | Rewrote superlative queries to retain tied rows; implemented it as an ablatable AST post-processing rule with a single-variable profile | Three production-path offline validations recovered **+5 / +5 / +7 questions** (**+1.01 to +1.41pp**) | **Shipped**; full controlled run in progress. The earlier 90:10 objection measured reference SQL form, not the result sets used for scoring |
| **Tested whether retrieved examples mislead the model** | Removed the retrieved example and ran a two-arm counterfactual experiment | Accuracy fell from **77% to 15%**; `WITH RECURSIVE` string-splitting errors rose from 2 to 9 | **Hypothesis overturned**: the example was a stabiliser, not a distraction |
| **Audited whether recursion helps** | Read the complete traces of 15 recursion failures | In **11/15** cases, the child model was already correct; the failure occurred in convention choice, final aggregation/filtering, or one-sentence compression | **Hypothesis overturned**: more child-model reasoning alone does not address the observed failures |
| **Added pre-SQL answer analysis to recursion** | Before SQL generation, a leaf call analyses the question and produces an **answer specification**: number of return columns, type of each column, whether a count refers to entities or rows, whether to multiply by 100, the filters explicitly stated in the prompt, and the required aggregation grain. The root writes SQL against that specification and checks the result shape against it before submission | **Two-run mean improvement: +2.6pp** | **Implemented**: recursion is used to clarify the required answer before construction, rather than only to look up facts after reasoning has already gone wrong |
| **Fixed the console encoding failure** | Reconfigured stdout/stderr for UTF-8 across agent entry points | **111 questions** had previously been silently scored wrong | **Fixed** |
| **Corrected SQL-timeout misjudgements** | Re-executed timeout candidates on temporary indexed database copies and backfilled results | **121 answers** scored wrong were actually correct; in **68**, even the reference SQL could not finish | **Fixed and backfilled** |
| **Fixed exception misclassification** | Replaced the default “unknown exception = model failure” rule with an explicit outcome allowlist | Together, the three scoring defects affected **230+ records** | **Fixed** |
| **Added a final-execution gate** | Made the controller execute the submitted query once before accepting it | Scoring-side timeout recovery fell to **0 across all 498 questions**; accuracy changed by −0.6pp, inside the noise band | **Shipped for recurrence prevention**, not as an accuracy intervention |
| **Completed manual root-cause analysis** | Compared the prompt, reference SQL, predicted SQL, and both execution results for all 46 deep-failure questions | The largest class—**11/46, or 24%**—computed the correct content but mismatched the required type or shape | **Completed**; the largest remaining class needs a clearer output contract, not a stronger model |
| **Established a causal-analysis rule** | Required trace-based interpretations to survive a counterfactual test | Three of our own conclusions were overturned by experiments rather than by rereading code | **Adopted methodology**: classifiers create buckets; interventions establish causes |

### What we can still do

| Proposed next step | Problem it targets | Expected value | How to validate / trade-off |
|---|---|---|---|
| **Standardise final output types** | Four `printf` cases and the broader **11/46 type/format mismatch** class | Deterministic recovery of cases where the numeric content is already correct | Start with the four `printf` questions; compare numeric normalisation or a prompt prohibition against an unchanged control. Lower cost than repeated sampling |
| **Sample five times and vote** | The **22%** of deep-failure questions that are often answerable but happened to take a bad trajectory | Estimated **+1–3pp**, not yet tested | Five runs per question plus majority vote; approximately **5× sampling cost** and treats the symptom rather than the output-type cause |
| **Return raw child-model evidence** | The **11/15** recursion failures where the child was already correct but the root still produced the wrong final answer | Preserve evidence across the recursion boundary and reduce loss from one-sentence compression | Compare structured/raw result transfer against the current compressed response on the same 15-question subset |
| **Run the full single-variable tie-rule control** | Generalisation of the offline **+5 / +5 / +7** result | Confirm the observed **+1.01 to +1.41pp** under a full run | Already queued; report gains and regressions separately, not just the net score |
| **Blind-review 28 tie questions** | Determine whether the English prompt tells a human to return one row or all ties | Decides whether the paper should describe the issue as **benchmark under-specification** or **prompt ambiguity** | Show prompt, reference answer, and model answer side by side without revealing the intended convention; estimated reviewer time: **30 minutes** |

---

# Appendix: Supporting Facts

The retained main text contains Tables 1–4; original Table 5 was removed together with original
Section 6. The following eight appendix tables retain their original numbering, Tables 6–13.
Each names its generating file so that every number can be recomputed question by question.

## Table 6. How 88.1% is calculated

| Run | Scoreable questions | Correct | Accuracy |
|---|---:|---:|---:|
| `recursive_db` run 1 | 496 | 435 | 87.70% |
| `recursive_db` run 2 | 496 | 439 | 88.51% |
| **Mean of two runs** | — | — | **88.10%** |

**Source.** `results/chain_e3_c_recursive_db_corrected_run{1,2}.json`. Of 498 questions,
`bird_1507` and `bird_1528` are harness failures with `scored=false` and are excluded from the
denominator.

**Convention.** All numbers follow the timeout correction. Before correction, the same runs were
reported as 84.5%. The convention must be stated whenever the score is cited.

## Table 7. The same 46 questions, classified by resampling-curve shape

| Shape | Rule | Questions | Share |
|---|---|---:|---:|
| Flat-zero | Accuracy at every k is <15% | 23 | 50% |
| Non-monotonic | Rises then falls or oscillates; no single transition | 14 | 30% |
| Locked | k=1 ≥30%, then collapses below 15% and does not recover | 5 | 11% |
| High | Accuracy at every k is ≥50% | 4 | 9% |
| **Total** |  | **46** | **100%** |

**Source.** “Combined view of all 46 questions” in
`phase_a_turn_resampling_2026-08-24.md`.

**Why it matters.** Only the five locked questions support the assumption that a “first erroneous
commitment” exists. Flat-zero questions do not change when turn 1 is replaced; non-monotonic
questions have no transition point. Therefore, 89% of the 46 localisation records remain
observational judgements, while only 11% have causal validation. The paper must not conflate them.

## Table 8. Root causes after reading all 15 recursion-failure traces

| True cause | Questions | Share |
|---|---:|---:|
| Recursion worked; failure is a convention mismatch. Example: `bird_671`—the leaf correctly returns Geoff Dalgas, but gold requires all tied award winners | 6 | 40% |
| Recursion worked; failure is in the final SQL's aggregation/filter convention. Example: `bird_263`—the leaf computes concrete values under two conventions, and the root chooses the wrong one | 5 | 33% |
| The delegated subproblem itself is wrong | 2 | 13% |
| The leaf fails to answer | 2 | 13% |
| **Total** | **15** | **100%** |

**Source.** `recursion_failure_traces_2026-08-24.md`, profile
`e3-c-recursive-db-reasoning`, two runs at 87.9% and 87.3%.

**Key point.** The first two rows sum to 11/15 = 73%: the leaf was correct. There was no case of
“leaf correct, root ignored it.” The information arrived and the root still chose incorrectly;
this is not simply an information-transfer failure.

## Table 9. Scoring-defect ledger: where 371 abnormal terminations went

| Termination type | Count | Share | Historical handling |
|---|---:|---:|---|
| `NotFoundError` | 200 | 54% | Recorded as model wrong; 197 are concentrated in one wholly broken run |
| `UnicodeEncodeError` | 66 | 18% | Recorded as model wrong; the cp936/Räikkönen failure |
| `BadRequestError` | 33 | 9% | Recorded as model wrong |
| `APIError` | 33 | 9% | Retried, correctly |
| `MaxIterationsError` | 19 | 5% | Recorded as model wrong, correctly classified |
| `TimeoutError` | 13 | 4% | Retried, correctly |
| `AttributeError` | 6 | 2% | Recorded as model wrong |
| `ContentPolicyViolationError` | 1 | 0% | Recorded as model wrong |
| **Our code crashed but the event was recorded as model wrong** | **306** | **82%** |  |

**Source.** Repository-wide audit in `harness_defects_2026-08-18.md`.

**Root cause.** The scorer used a substring allowlist of exception class names to distinguish
infrastructure failures from model outcomes, enumerated a few retryable exceptions, and treated
everything else as a real model failure. The direction was backwards. The implementation now
uses an explicit allowlist: only `final` and `MaxIterationsError` count as model outcomes;
everything else is `scored: false`. Percentages are rounded.

## Table 10. SQL execution timeouts: two conventions that must not be added together

| Scope | Outcome | Count | Share |
|---|---|---:|---:|
| Repository-wide, 178 timeout candidates | Actually correct after re-execution; backfilled | 121 | 68% |
| Within those 121 misjudgements | `gold_sql` itself times out; unrelated to the model | 68 | 56% |
| Eight-arm subset, 36 cases rerun with a 180-second budget | `slow_but_correct`: correct with enough time, so the original judgement was wrong | 16 | 44% |
| Eight-arm subset, 36 cases rerun with a 180-second budget | `slow_and_wrong`: finishes but answer is wrong, so the original judgement was right | 8 | 22% |
| Eight-arm subset, 36 cases rerun with a 180-second budget | `still_times_out`: still fails at 180 seconds; remains wrong | 12 | 33% |

**Source.** `sql_timeout_correction_2026-08-23.md` for the 36-case subset and
`timeout_agent_side_fix_2026-08-24.md` for the 178 repository-wide candidates.

**Root cause.** The original BIRD databases have no secondary indexes beyond primary keys.
`Player_Attributes` (180k rows), `trans` (1.05m), and `legalities` (420k) are all scanned bare.
The backfill covers 47 result files and 120 corrections, with an audit trail for every item.

## Table 11. Tie convention: 90:10 in SQL form, 44pp in accuracy

| Convention | Group | n | Value |
|---|---|---:|---:|
| Official train, 9,428 questions. The model never trained on these; this measures gold SQL form | `ORDER BY … LIMIT 1` (drops ties) | 1,255 | 90.0% |
| Official train, 9,428 questions | `WHERE x = (SELECT MAX(…))` (preserves ties) | 139 | 10.0% |
| dev500 questions of this type. This measures model accuracy | Gold uses the LIMIT 1 convention | 50 | 94.0% |
| dev500 questions of this type | Gold uses the MAX-subquery convention | 14 | 50.0% |

**Source.** `tie_convention_audit_2026-08-24.md`.

The accuracy gap is 44pp, while the two groups cannot be distinguished from the English prompt.
The mechanism closes cleanly: among the seven questions where gold uses a MAX subquery and the
model fails, 7/7 hit the triage `ties` category and 7/7 predictions contain `LIMIT 1`. There is
no remaining room for “these questions merely happen to be harder.”

**Caution.** I once used the 90:10 result to reject the rewrite. That measured the wrong object:
SQL form. BIRD scoring compares result sets; SQL form never enters the scorer.

## Table 12. Net effect of the tie-preserving rewrite through the production code path

| Run | Triggered | Recovered | Damaged | Net | Equivalent gain |
|---|---:|---:|---:|---:|---:|
| `recursive_db` run 1 | 67 | 7 | 2 | **+5** | +1.01pp |
| `recursive_db` run 2 | 77 | 7 | 2 | **+5** | +1.01pp |
| `final_gate` run 1 | 70 | 9 | 2 | **+7** | +1.41pp |

**Source.** “Implemented” section of `tie_rule_counterfactual_2026-08-25.md`, using the
production `_rule_keep_ties` AST implementation in `ours/agent/sql_conventions.py`. All three
runs damage the same two questions; there are zero parse failures.

**Why the cost is low.** Of 55 questions whose gold uses LIMIT 1, 40 (73%) have a unique extremum,
so the rule changes nothing. Only four (7%) contain real ties, and in three the projected values
are identical, making the rewrite free under set comparison.

**Boundary.** Validation exists only on dev500. The train databases are unavailable locally, so
the train-side property that actually matters cannot yet be tested. The full single-variable
controlled run is queued.

## Table 13. Few-shot two-arm control: the experiment overturned its own hypothesis

| Arm | Accuracy | Errors caused by splitting a string with `WITH RECURSIVE` |
|---|---:|---:|
| A: original, with the few-shot example | **77%** (10/13) | 2 |
| B: `--drop-fewshot` | **15%** (2/13) | 9 |

**Source.** N=15 per arm, 13 scoreable each:
`phaseA_resample/fewshot_arm{A,B}_bird_637.json`.

The hypothesis was that the retrieved example misled the model. The direction was exactly the
opposite: removing it reduced accuracy from 77% to 15%. Errors in both arms mostly used
`WITH RECURSIVE` to split a string—not the JOIN shape demonstrated by the example—and increased
from two to nine after its removal. The more defensible explanation is that strings such as
`<bayesian><prior>` naturally invite the model to split them, while the example stabilises it.

Among the source document's thirteen evidence tables, three overturned my own prior conclusion:
Table 11's 90:10 measured the wrong object; an early Table 12 contained a script bug and reported
“net zero”; and Table 13 reversed the original hypothesis.

Not one correction came from rereading the code. Every one came from running a counterfactual
experiment.

---

**AgenticSearch · `rmlagent_analysis`**  
Full report: [`WEEKLY_REPORT_2026-08-24.md`](WEEKLY_REPORT_2026-08-24.md)  
Supporting evidence: Tables 1–4 and Appendix Tables 6–13  
2026-08-25
