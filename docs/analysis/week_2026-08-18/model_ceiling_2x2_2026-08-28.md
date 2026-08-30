# 模型 × 推理强度 2×2：天花板不是模型能力（2026-08-28）

**结论先说：把生成模型从 `gpt-5.4-mini` 换成完整的 `gpt-5.4`，在 high 推理强度下
准确率变化 +0.61pp（McNemar p=0.68），落在 ±1.4pp 噪声带正中。
换一个大一档的模型，撞的是同一堵墙。**

因此"87~88% 之后上不去"**不是 model capability ceiling**。
剩下的嫌疑人只剩 benchmark / architecture / schema / reasoning strategy。

脚本：[`scripts/model_effort_crossing.py`](../../../scripts/model_effort_crossing.py)
（含 McNemar 精确检验），原始数字
[`analysisDetail/model_effort_crossing.json`](../analysisDetail/model_effort_crossing.json)。

---

## 一、设计

除被交叉的两个因子外全部钉死：profile `e3-c-conv-rules`、`max_iterations=8`、
`k=1`、修正数据集 `bird_dev_500_corrected_full.json`（498 题）、
**四臂同一天、同一时间窗内并行跑完**——最后这条是因为响应格式行为按天漂移
（见 [`reasoning_cost_2026-08-28.md`](reasoning_cost_2026-08-28.md) §四），
不同天跑会把漂移混进模型效应。

| | `reasoning_effort=low` | `reasoning_effort=high` |
|---|---|---|
| `azure/seminar-gpt-5.4-mini` | `modelcmp_mini_low_run1` | `modelcmp_mini_run1` |
| `azure/gpt-5.4` | `modelcmp_normal_low_run1` | `modelcmp_normal_run1` |

完整模型部署名是**裸 `gpt-5.4`**（`gpt-5.4-2026-03-05`）；
`seminar-gpt-5.4` 不存在。runner 已支持 `--model`，无需改代码。

---

## 二、四格结果（491 题共同可计分集）

| 格 | 准确率 | `llm_calls` | 推理量均值 | 推理量中位 | 总 token/题 | 延迟/题 |
|---|---:|---:|---:|---:|---:|---:|
| mini × low | 81.26% | 2.55 | 490 | 415 | 7137 | 7.2s |
| mini × high | 87.78% | 1.32 | 2618 | 1958 | 5993 | 17.4s |
| normal × low | 86.35% | 1.26 | 196 | 125 | 3468 | 6.0s |
| **normal × high** | **88.39%** | 1.54 | 1137 | 899 | 4936 | 28.9s |

全集 498 原始数字：mini×low 404/498 = 81.12%，normal×low 426/498 = 85.54%，
mini×high **435/498 = 87.35%**，normal×high **434/498 = 87.15%**
——**在未剔除崩溃题的原始口径上，小模型反而多对 1 道。**

### 配对检验

| 对照 | Δ准确率 | 只有 A 对 | 只有 B 对 | McNemar p |
|---|---:|---:|---:|---:|
| **模型效应 @ low**：mini → normal | **+5.09pp** | 15 | 40 | **0.0010** |
| **模型效应 @ high**：mini → normal | +0.61pp | 10 | 13 | **0.6776** |
| 推理强度 @ mini：low → high | **+6.52pp** | 8 | 40 | **<0.0001** |
| 推理强度 @ normal：low → high | +2.04pp | 9 | 19 | 0.0872 |

**交互项 −4.48pp。**

---

## 三、怎么读这张表

### 3.1 模型效应只在低推理强度下存在

大模型的优势 **+5.09pp（p=0.001）→ +0.61pp（p=0.68）**：
推理强度一给足就消失。等价的说法是——

> **`mini` + high effort ≈ `normal` + high effort。
> 小模型多想一会儿，就能到大模型的位置。**

两条臂从相反方向收敛到同一个 ~88%：mini 从 81.26% 涨 6.52pp 上来，
normal 从 86.35% 涨 2.04pp 上来。**同一个天花板，两个方向撞到。**
这正是"不是模型能力问题"最有力的形状——单看任何一条臂都得不出。

### 3.2 大模型不是在"更会做难题"

high 强度下按难度拆：

| 难度 | n | mini | normal |
|---|---:|---:|---:|
| simple | 148 | 91.89% | 92.57% |
| moderate | 246 | 86.99% | 88.21% |
| challenging | 97 | 83.51% | **82.47%（更低）** |

**最难的一档大模型反而略低。** 如果 87~88% 之后卡的是推理能力，
大模型的增益应该集中在 challenging——事实相反。

