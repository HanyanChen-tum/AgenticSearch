# F-Audit：过滤类失败与 Schema/Join 疑似噪声人工复核（2026-08-07）

## 方法

按 `docs/experiment-plan/README.md` §8.2 的抽样设计，取自修复后分类器（`docs/analysis/README.md` §4.1）产出的固定样本：

- **E0 两次运行都稳定归因为过滤类（`SEMANTIC_REVIEW_REQUIRED`）的失败**：14 题（原设计"E0 两次都为过滤错误的稳定失败"，用修正后分类重新界定）。
- **E3-A 相对 E0 恢复/新增回退的过滤类题目**：3 题（`bird_1350`、`bird_598`、`bird_1171`）。
- **Schema/Join 深度诊断（`schema_join_diagnosis_2026-08-07.md`）中标记为"可能是 gold 书写风格噪声"的候选**：3 题（`bird_1175`、`bird_1251`、`bird_1252`，均属 `thrombosis_prediction`）。

共 20 题。对每题：取 question、evidence（BIRD Hint）、gold SQL、predicted SQL，**实际对当前数据库重新执行两条 SQL**（只读连接，30 秒超时），比较返回的结果集，而不是只读 SQL 文本猜测。这是与 `schema_join_diagnosis_2026-08-07.md` 最大的方法论差异——那份文档只读了 SQL 文本就下了"可能等价"的判断，其中 3 题被本次实际执行证明是错的（见该文档 §3.2 更正）。

gold 只用于运行后人工判定，不进入任何在线机制。

> **2026-08-07 第二轮补充**：首轮标为"混合/真实歧义/待进一步核实"的 6 题（`bird_1265`、`bird_743`、`bird_937`、`bird_533`、`bird_963`、`bird_1252`）已逐一执行验证解决，见下表更新和 §补充验证。方法：对每个候选解释单独构造 SQL 并实际执行，量化每个因素对结果差异的实际贡献，而不是停留在"可能是A也可能是B"。

## 结论总表

