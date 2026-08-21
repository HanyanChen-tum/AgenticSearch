# Five-Layer Ablation Chain and Reasoning-Volume Metrics (2026-08-19)

A full re-run on the corrected dataset `bird_dev_500_corrected_full.json` (498 questions),
twice per configuration. All harness encoding crashes have been fixed (see
[`harness_defects_2026-08-18.md`](harness_defects_2026-08-18.md)). Every number below is
computed on **the same 491 scorable questions**: the 7 questions that a harness crash left
without a result in any arm are dropped from every arm, because otherwise the layers are
not being judged on the same questions.

---

## 1. The five-layer chain

| Layer | Configuration | What it adds | run1 | run2 | Mean | Noise |
|---|---|---|---:|---:|---:|---:|
| 0 | B1 | No method: one-shot generation | 70.7% | 70.3% | **70.5%** | 0.4pp |
| 0-prime | B2 | + keyword-table prefilter | 67.0% | 68.0% | 67.5% | 1.0pp |
| 1 | `clean-e0` | + agent tool loop | 84.3% | 83.5% | **83.9%** | 0.8pp |
| 2 | `e3-c-noconv` | + offline schema retrieval | 85.7% | 87.2% | **86.5%** | 1.4pp |
| 3 | `e3-c-conv-rules` | + convention post-processing | 87.0% | 86.8% | **86.9%** | 0.2pp |
| 4 | `e3-c-recursive-db` | + **RLM recursion** | 86.6% | 87.8% | **87.2%** | 1.2pp |

**Measured noise is 0.2-1.4pp** across four same-configuration repeats. The "1-2pp" figure
recorded earlier in config_inventory does not hold: one of its two pairs differed in
`max_iterations` (8 vs 15), the other had unequal crash counts on the two sides. A 0.0pp
reading obtained mid-investigation was luck - offsetting per-question flips.
**Use 1.4pp as the ruler.**

### Layer increments

| Increment | Value | Reading |
|---|---:|---|
| 0 to 1, agent tool loop | **+13.4pp** | Far above noise; the one real effect |
| 1 to 2, offline schema retrieval | **+2.5pp** | Above noise; credible |
| 2 to 3, convention post-processing | +0.4pp | **Inside noise; unreadable** |
| 3 to 4, **RLM recursion** | **+0.3pp** | **Inside noise; unreadable** |

**Of the 16.7pp total gain, 13.4pp comes from layer 1.** The three layers above it sum to
+3.2pp, diminishing at each step, and the last two are individually inside the noise band.

### RLM recursion: both numbers, as required

A paper may report neither the full-set effect alone (diluted) nor the invoked-only effect
alone (selective reporting). Both:

| | Invocation rate | On questions that invoked recursion, vs layer 3 | On the rest |
|---|---:|---:|---:|
| run1 | 74/498 = 14.9% | **+2.7pp** (87.8% vs 85.1%, n=74) | -1.2pp |
| run2 | 64/498 = 12.9% | **-3.1pp** (89.1% vs 92.2%, n=64) | +1.4pp |

**The two repeats have opposite signs.** At n=64-74, 3pp is two or three questions. The
conclusion is therefore not "an effect exists but is diluted by the full set" - it is that
**no stable effect is measurable**.

Invocation rate is 12.9%-14.9%, far steadier than the 3.8%-15.6% recorded in
config_inventory section 7. The 4.0% entry there (`e3_c_recursive_db_dev200_run1`) was
shown by [`run_config_audit_2026-08-18.md`](run_config_audit_2026-08-18.md) to have run
**a different prompt** (`recursive-leaf-protocol-v1`); it is not same-configuration
variance, and that section's "nearly 4x swing at the same configuration" must be rewritten
accordingly.

---

## 2. Reasoning-step statistics

Script: [`scripts/reasoning_step_stats.py`](../../../scripts/reasoning_step_stats.py).
Four measures:

| Measure | Meaning | `e3-c-conv-rules` run1 |
|---|---|---|
| `llm_calls` | Agent turns | mean 2.3, median 2, max 6 |
| `tool_actions` | `db.execute` / `sample_values` calls | mean 1.8, median 1, max 13 |
| `turns` | Deepest turn index in the trace | mean 1.1, median 1 |
| `reasoning_tokens` | Tokens spent inside the model's reasoning | mean 3259, median 2262, p90 7440, max 25137 |

**The first three are nearly constant** - 96% of questions finish within one or two turns.
This agent does not work by iterating over turns; it works by reasoning at length inside a
single turn. So "reasoning steps" carries information only in the token measure.

