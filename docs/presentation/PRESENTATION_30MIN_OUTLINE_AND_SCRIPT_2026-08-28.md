# DB-RLM 30 分钟 Presentation：Outline 与讲稿示例

版本：2026-08-28  
用途：约 24 分钟正式讲述 + 6 分钟问答  
建议主 Deck：17 页；Backup：8 页

## 叙事主线

```text
Motivation & Research Question
  → System Architecture
  → Headline Results Chain
  → The Gold-Set Ceiling Finding
  → Failure Analysis
  → Negative Results: Recursion
  → Conclusion & Next Steps
```

全场只回答三个问题：

1. 固定小模型、不做微调，只改变 inference-time system，能够提高多少？
2. RLM 三个机制中，收益究竟来自哪一个？
3. 剩余错误来自模型、gold conventions，还是评测基础设施？

## 数字口径

主结果统一使用 corrected dev 上 491 道共同可计分题、每配置两次、修正 SQL 30 秒超时误判后的口径：

| 层 | 配置 | 均值 | 相对上一层 |
|---|---|---:|---:|
| 0 | B1 one-shot | 70.47% | — |
| 1 | + executable tool loop | 84.32% | +13.85pp |
| 2 | + offline schema retrieval | 86.86% | +2.55pp |
| 3 | + output post-processing | 87.37% | +0.51pp |
| 4 | + depth-1 recursion | 87.47% | +0.10pp |

保守噪声上界使用 1.4pp。旧文档里的 70.5 → 83.9 → 86.5 → 86.9 → 87.2 是超时误判修正前口径，不与本表混用。

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

> To answer these questions, I designed the system so that every major capability could be switched on and measured independently.

---

# 2. System Architecture

## Slide 4 — DB-RLM Architecture（1:30）

### 建议视觉

```text
Question + Evidence
        ↓
Offline Schema Retrieval
        ↓
Root Reasoning Agent
        ↓
Python REPL + DB Tools
        ↓
Database Observation
        ↓
Optional Depth-1 Leaf
        ↓
FINAL SQL
        ↓
Optional Deterministic Post-processing
```

### 讲稿示例

> The root agent operates inside a persistent Python environment. It can execute SQL, sample stored values, observe errors or empty results, and revise its query before submission. Offline retrieval provides question-specific schema fragments. For selected questions, the root may delegate one subproblem to a depth-one leaf. Finally, deterministic rules can transform the submitted SQL, but these rules are treated as a separate ablatable component.

## Slide 5 — Architecture as Experimental Design（1:20）

### 页面内容

| Layer | Added capability |
|---|---|
| B1 | One-shot SQL generation |
| Clean E0 | Executable tool loop |
| E3-C no-convention | Offline schema retrieval |
| E3-C convention | Output post-processing |
| Recursive DB | Depth-1 recursion |

### 讲稿示例

> The architecture is also the experimental design. Instead of comparing a simple baseline against one large agent, I add one capability at a time. This allows the final score to be decomposed into mechanism-level increments.

---

# 3. Headline Results Chain

## Slide 6 — Baseline 1 and the Negative Control（1:20）

### 页面内容

- B1: complete schema, one SQL answer, no database access, no revision — 70.47%
- B2: keyword-overlap top-five table pruning — approximately 67.5%
- B2 vs B1: approximately −3.0pp

### 讲稿示例

> Baseline 1 receives the schema and the benchmark evidence, but it must answer once. Baseline 2 adds a naive keyword table selector. The selector hurts by around three percentage points because it removes structural information that the model later needs. This gives us a useful negative control: schema reduction is not automatically beneficial.

## Slide 7 — Five-Layer Results Chain（2:30）

### 建议视觉

使用阶梯图或 waterfall chart：

```text
70.47 ── +13.85 ── 84.32 ── +2.55 ── 86.86 ── +0.51 ── 87.37 ── +0.10 ── 87.47
  B1        Tools        Schema         Post-process       Recursion
```

### 讲稿示例

> This is the central result. The complete system gains seventeen percentage points over the one-shot baseline. However, the return is extremely uneven. The executable tool loop contributes 13.85 points, which is about eighty-one percent of the total gain. Offline schema retrieval adds another 2.55 points. Output post-processing adds 0.51, and depth-one recursion adds only 0.10. The last two increments are below the conservative 1.4-point noise bound.

> Therefore, the result is not that RLM works or fails as a single object. The result is that its mechanisms pay off very differently.

## Slide 8 — Mapping the Gain to RLM Mechanisms（1:30）

### 页面内容

| RLM mechanism | Project implementation | Result |
|---|---|---:|
| Executable environment + self-improvement | REPL, DB tools, observation-driven revision | +13.85pp |
| Programmatic exploration, weakened form | Deterministic schema retrieval | +2.55pp |
| Programmatic exploration, full form | Autonomous context store | Accuracy flat; cost higher |
| Divide-and-conquer | Depth-1 leaf | +0.10pp, inside noise |

