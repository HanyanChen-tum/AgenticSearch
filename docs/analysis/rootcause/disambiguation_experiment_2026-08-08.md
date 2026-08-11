# 反事实消歧实验：指代歧义是不是真正的失败原因（2026-08-08）

## 设计

`stable_failure_audit_2026-08-08.md` 把 77 条稳定失败拆成六类，其中**指代歧义**（问题中的名词在 schema 中对应多个候选，题面未消歧）约占 13%。本实验做因果检验：**只消除指代歧义，其余一切不变，看失败是否消失。**

**候选筛选**：先用机械检测器扫描全部 77 条（gold 与预测使用了不同的表/输出列，且该列名在多张表中存在），得 25 个候选；再逐题人工筛去 CTE 命名差异、gold 缺陷、输出约定等非指代问题，保留 **7 条**干净的指代歧义。

**改写规则**（每条都遵守）：
- 只澄清那个歧义名词**在现实世界中指什么**
- **不出现任何表名或列名**
- **不透露该返回哪些列，也不透露任何聚合/过滤结构**
- Hint 原样保留，不改

例：

| 题号 | 原问题（歧义处） | 改写后 |
|---|---|---|
| `bird_902` | "when he was in **track number** less than 20" | "when his **position in the driver standings** was less than 20" |
| `bird_584` | "all the **comments** left by users who edited the post" | "all the **revision-history comments** recorded when users edited the post" |
| `bird_1166` | "Identify **their diagnosis**" | "Identify **that patient's own overall diagnosis, rather than the diagnosis noted for that particular examination**" |
| `bird_1529` | "the **amount spent** by customer" | "the total **money** spent by customer" |

**两臂对照**，配置完全相同（`e3-c`、`k=1`、`max_iterations=8`、`temperature=0`（**注：该参数被静默丢弃，实际以 API 默认采样运行**，见 SYNTHESIS §4.5）、`reasoning_effort=high`），唯一差别是数据集中这 7 条的 question 字段：

- 对照臂：原问题 → `results/rootcause_ambiguity_control.json`
- 处理臂：消歧问题 → `results/rootcause_ambiguity_disambiguated.json`

## 结果

| 指标 | 对照臂 | 处理臂 |
|---|---:|---:|
| 整题正确 | **0 / 7** | **2 / 7** |
| **命中预期指代对象** | **1 / 7** | **6 / 7** |

按题拆开（"命中指代"= 预测 SQL 使用了该题歧义所指向的那个表/列）：

| 题号 | 歧义所指 | 对照臂命中 | 处理臂命中 | 整题正确 |
|---|---|---|---|---|
| `bird_902` | `driverStandings` | ✗ | ✓ | **✓** |
| `bird_906` | `driverStandings` | ✗ | ✓ | **✓** |
| `bird_1166` | `Patient.Diagnosis` | ✗ | ✓ | ✗ |
| `bird_465` | `set_translations` | ✗ | ✓ | ✗ |
| `bird_584` | `postHistory.Comment` | ✗ | ✓ | ✗ |
| `bird_145` | `trans.account_id` | ✓ | ✓ | ✗ |
| `bird_1529` | `Price`（金额） | ✗ | ✗ | ✗ |

## 解读：消歧起作用了，但被第二层问题挡住

**指代歧义确实是因果原因**：7 条里 5 条经消歧后模型改用了正确的表/列（`bird_145` 本来就命中，`bird_1529` 未被纠正）。这不是巧合——改写只碰了那一个名词。

**但只有 2 条整题转正**，因为其余 4 条在指代被纠正后，**撞上了此前已记录的其它类别的问题**：

| 题号 | 指代已纠正，但仍失败于 |
|---|---|
| `bird_145` | gold 返回**重复行**（`14` 出现 6 次），模型用了 `DISTINCT` —— 即已记录的 DISTINCT 标注约定问题 |
| `bird_465` | 题目是是非题，gold 返回 `'YES'`，模型返回翻译文本本身 —— 输出约定 |
| `bird_584` | gold 的结果包含**空字符串行** `['']`，模型的结果不含 —— 空值处理约定 |
| `bird_1166` | 指代改对后模型改用 `Birthday = (SELECT MAX(...))` 的等值写法，结果为空 —— 新引入的查询结构错误 |

`bird_1529` 是唯一消歧无效的：把"amount spent"改成"total money spent"之后，模型仍然算 `Amount × Price`，没有意识到该 schema 里 `Price` 本身就是金额。

## 结论

1. **指代歧义是真实的因果原因，可被消除。** 5/7 的指代错误只靠改写一个名词就纠正了，模型并非"能力不足以选对表"，而是**题面没有提供选择所需的信息**。

2. **但单独消除它只能救回 2/7**，因为这些题目往往**同时**踩中多个数据集侧问题（DISTINCT 约定、输出约定、空值约定）。这与 `stable_failure_audit_2026-08-08.md` 的分布一致：那些类别不是互斥的，一道题可以同时属于多类。

3. **这为结论三提供了因果层面的证据**：此前"40% 是 gold 缺陷""+2.03 pp 靠标注对齐""稳定失败中仅 10% 是推理错误"都是**观测性**证据；本实验是**干预性**证据——改变题面的一个歧义词，模型行为随之改变，证明失败源于题面信息不足而非模型能力。

## 边界与限制

- **样本极小（n=7）**，只覆盖指代歧义这一个子类（占稳定失败约 13%），不能外推到其它类别。
- **改写是在已知 gold 的情况下写的**，因此测得的是**上界**："若有一个先知消除了指代歧义，模型能否做对"。**这是诊断工具，不是机制**——它不能、也不应被报告为准确率提升手段，理由与 F-Audit 使用 gold 做运行后归因相同。
- 表级检测会低估指代纠正率（部分歧义发生在列级），因此本文按每题预期的具体表/列做匹配，而非表集合比对。
- 未做 Hint 消融对照。`bird_1529` 的失败提示 Hint 与 schema 命名的交互可能是另一个独立因素，值得单独设计。
