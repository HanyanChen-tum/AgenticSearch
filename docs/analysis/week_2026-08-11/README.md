# Weekly Report, 11–18 August 2026

Results only. The full account, including every negative result and every conclusion
withdrawn this week, is in [`WEEKLY_REPORT_0811_0818.md`](../WEEKLY_REPORT_0811_0818.md).

---

## 1. Accuracy improvements

| Change | Effect |
|---|---|
| Fixed the console encoding crash | **+2.2pp** on each of the two reasoning arms; `arcwise_full` 84.5% → **86.7%** |
| Disabled the two semantics-changing convention rules | Positive on the corrected gold |

### 1.1 The encoding crash

This machine's console is cp936. A database row containing a character it cannot encode
raised `UnicodeEncodeError`, the exception escaped, and the harness recorded it as the
model's own failure with `correct=False`.

**`bird_847`: the model queried correctly and got back `Räikkönen`. `ä` does not encode
in cp936, so the question was scored wrong.**

This was selective rather than random noise. The questions it killed are the ones whose
answers contain non-Latin characters, and they cluster by database — `card_games` 12%,
`formula_1` 8% — so it distorted the totals *and* every per-database or per-difficulty
breakdown built on them.

Fixed by `force_utf8_console()` in `shared/console.py`, which reconfigures stdout/stderr
at the stream level. Wired into all five agent entry points.

### 1.2 A criterion for convention rewriting

`count_no_distinct` strips `DISTINCT` from `COUNT` whenever the query joins. Its warrant
was 2377 applicable queries across 69 databases in the train gold, at **0.891 support**.

But the corrected gold uses `DISTINCT` in 130 of 498 questions where the original used it
in 83 — **a 57% increase**. That 0.891 was not measuring SQL semantics. It was measuring
how often the annotators forgot to write `DISTINCT`.

`bird_1505` asks "how many **customers**":

```
what the model wrote (right)  COUNT(DISTINCT T1.CustomerID)
what the harness made of it   COUNT(T1.CustomerID)
the original gold (also wrong) COUNT(*)
```

The rule's error and the gold's error cancelled, so the answer scored as correct.

**The criterion this produced** — it predicts the table below without running anything:

| Rule | What it changes | Verdict |
|---|---|---|
| `no_select_concat` | **Output shape** — splits into two columns, not one byte of data differs | Keep |
| `count_no_distinct` | **What the query computes** — COUNT switches from entities to rows | Disable |
| `superlative_order_limit` | Semantics, and it can drop WHERE conditions | Disable |

> Harness post-processing may normalise the shape of an answer. It may not change what
> the query computes.

The criterion lives in `SEMANTICS_CHANGING` in `build_sql_conventions.py`, not only in the
artefact: that script recomputes `enabled` from support, so editing the artefact alone
would let the rules come back on the next rebuild.

---

## 2. Where the 163 failures actually come from

Every failure read question by question — the question text, the hint, both SQL queries,
both execution results, and counter-queries against the database where a claim needed
testing. All 163 assigned, **150 of them by hand**.

**Result: gold defects 61, model errors 30.**

About 27 are SQL bugs that execution alone falsifies, independent of how one reads the
question:

| Mechanism | Instance |
|---|---|
| Missing parentheses, so AND/OR precedence collapses the condition | `bird_1265` gold returns 47; the correct answer is 35 |
| A text column sorted as if numeric | `bird_879` picks `'91.610'`; the real maximum is 257.32 |
| NULLs sort first under ASC and get picked | `bird_847` returns a driver with no recorded time |
| Join fan-out inflating an aggregate | `bird_198` gives 732.1; the correct value is 20.25 |

Published as a standalone page: `fault_ledger_163.html`.

---

## 3. Independent external validation

Cross-checked against the corrected gold released by a different group
(VLDB 2026, arXiv:2601.08778). The design separates two things that a naive comparison
conflates — a changed reference answer, and a fresh sample from a stochastic agent:

| Column | Model's answer | Scored against |
|---|---|---|
| A | original answers | original gold |
| B | **the same original answers** | corrected gold |
| C | answers from a new run | corrected gold |

| | Clean subset, 277 | **Gold-only corrections, 74** |
|---|---:|---:|
| A original answers × original gold | 81.9% | **50.0%** |
| B original answers × corrected gold | 87.7% | **71.6%** |
| C new run × corrected gold | 86.3% | 70.3% |
| **Attributable to the reference change** | **+16** | **+16** |
| Attributable to resampling | −4 | −1 |

On the 74 questions where neither the question text nor the hint was touched, **not one
byte of the model's SQL changed and the score went from 50.0% to 71.6%**.

