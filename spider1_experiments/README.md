# Spider1 Experiments

这个目录是 Spider 1.0 / SQLite 实验入口。它是从根目录原有 Spider1 代码整理出来的独立包。

原来的目录仍然保留：

```text
baselines/
shared/
scripts/
prompts/
ours/
```

新实验建议使用：

```text
spider1_experiments/
```

这样 Spider1 和 Spider2-Snow 分开：

```text
spider1_experiments/        # Spider 1.0 / SQLite
spider2_snow_experiments/   # Spider 2.0-Snow / Snowflake
```

## 目录结构

```text
spider1_experiments/
├── baselines/
│   ├── baseline_1_direct_llm_schema.py
│   ├── baseline_2_direct_text_to_sql.py
│   └── baseline_3_non_recursive_db_agent.py
├── ours/
│   └── recursive_db_rlm.py
├── shared/
│   ├── config.py
│   ├── data_loader.py
│   ├── evaluator.py
│   ├── llm_client.py
│   ├── schema_utils.py
│   └── sql_executor.py
├── prompts/
└── scripts/
    ├── prepare_spider1.py
    ├── smoke_test.py
    ├── run_all_baselines.py
    ├── run_baseline_1.py
    ├── run_baseline_2.py
    ├── run_baseline_3.py
    ├── run_ours.py
    └── evaluate_results.py
```

## 数据准备

Spider 1.0 解压到：

```text
data/spider_data/
├── train_spider.json
├── dev.json
├── tables.json
└── database/
```

Windows 上建议复制数据库而不是 symlink：

```powershell
python -m spider1_experiments.scripts.prepare_spider1 --database-mode copy
```

准备后会使用：

```text
data/processed/dev_questions.json
data/databases/{db_id}/{db_id}.sqlite
```

## 配置本地 Qwen

可以复制模板：

```powershell
copy spider1_experiments\.env.example spider1_experiments\.env
```

默认本地 Ollama：

```dotenv
LLM_PROVIDER=openai_compatible
MODEL=qwen2.5-coder:7b
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
TEMPERATURE=0
MAX_TOKENS=1024
```

## Smoke Test

只检查数据和 SQLite schema：

```powershell
python -m spider1_experiments.scripts.smoke_test --limit 2
```

额外检查 LLM：

```powershell
python -m spider1_experiments.scripts.smoke_test --limit 1 --llm
```

## 运行 Baselines

小样本跑三个 baseline：

```powershell
python -m spider1_experiments.scripts.run_all_baselines --limit 5
```

单独运行：

```powershell
python -m spider1_experiments.scripts.run_baseline_1 --limit 5
python -m spider1_experiments.scripts.run_baseline_2 --limit 5 --top-k-tables 5 --top-k-columns 8
python -m spider1_experiments.scripts.run_baseline_3 --limit 5 --max-steps 8
```

运行 recursive DB-RLM：

```powershell
python -m spider1_experiments.scripts.run_ours --limit 5 --max-depth 2 --max-actions 24
```

默认结果目录：

```text
results/spider1/
```

默认日志目录：

```text
logs/spider1/
```

## 汇总指标

```powershell
python -m spider1_experiments.scripts.evaluate_results --results-dir results\spider1 --output results\spider1\summary_metrics.json
```

