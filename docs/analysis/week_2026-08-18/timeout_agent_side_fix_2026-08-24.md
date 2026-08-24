# 超时问题的两端修复：判分侧回填 121 条，agent 侧新机制测出 0.0pp（2026-08-24）

承接 [`sql_timeout_correction_2026-08-23.md`](sql_timeout_correction_2026-08-23.md)。上一轮只修了
五层链八臂里的 36 条，并明确留下「全仓约 140+ 条未处理」。本轮把两端都做完：
判分侧全仓回填，agent 侧新增一个可消融机制并做了对照实验。

---

## 一、根因不是「查询太慢」，是数据库没有索引

上一轮把这类记录归因为「执行代价问题」，不够准确。逐条查证：

```
bird_1148 的 predicted_sql（相关子查询形状）
  原始库执行：262 秒，返回 51.1572856391373
  gold_answer：      51.1572856391373   ← 完全一致
```

**模型的 SQL 从来就是对的，只是跑得慢。** 查 `Player_Attributes`（18 万行）发现
**一个二级索引都没有**，那句 `EXISTS` 子查询要对每个 `Player` 全表扫一遍 18 万行。

这不是个例，是 BIRD 原始库的普遍特征——除主键自带索引外，外键风格的列基本全裸：

| 数据库 | 零索引的大表 |
|---|---|
| `european_football_2` | `Player_Attributes`（183,978 行） |
| `card_games` | `legalities`（427,907）、`rulings`（87,769）、`foreign_data`（229,186） |
| `codebase_community` | `comments`（174,285）、`badges`（79,851）、`votes`（38,930） |
| `financial` | `trans`（1,056,320） |

全仓超时候选按库分布高度集中，与上表吻合：`card_games` 81 条、`codebase_community` 56 条、
`european_football_2` 20 条、`debit_card_specializing` 20 条、`financial` 1 条。

---

## 二、判分侧：用临时索引副本核实，回填 121 条

**方法的正当性**：索引在数学上不改变查询结果，只改变速度。所以在一份**临时副本**上
按查询自身的关联列建索引后重跑，拿到的就是「给够时间本该得到的真实答案」，
不是猜的，也不需要机械改写模型的 SQL。

**明确不做的事**：不给 benchmark 原始 `.sqlite` 文件加索引。虽然全仓审计确认
没有任何地方对 `.sqlite` 做哈希校验（`dataset_sha256` 校验的是修正版 JSON），
技术上可行且不会让历史运行作废，但那会让所有跑分都建立在一个被我们动过的
基准上，不公平。索引只存在于诊断脚本临时建、用完即弃的副本里。

新增 `scripts/`（本轮临时脚本）对全仓 178 条候选逐条核实：

| 判读 | 条数 | 含义 |
|---|---:|---|
| `slow_but_correct` | **121** | 给够条件确认答对——原判定是误判，已改判 |
| `slow_and_wrong` | 30 | 确认真答错，不是超时的锅 |
| `still_times_out_or_errors` | 27（9 道题） | 加索引仍跑不完——真实执行代价问题，维持判错 |

实际写回 **47 个结果文件、120 处修正**，每条带 `timeout_repair` 字段留痕。

**顺带修了上一轮诊断方法本身的一个 bug**：旧脚本只测 `predicted_sql` 的耗时，
如果 `gold_sql` 自己也跑不完，会被归成「跑出结果了但答案不对」（`slow_and_wrong`）。
`bird_701` 实测：gold_sql 在 180 秒预算下**依然跑不完**，此前却被标成「模型确实答错」——
换索引副本后 gold 秒出，与模型答案完全一致。121 条里有 68 条属于这种 gold 侧问题。

---

## 三、判分侧防复发：`shared/timeout_recovery.py`

只回填历史记录不够——下次重跑会原样再踩一遍。`DEFAULT_QUERY_TIMEOUT_SECONDS`
从 30s 提到 180s 也不够：`bird_1148` 光 predicted 就要 262 秒。

新增 [`shared/timeout_recovery.py`](../../../shared/timeout_recovery.py)：判分时任何一次执行
超时，自动用同一套临时索引副本方法重试一次。已接入全部五个 `run_one()` 实现
（`run_bird_ours`、`run_bird_indomain_fewshot`、`baselines/run_bird_b{1,2}_azure`、
`recursive_db_rlm`）。每条记录带 `timeout_recovery: {predicted, gold}` 字段，
标明该结果是否靠恢复机制拿到，不静默混入。

**边界**：只覆盖「缺索引导致的慢」，且只识别 `A.col = B.col` 这种常见关联写法。
排序量过大、`LIKE` 模糊匹配、或特殊关联写法导致的超时，这套机制无能为力。

---

## 四、agent 侧：`final_execution_gate`，及它与 E1 被否决机制的区别

