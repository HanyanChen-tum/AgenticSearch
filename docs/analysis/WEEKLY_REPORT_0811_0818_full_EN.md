# Seven Days: How Causal Analysis Improved the System (11–18 August 2026)

The thread running through this week: **every improvement came either from turning a
correlation into a causal test, or from falsifying a number that had been treated as a
conclusion.** Two changes actually raised accuracy. Six conclusions were withdrawn — and
the withdrawals are the larger part of the week's output.

A results-only cut of this report, for readers who want what held rather than how it was
arrived at, is in [`WEEKLY_REPORT_0811_0818_EN.md`](WEEKLY_REPORT_0811_0818_EN.md).

---

## 1. Timeline

| Date | Work | Kind |
|---|---|---|
| Tue 08-11 | First profile exposing RLM recursion to the model; opt-in path capturing reasoning at generation time; **corrected the claim that runs were deterministic** | Found the measurement premise was wrong |
| Wed 08-12 | Full reasoning capture; decision points ranked by information gain | Built the diagnostic |
| Thu 08-13 | Sankey generator; **causal resampling of the call-count signal** | Correlation → causal test |
| Fri 08-14 | Hint ablation; error-origin layering; **four tie-handling fixes, all rejected** | Intervention testing |
| Sun 08-16 | All 163 failures adjudicated question by question; **turn-by-turn replay locating where the error enters** | Causal localisation |
| Mon 08-17 | Published the 163-failure fault ledger | Delivery |
| Tue 08-18 | Cross-check against externally corrected gold; three harness defects found; five-layer chain | Found the ruler was broken |

---

## 2. Six corrections where a correlation had been read as a cause

### 2.1 The runs were never deterministic (08-11)

`temperature=0` in the request **is silently dropped by litellm** — gpt-5 models accept
only `temperature=1`. Every prior statement about a configuration reproducing itself
rested on a premise that did not hold.

**Consequence: the ±3pp run-to-run uncertainty cannot be configured away.** From here on
every conclusion carries a noise band. This one changed how all subsequent experiments
have to be read.

### 2.2 "High call count causes failure" — does not reproduce (08-13)

Statistically strong: questions with 6+ tool calls score 34.5%, against 75.1% for those
with 1–2.

Three questions that originally took 15–18 calls, rerun five times each through the full
agent:

| Question | Original calls | Calls on resampling |
|---|---:|---|
| `bird_944` | 18 | 6 (several runs hit the iteration ceiling) |
| `bird_1524` | 15 | 2–11, mean 7.4 |
| `bird_1526` | 15 | 1–8, mean 3.6 |

**Not one run came close to the original count.** The extreme call counts are artefacts of
those particular generations, not properties of the questions. The sample is too small to
claim "fewer calls is better", but reading high call count as a cause of failure is ruled
out.

### 2.3 "Result shape mismatch" is a heterogeneous bucket, not one defect (08-12/13)

Second by information gain (55.3pp spread in accuracy). Twenty cases, **each verified by
causal resampling**, decompose as:

| Sub-type | Questions | Representative |
|---|---:|---|
| **Superlative question, ties never checked** | **3–4** | `bird_1092` (8/8 deterministic), `bird_930` (10/10) |
| Original failure was chance; resampling recovers it | 4 | `bird_798`, `bird_483`, `bird_213`, `bird_149` |
| Gold itself has a logic bug | 3 | `bird_1322` (EXCEPT inverted), `bird_529` (second condition always true), `bird_1399` (CASE with no ELSE) |
| Ties handled backwards | 2 | `bird_1135`, `bird_41` (`ROW_NUMBER` where gold wants `RANK`) |
| Yes/no question wants a YES/NO literal | 2 | `bird_473`, `bird_1399` |
| Output contract / half of a two-part question dropped | 1 | `bird_530` |
| Model over-complicated a simple question | 1 | `bird_637` (gold wants the raw field; the model parsed it with a recursive CTE) |
| Concatenation vs separate columns | 1 | `bird_1011` |
| **Definite-article phrasing triggers `LIMIT 1`** | 1 | `bird_412` ("the card by artist X" matches 50 cards; the model assumed uniqueness without checking) |

**Finding: a statistically strong signal that is mechanically heterogeneous.** Genuine,
reproducible model defects are only **20–25%** of it; about 20% is noise that resampling
clears; about 15% is gold's fault; the rest is known nodes (yes/no form, output width,
concatenated output) re-exposed through this particular cut.

