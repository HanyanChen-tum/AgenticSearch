# Harness 缺陷与由此产生的数字更正（2026-08-18）

本轮在准备推理轨迹阶段时，先查了一遍正在跑的实验，发现三个 harness 缺陷。
它们都不改变模型的能力，但都以「模型答错」的形式进入了已发表的数字。
本文记录缺陷本身、影响范围、已修与未修的部分，以及需要更正的具体数值。

---

## 一、控制台编码崩溃（已修）

**机制。** 本机 `sys.stdout.encoding` 是 `gbk`（ANSI 代码页 cp936），仓库里没有
`PYTHONUTF8` / `PYTHONIOENCODING` / `reconfigure()`。而
[`ours/recursive_db_rlm.py:504`](../../../ours/recursive_db_rlm.py) 打印模型回复、
[`:610`](../../../ours/recursive_db_rlm.py) 打印 REPL 输出（含数据库行），**两处都无 verbose 开关**。
数据库行里只要有一个 cp936 编不出的字符，`print()` 就抛 `UnicodeEncodeError`。

**为什么会变成答错。** 见下面第二条——异常穿出 `complete_sql` 后被当作模型的真实失败，
`predicted_sql=""`、`correct=False`，并作为**已完成记录**落盘；resume 跳过已完成记录，
所以它永远不会自我纠正。

**证据。** `bird_847` 的 trace 事件：

```json
{"tool": "db.execute",
 "arguments": {"sql": "SELECT d.surname FROM qualifying AS q JOIN drivers AS d ... LIMIT 1;"},
 "result": {"columns": ["surname"], "rows": [["Räikkönen"]], "error": null}}
```

模型查对了，`ä` 编不进 cp936，于是这道题记为答错。

**它有选择性，不是随机噪声。** 被杀的是**答案本身含非拉丁字符**的题，按数据库高度集中：
`card_games` 12%、`formula_1` 8%、`debit_card_specializing` 7%。
典型被杀值：`Räikkönen`、`Häkkinen`、`São Paulo`、`1. FC Köln`、`AS Saint-Étienne`、
`Élu de l'Ancêtre`、`갈등`、`Autoprísluš.`。
因此它同时扭曲总分**和**任何按数据库、按难度的分层分析。

**修复。** 新增 [`shared/console.py`](../../../shared/console.py) 的 `force_utf8_console()`，
在流层面把 stdout/stderr 重配为 `utf-8` + `errors="replace"`，
已接入全部 5 个驱动 agent 的入口脚本。**任何新入口都必须调用它。**

已写入的记录不会自动重跑（resume 会跳过），需用
[`scripts/purge_harness_crash_records.py`](../../../scripts/purge_harness_crash_records.py) 先删再跑。

---

## 二、异常误分类（**已修，2026-08-21**）

[`scripts/run_bird_indomain_fewshot.py:66-74`](../../../scripts/run_bird_indomain_fewshot.py)：

```python
except Exception as e:
    termination = type(e).__name__
    # Retry infra failures; model failures (MaxIterations etc.) are real results
    if attempt < 2 and any(s in termination for s in ("API", "Connection", "Timeout")):
        ...continue
    break
```

用**异常类名的子串白名单**区分「基础设施故障」与「模型能力结果」。
凡类名不含 `API`/`Connection`/`Timeout` 的，一律不重试、记为 `correct=False`。

方向是反的：它枚举了要重试的故障，然后默认「其余都是模型的真实失败」；
而实际上未预料的异常绝大多数是我们自己的代码崩了。全仓审计：

| termination                     | 条数 | 重试 | 记为模型答错                                                               |
| ------------------------------- | ---: | ---- | -------------------------------------------------------------------------- |
| `NotFoundError`               |  200 | 否   | **是**（197 条集中在 `e3_c_schema_v4_core197_run2`，该跑整体失效） |
| `UnicodeEncodeError`          |   66 | 否   | **是**                                                               |
| `BadRequestError`             |   33 | 否   | **是**                                                               |
| `APIError`                    |   33 | 是   | 否                                                                         |
| `MaxIterationsError`          |   19 | 否   | 是（**分类正确**，模型确实未收敛）                                   |
| `TimeoutError`                |   13 | 是   | 否                                                                         |
| `AttributeError`              |    6 | 否   | **是**                                                               |
| `ContentPolicyViolationError` |    1 | 否   | **是**                                                               |

