# 标注约定后处理（E3-C-CONV）与同配置重跑方差（2026-08-08）

## 起点

`analysisDetail/e3_d_query_mining_diagnosis_2026-08-08.md` 在否决 E3-D 时留了一句：若日后重启，
挖掘目标须从"问题 → SQL 结构"（与模型能力重叠）改为"数据集书写约定"。本文档记录该重定向的完整执行与结果。

关键设计选择是**交付方式**：约定不写进 Prompt，而由 harness 对最终 SQL 做确定性改写。理由见下节的受控测量。

---

## 一、把约定写进 Prompt 无效（受控测量）

E3-A 的静态 patterns 文本里逐字写着：

- `- List without duplicates: ... consider whether DISTINCT is required to preserve the requested output ...`
- `- Top or bottom result: For highest, lowest, earliest, latest, or top-k questions, verify the ORDER BY direction and apply LIMIT ...`

新建 profile `e3-ac` = e3-c + `query_pattern_mode="train-static-v1"`，与 `e3-c` 只差这一个变量
（schema、capability gate、few-shot 全同），因此指令在场与否是受控的。统计模型违反三条约定的次数：

| profile | 指令 | 最值 | 拼接 | DISTINCT | 合计违反 |
|---|:--:|---:|---:|---:|---:|
| e3-c | 无 | 7违/6错 | 4违/4错 | 14违/11错 | **25** |
| e3-ac | **有** | 8违/7错 | 2违/2错 | 14违/12错 | **24** |

**25 → 24。指令在场与否，模型违反约定的行为没有变化**；写着"考虑是否需要 DISTINCT"的 e3-ac，
DISTINCT 违反数与完全没这句话的 e3-c 一模一样（14 vs 14）。

这个结论比准确率对比可靠，因为它不经过评分环节，直接数模型写出的 SQL 形态（见 §四的方差讨论）。

机理：这三条不是模型缺失的知识，而是 BIRD 的书写偏好，且偏好在语义上是不占理的一方
（计数遇 JOIN 时去重是对的，BIRD gold 89% 不去重）。指令只是提醒模型去想，模型想过之后结论不变。
要让 Prompt 生效，得写成"即使存在重复也一律不要 COUNT(DISTINCT)"——一条语义上错误的硬指令。

---

## 二、组件

| 文件 | 职责 |
|---|---|
| `scripts/build_sql_conventions.py` | 从 `data/train_pool.json` 挖掘约定，产出带支持度与跨库检验的 artifact |
| `data/processed/sql_conventions_v1.json` | artifact，版本 `train-conventions-v1` |
| `ours/agent/sql_conventions.py` | 运行时改写器 + manifest |
| `scripts/apply_sql_conventions.py` | 离线重评，无 LLM 调用 |
| profile `e3-c-conv` | e3-c + `sql_convention_mode="train-conventions-v1"` |

挖掘结果（9428 条 train SQL 全部解析成功）：

| 约定 | train 支持度 | 适用题数 | 多数遵守的库 |
|---|---:|---:|---:|
| `no_select_concat` — 分列而非 `\|\|` 拼接 | **99.99%** | 9428 | 69/69 |
| `superlative_order_limit` — `ORDER BY...LIMIT` 而非 `= (SELECT MAX)` | **90.34%** | 1542 | 63/65 |
| `count_no_distinct` — 计数遇 JOIN 不去重 | **89.10%** | 2377 | 65/67 |

支持度是**条件比率**（分母限定为标注者真正面临该选择的查询），不是语料频率。
门禁要求支持度 ≥0.80、适用题数 ≥100、覆盖库数 ≥8，三条全部通过。

改写规则刻意保守，形状不符即拒绝：

- `count_no_distinct` 仅在查询含 JOIN 时剥离；无 JOIN 时不存在连接放大，模型写的 DISTINCT 更可能是题目真要的
- `no_select_concat` 在别名被 `ORDER BY`/`GROUP BY`/`HAVING` 引用时拒绝拆分——`bird_1011` 上拆分曾把
  一个错答案变成 `no such column: full_name` 的硬报错，已加守卫并写了回归测试
- `superlative_order_limit` 仅在子查询是单表裸聚合、且外层无 `ORDER BY`/`LIMIT`/`GROUP BY` 时触发。
  该规则在 197 题上**触发 0 次**：约定为真，但模型实际写出的 7 处违反全部不属于可机械改写的形状
  （4 处外层已有 `ORDER BY`，会与改写冲突；4 处子查询自带 `WHERE`/`JOIN`，去掉会改变语义）

