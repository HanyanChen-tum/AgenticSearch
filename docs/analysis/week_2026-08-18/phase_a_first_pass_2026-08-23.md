# Phase A 首轮定位：29 道，及一个验证方法的教训（2026-08-23）

## 产出链条

用 `e3-c-rules-reasoning` 在修正数据集上跑的两次运行（[`reruns_2026-08-20.md`](reruns_2026-08-20.md)
之后新跑的这两次，见对话记录），走完整条流水线：

1. [`scripts/extract_inline_reasoning.py`](../../../scripts/extract_inline_reasoning.py)
   从 trace 里拉出 turn1 的 `reasoning_capture`
2. [`scripts/label_reasoning_sentences.py`](../../../scripts/label_reasoning_sentences.py)
   给 Phase A 候选池（29 道，见下）的句子打 Thought Anchors 八分类标签
3. [`scripts/locate_first_wrong_sentence.py`](../../../scripts/locate_first_wrong_sentence.py)
   定位每道题"第一个承诺错误的句子"
4. 新增 [`scripts/verify_located_claims.py`](../../../scripts/verify_located_claims.py)
   执行每条定位附带的 `check_sql`

候选池沿用 [`five_layer_chain_results_2026-08-19.md`](five_layer_chain_results_2026-08-19.md)
建立的分诊口径：剔除 harness 崩溃、自信型失误、格式型失误、行集类、比例公式子模式，
只留"其它"类真正的语义失败。两次运行各 25 道，21 道两次都失败（84% 重合，说明是可复现的
真实困难，不是采样噪声），并集 **29 道**。

## 结果

| 指标 | 值 |
|---|---|
| 定位到的句子位置（相对推理长度百分比） | 中位 20.4%，均值 27.9% |
| 标签分布 | FR 12、AC 11、PS 2、RC 2、PG 1、FAE 1 |
| 带可执行断言的 | 28/29 |

## 一个必须记录的方法教训：自动"非空即真"验证是错的

`verify_located_claims.py` 最初的判定逻辑是"`check_sql` 执行成功且返回了非空/非零值就算
confirmed"，跑出来 28/29（97%）"confirmed"。**这个数字是假的，不能用。**

逐条人工读了 claim 文本和返回内容之后发现：真正严谨验证了断言的只有约 8~9 道
（例如 `bird_518`：`COUNT(status='Banned')` 返回 7698 而 `SUM(CASE WHEN...)` 返回 34，
两个数量级的差直接坐实了布尔计数 bug；`bird_1068`：`AVG`=68.9 而 `SUM/COUNT`=68，
整数截断现形）。**有 1 道被自动判定为 confirmed，实际是反驳**：`bird_637` 的断言说该用
`TagName` 列，但 `check_sql`（`pragma_table_info`）查出来这张表**根本没有 `TagName` 这一列**——
SQL 正常执行、返回了一行，我的脚本只看"有没有返回值"，没有看返回的内容是不是支持断言。
其余约 19 道是"SQL 跑通了，但没有真正测到那句断言"的弱验证（比如只是抽样打印了某列的值，
没有对比"用这个字段 vs 用另一个字段"哪个才是对的）。

**教训**：`check_sql` 返回非空不等于断言为真，必须读返回内容跟断言文本对不对得上。
这跟本项目已经踩过的机械判定失效是同一类错误，只是这次是我自己新写的验证脚本踩了一次，
不是复用旧规则踩的。`verify_located_claims.py` 的自动分类现在只用于筛出"SQL 都执行失败"
这种硬故障，**不能拿它的 confirmed/refuted 标签当结论**。

## 定位本身不受这个问题影响

`check_sql` 验证不严谨，不代表"第一个错误句在第几句"这个定位错了——那是 LLM 单次判断给出的
候选，跟此前验证过的机制一样（10 道人工抽检 8/10 命中的那次）。受影响的只是"这句话确实是
错误起点"这个置信度分级，不是定位坐标本身。

## 下一步：真正的人工基准校准还没做

原计划（[`reasoning_trace_plan_2026-08-12.md`](../reasoning_trace_plan_2026-08-12.md)）
就要求"人工抽 20~30 道做基准校准"，这次因为语料量小（29 道）本可以全量做，
但还没有人（不管是我还是用户）真正逐条读过 claim 和 check_result 打分——
本文档上面的"约 8~9 道"是我做的第一遍人工判读，**不是独立校准，是同一个 AI 系统内部的复核**，
不能替代真正独立的人工基准。这是这一轮唯一还没完成的一步。

## 涉及文件

- `docs/analysis/analysisDetail/reasoning_capture_rc_corrected_run{1,2}_turn1.json`
- `docs/analysis/analysisDetail/sentence_labels_phaseA_run{1,2}.json`
- `docs/analysis/analysisDetail/located_phaseA_run{1,2}.json`、`located_phaseA_all29.json`
- `docs/analysis/analysisDetail/located_phaseA_verified.json`（含不可信的自动 verification 标签，
  仅供参考，不能引用其 confirmed/refuted 比例）
- `docs/analysis/analysisDetail/phase_a_source_map.json`（29 道题各自取自 run1 还是 run2）
