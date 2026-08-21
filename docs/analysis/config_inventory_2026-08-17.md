# 可用配置清单与重跑计划（2026-08-17）

外部修正版 gold 让本项目的配置排名大幅重排，所以在设计下一轮对比前，先厘清
**哪些运行的配置是可确认的**、**同配置重复的噪声有多大**、**哪些必须重跑**。

---

> **2026-08-18 更正。** 本节的噪声带估计已被推翻，`e3-c-rc-ctl` / `e3-c-rc-trt` /
> `e3_c_arcwise_full` 的数字已更新，另有三个运行仍被 harness 缺陷压低。
> 详见 [`harness_defects_2026-08-18.md`](week_2026-08-18/harness_defects_2026-08-18.md)。

## 一、噪声带：先量它，否则读不出任何差异

同一配置跑两次，在 278 道干净子集（修正 gold）上的差距：

| 配置 | cfg_sha | 两次运行 | 差距 |
|---|---|---|---:|
| `e3-c-conv-rules` | `03c10637dc9a` | run1 87.0% / iter15 85.9% | **1.1pp** |
| `e3-c-rules-reasoning` | `e5435e0700bc` | rc_ctl 87.0% / rules_reasoning 85.2% | **1.8pp** |

~~**同配置噪声约 1~2pp。**~~ **2026-08-18 推翻：上表两组重复都不是干净的同配置重复。**

| 组 | 原估计 | 问题 |
|---|---:|---|
| `03c10637` run1 vs iter15 | 1.1pp | **不是同配置**：`max_iterations` 为 8 vs 15。该字段不进 `agent_config_sha256` |
| `e5435e07` rc_ctl vs rules_reasoning | 1.8pp | 两文件编码崩溃数不等（0 与 16），差值含 harness bug |

唯一干净的同配置重复（`671e8010`，修正数据集，两次完整运行，均已修复，`max_iterations` 同为 8）：
**两次都是 86.7%，聚合差距 0.0pp**；剔除 harness 崩溃的 480 题上两次都是 87.7%。

**但逐题翻转 20/480。** 配置级比较可以用很紧的尺子；
**逐题因果分析不能拿这个 0.0pp 当稳定性保证。**

这两组重复是偶然存在的（同一配置被跑过两次），不是设计出来的。下一轮应当**每个配置至少两次**，
让噪声带成为测量的一部分而不是事后发现的。

## 二、可写进文档的配置（有 cfg_sha + manifest + trace）

278 道干净子集（题面与 evidence 未被修正版改动），原始 gold → 修正 gold：

| 配置 | cfg_sha | 运行 | 原 gold | 修正 gold | 变化 |
|---|---|---|---:|---:|---:|
| `legacy-e0` | `40fcce2b4c64` | legacy_e0_run1 | 83.0% | **89.2%** | +17 |
| `e3-c-recursive` | `0d60da3313f7` | e3_c_recursive_run1 | 81.6% | **90.3%** | **+24** |
| `e3-c-toolconfirm-reasoning` | `a5eb47bf1e5d` | rc_trt | 82.7% | 87.7% | +14 |
| `e3-c-conv-rules` | `671e8010a65c` | v2（关掉两条改写规则） | 81.9% | 87.7% | +16 |
| `e3-c-conv-rules` | `03c10637dc9a` | run1 / iter15 | 86.3% / 83.9% | 87.0% / 85.9% | +2 / +5 |
| `e3-c-rules-reasoning` | `e5435e0700bc` | rc_ctl / rules_reasoning | 82.3% / 83.8% | 87.0% / 85.2% | +13 / +4 |
| `clean-e0` | `b35611609e5c` | clean_e0_run1 | 80.1% | 87.0% | +19 |
| `e3-c-semantic` | `9e8888b4c6d5` | e3_c_semantic_run1 | 81.6% | 86.6% ⚠️ | +14 |
| `e3-c-conv` | `1a372781e175` | e3_c_conv_run1 | 81.9% | 84.1% | +6 |

### 两个必须记录的翻转

**`e3-c-conv-rules` 的领先没有了。** 原始 gold 上它 86.3% 排第一；修正 gold 上 87.0%，
而 `clean-e0` 基线同为 87.0%、`legacy-e0` 89.2%、`e3-c-recursive` 90.3%。
它只涨 +2，别人涨 +17~+24——**此前的领先有相当部分来自更好地拟合了坏 gold**，
与 `count_no_distinct` 规则烂掉的机制相同（见 `sql_postprocessing_rules_2026-08-16.md`）。

