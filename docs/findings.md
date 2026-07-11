# Findings Ledger — what works, what fails, and why

Every claim below was measured on BIRD mini-dev with the official protocol,
same generator (gpt-5.4-mini), controlled comparisons. This file is the
project's institutional memory: read it before proposing an experiment —
it may already be answered.

## What works (measured gains)

| Technique | Gain | Mechanism |
|---|---|---|
| ReAct loop + live DB tools | **+9.0** (55.2→64.2) | model verifies against real data instead of guessing |
| `reasoning_effort=high` | **+5** (64→69-70) | biggest single factor; capability was the bottleneck, not instructions |
| Result-vote ensemble (equal-strength runs) | +2 | coin-flip formatting errors break differently per run |
| API-retry (3 attempts) in runner | +2.4 on one run | 22 questions had been silently lost to infra errors |
| Official set-comparison scoring | +1.5–3 vs strict | duplicates/order don't count officially |
| 30s sqlite query abort | reliability | runaway model-written JOINs froze runs for hours |
| BIRD hint injected as ground truth | large (in-loop) | hints define exact formats/formulas |

## What fails (all A/B-tested — do not retry without new mechanism)

| Technique | Result | Why it fails |
|---|---|---|
| Post-answer verification prompt | fixed 0 / broke 3 | model second-guesses correct answers |
| Blocking FINAL until exploration | fixed 0 / broke 8 | same |
| LLM judge picks among candidates | 2/15 correct picks | judge shares generator's biases |
| LLM refinement of candidates | +2/−2 | same |
| Train-set few-shot k=2-3 | +9/−9 canary churn ×2 | cross-domain examples destabilize |
| Naive value lookup (exact match, capped) | ±0 | too weak; proper index still untried |
| Prompt rule accumulation | ±0 at 500-scale | formatting flips are gold-inconsistency, rules can't fix a moving target |
| Keyword table pre-selection (B2) | −3.6 vs B1 | drops needed tables, no fallback |
| Big mixed ensembles (7 voters) | 67.8 < 70.2 solo | weak voters outvote the strong one |

Ensemble law: voting needs voters of similar strength making different
mistakes. 1 strong + N weak = worse than strong alone. 2 strong + 3 weak = works (72.3).

## The leakage incident (2026-07-04)

The legacy in-domain retriever's pool = dev questions answered correctly,
with their gold SQL. Similarity retrieval returned the query question itself
(own gold in prompt) for ~73% of pool questions. All pre-fix numbers retracted.
Fix: exact-text + >0.98-similarity exclusion; audit shows 0/100 self-hits.
Post-fix ablations: dev-pool retrieval was not load-bearing (clean configs
replicate within variance) — but per supervisor directive the eval set is now
never touched at all: examples/patterns come from the train split only.

## Error structure (from the 149-failure autopsy of the best run)

- ~33% recoverable coin-flips: gold's inconsistent output conventions
  (train-set mining: multi-part questions → 2+ columns only 76% of the time)
- ~64% never solved by ANY config incl. larger models: mostly defective gold
  (documented: gold with AND/OR precedence bug, gold answering 'Min' to a
  "who" question, gold computing a requested ratio inverted, corrupted
  question text) → effective ceiling ≈ 80%
- ~2% infra/starvation; grammar errors ≈ 0 (sqlglot patch unnecessary for mini)
- Errors are SYSTEMATIC: same misinterpretation across configs/temperatures —
  the root reason self-judging and big ensembles saturate.

## Cost notes

- reasoning-high ≈ 3-4× tokens, 22s vs 7s median/question. R-VES unaffected
  (it measures SQL runtime, not model latency).
- User-observed: mini at high reasoning may cost ≈ gpt-5.4 standard per question.
  Token logging (todo) will quantify. Precomputed insights are free at
  inference — the preferred direction for accuracy-per-cost.
