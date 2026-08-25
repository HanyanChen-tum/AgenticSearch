# Weekly Report: From Fixing the Ruler to Finding the Real Bottleneck (2026-08-18 ~ 08-24)

In one sentence: **these seven days did two things — cleaned up the scoring convention
(accuracy 84.5% → 88.1%, entirely measurement bias, not a capability gain), and used four
mutually independent lines of evidence to pin down one and the same bottleneck: what remains
is almost all semantic and convention failure, and neither the method stack nor the reasoning
budget can touch it.**

> **Update, 08-25.** Four more things happened after 08-24 and are folded in below:
>
> 1. **Phase A resampling finished across 28 questions, and the measurement itself needed two
>    rounds of repair** (§4.1). The most valuable statistic is §4.3: **58% of deep-failure
>    questions are genuinely out of reach; 24% are just runs that went astray.** The latter points
>    at a new direction — **sample and vote** — worth roughly 1–3pp, now the new P1.
> 2. **The few-shot two-arm experiment ran and came out opposite to the hypothesis, which is now
>    retracted** (§4.4); its residual explanation lands back on format/convention as a fifth line
>    of evidence.
> 3. **The recommended default profile's full run finished** (§7): 87.50%, −0.6pp against the
>    88.10% mean on the same convention — inside the noise band; and **zero records needed
>    scoring-side timeout recovery**, so its recurrence-prevention purpose is met.
> 4. **The tie convention: I changed my mind, the rule should ship** (P1.5). I rejected it three
>    times and **all three grounds were wrong** (the last was a bug in my own rewriter). Fixed, it
>    measures **+6 / +6 / +5 across three runs, about +1.0–1.2pp** — larger than layers 3 and 4
>    combined.

---

## 0. The seven days at a glance

| Date | Output | Kind |
|---|---|---|
| 08-18/19 | Five-layer chain complete, eight arms × two runs each | Main result |
| 08-18 | Three harness defects diagnosed + 66 run configs audited field by field | Fixing the ruler |
| 08-20 | RLM corrected from "recursion" to three mechanisms; the word *harness* split into three layers | Conceptual correction |
| 08-20 | Four historical ablations re-run on the corrected dataset | Re-check |
| 08-21 | Broke open the 424 "other" failures; four reasoning-effort settings × two runs each | Deepening |
| 08-23 | Phase A first-pass localisation of 29 questions + funnel persisted; SQL timeout misjudgement diagnosed | New direction |
| 08-24 | 121 timeout misjudgements backfilled repo-wide; `final_execution_gate` controlled experiment | Fixing the ruler + new mechanism |
| 08-24 | 15 recursion failures traced question by question; tie-convention train/dev audit | Mechanism explanation |
| 08-24 | Phase A turn-level counterfactual resampling, first batch of 5 | New method |

---

## 1. Scoring convention: three corrections, none of them about model capability

Every number that moved this week moved because **the evaluation harness contaminated the
result it was only supposed to observe.**

| Defect | Impact | Handling |
|---|---|---|
| Console cp936 encoding crash | 111 questions silently scored wrong | Fixed (`shared/console.py`), all re-run |
| SQL execution 30-second timeout | Of 178 repo-wide candidates, **121 were actually correct** | Verified on temporary indexed copies and backfilled: 47 result files, 120 corrections |
| Exception misclassification | Harness crashes recorded as model errors | Inverted to a whitelist (only `MaxIterationsError` counts as a model outcome) |

**The root cause of the timeouts is not "the query is slow" — it is that the original BIRD
databases carry no secondary index at all beyond the primary keys.**
`Player_Attributes` (183,978 rows), `trans` (1,056,320), `legalities` (427,907) are all bare.
Of the 121, **68 are cases where `gold_sql` itself could not finish** — the old diagnostic script
only timed the predicted SQL, so a gold-side problem was recorded as "the model got it wrong."

Convention shift: arcwise full set 84.5% → **86.7%**; best arm `e3-c-recursive-db` → **88.10%**.
**Every published number must now state which convention it is on**, or we manufacture another
incomparability like the 84.5% → 86.7% one.

> **Recurrence prevention.** New `shared/timeout_recovery.py`: on any scoring-time timeout,
> automatically retry once against the same temporary indexed-copy method. Wired into all five
> `run_one()` implementations; execution timeout raised 30s → 180s.
>
> **We do not add indexes to the benchmark's original `.sqlite` files.** It is technically
> possible and would not invalidate any historical run (the repo-wide audit confirmed nothing
> hashes the `.sqlite` files; `dataset_sha256` covers the corrected JSON), but it would put every
> score on a benchmark we had altered.

---

## 2. Main result: of RLM's three mechanisms, only one is paying the bill

Five-layer controlled chain, two runs per layer, corrected convention:

| Layer | What is added | Accuracy | Delta |
|---|---|---:|---:|
| 0 | B1: single-shot generation, no database access | 70.5% | — |
| 1 | **+ agent tool loop (can actually query the DB, see results, revise)** | 83.9% | **+13.4** |
| 2 | + offline schema retrieval | 86.5% | +2.5 |
| 3 | + convention post-processing | 86.9% | +0.4 |
| 4 | + RLM depth-1 recursion | 87.2% | +0.3 |

