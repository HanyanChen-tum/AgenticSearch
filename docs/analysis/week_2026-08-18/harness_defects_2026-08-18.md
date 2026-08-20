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

## 二、异常误分类（**未修**）

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

**编码崩溃只是撞上这个漏洞的第一个实例。** 建议改为：显式列出**算作模型结果**的异常
（实际上只有 `MaxIterationsError` 一类），其余记 `scored: false` 并排除出计分，
而不是无声地变成 `correct: false`。这样以后任何新 bug 表现为「样本量少了几道」——看得见；
而不是「准确率低了两个点」——看不见。

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

### 4.2 仍被压低、尚未重跑的

以下运行仍含编码崩溃记录，其在 `config_inventory_2026-08-17.md` 中的数字**偏低**，
偏低幅度未量化，引用时必须注明：

| 运行                                 | 崩溃数 |
| ------------------------------------ | -----: |
| `e3_c_rules_reasoning_dev500_run1` |     16 |
| `e3_c_conv_rules_v2_dev500_run1`   |     14 |
| `e3_c_semantic_dev500_run1`        |      8 |

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

## 五、尚未完成

1. 第二条（异常误分类）**仍未修**，在计分路径上——五层链已跑完，链本身不再是阻塞理由，
   但改动会让所有已发布数字的分母同步变化，需要一次性处理、同步更正引用
2. `BadRequestError`（33 条）尚未诊断——37 道题各出现一次、无重复，形状像零散基础设施抖动而非
   确定性故障，暂按事后审计 `termination` 分布处理，不建议在未查清前动代码

## 涉及文件

- [`shared/console.py`](../../../shared/console.py) —— 编码修复
- [`scripts/purge_harness_crash_records.py`](../../../scripts/purge_harness_crash_records.py) —— 删崩溃记录以便 resume 重跑
- [`scripts/rescore_against_corrected_gold.py`](../../../scripts/rescore_against_corrected_gold.py) —— 按修正 gold 重评
- [`scripts/triage_failure_causes.py`](../../../scripts/triage_failure_causes.py) —— 失败分诊（只出可复算的事实，不出结论）
