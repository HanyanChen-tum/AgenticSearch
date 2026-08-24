# 递归为什么没用：15 道失败的逐题追踪（2026-08-24）

## 为什么做这条线

五层链测出 RLM 递归（机制③后半，depth-1 leaf）的增量是 **+0.10pp**，在噪声带内，
且在调用过递归的题上两次重复符号相反（+2.7pp / −3.1pp）——
[`five_layer_chain_results_2026-08-19.md`](five_layer_chain_results_2026-08-19.md) §一。
**知道它没用，不知道为什么。** 链上八个臂一条 `reasoning_capture` 都没采，
看得到 leaf 被调用了、返回了什么，看不到两边各自推理了什么。

新注册 `e3-c-recursive-db-reasoning`（= `e3-c-recursive-db` + `reasoning_capture`，
单变量），修正数据集上跑两次：**87.9% / 87.3%**（Responses API 路径，
按既有口径不与 Chat Completions 臂直接比）。

## 数据结构：root 和 leaf 的推理能分开

leaf 复用 root 的 `_call_llm`，两边的推理进同一个 `reasoning_capture` 列表，
且都只标 **root 的**轮次号——一个跑了 2 轮的 leaf 会贡献 2 条、全部标着调用它的那个 root 轮次。
但 `recursive_llm` 工具事件自己记了 leaf 的轮次数，所以在每个 root 轮次内，
**最后 `turns` 条是 leaf 的**，前面的是 root 的。两次运行的 70 / 72 道题全部切分成功。

## 结果：leaf 几乎总是答对，失败在别处

| | run1 | run2 |
|---|---:|---:|
| 调用过递归的题 | 70 | 72 |
| 其中失败 | 6 | 9 |
| leaf 跑满轮次没答出来 | 2 | 0 |

**15 道失败逐题人工读完，没有一道是「leaf 答对了但 root 没采纳」。** 分布：

| 真实原因 | 题数 | 例 |
|---|---:|---|
| **递归正常工作，失败在约定不匹配** | 6 | `bird_671`（leaf 答 Geoff Dalgas，SQL 正确查了，但 gold 要列出全部并列获奖者）、`bird_736`、`bird_1387`（DISTINCT 约定）、`bird_1032`（三个联赛并列 3040 场，模型只返回一个） |
| **递归正常工作，失败在最终 SQL 的其它环节** | 5 | `bird_48`（leaf 正确确认 `StatusType='Merged'` 存在，最终 SQL 的 DOC 取值判断错）、`bird_892`（leaf 答 Lewis Hamilton 正确，但聚合口径错：24509 vs gold 2382）、`bird_263`（leaf 甚至算出了两种口径的具体数值，root 选了错的那个）、`bird_407`、`bird_1036` |
| **委托的子问题本身就问错了** | 2 | `bird_173`（问的是 `order` 表 amount=3539 的 k_symbol，题目要的根本是别的）、`bird_758`（子问题带着错误的过滤条件问，leaf 如实答"0 条匹配"） |
| **leaf 没答出来** | 2 | `bird_244`（run1 跑满轮次无答案；run2 同一题 leaf 答对了 `+`，root 的 SQL 仍返回空集） |

## 结论：递归没触及真正的失败原因

**11/15 的失败里 leaf 是答对的**——递归确实把它被委托的事情做好了，但最终仍然错，
错在约定不匹配（并列名次、DISTINCT）和最终 SQL 的聚合/过滤口径。

这跟五层链的另一条结论精确吻合：
[`five_layer_chain_results_2026-08-19.md`](five_layer_chain_results_2026-08-19.md) §三 测出
**约定类失败对方法层级和推理强度双重免疫**（沿方法栈 20→24→25→22，沿推理强度 22→13→16→12，
绝对数几乎不动）。递归是方法栈上的又一层，**它同样消不掉这类失败**——
现在有了机制层面的解释，不只是"效应太小"：

> 递归能帮模型把事实查清楚，但失败早就不在「事实没查清」这一层了。

`bird_263` 是最锋利的一例：leaf 把两种可能的计算口径**各算了一个具体数值**交回去
（0.0348 和 0.0268），root 选了前者，gold 是 3.4823（百分比乘 100）——
信息完整送达，root 仍然选错。这不是信息传递的问题。

## 方法学教训：一个自动分类规则又一次被人工判读推翻

本脚本第一版会输出分类（`leaf_wrong` / `leaf_unused` / `leaf_used_still_wrong`），
判据是 leaf 答案文本与最终 SQL 的 token 重叠。跑出来 run1 六道里五道标成 `leaf_unused`。
**逐条读 transcript 后发现 6 道里 5 道标错**：leaf 答 "Geoff Dalgas"、SQL 写
`SELECT u.DisplayName ... ORDER BY b.Date ASC LIMIT 1`——两者没有共同 token，
但 leaf 的答案显然被用上了。**SQL 里出现的是列名和谓词，不是答案文本，
表面重叠替代不了语义判断。**

与本项目已记录的同类错误同源：判读协议里"机械判定四次被证伪"，
以及本次会话中"`check_sql` 返回非空即视为断言成立"那个验证脚本
（[`phase_a_first_pass_2026-08-23.md`](phase_a_first_pass_2026-08-23.md)）。

脚本已改为**只输出可复算的事实**——子问题、leaf 答案、leaf 是否跑满轮次、最终 SQL、
两边答案集——判断留给人。样本量 6~9 道/次，逐题读完全可行，不需要自动分类。

## 限制

1. **15 道失败，样本极小**，本文所有比例都是描述性的，不构成任何统计结论。
   这一点在实验启动前就已知：递归调用率约 14%，其中失败的更少。
2. 人工判读由我（AI）完成，**不是独立的人工基准**。与 Phase A 那 29 道定位面临同样的问题
   （见 `phase_a_first_pass_2026-08-23.md` 末节），需要真正独立的人核对才能作为结论引用。
3. 两次运行的失败题重合度未统计；`bird_244`、`bird_48` 两次都失败但原因不同
   （`bird_244` run1 是 leaf 没答出来、run2 是 leaf 答对但 root 的 SQL 返回空集）。

## 涉及文件

- [`scripts/analyze_recursion_traces.py`](../../../scripts/analyze_recursion_traces.py)（root/leaf 切分 + 事实输出，不出判断）
- `docs/analysis/analysisDetail/recursion_trace_analysis_run{1,2}.json`
- `results/e3_c_recursive_db_reasoning_corrected_run{1,2}.json`、对应 trace 目录
- [`ours/agent/config.py`](../../../ours/agent/config.py) 新增 profile `e3-c-recursive-db-reasoning`