Mapped onto RLM's three mechanisms (`README.md` §2.3):

| RLM mechanism | Carried by | Delta | Reading |
|---|---|---:|---|
| ② executable environment + ③ self-improvement | Layer 1 | **+13.4pp** | The main contribution, far outside the noise band |
| ① programmatic exploration (weakened form: offline retrieval) | Layer 2 | +2.5pp | Above noise; the full form (context store) measured separately as no gain — context utilisation is only 4% |
| ③ divide-and-conquer (depth-1 recursion) | Layer 4 | +0.3pp | Inside noise, not measurable |
| (not RLM) convention post-processing | Layer 3 | +0.4pp | Inside noise |

**The conclusion is not "RLM contributes nothing" — it is "the three mechanisms pay off extremely
unevenly, and almost all of it sits on one branch."** That is a stronger claim than the original:
it is a directional positive result, and each branch has independent evidence for why it is or
is not worth its cost. The narrowing in `config_inventory` §6 ("demonstrate the contribution of
**RLM recursion**") has been corrected.

**Noise band measured at 0.2~1.4pp.** The previously recorded "1~2pp" rested on two pairs that
do not hold up: one pair differed in `max_iterations`, the other had unequal crash counts.
Noise also falls monotonically with reasoning effort: same-question-set accuracy gap 5.4pp
(minimal) → 2.2pp (low) → 2.2pp (medium) → 0.2pp (high); per-question flip rate 15.9% → 9.9% →
7.9% → 5.5%. **Turning reasoning effort down does not only trade accuracy for cost — it trades
reproducibility for cost.**

### The substitution relationship holds (the foundation of track B)

Three independent estimates — `clean-e0 × minimal` 69.1%, B1 mean 70.4%, `e3-c-conv-rules ×
minimal` 69.45% — sit inside a band of under 1.5pp. **The agent tool loop and the model's
internal reasoning are to a large extent substitutes for one another.** Direct evidence:
as reasoning volume goes down, tool-call count goes up (2.27 → 3.34).

So what the +13.4pp at layer 1 buys **may not be "having tools" but "being able to try things."**

---

## 3. Four independent lines of evidence, one bottleneck

The most important convergence of the week: four methodologically unrelated lines arrive at the
same conclusion — semantics and convention, not execution.

### Evidence 1 — convention failures are immune to both the method layer and the reasoning budget

Up the method stack: 20 → 24 → 25 → 22 questions. Up the reasoning effort: 22 → 13 → 16 → 12.
**The absolute count barely moves.** What gets eliminated is entirely the other class,
"didn't figure it out" (132 → 95; 116 → 52).

The irony: the layer-3 post-processing was built specifically for convention errors, and it took
that class from 24 to 25 — not one removed.

### Evidence 2 — why recursion doesn't help: the leaf is usually right, and it doesn't matter

Registered `e3-c-recursive-db-reasoning` (single variable: `reasoning_capture` on), two runs at
87.9% / 87.3%; all 15 failures read question by question:

| Actual cause | Count |
|---|---:|
| Recursion worked; failure is **convention mismatch** | 6 |
| Recursion worked; failure is in the final SQL's **aggregation / filter convention** | 5 |
| The delegated sub-question was itself wrong | 2 |
| The leaf produced no answer | 2 |

**In 11 of 15 failures the leaf was correct. Not one case is "the leaf was right but the root
ignored it."** The sharpest example is `bird_263`: the leaf computed a concrete number for *each*
of the two candidate conventions (0.0348 and 0.0268) and handed both back; the root picked the
first; gold is 3.4823 (percentage × 100). **The information arrived intact and the root still
chose wrong — this is not an information-transfer problem.**

> Recursion helps the model get the facts straight, but the failure stopped being at the
> "facts aren't straight" layer a long time ago.

### Evidence 3 — once execution errors are cleaned up, 98% of what remains is semantic

Of the 61 failures the best profile has on the full 498: **exactly 1 has an execution error;
60 have `error=None`.**

New `final_execution_gate`: the controller executes the exact `FINAL(sql)` itself (once, no extra
model turn on the success path) and blocks only on a real failure, handing back the specific
reason. 24-question single-variable comparison:

| | Control | Treatment |
|---|---:|---:|
| Accuracy | 91.7% | 91.7% (**+0.0pp**) |
| Per-question flips | — | 0 |
| Trigger rate | — | 8.3% |
| Model actually rewrote the SQL after a block | — | 2 / 2 |
| LLM calls / tokens | — | 1.10× |

**The mechanism works as designed, but its ceiling was always ~1pp.** (For contrast: E1's
`verified_final`, which was rejected, fired on 90% of questions.) `bird_529` is the clean case:
the model read "foreign-key columns have no indexes, use a JOIN" and did exactly that. But the
control arm's version of that question would have been rescued at scoring time anyway.
`bird_416` is the counter-case: the gate successfully turned a timing-out query into one that
finishes, and the answer is still wrong — wrong in the choice of denominator in a ratio formula.

**This reproduces E1's conclusion by a completely different route**: the bottleneck is semantic
judgement, not execution verification.

> **A fact not previously recorded.** The model **never executes its own final query before
> submitting it** (all 24 control-arm `events` lists are empty). So this gate is not "one more
> verification on top of an existing one" — it is the only real execution in the agent loop.

Also quantified: `no_answer` 21 → **6** (down 71%), and those 6 cover only 4 distinct questions;
on a re-run the control arm produced answers for all of them too. **`no_answer` is a stochastic
phenomenon, not a fixed set of bad questions** — "fix those N" is not a coherent statement.

### Evidence 4 — the `ties` class should not be fixed: BIRD is inconsistent with itself

`ties` is the bulk of `confident_miss` (11~12 of 14). The shape is identical every time: the
question is phrased in the singular, the model writes `ORDER BY … LIMIT 1`, and gold returns all
tied rows. The natural move is to add a rule: "on a tie, return them all."

Per project rule, first check what **BIRD's gold actually does** on the **official train split**
(9,428 questions, never trained on), by reading the *form* of the gold SQL:

| Form | n | Share between the two decidable forms |
|---|---:|---:|
| `ORDER BY … LIMIT 1` (drops ties) | 1255 | **90.0%** |
| `WHERE x = (SELECT MAX(…))` (keeps ties) | 139 | **10.0%** |

On dev500, the same class of question split by which convention gold used:

| Gold's convention | n | Model accuracy |
|---|---:|---:|
| `LIMIT1` | 50 | **94.0%** |
| `MAX-subquery` | 14 | **50.0%** |

**A 44-point gap, between two groups that are indistinguishable in English.** Side by side from
train: *Which country produced the car with the lowest price?* → gold uses `LIMIT 1`;
*What is the order priority of the order with the highest total price?* → gold uses
`= (SELECT MAX(…))`.

Mechanism closed: of the 7 questions where gold used `MAX-subquery` and the model was wrong,
**7/7 are triage `ties` hits, and 7/7 of the predictions contain `LIMIT 1`** — no room left for a
"those questions just happen to be harder" explanation.

1. **The rule "on a tie, return them all" cannot be built.** It would conflict with roughly 90%
   of train gold — far worse than the boolean rule that was rejected back then (29% conflict).
   **This is the sixth time we have walked up to the same pit; this time it was caught before any
   code was written.**
2. **The model is not the broken link.** It picked BIRD's own 90% majority convention and then
   lost points on the 10% minority. This explains why "have the model double-check afterwards"
   came out net negative five times out of five (`verify_before_limit`: recovered 1, broke 9,
   net −8) — **fixing something that isn't in the model can only make things worse.**
3. **The correct output is a measurement, not a fix.** `ties` should be reported as
   **benchmark convention inconsistency.**

---

## 4. Phase A and turn-level resampling: the numbers, and what they mean

Phase A's first-pass localisation was a single LLM judgement — observational evidence. This week
judgement was replaced with **counterfactual resampling**: truncate at each turn boundary,
resample N=10, and watch how P(correct | first k turns fixed) moves (Thought Anchors' resampling
importance, at turn granularity).

### 4.1 The measurement itself was fixed twice; only the third version is trustworthy

| Version | What it did | Result |
|---|---|---|
| v1 | Scored anything a regex matched as `FINAL("…")` | **Systematic overestimate** — counted drafts the harness would discard as submissions |
| v2 | Copied the harness's `is_final and not has_code`; drafts invalidated | **Overcorrected** — **40% of 680 samples** came back as drafts and the median k=1 valid-sample count fell to **0**; the whole tier became unmeasurable |
| **v3** | Do not discard a draft: **actually execute its code, feed the observation back in the real format, and let the model continue** (reusing `ours/recursive_db_rlm.py`'s own REPL and formatting), up to 2 continuations | **Measurable** — median k=1 valid samples back to **6** |

What v2 exposed is itself a finding: **at k=1 (no context at all) the model almost never submits a
clean FINAL — it probes first and writes a draft answer alongside.** That is not specific to
`bird_637`; it is general behaviour. v1 scored those drafts, v2 threw them away; both are wrong,
and v3 does what the harness actually does.

**All three versions' files are kept** (`all28_*` / `all28v2_*` / `all28v3_*`) for per-question,
per-k comparison.

### 4.2 Shape distribution (v3, independently recomputed)

28 deep-failure questions from the "other" class, N=10 per question per k:

| Shape | Criterion | v1 (buggy) | **v3 (trustworthy)** |
|---|---|---:|---:|
| **Flat-zero** | every k below 15% | 17 (61%) | **15 (54%)** |
| **Non-monotonic** | rises then falls, or oscillates | 3 (11%) | **7 (25%)** |
| **Locked-in** | k=1 ≥30%, then collapses below 15% and stays | 5 (18%) | **3 (11%)** |
| **High-band** | every k at or above 50% | 3 (11%) | **3 (11%)** |

**v1's headline (flat-zero is the majority) survives, but some details were genuinely wrong**:
`bird_85` was recorded as locked-in at 37.5% in v1; v3 shows k=1 at **0/6** — that 37.5% was
entirely draft contamination. Conversely v1's three high-band questions (`bird_931`, `bird_928`,
`bird_1479`) survive v3 unchanged, so they are real.

### 4.3 The statistic that actually matters: half unreachable, a quarter just unlucky

Taking **k=1** (starting over from the question, the closest thing to "rerun this question") as the
per-question resampling accuracy, and folding in this week's ratio-formula batch:

| | "Other" class | Ratio-formula | **Total** |
|---|---:|---:|---:|
| Questions | 28 | 10 | **38** |
| **Out of reach** (k=1 <15%) | 18 (64%) | 4 (40%) | **22 (58%)** |
| Marginal (15~50%) | 3 (11%) | 4 (40%) | **7 (18%)** |
| **Usually gets it right** (≥50%) | 7 (25%) | 2 (20%) | **9 (24%)** |

**This is the most valuable result in this section**: the questions we have been lumping together
as "deep failures" are two completely different things.

1. **58% are genuinely out of reach** — resampled ten times from scratch, still wrong almost
   every time. These have **no "first wrong commitment" to find**: the localisation script's
   premise simply does not hold for them, and an intervention arm cannot rescue them.
2. **24% are runs that happened to go astray** — the model had a 50%–100% chance of getting them
   right:

   | Question | k=1 accuracy |
   |---|---:|
   | `bird_383` | 5/5 (100%) |
   | `bird_637`, `bird_928` | 86% |
   | `bird_1531` (ratio-formula) | 80% |
   | `bird_1479`, `bird_931`, `bird_1080` | 75% |
   | `bird_1480` | 71% |
   | `bird_1243` (ratio-formula) | 50% |

**That 24% points at a direction nobody has considered here**: it needs no new method layer and no
extra reasoning budget — just **sampling more than once and voting** (self-consistency /
best-of-n). Extrapolated over the 61 failures the best profile has on the full set, the magnitude
is roughly 1–3pp — **comparable to layers 3 and 4 combined, at the cost of repeated sampling.**
This has not been tested; it is a **new testable hypothesis** this report proposes, not a result.

### 4.4 ⚠️ The few-shot hypothesis was overturned by its own experiment

The previous version of this report proposed, from `bird_637`'s trace, that the causal source of
the failure was the retrieved few-shot example (a "tags live in their own table, one row each"
template), and designed a two-arm test on that basis. **The experiment ran, and the result is the
opposite of the hypothesis** (`--drop-fewshot`, N=15 each):

| | Accuracy | Of the errors, `WITH RECURSIVE` string-splitting |
|---|---:|---:|
| Arm A (few-shot present, as recorded) | **10/13 (77%)** | 2 |
| Arm B (few-shot removed) | **2/13 (15%)** | **9** |

Deleting the example does not help — it drops the question from 77% to 15%. And the errors in both
arms are almost all `WITH RECURSIVE` splitting, **not** the JOIN shape that example demonstrates;
removing it makes that error class go *up*, from 2 to 9. The direction does not fit.

**The better-supported explanation**: seeing an angle-bracket delimited string like
`<bayesian><prior><elicitation>` is itself what triggers the urge to split, largely independent of
which example was retrieved. If that example did anything, it supplied a simple "just select the
column" pattern and acted as a **stabiliser**, not a distractor.

**Two conclusions**:

1. **The few-shot retriever is not the causal source of this failure class; do not invest there.**
2. The residual explanation — a delimiter-string format triggering the splitting urge — is
   **once again a format/convention problem**, pointing the same way as the four lines in §3.
   **That makes five.**

**Methodological value**: a causal story derived from reading a trace once has to survive a
counterfactual test before it can be believed. This is the causal-inference version of "mechanical
adjudication falsified" — except this time what got overturned was a hypothesis written in the
previous version of this very report.

### 4.5 Boundaries

1. **v3's k=1 is not "the agent's real accuracy"**: it starts from the question and allows at most
   2 continuations, where the real agent gets up to 8 turns. It approximates "what would happen if
   this question were rerun", which is not the same measurement.
2. **N=10 (4~9 on questions where it gave up) — a small sample.** Questions sitting near the
   15%/50% classification thresholds (`bird_383`, `bird_85`) swinging between versions is expected;
   what is stable is the **direction**: most are out of reach, a minority are usually right.
3. **The ratio-formula batch covers only turn 1 of 10 questions** (of 18); run2 not done. Its share
   is preliminary.
4. **The Phase A pool has grown from 29 to 46** (`phase_a_source_map_v2_46.json`); the 28+10 here
   are the part with completed resampling, not the whole pool.

## 5. Methodology: mechanical shortcuts were overturned three times this week

That makes five, six and seven.

| Who, this time | How it went wrong | Changed to |
|---|---|---|
| `verify_located_claims.py` | "`check_sql` returned something non-empty ⇒ confirmed" produced 28/29 (97%) — **fake**. Only 8~9 were rigorously verified, and one (`bird_637`) auto-labelled *confirmed* was in fact a **refutation** | Auto-classification is used only to screen hard failures; its labels are not results |
| `analyze_recursion_traces.py` v1 | Judged `leaf_unused` by **token overlap** between the leaf answer and the final SQL; five of six run1 cases mislabelled — the leaf answered "Geoff Dalgas", the SQL reads `SELECT u.DisplayName … LIMIT 1`, zero shared tokens, obviously used | Emits reproducible facts only; the judgement is left to a person |
| `resample_turn.py`'s scoring | Scored anything a regex matched as `FINAL("…")`, **but the real harness accepts on `is_final(response) and not has_code`** (`ours/recursive_db_rlm.py:539`) — when a turn carries both tool code and a `FINAL()`, that FINAL is discarded and the code runs instead. The script counted those **discarded drafts** as submissions, **systematically inflating k=1**; `bird_637`'s turn 1 is exactly that shape | Added `would_be_discarded()`; such samples get their own reason code and are excluded from the accuracy |

**Common lesson: surface overlap, a non-empty return, a regex match — none of them substitutes
for what the system under test would actually do.** The first two were adjudication scripts
standing in for a person's judgement; the third was a *measurement* script that failed to
replicate the harness's acceptance rule. Same consequence either way: a clean-looking number
pointing the wrong way. The triage constraint ("reproducible facts only, no conclusions")
stands, and measurement scripts get one more: **wherever a script decides whether something
counts as a submission, that decision must come from the same source as the harness.**

Separately, coverage of reproducible checks caps out around 30% (165/549). Within "other",
28% (30/107) has been localised to a **ratio-formula numerator/denominator** sub-pattern, but
**mechanising the judgement is not worth it** — the fix requires understanding the question, the
same class of risk as the retired `count_no_distinct` post-processing rule. **The next step can
only be manual adjudication.**

---

## 6. Code assets added this week

| File | Purpose |
|---|---|
| `shared/console.py` | Encoding fix; **every new agent entry point must call `force_utf8_console()`** |
| `shared/timeout_recovery.py` | Scoring-time timeout retry on a temporary indexed copy; wired into all 5 `run_one()` |
| `scripts/audit_run_configs.py` | Field-by-field run config comparison; **`cfg_sha` is unreliable in both directions — use this before comparing** |
| `scripts/triage_failure_causes.py` | Failure triage; added `column_permutation` / `concat_columns` |
| `scripts/build_phase_a_funnel.py` | Persists the 498 → 29 per-question funnel |
| `scripts/analyze_recursion_traces.py` | root/leaf reasoning split + fact output |
| `scripts/resample_turn.py` | Turn-level counterfactual resampling |
| `scripts/audit_tie_convention.py` | train/dev tie-convention audit |
| `scripts/compare_final_gate.py` | Two-arm gate comparison |
| `ours/agent/config.py` | New `final_execution_gate` field; profiles `e3-c-recursive-db-final-gate` (**recommended default for new runs**), `e3-c-conv-rules-final-gate`, `e3-c-recursive-db-reasoning` |
| `tests/test_timeout_recovery.py`, `tests/test_final_execution_gate.py` | 8 new tests |

---

## 7. The current best configuration, in detail

**Highest measured arm: `e3-c-recursive-db`** — two runs on the corrected dev500 at
**87.70% / 88.51%, mean 88.10%** (496 of 498 scorable).
**Recommended default for new runs: `e3-c-recursive-db-final-gate`** — the same configuration
plus the FINAL execution gate (single variable), there for recurrence prevention rather than
accuracy (see §3, Evidence 3).

### Agent configuration (from `trace/chain_e3_c_recursive_db_corrected_run1/run_manifest.json`)

| Field | Value | What it means |
|---|---|---|
| `prompt_profile` | `conventions-recursive-v1` | prompt_id `conventions-plus-recursive-leaf-v1`, source train-mined-conventions, **contains no examples**, contains task-specific SQL rules, sha `9b605cf1…` |
| `capability_gate` | `true` | Generic `recursive_llm` off, context store unreadable — **only depth-1 recursion is exposed** |
| `allowed_db_methods` | `("execute", "sample_values")` | The model has exactly these two database actions |
| `few_shot_mode` | `train-retrieval`, **k = 1** | `TrainFewShotRetriever`, pool `data/train_pool.json` (9,428 examples, sha `80c03262…`), embedding `all-MiniLM-L6-v2`, **source_split = bird-train** |
| `schema_context_mode` | `offline-retrieval` | The full schema is no longer stuffed into the prompt |
| `offline_metadata_mode` | `e3-f-schema-v4` | `data/processed/e3_f_schema_v4.json`, artifact sha `ed713b06…` |
| `sql_convention_mode` | `train-conventions-v1` | **Only one of three rules is on** — see below |
| `recursion_mode` | `leaf-db-v1` | The depth-1 leaf **shares the parent's gated database handle** (v1's text-only leaf knew strictly less and moved accuracy 0.00pp) |
| `verified_final` | `false` | Rejected in E1 (42.14% → 40.00%) |
| `final_execution_gate` | `false` (best arm) / `true` (recommended default) | Mutually exclusive with `verified_final` in `__post_init__` |
| `use_db_hints` / `context_mode` / `planner_mode` / `reasoning_mode` / `query_pattern_mode` / `reasoning_capture` / `literal_verification_nudge` | `false` / `direct` / `none` / `none` / `none` / `none` / `false` | Every other capability off |
| `agent_config_sha256` | `656e7cb19bf177b352b6b1becb04e857600783c04abb2125c2d883f5ba23cbb5` | **Diff field by field with `audit_run_configs.py` before comparing — do not trust this sha alone** |

