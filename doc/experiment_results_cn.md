# BIRD Mini-Dev Text-to-SQL 实验记录

## 概述

本项目当前围绕 BIRD Mini-Dev 的 SQLite Text-to-SQL 任务展开实验。核心研究问题是：

```text
RLM / recursive agent 加入数据库问答 agent 后，是否能提高 Text-to-SQL 的执行正确率？
```

目前已经完成一批 500 条样本实验，结果显示：

- `baseline_2_direct_text_to_sql` 是当前最强且最快的基础 baseline，准确率为 `0.510`。
- 单纯扩大上下文，例如 `full_workspace`，没有提高准确率，只显著增加延迟。
- `metadata_enrichment_probe` 是当前最强的单一 ours 变体，准确率为 `0.536`。
- 多个候选方法之间有互补性，三个候选的 oracle union 上限为 `0.636`，说明后续可以测试 candidate ensemble / verifier。
- 原先名为 `bird_ours_basic_500` 的结果实际是 `--no-recursion` 版本，不能代表 RLM basic。当前 suite 已经修正命名，后续会明确区分 `no_rlm` 和 `rlm`。
- 已完成 50 条严格 RLM/no-RLM 配对实验：no-RLM 为 `0.620`，RLM 为 `0.580`；当前没有观察到 RLM 的准确率收益。

因此，后续主线应从“堆更多 workspace 上下文”转向：

```text
1. 用 baseline_2 作为强基础 baseline
2. 用 metadata + enrichment + probe 作为更强候选生成
3. 做 no-RLM vs RLM 的严格控制变量实验
4. 可选测试 candidate ensemble + SQL repair 作为工程增强方法
```

## 目录

