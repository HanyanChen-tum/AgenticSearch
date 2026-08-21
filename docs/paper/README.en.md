# Paper Outline: DB-RLM — How RLM's Three Mechanisms Pay Off in Text-to-SQL (~30 pages)

Version: v0.4 (2026-08-21) — **v0.1–v0.3 all withdrawn**, see the revision log at the end.
Status: **outline only, no prose**. Each section states what to say, which numbers to use, and where they come from.
Scope: **the full experimental line**, from the legacy baselines through the **five-layer chain and four ablation reruns of 2026-08-20**.

> English version of [README.md](README.md). The Chinese document is the one maintained during
> day-to-day work; this version preserves the same claims, numbers, and decisions.

> **All three earlier versions wrote the conclusion as negative. That was wrong.**
> With the five-layer chain finished, the correct conclusion is: **RLM's three mechanisms pay off
> very unevenly, but the main branch pays off enormously** (+13.4pp, far above the 1.4pp noise band).
> See §0.2 and the revision log.

---

## 0. Goal and Headline Result

### 0.1 Goal

> **Extend the three core mechanisms of Recursive Language Models (RLM) to structured database
> reasoning, and test them under the supervisor's constraint: the generator is fixed to
> `gpt-5.4-mini`, there is no fine-tuning channel, and only the execution environment, tools,
> verifiers, and precomputed knowledge may change.**
> — [experiment-plan/README.md](../experiment-plan/README.md) §0.1/§1, [analysis/README.md](../analysis/README.md) §2.3

RLM is **three** mechanisms, not recursion alone. Narrowing it to recursion is the mistake
`config_inventory` made and that v0.1–v0.3 of this outline repeated — read that way, the result
becomes "RLM contributes nothing," which is false.

### 0.2 Headline result: the five-layer chain (corrected dataset, 498 items, two runs per config)

| Layer | Config | What it adds | Mean | Increment | RLM mechanism |
|---|---|---|---:|---:|---|
| 0 | B1 | No method: single-shot generation | **70.5%** | — | — (floor) |
| 0' | B2 | + keyword table pre-filter | 67.5% | −3.0pp | — (negative control) |
| 1 | `clean-e0` | + agent tool loop | **83.9%** | **+13.4pp** | **② executable environment + ③ first half, self-improvement** |
| 2 | `e3-c-noconv` | + offline schema retrieval | **86.5%** | **+2.5pp** | **① programmatic exploration (weakened form)** |
| 3 | `e3-c-conv-rules` | + output post-processing | 86.9% | +0.4pp | **not RLM**; part of the system under test |
| 4 | `e3-c-recursive-db` | + depth-1 recursion | **87.2%** | +0.3pp | **③ second half, divide-and-conquer** |

**Measured noise band: 0.2–1.4pp** (four same-config repeats). Use **1.4pp** as the ruler.

> **Total gain 16.7pp, of which 13.4pp sits in layer 1.**
> This is **not** "RLM contributes nothing." It is **a very uneven return across three mechanisms,
> concentrated almost entirely in one branch** — a directional **positive** result, with independent
> evidence for why each branch does or does not pay.

### 0.3 The paper's three threads (set by the project itself, WEEK_PLAN §0)

| Thread | Claim | Role |
|---|---|---|
| **A — Mechanism attribution** | How the gain distributes across the three mechanisms, and why each branch lands where it does | **Main thread** (§5–§10) |
| **B — Structure vs. reasoning volume** | Layer 1 buys not "having tools" but "being able to try" — it **substitutes for** internal reasoning | Deepens A (§9) |
| **C — Convention mismatch** | One failure class is **immune to both** the method stack and the reasoning budget | Discussion (§11) |

Plus one independent methodological result: **measurement is half of this work** (§14–§16).

### 0.4 Terminology (settled 2026-08-20; binding for the whole paper)

The dividing line is not who wrote the code — it is **whether it can change the prediction**:

| Term | What it covers | Can it change the prediction? |
|---|---|---|
| **evaluation harness** | runner, manifest, transcripts, scoring | **No — if it can, that is a defect** |
| **system under test / agent scaffold** | tool loop, offline retrieval, recursion | Yes; must be ablatable |
| **output post-processing** | SQL convention rewriting (layer 3) | Yes; must be ablatable |

> ⚠️ **Writing red line**: never again call the SQL convention rewriting a "harness" rewrite.
> `harness_convention_rules_*.md` has been renamed
> [`sql_postprocessing_rules_2026-08-16.md`](../analysis/sql_postprocessing_rules_2026-08-16.md),
> and the adjudication verdict `harness改写` is now `后处理改写` (post-processing rewrite).

---

## 1. Claim and Contributions

### 1.1 The claim in one paragraph

> On a frozen commercial small model, RLM's three mechanisms return **very unevenly but in a clear
> direction**: **executable environment + self-improvement +13.4pp** (far above the 1.4pp noise band,
> 80% of the 16.7pp total), **programmatic exploration in its weakened form +2.5pp** (the full context
> store measured separately as no gain, because context utilization is only ~4%), and
> **divide-and-conquer +0.3pp** (inside noise; the two repeats have opposite signs, so no stable
> effect is measurable). One layer deeper: the main branch buys **not "having tools" but "being able
> to try"** — barely reasoning with a tool loop (72.2%) matches reasoning hard with one shot (70.5%),
> so the two are **substitutes**, not addends. And the **ruler** these numbers depend on is half the
> work: corrected gold moves config rankings by −11 to +9 places, and a console encoding defect once
> silently consumed 111 questions.

### 1.2 Five contributions

| # | Contribution | Type | Strongest evidence |
|---|---|---|---|
| **C1** | **How RLM's three mechanisms distribute their return**: +13.4 / +2.5 / +0.3pp, each with its own mechanistic explanation | **Positive result** (thread A) | Five-layer chain, corrected dataset, 498 items, two runs per config, 1.4pp noise band |
| **C2** | **Structure and reasoning volume are substitutes**: the tool loop buys the ability to try | Positive result (thread B) | minimal 72.2% ≈ B1 70.5%; lower reasoning → higher `llm_calls` (2.27→3.34); 10× the reasoning buys only 3.3pp |
| **C3** | **Two failure classes point in opposite directions, and one is immune to everything** | New finding (thread C) | 91 convention-class items, median 1619 reasoning tokens (0.80×) vs. 424 "other" at 4212 (2.07×); across layers 20→24→25→22 and across effort 22→13→16→12 — **unmoved** |
| **C4** | **The measurement contaminated the measured**: the evaluation harness recorded its own crashes as model errors | Methodology | cp936 encoding crash consumed 111 items, selectively hitting non-Latin answers; 84.5%→**86.7%**; the exception substring allowlist points the wrong way |
| **C5** | **The ruler decides the conclusion**: corrected gold reshuffles rankings, and the "ceiling" is a property of the ruler, not the model | Benchmark study | `e3-c-conv-rules` 1st→8th, `e3-c-recursive` 13th→2nd; the post-processing rules were fitting annotation defects |

