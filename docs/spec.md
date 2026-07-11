# Spec: Offline Ingestion — Query-Pattern Mining & Reasoning-Trace Folding (v0.1)

*One-page design for supervisor review before implementation, per 2026-07-09 meeting.*

## Goal

Reduce per-question reasoning cost and improve grounding by precomputing,
once per database, the insights the generator currently re-derives on every
question. The eval set is never touched.

## Inputs

1. BIRD train split — 9,428 question/gold-SQL pairs (`data/train_pool.json`)
2. Database files + BIRD `database_description` CSVs
3. Reasoning-run transcripts from our own rollouts (visible ReAct events:
   model code, intermediate queries, observations — no eval gold anywhere)

## Stage 1 — Static metadata (per DB)

Schema graph with canonical FK join paths; per-column type, 2–3 sample
values, value formats (date shapes, enums, units); column descriptions merged
from CSVs. **Output:** `metadata.json` per DB.

## Stage 2 — Query-pattern mining (from train)

Cluster train gold SQL by template (join sets, aggregation type, filter
idioms). Extract per-DB idioms (canonical join paths actually used, IIF/CASE
conventions, date handling) and global output-format statistics per question
type (e.g., multi-part → 2+ columns 76%). **Output:** `patterns.json` per DB
+ global conventions. Replaces retrieved examples with a compact pattern block.

## Stage 3 — Reasoning-trace folding ("dynamic programming for reasoning")

Enable transcript logging in the runner. Across N rollouts × 500 questions,
mine recurring reasoning events/intentions (e.g., re-discovering that
`yearmonth.Date` is YYYYMM; re-deriving the same join path). Promote recurring
events into Stage 1/2 artifacts so they are *read* instead of *re-derived*.
**Metric:** reasoning tokens/question ↓ at equal accuracy.

## Serving

All artifacts compile to one compact per-DB context block (~1–2k tokens),
injected at prompt build. No runtime LLM calls. No eval-set content.

## Evaluation plan (incremental ablation, one module per trial)

Baseline (current best) → +metadata → +patterns → +folded-traces.
Report: official EX accuracy, reasoning tokens/question, latency.
Success criterion: ≥ current accuracy at measurably lower reasoning budget,
or accuracy gain at equal budget.

## Non-goals (v1)

No bigger generator models; no eval-set-derived examples; no trained
auxiliary models (pure precompute; the ≤1B surgical verifier is a separate
track, see tasks.md).