### The three convention rules: only one is enabled

| Rule | Train support | Status | Reason for disabling |
|---|---:|---|---|
| `no_select_concat` (split `a \|\| b` into separate projections) | **0.9999** (9427/9428) | **enabled** | — |
| `count_no_distinct` (strip DISTINCT from COUNT when the query joins) | 0.891 | disabled | Changes what COUNT counts (entities → rows) |
| `superlative_order_limit` (rewrite `= (SELECT MAX…)` to `ORDER BY … LIMIT 1`) | **0.9034** | disabled | Changes the computation, and can drop WHERE conditions |

**Note the third rule.** Its train support of 0.9034 matches the **90.0%** measured independently
by this week's tie-convention audit — the same 90:10 distribution quantified by two different
routes. It is also why the rule in the *opposite* direction ("on a tie, return them all") cannot
be built: that 90% is exactly what it would have to fight.

### Runtime parameters

| Item | Value |
|---|---|
| Model | `azure/seminar-gpt-5.4-mini`, `api_version 2024-12-01-preview` |
| `max_iterations` | **8** (this field is **not** part of `agent_config_sha256` — the historical source of "fake repeats") |
| `reasoning_effort` | `high` |
| temperature | requested 0.0, **not actually sent** (`drop_params` active, `temperature_sent: false`) — sampling is not pinned |
| Dataset | `data/processed/bird_dev_500_corrected_full.json`, sha `59dba552…`, 498 questions |
| Databases | `data/raw/bird/minidev/MINIDEV/dev_databases` |
| Scoring timeout | 30s in that run; **now 180s + `timeout_recovery`** (see §1) |