The recursion arm reasons a whole tier more (mean 4346 vs 3259, max 54206 vs 25137):
**recursion does make the model think more, and its accuracy contribution is +0.3pp.
The cost went up; the benefit did not.**

### A confound that has to be controlled

Unstratified, wrong answers use 1.7-2.1x the reasoning of right ones. But difficulty moves
with reasoning volume by itself:

| Difficulty | Accuracy | Median reasoning tokens |
|---|---:|---:|
| simple | 92.5% | 1532 |
| moderate | 85.9% | 2245 |
| challenging | 82.4% | 3286 |

Stratified by difficulty (median reasoning ratio, wrong over right):

| Difficulty | conv-rules | recursive-db |
|---|---:|---:|
| simple | 2.12x | 1.20x |
| moderate | 1.99x | 1.86x |
| challenging | **0.82x (reversed)** | 1.43x |

The effect survives stratification on simple and moderate, but the challenging stratum
reverses in one arm and each cell holds only 9-22 questions. **This is a lead, not a
finding** - it has the same shape as this project's earlier "wanting to verify is the
strongest failure signal", which turned out to be a difficulty proxy.

---

## 3. Error class by reasoning volume: two failure modes point opposite ways

> **Scope note, 2026-08-21.** "Convention" in this section means the three checks
> below (`ties` / `under_projection` / `distinct_repair`). Two checks added later,
> `column_permutation` and `concat_columns`, behave differently -- their reasoning
> volume is *higher* than correct answers (1.94x), not lower (see
> [`other_failures_breakdown_2026-08-21.md`](other_failures_breakdown_2026-08-21.md)).
> They are not part of "the model does not know it is wrong". Cite this section's
> finding scoped to the original three checks, not extended to the later ones.

Triaged with [`scripts/triage_failure_causes.py`](../../../scripts/triage_failure_causes.py),
which emits only facts that re-execute and never a verdict, then pooled over the eight arms:

| Class | n | Median reasoning tokens | vs correct |
|---|---:|---:|---:|
| **Convention** (`ties` / `under_projection` / `distinct_repair`) | 91 | **1619** | **0.80x (lower)** |
| Row-set (`row_superset` / `row_subset`) | 34 | 4434 | 2.18x |
| Other | 424 | 4212 | 2.07x |
| Correct answers | 3414 | 2036 | 1.00x |

**Convention failures reason 20% less than correct answers; the other two classes reason
twice as much.** This is why the previous section's "wrong answers reason longer" would not
come out clean under stratification - two populations pointing opposite ways were averaged
together:

- **The model does not know it is wrong** (convention): short reasoning, settled in one
  pass, confident. It answered the question correctly and lost on a convention in the
  reference SQL - `LIMIT 1` versus `HAVING = MIN` for ties, whether `COUNT(DISTINCT)` is
  required, whether one column or two are returned.
- **The model is stuck** (the other 424): long reasoning, repeated weighing. This is
  genuine semantic difficulty.

Averaging the two treats "wrong format" and "could not work it out" as one thing.

### Composition by layer: the method stack solves difficulty, not convention mismatch

| Layer | Total failures | Convention | Share | Other |
|---|---:|---:|---:|---:|
| 1 clean-e0 | 159 | 20 | 12.6% | 132 |
| 2 noconv | 133 | 24 | 18.0% | 99 |
| 3 conv-rules | 129 | 25 | **19.4%** | 95 |
| 4 recursive-db | 128 | 22 | 17.2% | 98 |

The convention count barely moves (20, 24, 25, 22); what gets eliminated is "other"
(132 to 95). Layer 3's convention post-processing is precisely the machinery meant to fix
this class, and it took convention failures from 24 to 25 - **not one removed**. That is
consistent with its +0.4pp sitting inside the noise, and it supplies a mechanism rather
than merely "the effect is too small".

---

## 4. Reasoning-effort sweep

Same configuration (`e3-c-conv-rules`), same corrected dataset, only `reasoning_effort`
varies. This arm was chosen because its two high-effort runs differ by 0.2pp, the tightest
repeat in the chain.

| Effort | Accuracy | Median reasoning tokens | Mean | Mean `llm_calls` | Median latency |
|---|---:|---:|---:|---:|---:|
| minimal | **72.2%** | 0 | 9 | 2.87 | 4.3s |
| low | 83.7% | 232 | 330 | 3.34 | 6.5s |
| medium | 85.9% | 864 | 1289 | 2.49 | 9.1s |
| high run1 | 87.1% | 2262 | 3259 | 2.27 | 14.7s |
| high run2 | 86.9% | 2046 | 3241 | 2.27 | 14.1s |

