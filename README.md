# Agentic Search — DB-RLM for Text-to-SQL

Extending Recursive Language Models (RLM) to structured database reasoning.
Evaluated on **BIRD mini-dev** (500 questions / 498 unique, 11 databases),
scored with the **official BIRD protocol** (execution accuracy, set comparison).

**Generator model everywhere: `gpt-5.4-mini` (Azure).** The research question
(per supervisor): how far can a small model go with the right harness —
execution environment, tools, verifiers, and precomputed insights — without
a bigger or domain-specific model?

## Results (all verified, all eval-set-free unless marked)

| Configuration | Accuracy | Notes |
|---|---|---|
| Baseline 1 — direct schema→SQL | 55.2% | no tools, one shot |
| Baseline 2 — + keyword table filter | 51.6% | naive pruning hurts |
| **DB-RLM harness (v4)** | **64.2%** | ReAct loop + live DB tools |
| **+ `reasoning_effort=high`, train-set few-shot k=1** | **69.2%** | single run, clean headline |
| + high reasoning, no few-shot | 68.6% | ablation: retrieval not load-bearing |
| **Clean 3-run ensemble** (result-vote) | **71.1%** | cost = 3 passes |
| Best 5-run ensemble | 72.3% | includes 2 runs w/ dev-pool retrieval (disclosed) |

Reasoning-high band over 4 runs: 67.2–70.2% (±~1.5). Run-to-run variance
means single-run deltas < ~2 points are noise.

~19% of mini-dev questions were never solved by any configuration (incl. a
much larger model); manual inspection shows defective gold SQL, corrupted
questions, and inconsistent output conventions → effective ceiling ≈ 80%.
See `docs/findings.md`.

## How it works

The model sits in a ReAct loop with a **sandboxed live SQLite connection**
(`ours/db_environment.py`): it can run exploratory SQL (`db.execute`), inspect
stored values (`db.sample_values`), test its query, see real results, and only
then submit via `FINAL("sql")`. Sandbox = read-only, 30s per-query abort,
row caps. The BIRD hint is injected as ground truth; guards block submitting
after empty/all-NULL results.

## Repo layout

```
src/rlm/        RLM engine (ReAct loop, REPL sandbox, parser)
ours/           DB agent: recursive_db_rlm.py (agent+prompt), db_environment.py
                (DB bridge), retrievers (train-set + legacy), schema cache
shared/         evaluator (official protocol) + SQL executor
scripts/        validated runners + rescore_official.py
baselines/      baseline 1 & 2 runners
results/        the 9 result files behind the table above
data/           question sets + train pool (databases NOT included, see below)
docs/           findings ledger, offline-ingestion spec, task split
```

## Setup

1. `pip install -r requirements.txt`
2. Download BIRD mini-dev databases → `data/raw/bird/minidev/MINIDEV/dev_databases/`
   (from https://bird-bench.github.io)
3. `.env`: `LLM_API_KEY=...`, `LLM_BASE_URL=...` (Azure endpoint)

## Reproduce the headline

```bash
python scripts/run_bird_train_fewshot.py \
  --output results/repro_trainfs_rhigh.json \
  --k 1 --max-iterations 8 --reasoning-effort high
```
Expect 67–70% (±1.5 run variance). Rescore any result file with the official
protocol: `python scripts/rescore_official.py`.

## Known dataset notes

- `data/processed/bird_dev_500.json` contains 2 exact duplicate entries
  (bird_137, bird_138) → 498 unique questions. All runs share them; effect ±0.1%.
- Results from before 2026-07-04 in the old repository used a leaky retriever
  and are retracted; this repo contains only post-fix artifacts.