### 1.3 What is explicitly not claimed

- Not a claim to a new BIRD SOTA
- **Not "RLM contributes nothing" or "all three mechanisms fail"** — that was the v0.1–v0.3 error
- Not that recursion is ineffective, only that **no stable effect is measurable on this dataset**
  (two repeats, opposite signs, n=64–74)
- Not that "true accuracy is higher" — against external corrected gold the net is −1 (§15)
- Not that layer 3's output post-processing is part of RLM — **it belongs to the system under test
  and must be ablatable** (§0.4)

---

## 2. Chapter Outline and Page Budget (30.0 pages total)

| Ch. | Title | Pages |
|---|---|---:|
| — | Abstract | 0.5 |
| **Part I — Setup** | | |
| 1 | Introduction | 1.5 |
| 2 | From RLM's three mechanisms to the five-layer chain | 1.5 |
| 3 | Related Work | 1.25 |
| 4 | Dataset, scoring basis, and measurement infrastructure | 2.0 |
| **Part II — Main result: mechanism attribution (thread A)** | | |
| 5 | The five-layer chain and the noise band | 2.5 |
| 6 | Mechanism ② + ③-first-half: executable environment and self-improvement (+13.4pp) | 1.5 |
| 7 | Mechanism ①: programmatic exploration — weakened +2.5pp, full form zero | 1.5 |
| 8 | Mechanism ③-second-half: divide-and-conquer (+0.3pp, unmeasurable) | 1.5 |
| 9 | Structure vs. reasoning volume: they are substitutes (thread B) | 2.0 |
| 10 | The non-RLM layer: output post-processing and its boundary criterion | 1.0 |
| **Part III — The structure of failure** | | |
| 11 | Two failure classes, opposite directions (thread C) | 2.0 |
| 12 | The timing law: before vs. after commitment | 2.0 |
| 13 | Evidence at the reasoning-trace level | 1.25 |
| **Part IV — Measurement itself** | | |
| 14 | Defects in the evaluation harness: the instrument contaminated the measurement | 1.5 |
| 15 | Change the ruler and the ranking changes: corrected gold and the 163-failure ledger | 2.75 |
| 16 | Withdrawal ledger and experimental discipline | 0.75 |
| **Part V** | | |
| 17 | Discussion | 1.0 |
| 18 | Threats to Validity / Limitations | 1.0 |
| 19 | Conclusion and Future Work | 0.5 |
| — | References | 0.5 |
| | **Total** | **30.0** |

---

## Part I — Setup

### 1. Introduction (1.5 pages)

- 1.1 The goal (§0.1), and why Text-to-SQL is the right test bed: it demands long-context
  organization, executable verification, and multi-stage decomposition at once — precisely what
  each of RLM's three mechanisms claims to solve
- 1.2 The constraint: frozen model, no fine-tuning channel. Not a resource limit — the research
  question itself
- 1.3 **The headline in one sentence** (§0.2 table) + **Figure 1**, the five-layer staircase
- 1.4 Five starting intuitions and where each ended up:

  | Intuition | Outcome | Section |
  |---|---|---|
  | Give the model tools so it can query and revise → more accurate | **Holds, +13.4pp** — 80% of the total gain | §6 |
  | Pre-select relevant tables and columns offline → more accurate | **Holds, +2.5pp** | §7 |
  | Recursive decomposition helps on hard questions | **Unmeasurable**: +0.3pp, the two repeats have opposite signs | §8 |
  | Auto-rewriting SQL into the reference style → more accurate | **Unmeasurable**, and it was fitting annotation defects | §10 |
  | The remaining failures are the model not thinking it through | **Only half right**: 91 convention-class items reason *less* than correct ones | §11 |

- 1.5 Contribution list (§1.2) and roadmap

### 2. From RLM's Three Mechanisms to the Five-Layer Chain (1.5 pages)

**This chapter is what makes the §5 table readable.**

- 2.1 The three mechanisms as originally defined ([analysis/README.md](../analysis/README.md) §2.3):
  ① programmatic reasoning/exploration (schema, descriptions, few-shot externalized into a context
  store the model searches, selects, and composes with code);
  ② executable environment (a REPL holding intermediate plans, candidate SQL, DB observations, with
  every key action executable and traced);
  ③ self-improvement and divide-and-conquer (Root revises its own SQL from observations; a depth-1
  Leaf **only** on complex questions)
- 2.2 **Each layer adds exactly one thing**, annotated with which mechanism it carries (§0.2, right
  column). **`e3-c-noconv` was built specifically so layer 4 has a clean comparison** — the earlier
  `e3-c-recursive` also switched off post-processing, binding two variables together
- 2.3 **Mechanism ① must be reported in both forms**: full (context store, model-driven retrieval)
  and weakened (offline deterministic retrieval). The former was tested separately as E5-A; the
  latter is layer 2 of this chain
- 2.4 **Mechanism ③ must be reported in both halves**: self-improvement (first half, inside layer 1)
  and divide-and-conquer (second half, layer 4)
- 2.5 The pre-registered reading rule: **measure the noise band before reading any difference**;
  anything below it is recorded as "unmeasurable," **never as "ineffective"**
- 2.6 Scope declaration and the gold-usage rule (gold only for offline scoring and post-run diagnosis)

### 3. Related Work (1.25 pages)

- 3.1 **RLM**: the source of the three mechanisms
- 3.2 Text-to-SQL and BIRD; the intent and the consequences of the `evidence`/hint field
  (foreshadows §15)
- 3.3 **SQRL** (BIRD Dev 70.6%): its inference-time architecture is essentially equivalent to ours;
  the difference is execution-based RL. **This project is the other half of that comparison**:
  same architecture + instructions only = ceiling
- 3.4 **Thought Anchors** (arXiv 2506.19143): reproduced here at the action level; sentence-level
  analysis is not possible on a closed API
- 3.5 **Benchmark annotation quality**: ACL 2024; **VLDB 2026 (arXiv:2601.08778), which audits the
  same 498 Mini-Dev items, reports 52.8% carrying annotation errors, and publishes the
  `Arcwise-Plat-SQL` corrected gold**; CIDR 2026
- 3.6 SIRIUS-SQL / Agentar ("generate + select" worth ~10.5 points) — used in §19