**Sharply diminishing returns:** minimal to low spends 232 reasoning tokens to buy
+11.5pp; low to medium spends another 632 to buy +2.2pp; medium to high spends another
1400 to buy +1.1pp. **Reasoning volume rises nearly tenfold (232 to 2262) to move accuracy
from 83.7% to 87.0%.**

Two side conclusions:

1. **`minimal` at 72.2% is comparable to B1 at 70.5%.** B1 is one-shot generation with high
   reasoning; `minimal` is the full agent tool loop with almost no reasoning. That they land
   together means **the agent loop and the model's internal reasoning are largely
   substitutes for one another**, not two things that add up. This sharpens how layer 1's
   +13.4pp should be read: what it buys is not the tools as such.
2. **Lower reasoning, more `llm_calls`** (2.27 to 3.34): a model that thinks less internally
   goes back to the database more often. The two kinds of "thinking" trade off observably.

### How the error mix moves with effort

| Effort | Failures | Convention | Share | Other |
|---|---:|---:|---:|---:|
| minimal | 138 | 22 | 15.9% | 116 |
| low | 81 | 13 | 16.0% | 68 |
| medium | 70 | 16 | 22.9% | 54 |
| high | 64 | 12 | 18.8% | 52 |

**The absolute convention count is essentially flat across all four settings (22, 13, 16,
12); what reasoning volume removes is "other" (116 to 52).** This agrees with the by-layer
result in section 3: **reasoning volume buys semantic correctness and cannot buy format
compliance.** Convention failures are near-immune both to reasoning effort and to method
layer; they need a different instrument.

---

## 5. Limitations

1. Each effort setting was run **once**. That is sufficient for `reasoning_tokens`
   (a continuous measure at n of about 496), but 1pp-scale **accuracy** differences between
   settings need repeats - the 1.1pp between medium and high is not yet decidable.
2. The error classes in sections 3-4 come from the re-executable triage, which covers only
   what can be checked mechanically. "Other" remains a mixed class and is not yet broken
   down.
3. Per-question flip rate between same-configuration repeats is a stable 5-6% (order of
   20/480). **Aggregate stability does not imply per-question stability**; no per-question
   causal analysis may treat the aggregate noise band as a guarantee.
4. Still unfixed: exception misclassification and `evidence=None` (harness_defects
   sections 2 and 3); 33 `BadRequestError` records remain undiagnosed.

---

## 6. Conclusions, in plain terms

### What was actually done

Start from the plainest possible method, add one thing per layer, measure each layer,
run every configuration twice:

| Baseline | Hand the model the question and the schema, let it write SQL once, no database access, no revision | **70.5%** |
|---|---|---:|
| Layer 1 | Give it tools, so it can actually query the database and revise after seeing results | **83.9%** (+13.4) |
| Layer 2 | Pre-select the probably-relevant tables and columns offline, then hand those over | **86.5%** (+2.5) |
| Layer 3 | Rewrite its SQL automatically into the conventions the reference answers use | **86.9%** (+0.4) |
| Layer 4 | On hard questions, split off sub-problems and solve them recursively | **87.2%** (+0.3) |

### Conclusion 1: only the first layer really works

**Of the 16.7 percentage points gained in total, 13.4 come from layer 1** — from letting the
model actually touch the database.

How should +0.4 and +0.3 be read? Running **the same configuration twice, unchanged**, the
two results already differ by 0.2-1.4 points. That is the model's randomness, not the
configuration. Since +0.4 and +0.3 are smaller than "the same thing done twice", **they were
not measured at all**.

By analogy: if the bathroom scale is accurate to 1.4 kg, reading 0.3 kg lighter is not
weight loss.

### Conclusion 1.5: which RLM mechanisms these layers correspond to

This has to be stated precisely or the result is easy to misread.
[`README.md` §2.3](../README.md) splits RLM into **three** measurable capabilities, not one:

| RLM mechanism | What it means | Which layer carries it | Measured |
|---|---|---|---:|
| 1. Programmatic reasoning / exploration | Schema, descriptions and few-shot externalised into a context store the model searches, selects from and composes by code | Layer 2 (offline schema retrieval — a weakened form of it) | **+2.5pp** |
| 2. Executable environment | A REPL holding intermediate plans, candidate SQL, DB observations; every key action executes and enters the trace | **Layer 1** | **+13.4pp** |
| 3. Self-improvement and divide-and-conquer | Root revises its own SQL from observations; **only on** hard questions it calls a depth-1 leaf | First half in layer 1, second half is layer 4 | second half **+0.3pp** |

