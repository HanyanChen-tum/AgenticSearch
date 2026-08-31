# DB-RLM 30 分钟 Presentation：Outline 与讲稿示例

版本：2026-08-30
用途：约 24 分钟正式讲述 + 6 分钟问答  
建议主 Deck：15 页；Backup：10 页

## 叙事主线

```text
Motivation & Research Question
  → System Architecture
  → Headline Results Chain
  → Error Statistics
  → Simple Counterfactual Tests
  → Concrete Cases
  → Executable Grammar as a General Framework
```

全场只回答三个问题：

1. 固定小模型、不做微调，只改变 inference-time system，能够提高多少？
2. RLM 三个机制中，收益究竟来自哪一个？
3. 剩余错误有什么共同模式，这些模式能否变成可验证、可执行的 grammar？

## 数字口径

主链准确率与资源指标统一放在下表。层 0–4 使用 corrected dev 上共同可计分的 491 题、每配置两次；`reasoning tokens` 与 `total tokens` 是每题均值，`latency` 是每题中位数。MB-A/MB-B 使用历史 core197 上固定 10 道空集触发题、每臂重复 3 次。

| 层 / 对照 | 配置 | 效果 | 相对上一层 / 对照 | Reasoning tokens / 题 | Total tokens / 题 | Agent turns / 题（LLM calls） | Median latency / 题 | 成本记录 |
|---|---|---:|---|---:|---:|---:|---:|---|
| 0 | B1 one-shot | 70.67% | — | 未记录 | 未记录 | 1.00（设计值） | 1.25s | 金额未记录 |
| 1 | + executable tool-loop bundle | 84.62% | +13.95pp | 2,891* | 8,092* | 2.14 | 15.10s | token workload 基准 1.00×；金额未记录 |
| 2 | + offline schema retrieval | 87.17% | +2.55pp | 3,307* | 9,768* | 2.32 | 14.35s | 相对第 1 层 1.21×；金额未记录 |
| 3 | + output post-processing | 87.58% | +0.41pp；噪声内 | 3,233* | 9,561* | 2.27 | 14.36s | 相对第 2 层 0.98×；金额未记录 |
| 4 | + depth-1 recursion | 88.19% | +0.61pp；噪声内 | 4,266* | 11,870* | 2.61 | 16.41s | 相对第 3 层 **1.24×**；金额未记录 |


`Reasoning steps` 不能被直接计数：API 不公开模型内部逐步推理过程。因此表中同时报告两个可观察代理——`Agent turns` 表示外部交互轮数，`reasoning tokens` 表示模型调用内部的推理量。二者不能互相替代。

`*` 少量调用缺失 usage，因此 reasoning-token 与 total-token 均值是下界。`†` MB-A/MB-B 只能确认额外调用次数相同。项目没有保存 Azure 部署的可复算单价或逐调用金额，不能可靠补写美元成本；表中以 total-token ratio 作为成本代理。当前第 3→4 层并非 matched-budget：递归使 reasoning tokens 增加约 32%、total tokens 增加约 24%、调用次数增加约 15%、中位延迟增加约 14%，准确率只增加 0.61pp，且仍在噪声范围内。历史 MB-A/MB-B 未记录 token、延迟和金额，所以更准确的名称是 **call-matched control**。

主链保守噪声上界使用 1.4pp。旧文档里的 70.5 → 83.9 → 86.5 → 86.9 → 87.2 是超时误判修正前口径，不与本表混用。

### 归因边界

- `+13.95pp` 是 **executable tool-loop bundle** 的增量：它联合引入数据库工具、执行观察与 observation-driven revision，现有实验不能把三者继续拆成独立百分点。
- `+2.55pp` 是当前主链中 offline schema retrieval 的逐层增量；core197 上另有一次专门消融得到 `+4.82pp`，因题集和分母不同，只作机制支持，不与主链数值合并。
- `+0.41pp` 与 `+0.61pp` 均低于 1.4pp 保守噪声上界，报告为 **no stable measurable effect**，不称为稳定提升。
- 历史 core197 上存在 E6-A/E6-B 三次重复，但只做到额外调用次数匹配，token、延迟和金额均未记录；它测的是“纯重试 vs 带确定性定位事实的文本反馈”，不是当前主链的 depth-1 DB leaf。

---

# 1. Motivation & Research Question

## Slide 1 — DB-RLM for Text-to-SQL（0:30）

### 页面内容

- DB-RLM: Understanding Where RLM Mechanisms Pay Off in Text-to-SQL
- Frozen generator: `gpt-5.4-mini`
- No fine-tuning

### 讲稿示例

> Large language models can generate SQL, but generating a valid query is not enough. The model must select the correct schema, understand the requested statistical grain, use database evidence, and match the benchmark's output conventions. In this project, I ask how far a frozen small model can go when we improve only its inference-time environment.

