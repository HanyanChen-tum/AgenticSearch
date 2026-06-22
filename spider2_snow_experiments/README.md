# Spider2-Snow Experiments

这个目录是独立的 Spider 2.0-Snow 实验入口，不修改根目录已有的 Spider 1.0 baseline。

## 目录职责

```text
spider2_snow_experiments/
├── config.py                  # 路径、LLM、Snowflake 配置
├── data.py                    # 读取 spider2-snow.jsonl
├── schema.py                  # 从 Spider2-Snow resource/databases/*/DDL.csv 读取 schema
├── llm.py                     # Gemini / OpenAI-compatible LLM 客户端
├── snowflake_backend.py       # 可选 Snowflake SQL 执行
├── runner.py                  # 三个 baseline 共用运行循环
├── baselines/
│   ├── baseline_1_direct_llm_schema.py
│   ├── baseline_2_retrieved_schema.py
│   └── baseline_3_non_recursive_db_agent.py
├── prompts/
└── scripts/
    ├── smoke_test.py
    ├── run_baseline_1.py
    ├── run_baseline_2.py
    ├── run_baseline_3.py
    ├── run_all_baselines.py
    └── export_sql_submission.py
```

根目录原来的 `baselines/`, `shared/`, `scripts/prepare_spider1.py` 仍然用于 Spider 1.0 / SQLite。

## 前置条件

Spider2 官方数据默认放在：

```text
Spider2/spider2-snow/spider2-snow.jsonl
Spider2/spider2-snow/resource/databases
Spider2/spider2-snow/resource/documents
```

本地 Qwen 推荐使用 Ollama：

```powershell
ollama list
```

如果 `http://localhost:11434/v1` 可用，就可以通过 OpenAI-compatible 接口调用。

## 配置

可以直接复用根目录 `.env`，也可以复制本目录模板：

```powershell
copy spider2_snow_experiments\.env.example spider2_snow_experiments\.env
```

本地 Qwen 示例：

```dotenv
LLM_PROVIDER=openai_compatible
MODEL=qwen2.5-coder:7b
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
TEMPERATURE=0
MAX_TOKENS=1024
```

如果要在 baseline 运行时直接执行 Snowflake SQL，还需要配置：

```dotenv
SPIDER2_SNOW_CREDENTIAL_PATH=C:\Users\Irene\AgenticSearch\Spider2\methods\spider-agent-snow\snowflake_credential.json
```

或使用环境变量：

```dotenv
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_ACCOUNT=RSRSBDK-YDB67606
```

## Smoke Test

只测试 Spider2 数据、DDL schema 和外部文档是否能读取：

```powershell
python -m spider2_snow_experiments.scripts.smoke_test --limit 2
```

额外测试 LLM endpoint：

```powershell
python -m spider2_snow_experiments.scripts.smoke_test --limit 2 --llm
```

## 跑三个 Baseline

先跑小样本，不执行 Snowflake：

```powershell
python -m spider2_snow_experiments.scripts.run_all_baselines --limit 1 --model qwen2.5-coder:7b
```

只跑某一个：

```powershell
python -m spider2_snow_experiments.scripts.run_baseline_1 --limit 1
python -m spider2_snow_experiments.scripts.run_baseline_2 --limit 1 --top-k-tables 8
python -m spider2_snow_experiments.scripts.run_baseline_3 --limit 1 --max-steps 8
```

Baseline 3 默认只用本地 DDL 工具，不在推理过程中访问 Snowflake。如果要允许它采样或执行中间 SQL：

```powershell
python -m spider2_snow_experiments.scripts.run_baseline_3 --limit 1 --allow-live-tools
```

如果要在生成后直接执行最终 SQL：

```powershell
python -m spider2_snow_experiments.scripts.run_all_baselines --limit 1 --execute
```

## 导出官方评估格式

生成结果 JSON 后，导出为 Spider2-Snow 官方 `evaluate.py --mode sql` 需要的 `.sql` 文件夹：

```powershell
python -m spider2_snow_experiments.scripts.export_sql_submission `
  --result-json results\spider2_snow\baseline_1_direct_llm_schema.json `
  --submission-dir results\spider2_snow_submissions\baseline_1_direct_llm_schema `
  --overwrite
```

然后用官方评估：

```powershell
cd Spider2\spider2-snow\evaluation_suite
python evaluate.py --mode sql --result_dir C:\Users\Irene\AgenticSearch\results\spider2_snow_submissions\baseline_1_direct_llm_schema
```

## Baseline 定义

- `baseline_1_direct_llm_schema`: 问题 + 当前 `db_id` 的完整本地 DDL + external knowledge。
- `baseline_2_retrieved_schema`: 先按词面相关性检索 top-k 表，再让 LLM 生成 SQL。
- `baseline_3_non_recursive_db_agent`: 多步非递归工具 agent，可调用 `SHOW_TABLES`, `DESCRIBE_TABLE`，可选调用 Snowflake live tools。

