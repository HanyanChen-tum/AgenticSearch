# Hint 消融实验：BIRD 的 evidence 字段是不是失败原因之一（2026-08-08）

## 动机

`stable_failure_audit_2026-08-08.md` 发现一类失败：**模型忠实执行了 Hint 给出的公式，而 gold 违背了自己的 Hint**（`bird_219`、`bird_118`）。这与 `../findings.md` 记载的 legacy 时代结论相冲突——那里把 "BIRD hint injected as ground truth" 记为 large positive，但**该结论从未在 clean harness 上做过消融**。

本实验做因果检验：**只删除 Hint，其余全部不变。**

## 候选检测

机械扫描 197 题：Hint 中出现显式公式（`= DIVIDE(...)`、`refers to SUM(...)` 等），但 gold SQL 未使用该公式所声明的聚合函数。命中 **29 题**。

其中多数是良性的——Hint 写 `MAX(x)` 而 gold 用 `ORDER BY x DESC LIMIT 1`，语义等价。真正的结构性矛盾集中在 **Hint 声明 `SUM(...)` 而 gold 使用 `COUNT`/`AVG`** 这一簇。

## 三臂设计

配置完全相同（`e3-c`、`k=1`、`max_iterations=8`、`temperature=0`（**注：该参数被静默丢弃，实际以 API 默认采样运行**，见 SYNTHESIS §4.5）、`reasoning_effort=high`），唯一差别是被测题目的 `evidence` 字段是否置空。

| 集合 | 构成 | 目的 |
|---|---|---|
| **A** | Hint 公式与 gold 矛盾、**当前失败** 5 题（`bird_198/218/219/228/604`） | 检验 Hint 是否为致败原因 |
| **B** | 同一签名但**当前正确** 5 题（`bird_282/775/1076/1471/208`） | 同类内的附带损害对照 |
| **C** | Hint 提供**值编码**（非公式）、当前正确 5 题（`bird_1344/1350/1238/1103/1113`） | 检验 Hint 是否为必需信息 |

## 结果

| 集合 | 有 Hint | 无 Hint | 变化 |
|---|---:|---:|---:|
| A　Hint 公式与 gold 矛盾、原本失败 | 0/5 | **3/5** | **+3** |
| B　同签名但原本正确 | 5/5 | 5/5 | 0 |
| C　值编码型 Hint、原本正确 | 5/5 | 5/5 | 0 |
| **合计** | **10/15** | **13/15** | **+3** |

**删除 Hint 修好 3 题，且未破坏任何一题。**

## 机制确认

三条转正题的 SQL 变化直接印证了因果链：

### `bird_604`

> 问："创建超过 10 篇帖子的用户，其 up votes 平均值与年龄平均值是多少？"
> Hint：`average of the up votes = Divide (Sum(UpVotes), Count (UserId))`

| | SQL |
|---|---|
| 有 Hint（错） | `SUM(T1.UpVotes)/COUNT(T1.Id)` ← **严格照 Hint 实现** |
| gold | `AVG(T1.UpVotes)` |
| 无 Hint（对） | `AVG(T1.UpVotes)` ← **与 gold 一致** |

`SUM/COUNT` 与 `AVG` 在存在 NULL 时结果不同。**Hint 给的公式本身有细微错误，模型照做就错。**

### `bird_219`

> 问："三键类型中致癌分子的百分比是多少？"
> Hint：`percentage = DIVIDE(SUM(bond_type = '#') * 100, COUNT(bond_id)) where label = '+'`

| | 结果 |
|---|---|
| 有 Hint（错） | 严格实现该公式 → `0.08` |
| gold | `COUNT(DISTINCT 致癌分子)/COUNT(DISTINCT 分子)` → `66.67` |
| 无 Hint（对） | 按题意自行推理"有三键的分子中致癌的占比" → 与 gold 一致 |

**Hint 的公式计算的根本是另一个量。** 去掉之后，模型自行理解题意反而算对。

### `bird_228`

Hint 给的公式使模型采用 `printf('%.4f', ...)`（返回字符串）；去掉 Hint 后模型改用 `ROUND(..., 4)`（返回数值），与 gold 的类型一致。

## 结论

1. **BIRD 的 Hint 不是一致有益的。** 在"Hint 公式与 gold 矛盾"这一可机械识别的子集上，Hint 是**致败原因**：模型因忠实执行给定指令而被判错，删除该指令即修复 3/5。

2. **在本实验的样本中，Hint 也不是必需的。** 集合 C 显示，即便删除提供值编码的 Hint（如 `source = 'Fundraising'`），5/5 仍全部正确。可能的解释是 **E3-C 的 Offline Schema artifact 已经携带 `value_description`**（来自 BIRD 官方 `database_description/*.csv`），使 Hint 的内容变得冗余。

3. **这与 legacy 时代的结论并不矛盾，但适用条件已改变。** `../findings.md` 记录 Hint 为 large positive，那是在**没有 Offline Schema Context** 的 harness 上测的。E3-C 引入 schema artifact 之后，Hint 的边际价值很可能已被吸收。

4. **本实验是本项目第二个干预性证据**（第一个是 `disambiguation_experiment_2026-08-08.md`），共同支撑 `../SYNTHESIS.md` 结论三：这些失败源于**题面/标注侧的信息问题**，而非模型能力不足。

## 边界与限制

- **样本经过定向选择，不是随机抽样**：集合 A 按"公式矛盾且失败"选出，B/C 按"当前正确"选出。因此 `10/15 → 13/15` **不能外推为全集的准确率提升**。
- **n=5 每组**，个位数样本，只能作为方向性证据。
- 集合 C 只覆盖"值编码"一种 Hint 类型，不能推广到全部 Hint（例如 `bird_1482` 那类给出多步计算口径的 Hint 未被测试）。
- 未区分"Hint 冗余"与"Hint 有害"对总分的净效应。

## 建议的后续实验

**在完整 197 题上做一次 Hint 消融**（`e3-c` 有/无 Hint 两臂）。这是当前唯一一个**同时具备**以下性质的候选实验：

- 有干预性预实验支持（本文档）
- 单变量、可归因、无需新机制代码
- 可能同时得到正向结果（若 Hint 净有害）或有价值的负向结果（若 Hint 在全集上仍是净正，则说明本次的定向样本不可外推）
- 成本为一次完整运行

若结果为"Hint 净有害或中性"，则这是一个**真正可报告的准确率改进**（与标注对齐机制不同，删除 Hint 不涉及复现 gold 缺陷，反而是移除一个误导源），且对所有使用 BIRD evidence 字段的工作都有意义。