### Reproduction command

```bash
python scripts/run_bird_train_fewshot.py \
  --agent-profile e3-c-recursive-db-final-gate \
  --dataset data/processed/bird_dev_500_corrected_full.json \
  --model azure/seminar-gpt-5.4-mini \
  --max-iterations 8 --k 1 --reasoning-effort high \
  --output results/<name>.json
```

### Full run of the recommended default profile: finished

`e3-c-recursive-db-final-gate` completed its first full pass over the corrected dev500 overnight
on 08-24 (`agent_config_sha256` `316263c67080…`, `max_iterations=8` / `k=1` / `effort=high` /
scoring timeout 180s):

| | final-gate | control `e3-c-recursive-db` |
|---|---:|---:|
| Scorable | **498 / 498** | 496 / 498 |
| Correct | 436 | 435 / 439 |
| Accuracy (same 496 convention) | **87.50%** | 87.70% / 88.51% (mean 88.10%) |
| **Scoring-side timeout recoveries** | **0** | 121 backfills were needed repo-wide |

**Two readings**:

1. **−0.6pp, inside the noise band (0.2~1.4pp)** — matching the ±1pp predicted by §3, Evidence 3.
   **It does not raise accuracy, and that now rests on a full run rather than a 24-question
   sample.**
2. **Its recurrence-prevention purpose is met**: across all 498 questions, **not one** record
   needed scoring-side timeout recovery. That is exactly why it was added — so a query that errors
   or times out inside the loop returns to the model with its real error instead of reaching
   scoring as a `no_answer`.

