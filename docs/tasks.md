# Task Board — all open work

One shared list; assignment decided by the team (goal per supervisor: split
into complementary tracks, no duplication — write names next to items once
agreed). Ordered by dependency, then priority.

## 1. Instrumentation (prerequisite for most of the below)

- [ ] Transcript logging in the runner: save the full ReAct message history
      per question (needed for trace folding; costs nothing)
- [ ] Token-usage logging: sum litellm `usage` per call into each result
      record (needed for all cost claims and the trace-folding metric)
- [ ] Record model name + config in every result file

## 2. Offline ingestion (see `spec.md` — get supervisor's review BEFORE coding)

- [ ] Stage 1: per-DB metadata precompute — schema graph, canonical FK join
      paths, value formats, sample values, description-CSV merge
- [ ] Stage 2: query-pattern mining from the train split (9,428 gold pairs) —
      per-DB idioms + global output-format statistics; inject as a compact
      pattern block replacing retrieved examples
- [ ] Stage 3: reasoning-trace folding — mine 2-3 logged rollouts for
      recurring reasoning events, promote them into Stage 1/2 artifacts;
      metric = reasoning tokens ↓ at equal accuracy

## 3. Cost / accuracy experiments (cheap, high information)

- [ ] Reasoning-effort sweep: low / medium (only default & high ever tested) —
      test on the 197-question core first; medium ≈ high at half tokens would
      be the accuracy-per-cost sweet spot
- [ ] Difficulty-aware effort routing: simple→low effort, challenging→high
      (simple already at ~80% without thinking)
- [ ] v4-config × reasoning-high (missing ablation cell)
- [ ] Investigator/recursion sub-agent + reasoning-high (SQ2 evidence;
      measured surface: ~28 struggling questions/run)
- [ ] Rollout scaling (N=3-5 reasoning-high rollouts + result vote) — after
      effort sweep reduces per-rollout cost

## 4. Verification & surgical patching (supervisor: ≤4B, ideally ≤1B, surgical)

- [ ] Output-format verifier v0 (rules from train-set conventions) evaluated
      as re-ranker/veto over stored rollout candidates — pure offline, no API
- [ ] Verifier v1 as tiny trained model (≤1B) if v0 shows signal
- [ ] Failure-mode deep dives on the failure maps (never-solved vs coin-flip),
      feeding patterns back to Stage 2

## 5. Report (start NOW per supervisor; ~1.5 months left)

- [ ] Report skeleton: intro, background, method, experiments, findings
- [ ] Literature review, 2 papers/person/week → background section.
      Suggested: CHESS, DAIL-SQL, CHASE-SQL, RLM paper, Self-Consistency
      (Wang et al.), Arctic-Text2SQL-R1
- [ ] Ablation tables & charts in supervisor's format ("Baseline",
      "Baseline + [module]", text-annotated, one module per row)
- [ ] Gold-noise exhibit: documented defective-gold cases (~19% of set)
- [ ] Methodology section: official protocol, leakage discovery + fix,
      variance measurement (institutional-rigor story)

## 6. Scaling & closing round

- [ ] **Full BIRD dev run (1,534 questions)** with the best validated config —
      we have only ever evaluated on mini-dev (500). Full dev = the number
      comparable to published papers. Budget note: ~3× the questions; run
      after the reasoning-effort sweep picks the cheapest good setting
- [ ] Unified token budgets across all configurations, final fair comparison
      (supervisor-deferred until modules validated)

## Standing rules

- The eval set is never used as a data source (examples, patterns, tuning)
- Official scoring only (`shared/evaluator.py`); rescore with
  `scripts/rescore_official.py`
- Any single-run delta < ~2 points is within variance — validate on the
  197-question core + canary before spending a full run
- Spec review with supervisor before implementing Stage 2/3


## Onboarding checklist (do these first)

1. Read `README.md`, then `docs/findings.md` (what's proven/dead — saves you
   from re-running failed ideas), then this file
2. Setup: `pip install -r requirements.txt`; copy `.env.example` → `.env`
   (ask Aziz for the seminar API key); download BIRD mini-dev databases from
   https://bird-bench.github.io → `data/raw/bird/minidev/MINIDEV/dev_databases/`
3. Smoke test (~2 min, 10 questions):
   `python scripts/run_bird_train_fewshot.py --limit 10 --output results/smoke.json`
4. **No-API entry point**: the verifier and failure-analysis tasks work
   entirely offline on the stored result files in `results/` — you can start
   before any key/database setup:
   - every result file has per-question `predicted_sql`, `predicted_answer`,
     `gold_answer` — score things with `shared/evaluator.py`
   - `data/processed/bird_cleancore_ids.json` = the hard-core /canary split
     used for cheap intervention tests
5. Conventions: work on branches (`name/topic`), PRs into `main`; every run
   records model+config; deltas < ~2 points are run-variance — validate on
   the core+canary subset before spending a full run