| ID | 数据库 | 判定 | 置信度 | 一句话原因 |
|---|---|---|---|---|
| `bird_1247` | thrombosis_prediction | **gold 缺陷**（AND/OR 优先级） | 高 | gold SQL 缺括号，实际按 `FG<=150 OR (FG>=450 AND ...)` 解析，与 evidence 矛盾；predicted 加了括号，逻辑正确 |
| `bird_1254` | thrombosis_prediction | **gold 缺陷**（边界不一致） | 高 | evidence 明确写 `>=1990`，gold SQL 却用 `>1990`；predicted 忠实遵循 evidence |
| `bird_1265` | thrombosis_prediction | **gold 缺陷**（AND/OR 优先级，第二轮升级为高置信度） | 高 | 实测：按 evidence 修正括号后的"意图正确"查询结果为35，与 predicted 的35完全一致（predicted 额外加的 `'-'`/`'+-'` 字面量未匹配任何行，无害）；gold 实际执行得47，确认是bug，不是取值歧义 |
| `bird_1267` | thrombosis_prediction | **Agent 错误**（取值字面量译反） | 高 | evidence 说"`-` 代表 `negative`"，predicted 直接把符号 `-`/`+-` 当作数据库字面量用，没有代入解码后的值 |
| `bird_1322` | student_club | **gold 缺陷**（答非所问） | 高 | 题目问"多少个是会议"，gold SQL 却用 EXCEPT 返回"非会议"事件名称列表；predicted 正确统计了会议数量(4) |
| `bird_340` | card_games | **输出契约歧义**（非过滤问题） | 高 | predicted 和 gold 的 WHERE 逻辑完全一致，25061 行完全相同，只是选了 `name` 列而不是 `id` 列 |
| `bird_474` | card_games | **evidence 自相矛盾** | 高 | evidence 明确说"under 100 指 baseSetSize<10"，gold SQL 却用 `<100`；predicted 忠实遵循了 evidence 的（错误）公式 |
| `bird_533` | codebase_community | **真实歧义**（日期截断惯例，第二轮量化确认） | 中 | 实测：`LastAccessDate` 是完整时间戳（如 `2014-08-08 06:42:58.0`），恰好205行落在"2014-09-01当天但带时间"这个区间，是这205行造成了5146 vs 4941的全部差距；evidence 原文只给了日期字面量、未注明截断，"after DATE"该按日粒度还是时间戳粒度理解本身有歧义，两种解读都能自圆其说 |
| `bird_672` | codebase_community | **gold 缺陷**（缺 DISTINCT） | 高 | 题目问"多少用户"，gold 未去重导致一用户多帖被重复计数；predicted 用了 DISTINCT，逻辑更贴合题意 |
| `bird_710` | codebase_community | **gold 缺陷**（查错表的字段） | 高 | 题目问"评论的分数"，gold 却检查了 posts.Score 而不是 comments.Score；predicted 查对了字段 |
| `bird_743` | superhero | **偏向 Agent 轻微错误**（分母口径，第二轮量化） | 低中 | 实测：750个superhero里只有9个缺publisher/alignment关联(1.2%)；gold用全体750做分母（更贴合"占全体superhero的百分比"的字面问法），predicted隐式把分母收窄成有关联的741——问题问的是"占superheroes的百分比"，倾向支持gold口径更贴题，但影响幅度很小(28.27%vs28.61%) |
| `bird_85` | california_schools | **输出契约**（列顺序，非过滤问题） | 高 | 两个值完全正确，只是列顺序互换；官方评测按元组精确匹配会判错，但计算逻辑 100% 正确 |
| `bird_937` | formula_1 | **偏向 gold 解读有误**（rank vs position，第二轮查官方字段说明确认） | 中高 | 数据库自带字段说明明确写：`rank`="按最快圈速排的起始名次"，`position`="比赛完赛名次"。题目问的是"finish time"（完赛用时），跟`position`（完赛名次）语义配对才自洽；gold用`rank`（圈速名次）配"finish time"内部逻辑不一致，predicted用`position`更合理 |
| `bird_963` | formula_1 | **gold 缺陷**（缺 DISTINCT，第二轮验证并推翻原假设） | 高 | 实测：`time`字符串解析值与`milliseconds`整数值完全等价（同一测量的两种格式，不是语义不同的列，原假设错误）；真正原因是gold的`COUNT(T1.driverId)`不去重，统计的是23292条单圈记录，而题目问"多少法国车手"应该去重，`COUNT(DISTINCT...)`=9与predicted完全一致 |
| `bird_1350` | student_club | **Agent 错误**（未核实 Hint 格式） | 高 | evidence 给出的日期字面量 `'2019-8-20'` 与数据库实际存储格式 `'2019-08-20'` 不一致，predicted 直接照抄未用 `sample_values` 核实 |
| `bird_598` | codebase_community | **Agent 错误**（分母口径错） | 中高 | evidence 隐含分母应限定在 `Name='Student'` 的记录内，predicted 的分母却覆盖了全部 badge 类型 |
| `bird_1171` | thrombosis_prediction | **Agent 错误**（逻辑错误） | 高 | 把"出生年份 < 18"当成了"未成年"判据，应该是"检查年份-出生年份 < 18"（年龄） |
| `bird_1175` | thrombosis_prediction | **Agent 错误**（错误 JOIN 条件） | 高 | 多加了一个日期相等的 JOIN 条件，导致结果集被过滤为空 |
| `bird_1251` | thrombosis_prediction | **Agent 错误**（遗漏必要 JOIN） | 高 | 省略了到 `Examination` 的连接，把没有检查记录的患者也计入，136 vs gold 的 9 |
| `bird_1252` | thrombosis_prediction | **gold 缺陷**（缺 DISTINCT，第二轮升级为高置信度） | 高 | 实测：只有1个distinct患者满足条件，但该患者有4条匹配的Lab×Exam行组合；gold的`COUNT(T1.ID)`不去重把4行都计入变成4，predicted的`COUNT(DISTINCT...)`=1才对。另外验证evidence与gold的边界不一致(严格不等式 vs BETWEEN)在本例中实际不影响结果(无行落在边界值上)，缺DISTINCT才是真正原因 |