改写全部留痕：trace 中 `sql_convention_manifest` 记录 artifact 哈希与合规声明
（`uses_dev_data=false`、`uses_gold_sql=false`），`sql_convention_rewrite` 逐题记录命中规则与改写前后 SQL。
因此任何一次运行的准确率都可以拆成"模型产出"与"harness 改写"两部分。

Prompt 哈希未变：`e3-c-conv` 与 `e3-c` 同为 `1ea7ea4d3306`，从哈希层面证明该组件不碰 Prompt。
（`agent_config_sha256` 因 dataclass 新增字段而变化，与此前加 `literal_verification_nudge`、`context_mode` 时同理，
历史结果比对须按字段而非按哈希。）

---

## 三、效果：+5，两次独立测量一致

| 测量方式 | 基线 | 后处理后 | 净 | 转正 | 打坏 |
|---|---:|---:|---:|---|---|
| 离线重评 e3-c run3 | 77/197 | **82/197** | **+5** | 1505, 1387, 1252, 1267, 865, 672 | 92 |
| 在线运行 e3-c-conv | 71/197 | **76/197** | **+5** | 1505, 1169, 1252, 1267, 865, 877 | 92 |

两次的模型产出完全不同（见 §四），后处理净收益都是 +5，转正题有 4 题重合。
`bird_92` 两次都被打坏——它的 gold 确实需要 `COUNT(DISTINCT district_id)`，是 89.10% 支持度背后 11% 反例的真实体现。
**+5 已经包含了这个代价。**

诚信说明：转正的题中 `bird_1252`、`bird_1267`、`bird_672` 是 F-Audit 判定的 gold 缺陷题，
这部分收益本质是让模型复现 gold 的写法。按 BIRD 规则合规（train-only 挖掘、后处理属 harness），
但只能报告为**标注对齐**，不得计入 SQL 能力提升。

---

## 四、同配置重跑方差：6 题（本项目首次直接测量）

`e3-c-conv` 与 `e3-c` run3 超参逐项对齐（`max_iterations=8`、`k=1`、`temperature=0`、
`reasoning_effort=high`、同一 ids-file 与 id-groups），只差 `sql_convention_mode`。
利用 `sql_convention_rewrite.original_sql` 可还原本次运行**后处理前**的成绩：

| | e3-c run3 | e3-c-conv 本次 | 差 |
|---|---:|---:|---:|
| 后处理前准确率 | 77/197 | 71/197 | **−6** |
| 后处理后准确率 | （未启用） | 76/197 | |

模型侧逐题比较：对→错 7 题，错→对 6 题，**SQL 逐字相同的仅 10.7%**。
`temperature=0` 并不锁定输出，因为约 93% 的 completion token 是每次不同的隐藏推理。

### 由此必须收回的一个结论

`e3-ac` 得 70/197，比 `e3-c` 的 77 低 7 题。此前口头报告称"7 题超出实测的 ±4 扰动噪声带"，
据此判断静态 patterns 有害。**该判断不成立**：同配置重跑的直接方差就是 6 题，−7 只比噪声大 1 题。

仍然站得住的是两条更弱的表述：

1. patterns 没有带来假设中的 +5 互补收益（三次运行均未出现）
2. §一的违反计数 24 vs 25 不受此影响——它不经过评分，"把约定写进 Prompt 无效"依然成立

### 对既有结论的普遍影响

**凡是基于单次运行、差异在 6 题（3 pp）以内的 profile 对比，都不能作为结论。**
`SYNTHESIS.md` §5 原写"小于约 2 pp 的变化只能记为趋势"，该阈值偏低，应改为 3 pp 并注明依据。

后处理的 +5 不受此约束，因为它是 `predicted_sql` 的确定性函数，模型跑好跑坏都复现。
这正是本项目反复出现的规律的又一例：**系统侧确定性干预可复现，模型侧干预被噪声淹没。**

---

## 五、后续

1. **e3-c 基线值得重跑 1–2 次取均值**。当前所有对比都建立在 run3 这个单点上，而单点的不确定度是 ±6 题。
2. **不要再用单次运行判定 profile 优劣**，除非效应量明显超过 6 题。
3. 剩余可挖的约定候选见 `full_failure_audit_2026-08-08.md`：纯列序差异 4 题、纯类型格式差异 1 题。
   列序无法在不看 gold 的情况下确定性修正，风险高于已实现的两条规则。