**`e3-c-recursive` 涨 +24，是全场最大。** 该配置此前被判定为"递归没用"，
那个结论建立在原始 gold 上。+24 远超 1~2pp 的噪声带，**需要重跑确认**。

## 三、B1 / B2：可用，且是唯一的"零方法"参照点

初版把这两个也划进了排除组，理由是"全部走 in-domain 检索路径"——**对这两个不成立**，
这是初版的一处错误。

| | B1 / B2 | 其余 7 个 |
|---|---|---|
| method | `bird_baseline_1_azure` / `_2_azure` | `bird_indomain_fewshot_db_rlm` |
| 实现 | `baselines/run_bird_b1_azure.py`（脚本尚在） | agent 框架 |
| 检索 | **无** —— docstring：*No exploration, no self-correction, no retries. One shot: question + schema → SQL* | in-domain 检索（出过泄漏事故） |

**它们不读 dev 池，泄漏问题与之无关。** 而且是纯单次生成，正是"在本项目做任何事之前，
模型加全 schema 能到多少"的参照点。

| 运行 | 干净子集 原→修正 |
|---|---:|
| bird_b1_azure_500 | 69.3% → **76.9%**（+21） |
| bird_b2_azure_500 | 64.6% → 68.2%（+10） |

B2 = B1 + 关键词表预筛，findings.md 记为 −3.6pp；修正 gold 上差距扩大到 −8.7pp，
**方向一致、幅度更大**，该结论稳。

仍缺 `agent_config_sha256`（脚本早于 manifest 机制），但脚本在、无检索、可复现，
**建议重跑一次补上指纹**，而不是排除。

## 三点五、不可用的 7 个运行

| 运行 | 干净子集 原→修正 |
|---|---:|
| bird_nofs_rhigh_500 | 85.2% → **91.3%** |
| bird_trainfs_rhigh_500 | 83.8% → 89.5% |
| bird_reasoning_high_500 | 85.2% → 89.2% |
| bird_rhigh_v2_500 / lean_distill / noleak_mini / ours_v4 | — |

`bird_nofs_rhigh` 在修正 gold 上是全场最高的 91.3%，**但这个数不能用**：

1. **无 `agent_config_sha256`、无 manifest、无 trace** —— 无法确认它跑的是什么，也无法复现
2. 走 `bird_indomain_fewshot_db_rlm`，即出过泄漏事故的 in-domain 检索路径
3. 文件时间 2026-07-08 晚于修复日 07-04，但 **mtime 不是可信证据**
4. findings.md 记录的导师指令是 **eval set 一律不碰，示例只能来自 train split**；
   in-domain 检索本身违反该指令

**结论：排除，不是隔离。** 一个无法复现、无法确认是否泄漏的第一名没有意义。

## 四、重跑计划

在**修正数据集**（`bird_dev_500_corrected_full.json`）上重跑，每配置 **2 次**以获得噪声带。

### 第一优先（6 个配置 × 2 次 = 12 次运行）

| 配置 | cfg_sha | 为什么 |
|---|---|---|
| `clean-e0` | `b35611609e5c` | 基线。没有它，任何"提升多少"都无从谈起 |
| `legacy-e0` | `40fcce2b4c64` | 第二基线，修正后 89.2% 反超当前最优 |
| `e3-c-conv-rules` | `671e8010a65c` | 现行最优（已关掉两条改写规则），需在修正基准上重新定位 |
| **`e3-c-noconv`** | `2dbc99a65da4` | **新增对照臂**，见下 |
| `e3-c-recursive` | `0d60da3313f7` | +24 的异常值，此前"递归没用"可能建立在坏 gold 上 |
| **`B1`** | 待补 | 零检索单次生成的参照点；重跑一次即可补上配置指纹 |

### 为什么必须加 `e3-c-noconv`

`e3-c-recursive` 同时改了两件事：打开 `recursion_mode=leaf-v1`，**并且关掉了 convention 后处理**
（`sql_convention_mode=none`）。所以它 +24 的来源分不清。

而本轮已测得：被关掉的两条规则在修正 gold 上分别值 **−13** 和 **−1**
（`sql_postprocessing_rules_2026-08-16.md`）。**+24 里有多少只是"没开那两条坏规则"，必须拆开。**

