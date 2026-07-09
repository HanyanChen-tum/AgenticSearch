# RLM Ablation Progress

## Naming Correction

`run_ours.py` defaults to recursion enabled, but the previous full-suite entry named `bird_ours_basic_500` explicitly passed:

```text
--no-recursion
--prompt-version basic
```

Therefore the old `results/bird_ours_basic_500.json` should be interpreted as a no-RLM basic agent result, not as an RLM result.

## Suite Update

`scripts/run_bird_full_suite.py` now separates the controlled RLM comparison:

```text
bird_ours_basic_no_rlm_500
bird_ours_basic_rlm_500
bird_ours_metadata_enrichment_probe_no_rlm_500
bird_ours_metadata_enrichment_probe_rlm_500
```

The key comparison for the research question is:

```text
basic_no_rlm vs basic_rlm
metadata_enrichment_probe_no_rlm vs metadata_enrichment_probe_rlm
```

These pairs keep the prompt family and context setting aligned, while changing whether recursive subquestion calls are enabled.

## 50-Example Commands

Basic no-RLM:

```powershell
python scripts\run_ours.py `
  --dataset data\processed\bird_mini_dev_questions.json `
  --database-dir data\databases `
  --limit 50 `
  --no-recursion `
  --prompt-version basic `
  --output results\bird_ours_basic_no_rlm_50.json
```

Basic RLM:

```powershell
python scripts\run_ours.py `
  --dataset data\processed\bird_mini_dev_questions.json `
  --database-dir data\databases `
  --limit 50 `
  --use-recursion `
  --prompt-version basic `
  --output results\bird_ours_basic_rlm_50.json
```

Probe no-RLM:

```powershell
python scripts\run_ours.py `
  --dataset data\processed\bird_mini_dev_questions.json `
  --database-dir data\databases `
  --limit 50 `
  --no-recursion `
  --use-metadata `
  --use-enrichment `
  --use-probe-queries `
  --prompt-version basic `
  --output results\bird_ours_metadata_enrichment_probe_no_rlm_50.json
```

Probe RLM:

```powershell
python scripts\run_ours.py `
  --dataset data\processed\bird_mini_dev_questions.json `
  --database-dir data\databases `
  --limit 50 `
  --use-recursion `
  --use-metadata `
  --use-enrichment `
  --use-probe-queries `
  --prompt-version recursive `
  --output results\bird_ours_metadata_enrichment_probe_rlm_50.json
```

Evaluate:

```powershell
python scripts\evaluate_results.py --result-files `
  results\bird_ours_basic_no_rlm_50.json `
  results\bird_ours_basic_rlm_50.json `
  results\bird_ours_metadata_enrichment_probe_no_rlm_50.json `
  results\bird_ours_metadata_enrichment_probe_rlm_50.json
```