### 讲稿示例

> The largest return comes from allowing the model to gather evidence and revise before commitment. Programmatic exploration helps when a deterministic program selects and delivers relevant schema information. The full context-store form does not help here because the prompt occupies only about four percent of the available context window, so externalization solves a constraint that is not present. Recursive divide-and-conquer produces no measurable stable gain.

---

# 4. The Gold-Set Ceiling Finding

## Slide 9 — A Benchmark-Imposed Ceiling（1:50）

### 页面内容

示例：

- Return one maximum row or all tied rows?
- `COUNT(*)` or `COUNT(DISTINCT entity)`?
- Numeric `ROUND()` or text-producing `printf()`?
- One row with three columns or three rows with one column?
- Gold SQL itself timing out

### 讲稿示例

> Part of the measured ceiling does not come from missing model capability. It comes from conventions encoded in the reference answers. For example, the question may not specify whether all tied maxima should be returned. The model may use SQLite `printf` to obey a decimal-format instruction, but `printf` returns text while the gold query returns a number. In these cases, additional reasoning does not reveal the benchmark's hidden preference.

> I therefore use “benchmark-imposed ceiling” rather than claiming a fixed model ceiling such as eighty percent.

## Slide 10 — Gold Is Not a Constant（1:50）

### 建议视觉

双向迁移图：

```text
Original gold wrong  ── 38 questions ──> Corrected gold correct
Original gold correct <── 39 questions ── Corrected gold wrong
Net change: −1
```

补充数字：

- Failure-selected audit: gold 61, model 30
- External corrected gold: 38 gained, 39 lost
- Configuration ranks can move by −11 to +9 places

### 讲稿示例

> A failure-only audit initially suggested that gold errors outnumbered model errors by about two to one. But this sample was selected from failures, so it could only observe one side of the migration. When I rescored the full dataset against an external corrected gold set, thirty-eight predictions became correct and thirty-nine became incorrect. The net change was minus one.

> Gold correction does not simply raise the score. It changes which systems win, which questions fail, and which mechanisms appear useful. The measured ceiling is jointly determined by the model, the reference conventions, and the evaluation procedure.

### 转场

> Once these measurement effects are separated, the remaining model failures also turn out not to be one homogeneous group.

---

# 5. Failure Analysis

## Slide 11 — Two Failure Regimes（1:40）

### 页面内容

| Failure regime | Reasoning volume | Behavior | Typical causes |
|---|---:|---|---|
| Convention mismatch | 0.80× correct cases | Short and confident | ties, projection, distinct, type |
| Semantic failure | About 2× correct cases | Long and uncertain | grain, filter, formula, wrong schema |

### 讲稿示例

> The common assumption is that wrong answers need more reasoning. This is true for semantic failures, but not for convention failures. Convention failures use less reasoning than correct answers. The model produces them quickly because it does not know that the evaluator expects a different representation.

## Slide 12 — What the Method Stack Fixes（1:30）

### 页面内容

沿方法层：

- Convention failures: 20 → 24 → 25 → 22
- Other failures: 132 → 95

沿 reasoning effort：

- Convention failures: 22 → 13 → 16 → 12
- Other failures: 116 → 52

### 讲稿示例

> The method stack and reasoning budget mainly remove semantic failures. The absolute number of convention failures remains nearly unchanged. This means the system helps the model understand the task, but does not reliably tell it which unstated benchmark convention to follow.

## Slide 13 — Timing of Intervention（1:40）

### 建议视觉

```text
Before commitment: evidence → execute → observe → revise    Effective
After commitment:  draft → verify/remind/retry              Usually ineffective
```

### 页面证据

- 143/157 = 91.1% failures already wrong in the first draft
- Failure cases rarely produce a correct intermediate row set
- Strict final verification, QueryPlan, literal warnings and post-answer checks show no stable gain

### 讲稿示例

> Evidence is most useful before the model commits to a solution. In 91.1 percent of the analyzed failures, the first draft was already wrong. Later verification usually has no correct candidate to select. This provides a common explanation for several negative experiments: they intervene after the semantic decision has already been made.

---

# 6. Negative Results: Recursion

## Slide 14 — Recursion Has No Stable Measurable Effect（1:30）

### 页面内容

全量：

- +0.10pp
- Below the 1.4pp conservative noise bound

仅看触发递归的题：

- Run 1: +2.7pp, n=74
- Run 2: −3.1pp, n=64

### 讲稿示例

> Because recursion is triggered only for a subset of questions, I report both the full-set effect and the conditional effect. The full-set increment is 0.10 points. On triggered questions, one run is positive and the other is negative. The problem is therefore not only dilution; the conditional effect itself changes sign.