新臂与两侧的关系：

| 对照 | 差异字段 | 干净度 |
|---|---|---|
| `e3-c-conv-rules` → `e3-c-noconv` | 仅 `sql_convention_mode` | **单变量** |
| `e3-c-noconv` → `e3-c-recursive` | `prompt_profile` + `recursion_mode` | **仍有 prompt 混淆** |

第二组的混淆消不掉：`basic-recursive-v1` 必须点名递归工具，否则模型不会调用它
（config.py 记录：此前无 prompt 提及它，197 题中 0 次调用）。**报告时不得把它写成干净的递归对照。**

### 第二优先（有余力再做）

`e3-c-semantic`、`e3-c-conv` —— 用于确认"约定写进 prompt vs 写进输出后处理"这条线在修正基准上是否还成立。

### 不重跑

§3.5 那 7 个。要它们的能力数据，只能用当前代码重新实现一个等价配置，而不是复用旧结果。
（B1/B2 不在此列——见 §3。）

## 五、重跑时必须固定的事

1. **数据集**：`bird_dev_500_corrected_full.json`（sha 记入 manifest）。
   注意它改写了 147 道题面、140 条 evidence，**与原始 BIRD 的任何数字都不可并列**
2. **每配置 ≥2 次**，噪声带随结果一起报，不做事后补救
3. **同时报干净子集**：278 道题面+evidence 未改、74 道纯 gold 修正。
   后者是唯一"模型答案不变、只有参考答案变"的对照
4. **`reasoning_capture`**：若要做推理层分析必须开，但它走 Responses API，
   准确率只能与同样开启的运行比较（见 `ours/agent/reasoning_capture.py` 的声明）


## 六、论文用的五层对照链（RLM 相对基线的作用）

> **2026-08-20 更正。** 原文写的是"论文要论证的是 **RLM 递归**相对基线的贡献"，
> 这把 RLM 窄化成了它的一个机制。按 [`README.md` §2.3](README.md)，RLM 是**三个**能力：
> ① 程序化推理/探索（context store 外部化）② 可执行环境（REPL + DB observation）
> ③ 自我改进与分而治之。递归只是 ③ 的后半。
> 按窄表述读，实测结果会被误读成"RLM 没有贡献"——而真实结论是收益**极不均衡**：
> ② + ③ 前半贡献 +13.4pp，① 的弱化版 +2.5pp，③ 后半 +0.3pp（误差内）。
> 见 [`five_layer_chain_results_2026-08-19.md`](week_2026-08-18/five_layer_chain_results_2026-08-19.md) §六。

论文要论证的是 RLM **三个机制各自**相对基线的贡献，所以对照链每层只加一件事
（右侧标注该层对应哪个机制）：

| 层 | 配置 | 相对上一层新增 |
|---|---|---|
| 0 | **B1** | —— 零方法：单次生成，无探索、无自我纠正、无重试 |
| 1 | `clean-e0` | agent 工具循环 —— **RLM 机制 ② 可执行环境 + ③ 自我改进** |
| 2 | `e3-c-noconv` | 离线 schema 检索 + 元数据（`capability_gate`、`e3-f-schema-v4`）—— **机制 ① 的弱化版**（离线检索，非模型自主检索） |
| 3 | `e3-c-conv-rules` | convention 后处理 —— **不属于 RLM**，是 输出后处理，属被测对象 |
| 4 | **`e3-c-recursive-db`** | **机制 ③ 后半：分而治之**（`leaf-db-v1`，叶子共享父的受控数据库句柄） |

`e3-c-noconv` 是为第 4 层能干净对比而新建的——原来的 `e3-c-recursive`（leaf-v1）
同时关掉了 convention 后处理，两个变量绑在一起。

### 已测得的地板（B1/B2，修正数据集，各 2 次）

| 配置 | run1 | run2 | 噪声 |
|---|---:|---:|---:|
| B1 | 70.5% | 70.3% | **0.2pp** |
| B2 | 66.9% | 67.9% | **1.0pp** |

> 2026-08-21 更正：原记录 70.3%/70.1%、66.7%/67.7%；`evidence=None` 修复后各 +0.2pp，
> 见 [`week_2026-08-18/harness_defects_2026-08-18.md`](week_2026-08-18/harness_defects_2026-08-18.md) §四。