### 4. Dataset, Scoring Basis, and Measurement Infrastructure (2.0 pages)

- 4.1 **Three datasets, never mixed**: the original `bird_dev_500.json` (498 unique items), the
  **corrected `bird_dev_500_corrected_full.json` (498, used for the headline results)**, and the
  core197 adversarial subset (used by the historical experiments; **its accuracy is not comparable
  to the full set**)
- 4.2 **One common scorable set**: the 7 items that crashed on any arm are dropped from **every** arm
  (491 remain) — otherwise the layers are not judging the same questions
- 4.3 Official BIRD set-comparison scoring; the `correct` field in old result files used strict
  ordered comparison and must be rescored first
- 4.4 Provenance: immutable profiles, manifest + SHA-256, capability gate, structured observations.
  **`agent_config_sha256` is unreliable in both directions** (`max_iterations` does not enter the
  hash) — diff field by field before comparing (`scripts/audit_run_configs.py`)
- 4.5 **Measured noise band 0.2–1.4pp** (four same-config repeats). The earlier "1–2pp" estimate
  fails on **both** of its sources: one pair differed in `max_iterations` (8 vs. 15), the other had
  unequal crash counts. The **one clean repeat** agrees to 0.0pp in aggregate — **but flips 20 of 480
  items**. **Aggregate stability is not per-item stability; no per-item causal analysis may lean on
  that 0.0pp**
- 4.6 `temperature=0` never took effect (gpt-5-family models reject it; `litellm.drop_params` dropped
  it silently)
- 4.7 A conversion table across the three coordinate systems: legacy full-500, core197, corrected-498
  — **these three sets of numbers cannot be subtracted from one another**

---

## Part II — Main Result: Mechanism Attribution (thread A)

### 5. The Five-Layer Chain and the Noise Band (2.5 pages)

- 5.1 **Historical precursor** (one paragraph, for provenance): B1 55.20% → B2 51.60% →
  DB-RLM v4 64.20% (**+9.0**) → + reasoning high 69.20%.
  **This chain re-measured B1/B2 on the corrected dataset and redid that +9.0 as +13.4pp** — same
  phenomenon, cleaner ruler. Incidentally discovered: **B1/B2 had been unrunnable** since a shared
  resolver refactor, fixed only this week
- 5.2 **The main table** (§0.2) and the layer-increment table
- 5.3 **How the noise band was measured** (§4.5), and why it must precede any reading
- 5.4 **B2 is the negative control**: −3.0pp, agreeing in direction with the −3.6pp in findings.md —
  **that conclusion survived both the gold correction and the rerun**
- 5.5 Reading rule: +0.4pp and +0.3pp **cannot be called "ineffective," only "unmeasurable."**
  (A scale with ±1.4kg error reading 0.3kg lighter is not weight loss.)
- 5.6 **One scoring discrepancy still to reconcile**: layer 2→3 is recorded as **+1.4pp** on the
  corrected full 498 (7 items, 20 won / 13 lost) and **+0.4pp** on the chain's 491-item basis.
  Different denominators and different runs — **must be unified before writing** (→ §6, gap 6)

### 6. Mechanism ② + ③-First-Half: Executable Environment and Self-Improvement (+13.4pp) (1.5 pages)

**Claim**: this is RLM's main contribution on this task — 80% of the total gain.

- 6.1 What the layer adds: the agent tool loop — `db.execute` / `db.sample_values`, error and
  empty-result feedback, multi-turn observations, FINAL submission
- 6.2 +13.4pp, far above the 1.4pp band — **the only unambiguous large effect in the chain**
- 6.3 Consistency with the legacy-era +9.0 (different dataset and ruler, same direction)
- 6.4 **But what does it buy?** Three metrics show this agent **does not work by iterating**:
  `llm_calls` mean 2.3, `tool_actions` 1.8, `turns` 1.1 — **96% of items finish within 1–2 turns**.
  → leads into §9: it runs on long single-turn internal reasoning, and what the loop supplies is the
  ability to try
- 6.5 Interface to §12's timing law: **the loop works, but in an extreme binary** — recovery rate
  4–14% on correct items, **exactly 0 on incorrect ones**

### 7. Mechanism ①: Programmatic Exploration — Weakened +2.5pp, Full Form Zero (1.5 pages)

**Claim**: **organizing and delivering information works — but only when a deterministic program
does the selecting, and only when the information is something the model cannot derive itself.**

- 7.1 **Weakened form (layer 2, +2.5pp)**: full schema injection replaced by per-question
  deterministic retrieval (table/column descriptions, PK/FK graph, join cardinality and fan-out,
  value formats), with unselected tables reduced to a names-only index. Table recall **98.4%**
  (492/500), and the 8 items that missed a table scored *higher* (87.5%)
- 7.2 **Full form (E5-A/E5-B, zero gain)**: information equivalence 197/197, reachability 11/11,
  zero capability violations — **the mechanism was implemented correctly** — yet +108.9% tokens,
  +312.3% latency, accuracy flat. The root cause is structural: knowledge payload 726–2,572 tokens
  against a ~5,171-token prompt, i.e. **context utilization ~4%** — the premise "externalize because
  it does not fit" does not hold
- 7.3 **The gap between the two is the mechanism's boundary**: select deterministically for the model
  → works; let the model select for itself → only overhead remains
- 7.4 **A second boundary (E3-D)**: of 28 Query Mining slots, **zero** passed the cross-database
  gate; the best slot scored 0.906 precision against **the model's own 0.891** — 1.5pp stronger →
  **information that duplicates what the model can already do returns nothing, however rigorous its
  statistical validation**
- 7.5 A prediction that was overturned: we expected the model to skip reading; the opposite held — it
  called tools 5.36 times per item **to acquire information** and only 1.6 times **to verify SQL**

### 8. Mechanism ③-Second-Half: Divide-and-Conquer (+0.3pp, Unmeasurable) (1.5 pages)

**Claim**: **not "the effect was diluted by averaging" — there is no stable effect to find.**

- 8.1 +0.3pp on the full set, inside the noise band
- 8.2 **Both numbers must be reported** (otherwise it is selective reporting):

  | | Call rate | On items that used recursion | On the rest |
  |---|---:|---:|---:|
  | run1 | 74/498 = 14.9% | **+2.7pp** (n=74) | −1.2pp |
  | run2 | 64/498 = 12.9% | **−3.1pp** (n=64) | +1.4pp |

  **The two repeats have opposite signs**; at n=64–74, ±3pp is two or three questions
- 8.3 **And the cost went up**: the recursion arm reasons more (mean 4346 vs. 3259, max 54206 vs.
  25137). **Recursion does make the model think more; the accuracy contribution is +0.3pp**
