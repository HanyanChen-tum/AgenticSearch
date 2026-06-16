# Spider 1.0 200DB Error Analysis

Dataset label: `spider1_200db`

Source file: `results/spider1_200db_summary_metrics.json`

## Summary

The best execution accuracy in the current saved results is `baseline_2_direct_text_to_sql` at `0.700`. `baseline_3_non_recursive_db_agent` uses database tools but has lower execution accuracy and much higher latency/token cost in this run.

`ours_recursive_db_rlm` is not included in the comparison yet because the current results directory does not contain `results/ours_recursive_db_rlm.json`.

## Failure Breakdown

| Method | Total Failures | Wrong Table | Wrong Join | Wrong Aggregation | Invalid SQL | Wrong Result |
|---|---:|---:|---:|---:|---:|---:|
| `baseline_1_direct_llm_schema` | 64 | 15 | 3 | 4 | 36 | 6 |
| `baseline_2_direct_text_to_sql` | 60 | 29 | 10 | 4 | 8 | 9 |
| `baseline_3_non_recursive_db_agent` | 71 | 36 | 10 | 3 | 8 | 14 |

## Observations

- `baseline_1_direct_llm_schema` has the highest invalid SQL count, mainly from schema reference errors.
- `baseline_2_direct_text_to_sql` improves SQL validity but still has many wrong-table failures.
- `baseline_3_non_recursive_db_agent` makes many DB tool calls, but the current run does not translate those calls into better accuracy.
- The recursive method should be rerun and added before drawing a final conclusion about the proposed method.