Of the 26 questions that flipped from wrong to right, **19 are questions this project had
independently assigned to `gold`** in section 2 — reading the question plus counter-query,
an outside group's re-annotation, and an unchanged answer scoring differently all agree.

---

## 4. Which layer the error enters at

All 163 failures, mechanically assigned to the **first** layer of the SQL construction
pipeline that diverges from gold (sqlglot parsing, no LLM judgement). *First* is the point:
everything downstream of a wrong table is a foregone consequence, so only the first
divergence is worth intervening on.

| First layer to diverge | Questions | Share |
|---|---:|---:|
| Filter column | 35 | 21.5% |
| **Table selection** | **33** | **20.2%** |
| Join key | 24 | 14.7% |
| Aggregate function | 22 | 13.5% |
| Formatting / column order only | 11 | 6.7% |
| Used an extra table | 10 | 6.1% |
| Projection width / filter literal / grouping / ORDER BY LIMIT | 27 | 16.5% |

For the 33 table-selection failures, each table that gold needed and the prediction missed
was checked against whether it had been retrieved and offered to the model at the time:

| Case | (question, table) pairs |
|---|---:|
| Never retrieved | **0** |
| Retrieved but not selected | **0** |
| **Retrieved, selected, and the model did not use it** | **37** |

### What this says can be improved

1. **Improving schema retrieval is ruled out for this class.** 37 of 37 had the table in
   front of the model already; table recall is 98.4%. Further work on retrieval is wasted
   effort here.
2. **The filter column layer (21.5%) is where the model's real errors concentrate** — not
   table selection, which is the one that looks most like a method problem.
3. Of those 33 table-selection failures, **23 are cases where gold joins one more table
   than the model did**; the model wrote the simpler query. Cross-checked against the
   per-question adjudication: 20 gold defects, 2 genuine model errors.
   **A layer breakdown like this has to have gold defects removed before it is read**,
   or effort goes to the wrong layer.

---

## 5. Decomposing the "result shape" decision point (20 cases, each causally verified)

The second-strongest signal by information gain (55.3pp spread in accuracy):

| Sub-type | Questions | Representative |
|---|---:|---|
| **Superlative question, ties never checked** | **3–4** | `bird_1092` (8/8 deterministic), `bird_930` (10/10) |
| Original failure was chance; resampling recovers it | 4 | `bird_798`, `bird_483`, `bird_213`, `bird_149` |
| Gold itself has a logic bug | 3 | `bird_1322`, `bird_529`, `bird_1399` |
| Ties handled backwards | 2 | `bird_1135`, `bird_41` (`ROW_NUMBER` where gold wants `RANK`) |
| Yes/no question wants a YES/NO literal | 2 | `bird_473`, `bird_1399` |
| Output contract / half of a two-part question dropped | 1 | `bird_530` |
| Model over-complicated a simple question | 1 | `bird_637` |
| Concatenation vs separate columns | 1 | `bird_1011` |
| **Definite-article phrasing triggers `LIMIT 1`** | 1 | `bird_412` ("the card by artist X" matches 50 cards) |

### What this says can be improved

The one generalisable mechanism is **assuming uniqueness without checking for it**.
`bird_412` widens it from superlative questions to **any definite-article singular
phrasing**, which is a larger surface than it first appeared.

The intervention has to sit **in the model's own reasoning before it commits** — deciding
whether there really is only one row — rather than in a harness override after the fact.

---

## 6. Other fixes, new capability, and next steps

**Fixes**

| Item | Note |
|---|---|
| Encoding and credentials in `baselines/` | B1/B2 have been **unable to run** since a shared-resolver refactor; found this week |
| `no_select_concat` guard gap | Splitting a concatenation inside a subquery broke the outer reference, raising `no such column` |

**New scripts (8)**: sentence-level eight-category labelling, inline reasoning extraction,
two-arm comparison, gold-version three-column decomposition, first-wrong-sentence
location, corrected dataset construction, rescoring against corrected gold, failure triage.

**New corpus**: 12,618 sentences labelled with the Thought Anchors categories, captured
inline so each reasoning chain is tied to the answer it produced — 483 questions in one
arm, 461 in the other.

### Next week

1. Finish the chain: two runs of `clean-e0`, second runs of the rest
2. Fix the two remaining harness defects (exception misclassification, `evidence` being
   `None`) and rerun the three runs still depressed by them
3. Redo the reasoning-trace causal tracing on the corrected gold
4. The 14.9% recursion invocation rate is a precondition for the RLM paper, not a detail —
   settle it before measuring effects
