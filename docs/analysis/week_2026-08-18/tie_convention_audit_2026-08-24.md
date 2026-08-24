# 并列约定审计：`ties` 那一类不该修，BIRD 自己就不一致（2026-08-24）

脚本 [`scripts/audit_tie_convention.py`](../../../scripts/audit_tie_convention.py)，
结果 `analysisDetail/tie_convention_audit.json`。

## 起因

`ties` 是 `confident_miss` 的主体（run1 11/14、run2 12/14）。它们形状完全一致：题面用单数问
（"who is the dumbest superhero?"），模型写 `ORDER BY … LIMIT 1`，gold 返回所有并列行。
自然的想法是加一条"遇到并列要全返回"的规则。

按项目规矩，规则上线前必须过 official train 验证——"是非题不答布尔值"那条在 dev 上 9/9 完美，
在 train 上却与 29% 的 gold 冲突。所以要问的不是"模型该怎么做"，是"**BIRD 的 gold 到底怎么做**"。

## 做法

train 数据库本地没有（只有 dev/minidev），所以不执行，改读 gold SQL 的**写法**——约定问题本来
就写在形式里：

| 形式 | 含义 |
|---|---|
| `ORDER BY … LIMIT 1` | gold 自己只留一行，并列被丢掉 |
| `WHERE x = (SELECT MAX(…))` | gold 保留全部并列行 |
| 其它（投影里裸 `MAX()`、窗口函数、`IN (SELECT …)`） | 不分类，算比例时排除 |

题面侧的筛选故意保守：必须含最值词、且**不得**含显式复数要求（"top 5"、"list all"），
剩下的才是英文读起来确实只问一个东西的那一类。

## 结果

**train pool（9428 道，模型从未训练过）**

| | n | 占比 |
|---|---:|---:|
| singular-superlative 命中 | 1688 | |
| `LIMIT1` | 1255 | 74.3% |
| 其它（未分类） | 288 | 17.1% |
| `MAX-subquery` | 139 | 8.2% |
| 两者都有 | 6 | 0.4% |

**在两种可判定形式之间：`LIMIT1` 90.0% / `MAX-subquery` 10.0%。**

**dev500（corrected，`e3_c_rules_reasoning_corrected_run1`）**——同一类题按 gold 用哪种约定分开看模型正确率：

| gold 的约定 | n | 答对 | 正确率 |
|---|---:|---:|---:|
| `LIMIT1` | 50 | 47 | **94.0%** |
| `MAX-subquery` | 14 | 7 | **50.0%** |

**44 个百分点的差距，而两组题在英文上无法区分。** train 里的例子并排放着就能看出来：

- `Which country produced the car with the lowest price?` → gold 用 `LIMIT 1`
- `What is the order priority of the order with the highest total price?` → gold 用 `= (SELECT MAX(…))`

## 机制闭环

gold 用 `MAX-subquery` 而模型答错的 **7 道，7/7 全部是 triage 的 `ties` 命中，且 7/7 的预测里都含 `LIMIT 1`**：

```
bird_1028  bird_1032  bird_1092  bird_349  bird_37  bird_736  bird_794
```

没有"这些题恰好更难"的剩余解释空间——失败机制就是并列约定本身。

## 结论

1. **"遇到并列要全返回"这条规则不能做。** 它会与 train gold 的约 90% 冲突，比当年被否掉的
   布尔规则（29% 冲突）严重得多。这是第六次触到同一个坑，这次在写代码之前就拦住了。
2. **模型不是坏掉的那一环。** 它选了 BIRD 自己 90% 的多数约定，然后在 10% 的少数约定上被扣分。
   这解释了为什么"让模型事后复核"五次全部净负（见
   [`reasoning_trace_findings_2026-08-12.md`](../reasoning_trace_findings_2026-08-12.md) §6.4，
   `verify_before_limit` 恢复 1、打坏 9、净 −8）——**修一个不在模型里的东西，当然只会越修越差。**
3. **正确的产出是测量，不是修复。** `ties` 这一类应当作为**基准约定不一致**报告：
   同一种英文问法，BIRD 的 gold 有两种互斥的答法，题面不提供任何区分依据。
   在本次 89 道 singular-superlative 里，它造成 44pp 的正确率落差。

## 对 `confident_miss` 这个名字的进一步影响

结合上一条已经查明的问题（0.79× 推理量签名在本人群上是 0.87×/1.24×，run2 方向相反），
`confident_miss` 这个标签现在有两处不成立：签名没复现，"失误"本身对其主体也不准确——
**那 23 道里的绝大部分不是模型失误，是口径分歧。**

建议在 Phase A 语境下改名 `mechanically_repairable`（描述测试做了什么），
并在论文里把 `ties` 从"模型错误"移到"基准歧义"一节。

## 边界

- 题面筛选是英文正则，会错分一些题；本文的用途是确立一个**悬殊比例**，不是精确率。
- `neither` 桶（train 288、dev 22）未分类，比例只在两种可判定形式之间计算。
- dev 侧两组 n=50 / n=14，第二组偏小；44pp 的差距远大于噪声带，但具体数值不宜精确引用。
- 未检验的一个方向：题面里是否存在**人类可察觉但正则没抓到**的区分信号。若有，规则仍不可做
  （train 比例摆在那里），但"题面完全无法区分"这个更强的说法要收窄。
