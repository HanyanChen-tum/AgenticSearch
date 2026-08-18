# harness 改写规则的处置：改形状可以，改语义不行（2026-08-16）

> ## ⚠️ 本文 §3.6 及一切基于「外部修正版 gold」的数字暂停使用（2026-08-17）
>
> 用作外部参照的 `arcwise_plat_sql_only_with_diff.json` **并非只改 SQL**：
> 对照 BIRD 源文件 `mini_dev_sqlite.json`，它改写了 **81 道题面、68 条 evidence**，
> 其中包含实质性改动——`bird_1500` 的 September 2013 → August 2012、
> `bird_1501` 的 June 2013 → August 2012、`bird_1529` 的 January 2012 → August 2012。
> **换了日期就是另一道题。**（本项目的 `bird_dev_500.json` 与 BIRD 源逐字一致，0 处差异。）
>
> 我此前拿模型对**原题面**的回答，去比对**改写后题面**的 gold，至少 81 题属错配。因此作废：
>
> - 修正版 gold 上的 **67.07%**、**+20/+18**、**70.68%**
> - 「我判 gold 的 84% 被对方独立修正」这一佐证梯度（84%/25%/12%）
> - 「标注噪声在两个方向上对消」这一结论
> - core197 标签翻转 **20.3%**
>
> 正在于「题面与 evidence 均未改动」的子集上重算。**在重算结果落盘前，上述数字不得引用。**
> 未受影响：163 道责任判读本身（那是逐题读题面+SQL+执行结果做的，不依赖 Arcwise）。


## 一、结论