## Slide 2 — Motivation（1:10）

### 页面内容

四类困难：

- Schema selection and join paths
- Semantic reasoning: grain, aggregation, denominator and filters
- Execution grounding
- Output conventions and reference-answer format

### 讲稿示例

> Text-to-SQL is a useful setting for studying agentic reasoning because errors occur at several different layers. A query can be syntactically valid but use the wrong table. It can execute successfully but count rows instead of entities. It can even compute the intended value and still lose because the benchmark expects a different type, column arrangement, or tie convention.

## Slide 3 — Research Questions and Constraints（1:20）

### 页面内容

**RQ1.** How much can an inference-time DB-RLM system improve a frozen small model?  
**RQ2.** Which RLM mechanisms contribute the gain?  
**RQ3.** What limits further improvement: reasoning, conventions, or measurement?

约束：

- 同一个 generator
- 不允许 fine-tuning
- Gold 只用于离线评分和运行后诊断
- 允许改变环境、工具、预计算知识和可消融后处理

### 讲稿示例

> The constraint is part of the research question. I do not replace the model and I do not fine-tune it. I only change what the model can do at inference time: which tools it can call, which observations it receives, how schema information is organized, and whether deterministic post-processing is applied.

### 转场

> To answer these questions, I first decomposed RLM into three mechanisms, then mapped each mechanism to a concrete system intervention and ablation. Where two mechanisms enter together, I report the identification boundary instead of assigning them separate gains.

---

# 2. System Architecture

## Slide 4 — DB-RLM as Three Mechanisms（1:50）

### 页面内容

RLM 在本项目中不等于 recursion，而是三个可测量的部分：

| RLM 部分 | 能力 | 本项目的切入点 |
|---|---|---|
| ① Programmatic reasoning / exploration | 用程序搜索、选择和组合外部上下文 | train few-shot retrieval、offline schema retrieval、context-store 实验 |
| ② Executable environment | 在持久 REPL 中执行关键动作并保留 observation | Python REPL、`db.execute`、`db.sample_values`、execution trace |
| ③ Self-improvement and divide-and-conquer | 根据 observation 修改候选解，必要时分解给 leaf | observation-driven SQL revision + optional depth-1 DB leaf |

### 建议视觉

```text
① PROGRAMMATIC EXPLORATION — before the first model call
Question + Evidence → top-1 train few-shot + Offline Schema V4 → assembled prompt
                                                                    ↓
② EXECUTABLE ENVIRONMENT       Root Agent ↔ Python REPL / DB Tools ↔ Observation
                                                                    ↻
③ SELF-IMPROVEMENT             revise candidate SQL; optionally call depth-1 DB Leaf
                                                                    ↓
                                                               FINAL SQL
                                                                    ↓
                         Deterministic post-processing (not an RLM mechanism)
```

### 讲稿示例

> I do not use RLM as a synonym for recursion. I operationalize it as three mechanisms and start from each one separately. First, programmatic exploration controls how external knowledge is selected: before the first model call, the system retrieves one semantically similar training example and a question-specific Schema V4 fragment. Second, the executable environment gives the root agent a persistent Python REPL and live database tools, so candidate SQL produces real observations. Third, self-improvement uses those observations to revise the candidate, while the divide-and-conquer extension may delegate one unresolved subproblem to a depth-one database leaf. The final deterministic SQL rewrite is outside these three RLM mechanisms and is ablated separately.

## Slide 5 — Architecture as Experimental Design（1:20）

### 页面内容

| Layer | Added capability | Identification scope |
|---|---|---|
| B1 | One-shot SQL generation | Floor |
| Clean E0 | Executable tool-loop bundle | Tools + observations + revision jointly |
| E3-C no-convention | Offline schema retrieval | Incremental layer contrast |
| E3-C convention | Output post-processing | Deterministic, separately ablatable |
| Recursive DB | Depth-1 recursion | Treatment includes the recursion-enabling prompt |

两层证据回答两个不同问题：

| 方法 | 通俗地说 | 回答什么？ |
|---|---|---|
| 系统级消融 | 每次只增加一个系统能力，在同一批题上比较前后变化 | **整体上，哪一部分带来了提升？** |
| 逐题反事实实验 | 固定一段真实 trace，从不同位置重新生成，看答案是否改变 | **某一道错题为什么错，应该在哪里干预？** |

### 讲稿示例

> The architecture is also the experimental design. For the first RLM mechanism, I compare naive pruning, deterministic offline retrieval, and the fuller context-store form. For the second, I compare one-shot generation with an executable REPL and database tools. For the third, observation-driven revision enters with that tool loop, and depth-one decomposition is then tested as a further layer. This is a mechanism-driven design, but not every mechanism is perfectly isolated: tools, observations and root revision enter together in layer one, so I report their 13.95-point effect as a joint bundle.