**编码崩溃只是撞上这个漏洞的第一个实例。**

**修复（2026-08-21）**：方向按建议反过来了。[`shared/evaluator.py`](../../../shared/evaluator.py)
新增 `MODEL_TERMINATIONS = frozenset({"final", "MaxIterationsError"})` 和 `is_scored()`——
显式列出**算作模型结果**的两种终止方式，其余一律记 `scored: false`。三个 `run_one()` 实现
（`run_bird_indomain_fewshot.py`、`run_bird_ours.py`、`baselines/run_bird_b{1,2}_azure.py`，
后两个此前完全没有 `termination` 概念，本次一并补上）都写入这个字段。`correct` 字段保留原样
（崩溃记录仍是 `correct: false`，这本身没错——它确实没答对），但任何准确率计算现在必须先按
`scored` 过滤，不能直接对 `correct` 取平均。

**全仓回填**：新增 [`scripts/backfill_scored_field.py`](../../../scripts/backfill_scored_field.py)，
给 86 个既有结果文件补上 `scored`（不重跑，纯粹是 `termination` 的确定性函数）。四个 B1/B2 文件
没有 `termination` 字段（比这次修复更老），用唯一可靠的信号回填：`predicted_sql` 非空说明 LLM
调用本身成功过，记 `termination="final"`；这批文件里没有一条 `predicted_sql` 为空，所以回填无歧义。

**验证**：用回填后的 `scored` 字段重算五层链（491 题共同可计分集），**六个数字与更正前逐一相同**——
说明分析时手动排除 `UnicodeEncodeError` 等已知崩溃类型的口径，从一开始就是对的；
这次修复没有改变任何已发布数字，只是把原来靠人工记忆的排除规则固化进了数据 schema。

**顺带发现**：B1/B2 修正数据集的四次运行也踩了 `evidence=None`（`bird_1507`/`bird_1528`），
之前完全没被发现——因为这两个脚本连 `termination` 字段都没有，旧的 `HARNESS` 审计方法
（按 `termination` 分组统计）根本看不到它们。修复后重跑：B1 70.3%/70.1% → **70.5%/70.3%**，
B2 66.7%/67.7% → **66.9%/67.9%**（各 +0.2pp）。

---

## 三、`evidence` 为 `None` 导致的崩溃（**已修，2026-08-20**，修正数据集引入的回归）

链条三处：

1. [`scripts/build_corrected_dev500.py:66`](../../../scripts/build_corrected_dev500.py)
   写 `"evidence": rec.get("evidence")`，**保留了 `None`**
2. [`scripts/run_bird_indomain_fewshot.py:64`](../../../scripts/run_bird_indomain_fewshot.py)
   传 `evidence=example.get("evidence", "")` —— `.get(k, default)` 只在**键不存在**时给默认值，
   键存在而值为 `None` 时照样返回 `None`
3. [`ours/recursive_db_rlm.py:102`](../../../ours/recursive_db_rlm.py) 与
   [`:123`](../../../ours/recursive_db_rlm.py) 调 `evidence.strip()` → `AttributeError`

| 数据集                    |                        `evidence is None` | `evidence == ""` |
| ------------------------- | ------------------------------------------: | -----------------: |
| 原始`bird_dev_500.json` |                                           0 |                  2 |
| 修正版 498                | **2**（`bird_1507`、`bird_1528`） |                  0 |

原始数据集这两题的 evidence 是空字符串，`.strip()` 正常；修正版把它变成 `None`。

**修复（2026-08-20）**：`run_bird_indomain_fewshot.py` 的 `.get("evidence", "")` 改为 `.get("evidence") or ""`；`recursive_db_rlm.py` 两处 `evidence.strip()` 改为 `(evidence or "").strip()`。冒烟测试 `bird_1507`、`bird_1528` 均 `final`，2/2 答对。详见 [`reruns_2026-08-20.md`](reruns_2026-08-20.md)。
所以该缺陷**只在修正数据集的运行上出现**——观测到的 6 条 `AttributeError` 全部来自
三个修正数据集运行（noconv、conv-rules、arcwise），原始数据集运行一条都没有。