**high 强度下两个模型同时答错 47/491 = 9.6%。** 这 47 道是真正的硬核，
与本项目此前的根因审计对得上：其中很大一部分不是模型推理错误，
而是 gold 缺陷与标注约定不一致（见 [`rootcause/`](../rootcause/)）。

### 3.3 成本方向与直觉相反

**大模型更便宜。** normal×high 的推理量是 mini×high 的 **43%**（1137 vs 2618），
总 token 是 82%。mini 靠"想得久"补能力，normal 一次想清楚。
但 normal 延迟高 66%（28.9s vs 17.4s）——每 token 更慢。

按 [`reasoning_cost_2026-08-28.md`](reasoning_cost_2026-08-28.md) 的单价口径：
`normal` 的 low→high 花 941 推理 token 换 +2.04pp = **461 token/pp**，
`mini` 花 2128 换 +6.52pp = **326 token/pp**。**小模型的推理 token 单价更划算**，
虽然它需要买更多。

---

## 四、附带得到的第二个结论：工具循环在 high 强度下贡献为 0

今天四臂的工具循环全部是死的（模型不走 ```` ```python ````，
`db.execute` ≈ 0，详见 [`reasoning_cost_2026-08-28.md`](reasoning_cost_2026-08-28.md) §四）。
这**意外构成了一次工具循环的对照实验**：同 profile、同 effort、同数据集，
唯一差别是循环通不通。

| `e3-c-conv-rules` × high，496 题共同集 | 准确率 | `llm_calls` | 推理量 | 延迟 |
|---|---:|---:|---:|---:|
| 循环健康（08-17） | 87.70% | 2.27 | 3259 | 20.4s |
| 循环健康（08-18） | 87.70% | 2.27 | 3241 | 20.4s |
| **循环已死（08-28）** | **87.30%** | **1.33** | **2700** | **18.0s** |

配对 McNemar：对 run1 **p=0.8555**（16/14 不一致），对 run2 **p=0.8601**（17/15）。

> **在 high 推理强度下、prompt 里已有离线 schema 的前提下，
> ReAct 工具循环带来 +0.40pp（读不出），却多花 41% 的 LLM 调用和 21% 的推理 token。**

这把项目此前的"替代关系假说"从三条独立估计的收敛，
升级为一次同配置的逐题配对检验。

**两条必须附带的限制**：

1. 循环是因**模型侧行为漂移**而死的，不是随机开关。今天模型的其它行为
   原则上也可能有别，因此这是**自然实验**，不是随机化消融。
   要做实的，需要一个显式关掉工具的 profile。
2. 这**不否定第 1 层的 +13.95pp**。那一层是对 B1 测的，B1 用的是另一个 runner、
   `runtime-full` schema。本节只说明：**在 L3 这套配置里，循环已经不再是收益来源。**

---

## 五、对上层问题的回答

> 问题到底来自 model capability ceiling，还是 agent architecture？

| 嫌疑人 | 证据 | 判定 |
|---|---|---|
| **Model capability** | 换大一档模型 +0.61pp，p=0.68；challenging 档反而更低 | ❌ **排除** |
| **Agent architecture（工具循环）** | 循环死活 +0.40pp，p=0.86 | ❌ **在 L3 配置下排除** |
| **Schema** | 全链唯一超噪声的一层（+2.55pp，164 token/pp） | ⚠️ **有效但已用尽**——需要新的 schema 表示才有增量 |
| **Reasoning strategy** | 强度扫描收益递减，medium→high 单价 1,945 token/pp | ⚠️ **接近饱和** |
| **Benchmark / 标注约定** | 两模型同时错的 47 道；F-Audit 实测 40% 的"失败"是 gold 缺陷；约定类失败对推理量和方法层级双重免疫 | ✅ **最大的剩余嫌疑人** |

**四条里已经排除两条，且剩下的两条机制性嫌疑人（schema、reasoning strategy）
都表现出饱和特征。证据集中指向 benchmark 与标注约定。**

---

## 六、下一步（按信息量排序）

1. **把工具循环修好再复跑这个 2×2。** 当前四格都是单次生成器。
   如果修好后 mini×high 仍 ≈ normal×high，结论从"单次生成层面"升级到"agent 层面"，
   这是论文里最需要的那一句。
2. **显式的 `no-tools` profile。** 把 §四 的自然实验做成随机化消融，
   一次运行即可，成本极低。
3. **逐题读那 47 道两模型同时错的题。** 这是"benchmark vs 方法"最干净的样本，
   且规模可人工穷尽。
4. 四格各补一次重复。当前每格 1 次；`model effect @ high` 的 p=0.68
   本身就是"测不到"，补重复主要是为了给 low 档那个 +5.09pp 上保险。