## 汇总统计（2026-08-07 第二轮补充验证后更新）

| 类别 | 题数 | 占比 |
|---|---:|---:|
| **确认 gold 本身有缺陷**（逻辑/优先级/答非所问/缺 DISTINCT/查错字段） | 8（`1247`、`1254`、`1322`、`672`、`710`、`1265`、`963`、`1252`） | 40% |
| evidence 与 gold SQL 自相矛盾 | 1（`474`） | 5% |
| 输出契约问题被误归为过滤/Schema 错误（数值 100% 正确，只是列选择/顺序不同） | 2（`340`、`85`） | 10% |
| 真实歧义（题面/schema 本身有多种合理解读，量化后仍无法判定单一真值） | 1（`533`） | 5% |
| 量化后有倾向性但置信度不满格 | 2（`937` 偏向 gold 解读有误、`743` 偏向 predicted 轻微口径错误） | 10% |
| **确认为真实 Agent 错误** | 6（`1267`、`1350`、`598`、`1171`、`1175`、`1251`） | 30% |

首轮标注"混合/真实歧义/待核实"的 6 题（`1265`、`743`、`937`、`533`、`963`、`1252`）已全部逐一执行验证：`1265`、`963`、`1252` 三题实测证明是 gold 缺陷（分别是同类 AND/OR 优先级 bug、缺 DISTINCT、缺 DISTINCT——**缺 DISTINCT 这个具体 bug 模式在 20 题样本里出现了至少 3 次**，`672`也是同类，跨 4 个不同数据库出现，是目前样本里最常见的单一 gold 缺陷类型）；`937` 靠数据库自带字段说明确认 gold 把"完赛名次"和"圈速名次"两个真实存在但含义不同的列搞混了；`743` 量化后影响幅度很小（1.2%的行）但仍倾向 predicted 有轻微口径问题；只有 `533`（日期截断粒度）在实测量化后依然是真正的、无法用执行结果本身判定的语义歧义。

**核心结论：这 20 题里只有 30% 是干净的、可以直接拿去指导下一个机制的 Agent 推理错误；70% 要么是数据集本身有缺陷、要么是被误归类的输出格式问题、要么是执行验证后仍然存在的真实歧义或倾向性判断。** 比首轮的 35%/65% 更极端。这印证了文档里一直强调的"过滤类是自动分类置信度最低的一类"，且这次是靠逐题实际执行验证得出的，不是停留在读 SQL 猜测。

## 对已发布数据的影响