So it is **wrong to say "RLM's contribution cannot be measured"** — the opposite. Almost all
of what was gained (+13.4pp) *is* mechanism 2, plus the first half of mechanism 3. The
accurate conclusion is much sharper:

**RLM's three mechanisms pay off very unevenly on this task; nearly all of the return sits
in "executable environment plus self-improvement".**

The other two each have independent evidence for why they do not pay. Mechanism 1 in its
full form (the context store) was already measured in
[`e5_a_context_store_smoke1.md`](../analysisDetail/e5_a_context_store_smoke1.md): this task runs
at **4% context utilisation**, so the premise "externalise because it does not fit" does not
hold and only the cost of extra read turns remains. Layer 2 here is its weakened form
(offline retrieval rather than model-driven search) and returns +2.5pp. Mechanism 3's second
half is below.

### Conclusion 2: the divide-and-conquer half shows no measurable effect

Layer 4's depth-1 recursion is the second half of mechanism 3. On the full set it is +0.3
percentage points, inside the error bar.

One might object that recursion only fires on a few hard questions, so a full-set average
would of course wash it out, and one should look only at the questions that used it. Done —
and it comes out worse:

- Run 1: on the 74 questions that used recursion, **2.7 points higher** than without
- Run 2: on the 64 questions that used recursion, **3.1 points lower** than without

**The two runs conclude the opposite.** Three points across a few dozen questions is two or
three questions. So the problem is not "the effect was diluted by averaging" — there is
**no stable effect to speak of**.

And recursion made the model think about a third more (mean reasoning volume 4346 vs 3259).
**The cost went up; the return did not.**

### Conclusion 3: the model makes two kinds of mistake, and only one was addressed

Splitting the wrong answers apart reveals two quite different populations:

| | The model "does not know it is wrong" | The model "could not work it out" |
|---|---|---|
| Count | 91 | 424 |
| How long it thought | **20% less than on correct answers** | 2x correct answers |
| Behaviour | Settled in one pass, confident | Weighs repeatedly, revises |
| What went wrong | It answered the question correctly; the writing convention differs from the reference | It genuinely misread the question or the data |

Examples of the first kind: with a tie for first place the reference lists every tied row and
the model returned one; the reference counts distinct values and the model counted rows; the
question asks two things and the model answered one. **The model is blind to these** — it
believes it answered correctly, which is why it thinks fast and briefly.

The key finding: **no matter how many method layers are stacked, and no matter how long the
model is allowed to think, the count of the first kind barely moves.**

- Up the method layers: 20, 24, 25, 22
- Up the reasoning budget: 22, 13, 16, 12

What gets eliminated is entirely the second kind (132 to 95; 116 to 52).

More pointedly: layer 3, the module built specifically to fix the first kind, took it from
24 to 25 — **not one removed**.

In one line: **everything built here helps the model "work it out", and none of it helps the
model "guess the grader's habits".**

### Conclusion 4: letting the model think longer pays off fast, then barely at all

Holding the configuration fixed and turning only the thinking-budget dial:

| Thinking budget | Accuracy | Reasoning spent |
|---|---:|---:|
| Almost none | 72.2% | 0 |
| Low | 83.7% | 232 |
| Medium | 85.9% | 864 |
| High | 87.0% | 2262 |

**The first 232 reasoning tokens buy 11.5 points; nearly ten times more spending after that
buys another 3.3.**

An interesting side observation: **"barely thinks but can query the database" (72.2%) lands
close to "thinks hard but answers once" (70.5%).** That suggests "let the model try things"
and "let the model think it through" are largely **two substitutable routes**, not two
things that add up. Supporting evidence: the lower the thinking budget, the more often the
model goes back to the database (2.27 calls up to 3.34) — less thinking inside, more trying
outside.

This also sharpens how conclusion 1's +13.4 points should be read: **what it buys may not be
"tools" as such, but the ability to try and correct** — and trying is the same thing as
internal reasoning in a different form.

---

## 7. What to do next, and why

### First, a decision: how the paper should be organised

`config_inventory_2026-08-17.md` §6 stated the thesis as "argue the contribution of **RLM
recursion** over the baseline". **That phrasing narrows RLM** — per
[`README.md` §2.3](../README.md) RLM is three mechanisms and recursion is only the second half
of mechanism 3. Read through the narrow phrasing, these results would be misreported as
"RLM contributes nothing", which is wrong.

Taken mechanism by mechanism, the conclusion is **a very uneven return, not an absent one**:

| RLM mechanism | Increment | Status |
|---|---:|---|
| 2 executable environment + 3 self-improvement | **+13.4pp** | **The main contribution, far above the error bar** |
| 1 programmatic exploration (weakened: offline retrieval) | +2.5pp | Above the error bar; the full context store measured separately as no gain |
| 3 divide-and-conquer (depth-1 recursion) | +0.3pp | Inside the error bar; not measurable |

**So the paper's question is not "does RLM help" but "which of RLM's three mechanisms is
paying the bill".** That is a stronger thesis than the original: it is a positive, directional
result, and each branch has independent evidence for why it does or does not pay.

What should *not* be done is adding configurations or tuning prompts to rescue the recursion
branch. The +0.3pp was measured across two repeats against a 1.4pp error bar; trying more
configurations only raises the chance of a good-looking number appearing by luck. That is
not a finding, that is picking data.

Three pieces of content under this thesis:

| | Claim | Still missing |
|---|---|---|
| **A. Mechanism attribution (main line)** | How the return distributes across the three mechanisms, and why each branch came out as it did | Breaking down the 424 "could not work it out" questions |
| **B. Structure vs reasoning volume (deepens A)** | How much of the executable environment's return is really "being able to try" rather than "having tools" — it substitutes for internal reasoning | One cheap follow-up experiment (below) |
| **C. Convention mismatch (discussion)** | One class of failure is immune to both method layer and thinking budget, and needs a different instrument | Manual adjudication of the 91 questions |

**Suggested: A as the main line, B deepening A, C as a discussion section.**

`config_inventory_2026-08-17.md` §6 has been corrected accordingly, so later readers do not
repeat the same narrowing.

### The four concrete tasks, in order

**First, fix the three harness defects (half a day).**
Why: they all sit on the scoring path, and leaving them means every new number has to be
redone later. The encoding bug already forced one published number from 84.5% to 86.7%; that
must not happen twice. The chain has finished and nothing is running, which is the only safe
window to change scoring.

**Second, test whether the substitution relationship actually holds (2-3 hours).**
Why: this is the claim most likely to be overturned this week, so it goes first. At present
there is only one cross-configuration single run behind it — 72.2% against 70.5%, a gap of
1.7 points sitting right at the error bar. The clean version is to fill in the
`clean-e0 × almost-no-thinking` cell, which directly answers "of layer 1's 13.4 points, how
much is the tools and how much is merely moving the thinking into the loop".
**If it does not support substitution, branch B has to be withdrawn — better to know early.**

**Third, break down the 424 "could not work it out" questions (two to three days).**
Why: this is the core evidence for the main line and the largest information gap. All that is
known now is that they take longer; not where they go wrong. The method must be **checks that
re-execute** ("change this to X and the result matches the reference row for row"), not
labels from another model — this project's LLM judge has a historical accuracy of 2 out of
15, and mechanical rules have already been falsified four times. Adjudicate 30 by hand first
as a baseline; below about 80% agreement the automatic pass cannot carry statistics.

**Fourth, fill in the repeats (background).**
Why: each of the four thinking budgets was run once. That is enough for reasoning volume as a
continuous measure, but medium 85.9% against high 87.0% is 1.1 points and still inside the
error bar. Without repeats it is three points, not a diminishing-returns curve.

### Explicitly not doing

- **No more configurations or prompt tuning to rescue the recursion branch.** Reasons above.
- **No re-running old experiments whose configuration definition has since changed.** Their
  data should be regenerated with current code rather than mixed with new results.
- **No LLM as a labelling oracle for conclusions.** Use it for triage only; conclusions must
  rest on executable checks or human adjudication.

### One bookkeeping issue that must be handled at the same time

Once the exception misclassification is fixed, the accuracy denominator will no longer include
questions that crashed. Every arm's number will rise by 0.4-0.9 points together. **Every number
already published must be labelled with which convention it uses**, or this produces another
batch of non-comparable figures — exactly the trap of the 84.5% to 86.7% correction.

## Files

- `results/chain_*_corrected_run{1,2}.json` - the eight arms of the chain
- `results/effort_{minimal,low,medium}_conv_rules_run1.json` - the effort sweep
- `analysisDetail/step_stats_high.json`, `analysisDetail/triage_chain_*.json`, `analysisDetail/triage_effort_*.json`
- [`scripts/reasoning_step_stats.py`](../../../scripts/reasoning_step_stats.py), [`scripts/triage_failure_causes.py`](../../../scripts/triage_failure_causes.py), [`scripts/audit_run_configs.py`](../../../scripts/audit_run_configs.py)