仓库里早有正确写法（`build_decision_paths.py`、`counterfactual_decision.py`、
`locate_first_wrong_sentence.py` 等 6 处都用 `r.get("evidence") or ""`），只有 runner 用错。

**修法：改消费端，不要改数据源。** 改 `build_corrected_dev500.py` 重新生成数据集会改变
`dataset_sha256`，链上所有 manifest 的配置校验失败，已跑完的全部作废。

---

## 四、需要更正的数字

### 4.1 已修复并重跑的

| 运行                              | 口径                | 原记录 | **更正后** |
| --------------------------------- | ------------------- | -----: | ---------------: |
| `e3_c_arcwise_full_dev500_run1` | 修正全集 498        |  84.5% |  **86.7%** |
| `e3_c_rc_ctl_dev500_run1`       | 干净 277，原 gold   |  82.3% |  **84.1%** |
| `e3_c_rc_ctl_dev500_run1`       | 干净 277，修正 gold |  87.0% |  **89.2%** |
| `e3_c_rc_trt_dev500_run1`       | 干净 277，原 gold   |  82.7% |  **84.5%** |
| `e3_c_rc_trt_dev500_run1`       | 干净 277，修正 gold |  87.7% |  **89.9%** |

两个推理捕获臂各涨 **+2.2pp**，全部来自崩溃题被真实作答。

| 运行 | 原记录 | **更正后** |
|---|---:|---:|
| B1 修正数据集 run1 / run2 | 70.3% / 70.1% | **70.5% / 70.3%** |
| B2 修正数据集 run1 / run2 | 66.7% / 67.7% | **66.9% / 67.9%**（2026-08-21，`evidence=None` 修复，见 §二）|

### 4.2 已补跑两个，一个不可复现（2026-08-18 补跑，此处 2026-08-21 补记）

| 运行 | 原记录 | 状态 |
|---|---:|---|
| `e3_c_rules_reasoning_dev500_run1` | 65.8%（16 崩溃） | **已补跑 → 67.2%**（0 崩溃，500/500） |
| `e3_c_conv_rules_v2_dev500_run1` | 65.4%（14 崩溃） | **已补跑 → 67.2%**（0 崩溃，500/500） |
| `e3_c_semantic_dev500_run1` | 64.2%（8 崩溃） | **补不了**：`agent_config_sha256` 已随 profile 定义变更漂移，当前代码无法复现该次运行的确切配置。已把 8 条崩溃记录删除，剩 492 道均为真实作答，**65.2%（492/492）可引用**，但样本数与其余 500 题运行不同，逐题并列时需取交集 |

已确认**无**崩溃、数字可直接引用的：`legacy_e0_dev500_run1`、`e3_c_recursive_dev500_run1`、
`clean_e0_dev500_run1`、`e3_c_conv_dev500_run1`、`e3_c_conv_rules_dev500_run1`、
`e3_c_conv_rules_dev500_iter15`、B1/B2 各两次。

### 4.3 噪声带：原来的两个估计都不成立

`config_inventory_2026-08-17.md` §一 用两组重复给出「同配置噪声约 1~2pp」。两组都有问题：

| 组                                     | 原估计 | 问题                                                                                                             |
| -------------------------------------- | -----: | ---------------------------------------------------------------------------------------------------------------- |
| `03c10637` run1 vs iter15            |  1.1pp | **不是同配置**：`max_iterations` 为 8 vs 15。该字段不进 `agent_config_sha256`，所以 sha 相同但配置不同 |
| `e5435e07` rc_ctl vs rules_reasoning |  1.8pp | 两个文件崩溃数不等（现分别为 0 与 16），差值含编码 bug                                                           |

**唯一干净的同配置重复**是本轮新得到的：`e3-c-conv-rules`（sha `671e8010`）
在修正数据集上两次独立完整运行，均已修复且 `max_iterations` 同为 8：

|                                          |        全集 498 | 剔除 harness 崩溃的 480 |
| ---------------------------------------- | --------------: | ----------------------: |
| `chain_e3_c_conv_rules_corrected_run1` |           86.7% |                   87.7% |
| `e3_c_arcwise_full_dev500_run1`        |           86.7% |                   87.7% |
| **聚合差距**                       | **0.0pp** |         **0.0pp** |

