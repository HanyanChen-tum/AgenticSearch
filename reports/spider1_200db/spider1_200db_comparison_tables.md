# Spider 1.0 200DB Experiment Summary

Dataset label: `spider1_200db`

Source file: `results/spider1_200db_summary_metrics.json`

This report stores the current summary metrics for the Spider 1.0 run labeled as 200DB. The three baseline methods currently have 200 evaluated examples each. `ours_recursive_db_rlm` is listed as missing because `results/ours_recursive_db_rlm.json` is not present in the current results directory.

## Main Metrics

| Method | Total | Correct | Execution Accuracy | SQL Valid Rate | Error Rate | Exact Match | Component Match | Avg Latency (s) | Input Tokens | Output Tokens | Tool Calls | Avg Tool Calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline_1_direct_llm_schema` | 200 | 136 | 0.680 | 0.820 | 0.180 | 0.175 | 0.505 | 2.7833 | 56414 | 6706 | 0 | 0.00 |
| `baseline_2_direct_text_to_sql` | 200 | 140 | 0.700 | 0.960 | 0.040 | 0.195 | 0.490 | 2.7397 | 50313 | 6808 | 0 | 0.00 |
| `baseline_3_non_recursive_db_agent` | 200 | 129 | 0.645 | 0.960 | 0.040 | 0.180 | 0.470 | 14.5655 | 643201 | 24784 | 922 | 4.61 |
| `ours_recursive_db_rlm` | 0 | 0 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

## Component Accuracy

| Method | Tables | Columns | Joins | Aggregations |
|---|---:|---:|---:|---:|
| `baseline_1_direct_llm_schema` | 0.815 | 0.905 | 0.570 | 0.935 |
| `baseline_2_direct_text_to_sql` | 0.795 | 0.890 | 0.550 | 0.935 |
| `baseline_3_non_recursive_db_agent` | 0.760 | 0.780 | 0.555 | 0.900 |
| `ours_recursive_db_rlm` | N/A | N/A | N/A | N/A |

## Failure Type Counts

| Method | Wrong Table | Wrong Join | Wrong Aggregation | Invalid SQL | Wrong Result |
|---|---:|---:|---:|---:|---:|
| `baseline_1_direct_llm_schema` | 15 | 3 | 4 | 36 | 6 |
| `baseline_2_direct_text_to_sql` | 29 | 10 | 4 | 8 | 9 |
| `baseline_3_non_recursive_db_agent` | 36 | 10 | 3 | 8 | 14 |
| `ours_recursive_db_rlm` | N/A | N/A | N/A | N/A | N/A |