`ours/agent/sql_conventions.py` 的三条改写规则，用**外部独立修正版 gold**
（VLDB 2026 `Arcwise-Plat-SQL`，[arXiv:2601.08778](https://arxiv.org/html/2601.08778v1)，
覆盖同一批 BIRD Mini-Dev；该集去重后为 **498 道**）逐条重测：

| 规则 | train 支持度 | 命中 | 开着判对 | 关掉判对 | 净 | 处置 |
|---|---:|---:|---:|---:|---:|---|
| `count_no_distinct` | 0.891 | 29 | 9 | 25 | **−16** | **关闭** |
| `no_select_concat` | 0.9999 | 9 | 8 | 0 | **+8** | 保留 |
| `superlative_order_limit` | 0.9034 | 2 | 0 | 2 | **−2** | **关闭** |
| 合计 | | 40 | 17 | 27 | **−10** | |

**关掉两条、保留一条 = +18 题。** 全部删掉只有 +10——会连 `no_select_concat` 的 8 题一起丢，
所以不能一删了之。

端到端离线复核（用模型改写前 SQL 重新过新配置，逐题执行）：

| 评分基准 | 旧配置 | 新配置 | 变化 |
|---|---:|---:|---:|
| **修正版 gold** | 334（67.07%） | **354（71.08%）** | +20 |
| 原始 BIRD gold | 335（67.27%） | 333（66.87%） | −2 |

**可归因于本次改动的是 +18，不是 +20。** 逐题分解：在被旧配置改写过的 40 道上
**净赚 18、赔 0**（`bird_92` `bird_672` `bird_701` `bird_963` `bird_1084` `bird_1136`
`bird_1229` `bird_1231` `bird_1247` `bird_1252` `bird_1254` `bird_1256` `bird_1257`
`bird_1265` `bird_1267` `bird_1302` `bird_1505` `bird_1525`）。

多出的 2 道是**重放假象**：端到端脚本用重新执行的结果对比原运行记录的
`predicted_answer`，而原运行有几道模型 SQL 在 30 秒处超时、记为无结果，
重放时用的是按操作数计的预算而非墙钟超时，于是"复活"了。**与本次改动无关。**

守卫修复（§5）对 `bird_1011` 的收益是 **0**——拆分虽已避免、不再报
`no such column`，但该题模型 SQL 本身对修正版 gold 仍不成立。
修守卫的价值是消除一类硬报错，不是这次的分数。

### 独立复现（iter15）

同一改动在**另一批模型 SQL** 上重放。`iter15` 是同模型、同 profile、同温度、
`max_iterations` 8→15 的另一次运行，已完成 444 题：

| | 题数 | 原始 gold | **修正版 gold** |
|---|---:|---:|---:|
| run1 | 498 | 335 → 333（−2） | 334 → 352（**+18**） |
| iter15 | 444 | 309 → 306（−3） | 305 → 323（**+18**） |

**两批完全不同的 SQL，修正版 gold 上都是正好 +18。** 改动不是对 run1 的过拟合。

准确率：修正版 gold 上 run1 **70.68%**、iter15 **72.75%**；原始 gold 上分别为
66.87%、68.92%。**同一份预测，两版 gold 差 3.8~3.9pp——"到没到 70%"是基准问题，不是模型问题。**

两点保留：
- iter15 的 72.75% **不可直接与 run1 的 70.68% 比**——它中途停止，那 444 题是数据集顺序的前
  444，不是随机子集，库构成可能有偏。但 **+18 是同批题内部的前后对比**，作为效果复现有效。
- 两次同一模型、温度 0，复现的是**改动**的稳健性，不是模型的稳健性。

**原始 gold 上恰好 −2，与历史记录"去 DISTINCT 规则改动 −2"完全吻合。**
当年那次测量是准的——它准确地测出了**一个错误目标上的损失**。同一个改动，
在坏 gold 上 −2，在好 gold 上 +20。这就是为什么评测基准的正确性先于任何调优。

## 二、判据：改形状 vs 改语义

| 规则 | 改的是什么 | 是否合法 |
|---|---|---|
| `no_select_concat` | **输出形状**——`a \|\| ' ' \|\| b` 拆成两列，返回的数据一个字节没变 | 合法 |
| `count_no_distinct` | **计算语义**——COUNT 的对象从实体变成行 | 不合法 |
| `superlative_order_limit` | **计算语义**，且会丢掉 WHERE 条件 | 不合法 |

**harness 后处理可以规整输出格式，不可以改变查询算的是什么。**

这条判据不需要做实验就能预判上表的结果，而且它解释了为什么"用 gold 支持度做门槛"会失灵：
**支持度只能说明标注者多常这样写，不能说明这样写是对的。**

## 三、`count_no_distinct` 是怎么烂掉的

它在 train gold 上有 2377 个适用样本、69 个库、**0.891 支持度**，看起来无可辩驳。

但修正版 gold 把 DISTINCT 的使用从 **83 题提高到 130 题（+57%）**。
那 0.891 度量的不是 SQL 语义，是 **BIRD 标注者系统性漏写 DISTINCT 的习惯**——
规则把标注缺陷编码进了系统。

最干净的例子是 `bird_1505`（题面 "how many **customers**"）：

```sql
-- 模型写的（对，正是修正版 gold 要求的）
SELECT COUNT(DISTINCT T1.CustomerID) FROM customers T1 JOIN yearmonth T2 ON …
-- harness 改成（错）
SELECT COUNT(T1.CustomerID)          FROM customers T1 JOIN yearmonth T2 ON …
-- 原始 gold（也错，同一个错）
SELECT COUNT(*)                      FROM yearmonth T1 JOIN customers T2 ON …
```

**规则的错和 gold 的错互相抵消，于是在原始 gold 上判"对"。** gold 一修好，抵消消失。

这解释了先前对不上的三件事：

1. 为什么这条规则在原始 gold 上测出来是净正的——它在拟合 gold 的缺陷
2. 为什么它自己造成了 5 道失败（`bird_1257` 等题面明写 "how many patients"）
3. 为什么用修正版 gold 评分时，新增失败集中在实体计数题
   （39 道新增失败里 17 道是修正版补了 DISTINCT 的题，全集基准率只有 11%，富集 4 倍）

被它害掉的 16 道：`bird_92` `bird_672` `bird_963` `bird_1084` `bird_1229` `bird_1231`
`bird_1247` `bird_1252` `bird_1254` `bird_1256` `bird_1257` `bird_1265` `bird_1267`
`bird_1302` `bird_1505` `bird_1525`。**它一道都没帮到。**

## 四、`no_select_concat` 为什么留

净 +8，而且**关掉是 0 分**——那 9 道里 8 道全靠它。

它的 0.9999 支持度**经受住了修正**：修正版 gold 由另一团队重写，依然全部用分列。

| 题 | 修正版 gold | 模型原写 |
|---|---|---|
| `bird_1460` | `SELECT first_name, last_name, cost` | `first_name \|\| ' ' \|\| last_name` |
| `bird_865` | `SELECT forename, surname` | `forename \|\| ' ' \|\| surname` |
| `bird_897` | `SELECT forename, surname, nationality, MAX(points)` | 同上拼接 |

**但要记住它的 +8 本质上是评测器的产物**，不是 SQL 对错——拼接与分列返回的信息完全相同，
是评测器按列匹配才判错。更本质的修法是**在评测器里归一化拼接**，而不是改模型写的 SQL。
那样 harness 可以真的清零。现在不动，因为那会改变评分口径、与公开 BIRD 结果不可比。

## 五、`no_select_concat` 的守卫洞（已修）

`_alias_is_referenced` 原本只检查**同一层 select** 的 ORDER BY / GROUP BY / HAVING，
不检查**外层查询对子查询别名的引用**。于是 `bird_1011`：

```sql
SELECT full_name FROM (SELECT d.forename || ' ' || d.surname AS full_name, …) AS t
```

子查询里的拼接被拆成两列，外层 `SELECT full_name` 随即失效，报 `no such column: full_name`。
**该题名字就写在这个守卫的 docstring 里**（"Observed on bird_1011"），守卫却没覆盖住它。

已扩展为：给定根节点时，该别名若在本 select 自身投影之外的任何位置作为列名出现（限定与否都算），
即拒绝拆分。**宁可少改一次，不可改出硬报错。**

## 六、落地改动

| 文件 | 改动 |
|---|---|
| `scripts/build_sql_conventions.py` | 新增 `SEMANTICS_CHANGING` 集合，无论支持度多高一律不启用；`gate.passed` 与 `enabled` 拆开记录，并写入 `disabled_reason` |
| `data/processed/sql_conventions_v1.json` | 两条 `enabled: false`，附 `disabled_reason` |
| `ours/agent/sql_conventions.py` | `_alias_is_referenced` 增加外层引用检查 |

把判据写进 `build_sql_conventions.py` 而不只是改产物，是因为该脚本按支持度重算 `enabled`，
**重跑一次就会把这两条重新打开**。

## 七、注意事项

- **+18 是在修正版 gold 上测的（+20 里有 2 道是重放假象）。** 在原始 BIRD gold 上这个改动是 −2——
  因为原始 gold 和被关掉的规则犯同一个错。**这不是改动有问题，是原始 gold 不该作为优化目标。**
- 先前记录的"去 DISTINCT 规则现状已最优、改动 −2"**不作废，但要重新理解**：
  那个 −2 测得准确，只是测在错误的目标上。
- **基数是 498 不是 500**：`bird_137`、`bird_138` 在数据集里各重复一次且均答对，
  按 500 计会把准确率抬高 0.13pp。历史上的 337/500 = 67.40% 应为 335/498 = 67.27%。
- `no_select_concat` 的 +8 只在 9 道题上测得，样本小。改写本身是确定性的，
  对本次运行的测量是精确的，但不保证推广到别的运行所产生的 SQL 分布。

## 涉及文件

- 复现：`scripts/verify_gold_fix.py`、`scripts/apply_sql_conventions.py`
- 数据：`docs/analysis/analysisDetail/rescore_vs_arcwise.json`
- 背景：`docs/analysis/failure_adjudication_final_2026-08-16.md` §3.6、§5