1. **`docs/analysis/README.md` §4.1 里 E0 合计 36 条过滤类失败，不应直接作为"36 个 Agent 推理错误"使用**——按本次抽样的比例外推（40%确认gold缺陷+10%被误归类输出问题+15%歧义/倾向性=65%不是干净agent错误），过滤类的"真实 Agent 错误"存量可能只有约三分之一。抽样并非随机（覆盖了稳定失败+E3-A迁移+Schema疑似噪声的定向样本），比例不能直接线性外推，但方向性结论比首轮更确定。
2. **"缺 DISTINCT"是这批数据集里最值得单独关注的 gold 缺陷模式**：`672`、`963`、`1252` 三题（跨 codebase_community、formula_1、thrombosis_prediction 三个数据库）都是同一种 bug——题目问"多少个X"（去重计数实体），gold 却用不去重的 `COUNT(col)` 在一对多 JOIN 之后统计，导致一个实体因为在子表里有多条匹配行而被重复计数。这不是随机噪声，是可能贯穿整个数据集的系统性 gold 编写模式，值得在后续任何"predicted 和 gold 不一致"的场景里，优先检查是不是这个原因。
3. **`bird_340`、`bird_85` 应重新归类为 `OUTPUT_CONTRACT`，不是 `SEMANTIC_REVIEW_REQUIRED`**——分类器目前的过滤兜底桶里混入了这类"值完全正确、只是列选择/顺序不同"的题目；`docs/analysis/README.md` §4.1 已经指出分类器对输出契约有专门检查（`output_column_count_mismatch`），但没有检查"列内容正确、列顺序不同"这种情况——这是分类器本身还没覆盖到的第三个盲点，值得在后续修分类器时一并处理。
4. **确认为 gold 缺陷的 8 题**（`bird_1247`、`bird_1254`、`bird_1322`、`bird_672`、`bird_710`、`bird_1265`、`bird_963`、`bird_1252`）**已标记为 `DATASET_OR_GOLD_CONFLICT`**（写回 `e0_core_run1`/`e0_core_run2`/`e3_a_core197_run1`/`e3_c_schema_v4_core197_run3` 的 `classification_sheet.csv`）——这两个类别此前从未被自动分类器赋值过（`docs/analysis/README.md` §4.1 已指出这一点），本次是首批实际产出的人工判定。这 8 题不应计入任何后续机制的"待恢复错误"分母。
5. **`bird_937` 的 rank/position 混淆与 Schema/Join 诊断里发现的近义列模式（`european_football_2` 的两个候选外键、`formula_1` 的 results/driverStandings）属于同一类问题**，进一步支持该诊断的方向判断，只是这次这道具体题目被分类器归进了过滤类而不是 Schema 类——说明"近义 schema 元素混淆"这个模式的实际影响面比 Schema/Join 类别单独统计出来的还要广，会渗透到其他语义类别的误判里。
6. **`schema_join_diagnosis_2026-08-07.md` 的一处假设已被推翻并更正**：`thrombosis_prediction` 的 3 题 Schema/Join 失败不是 gold 书写风格噪声，是真实 Agent 错误（详见该文档 §3.2 更正）。

## 方法论教训

`schema_join_diagnosis_2026-08-07.md` 只读 SQL 文本就对 3 道题下了"可能等价"的判断，其中全部被本次实际执行推翻。**任何"predicted 和 gold 逻辑等价、只是写法不同"的判断，必须先实际执行两条 SQL 并比较结果集，不能只靠读 SQL 结构猜测**——即便是经验丰富的人工审查也会在这一步出错，更不能指望自动分类器靠正则/字符串比较做到。这条教训同样适用于未来任何"这个 JOIN/字段是不是必要"的人工判断，第二轮补充验证（`bird_1265`/`963`/`1252`/`937`/`743`/`533`）延续了同一方法，把三道"混合/待核实"题目量化确认为干净的 gold 缺陷。

## 下一步

1. ~~将确认的 gold 缺陷和输出契约误归类的判定写回对应 `classification_sheet.csv`~~ ——**已完成**（两轮共 8 题 gold 缺陷 + 2 题输出契约误归类，见上方 §对已发布数据的影响）。
2. `bird_1267`、`bird_1171`、`bird_1175`、`bird_1251` 这类"取值字面量译反"、"逻辑符号写反"、"JOIN 条件想当然"的真实 Agent 错误，共性是模型没有在生成 SQL 前用 `sample_values` 核实过 Hint 里给出的字面量或枚举编码是否与数据库实际存储一致。**已实现并测试"FINAL 前未核实字面量警告"机制（`e3-c-literal-check` profile），N=44 分层验证显示净回退，已拒绝**，详见 [`e3_c_literal_check_smoke2.md`](e3_c_literal_check_smoke2.md)。
3. Schema/Join 诊断衍生的"防御性过度 JOIN 提醒"机制（`e3-c-join-minimal`）N=26 smoke 显示净正向但样本太小，v2 迭代后净效果归零且发现样本内"脆弱题"噪声，已暂停迭代，详见 [`e3_c_join_minimal_v2_smoke1.md`](e3_c_join_minimal_v2_smoke1.md)。
4. **"缺 DISTINCT"这个跨数据库反复出现的 gold 缺陷模式**（本文档 §对已发布数据的影响 第2点）目前还没有对应的机制候选——它是纯数据集问题，不需要 Agent 侧机制，但值得在后续任何"predicted 和 gold 不一致"的自动/人工判断里，把"predicted 是否用了 DISTINCT、gold 是否漏了"作为一个专门检查项，可以直接减少下一轮 F-Audit 或分类修复的重复劳动。