**What can be improved:** the one generalisable mechanism is **assuming uniqueness without
checking**. `bird_412` widens it from superlative questions to **any definite-article
singular phrasing**, a larger surface than it first appeared. Note the direction, though:
hard-coded tie detection was tested (`LIMIT 1 → LIMIT 2`, compared by execution) and
repairs 3 questions while breaking 7 — **net negative**. The intervention has to sit in
the model's own reasoning before it commits, not in a harness override after the fact.

### 2.4 The "yes/no form" node was underrated by the original ranking (08-12)

Only 9 of 500 questions are yes/no in form, but **4 of them (44%)** land in the
result-shape bucket, against a base rate of 4.0% across the full set — eleven times the
concentration. Small sample, clear signal.

### 2.5 Post-hoc re-checking is ruled out as a direction (08-14)

Rather than hard-coding, a **gated re-check** was built: when a query ends in `LIMIT 1` and
more than one distinct value actually exists, feed that concrete execution result back to
the model as a new observation and let it decide. Tested on all 83 matching questions:

- 23 questions where the model did rewrite its SQL (the mechanism works)
- **1 recovered, 9 broken, net −8**

This turned the earlier correlation — rewriting the first guess in the final turn scores
56.7% against 71.9% for not rewriting — **into a causal result**.

With the four earlier attempts, that is **five independent tries at getting the model to
re-check an answer it has already produced, all five net negative.** This is not a problem
with any one implementation; the model-plus-harness combination is structurally bad at
post-hoc review. **The direction is closed; no further variants need testing.**

### 2.6 "22.8% of questions fail because the model believes tools are unavailable" — falsified in four steps (08-18)

Reading the reasoning showed 22.8% of questions where the model states it cannot execute
tools, and those questions score 12.5pp lower. A single-variable A/B followed: one sentence
added to the prompt saying the calls really do execute.

1. The interaction table shows the **actual tool-call rate is 94–100% in all four cells** —
   the model says it cannot execute and calls the tools anyway. The mechanism does not exist.
2. "Wants to verify" is the stronger signal (−17.3pp), but that is **reverse causation**:
   hard question → uncertainty → says it should verify.
