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

Script: [`scripts/reasoning_step_stats.py`](../../scripts/reasoning_step_stats.py).
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

Triaged with [`scripts/triage_failure_causes.py`](../../scripts/triage_failure_causes.py),
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

## Files

- `results/chain_*_corrected_run{1,2}.json` - the eight arms of the chain
- `results/effort_{minimal,low,medium}_conv_rules_run1.json` - the effort sweep
- `analysisDetail/step_stats_high.json`, `analysisDetail/triage_chain_*.json`, `analysisDetail/triage_effort_*.json`
- [`scripts/reasoning_step_stats.py`](../../scripts/reasoning_step_stats.py), [`scripts/triage_failure_causes.py`](../../scripts/triage_failure_causes.py), [`scripts/audit_run_configs.py`](../../scripts/audit_run_configs.py)