Incidentally, **all 498 were scorable** this time, with `bird_1507`/`bird_1528` participating and
both correct — confirming the `evidence=None` defect is genuinely fixed (see point 3 below).

### Three things that must be stated whenever this number is cited

1. **88.10% is on the corrected gold *after* the timeout backfill** — not directly comparable to
   any number published before 08-23.
2. **It runs on the Chat Completions path.** Arms carrying `reasoning_capture` run on the
   Responses API and are not accuracy-comparable (`e3-c-recursive-db-reasoning`'s 87.9% / 87.3%
   belong to the latter).
3. **2 of the 498 are not scorable** — the denominator is 496. They are `bird_1507` and
   `bird_1528`: the `evidence=None` `AttributeError` from `harness_defects_2026-08-18.md` §2.
   **Correction: that defect is fixed** (`(evidence or "").strip()` at
   `ours/recursive_db_rlm.py:102,123`); the eight-arm runs simply predate the fix, so their
   denominator is permanently 496. **New runs score both questions** — the final-gate full run
   that finished overnight on 08-24 is 498/498 scorable, with both of them correct.

---

# The plan from here (from 2026-08-25)

## Why this ordering

Last week's four tasks are all complete; `WEEK_PLAN_2026-08-20.md` is closed. This week's four
lines of evidence pin the bottleneck on **semantics + benchmark convention**, so the ordering
principle is: **anything that routes around that bottleneck gets demoted.**