B1 两次只差 1 道——单次生成没有 agent 循环的随机性，是可靠的地板。
B2 比 B1 低 2.9pp，与 findings.md 记录的 −3.6pp 方向一致，**该结论经受住了 gold 修正与重跑**。

## 七、递归调用率：论文必须先报的数

递归**极少被真正调用**，而且同配置之间波动近 4 倍：

| 运行 | 题数 | 递归调用 | 调用率 |
|---|---:|---:|---:|
| `e3-c-recursive` dev500 | 500 | 19 | **3.8%** |
| `e3-c-recursive-db` dev200 run1 | 199 | 8 | **4.0%** |
| run2 / run3 / run4 | 199 | 30 / 31 / 31 | 15.1% / 15.6% / 14.6% |

三个后果，都要写进论文：

1. **`e3-c-recursive` 在修正 gold 上 +24，不可能来自递归**——全集只有 19 题调用过递归，
   比多出来的题还少。那 +24 主要来自它关掉了 convention 后处理（§六的混淆）。
2. **温度为 0，调用率却在 4.0%~15.6% 间波动**。是否触发递归本身极不稳定，
   任何"递归有/没有作用"的结论都要先交代这一点。
3. **有效样本只有约 8~31 题**。要在这个量级上测出效应，效应必须极大。

因此论文应当**同时报两个数**：全集上的效应，以及**仅在调用过递归的题上**的效应。
只报前者会把效应稀释到看不见；只报后者是选择性报告。

### `e3-c-recursive`（leaf-v1）建议弃用

config.py 自己记着：v1 的文本叶子"知道得严格更少，dev500 上准确率变动 0.00pp"。
v2（`leaf-db-v1`）让叶子共享父的数据库句柄，才是有意义的递归。
v1 那个 profile 又把 convention 混了进来，混淆无法消除。

## 涉及数据

- `analysisDetail/rescore_all_runs_corrected.json` —— 20 个运行的重评结果
- `analysisDetail/gold_versions_clean278.json` / `gold_versions_pure74.json` —— 三列拆解
- `data/processed/bird_dev_500_corrected_full.json` —— 修正数据集（含 `question_unchanged` 标记）


---

## 八、2026-08-18 更正汇总

详见 [`harness_defects_2026-08-18.md`](week_2026-08-18/harness_defects_2026-08-18.md)。要点：

**已修复并重跑，数字更新：**

| 运行 | 口径 | 原记录 | 更正后 |
|---|---|---:|---:|
| `e3_c_arcwise_full_dev500_run1` | 修正全集 498 | 84.5% | **86.7%** |
| `e3_c_rc_ctl_dev500_run1` | 干净 277，原→修正 gold | 82.3% → 87.0% | **84.1% → 89.2%** |
| `e3_c_rc_trt_dev500_run1` | 干净 277，原→修正 gold | 82.7% → 87.7% | **84.5% → 89.9%** |

**⚠️ 仍被压低、引用需注明**（含未重跑的编码崩溃记录）：
`e3_c_rules_reasoning_dev500_run1`（16 道）、`e3_c_conv_rules_v2_dev500_run1`（14 道）、
`e3_c_semantic_dev500_run1`（8 道）。

**已确认无崩溃、可直接引用：** `legacy_e0_dev500_run1`、`e3_c_recursive_dev500_run1`、
`clean_e0_dev500_run1`、`e3_c_conv_dev500_run1`、`e3_c_conv_rules_dev500_run1`、
`e3_c_conv_rules_dev500_iter15`、B1/B2 各两次。

**五层对照链当前进度**（修正数据集 498，每题均已修复编码缺陷）：

| 层 | 配置 | 结果 |
|---|---|---:|
| 0 | B1 run1 / run2 | 70.5% / 70.3% |
| 0' | B2 run1 / run2 | 66.9% / 67.9% |
| 1 | `clean-e0` | 运行中 |
| 2 | `e3-c-noconv` | **85.3%** |
| 3 | `e3-c-conv-rules` | **86.7%**（两次独立运行均为 86.7%） |
| 4 | `e3-c-recursive-db` | 运行中 |

第 2→3 层（convention 后处理）**+1.4pp**（7 道；赢 20 输 13，churn 33）——
在旧的 1~2pp 尺子下读不出，在新尺子下可读，但赢输双向，不是净增益机制。