> 后面的证据分成两层。消融实验看全局：加上一项能力以后，整批题平均提高多少。逐题反事实实验看局部：对一道已经答错的题，从 trace 的不同位置重新生成，检查错误是否会被改变。前者回答“什么有效”，后者回答“为什么错”；两者不能互相替代。

---

# 3. Headline Results Chain

## Slide 6 — Baseline 1 and the Negative Control（1:20）

### 页面内容

- B1: complete schema, one SQL answer, no database access, no revision — 70.67%
- B2: keyword-overlap top-five table pruning — 67.82%
- B2 vs B1: −2.85pp

### 讲稿示例

> Baseline 1 receives the schema and the benchmark evidence, but it must answer once. Baseline 2 adds a naive keyword table selector. The selector hurts by 2.85 percentage points because it removes structural information that the model later needs. This gives us a useful negative control: schema reduction is not automatically beneficial.

## Slide 7 — Five-Layer Results Chain（2:30）

### 建议视觉

使用阶梯图或 waterfall chart：

```text
70.67 ── +13.95 ── 84.62 ── +2.55 ── 87.17 ── +0.41 ── 87.58 ── +0.61 ── 88.19
  B1    Tool-loop bundle  Schema         Post-process       Recursion
```

### 讲稿示例

> This is the central result. The complete system gains 17.5 percentage points over the one-shot baseline. However, the return is extremely uneven. The executable tool-loop bundle contributes 13.95 points, which is about eighty percent of the total gain. Offline schema retrieval adds another 2.55 points. Output post-processing adds 0.41, and depth-one recursion adds 0.61. The last two increments are below the conservative 1.4-point noise bound and are therefore reported as having no stable measurable effect.

> Therefore, the result is not that RLM works or fails as a single object. The result is that its mechanisms pay off very differently.

### 数据来源（不放页面）

- 主链与重复：[`../analysis/week_2026-08-18/README.md`](../analysis/week_2026-08-18/README.md)
- 主链成本：[`../analysis/week_2026-08-18/reasoning_cost_2026-08-28.md`](../analysis/week_2026-08-18/reasoning_cost_2026-08-28.md)
- 30 秒 timeout 修正：[`../analysis/week_2026-08-18/sql_timeout_correction_2026-08-23.md`](../analysis/week_2026-08-18/sql_timeout_correction_2026-08-23.md)
- 原始结果：`../../results/bird_b1_corrected_run{1,2}.json` 与 `../../results/chain_*_corrected_run{1,2}.json`

## Slide 8 — 多想一点值不值？换大模型值不值？（1:45）

### 页面内容

**同一个 mini 模型：medium → high reasoning（同一次配对）**

| | Accuracy | 推理 token 中位数 | Total tokens / 题（均值） | LLM calls / 题 | 延迟中位数 |
|---|---:|---:|---:|---:|---:|
| Medium | 85.9% | 864 | 8,163 | 2.49 | 9.1s |
| High | 87.1% | 2,262 | 9,552 | 2.27 | 14.7s |
| 变化 | **+1.2pp** | **2.6×** | **1.17×** | −0.22 | **+5.6s** |

**同一 harness、同一配置：mini → normal（初步 model-scale control）**

| Reasoning | GPT-5.4 mini | GPT-5.4 normal | 差异 |
|---|---:|---:|---:|
| High | 70.2% | 71.0% | **+0.8pp** |
| Low | 68.0% | 71.6% | **+3.6pp** |

> 注：上下两张表来自不同实验口径，不能把 70% 与 87% 直接比较。

### 讲稿示例

> Accuracy 不是免费的。把同一个 mini 模型从 medium 调到 high，单次配对中多得到 1.2 个百分点，但推理 token 从 864 增加到 2,262，是原来的 2.6 倍；总 token 增加约 17%，中位延迟也从 9.1 秒增加到 14.7 秒。调用次数反而略微下降，说明模型不是多跑了几轮，而是在每次调用内部想得更久。

> 我们看不到模型内部真实的 reasoning step 数，所以这里不假装能数“思考了几步”。我们报告可以测量的四项：reasoning tokens、LLM calls、总 token 和延迟。

> 换成更大的 GPT-5.4 normal 后，high reasoning 下只比 mini 高 0.8 个百分点，这还在约 1.4 个百分点的运行噪声内；low reasoning 下差距更大，是 3.6 个百分点。一个通俗的理解是：计算预算较小时，大模型的能力优势更明显；给 mini 更多内部推理后，差距可能缩小。但这只是初步证据，不能据此宣布两个模型具有完全相同的上限。