## Slide 15 — Why Recursion Did Not Help（1:30）

### 页面内容

- Reasoning tokens: approximately 4346 vs 3259
- Recursion increases computation
- In 11 of 15 inspected failures, the leaf largely completed its local task
- The remaining error was often the root's global aggregation, filtering, or convention decision

### 讲稿示例

> Recursion does make the system think more. However, the leaf often retrieves the requested fact correctly. The root still has to decide how the local evidence maps to the final statistical grain or output convention. More local computation does not resolve that global decision.

> This result does not prove that recursion is universally ineffective. It means that under this dataset, trigger policy, model and depth-one implementation, no stable benefit is measurable.

---

# 7. Conclusion & Next Steps

## Slide 16 — Conclusions（1:10）

### 页面内容

1. Executable environment + pre-commitment self-improvement: **+13.85pp**
2. Offline schema organization: **+2.55pp**
3. Recursion: **+0.10pp, not measurable beyond noise**
4. Semantic and convention failures require different interventions
5. Gold and evaluation infrastructure materially change the conclusion

### 讲稿示例

> The main contribution is not simply a higher Text-to-SQL score. It is a decomposition of where inference-time system design helps and where it stops helping. Most of the gain comes from executable grounding before commitment. Schema organization provides a smaller but real gain. Recursion adds cost without a stable measured benefit. Finally, benchmark conventions and evaluation infrastructure must be treated as part of the empirical system.

## Slide 17 — Next Steps（1:20）

### 页面内容

**1. Stabilize measurement**

- Monitor Python-block, raw-SQL and one-turn response rates
- Use one declared denominator
- Record effective sampling parameters and infrastructure failures

**2. Build the Grammar Framework**

```text
Mine AST differences
        ↓
Validate rescue and damage on the full set
        ↓
Ship versioned, ablatable transforms
```

**3. Validate generalization**

- Second split or database collection
- Independent review of the failure taxonomy
- Matched-effort one-shot vs tool-loop experiment

### 讲稿示例

> The next step is to stabilize the measurement contract and then turn systematic output differences into executable grammar transformations. The first acceptance test is whether an automatic miner can rediscover the known `keep_ties` and `printf_to_round` transforms. Any candidate must be evaluated on the full dataset and must report both rescued and damaged questions.

### 最后一句

> Before adding deeper recursion or more verification prompts, we should first stabilize the ruler and convert repeatable differences into transformations that are executable, testable, and reversible.

---

# 建议的 Backup Slides

## Backup 1 — Baseline Provenance

- Legacy B1 stored strict score: 52.40%
- Official set-comparison rescore: 55.20%
- Corrected dev498 reruns: 70.68% / 70.48%
- 不把 55.20 → 70.47 写成方法收益，因为题面/evidence 版本不同

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

## Backup 6 — Gold Migration

- 38 predictions become correct
- 39 predictions become incorrect
- Net −1
- Ranking changes can be much larger than the aggregate change

## Backup 7 — Deterministic Rule Evaluation

| Rule | Rescue | Damage | Status |
|---|---:|---:|---|
| keep_ties | 7 / run | 2 / run | Offline evidence positive |
| printf_to_round | 2–3 / run | 0 | Offline evidence positive |

## Backup 8 — Limitations

- Sampling parameters were not fully fixed in historical runs
- Aggregate stability does not imply item-level stability
- core197 and Phase A are selected failure-heavy populations
- Failure taxonomy lacks independent second-person calibration
- Rule generalization has not been tested on a second split
- Recent online runs are affected by response-format drift

# 问答时的关键回答

## “Why not simply say recursion failed?”

> The measured increment is inside the noise band and the triggered-subset effect changes sign between runs. The evidence supports “no stable effect is measurable in this setting,” not a universal claim that recursion cannot work.

## “Is the +13.85pp caused by tools or by more reasoning?”

> The layer jointly introduces the executable environment and observation-driven revision, so the two cannot be fully separated. The reasoning-effort sweep suggests substitution between internal reasoning and external trial, but Baseline 1 does not record explicit reasoning effort. I therefore present this as a mechanistic clue rather than a complete causal decomposition.

## “Is post-processing cheating?”

> Any post-processing that changes predictions is part of the system under test and must be separately ablated. I distinguish shape normalization from semantic rewriting and report both rescue and damage on the full set.

## “Why does corrected gold not improve accuracy?”

> Gold corrections move decisions in both directions. Thirty-eight predictions become correct and thirty-nine become incorrect, so the net is minus one. The larger effect is on rankings and error composition, not necessarily on aggregate accuracy.

## “What is the strongest contribution?”

> The strongest result is the mechanism-level decomposition: most of the gain comes from executable grounding before commitment, while recursion and post-commitment verification show no stable marginal gain. The second contribution is showing that the evaluation instrument materially affects that conclusion.
