# Local 50-Sample Baseline Results

Model: qwen2.5-coder:3b via Ollama  
Dataset: Spider dev sample, 50 examples

| Method | Correct | Accuracy | Avg latency |
|---|---:|---:|---:|
| Baseline 1: Direct LLM + schema | 25/50 | 50% | 1.303s |
| Baseline 2: Direct Text-to-SQL | 33/50 | 66% | 1.651s |
| Baseline 3: Non-recursive DB Agent | 36/50 | 72% | 2.161s |

Observation:
Baseline 3 performs best, suggesting that schema selection and table sampling help the model compared to direct prompting.

Main failure types:
- Invented columns
- Wrong joins
- Wrong anti-join logic
- Wrong aggregation pattern
- Duplicate preservation issues
- Spider-specific interpretation errors