> 因此，剩余错误不能全部归咎于“小模型不够强”。接下来我们固定模型，并逐项检查 schema、工具循环、prompt 和输出规则，再直接分析失败样本。

### 数据来源（不放页面）

- Reasoning-effort 与成本：[`../analysis/week_2026-08-18/five_layer_chain_results_2026-08-19.md`](../analysis/week_2026-08-18/five_layer_chain_results_2026-08-19.md)；原始文件 `../../results/effort_medium_conv_rules_run1.json` 与 `../../results/chain_e3_c_conv_rules_corrected_run1.json`
- Model-scale 数字来自现有 “Model Scale Comparison” 对照页；进入最终 Deck 前必须补上原始结果文件、共同分母和重复次数

---

# 4. Understanding the Remaining Errors

## Slide 9 — 46 个错误到底是什么？（1:20）

### 建议视觉

横向条形图；如果暂时不用图，可直接使用下表。

**46 题来源：** 两次完整运行的 failure，经过预先定义的 triage，并保留具有有效反事实曲线的记录。它是 failure-selected diagnostic set，不是全部错误或随机样本。

| 错误类型 | 数量 | 占 46 题 |
|---|---:|---:|
| 内容算对，但类型或输出形状不对 | **11** | **24%** |
| 选错列或表 | 6 | 13% |
| 计数粒度或去重错误 | 6 | 13% |
| NULL / 缺失值处理错误 | 4 | 9% |
| 漏掉或多加过滤条件 | 4 | 9% |
| 公式或分母口径错误 | 4 | 9% |
| 百分比忘记乘 100 | 3 | 7% |
| 题意理解错误 | 3 | 7% |
| 缺少一次聚合 | 2 | 4% |
| 其它 | 3 | 7% |

### 演讲稿

> 前面我们看到，系统准确率已经达到 88.19%。接下来要问的是：剩下的题为什么还会错？我们从两次完整运行中收集 failure，按照预先确定的规则筛选，最后留下 46 题。这些题专门用于诊断失败，不代表整个 benchmark 的自然错误比例。[候选池构建](../analysis/week_2026-08-18/phase_a_turn_resampling_2026-08-24.md)

> 我们逐题比较问题、数据库、模型 SQL、参考 SQL 和执行结果。最大的类别不是完全不会做，而是内容基本正确，返回类型或形状不对，一共有 11 题。另外，6 题选错表或列，6 题数错对象，还有 4 题没有正确处理 NULL。[逐题根因表](../analysis/week_2026-08-18/flatzero_23_root_causes_2026-08-25.md)

> 这说明剩余错误不是同一种问题，也不可能只靠一句“再想一遍”解决。但统计只能告诉我们错成什么样，不能证明为什么错。所以下一步，我们主动改变 reasoning trace。

## Slide 10 — 我们怎样验证“错误原因”？（1:25）

### 页面内容

这里有两个维度：`k` 是**从哪里重新开始生成**，`N` 是**在同一个位置重复多少次**。

```text
原 trace：Question ── Turn 1 / Obs. 1 ── Turn 2 / Obs. 2 ── Turn 3 / Obs. 3 ── …
              ↑                    ↑                    ↑
           k = 1                k = 2                k = 3
       不固定模型回答        固定第 1 轮后重生成      固定前 2 轮后重生成

对每一个 k：保留 k 之前完全相同的真实 prefix
                 ↓
          独立重采样 N = 10 次
                 ↓
   得到该位置的正确率 = 正确 FINAL / 有效样本
```

| 设置 | 具体做法 |
|---|---|
| 题目 | 上一页人工检查的全部 46 个 failure；不是随机全数据集样本 |
| `k`：重生成起点 | `k=1` 从第一轮开始生成；`k=2` 固定真实第 1 轮后再生成；依此类推。`K` 取决于原 trace 有多少轮，本实验最多到 `k=4` |
| `N`：每个起点的样本数 | 对每一个 `k` 的相同固定 prefix 发出 `N=10` 个独立 API 请求；模型和 `reasoning_effort=high` 不变 |
| 模拟真实 Agent | 若输出的是工具草稿，就真实执行并把 observation 喂回；最多再续写 2 次得到干净 FINAL |
| `k` 点正确率 | 该 `k` 下“正确 FINAL 数 ÷ 有效 continuation 数”；少数 `k` 只有 4–9 个有效样本 |

### 演讲稿

> 我们使用逐轮反事实重采样。简单来说，就是保留同一道题和同一段历史，只改变模型从哪里重新回答。图里的 `k` 是起点：`k=1` 从问题开始；`k=2` 保留原来的第一轮和工具结果，再继续生成；`k=3` 再多保留一轮。这批 trace 最长到 `k=4`。