---

## P0 — Human baseline calibration (the only blocking item; needs you personally)

This is the **one step of this round that was not completed**, and it has to be done by a person:
"a review conducted inside the same AI system" cannot substitute for an independent baseline.
Two materials are ready, laid out question by question for direct reading:

| Material | What to judge |
|---|---|
| `tie_convention_manual_review.md` — 28 tie questions: prompt text / gold row count / gold SQL / model SQL, the two groups laid out separately | **Can a human tell from the question text whether to return one row or all ties?** (Blind-judge "one / all", then check against the answer key — about 30 minutes) |
| `located_phaseA_all29.json` + the closing section of `phase_a_first_pass` — 29 localisation claims with their `check_result` | Did the localisation land; was the claim genuinely verified (about 1 hour) |

**Why this blocks the rest.** The tie material decides whether the paper writes `ties` as
"model error" or "benchmark ambiguity." If a human also cannot tell the two groups apart, it is
clean benchmark-defect evidence (44pp gap + 7/7 closed mechanism) and goes straight into the
discussion section; if a human can tell, the stronger claim ("the question text provides no basis
for distinguishing them") has to be narrowed — though the rule still cannot be built, since
train's 90:10 stands either way. The Phase A material decides whether the 29-question corpus can
still be used for causal analysis.

---

## P1 — Resampling has said what it has to say; the next move is sampling, not another layer

The planned P1 ("run the few-shot two-arm test") ran on 08-24 and **came out negative** (§4.4).
The measurement itself then needed two more rounds of repair (§4.1); only the third is
trustworthy. The line has now converged on one result:

**58% of deep-failure questions are genuinely out of the model's reach; 24% are just runs that
went astray** (§4.3).

That formally closes the intervention-arm route: it only means anything on questions with a
commitment point to intervene on, and locked-in is down to **3 of 28 (11%)** under v3. Adding arms
across 3 questions is multiple comparisons, which this project does not do.

### Do this one first: test "sample more than once and vote"

| | |
|---|---|
| **Hypothesis** | The 24% in §4.3 (k=1 accuracy 50%–100%) need no new method layer — only self-consistency / best-of-n |
| **How to test** | N=5 on the full 498 with the best profile, majority vote, against the single-sample baseline |
| **Expected magnitude** | Roughly 1–3pp — **comparable to layers 3 and 4 combined**, with no new component |
| **Why it is worth it** | The only **new, positive, testable** direction this week produced; every other lead says "do not invest there" |
| **Risk** | 5× cost; and if the failures are *consistent* (the model errs the same way every time) voting gains nothing — which is exactly what the test settles |

**This is a hypothesis, not a result.** The 24% is computed at k=1 over 38 questions, and k=1 is
not the real agent's full trajectory (§4.5, boundary 1).

### Then two cheap ones, in parallel

| # | What | Why |
|---|---|---|
| 2 | **Chase the delimiter-splitting urge**: on how many questions does a packed `<a><b><c>` string trigger a `WITH RECURSIVE` / `split`-style rewrite? | The **one positive lead** the two-arm experiment left, landing on the §3 bottleneck (format/convention) — feeds track C directly |
| 3 | **Finish the ratio-formula resampling**: currently only turn 1 of 10 of 18 questions, run2 not done | Its "marginal" share is 40% against 11% in the "other" class — worth confirming the classes really differ |

**Known-issue status**:

1. ~~`resample_turn.py` needs a per-sample fallback~~ — **fixed and committed**.
2. ~~k=1 semantics are wrong~~ — **resolved by v3's execute-draft-and-continue** (§4.1).
3. Backfill `gold_answer` for `bird_518` and `bird_701` (currently `None`) — **still not fixed.**
   `shared/evaluator.py:46` returns `False` for `None` unconditionally, so a run yields a
   beautiful-looking 0/10 that is really the scorer comparing against `None`.

---

## P1.5 — The tie convention: I changed my mind, this rule should ship

See [`tie_rule_counterfactual_2026-08-25.md`](tie_rule_counterfactual_2026-08-25.md). I rejected
this rule three times, and **all three grounds were wrong**:

| | Ground for rejection | Why it was wrong |
|---|---|---|
| A | Conflicts with 90% of train gold | **Measured the wrong object** — 90:10 describes gold's *syntax*, and BIRD scores by set comparison, so syntax never reaches the scorer |
| B | Net zero | **Script bug** — the probe took `MAX` unconditionally, so every `ORDER BY … ASC` question was measured at the wrong end |
| C | Net +1~+3, too small | **Rewriter bug** — no projection-alias resolution and no NULL-extremum guard inflated the cost by 2 questions |

With the rewriter fixed (alias resolution + empty-result fallback) and the trigger widened to
**every prediction containing `LIMIT 1`**:

| Run | Pool | Recovered | Broken | Net |
|---|---:|---:|---:|---:|
| `recursive_db` run1 | 93 | 7 | 1 | **+6 (+1.21pp)** |
| `recursive_db` run2 | 97 | 7 | 1 | **+6 (+1.21pp)** |
| `final_gate` run1 | 100 | 9 | 4 | **+5 (+1.00pp)** |

**That is larger than layers 3 (+0.4) and 4 (+0.3) combined**, and comparable to the entire
theoretical ceiling of `final_execution_gate` (~1pp) — which we shipped as the recommended default.

**The noise band is the wrong yardstick here**: it measures the randomness of rerunning the model,
while this is a **deterministic post-processing rewrite** — the same transform on the same
predictions gives the same answer every time. The question is whether it holds on a *different*
set of predictions, and across three runs it does: **+6 / +6 / +5.**

### How to land it

1. Implement it as an **ablatable** rule in `sql_postprocessing_rules` with a profile flag, at the
   same level as `no_select_concat`. **Do not flip it on `e3-c-recursive-db` itself** —
   `agent_config_sha256` would change and break the existing eight-arm comparison.
2. **Both guards are mandatory**: projection-alias resolution, and falling back to the original
   query when keeping ties returns an empty set. Drop either and the cost goes from 1 to 3.
3. `bird_82` is a **known, acceptable cost** (the same question in all three runs; the cause is
   clear — the model's `WHERE` differs from gold's).
4. **The train-validation step is blocked and must be stated as such**: there is no local train
   database, only gold syntax to read, and syntax does not reach the scorer. Until a train
   database is available this rule is validated on dev only, and that has to be recorded honestly
   rather than passed off as having cleared the train gate.

**The paper's wording still has to change** (independent of whether the rule ships): not "model
error", and not merely "two coexisting conventions", but — **BIRD's majority style silently drops
answers when the data ties, and which one it drops depends on execution order** (`bird_1002`: 13
tied rows, 13 different answers, gold recorded one of them).

---

## P2 — Settle the paper's structure (three blocks, all on existing data)

| Track | Claim | Evidence status |
|---|---|---|
| **A — mechanism attribution (main line)** | How RLM's three mechanisms distribute their gains, and why each branch came out the way it did | **Complete** — five-layer chain × 2 repeats + three-mechanism mapping + context store's 4% utilisation + 15 recursion failures traced |
| **B — structure vs reasoning volume (deepens A)** | How much of layer 1's gain is "being able to try things" rather than "having tools"; it substitutes for internal reasoning | **Complete** — three independent estimates inside 1.5pp + inverse move in call count + four effort settings × 2 runs |
| **C — convention mismatch (discussion section)** | A class of failure immune to both the method layer and the reasoning budget; it needs different tooling | **Waiting on P0** — train 90:10 audit + 44pp gap + 7/7 closed mechanism are ready; the human adjudication link is missing |

This week's two new lines (per-question recursion tracing, the gate ceiling analysis) both belong
to A; they upgrade "the effect is too small" into **a mechanism-level explanation.**

**Renaming.** `confident_miss` now fails on two counts: the 0.79× reasoning-volume signature comes
out as 0.87×/1.24× on this population (run2 in the opposite direction), and "miss" is inaccurate
for the bulk of it. Rename to **`mechanically_repairable`** in the Phase A context (it describes
what the test does), and move `ties` into a "benchmark ambiguity" section in the paper.

---

## P3 — Cleanup and hygiene

- **Commit this week's uncommitted work**: 5 documents (`phase_a_turn_resampling`,
  `tie_convention_audit`, `tie_convention_manual_review`, and this report in both languages),
  2 scripts (`audit_tie_convention.py`, the change to `resample_turn.py`), and
  `analysisDetail/phaseA_resample/`.
