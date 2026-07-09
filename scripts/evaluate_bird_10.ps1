$outputPath = "results/bird_10_evaluation.txt"

python scripts/evaluate_results.py `
  --result-files `
  results/bird_b1_10.json `
  results/bird_b2_10.json `
  results/bird_b3_10.json `
  results/bird_ours_basic_10.json `
  results/bird_ours_metadata_10.json `
  results/bird_ours_metadata_enrichment_10.json `
  results/bird_ours_metadata_enrichment_probe_10.json `
  results/bird_ours_full_workspace_10.json `
  | Tee-Object -FilePath $outputPath

Write-Host "Saved evaluation output to $outputPath"
