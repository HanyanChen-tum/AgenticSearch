# Candidate Ensemble Progress

## Current Finding

The 500-example BIRD Mini-Dev results show that larger context alone is not a strong improvement path:

| method | correct | accuracy | avg latency |
|---|---:|---:|---:|
| baseline_2_direct_text_to_sql | 255 / 500 | 0.510 | 3.6926s |
| bird_ours_metadata_enrichment | 262 / 500 | 0.524 | 16.8055s |
| bird_ours_metadata_enrichment_probe | 268 / 500 | 0.536 | 16.9697s |
| bird_ours_full_workspace | 255 / 500 | 0.510 | 17.7574s |

The best current variant improves over baseline 2 by 13 questions, but it costs about 4.6x latency. Full workspace does not improve accuracy. This suggests the next step should not be more context; it should be better candidate selection.

Overlap analysis across baseline 2, metadata enrichment, and metadata enrichment + probe:

| metric | value |
|---|---:|
| baseline 2 correct | 255 / 500 |
| metadata enrichment correct | 262 / 500 |
| metadata enrichment + probe correct | 268 / 500 |
| oracle union upper bound | 318 / 500 = 0.636 |
| all-correct intersection | 203 / 500 = 0.406 |
| baseline 2 correct but probe wrong | 40 |
| probe correct but baseline 2 wrong | 53 |

This is enough headroom to justify a selector/verifier: the candidates collectively contain 318 correct answers, but the best single candidate only reaches 268.

## Change Made

Added `scripts/run_candidate_ensemble.py`.

The new script:

1. Reuses existing result files as SQL candidates.
2. Executes every candidate SQL against the target database.
3. Rejects invalid SQL and, by default, empty-result candidates.
4. Repairs unusable candidates with a bounded SQL repair loop.
5. Skips the verifier when there is only one usable candidate or all usable candidates return the same answer.
6. Calls an LLM verifier only when usable candidates disagree.
7. Falls back to the first usable candidate, normally baseline 2, if verifier parsing fails.

SQL repair defaults:

```text
--repair-attempts 1
--repair-empty-results
```

Use `--repair-attempts 0` to disable repair, or `--no-repair-empty-results` to repair only execution errors.

Default candidate order:

```text
results/bird_b2_500.json
results/bird_ours_metadata_enrichment_500.json
results/bird_ours_metadata_enrichment_probe_500.json
```

This keeps the strong direct text-to-SQL baseline as the default and uses metadata/probe only when their executed answers give useful alternatives.

Also added `scripts/analyze_candidate_overlap.py`, which computes the oracle union upper bound across result files. This tells us whether verifier selection can realistically improve accuracy.

## Suite Change

Updated `scripts/run_bird_full_suite.py`:

- Adds `bird_ours_candidate_ensemble_500` to the default suite.
- Stops running `bird_ours_full_workspace_500` by default.
- Keeps full workspace available through `--include-workspace`.

## How To Run

Run the full suite with resume enabled:

```powershell
python scripts/run_bird_full_suite.py --keep-existing
```

Run only the ensemble after candidate files already exist:

```powershell
python scripts/run_candidate_ensemble.py `
  --dataset data\processed\bird_mini_dev_questions.json `
  --database-dir data\databases `
  --limit 500 `
  --candidate-files results\bird_b2_500.json results\bird_ours_metadata_enrichment_500.json results\bird_ours_metadata_enrichment_probe_500.json `
  --repair-attempts 1 `
  --output results\bird_ours_candidate_ensemble_500.json
```

Evaluate:

```powershell
python scripts/evaluate_results.py --result-files `
  results\bird_b2_500.json `
  results\bird_ours_metadata_enrichment_probe_500.json `
  results\bird_ours_candidate_ensemble_500.json
```

Analyze overlap before spending more LLM calls:

```powershell
python scripts/analyze_candidate_overlap.py --result-files `
  results\bird_b2_500.json `
  results\bird_ours_metadata_enrichment_500.json `
  results\bird_ours_metadata_enrichment_probe_500.json
```

## Next Diagnostic

Before running more expensive ablations, compute candidate overlap with `scripts/analyze_candidate_overlap.py`:

- baseline 2 correct and probe wrong
- baseline 2 wrong and probe correct
- candidate union upper bound
- verifier selection accuracy on disagreement cases

If the union upper bound is much higher than 0.536, the verifier is the bottleneck. If the union upper bound is close to 0.536, the candidate generation strategy needs stronger changes.