**但逐题翻转 20/480。** 聚合完全重合是正负抵消，不是单题稳定。
两条都要报：配置级比较可以用很紧的尺子，**逐题因果分析不能拿这个 0.0pp 当保证**。

这条更正的后果：此前因「小于 1~2pp 噪声带」而被判为读不出的差异，需要重新审视。
例如第 2→3 层（convention 后处理）在修正全集 498 上是 **+1.4pp**（7 道，赢 20 输 13），
在旧尺子下读不出，现在可读——但赢输双向说明它不是净增益机制。

---

## 五、`BadRequestError` 诊断（2026-08-20）——Azure 内容安全策略误判，不是基础设施抖动

全部 37 条错误消息一致：

```
litellm.BadRequestError: AzureException BadRequestError - Invalid prompt:
your prompt was flagged as potentially violating our usage policy.
```

不是 token 超限、不是限流，是 Azure 的内容安全分类器判定这次请求违规。数据库分布高度集中：

| db_id | 命中数 |
|---|---:|
| `thrombosis_prediction` | 7 |
| `card_games` | 7 |
| `european_football_2` | 5 |
| `formula_1` | 4 |

`card_games` 是卡牌 flavor text（此前编码 bug 调查里见过 `Diacre infâme`、`Insurreição` 这类带黑暗奇幻主题的文本），`thrombosis_prediction` 是医疗数据——两个都是"内容本身可能触发分类器、但对 SQL 任务完全无害"的数据库，与 `UnicodeEncodeError` 当时命中的高危库高度重合，不是巧合。

逐条查了 `chain_clean_e0_corrected_run1` 里的 `bird_345`：题面、hint、前几轮的工具调用结果（`Legal`/`Restricted`/`Banned`、一条 SQL 语法错误提示）**全部肉眼看不出违规内容**，触发点大概率藏在 7477 字符的完整 schema 转储更深处（未逐字符扫描），或者是分类器本身的概率性判定——这一层排查到此为止，继续深挖性价比不高。

**影响范围**：37 条里 **6 条落在当前正在使用的结果文件**（`chain_clean_e0_corrected_run1`、`chain_e3_c_noconv_corrected_run2`、`e3_c_arcwise_full_dev500_run1`、`e3_c_rc_trt_dev500_run1`），其余分布在已排除的旧运行（`bird_nofs_rhigh_500` 等 9 个不可用运行）。绝对数量小，不改变任何已报告的层间结论。

**建议处置**：与 `TimeoutError`/`APIError` 同类对待——排除出计分，而不是retry。**不建议重试**：这是内容驱动的拒绝，同样的 prompt 重试大概率原样再被拒一次，重试消耗的是配额不是修复问题。真正的修复需要在送入 API 前对 schema/sample 内容做检测或改写，超出当前范围，留作后续。

## 六、尚未完成

第一至三条已修，第五条已诊断。剩下的：

1. **回填后的 `scored` 字段还没有反向传播进各分析文档**——五层链、`config_inventory`
   等文档目前引用的数字都是修复前手动排除口径算出来的，与回填后重算的结果逐一相同（见第二条
   的验证），所以数值本身不用改，但文档里"如何排除 harness 崩溃"的方法论描述可以统一改成
   "过滤 `scored=False`"，不必再重复列举异常类名
2. 第五条诊断出的 `BadRequestError` 尚未在计分逻辑里落地为 `scored: false`——它符合
   `is_scored()` 的判定（不在 `MODEL_TERMINATIONS` 里），新跑的运行会自动排除；
   已有的 6 条已通过回填脚本标记，无需额外动作

## 涉及文件

- [`shared/console.py`](../../../shared/console.py) —— 编码修复
- [`scripts/purge_harness_crash_records.py`](../../../scripts/purge_harness_crash_records.py) —— 删崩溃记录以便 resume 重跑
- [`scripts/rescore_against_corrected_gold.py`](../../../scripts/rescore_against_corrected_gold.py) —— 按修正 gold 重评
- [`scripts/triage_failure_causes.py`](../../../scripts/triage_failure_causes.py) —— 失败分诊（只出可复算的事实，不出结论）