3. The evidence rested on **replayed** reasoning, which may not correspond to the original
   run (the module's own docstring names `bird_93` for exactly this).
4. The A/B measured **−4 questions**, with 22 flips one way and 26 the other — cancelling.

**One real side effect, though**: the added sentence made first-turn reasoning 22% shorter
(51.0 → 39.8 sentences per question) with no accuracy change. That reasoning was redundant.

---

## 3. Causal localisation: which step the error enters at

### 3.1 Turn-by-turn replay: 91% of failures are already wrong in the first draft (08-16)

Taking the SQL the model wrote at every turn and **executing each one against gold**:

| Where the error enters | Questions | Share |
|---|---:|---:|
| **Wrong from the first draft, never once correct** | **143** | **91.1%** |
| Correct at some point, then changed to wrong | 7 | 4.5% |
| First draft correct, later broken | 4 | 2.5% |

An average of 2.3 further turns and 13.1 reasoning sections of exploration **almost never
changes the outcome.**

**This independently explains why the five interventions in §2.5 were all net negative**:
the error is fixed at the moment of writing, and anything that looks again is looking at
something already wrong.

### 3.2 Adjudicating all 163 failures question by question (08-16/17)

No aggregate statistics. Each failure read as question text, hint, both SQL queries, both
execution results, with counter-queries against the database where a claim needed testing.

**Result: gold defects 61, model errors 30.** About 27 are SQL bugs that execution alone
falsifies:

| Mechanism | Instance |
|---|---|
| Missing parentheses collapse the condition via AND/OR precedence | `bird_1265` gold returns 47; correct is 35 |
| Text column sorted as if numeric | `bird_879` picks `'91.610'`; the real maximum is 257.32 |
| NULLs sort first under ASC and get picked | `bird_847` returns a driver with no time |
| Join fan-out inflating an aggregate | `bird_198` gives 732.1; correct is 20.25 |

Published as a standalone ledger page, `fault_ledger_163.html` (08-17).

### 3.3 Error origin by layer: where the query first diverges from gold (08-14)

All 163 failures assigned to the **first** layer of the SQL construction pipeline (tables →
join keys → filters → grouping → aggregation → projection → ORDER BY/LIMIT → formatting)
that diverges from gold, by sqlglot parsing with no LLM judgement. *First* is the point:
everything downstream of a wrong table follows necessarily, so only the first divergence is
worth intervening on.

| First layer to diverge | Questions | Share |
|---|---:|---:|
| Filter column | 35 | 21.5% |
| **Table selection** | **33** | **20.2%** |
| Join key | 24 | 14.7% |
| Aggregate function | 22 | 13.5% |
| Formatting / column order only | 11 | 6.7% |
| Used an extra table | 10 | 6.1% |
| Projection width / filter literal / grouping / ORDER BY LIMIT | 27 | 16.5% |

**Finding 1: retrieval is not the gap.** For each of the 33 table-selection failures, the
table gold needed and the prediction missed was checked against whether it had been
retrieved and offered to the model (the trace carries a `selected` flag):

| Case | (question, table) pairs |
|---|---:|
| Never retrieved | **0** |
| Retrieved but not selected | **0** |
| **Retrieved, selected, and the model did not use it** | **37** |

**37 of 37 had the table in front of the model already.**

**Finding 2: only 2 of those 33 are genuinely the model's error.** Looking at what the
model used instead, **23 of 33 are cases where gold joins one more table than the model
did** — the model wrote the simpler query rather than picking the wrong table.
Cross-checked against the per-question adjudication: 20 gold defects, 2 genuine model
errors (`bird_352`, `bird_465`), 11 not covered.

**What can be improved:**

1. **Improving schema retrieval is ruled out for this class** — 37/37 leaves no retrieval
   gap to close, and 98.4% table recall says the same. Further investment there is wasted.
2. **The filter column layer (21.5%) is where the model's real errors concentrate**, not
   table selection, which is the one that looks most like a method problem.
3. Most of the table-selection "errors" are an artefact of gold joining an extra table.
   **A layer breakdown like this must have gold defects removed before it is read**, or
   effort goes to the wrong layer.

---

## 4. The ruler is broken (08-18, the most important finding of the week)

### 4.1 Three columns, separating "changed reference" from "resampled"

Cross-checked against the corrected gold released by a different group (VLDB 2026,
arXiv:2601.08778):

| Column | Model's answer | Scored against |
|---|---|---|
| A | original answers | original gold |
| B | **the same original answers** | corrected gold |
| C | answers from a new run | corrected gold |

`B − A` isolates the reference change; `C − B` isolates resampling. Without that split the
two are indistinguishable — and two runs of the same configuration in this project flip 20
questions out of 480, which is larger than most interventions tried here.

| | Clean subset, 277 | **Gold-only corrections, 74** |
|---|---:|---:|
| A | 81.9% | **50.0%** |
| B | 87.7% | **71.6%** |
| C | 86.3% | 70.3% |
| **Attributable to the reference change** | **+16** | **+16** |
| Attributable to resampling | −4 | −1 |

On the 74 questions where neither question text nor hint was touched, **not one byte of the
model's SQL changed and the score went from 50.0% to 71.6%.**

Of the 26 questions that flipped from wrong to right, **19 are ones §3.2 had independently
assigned to `gold`** — three lines of evidence converging.

### 4.2 A harness rule fitting the broken gold

`count_no_distinct` strips `DISTINCT` from `COUNT` whenever the query joins, warranted by
2377 applicable train queries at **0.891 support**.

But the corrected gold uses `DISTINCT` in 130 of 498 questions where the original used it
in 83 — **a 57% increase**. That 0.891 was measuring how often annotators omitted
`DISTINCT`, not what the SQL means.

`bird_1505` asks "how many **customers**":

```
what the model wrote (right)   COUNT(DISTINCT T1.CustomerID)
what the harness made of it    COUNT(T1.CustomerID)
the original gold (also wrong) COUNT(*)
```

**The rule's error and the gold's error cancelled, so it scored as correct** on the
original gold. Correct the gold and the cancellation disappears.

**Disposition:** disable the two rules that change **what the query computes**; keep the one
that only changes **output shape**. The criterion lives in `SEMANTICS_CHANGING` in
`build_sql_conventions.py` — that script recomputes `enabled` from support, so editing the
artefact alone would let the rules come back on the next rebuild.

> Harness post-processing may normalise the shape of an answer. It may not change what the
> query computes. Support says how often annotators wrote something, not whether writing it
> was right.

### 4.3 The harness scored its own crashes as model failures

This machine's console is cp936 and neither `print()` call has a verbosity switch. A
database row containing a character it cannot encode raises `UnicodeEncodeError`; the
exception escapes and is recorded as the model's failure with `correct=False`.

**`bird_847`: the model queried correctly and got `Räikkönen`; `ä` does not encode in
cp936, so the question scored wrong.**

**This is selective, not random noise** — it kills questions whose answers contain
non-Latin characters, clustered by database (`card_games` 12%, `formula_1` 8%), so it
distorts the totals *and* every stratified analysis.

One level deeper: exception classification uses a **substring whitelist on the class name**.
Anything not containing `API`/`Connection`/`Timeout` is recorded as a model failure. The
direction is inverted — unanticipated exceptions are overwhelmingly our own code breaking.
Repository-wide audit: `NotFoundError` 200, `UnicodeEncodeError` 66, `BadRequestError` 33,
all silently scored as the model being unable.

### 4.4 The noise band itself was measuring the wrong thing

The "1–2pp same-configuration noise" figure came from two pairs of repeats. Checked
individually, **neither pair holds**: one differs in `max_iterations` (8 vs 15, a field that
does **not** enter `agent_config_sha256`, so the hashes match while the configurations do
not); the other has unequal crash counts (0 and 16), so the gap includes a harness bug.

The one clean same-configuration repeat: **86.7% both times, 0.0pp aggregate difference —
but 20 of 480 questions flip.** Both numbers have to be reported. Configuration-level
comparison can use a tight ruler; **per-question causal analysis cannot treat that 0.0pp as
stability.**

---

## 5. What actually raised accuracy this week (two things)

| Change | Effect | Kind |
|---|---|---|
| Fixed the console encoding crash | **+2.2pp** on each reasoning arm; `arcwise_full` 84.5% → **86.7%** | Recovered misjudged questions |
| Disabled the two semantics-changing convention rules | Positive on corrected gold, −2 on the original | Stopped fitting the broken gold |

**Everything else was a negative result or a withdrawal.** That is not a failure: §2.5's
five net-negative post-hoc interventions and §3.1's 91% first-draft finding corroborate each
other, and together they **close off post-commitment intervention as a direction** — worth
more than two points.

Also fixed along the way: encoding and credentials in `baselines/` (B1/B2 have been
**unable to run** since a shared-resolver refactor, discovered only this week), and the
guard gap where `no_select_concat` broke a subquery alias.

---

## 6. The five-layer chain (in progress)

Corrected dataset, 498 questions:

| Layer | Configuration | Accuracy |
|---|---|---:|
| 0 | B1, no method at all | **70.3% / 70.1%** (0.2pp noise) |
| 1 | `clean-e0` | in progress |
| 2 | `e3-c-noconv` | **85.3%** |
| 3 | `e3-c-conv-rules` | **86.7% / 86.7%** |
| 4 | `e3-c-recursive-db` | **86.1%** |

### Recursion (the paper's subject): first results

| | Questions | No recursion | With recursion | Diff |
|---|---:|---:|---:|---:|
| Full set | 498 | 86.7% | 86.1% | −3 |
| **Recursion actually invoked** | **74 (14.9%)** | 85.1% | 87.8% | **+2** |
| Not invoked | 424 | 87.0% | 85.8% | −5 |

**The +2 sits inside the per-question jitter** (20 flips per 480 on a clean repeat) and
cannot be called an effect. The −5 on the 424 questions where recursion never ran can only
come from the prompt difference — a confound that cannot be designed away, since a prompt
that does not name the recursion tool means the model never calls it (historically: 0
invocations across 197 questions).

**This week's data supports neither "recursion helps" nor "recursion hurts." The effective
sample is too small.**

---

## 7. Next week

1. Finish the chain: two runs of `clean-e0`, second runs of the rest
2. Fix the two remaining harness defects (exception misclassification, `evidence` being
   `None`) and rerun the three runs still depressed by them
3. Redo the reasoning-trace causal tracing on the corrected gold; two methods exist, and
   **neither produces conclusions until a human agreement rate is measured**
4. **The 14.9% recursion invocation rate is a precondition for the RLM paper**, not a
   detail — either raise the rate, or change the paper's subject to why the model so rarely
   chooses recursion

> Cleanup: a stray `jixu` sits on the first line of `SYNTHESIS.md` and should be removed.
