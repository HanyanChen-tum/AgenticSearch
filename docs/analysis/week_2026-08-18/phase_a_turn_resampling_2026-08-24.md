# Phase A 轮次级反事实重采样：首批 5 道（2026-08-24）

Phase A 首轮的定位是一次 LLM 判断，属于观察性证据。本文记录第一次用**测量**代替判断的结果：
在每个轮次边界截断，重采样 N=10，看 P(答对 | 前 k 轮固定) 怎么变。这是 Thought Anchors
的 resampling importance，**轮次粒度**（句子粒度为何做不到，见
[`reasoning_trace_plan_2026-08-12.md`](../reasoning_trace_plan_2026-08-12.md) §论文方法 vs 本项目）。

脚本：[`scripts/resample_turn.py`](../../../scripts/resample_turn.py)，
语料 `e3_c_rules_reasoning_corrected_run1`，输出 `analysisDetail/phaseA_resample/turn{1..4}.json`。

## 结果

分母是有效样本数（模型这一轮输出工具调用而非 `FINAL()` 的样本不计分）。

| 题 | k=1 | k=2 | k=3 | k=4 |
|---|---|---|---|---|
| `bird_637`  | **7/9 (78%)** | 0/8 (0%) | 0/9 (0%) | — |
| `bird_587`  | 1/10 (10%) | 5/7 (71%) | 0/9 (0%) | 2/10 (20%) |
| `bird_465`  | 0/7 (0%) | 1/7 (14%) | 0/8 (0%) | 0/8 (0%) |
| `bird_1068` | 0/8 (0%) | 0/9 (0%) | — | — |
| `bird_173`  | 崩溃 | 0/5 (0%) | 0/9 (0%) | 0/9 (0%) |

**5 道分成三种形态，不是一种。** 这本身是第一个结论：

- **锁死型**（`bird_637`）：从零开始 78% 对，第 1 轮固定后归零。跌落 0.78 就是第 1 轮的
  测得重要性。这是一个干净的因果承诺点。
- **非单调型**（`bird_587`）：10% → 71% → 0% → 20%。k=1→k=2 上升说明记录里的第 1 轮
  **是有帮助的**，伤害发生在第 2→3 轮，k=4 又部分恢复。**这道题没有"第一个错误承诺点"**——
  Phase A 定位脚本的前提在这里不成立。
- **平零型**（`bird_1068`、`bird_465`、`bird_173`）：处处接近 0，包括从零开始。
  重采样在这类题上测不到任何东西，**必须换成介入臂**，光重采样是瞎的。

## `bird_637`：机制完全可见

题目：`State all the tags used by Mark Meckes in his posts that doesn't have comments.`

gold 是最朴素的写法——`SELECT DISTINCT p.Tags`，整串 `<bayesian><prior>` 原样返回。

两次真实运行都失败，而且**方向一致**：run1 用 `WITH RECURSIVE split(...)` 把标签串拆成单个
标签，run2 去 `INNER JOIN tags AS t` 取 `t.TagName`。k=1 的 9 个有效样本里，7 个写了朴素
版本并且答对，2 个走了 RECURSIVE 拆分并且答错——**失败与"拆分"完全同现**。

读 trace 看到三件事：

1. **第 1 轮在看到任何工具结果之前就已经提交了 `WITH RECURSIVE` 的临时 `FINAL()`。**
   同一轮里发出的 `db.sample_values` 观察在下一条消息才回来。承诺先于观察。
2. **诱因很可能是检索到的 few-shot 例子**，它就在 prompt 里：
   `Q: What are the tags of the release "sugarhill gang"?` /
   `SQL: SELECT T2.tag FROM torrents AS T1 INNER JOIN tags AS T2 ON T1.id = T2.id ...`
   ——一个"标签在独立表里、一行一个"的模板。run2 的 `INNER JOIN tags AS t` 几乎是它的
   逐字模仿。两次运行的错误方向都对得上这个例子，对不上题目。
3. **工具循环有机会纠正而没有纠正。** 第 2 轮真的把递归查询跑了一遍，
   返回 `{"rows":[["books"]]}` 只有一行，模型看到之后原样提交了。

所以这道题的失败不是"模型不会写"，是**被检索到的样例带偏，且工具观察没能把它拉回来**。

## 这给出了第二步介入臂的具体设计

原计划的介入臂是"注入断言的真值"。`bird_637` 提示了一个更好、更便宜、且直接指向
**被测系统组件**的介入：

- 臂 A：原样重采样（本文 k=1 列，已有）
- 臂 B：**删掉或替换检索到的 few-shot 例子**，其余不变，重采样同样次数

B 显著高于 A → few-shot 检索器是失败的因果来源之一。这比"注入事实"更有价值，因为
它检验的是 e3-c 自己的一个部件，可消融、可改，正好落在"用因果关系找 agent 问题"上。

## 边界（必须跟结果一起引用）

1. **k=1 的语义不是"agent 有 78% 概率答对"。** `resample_turn.py` 只生成一轮、要求
   `FINAL()`，所以 k=1 测的是"**被迫直接作答**时答对的比例"。真实 agent 在这道题上用了
   3 次调用并且失败。正确的读法是：**直接作答在这道题上强于工具循环**——这与本项目
   `minimal ≈ B1` 的替代关系结论同向，但不是同一个测量。
2. **n 极小**：5 道题、每题约 10 个样本。三种形态的存在是可靠的（78% vs 0% 不是噪声），
   但各形态的占比完全未知，不能外推到 28 道。
3. **`bird_173` 的 k=1 缺失**：Azure 内容安全 `invalid_prompt` 误判，即
   [`harness_defects_2026-08-18.md`](harness_defects_2026-08-18.md) §五 已诊断的
   `BadRequestError`。它在 `resample_turn.py` 批处理里会**掀掉整个 k 批次**
   （`f.result()` 直接抛出），turn1.json 只存下先完成的 4 道。铺开前要加 per-sample
   兜底，否则一条误判会毁掉一整轮的预算。
4. **`bird_518`、`bird_701` 永远不能进重采样**：30 秒超时修正走
   `indexed_reexecution`，没有回填 `gold_answer`（现为 `None`），而
   [`shared/evaluator.py:46`](../../../shared/evaluator.py) 对 `None` 一律返回 `False`——
   跑了会得到一个看起来很漂亮的 0/10，实际是评分函数在跟 `None` 比较。

## 对 Phase A 前提的影响

`locate_first_wrong_sentence.py` 假设"存在第一个承诺错误的句子"。`bird_637` 证明这个假设
有时成立且可测量；`bird_587` 证明它有时不成立。**这个前提本身应当逐题检验，而不是默认。**
轮次曲线正好是检验它的工具：单调下跌一次到底 → 前提成立；非单调 → 前提不成立。

另注：`bird_637` 的定位断言此前被 `check_sql` 反驳（见
[`phase_a_first_pass_2026-08-23.md`](phase_a_first_pass_2026-08-23.md)），但重采样独立证实
**第 1 轮确实是承诺点**。即：位置对，理由错。这支持该文档"定位本身不受验证问题影响"的说法。