- **`INDEX.md` needs three more rows**: the three documents from the second half of 08-24 are not
  indexed yet.
- **Two copies of `HanyanChen_CV.pdf`** sit in the repo root and under `src/`, unrelated to the
  project — move them out or add to `.gitignore`.
- Documentation loose ends: `NEXT_PHASE_PROMPT.md`'s "check `agent_config_sha256` before
  comparing" needs to become a field-by-field diff; `config_inventory_2026-08-17.md` §7's
  "recursion call rate swings nearly 4×" was really `dev200_run1` using a different prompt —
  measured stable at 12.9%~14.9%.

---

## Explicitly not doing

| Not doing | Why |
|---|---|
| Further investment in the **execution-verification** direction | 60 of 61 remaining failures are semantic; the gate's ceiling is ~1pp and it measured 0.0pp |
| Adding a "on a tie, return them all" post-processing rule | Conflicts with 90% of train gold; sixth approach to the same pit |
| Adding configs or tuning prompts to rescue the recursion effect | +0.3pp was measured across two repeats inside a 1.4pp noise band; more arms only add multiple-comparison risk |
| Using an LLM annotator to produce conclusions | This project's LLM judge scored 2/15; mechanical adjudication has been falsified six times |
| Adding more mechanical checks to "other" | Coverage caps at 30%; the 30 ratio-formula questions were the last safe sub-pattern |
| Adding indexes to the benchmark's original `.sqlite` | Technically possible and would not invalidate historical runs, but it puts every score on a benchmark we altered |
| Regenerating the dataset from source | Changes `dataset_sha256`, fails manifest validation across the whole chain, and voids every completed run |

---

## The next phase in one sentence

**The method-stack line has been measured to its end — four independent lines of evidence all
point at one bottleneck, and it does not live on the method stack. All the value in the next step
sits in two things: getting a human to calibrate those two adjudication sets, and using the
intervention arm to turn "the few-shot retriever led the model astray" into a causal conclusion.**
