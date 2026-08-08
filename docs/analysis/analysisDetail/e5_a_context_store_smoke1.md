# E5-A：同信息外部化 smoke 结果（2026-08-08）

## 机制与边界

E5-A 把原本拼进 Prompt 的知识 section（`hint`、`few_shot`、`offline_metadata`）改为放进只读 context store，模型用 `ctx.list()` / `ctx.read("section")` 按需读取。**只改访问方式，不改信息内容**；不提供 search / slice / compose（那是 E5-B 的变量）。

- 实现：`ours/agent/context_store.py`（`ContextStore` + `GatedContextStore`）、`ours/agent/prompts.py` 的 `basic-context-store`、profile `e5-a`
- 父配置：**E3-C**（已验证的结构化配置），与 E3-C 的唯一差异是 `context_mode` 与相应的 protocol prompt；**不涉及已被拒绝的 QueryPlan**
- `GatedContextStore` 只暴露 `list`/`read`，把 `content`/`manifest`/`read_log` 等验证接口挡在模型之外——否则模型可绕过读取日志直接取内容，"模型到底读了哪些 section"的测量就失效了
- 测试：`tests/test_e5_a_context_store.py`，12 项；含一项防回归测试锁定直接 Prompt 路径的 section 顺序（实现过程中曾误改该顺序，会改变所有历史 profile 的 prompt 哈希）。仓库全量 107 项测试通过。

> 关于此前的暂停理由：E5-A 原状态为"暂停：上游 E4-A 未通过，不把失败的 QueryPlan 带入 context store"。复核确认该理由不适用于 E5-A 本身——E5-A 的内容是信息外部化与等价性验证，不需要 QueryPlan 参与，父配置可直接用已验证的 E3-C。

## 通过条件一：信息等价性（正式条件，已通过）

计划 §9.1 的通过条件是"信息集合和哈希一致、可访问、无隐藏能力"。用 `scripts/verify_e5_a_information_equivalence.py` 在**全部 197 题**上离线逐字节比对（无 LLM 调用）：

```
questions             : 197
information-equivalent: 197
failures              : 0
section presence      : {'hint': 197, 'few_shot': 197, 'offline_metadata': 197}
PASSED                : True
```

三个 section 在 197 题上全部逐字节一致，无缺失、无多余、无内容差异。逐题 SHA-256 记录于 `e5_a_information_equivalence.json`。

## 通过条件二：可达性与实际读取行为（smoke，已通过）

11 题覆盖全部 11 个数据库（`data/processed/e5_a_smoke_ids.json`），运行 `e5_a_smoke1`。

**模型确实主动读取 context store**：

| 指标 | 数值 |
|---|---:|
| `context.read` 事件总数 | 59 |
| 平均读取次数/题 | 5.36 |
| 读取次数为 0 的题 | **0 / 11** |
| `context.list` 事件总数 | 55 |

逐题读取序列（节选）：

| 题目 | 读取次数 | 读取顺序 |
|---|---:|---|
| `bird_197` | 11 | hint ×3, few_shot, offline_metadata, few_shot, offline_metadata, few_shot, offline_metadata ×2 |
| `bird_728` | 8 | hint ×2, few_shot, offline_metadata, hint, few_shot, offline_metadata, hint |
| `bird_1471` | 7 | hint ×2, offline_metadata ×3, few_shot, offline_metadata |
| `bird_92` | **1** | hint（**只读了 hint，从未读 schema**） |

11/11 的题都先读 `hint`。能力边界方面，事件日志中只出现 `context.list`、`context.read`、`db.execute`，无越权调用。

**这否定了一个此前基于 ReAct 循环测量做出的预测**：`react_loop_efficacy_2026-08-08.md` 显示模型平均只用 1–2 轮执行、2/3 的正确答案未经 FINAL 验证，据此我曾预期"模型很可能懒得去读 store"。实测相反——模型对**读取上下文**相当积极（5.36 次/题），远高于它对**验证 SQL** 的积极性。

## 一个值得注意的不对称

同样 11 题，E5-A 与 E3-C 的工具使用对比：

| 配置 | `db.execute`/题 | `db.sample_values`/题 | `context.read`/题 |
|---|---:|---:|---:|
| E5-A（store） | 1.64 | **0.00** | 5.36 |
| E3-C（direct） | 1.36 | 0.27 | 0.00 |

模型愿意为"获取信息"调用 5.36 次工具，却只愿意为"验证 SQL"调用 1.6 次；且在 store 模式下 `sample_values`（值 grounding）降到了 0。这与 SQRL 的论点一致：**inspection/verification 的决策能力是训练习得的，而不是工具可达性问题**——工具一直都在，模型只是不用它来验证。

## 准确率（仅供参考，非通过条件）

计划明确规定 E5-A"不用于宣称准确率提升"。同 11 题配对：