> 在每个起点，我们独立生成 10 次，也就是 `N=10`。十次看到相同的问题、schema 和前文；如果模型调用工具，我们也真实执行并回传结果。最后，计算每个起点答对的比例。

> 如果固定某一轮以后，后续正确率明显变化，才说明这个位置可能真的重要。只读 trace 时，一句可疑的话很容易被误认为原因；反事实实验要求它能够改变结果。这与 Thought Anchors 的干预思路相近，也回应了 reasoning trace 可能并不忠实的问题。[Bogdan et al., 2025](https://arxiv.org/abs/2506.19143)；[Turpin et al., 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract.html)

### 数据来源（不放页面）

- [Phase A turn-resampling 实验](../analysis/week_2026-08-18/phase_a_turn_resampling_2026-08-24.md)

## Slide 11 — 从不同位置重新生成，会发生什么？（1:35）

### 页面内容

```text
横轴：重生成起点 `k=1,2,…,K` 沿原 trace 后移，固定的原始轮次越来越多
纵轴：每个 `k` 上 N=10 次重采样的正确 FINAL 数 / 有效样本数
```

| 类型 | 数量 | 正确率曲线是什么意思？ | 对改进系统的意义 |
|---|---:|---|---|
| Flat-zero（全程接近 0） | **23 / 46（50%）** | 所有 checkpoint 都低于约 15%：从很早重答也不会 | 同模型再想一次帮助有限；需要新信息、训练或规则 |
| Non-monotonic（上下波动） | **14 / 46（30%）** | 曲线先升后降或再次回升：没有唯一转折点 | 需要可靠 verifier，而不只是生成更多候选 |
| Locked-in（某一步后锁死） | **5 / 46（11%）** | 早期至少约 30%，固定某一步后降到 15% 以下且不再恢复 | 适合在 commitment 前做 targeted A/B |
| High-band（始终较高） | **4 / 46（9%）** | 所有 checkpoint 都在约 50% 以上：原 failure 是低概率事件 | 可尝试多次采样或同强度 voting |

### 演讲稿

> 每道题都会得到一条正确率曲线，我们把它们分成四类。Flat-zero 有 23 题，占一半：无论从哪里重答都几乎一直错，所以同一个模型多试几次帮助有限。Non-monotonic 有 14 题：有时对、有时错，没有唯一转折点，更需要可靠的答案选择器。

> Locked-in 只有 5 题：前面还有机会答对，但固定某一步以后就几乎一直错，适合在那个决定之前干预。最后 4 题是 High-band：从各个位置重答都经常正确，原来的错误更像偶然抽样，适合 retry 或 voting。

> 关键是，46 题中只有 5 题支持明确的“锁死位置”。所以 reasoning trace 可以提出原因，但不能单独证明原因。[实验结果](../analysis/week_2026-08-18/phase_a_turn_resampling_2026-08-24.md) 下面这个案例就说明，一个很合理的解释，实验以后可能完全相反。

## Slide 12 — Example：Few-shot 真的是错误来源吗？（1:15）

### 页面内容

案例：`bird_637`

| 问题 | 证据 |
|---|---|
| Query | “Mark Meckes 没有评论的帖子有哪些 tags？” |
| 数据库真实值 | `posts.Tags = '<books>'`，评论数为 0 |
| 模型错误 | 把一个完整字符串拆成 `books` |
| 最初猜测 | few-shot 示例把模型带偏了 |
| 验证方法 | 其它内容不变，只比较保留和删除 few-shot |
| 实验结果 | 保留：**10/13 正确（77%）**；删除：**2/13 正确（15%）** |

### 演讲稿

> 这道题询问 Mark Meckes 没有评论的帖子带有什么 tag。数据库中的完整字符串是 `<books>`，模型却返回了 `books`。因为检索到的 few-shot 使用了另一种 tag 结构，我们最初怀疑是它把模型带偏了。

> 我们保持其它设置不变，只删除 few-shot。结果与直觉相反：保留时，13 次有效回答中有 10 次正确；删除后只剩 2 次，字符串拆分错误也从 2 次增加到 9 次。[`bird_637` A/B](../analysis/week_2026-08-18/phase_a_turn_resampling_2026-08-24.md)

> 所以，在 reasoning trace 中“看起来像原因”的内容仍然只是一个假设。必须真正改变这个因素，再观察结果。接下来，我们不再停留在单个案例，而是寻找跨题重复出现的决定。

## Slide 13 — 重复出现的 Decision Patterns（0:50）

### 页面内容

| 跨题重复出现的决定 | 在错误输出中的表现 |
|---|---|
| 返回数字、文字、一行还是多行？ | 类型或输出形状不匹配 |
| 信息来自哪个表和哪一列？ | 选错 source |
| 数的是实体还是记录？ | 计数粒度或 `DISTINCT` 错误 |
| NULL、0 或其它特殊值是否有效？ | 缺失值处理错误 |
| 分子、分母和过滤条件是什么？ | 公式或筛选范围错误 |

### 演讲稿

> 从整体看，这些错误虽然来自不同数据库，却反复涉及五个决定：输出形式、数据来源、计数对象、NULL 处理，以及公式和过滤范围。[逐题根因表](../analysis/week_2026-08-18/flatzero_23_root_causes_2026-08-25.md)

> 这说明错误不是完全随机的，而是具有可以抽象的结构。不过，我们目前找到的是 recurring decision patterns，还不是完整的 state machine。反事实重采样告诉我们何时干预，这五类模式告诉我们检查什么。两者结合起来，就得到下一页的实验。

---

# 5. Discussion and Future Work

## Slide 14 — 从诊断到完整 Agent 验证（1:10）

### 页面内容

**从诊断到干预：** 反事实重采样表明，通用重试不是主要答案；对可能被早期决定锁死的错误，我们在写 SQL 前加入 Answer Contract。

```text
Counterfactual diagnosis → pre-commitment Answer Contract → full-agent A/B/C
```

> **排版占位：下表是预测，不是实验结果。完整 498 题和重复运行结束后必须替换。**

| Full-agent arm | 预测 accuracy | 相对 A | 预测 reasoning cost |
|---|---:|---:|---:|
| A — No pre-read | ≈ **87.9%** | — | baseline |
| B — Generic pre-read | ≈ **88.1%** | ≈ +0.2pp | +5%～8% |
| C — Structured Contract | ≈ **88.4%** | ≈ +0.5pp | +8%～12% |

**预测解释：** `A ≈ B ≈ C`；Contract 可能略高，但差异很可能仍在 1.4pp 噪声范围内，因此不应默认启用，只考虑针对性使用。

**已经得到的参考证据**

| Preserve tied rows | Numeric rounding |
|---:|---:|
| **Net +5** | **Net +2～3** |

**最终原则：** 预测不进入 final claim；完整 agent 的 accuracy、rescue/damage 和 cost 决定是否采用。

### 演讲稿

> 前面的反事实分析说明，通用重试不是主要答案，所以我们把干预放在写 SQL 之前。Answer Contract 让模型先明确输出形式、数据来源、计数对象、NULL 处理和计算公式。完整实验比较直接生成、相同预算的普通分析，以及结构化 Contract；中间一组用来区分“多读一遍题”和 Contract 结构本身的效果。

> 这里的数字目前只是排版预测，不能作为最终结论。如果实际结果接近这个形状，那么三组准确率没有稳定差异，而 Contract 增加了 reasoning cost，因此不应该默认用于所有题，只适合针对高风险的 early-commitment 情况。作为参考，两个定义清楚的输出规则已经取得净加 5 和净加 2 到 3。[规则双向重放](../analysis/week_2026-08-18/rootcause_58_2026-08-27.md) 最终是否采用，必须由完整 agent 的准确率和成本决定。

## Slide 15 — Conclusion & Future Work（1:10）

### 页面内容

**What did we learn?**

- Agent architecture matters：准确率从 **70.67% 提升到 88.19%**。
- Executable tool loop 贡献了最大的提升：**+13.95 个百分点**。
- 更多 reasoning 不一定更好：recursion 使用了 **32% 更多 reasoning tokens**，但只增加了 **0.61 个百分点**，仍在实验噪声范围内。

**Broader outlook**

- 重复出现的 reasoning patterns 表明，部分推理过程可能被整理成**可执行、可验证的知识**。
- 跨数据库泛化和 smaller-model execution 是这个 framework 的潜在扩展，**不是本项目已经证明的结果**。

**Takeaway：** DB-RLM 是我们迈向通用 framework 的第一个 test case；目标是实现可复用、高效、可验证的 reasoning。

### 演讲稿

> 最后有三个结论。第一，不更换模型，只改 agent architecture，准确率就从 70.67% 提升到 88.19%。第二，最大的收益来自 executable tool loop，贡献 13.95 个百分点，说明查询数据库、看到结果再修改答案，比单纯延长内部思考更重要。第三，更多 reasoning 不一定更好：recursion 多用了 32% 的 reasoning tokens，却只增加 0.61 个百分点，而且仍在噪声范围内。

> 这些结果也带来一个更广的启发：reasoning 不一定只能以一次性的长 trace 存在。如果选表、计数和 NULL 处理等模式能够在不同任务中反复验证，它们就可能被整理成可执行、可审计的知识，部分稳定步骤也可能由 smaller models 执行。本项目还没有证明这种跨任务泛化；DB-RLM 提供的是第一个可执行、可验证的 test case，并为更通用的 reasoning framework 提供了初步证据。

---

# 建议的 Backup Slides

## Backup 1 — Baseline Provenance

- Legacy B1 stored strict score: 52.40%
- Official set-comparison rescore: 55.20%
- Corrected dev498 reruns: 70.68% / 70.48%
- 不把 55.20 → 70.67 写成方法收益，因为题面/evidence 版本不同

## Backup 2 — Why 491, 496 and 498 Differ

- 491：所有主链 arms 的共同可计分题，用于因果层间比较
- 496：部分最好 arms 的自身可计分分母，用于描述绝对水平
- 498：corrected dev 唯一题总数

## Backup 3 — Clean E-Series Ledger

- E0: 34.26% on adversarial core197
- E1 strict final: rejected
- E3-A static patterns: directional only
- E3-B patterns replace few-shot: rejected
- E3-C schema: accepted
- E4-A QueryPlan: rejected
- E5-A context store: accurate but costly
- E6: no stable recursion effect

## Backup 4 — Reasoning-Effort Repeats

| Effort | Two-run mean | Same-set difference |
|---|---:|---:|
| minimal | 69.45% | 5.4pp |
| low | 82.60% | 2.2pp |
| medium | 84.80% | 2.2pp |
| high | 87.0% | 0.2pp |

## Backup 5 — Recursion Triggered-Subset Details

- Run 1: 74 triggered questions
- Run 2: 64 triggered questions
- Conditional signs are opposite
- Recursion call overlap is unstable

## Backup 6 — Budget Audit and Call-Matched Control

实验范围：历史 core197；固定 10 道空集触发题；相同模型与参数；每臂多一次调用；各重复 3 次。

| Treatment | Extra calls / trigger | Token | Latency | Monetary cost | Wrong → correct | Net |
|---|---:|---:|---:|---:|---:|---:|
| Deterministic rewrite | 0 | 0 | Offline only | 0 API cost | 1 | +1 |
| E6-A extra retry | +1 | 未记录 | 未记录 | 未记录 | 1/25 = 4.0% | 0 |
| E6-B retry + deterministic localization | +1 | 未记录 | 未记录 | 未记录 | 1/23 = 4.3% | −1 |

- E6-A and E6-B are statistically indistinguishable
- Their only recoveries occurred in different questions and only one of three repeats
- E6-A and E6-B match additional call count, but exact token, latency and monetary budgets cannot be verified
- It does **not** constitute a strict matched-budget test of the current depth-1 DB leaf

## Backup 7 — Causal Literature and Evidence Matrix

| 用途 | 文献 | 本项目中的对应做法 |
|---|---|---|
| Potential outcomes / treatment definition | [Rubin, 2005](https://doi.org/10.1198/016214504000001880) | 先定义 unit、treatment、outcome 与 population |
| NLP significance testing | [Dror et al., 2018](https://aclanthology.org/P18-1128/) | 同题配对、重复运行、报告噪声边界 |
| Compute and run reporting | [Dodge et al., 2019](https://aclanthology.org/D19-1224/) | token、calls、latency 与效果一起报告 |
| Counterfactual trace intervention | [Bogdan et al., 2025](https://arxiv.org/abs/2506.19143) | 固定 turn prefix 后重采样 continuation |
| CoT faithfulness limitation | [Turpin et al., 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract.html) | trace 只生成假设，不单独证明因果 |
| Recursive inference | [Zhang et al., 2025](https://arxiv.org/abs/2512.24601) | 对 depth-1 leaf 同时报 effect、异质性与预算 |
| Execution-aware feedback | [ReEx-SQL, 2026](https://aclanthology.org/2026.acl-long.35/) | 用可执行 outcome 验证 correction，而非只读解释 |
| Reasoning distillation | [Hsieh et al., 2023](https://aclanthology.org/2023.findings-acl.507/) | 支持把大模型的 reasoning information 交给 smaller model 的未来方向 |
| Model routing / cascade | [RouteLLM, 2024](https://arxiv.org/abs/2406.18665)；[FrugalGPT, 2023](https://arxiv.org/abs/2305.05176) | 已有互补方案；选择模型，不等于编译结构性错误规则 |

## Backup 8 — Deterministic Rule Evaluation

| Rule | Rescue | Damage | Status |
|---|---:|---:|---|
| keep_ties | 7 / run | 2 / run | Offline evidence positive |
| printf_to_round | 2–3 / run | 0 | Offline evidence positive |

## Backup 9 — Limitations

- Sampling parameters were not fully fixed in historical runs
- Aggregate stability does not imply item-level stability
- core197 and Phase A are selected failure-heavy populations
- Failure taxonomy lacks independent second-person calibration
- Rule generalization has not been tested on a second split
- Recent online runs are affected by response-format drift
- The current depth-1 DB leaf lacks a full-set token- and cost-matched Extra-Root control; the historical core197 E6 experiment matches only the number of extra calls
- 自动 grammar mining 和 small-model offloading 尚未验证；当前证据只支持两条人工发现、反事实验证的 executable rules

## Backup 10 — 怎样区分模型、系统和 Benchmark 限制？

| 干预以后观察到什么？ | 更可能是什么问题？ |
|---|---|
| 架构不变，只换 normal 后稳定答对 mini 的错题 | **模型能力限制** |
| 模型不变，只换 schema、loop 或 prompt 后答对 | **外部系统 / 架构限制** |
| 两种模型和多种配置都失败，且检查发现 gold 有歧义或错误 | **Benchmark / 评测限制** |
| 都失败，但 gold 已确认正确 | **暂时无法确定**，可能是共同的推理盲点 |

这是回答问题时使用的**归因判断框架**，不是已经得到各类别数量的实验结果。不能只看一条 reasoning trace 就归因；trace 用来提出假设，A/B、重采样和数据库执行用来验证。[Turpin et al., 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract.html)

# 问答时的关键回答

## “Why not simply say recursion failed?”

> The measured increment is inside the noise band and the triggered-subset effect changes sign between runs. The evidence supports “no stable effect is measurable in this setting,” not a universal claim that recursion cannot work.

## “Did you control for recursion simply adding another model call?”

> Only at the call-count level. In the historical core197 experiment, E6-A and E6-B used the same trigger set, model and parameters, and both added one call per triggered instance. A pure retry recovered 1 of 25 wrong cases, or 4.0 percent; deterministic predicate-localization feedback recovered 1 of 23, or 4.3 percent. But token usage, latency and monetary cost were not logged, so I call this call-matched rather than strictly matched-budget. The current depth-one leaf itself uses about 24 percent more tokens, 15 percent more calls and 14 percent more median latency than its parent.

## “Is the +13.95pp caused by tools or by more reasoning?”

> The layer jointly introduces the executable environment and observation-driven revision, so the two cannot be fully separated. The reasoning-effort sweep suggests substitution between internal reasoning and external trial, but Baseline 1 does not record explicit reasoning effort. I therefore present this as a mechanistic clue rather than a complete causal decomposition.

## “Is post-processing cheating?”

> Any post-processing that changes predictions is part of the system under test and must be separately ablated. I distinguish shape normalization from semantic rewriting and report both rescue and damage on the full set.

## “Why call these effects causal rather than correlations?”

> 因为 treatment 和 outcome 是预先定义的，并在同一批题、同一 corrected gold 与 evaluator 下做 paired comparison；规则与逐题机制还使用了 replay、A/B 或 executable counterfactual。但 sampling 没有完全固定、重复次数有限、递归预算也未严格匹配，所以我把结论限定为 “causally credible under this harness”，而不是普遍因果定律。

## “Can a reasoning trace prove the cause?”

> 不能。Trace 只用于提出可证伪假设。`bird_637` 的 trace 假设在 targeted A/B 中被反证；`bird_928` 的 NULL claim 则由原 SQL 和反事实 SQL 的不同执行结果支持。因果结论来自干预后的 outcome，而不是解释文本本身。

## “既然已经找到问题，为什么不继续修？”

> 我们继续验证了，但不会把每一道错题都直接写成补丁。对全部 46 题做重采样后，23 题从各个位置重新生成仍接近零；few-shot 删除实验也推翻了最初的直觉。对于能够跨题重复、精确定义的模式，我们才写成候选规则并在全集上检查 rescue 和 damage。`keep_ties` 与 `printf_to_round` 通过了这个标准，其它没有正净收益的想法不进入系统。

## “Why not simply use a large/small model cascade?”

> 这是合理而且已有充分研究的工程方案。Model routing 解决的是“整道题交给哪个模型”；我们的 framework 解决的是“反复出现、可以测量的结构性错误能否被编译成确定性规则”。验证过的规则不增加 inference-time model call，而且 rescue、damage 和适用范围都可以审计。两种方法可以组合，但本项目没有测试 small-model offloading，因此不把它写成已经证明的收益。

## “What is the strongest contribution?”

> 已完成实验中最强的结果仍然是机制分解：主要收益来自 executable tool-loop bundle 和 schema retrieval。更广泛的研究意义来自错误分析：跨数据库重复出现的 output、counting、NULL、filter 等差异，可以被抽象为候选规则，再通过全集反事实重放验证。当前已验证的是两条人工发现的 executable rules；自动 grammar mining 仍属于 future work。