判分侧修复只是「事后不冤枉」，不改变模型生成低效 SQL 这件事本身。agent 侧新增
`final_execution_gate`（profile `e3-c-conv-rules-final-gate`，单变量对照 `e3-c-conv-rules`）：

模型调用 `FINAL(sql)` 时，**控制器直接把这句 SQL 执行一次**（成功路径不占用模型额外轮次），
只在真实执行失败时拦截，并把**具体原因**返回给模型：

- 语法/表名错误 → 带上 sqlite 原始错误文本 + 「按这个错误修正后重新提交」
- 超时 → 「别重交同一句，重新设计。这些库外键列基本没索引，`WHERE` 里的相关子查询
  （`EXISTS`/`NOT EXISTS`/标量子查询）会对每个外层行全表扫内层表，考虑改写成 JOIN」

**与 E1 `verified_final` 的区别是关键**（[`e1_verified_summary.md`](../analysisDetail/e1_verified_summary.md)
已否决那条路：准确率 42.14%→40.00%，调用与 token 翻倍，把 3 道稳定答对的题弄错）：
E1 要求**模型自己**提前跑过一模一样的字符串，模型稍作修改就被拦，90% 的题都触发过，
拦的多数不是真问题。这里是**控制器**在提交那刻自己执行，不要求模型预先验证，
只有真实执行失败才拦。两者在 `AgentConfig.__post_init__` 里互斥，不能同时开。

**一个此前没被记录的事实**：读控制组 trace 发现，模型在提交前**从不执行自己的最终查询**
（24 道题 `events` 全空）。典型轨迹是第一轮吐裸 SQL → REPL 报语法错 → 第二轮原样包进
`FINAL()` 提交。所以这个 gate 不是「在已有验证之上再加一次」，而是 agent 循环里
**唯一的一次真实执行**。

---

## 五、对照实验结果：机制按设计工作，准确率 0.0pp

24 道题（9 道已知超时题 + 15 道随机背景题，seed=42），两臂单变量，
同模型 `azure/seminar-gpt-5.4-mini`、`max_iterations=8`、`reasoning_effort=high`：

| | 控制组 | 实验组 | 差 |
|---|---:|---:|---:|
| 整体 | 22/24 = 91.7% | 22/24 = 91.7% | **+0.0pp** |
| 9 道已知超时题 | 7/9 = 77.8% | 7/9 = 77.8% | +0.0pp |
| 15 道背景题 | 15/15 = 100% | 15/15 = 100% | +0.0pp |
| LLM 调用 | 29 | 32 | 1.10× |
| Total tokens | 156,889 | 173,132 | 1.10× |

**逐题翻转：0 道。** E1 的翻车方式（把稳定答对的题弄错）没有出现。

**gate 行为**（这部分是正面的）：

| 指标 | 值 | 对照 |
|---|---|---|
| 触发率 | **2/24 = 8.3%** | E1 被否决时是 90% |
| 触发后模型是否真的改写 SQL | **2/2 都改了** | 不是原样重交 |
| 两次触发都是超时分支 | 是，反馈文案正确 | — |

`bird_529` 是机制生效的干净案例：

```
控制组：EXISTS ... AND NOT EXISTS 相关子查询 → 判分时超时 → 靠判分侧索引恢复才算对
实验组：gate 在循环内拦下 → 模型改写成 INNER JOIN (SELECT DISTINCT ...) + LEFT JOIN
        → 答对，且 timeout_recovery=False（不再需要判分侧兜底）
```

模型确实读懂了「外键无索引，改用 JOIN」这条具体指引并照做了。但这**没有转化成准确率**——
控制组那道题本来也会被判分侧救回来，两边都对。

---

## 六、为什么 0.0pp 不是偶然：这个机制的天花板本来就很低

查当前最好 profile 在全量 498 上的失败构成：

| | run1 | run2 |
|---|---:|---:|
| 判错总数（可计分 496） | 61 | 61 |
| 其中**有执行错误**（gate 能介入） | **1** | **1** |
| 其中 `error=None`（语义错，gate 完全看不见） | **60** | **60** |
| 空结果（gate 也会拦） | 4 | 1 |

**判分侧修完之后，剩余失败的 98% 是语义错误**——SQL 跑得通、跑得完，就是答得不对。
`final_execution_gate` 的理论上限是 5 道（run1）/ 2 道（run2），约 +1.0pp / +0.4pp，
还得假设模型每次被拦后都能改对。实测 `bird_416` 就是反例：gate 成功把超时的查询
变成了跑得完的查询，但答案仍错——它错在比例公式的分母选择（
[`拆开「其它」424 道失败_2026-08-21.md`](拆开「其它」424%20道失败_2026-08-21.md) §三 的
`ratio_formula` 子模式），是语义问题，gate 结构上无法触及。

**这从一条完全不同的路径复现了 E1 的结论**：模型的瓶颈是语义判断，不是执行验证。
E1 是通过「强制验证消除了 `UNVERIFIED_FINAL` 标签但准确率没动」得出的；
本轮是通过「把执行失败这一类修干净后，发现剩下的几乎全是语义错」得出的。

