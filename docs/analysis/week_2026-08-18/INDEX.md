# 本周文档索引（2026-08-18 → 08-24）

## 按阅读顺序

| # | 文档 | 讲什么 |
|---|---|---|
| 1 | [`five_layer_chain_results_2026-08-19.md`](five_layer_chain_results_2026-08-19.md) | **主结果**：五层对照链、推理量指标、错误分类。§六 是通俗版结论，§七 是下一步 |
| 1' | [`five_layer_chain_results_2026-08-19.en.md`](five_layer_chain_results_2026-08-19.en.md) | 同上的英文版（内容一一对应） |
| 2 | [`WEEK_PLAN_2026-08-20.md`](WEEK_PLAN_2026-08-20.md) | 下周计划、优先级与理由 |
| 3 | [`harness_defects_2026-08-18.md`](harness_defects_2026-08-18.md) | 三个 harness 缺陷，及由此产生的数字更正 |
| 4 | [`run_config_audit_2026-08-18.md`](run_config_audit_2026-08-18.md) | 66 个运行的配置逐字段核对结果 |
| 5 | [`reruns_2026-08-20.md`](reruns_2026-08-20.md) | 四项历史消融在修正数据集上重跑：Hint 消融、指代歧义、E6 递归、prompt 教约定 |
| 6 | [`disambiguation_recheck_2026-08-20.md`](disambiguation_recheck_2026-08-20.md) | 指代歧义 7 道题的题面/gold 变动诊断 |

只想看一个的话，看 1；只想知道下一步做什么，看 2。

## 本周的三个主要结论

1. **16.7pp 总增益里 13.4pp 在第 1 层。** 按 RLM 三机制归位：可执行环境 + 自我改进
   +13.4pp，程序化探索（弱化版）+2.5pp，分而治之 +0.3pp（误差内）。
   收益极不均衡，不是没有收益。
2. **模型犯两种错，方向相反。** 「不知道自己错了」（约定类，91 道）推理量比答对的题
   还低 20%；「没想明白」（424 道）是 2 倍。方法栈和推理预算只消灭后者，前者纹丝不动。
3. **噪声带实测 0.2~1.4pp。** 此前记的「1~2pp」两个来源都不成立
   （一对差在 `max_iterations`，一对崩溃数不等）。

## 本周修掉的东西

- 控制台编码崩溃（cp936）：111 道题被静默判错，已修并重跑
- 84.5% → **86.7%**（arcwise 全集）、rc_ctl 87.0% → **89.2%**、rc_trt 87.7% → **89.9%**
- 「RLM 递归」这个窄表述：RLM 是三个机制，已在 `config_inventory` §六 更正

## 仍未修（下周第一件事）

- 异常误分类：harness 崩溃仍被静默记为模型答错
- `evidence=None` 导致的 `AttributeError`（`bird_1507`、`bird_1528`）
- `BadRequestError` 37 条未诊断

## 相关但不在本文件夹的

这些是本周产生或本周更新、但归属别处的文档：

- [`../config_inventory_2026-08-17.md`](../config_inventory_2026-08-17.md) —— 配置清单，§六 已按三机制更正
- [`../NEXT_PHASE_PROMPT.md`](../NEXT_PHASE_PROMPT.md) —— 阶段交接说明，已同步更正
- [`../failure_adjudication_final_2026-08-16.md`](../failure_adjudication_final_2026-08-16.md) —— §「全集 84.5% 不可引用」已更正数值
- [`../reasoning_trace_findings_2026-08-18.md`](../reasoning_trace_findings_2026-08-18.md)、
  [`../WEEKLY_REPORT_2026-08-18.md`](../WEEKLY_REPORT_2026-08-18.md) 及
  `../WEEKLY_REPORT_0811_0818*.md` —— 另一批本周文档，留在原处未移动

## 术语（2026-08-20 厘清）

此前 "harness" 一词同时指两个边界完全不同的东西，第 3 层"算不算方法的一部分"说不清即源于此。
分界线不是谁写的代码，而是**能不能改变预测**：

| 中文 | English | 指什么 | 能改变预测吗 |
|---|---|---|---|
| **评测框架** | evaluation harness | runner、`run_manifest`、`transcripts.jsonl`、判分 | **不能——能就是缺陷** |
| **被测系统 / 脚手架** | system under test / agent scaffold | 工具循环、离线检索、递归 | 能，必须可消融 |
| **输出后处理** | output post-processing | SQL 约定改写（第 3 层） | 能，必须可消融 |

由此，异常误分类那个缺陷可以说得更准：**评测框架改变了它本该只观测的结果——
测量仪器污染了测量。** 这不是"有个 bug"，是违反了 harness 的定义性约束，
也解释了它为何难被发现：它伪装成被测对象的属性。

已执行的更名：`harness_convention_rules_2026-08-16.md` →
[`../sql_postprocessing_rules_2026-08-16.md`](../sql_postprocessing_rules_2026-08-16.md)；
文档与判读数据里的 `harness 改写` / `harness改写` → `后处理改写`；
代码注释同步。`harness_defects_2026-08-18.md` **未改名**——那三个缺陷确实都在评测框架里。

## 本周新增的脚本

| 脚本 | 用途 |
|---|---|
| [`../../../shared/console.py`](../../../shared/console.py) | 编码修复；**任何新的 agent 入口都必须调用 `force_utf8_console()`** |
| [`../../../scripts/purge_harness_crash_records.py`](../../../scripts/purge_harness_crash_records.py) | 删掉崩溃记录，让 resume 重跑它们 |
| [`../../../scripts/rescore_against_corrected_gold.py`](../../../scripts/rescore_against_corrected_gold.py) | 按修正 gold 重评旧运行 |
| [`../../../scripts/triage_failure_causes.py`](../../../scripts/triage_failure_causes.py) | 失败分诊；只出可复算的事实，不出结论 |
| [`../../../scripts/reasoning_step_stats.py`](../../../scripts/reasoning_step_stats.py) | 推理步数/推理量统计 |
| [`../../../scripts/audit_run_configs.py`](../../../scripts/audit_run_configs.py) | 逐字段核对运行配置；**`cfg_sha` 两个方向都不可靠，比较前用它** |