- 8.4 Call rate is stable at **12.9%–14.9%**. The previously recorded "3.8%–15.6%, nearly 4× variation
  at the same config" was traced by the config audit to **a different prompt**
  (`recursive-leaf-protocol-v1`) — not same-config variance
- 8.5 **Why the other recursion form (structural constraint) was not rebuilt**: a zero-cost detector
  found only **1–2 targets** on the cleanest available failure population (4 of 118 stable failures
  in the original experiment, ~3.4%). **Corrected gold did not solve the target-sparsity problem**,
  because the empty-result trigger is an execution-level signal, independent of gold quality
- 8.6 **Explicitly not doing**: no extra configs or prompt tuning to rescue the recursion branch.
  The +0.3pp was measured with two repeats against a 1.4pp band; adding arms only raises the chance
  of a lucky number — **that is not discovery, that is picking data**

### 9. Structure vs. Reasoning Volume: They Are Substitutes (thread B) (2.0 pages)

**This chapter deepens §6 and is the paper's second positive result.**

- 9.1 **Reasoning-effort sweep** (same config `e3-c-conv-rules`, only `reasoning_effort` varies):

  | effort | Accuracy | Median reasoning tokens | `llm_calls` | Median latency |
  |---|---:|---:|---:|---:|
  | minimal | **72.2%** | 0 | 2.87 | 4.3s |
  | low | 83.7% | 232 | 3.34 | 6.5s |
  | medium | 85.9% | 864 | 2.49 | 9.1s |
  | high | 87.0% | 2262 | 2.27 | 14.7s |

  **The first 232 reasoning tokens buy +11.5pp; a further ~10× buys only 3.3pp. Returns fall sharply**
- 9.2 **The key comparison**: `minimal` at **72.2%** (full tool loop, barely reasoning) ≈ B1 at
  **70.5%** (single-shot, high reasoning). → **the agent loop and internal reasoning are largely
  substitutes for one another, not two things that add up**
- 9.3 **Mechanistic evidence**: the less it reasons, the more it calls (2.27 → 3.34) — thinking less
  in the head is compensated by trying more by hand. **The substitution is directly observable**
- 9.4 **Which re-reads §6's +13.4pp**: what it buys may not be "tools" but **"being able to try"**
- 9.5 **Stated honestly**: this is the thread **most likely to fall over**. 72.2% vs. 70.5% is only
  1.7pp, right at the edge of the band, and it is a **cross-config, single-run** comparison. The clean
  version is a 2×2 grid with `clean-e0 × minimal` (**not yet run, §6 gap 2**). If that cell lands
  above 80%, **the substitution claim fails and this thread is withdrawn**

### 10. The Non-RLM Layer: Output Post-Processing and Its Boundary Criterion (1.0 page)

- 10.1 **It is not part of RLM, and it changes the prediction, so it must be ablatable** (§0.4)
- 10.2 The effect is unmeasurable (+0.4pp), but **the mechanistic explanation matters more than the
  effect size**: it was built precisely to fix convention-class failures, and it moved them from 24
  to 25 — **not one question** (§11)