---

## 七、样本设计的一个缺陷（影响本次结论的强度）

那 9 道「已知卡住」题，是按**旧运行里旧的 `predicted_sql`** 判定的。新跑一次模型
生成的是不同的 SQL，卡住状态不转移——控制组里 7/9 直接就对了。
背景组 15/15 满分，天花板效应明显。

因此本次实验**能可靠支持的结论**是：机制不造成回退、触发率低（8.3%）、
被拦后模型会真的重新设计。**不能可靠支持**的是「+0.0pp 就是它在全量上的真实效应」——
样本太小、且几乎没有留给它发挥的失败。第六节的天花板分析（基于全量 498）比这个
24 道样本更能说明问题。

---

## 八、`no_answer` 到底解决了没有：量化回答

用 `triage_failure_causes.py:146` 的原定义（`predicted_answer is None`）重新统计，
口径对齐 [`拆开「其它」424 道失败_2026-08-21.md`](拆开「其它」424%20道失败_2026-08-21.md)
（该文记录八臂合计 21 条）：

| | 数量 |
|---|---:|
| 原文档记录 | 21 |
| **判分侧回填后** | **6**（降 71%） |
| 其中仍是超时 | 5 |
| 其中其他（`misuse of aggregate: COUNT()`） | 1 |

**剩下这 6 条不需要修，因为重跑就不存在了。** 这 6 条只涉及 4 道不同的题
（`bird_529` 在三个臂里重复）。把这 4 道重新跑一遍：

| 题目 | 控制组（无 gate） | 实验组（有 gate） |
|---|---|---|
| `bird_409` | 有答案，对 | 有答案，对 |
| `bird_416` | 有答案，错（语义） | 有答案，错（语义） |
| `bird_529` | 有答案，对 | 有答案，对 |
| `bird_1036` | 有答案，对（gate 未触发） | 有答案，对（gate 未触发） |

**关键是控制组也全都出了答案。** 所以这些 `no_answer` 不是「这些题有问题」，
而是当时那次采样恰好生成了低效或错误的 SQL。

**结论：`no_answer` 是一个随机现象，不是一批固定的坏题。** 它取决于模型那一次
采样出什么 SQL，因此「把这 N 道修掉」这个说法本身不成立——它们已经不存在于新运行里。
能问的只有「开着 gate 跑全量，`no_answer` 的发生率会不会下降」，但当前基准发生率
已经是 ~1/496，这个效应量在 498 道上测不出来。

---

## 九、结论与建议

1. **判分侧修复应当保留并采用**：121 条误判是实打实的测量偏差，与模型能力无关。
2. **`final_execution_gate` 已加入推荐默认配置**：新增 profile
   `e3-c-recursive-db-final-gate` = 最高分臂 `e3-c-recursive-db`（88.10%）+ gate，
   单变量。理由是**防复发**而非提准：它让循环内出错或超时的查询带着真实错误
   回到模型手里，而不是以 `no_answer` 的形式流到判分。
   **不作为提准手段**——天花板 ~1pp，实测 0.0pp。

   *为什么新建 profile 而不是直接翻 `e3-c-recursive-db` 的开关*：`agent_config_sha256`
   进入每次运行的 manifest，改动现有 profile 会让 `audit_run_configs.py` 不再认为
   已有八臂运行是「同配置」，断掉既有对照关系。项目惯例也是一个变量一个新 profile。
3. **下一步不应继续在执行验证方向投入**。剩余 60/61 的语义失败才是瓶颈，
   与 `WEEK_PLAN` 的 Phase A 人工判读方向一致。

## 涉及文件

- [`shared/timeout_recovery.py`](../../../shared/timeout_recovery.py)、
  [`shared/sql_executor.py`](../../../shared/sql_executor.py)（30s → 180s）
- [`ours/agent/config.py`](../../../ours/agent/config.py)（`final_execution_gate` 字段、
  profile `e3-c-conv-rules-final-gate`（实验用）与
  **`e3-c-recursive-db-final-gate`（新运行推荐默认）**）、
  [`ours/recursive_db_rlm.py`](../../../ours/recursive_db_rlm.py)（FINAL 分支）
- `results/q1036_{ctl,trt}.json`（第八节重跑 `bird_1036` 的两臂证据）
- `tests/test_timeout_recovery.py`、`tests/test_final_execution_gate.py`（8 个新测试）
- `data/processed/finalgate_sample24.json`（24 道对照样本，逐题可复现）
- `scripts/compare_final_gate.py`（两臂对比分析）
- `results/finalgate_{ctl,trt}_sample24.json`、`trace/finalgate_{ctl,trt}_sample24/`
- 47 个 `results/*.json` 就地修正，各记录带 `timeout_repair` 字段留痕