| 配置 | 正确数 |
|---|---:|
| E3-C（基线） | 5/11 |
| E5-A | 5/11（恢复 `bird_17`，回退 `bird_92`） |

`bird_92` 的回退有明确解释：它是唯一只读了 `hint`、从未读取 `offline_metadata` 的题——模型在缺少 schema 信息的情况下作答。这是外部化引入的**真实新失败模式**（信息可达但模型未取用），值得记录为 E5-B 设计时必须处理的风险，但 N=11 不足以量化其频率。

## 成本：外部化是净负担（对 E5-B 有决定性影响）

同 11 题配对成本对比：

| 指标 | E3-C（直接） | E5-A（store） | 变化 |
|---|---:|---:|---:|
| prompt tokens | 5,171 | 4,265 | −17.5% |
| completion tokens | 4,115 | 15,138 | **+267.9%** |
| reasoning tokens | 3,740 | 14,341 | **+283.4%** |
| **total tokens** | 9,286 | 19,403 | **+108.9%** |
| LLM 调用 | 2.3 | 4.5 | +100.0% |
| 延迟 | 20.6 s | 85.0 s | **+312.3%** |

Prompt token 如预期下降（信息移出），但**推理 token 增长近三倍**：模型需要额外轮次去读取，每次读取都是一轮完整响应且携带完整隐藏推理；smoke 中还观察到大量重复读取（`bird_197` 读 11 次、`bird_1471` 把 `offline_metadata` 读 4 次），每次都把整段内容重新灌回对话。净效果是 **2 倍 token、4 倍延迟，准确率持平**。

### 为什么：这个任务没有 context store 要解决的那个问题

| 量 | 数值 |
|---|---:|
| 完整知识载荷（11 题，min/中位/max） | 726 / 1,410 / 2,572 tokens |
| E3-C 实测 prompt tokens/题 | 5,171 |
| 现代上下文窗口 | 128,000+ |
| **上下文利用率** | **约 4%** |

RLM 的 context store 针对的是"上下文装不下、必须外部化按需取用"的场景。本任务在 **4% 的上下文利用率**下运行，不存在该约束，因此外部化没有可兑现的收益，只留下多轮读取的开销。这解释了上表的成本结构，也是一个**关于机制适用边界的结论，而非工程实现问题**——把 store 做得更快也无法产生本来就不存在的收益。

## 结论

**E5-A 通过。** 两个通过条件均满足：信息等价性 197/197 逐字节一致；可达性经 11 题验证，模型主动读取且无越权。机制本身按设计工作。

## 对 E5-B 的评估：两条接受轴的先验都很差

计划 §9.2 给 E5-B 的接受条件是"(1) 不明显低于对应的直接 Prompt 结构化配置；(2) 目标错误或 token 至少一项明确改善"。逐条看当前证据：

**轴一（目标错误）先验差。** `schema_join_diagnosis_2026-08-07.md` 与 `e3_c_schema_v4_summary.md` 已确认：E3-C 残留失败中 **89–93% 的 gold 表/字段本来就已完整出现在交付的上下文里**——瓶颈不是"找不到信息"，是"拿到了正确信息仍然推理错误"。E5-B 提供的是更强的**查找**能力，而查找不是瓶颈。

**轴二（token）先验差。** E5-A 在只做 read 的情况下已经是 **+109% token / +312% 延迟**。E5-B 在此之上增加 search/slice/compose，意味着**更多**工具调用轮次。即便 slice 相对 E5-A 的整段 read 能省一些，要回到 E3-C 的水平需要削减一半以上成本，与"增加调用轮次"的方向相反。

**根本原因（§成本）**：本任务上下文利用率约 4%，context store 要解决的约束在此不存在。这不是 E5-B 的实现问题，改进实现无法创造本来不存在的收益。

**三条具体输入**（若日后在上下文确实紧张的场景重启该方向）：

1. **可达性不是瓶颈**——模型愿意读（5.36 次/题，0 题未读），不需要额外设计激励读取的机制。
2. **"读了但读得不全"是新增风险**：`bird_92` 只读 hint 就作答并因此回退。E5-B 引入更细的片段后漏读风险只会更高，需在设计中显式区分"检索未命中"与"检索命中但未读取"。
3. **不要期待 E5-B 修复验证行为**：store 模式下 `sample_values` 降至 0，改变信息访问方式不改善验证行为——与本项目主论点（`../SYNTHESIS.md`）一致。E5-B 至多只能声称上下文利用效率，不应声称修复 verification。

**建议**：不把 E5-B 作为准确率实验运行。N=11 的样本量不足以精确量化成本倍数，但 2 倍 token / 4 倍延迟属于大效应而非边缘差异，且 4% 上下文利用率这一结构性事实与样本量无关。
