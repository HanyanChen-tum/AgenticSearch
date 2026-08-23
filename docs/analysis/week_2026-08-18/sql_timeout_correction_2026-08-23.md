# SQL 执行超时误判：诊断与修正（2026-08-23）

## 起点

`e3-c-rules-reasoning` 语料里几道 `no_answer` 失败查出来是 `SQL execution timed out
after 30 seconds`——模型的 SQL 语法完全正确，只是跑不完 30 秒预算，被 `run_one()` 的
`"error": predicted_exec.get("error") or gold_exec.get("error")` 逻辑无声地判成
`correct=False`。这跟本项目这轮反复揪出来的其它测量偏差（编码 bug、`evidence=None`、
异常误分类）是同一种模式：harness 自己的一个内部参数（`DEFAULT_QUERY_TIMEOUT_SECONDS
= 30.0`，[`shared/sql_executor.py:12`](../../../shared/sql_executor.py)）不是 BIRD
官方基准的规则，只是本项目自己选的数字，它在惩罚跟模型能力无关的东西。

全仓扫描：这个模式出现在 **190 条记录、52 个文件**里，其中**五层链八个臂（头条数字
86.9%/87.2% 那几个）合计 36 条**。本次只修了这 36 条，其余约 140+ 条留作后续工作。

## 诊断：不能假设"超时=其实是对的"，必须逐题重新执行验证

新增 [`scripts/diagnose_sql_timeouts.py`](../../../scripts/diagnose_sql_timeouts.py)，
对每条 `termination=final` 且 `error` 含 "timed out" 的记录，用更长预算（180 秒）
重新执行 `predicted_sql` 和 `gold_sql`，比对答案，不做任何假设。

八臂合计 36 条，三种结果：

| 判读 | 条数 | 含义 |
|---|---:|---|
| `slow_but_correct` | 16 | 给够时间能跑完，且答案正确——原判定是误判 |
| `slow_and_wrong` | 8 | 给够时间能跑完，但答案错——原判定本来就对，只是理由不对（不是超时，是真答错） |
| `still_times_out_or_errors` | 12 | 180 秒预算还是跑不完——真实的执行代价问题，维持判错 |

## 一个意外发现：44% 的记录（16/36）跟模型无关，是 gold 侧的问题

按"到底是谁慢"重新归因后，36 条分成两个完全不同的群体：

### 群体一：`bird_518` + `bird_701`，16 条，**gold_sql 本身要 60+ 秒**

两道题在全部八个臂里都被打上超时标签，模式高度一致——查了才发现根本不是模型的问题：

```
bird_518 gold_sql 单独执行: 60.01s（超过 60 秒预算）
bird_701 gold_sql 单独执行: 60.03s（超过 60 秒预算）
```

`predicted_sql` 两道题在全部出现里都是 0.1~0.7 秒跑完——**模型的 SQL 从来不是瓶颈**。
`run_one()` 的判分逻辑只要 `gold_exec.get("error")` 非空就整题判错，不管模型答案对不对。
逐题验证结果：

- `bird_518`：模型每次都答对，8 次全部被冤枉判错——纠正为 `correct=True`
- `bird_701`：模型确实答错，8 次判错本身是对的，只是原因写错了（不是超时，是真的算错）——不改

### 群体二：11 道不同题，20 条，模型侧真实的执行代价问题

跟这轮之前诊断过的相关子查询模式（`EXISTS` 嵌套导致全表扫描）一致：

- 8 条（`bird_1490`/`bird_1505`/`bird_672`）：给够时间能跑完且答案对——纠正为 `correct=True`
- 12 条（`bird_1148`/`bird_409`/`bird_529` 等 8 道不同题）：180 秒仍跑不完——维持判错，真实结果

## 修正：只改真正核实过的，逐条留痕

新增 [`scripts/apply_timeout_diagnosis.py`](../../../scripts/apply_timeout_diagnosis.py)，
**不直接信任诊断文件**，应用时对每条 `slow_but_correct` 记录重新执行一遍（180 秒预算），
确认真的对了才改 `correct: true`，并在记录里加 `timeout_repair` 字段留下原始 `error`
和原始 `correct` 值。八臂全部跑完，共改动 **16 条**，与诊断阶段的计数完全一致，
没有一条"诊断说对、复核却不对"的情况。

## 对头条数字的影响：数字小幅上移，结论方向不变

| 层 | 修正前均值 | 修正后均值 | 差 |
|---|---:|---:|---:|
| 0 B1 | 70.5% | 70.47% | −0.03pp（未涉及，噪声） |
| 1 clean-e0 | 83.9% | 84.32% | +0.42pp |
| 2 noconv | 86.5% | 86.86% | +0.36pp |
| 3 conv-rules | 86.9% | 87.37% | +0.47pp |
| 4 recursive-db | 87.2% | 87.47% | +0.27pp |

| 层间增量 | 修正前 | 修正后 |
|---|---:|---:|
| 0→1 agent 工具循环 | +13.4pp | +13.85pp |
| 1→2 机制①（离线检索） | +2.5pp | +2.55pp |
| 2→3 后处理（非 RLM） | +0.4pp | +0.51pp |
| 3→4 **机制③递归** | +0.3pp | **+0.10pp** |

噪声带重测：0.00~1.02pp（原 0.2~1.4pp），量级未变。

**结论不变，其中一条更扎实了**：递归那一层的增量从 +0.3pp 变成 +0.10pp，
"RLM 递归测不出稳定效应"这条结论没有被削弱，反而更接近零。
这次修正没有推翻 [`five_layer_chain_results_2026-08-19.md`](five_layer_chain_results_2026-08-19.md)
的任何判断，只是把口径修准。该文档已加更正说明，未改写原表格数值。

## 尚未处理的部分

- 全仓约 **140+ 条**同类记录（190 条总数减去这次修的 36 条）分布在头条数字以外的历史运行里，
  没有处理，优先级低于当前正在引用的数字
- 群体二里"180 秒仍跑不完"的 8 道题（`bird_1148` 等），根因是相关子查询模式，
  修复方案见对话记录——机械改写成 JOIN 风险较高，需要严格的安全闸门，样本量小，暂不投入

## 涉及文件

- [`scripts/diagnose_sql_timeouts.py`](../../../scripts/diagnose_sql_timeouts.py)、
  [`scripts/apply_timeout_diagnosis.py`](../../../scripts/apply_timeout_diagnosis.py)
- `docs/analysis/analysisDetail/timeout_diag_*.json`（八臂诊断结果，每条含执行耗时和判读）
- `results/chain_*_corrected_run{1,2}.json`（八个文件均被就地修正，各记录带 `timeout_repair` 字段留痕）