- [实验设计总览](#实验设计总览)
- [数据与统一评估设置](#数据与统一评估设置)
- [实验 1：Baseline 1 直接 Schema Prompt](#实验-1baseline-1-直接-schema-prompt)
- [实验 2：Baseline 2 Schema Retrieval Text-to-SQL](#实验-2baseline-2-schema-retrieval-text-to-sql)
- [实验 3：Baseline 3 非递归数据库 Agent](#实验-3baseline-3-非递归数据库-agent)
- [实验 4：Ours Basic No-RLM](#实验-4ours-basic-no-rlm)
- [实验 5：Ours Metadata No-RLM](#实验-5ours-metadata-no-rlm)
- [实验 6：Ours Metadata Enrichment No-RLM](#实验-6ours-metadata-enrichment-no-rlm)
- [实验 7：Ours Metadata Enrichment Probe No-RLM](#实验-7ours-metadata-enrichment-probe-no-rlm)
- [实验 8：Ours Full Workspace](#实验-8ours-full-workspace)
- [实验 9：Candidate Ensemble + SQL Repair](#实验-9candidate-ensemble--sql-repair)
- [实验 10：RLM 控制变量实验](#实验-10rlm-控制变量实验)
- [当前结论](#当前结论)
- [后续建议实验顺序](#后续建议实验顺序)

## 实验设计总览

当前实验按 baseline 逐步增强：

| 阶段 | 方法 | 目的 | 当前状态 |
|---|---|---|---|
| Baseline | `baseline_1_direct_llm_schema` | 直接给 schema，测试最基础 text-to-SQL 能力 | 已完成 500 条 |
| Baseline | `baseline_2_direct_text_to_sql` | 检索相关 schema 后生成 SQL | 已完成 500 条，当前强 baseline |
| Baseline Agent | `baseline_3_non_recursive_db_agent` | 非递归 agent 可查 DB / 执行 SQL | 已完成 500 条，慢且无提升 |
| Ours No-RLM | `bird_ours_basic_500` 历史结果 | basic prompt，无递归、无 metadata | 已完成 500 条，但命名需解释为 no-RLM |
| Ours No-RLM | `bird_ours_metadata_500` | 加 metadata，不加 enrichment/probe | 已完成 500 条 |
| Ours No-RLM | `bird_ours_metadata_enrichment_500` | 加 query enrichment | 已完成 500 条 |
| Ours No-RLM | `bird_ours_metadata_enrichment_probe_500` | 加真实数据 probe | 已完成 500 条，当前最强单一 ours 变体 |
| Workspace | `bird_ours_full_workspace_500` | 测试更大 workspace 上下文 | 已完成 500 条，不建议继续主测 |
| Ensemble | `bird_ours_candidate_ensemble_*` | 多候选 SQL + verifier + repair | 已实现，待跑 50 / 500 条 |
| RLM Ablation | `*_no_rlm` vs `*_rlm` | 严格测试 RLM 是否有用 | 已完成 50 条 pilot，RLM 未提升 |

## 数据与统一评估设置

### 数据

| 项目 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 样本文件 | `data/processed/bird_mini_dev_questions.json` |
| 数据库目录 | `data/databases` |
| 当前完整实验规模 | `500` 条 |
| 小规模调试规模 | `50` 条 |
| 数据库类型 | SQLite |

### 评估指标

| 指标 | 含义 |
|---|---|
| `total` | 样本数 |
| `correct` | 执行结果正确的样本数 |
| `execution_accuracy` | `correct / total` |
| `avg_latency_seconds` | 平均每题运行时间 |
| `total_input_tokens` | 总输入 token 数，部分方法未记录 |
| `total_output_tokens` | 总输出 token 数，部分方法未记录 |
| `total_tool_calls` | 工具调用次数，主要用于 agent 方法 |
| `avg_tool_calls` | 平均工具调用次数 |

### 当前固定量

已完成 500 条结果中，固定量包括：

```text
dataset = data/processed/bird_mini_dev_questions.json
database_dir = data/databases
limit = 500
metric = execution accuracy
database = SQLite
```

需要注意：当前结果表没有完整记录每次使用的模型名、API provider 和温度设置。后续正式实验应把这些写入结果文件或报告。

## 已完成 500 条实验结果总表

| method | total | correct | execution_accuracy | avg_latency_seconds | total_input_tokens | total_output_tokens | total_tool_calls | avg_tool_calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_1_direct_llm_schema | 500 | 254 | 0.508 | 3.6097 | 389309 | 34741 | None | None |
| baseline_2_direct_text_to_sql | 500 | 255 | 0.510 | 3.6926 | 213378 | 33815 | None | None |
| baseline_3_non_recursive_db_agent | 500 | 246 | 0.492 | 28.1828 | 2330232 | 109152 | 1966 | 3.932 |
| bird_ours_basic_500 | 500 | 133 | 0.266 | 4.0151 | None | None | None | None |
| bird_ours_metadata_500 | 500 | 255 | 0.510 | 4.9427 | None | None | None | None |
| bird_ours_metadata_enrichment_500 | 500 | 262 | 0.524 | 16.8055 | None | None | None | None |
| bird_ours_metadata_enrichment_probe_500 | 500 | 268 | 0.536 | 16.9697 | None | None | None | None |
| bird_ours_full_workspace_500 | 500 | 255 | 0.510 | 17.7574 | None | None | None | None |

## 已完成 50 条严格 RLM 对照结果

| method | total | correct | execution_accuracy | avg_latency_seconds | total_input_tokens | total_output_tokens | total_tool_calls | avg_tool_calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bird_ours_metadata_enrichment_probe_no_rlm_50 | 50 | 31 | 0.620 | 2.4938 | None | None | None | None |
| bird_ours_metadata_enrichment_probe_rlm_50 | 50 | 29 | 0.580 | 3.2419 | None | None | None | None |

逐题配对结果：

| 配对类别 | 样本数 |
|---|---:|
| 两种方法都正确 | 29 |
| 仅 no-RLM 正确 | 2 |
| 仅 RLM 正确 | 0 |
| 两种方法都错误 | 19 |

RLM 相比 no-RLM 净减少 2 道正确题，准确率差为 `-4.00%`，平均延迟增加约 `30.0%`。该结果是 50 条 pilot，能够说明当前配置下没有观察到收益，但仍不能代替完整数据集上的统计结论。

## 实验 1：Baseline 1 直接 Schema Prompt

### 实验是什么

`baseline_1_direct_llm_schema` 是最基础的直接 text-to-SQL baseline。它主要把数据库 schema 提供给模型，让模型直接生成 SQL。

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 样本数 | 500 |
| 数据库 | SQLite |
| 是否 agent | 否 |
| 是否递归 | 否 |
| 是否执行中间 SQL | 否 |

### 变量

该实验本身不做复杂变量消融，主要作为基础 baseline。

### 数据与结果

| total | correct | accuracy | avg latency | input tokens | output tokens |
|---:|---:|---:|---:|---:|---:|
| 500 | 254 | 0.508 | 3.6097s | 389309 | 34741 |

### 分析

该方法准确率为 `0.508`，与 `baseline_2` 的 `0.510` 非常接近，但输入 token 更多。说明直接给 schema 已经有较强表现，但 schema 检索可以更省 token。

## 实验 2：Baseline 2 Schema Retrieval Text-to-SQL

### 实验是什么

`baseline_2_direct_text_to_sql` 先根据问题检索相关 tables / columns，再让模型生成 SQL。它不执行中间查询，也不做多步 agent 推理。

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 样本数 | 500 |
| 数据库 | SQLite |
| 是否 agent | 否 |
| 是否递归 | 否 |
| 是否执行中间 SQL | 否 |

### 变量

| 变量 | 当前设置 |
|---|---|
| schema retrieval | 开启 |
| top-k tables / columns | 使用 baseline 脚本默认值 |

### 数据与结果

| total | correct | accuracy | avg latency | input tokens | output tokens |
|---:|---:|---:|---:|---:|---:|
| 500 | 255 | 0.510 | 3.6926s | 213378 | 33815 |

### 分析

这是当前最重要的基础 baseline。它比 baseline 1 只多对 1 题，但输入 token 从 `389309` 降到 `213378`，成本更低。因此后续 ensemble 和 RLM 对照都应以 baseline 2 作为基础参照。

## 实验 3：Baseline 3 非递归数据库 Agent

### 实验是什么

`baseline_3_non_recursive_db_agent` 是一个非递归数据库 agent。它可以查询 schema、执行 SQL、观察结果，但不做 RLM 递归子问题拆解。

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 样本数 | 500 |
| 数据库 | SQLite |
| 是否 agent | 是 |
| 是否递归 | 否 |
| 最大步数 | `max_steps=8` |

### 变量

| 变量 | 当前设置 |
|---|---|
| 工具调用 | 开启 |
| 中间 SQL 执行 | 开启 |
| RLM recursion | 关闭 |

### 数据与结果

| total | correct | accuracy | avg latency | input tokens | output tokens | tool calls | avg tool calls |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 246 | 0.492 | 28.1828s | 2330232 | 109152 | 1966 | 3.932 |

### 分析

该方法比 baseline 2 更慢且更低准确率。说明“非递归 agent + 多步执行”本身不是有效提升。它可以作为对照说明：agent loop 如果没有更好的任务分解或选择机制，可能只会增加成本。

后续不建议继续主测该方法。

## 实验 4：Ours Basic No-RLM

### 实验是什么

历史结果文件名为 `bird_ours_basic_500`。根据当前脚本检查，这个实验实际命令包含：

```text
--no-recursion
--prompt-version basic
```

因此它应解释为：

```text
basic prompt + no RLM + no metadata + no enrichment + no probe
```

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 样本数 | 500 |
| 数据库 | SQLite |
| agent 框架 | `scripts/run_ours.py` |
| prompt version | `basic` |
| RLM recursion | 关闭 |

### 变量

| 变量 | 当前设置 |
|---|---|
| metadata | 关闭 |
| enrichment | 关闭 |
| probe queries | 关闭 |
| workspace | 关闭 |

### 数据与结果

| total | correct | accuracy | avg latency |
|---:|---:|---:|---:|
| 500 | 133 | 0.266 | 4.0151s |

### 分析

该结果明显低于 baseline 2。它不能代表 RLM 的效果，只能说明 basic no-RLM agent 在没有 metadata/probe 的情况下能力不足。

当前 suite 已修正命名，后续应使用：

```text
bird_ours_basic_no_rlm_500
bird_ours_basic_rlm_500
```

来做严格对比。

## 实验 5：Ours Metadata No-RLM

### 实验是什么

`bird_ours_metadata_500` 在 ours agent 中加入 metadata，但仍然关闭 recursion。

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 样本数 | 500 |
| prompt version | `basic` |
| RLM recursion | 关闭 |

### 变量

| 变量 | 当前设置 |
|---|---|
| metadata | 开启 |
| enrichment | 关闭 |
| probe queries | 关闭 |
| workspace | 关闭 |

### 数据与结果

| total | correct | accuracy | avg latency |
|---:|---:|---:|---:|
| 500 | 255 | 0.510 | 4.9427s |

### 分析

metadata 让 ours 从 basic no-RLM 的 `0.266` 提升到 `0.510`，说明 schema / metadata 是必要信息。但它没有超过 baseline 2，而且延迟更高。因此 metadata-only 不建议作为后续主实验继续跑 500 条。

## 实验 6：Ours Metadata Enrichment No-RLM

### 实验是什么

`bird_ours_metadata_enrichment_500` 在 metadata 基础上加入 query enrichment。它尝试根据问题补充相关表、列、实体线索和 join 方向。

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 样本数 | 500 |
| prompt version | `basic` |
| RLM recursion | 关闭 |

### 变量

| 变量 | 当前设置 |
|---|---|
| metadata | 开启 |
| enrichment | 开启 |
| probe queries | 关闭 |
| workspace | 关闭 |

### 数据与结果

| total | correct | accuracy | avg latency |
|---:|---:|---:|---:|
| 500 | 262 | 0.524 | 16.8055s |

### 分析

相比 baseline 2，准确率从 `0.510` 提升到 `0.524`，多对 7 题。但平均延迟从 `3.6926s` 增加到 `16.8055s`。说明 enrichment 有帮助，但成本较高。

如果预算有限，后续可跳过单独 enrichment，直接保留更强的 enrichment + probe。

## 实验 7：Ours Metadata Enrichment Probe No-RLM

### 实验是什么

`bird_ours_metadata_enrichment_probe_500` 在 metadata + enrichment 基础上增加 probe queries。probe 会在生成最终 SQL 前执行小型探测查询，观察真实数据库值和数据分布。

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 样本数 | 500 |
| prompt version | `basic` |
| RLM recursion | 关闭 |

### 变量

| 变量 | 当前设置 |
|---|---|
| metadata | 开启 |
| enrichment | 开启 |
| probe queries | 开启 |
| workspace | 关闭 |

### 数据与结果

| total | correct | accuracy | avg latency |
|---:|---:|---:|---:|
| 500 | 268 | 0.536 | 16.9697s |

### 分析

这是当前已完成 500 条实验中最强的单一 ours 变体。它比 baseline 2 多对 13 题：

```text
268 - 255 = 13
```

probe 的提升说明 BIRD 中不少错误来自真实值匹配、实体格式、字段内容判断，而不仅是 schema 理解。

后续若只保留一个 ours no-RLM 生成方法，应优先保留该方法。

## 实验 8：Ours Full Workspace

### 实验是什么

`bird_ours_full_workspace_500` 在 metadata + enrichment + probe 基础上启用 full workspace，把更多上下文和中间信息放入工作区。

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 样本数 | 500 |
| metadata | 开启 |
| enrichment | 开启 |
| probe queries | 开启 |
| workspace | 开启 |

### 变量

| 变量 | 当前设置 |
|---|---|
| workspace | full workspace |
| prompt version | `workspace` |

### 数据与结果

| total | correct | accuracy | avg latency |
|---:|---:|---:|---:|
| 500 | 255 | 0.510 | 17.7574s |

### 分析

full workspace 准确率与 baseline 2 一样：

```text
0.510 vs 0.510
```

但延迟约为 baseline 2 的 4.8 倍：

```text
17.7574 / 3.6926 ≈ 4.81
```

因此，当前版本的 workspace 不应继续作为主实验。它说明“更大上下文”不等于更好效果。后续如果继续使用 workspace，应改成：

```text
conditional workspace
compact evidence workspace
只在失败题启用 workspace
```

## 实验 9：Candidate Ensemble + SQL Repair

### 实验是什么

candidate ensemble 不是新的 SQL 生成模型，而是把多个已生成 SQL 候选放在一起执行，然后选择最可信的一个。

默认候选包括：

```text
results/bird_b2_500.json
results/bird_ours_metadata_enrichment_500.json
results/bird_ours_metadata_enrichment_probe_500.json
```

当前实现还加入 SQL repair loop：

```text
--repair-attempts 1
--repair-empty-results
```

即如果候选 SQL 报错或返回空结果，则最多修复 1 轮，并把修复后的 SQL 作为新候选。

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 数据库 | SQLite |
| 候选来源 | baseline 2, metadata enrichment, metadata enrichment probe |
| 选择方式 | execution-aware verifier |
| repair | 默认 1 轮 |

### 变量

| 变量 | 可测设置 |
|---|---|
| repair attempts | `0, 1, 2` |
| candidate files | baseline 2 / enrichment / probe / RLM candidate |
| verifier | 开启或关闭 |

### 当前数据

已完成 overlap 分析，结果为：

| 指标 | 数值 |
|---|---:|
| baseline 2 correct | 255 / 500 |
| metadata enrichment correct | 262 / 500 |
| metadata enrichment + probe correct | 268 / 500 |
| oracle union upper bound | 318 / 500 = 0.636 |
| all-correct intersection | 203 / 500 = 0.406 |
| baseline 2 correct but probe wrong | 40 |
| probe correct but baseline 2 wrong | 53 |

### 当前结果

截至本文档记录时，ensemble + repair 已实现，但 50 / 500 条正式结果尚未记录到总表。

### 分析

oracle union 上限 `0.636` 显著高于当前最强单一方法 `0.536`，说明多个候选之间确实互补。候选集合里有更多正确 SQL，问题变成如何选择。

该实验适合作为工程增强方法，但它不能直接证明 RLM 有用。若论文主问题是 RLM 是否有效，ensemble 应作为附加方法，而不是主证明。

## 实验 10：RLM 控制变量实验

### 实验是什么

为了回答“RLM 加在 agent 里是否有用”，需要严格比较：

```text
同一 agent
同一 prompt family
同一 metadata/probe 设置
唯一变量：use_recursion 开或关
```

当前 suite 已经修正为以下命名：

```text
bird_ours_basic_no_rlm_500
bird_ours_basic_rlm_500
bird_ours_metadata_enrichment_probe_no_rlm_500
bird_ours_metadata_enrichment_probe_rlm_500
```

### 固定量

| 固定量 | 设置 |
|---|---|
| 数据集 | BIRD Mini-Dev |
| 数据库 | SQLite |
| agent | `scripts/run_ours.py` |
| metric | execution accuracy |
| 对比方式 | paired ablation |

### 变量

| 对比组 | 固定条件 | 唯一变量 |
|---|---|---|
| basic no-RLM vs basic RLM | `prompt-version basic`, no metadata/probe | `--no-recursion` vs `--use-recursion` |
| probe no-RLM vs probe RLM | metadata + enrichment + probe | `--no-recursion` vs `--use-recursion` |

### 当前结果

严格的 metadata + enrichment + probe 对照已完成 50 条：

| 方法 | 正确数 | 准确率 | 平均延迟 |
|---|---:|---:|---:|
| no-RLM | 31 / 50 | 0.620 | 2.4938 秒 |
| RLM | 29 / 50 | 0.580 | 3.2419 秒 |

配对比较中，`both correct=29`、`no-RLM only=2`、`RLM only=0`、`both wrong=19`。RLM 净收益为 `-2` 题（`-4.00%`），且延迟更高。因此，当前 50 条实验不支持“RLM 能直接提高该 agent 准确率”的假设。

该组尚未完成 500 条结果。历史 `bird_ours_basic_500` 不能作为 RLM 结果，因为它实际使用了 `--no-recursion`。

### 50 条建议命令

Basic no-RLM：

```powershell
python scripts\run_ours.py `
  --dataset data\processed\bird_mini_dev_questions.json `
  --database-dir data\databases `
  --limit 50 `
  --no-recursion `
  --prompt-version basic `
  --output results\bird_ours_basic_no_rlm_50.json
```

Basic RLM：

```powershell
python scripts\run_ours.py `
  --dataset data\processed\bird_mini_dev_questions.json `
  --database-dir data\databases `
  --limit 50 `
  --use-recursion `
  --prompt-version basic `
  --output results\bird_ours_basic_rlm_50.json
```

Probe no-RLM：

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

Probe RLM：

```powershell
python scripts\run_ours.py `
  --dataset data\processed\bird_mini_dev_questions.json `
  --database-dir data\databases `
  --limit 50 `
  --use-recursion `
  --use-metadata `
  --use-enrichment `
  --use-probe-queries `
  --prompt-version basic `
  --output results\bird_ours_metadata_enrichment_probe_rlm_50.json
```

严格对照只运行上面的 Probe no-RLM / RLM 两组。也可以使用 suite 一次运行并评估：

```powershell
python scripts\run_bird_full_suite.py --limit 50 --only-rlm-ablation
```

两组均固定使用相同的数据前 50 条、模型、迭代预算、metadata、enrichment、
probe 和 `prompt-version basic`。唯一实验变量是是否启用
`answer_subquestion()` 递归工具。

运行结束后，汇总与逐题配对表保存在：

```text
results/bird_rlm_ablation_50.txt
```

配对部分会列出 `both correct`、`no-RLM only`、`RLM only`、`both wrong`
以及 RLM 的净增正确题数和准确率差。

评估：

```powershell
python scripts\evaluate_results.py --result-files `
  results\bird_ours_basic_no_rlm_50.json `
  results\bird_ours_basic_rlm_50.json `
  results\bird_ours_metadata_enrichment_probe_no_rlm_50.json `
  results\bird_ours_metadata_enrichment_probe_rlm_50.json
```

## 当前结论

### 已能确定的结论

1. `baseline_2_direct_text_to_sql` 是当前最强基础 baseline，准确率 `0.510`，平均延迟 `3.6926s`。
2. 非递归 agent baseline 更慢且更低准，不建议作为主线。
3. metadata 是必要信息，能把 basic no-RLM 从 `0.266` 提升到 `0.510`。
4. enrichment 和 probe 有增益，probe 版本达到 `0.536`，是当前最佳单一 ours 结果。
5. full workspace 没有提升准确率，后续不应继续主测。
6. 多候选 oracle union 上限达到 `0.636`，说明 candidate selection 有潜在空间。
7. 旧的 `bird_ours_basic_500` 不是 RLM 结果，不能用来判断 RLM 是否有效。
8. 50 条严格配对中，RLM 从 `0.620` 降至 `0.580`，并增加约 `30%` 延迟；当前配置下没有准确率收益。

### 还不能下结论的部分

1. RLM 在完整 500 条上的效果：50 条 pilot 为负结果，仍需完整实验确认统计结论。
2. ensemble + repair 是否提升最终分数：需要跑 50 条和 500 条正式结果。
3. conditional RLM 是否比 full RLM 更划算：尚未实现或记录。

## 后续建议实验顺序

### 第一优先级：RLM 是否有效

先跑 50 条：

```text
bird_ours_basic_no_rlm_50
bird_ours_basic_rlm_50
bird_ours_metadata_enrichment_probe_no_rlm_50
bird_ours_metadata_enrichment_probe_rlm_50
```

每个结果文件跑完后，都需要生成错误分析报告，记录失败原因：

```powershell
python scripts\analyze_result_errors.py `
  --result-file results\bird_ours_metadata_enrichment_probe_rlm_50.json `
  --output-md results\bird_ours_metadata_enrichment_probe_rlm_50_error_analysis.md `
  --output-json results\bird_ours_metadata_enrichment_probe_rlm_50_error_summary.json
```

如果 RLM 在 50 条上有明显提升，再跑 500 条。

### 第二优先级：candidate ensemble + repair

在已有 500 条候选结果基础上跑：

```text
bird_ours_candidate_ensemble_50_repair
```

如果超过 `metadata_enrichment_probe`，再跑 500 条。

### 暂停主测的实验

以下实验不建议继续作为主实验跑 500 条：

```text
baseline_3_non_recursive_db_agent
bird_ours_basic_500 历史 no-RLM basic
bird_ours_metadata_500
bird_ours_full_workspace_500
```

这些可以保留在报告中作为消融结果，但不应继续消耗主要实验预算。