- 10.3 **The criterion: reshaping output is allowed, changing semantics is not**

  | Rule | What it changes | Verdict | Net on external corrected gold |
  |---|---|---|---:|
  | `no_select_concat` | Output shape (split into two columns; not one byte of data changes) | Legitimate | **+8** |
  | `count_no_distinct` | Computational semantics (COUNT's object goes from entities to rows) | Illegitimate | **−16** |
  | `superlative_order_limit` | Computational semantics, and it drops WHERE conditions | Illegitimate | −2 |

  **The criterion predicts this table without running the experiment**
- 10.4 How `count_no_distinct` went bad: corrected gold raises DISTINCT usage from 83 to 130 items
  (+57%). **That 0.891 support was not measuring SQL semantics — it was measuring annotators
  systematically omitting DISTINCT.** `bird_1505` three ways: the model wrote it correctly →
  post-processing broke it → the original gold was broken the same way → **two errors cancelled and
  it scored "correct"**
- 10.5 Disposition: both semantics-changing rules disabled, and the criterion written into
  `build_sql_conventions.py` as `SEMANTICS_CHANGING` (editing only the artifact would let the next
  rebuild revive them)

---

## Part III — The Structure of Failure

### 11. Two Failure Classes, Opposite Directions (thread C) (2.0 pages)

**One of the most valuable new findings of this round.**

- 11.1 Triage results (recomputable basis — only facts that can be re-executed, never labels):

  | Class | n | Median reasoning tokens | vs. correct |
  |---|---:|---:|---:|
  | **Convention** (ties / under_projection / distinct_repair) | 91 | **1619** | **0.80× (lower)** |
  | Row-set | 34 | 4434 | 2.18× |
  | Other | 424 | 4212 | 2.07× |
  | Correct | 3414 | 2036 | 1.00× |

- 11.2 **The two classes point in opposite directions**:
  - **"Doesn't know it's wrong"** (convention): short reasoning, first-pass, confident. The question
    was effectively answered correctly; it lost on the reference answer's writing conventions
    (ties, `COUNT(DISTINCT)`, one column or two)
  - **"Didn't think it through"** (the 424): long reasoning, repeated weighing — genuine semantic
    difficulty
- 11.3 **The method stack only kills the second**: "other" goes 132 → 95 across layers, while
  convention goes 20 → 24 → 25 → 22 (**unmoved**)
- 11.4 **The reasoning budget only kills the second too**: "other" 116 → 52 across effort levels,
  while convention goes 22 → 13 → 16 → 12
- 11.5 **In one line**: everything we built helps the model *think it through*; nothing helps it
  *guess the grader's habits*
- 11.6 **A confound that must be controlled**: unstratified, wrong answers reason longer — but
  difficulty itself correlates with reasoning volume (simple 1532 / moderate 2245 / challenging
  3286). Stratified by difficulty, the challenging tier **reverses** on one arm (0.82×) with only
  9–22 items per cell — **a lead, not a conclusion**, and the same shape as the project's earlier
  "wanting to verify is the strongest failure signal," which turned out to be a difficulty proxy
- 11.7 **Not yet decomposed**: the 424 "other" is a mixed class; existing recomputable tests cover
  only 25% of it. Splitting it is thread A's largest evidence gap (§6, gap 3)

### 12. The Timing Law: Before vs. After Commitment (2.0 pages)

**Claim**: mechanism ③'s first half (self-improvement) works — but only *before* commitment.

- 12.1 **Seven interventions, seven negative results**:

  | # | Mechanism | Result |
  |---|---|---|
  | 1 | E1 strict verified-final | 0 recovered / 3 regressed, cost doubled |
  | 2 | E4-A QueryPlan | −6 items, **its own target category got worse** |
  | 3 | Literal-verification nudge | N=44, 0 recovered / 4 regressed |
  | 4 | JOIN-minimality hint | N=26, v1 +1 / v2 0 |
  | 5 | E6 empty-result feedback re-submission | statistically indistinguishable from plain retry |
  | 6 | LIMIT-1 multi-value gated recheck | 1 recovered / 9 broken = **−8** |
  | 7 | **Tool-visibility nudge** (new, 08-18) | ctl 330 vs. trt 326, **−4**; the hypothesis was falsified four ways |

  > ⚠️ Item 7 is **a different kind of intervention** — not post-hoc rechecking, but changing the
  > model's belief about its own capabilities. Three historical documents count these differently
  > (two say "five times" with different membership; one says "the sixth"). **Merged, there are 7
  > independent experiments, 6 of them post-hoc rechecking. Unify the count before writing**
  > (→ §6, gap 5)
- 12.2 **The unified explanation**: wrong→correct recovery on failing items is **exactly 0 across
  three runs**; **over 99% of failing items never once executed a result matching gold** — the loop
  has nothing to rescue; and the model **does not adapt its exploration** (1.22 vs. 1.38 executions)
- 12.3 **91.1% of failures are fixed at the first draft** (turn-by-turn replay, every SQL version
  actually executed): 143/157. On average 2.3 turns and 13.1 reasoning segments of further probing
  **almost never change the outcome**
- 12.4 **The timing law stated**: grounding *before* commitment works (+13.4pp / +9.0); rescue
  *after* an answer exists does not (7 net-negative results)
- 12.5 **Item 7's real side effect**: the added sentence shortened first-turn reasoning by **22%**
  (51.0 → 39.8 sentences per item) with **accuracy unchanged** → that reasoning was redundant,
  re-weighing something already settled. This corroborates §9's substitution result
- 12.6 **An untested alternative explanation**: every failed prompt mechanism used **vague wording**;
  two observations show behavior changes sharply when wording becomes concrete (violations 19→4;
  leaf DB-query rate 0%→94%). **"The mechanism fails" and "the wording fails" have not been separated**

### 13. Evidence at the Reasoning-Trace Level (1.25 pages)

- 13.1 Method and scale: Responses API with `reasoning.summary=detailed`, 496/498 items captured;
  turn-level counterfactual resampling on 20 cases
- 13.2 **Methodological boundary**: no sentence-level resampling (hidden reasoning state is not
  editable) and no attention analysis (closed API)
- 13.3 **Sentence-level eight-class labeling: correct and incorrect answers have nearly identical
  reasoning composition** (max difference 2.5pp) → **there is no targetable "wrong thinking pattern"**
- 13.4 But failing items **express uncertainty 15.8pp more often** (38.7% vs. 22.9%) — **the model
  knows when it is guessing**
- 13.5 **Two first-error-sentence localization methods** (for the next round): A, first committing
  sentence (10-item consistency check, 8/10 hits, but biased early); B, prefix-continuation
  resampling (`bird_48` agrees three ways and surfaces a layer manual reading misses).
  **Neither produces conclusions until the human agreement rate exists**
- 13.6 **A reverse-causation trap**: "wanting to verify" is the strongest failure signal (−17.3pp),
  but that runs hard question → uncertainty → says it wants to verify. Same trap as "high call count"

---

## Part IV — Measurement Itself

### 14. Defects in the Evaluation Harness: The Instrument Contaminated the Measurement (1.5 pages)

**Claim**: the defining constraint on an evaluation harness is that it **must not change the
prediction**. This project violated that three times, and each violation disguised itself as a
property of the system under test.

- 14.1 **Defect one: console encoding crash (fixed)**. `stdout.encoding` is cp936 on this machine,
  and two unguarded `print()` calls emit database rows; a non-Latin character raises
  `UnicodeEncodeError` → recorded as a model error with `predicted_sql=""`, persisted **as a completed
  record**, so resume never retries it. **It was selective**: it hit items whose answers contain
  non-Latin characters, concentrated by database (`card_games` 12%, `formula_1` 8%) — typical
  casualties `Räikkönen`, `São Paulo`, `갈등`. **So it distorted both the total and every stratified
  analysis.** Fix: `force_utf8_console()` in `shared/console.py`
- 14.2 **Defect two: exception misclassification (still unfixed)**. A **substring allowlist on
  exception class names** separates infrastructure failures from model failures, and **it points the
  wrong way** — it enumerates what to retry and then defaults to "everything else is a genuine model
  failure." Repository-wide audit: `NotFoundError` 200, `UnicodeEncodeError` 66, `BadRequestError` 33,
  `AttributeError` 6, all recorded as model errors; **the only correctly classified one is
  `MaxIterationsError`**
- 14.3 **Defect three: `evidence=None` (fixed)**. The corrected dataset wrote `None` where the
  original had an empty string, and `.get(k, "")` only supplies the default when the **key is
  missing** → `AttributeError`. **Fix the consumer, not the data source** — regenerating the dataset
  changes `dataset_sha256`, failing every manifest check on the chain and invalidating finished runs
- 14.4 **`BadRequestError`, 37 records, now diagnosed**: Azure content-safety false positives
  (`card_games` dark-fantasy flavor text, `thrombosis_prediction` medical terminology) — **neither
  rate limiting nor context overflow**, and concentrated in the same databases as the encoding defect.
  Disposition: exclude from scoring, **do not retry** (the same prompt will very likely be refused
  again)
- 14.5 **Resulting corrections**: `arcwise_full` 84.5% → **86.7%**; the two reasoning-capture arms
  each **+2.2pp** (rc_ctl 87.0→89.2, rc_trt 87.7→89.9)
- 14.6 **Why this deserves its own chapter**: this is not "there was a bug." It **violates the
  defining constraint of an evaluation harness**, which is also why it was so hard to find —
  **it disguises itself as a property of the thing being measured**

### 15. Change the Ruler and the Ranking Changes: Corrected Gold and the 163-Failure Ledger (2.75 pages)

- 15.1 **All 163 failures assigned responsibility** (150 read question by question):
  gold **61 (37.4%)** / question ambiguity 35 / **model 30 (18.4%)** / both 16 / scoring basis 9 /
  **post-processing rewrite 6** / unscorable 4 / infrastructure 1 / missing schema 1 →
  **gold : model ≈ 2.0 : 1**
- 15.2 The six reusable mechanisms behind gold defects; the most persuasive pair, `bird_1404` /
  `bird_1422` (same database, same two columns, **gold picks the opposite column from the question
  text both times**)
- 15.3 **The external independent corrected version — the most important self-correction here**:
  original gold 335/498 = 67.27%, independent corrected gold 334/498 = **67.07%**. The two versions
  differ semantically on 132 items (26.5%), yet **38 newly correct, 39 newly wrong, net −1**.
  → **"annotation noise was depressing our score" does not hold.** This ledger audits only failures,
  so it cannot see the half where a broken gold *gave* us a point — **a structural bias in the method**
- 15.4 **Discriminative gradient**: of the 61 I judged `gold`, **84%** were independently corrected by
  the other team; `both` 81%, `question ambiguity` 46%, `model` **25%**, and items we already answered
  correctly **12%**
- 15.5 **Circularity, quantified**: my own corrected gold scored 61/61; the external corrected gold
  scores only **29/61** — **about half of the gold I wrote was fitted toward the model's answer**
- 15.6 **Rankings reshuffle under the corrected ruler** (278-item clean subset):

  | Config | Original gold | Corrected gold | Rank |
  |---|---:|---:|---|
  | `e3-c-conv-rules` (the former "current best") | 86.3% | 87.0% | **1st → 8th** |
  | `e3-c-recursive` | 81.6% | **90.3%** | 13th → **2nd** |
  | `clean-e0` (baseline) | 80.1% | 87.0% | 15th → 10th |

  **The "current best" ties the baseline under the corrected ruler** — a substantial part of its lead
  came from fitting bad gold better. The external paper reports rank shifts of −9 to +9; this project
  reproduces **−11 to +9** internally, the same magnitude
- 15.7 **The "68.9% ceiling" framing is void**: it assumed a fixed ruler.
  **The ceiling is a property of the ruler, not the model**
- 15.8 **Four historical ablations rerun on the corrected dataset** (08-20):

  | Experiment | Status |
  |---|---|
  | Hint ablation | **Direction confirmed** (removing hints is a net loss; do not delete), **magnitude shrank from −13.5pp to −5.0pp**; single run |
  | Referential ambiguity | **3 of 5 now answered correctly** with no manual rewrite (the external correction converged independently on the same disambiguation); 2 of 5 are new samples; `bird_1529` **falsified the "gold defect" guess** |
  | E6 structural-constraint recursion | 1–2 targets; **judged not worth rebuilding** |
  | Prompt-taught conventions | run1 looked like a reversal (39 violations vs. 45), **run2 falsified it** (+3; mean of the two −1.5, essentially a tie). **The original "prompt-taught conventions do nothing" conclusion stands** |

  > The fourth is a clean example of **what repeat runs are for**: run1's reversal appeared to
  > undermine the controlled contrast behind "writing conventions into the prompt does nothing"
  > (originally 24 vs. 25); run2 falsified it immediately — opposite signs, mean −1.5, matching the
  > original experiment in both direction and magnitude. **It falsified an interesting but
  > untrustworthy single result rather than confirming it.**
- 15.9 **Mechanical adjudication falsified for the fourth time**: the two directional answer-level
  rules were reversed on **6 of 11** items on review → **never use them again**

### 16. Withdrawal Ledger and Experimental Discipline (0.75 pages)

- 16.1 The withdrawal list (§5 ledger; the five most important in the body, the full table in
  Appendix B)
- 16.2 **Experimental discipline** (each rule fixed by a near-miss wrong conclusion):
  1. Credentials through `resolve_llm_config`, paths through runner constants — never derived ad hoc
  2. **Exceptions must never be swallowed as result values**; infrastructure failures are accounted
     separately (§14.2 is the largest violation of this)
  3. **Trigger-set experiments repeat at least 3 times**
  4. **Prefer metrics that bypass scoring** (violation counts, call rates, table recall, reasoning
     volume)
  5. **Manifests record the effective value, not the requested one**; **`cfg_sha` is unreliable in
     both directions — diff field by field before comparing**
  6. **Measure the noise band before reading any difference**; below it, say "unmeasurable"
  7. **Never draw conclusions from an LLM labeler** (this project's LLM judge scored 2/15
     historically; mechanical adjudication has been falsified four times)
- 16.3 **Any judgment of "are these two SQL statements equivalent" or "is this gold wrong" must be
  settled by actually executing and comparing result sets**

---

## Part V

### 17. Discussion (1.0 page)

- 17.1 **Why the gain concentrates in mechanism ②**: what the model lacks is neither knowledge nor
  tools, but **the opportunity to try**. §9's substitution shows the loop and internal reasoning are
  two forms of the same thing; §12 shows that trying only has value **before commitment**
- 17.2 **Why mechanism ①'s full form and mechanism ③'s second half do not pay**: their premises do
  not hold on this task — context utilization ~4% (nothing fails to fit) and target density 1–3%
  (too few decomposable sub-problems). **This is a property of the task, not of the implementation**,
  which also predicts when they would come back: mechanism ① with larger schemas and longer evidence;
  mechanism ③ only on an evaluation set with higher capability-failure density
- 17.3 **Against SQRL**: same architecture + training = breakthrough; same architecture +
  instructions only = ceiling
- 17.4 **For benchmark users**: mechanism gains must first have dataset defects and annotation
  alignment subtracted out. **The correctness of the benchmark precedes any tuning** — the same
  change is −2 on bad gold and +20 on good gold
- 17.5 **Convention-class failures need a different instrument** (thread C's landing point): they are
  immune to both the method stack and the reasoning budget

### 18. Threats to Validity / Limitations (1.0 page)

1. **Each reasoning-effort level ran once**; medium 85.9% vs. high 87.0% is 1.1pp, inside the band
2. **§9's substitution is a cross-config single-run comparison**, 1.7pp against the band;
   `clean-e0 × minimal` has not been run
3. **The 424 "other" failures are not decomposed**; recomputable tests cover only 25%
4. **Aggregate stability is not per-item stability**: 20 of 480 items flip
5. **Exception misclassification is unfixed**; fixing it shifts the denominator of every published
   number
6. **Sampling was never pinned**; `temperature=0` was silently dropped
7. **The ledger audits only failures**, so it cannot see gifted points (quantified as 39 items)
8. **No extrapolation to other datasets or splits**: three databases account for 38% of the 163
   failures, and their gold quality is below average
9. **Vague vs. concrete wording has not been separated** (§12.6)
10. **Legacy-era runs are not reproducible** (no manifest, no trace; the result files do not even
    carry `agent_profile`)
11. Three runs are still depressed by the encoding defect and not yet rerun:
    `e3_c_rules_reasoning`, `e3_c_conv_rules_v2`, `e3_c_semantic`

### 19. Conclusion and Future Work (0.5 pages)

Three closing sentences: the distribution of mechanism gains / the substitution result / the ruler
decides the conclusion. Two items of future work: **multi-candidate generation with execution-feedback
selection** (Agentar's ablation values "generate + select" at ~10.5 points; this project has taken
none of it), and **building an evaluation set with higher capability-failure density** — the only
precondition under which mechanism ③ can be tested fairly.

### References (0.5 pages)

RLM / SQRL / Thought Anchors / BIRD / arXiv:2601.08778 (VLDB 2026) / ACL 2024 / CIDR 2026 /
SIRIUS-SQL / Agentar. **Citation details still to be filled in** (→ §6, gap 7).

### Appendices (not counted in the 30 pages)

- **A** Full experiment ledger (per run: profile, run_id, field-by-field config, accuracy, basis)
- **B** Complete withdrawal table
- **C** Per-item responsibility ledger for all 163 failures
- **D** Train-set mining and cross-database gating for the three post-processing rules
- **E** Full record of near-miss wrong conclusions

---

## 3. Figures and Tables

| # | Figure | Source | Status |
|---|---|---|---|
| 1 | **Five-layer staircase** (with the 1.4pp noise band) | `five_layer_chain_results` §1 | To draw |
| 2 | **Mechanism → layer → increment** map (the paper's skeleton) | §0.2 | To draw |
| 3 | Reasoning effort vs. accuracy, with `llm_calls` overlaid inversely | ibid. §4 | To draw |
| 4 | Reasoning-volume distribution of the two failure classes | `triage_chain_*.json` | Data exists |
| 5 | Convention-class counts flat across layers and effort levels | ibid. §3/§4 | Data exists |
| 6 | The recursion sign flip across two repeats (n=74 / n=64) | ibid. §1 | Data exists |
| 7 | Config ranking migration before/after corrected gold | `reasoning_trace_findings_2026-08-18` §2.2 | Data exists |
| 8 | Two-gold rescoring migration (38 newly correct / 39 newly wrong) | `rescore_vs_arcwise.json` | Data exists |
| 9 | Discriminative gradient (84/81/46/25/12%) | ibid. | Data exists |
| 10 | Selective incidence of the encoding defect by database | `harness_defects` §1 | Data exists |
| 11 | 91.1% fixed at the first draft | `error_origin_dev500.json` | Data exists |
| 12 | The three post-processing rules under both golds | `rescore_vs_arcwise.json` | Data exists |

Fifteen tables: T1 five-layer chain · T2 layer increments · T3 the four same-config repeats ·
T4 mechanism mapping · T5 recursion on both bases · T6 effort sweep · T7 failure class × reasoning
volume · T8 convention class across layers and effort · T9 the three-rule criterion ·
T10 three harness defects · T11 corrections · T12 the 163-failure ledger · T13 ranking reshuffle ·
T14 four ablation reruns · T15 withdrawal ledger

---

## 4. Claim → Evidence → Source Index

| Claim | Key numbers | Source |
|---|---|---|
| **Five-layer chain, noise band, reasoning volume, two failure classes, effort sweep** | +13.4/+2.5/+0.4/+0.3 | [week_2026-08-18/five_layer_chain_results_2026-08-19.md](../analysis/week_2026-08-18/five_layer_chain_results_2026-08-19.md) (**headline result**; English version in the same folder) |
| The three threads and next week's plan | — | [week_2026-08-18/WEEK_PLAN_2026-08-20.md](../analysis/week_2026-08-18/WEEK_PLAN_2026-08-20.md) |
| Three harness defects, corrections, noise-band falsification | 84.5→86.7 | [week_2026-08-18/harness_defects_2026-08-18.md](../analysis/week_2026-08-18/harness_defects_2026-08-18.md) |
| Field-by-field config audit of 66 runs | cfg_sha unreliable | [week_2026-08-18/run_config_audit_2026-08-18.md](../analysis/week_2026-08-18/run_config_audit_2026-08-18.md) |
| Four ablation reruns (including the reversal and its falsification) | 39 vs 45 → mean −1.5 | [week_2026-08-18/reruns_2026-08-20.md](../analysis/week_2026-08-18/reruns_2026-08-20.md) |
| Question-text and gold changes across the 7 ambiguity items | 3/5 correct | [week_2026-08-18/disambiguation_recheck_2026-08-20.md](../analysis/week_2026-08-18/disambiguation_recheck_2026-08-20.md) |
| Terminology boundary, the week's three conclusions | — | [week_2026-08-18/INDEX.md](../analysis/week_2026-08-18/INDEX.md) |
| Ranking reshuffle, ceiling voided, 7th intervention, sentence-level labeling | −11~+9 | [reasoning_trace_findings_2026-08-18.md](../analysis/reasoning_trace_findings_2026-08-18.md) |
| Chain design and the B1/B2 floor | 70.5/67.5 | [config_inventory_2026-08-17.md](../analysis/config_inventory_2026-08-17.md) §6 |
| Post-processing criterion, +18, iter15 replication | −16/+8/−2 | [sql_postprocessing_rules_2026-08-16.md](../analysis/sql_postprocessing_rules_2026-08-16.md) |
| 163-failure ledger, external gold cross-check | 61:30 | [failure_adjudication_final_2026-08-16.md](../analysis/failure_adjudication_final_2026-08-16.md) |
| 91.1% fixed at first draft | 143 | [error_origin_chain_2026-08-16.md](../analysis/error_origin_chain_2026-08-16.md) |
| Mechanism definitions, full per-experiment record | — | [analysis/README.md](../analysis/README.md) §2.3, [experiment-plan/README.md](../experiment-plan/README.md) |
| ReAct loop recovery, E5-A, E6, disambiguation, hints | 0/120, 4% | [analysisDetail/](../analysis/analysisDetail/), [rootcause/](../analysis/rootcause/) |
| Legacy arc, ensemble law, the leakage incident | 55.2→69.2 | [docs/findings.md](../findings.md) |

---

## 5. Citable / Non-Citable Numbers

### Not citable (withdrawn, falsified, or superseded)

| Number / statement | Why |
|---|---|
| **"Argue the contribution of RLM recursion" as the thesis** | Narrows RLM to the second half of mechanism ③; read that way it yields the false "RLM contributes nothing" |
| **"All three mechanisms fail"** | The error in v0.1–v0.3 of this outline. Mechanism ② +13.4pp, mechanism ① weakened form +2.5pp |
| **The word "harness" for the SQL rewriting** | Renamed "output post-processing"; it changes the prediction and belongs to the system under test |
| **Noise band "1–2pp"** | Both sources fail (`max_iterations` 8 vs. 15; unequal crash counts). Measured: **0.2–1.4pp** |
| **Recursion call rate "3.8%–15.6%, nearly 4× same-config variation"** | The 4.0% run used a different prompt. Measured stable at **12.9%–14.9%** |
| **`arcwise_full` 84.5%** | Depressed by the encoding crash. Corrected to **86.7%**; rc_ctl 87.0→89.2, rc_trt 87.7→89.9 |
| **The "68.9% ceiling" framing** | Assumes a fixed ruler. The ceiling is **a property of the ruler** |
| **"`e3-c-conv-rules` is the current best"** | 1st → 8th under the corrected ruler; ties the baseline |
| **Hint ablation −13.5pp** | **−5.0pp** on the corrected dataset (direction still holds) |
| **Every result from before 2026-07-04** | Retriever leakage; ~73% of pool items retrieved their own gold |
| **The `correct` field in old result files** | Strict ordered comparison, not official set comparison |
| **Every error distribution from before the classifier fix** | Schema/Join was systematically undercounted (38 → 97) |
| **E4-A "aggregation improved, dragged down by Schema"** | The direction is reversed |
| **"Gold defects are 64%" (08-08, old config)** | Not reproduced; independently measured at 44% on the strict basis this round |
| **80.7% / 68.64% / gold 72:26 / the 74% ceiling** | See Appendix B; reasons unchanged |
| **"Static patterns are harmful" (e3-ac −7)** | Only 1 item beyond noise |
| **The `temperature` field in old manifests** | Requested value ≠ sent value |
| **The directional answer-level rules** | 6 of 11 reversed on review |
| **337/500 = 67.40%** | The denominator should be 335/498 |
| **"Legacy led because of db_hints"** | Refuted by per-database accuracy |
| **"The 15pp gap on formula-hint items is caused by the hints"** | Hints are a difficulty marker |

### Open, pending confirmation (**not to be used as established**)

| Statement | Status |
|---|---|
| Is layer 2→3 +0.4pp or +1.4pp (§5.6) | Different denominators and runs; must be unified |
| §9's substitution result | Cross-config, single-run comparison; 1.7pp against the band |

### Citable (state the basis)

- **Every number in the five-layer chain** (corrected dataset, 491 common scorable items, two runs
  per config, 1.4pp noise band)
- **The reasoning-effort sweep** (same config, one run each; `reasoning_tokens` as a continuous
  quantity is reliable, 1pp-level accuracy differences are not)
- 67.27% (original gold, 498) / 67.07% (external corrected gold) / 86.7% (corrected gold, after the
  encoding fix)
- **Every mechanism metric that bypasses scoring** — violation counts, call rates, 98.4% table
  recall, 37/37 retrieved-but-unused, 110 tool events with 0 violations, 197/197 information
  equivalence, reasoning volume and `llm_calls`. **Prefer these**

---

## 6. Work Still Missing Before Writing

| # | Gap | Why it blocks | Cost |
|---|---|---|---|
| 1 | **Fix the exception misclassification** (defect two) | It sits on the scoring path; fixing it shifts every published denominator, so it must be done once and propagated | Half a day |
| 2 | **The `clean-e0 × minimal` cell** | §9's substitution rests on a cross-config single-run comparison; **the most likely thing to fall over** | 2–3h |
| 3 | **Decompose the 424 "other" failures** | Thread A's core evidence gap; recomputable tests cover only 25%. Read 30 by hand as a baseline first; below ~80% agreement it cannot carry statistics | 2–3 days |
| 4 | **A repeat each at low and medium effort** | Otherwise it is three points, not a curve | 3–4h |
| 5 | Unify the count of verification-class interventions | Three documents, three counts; merged it is 7 independent experiments | 30 min |
| 6 | Unify §5.6's +0.4 / +1.4pp | One layer, two numbers | 30 min |
| 7 | Fill in the references | RLM / SQRL / SIRIUS-SQL / Agentar / ACL 2024 / CIDR 2026 exist only as paraphrase | 1h |

---

## 7. Decisions Needed From You

| # | Question | Recommendation |
|---|---|---|
| 1 | **Thread A alone, or A+B?** | **A as the main thread, B deepening it, C in discussion** (matching WEEK_PLAN §0). B depends on gap 2; if the substitution result fails, drop B — A is unaffected |
| 2 | Is the reasoning corpus (5–12h overnight) still worth spending on? | **Not yet if you take A+B** — neither "recursion is unmeasurable" nor "structure vs. reasoning volume" depends on sentence-level traces |
| 3 | Format: Praktikum report / thesis chapter / conference submission? | 30 pages is thesis-chapter scale; cutting to ~9 pages for a conference means keeping only C1 + C2 |
| 4 | Chinese or English? | For Harshal / the Praktikum, **English** (the headline results document already has an `.en.md` version) |
| 5 | What does "baseline 3" refer to? | The repository has only B1/B2 as named baselines; the chain's layer 0 is B1 and layer 0' is B2 |

---

## Revision Log

- **v0.4 (2026-08-21)**: **Headline result updated throughout.** The three earlier versions had not
  read `docs/analysis/week_2026-08-18/` (five-layer chain, harness defects, config audit, four
  ablation reruns, ambiguity recheck) or `reasoning_trace_findings_2026-08-18.md`. Those documents
  **overturn the negative claim**: with the chain complete, RLM mechanism ② plus the first half of ③
  contribute **+13.4pp** (80% of the 16.7pp total), mechanism ①'s weakened form +2.5pp, and
  mechanism ③'s second half +0.3pp (inside noise). The claim therefore moves from "all three
  capabilities fail" (v0.2) and "the dividing line runs inside each capability" (v0.3) to
  **mechanism attribution: a very uneven return in a clear direction** — a **positive** result.
  Also folded in: the terminology correction (harness → output post-processing), the 0.2–1.4pp noise
  band, the two opposite failure classes, the effort sweep and the substitution result, the three
  harness defects, the ranking reshuffle under corrected gold, and the four ablation reruns
  (including the prompt-convention reversal that run2 then falsified).
- **v0.3 (2026-08-17)**: withdrawn. Claimed the dividing line ran inside each capability
  (deterministic delivery vs. model-driven use). Half right, but **it contradicts layer 1** — the
  tool loop is model-driven and is the largest gain. The real dividing line is **timing**
  (before/after commitment), not who exercises the capability.
- **v0.2 (2026-08-17)**: withdrawn. Wrote the conclusion as "all three capabilities fail."
- **v0.1 (2026-08-17)**: withdrawn. Took the timing law as the thesis; that is a result, not the goal.
