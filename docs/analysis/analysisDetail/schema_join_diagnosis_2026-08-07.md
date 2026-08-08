# Schema/Join 深度诊断（2026-08-07）

## 目的

`docs/analysis/README.md` §4.1 的分类器修复显示 Schema/Join 是 E0 基线里最大的语义错误类别（97/259），且即使在被接受的 E3-C（Offline Schema Context）之后，Schema/Join 仍是 E3-C 自身失败集合里最大的一类（46/120=38.3%）。本诊断回答一个问题：**E3-C 之后残留的 Schema/Join 失败，根因是检索召回不足，还是模型拿到正确信息后仍然选错？**

使用的数据全部来自已完成的 `e3_c_schema_v4_core197_run3`（修复后分类器重新生成的 `classification_sheet.csv` + 已有的 `e3_c_schema_v4_core197_run3_retrieval_audit.csv`，后者用 sqlglot 对 gold SQL 做 AST 级解析），未运行新实验。

## 1. 检索召回 vs 推理：结论明确

46 条 `SCHEMA_LINKING` 失败（33 条 `table_or_join_path_mismatch` + 13 条 `join_key_or_condition_mismatch`）按 retrieval audit 的 `diagnostic` 字段分类：

| 诊断 | table_or_join_path_mismatch | join_key_or_condition_mismatch | 合计 |
|---|---:|---:|---:|
| `retrieval_complete_mining_abstained_semantic_failure`（检索完整，纯语义/推理失败） | 31 | 12 | 43 |
| `detailed_schema_column_miss_or_compact_index_only`（检索确实有缺口） | 2 | 1 | 3 |

**93.5%（43/46）的 Schema/Join 失败发生在 gold 所需的表/字段已经完整出现在检索结果里的情况下。** 也就是说，E3-C 的 Offline Schema Context 检索机制本身基本没问题，瓶颈不在"模型有没有看到正确的 Schema"，而在"模型看到了正确 Schema，仍然选错了表、字段或 Join 路径"。这排除了"扩大检索范围/提高召回率"作为下一步机制的必要性——真正要解决的是选择/消歧问题。

## 2. 按数据库分布

| 数据库 | 失败数 |
|---|---:|
| codebase_community | 8 |
| formula_1 | 8 |
| financial | 6 |
| toxicology | 6 |
| card_games | 5 |
| debit_card_specializing | 4 |
| california_schools | 4 |
| thrombosis_prediction | 3 |
| european_football_2 | 1 |
| student_club | 1 |

失败高度集中在少数几个数据库，而不是均匀分布，这本身就是一个信号：问题更可能来自这些数据库特有的 schema 设计（近义表/近义字段），而不是通用的"模型不会读 schema"。

## 3. 逐题核对后的具体失败模式

抽样读取了 `formula_1`、`codebase_community`、`thrombosis_prediction`、`european_football_2`、`toxicology`、`financial`、`debit_card_specializing`、`student_club` 的 predicted SQL 与 gold SQL 全文（数据见同目录 `schema_join_failures_detail.json` 的生成脚本，未随本文档提交，可按需重新生成），归纳出四类具体模式：

### 3.1 近义表混淆（最主要、最可操作的一类）

- **`formula_1`：`results` 与 `driverStandings` 被系统性混淆。** 8 条失败里至少 3 条（`bird_896`、`bird_902`、`bird_906`）是 gold 要求 `driverStandings`（某场比赛后的累计车手积分榜排名），模型却用了 `results`（单场比赛的名次）。这两张表列名高度相似（都有 driverId、raceId、position/rank 类字段），但语义完全不同——一个是"这场比赛跑了第几"，一个是"这场比赛后总积分榜排第几"。这是可以通过在 Offline Schema metadata 里给这两张表加一句消歧说明直接解决的具体问题。
- **`codebase_community`：字面表名陷阱。** `bird_584` 问题要问的是 "Comment"，schema 里恰好有一张名为 `comments` 的表，模型直接选了它；但 gold 要的其实是 `postHistory` 表里 `Comment` 类型的历史记录（`postHistory.Comment` 字段配合 `PostHistoryTypeId`），`comments` 表在这个 schema 里另有语义（帖子下的用户评论，不是版本历史里的编辑说明）。这也是同类"表名字面相似、语义不同"的陷阱，且是三个 `codebase_community` 样本（`bird_584`、`bird_595`、`bird_637`）共有的根因方向：gold 反复通过 `postHistory` 表回答问题，模型反复绕开它去找"看起来更直接"的表。
- **`european_football_2`：同一张表上的两个候选外键。** `bird_1107` 中 `Player` 表同时有 `player_api_id` 和 `player_fifa_api_id` 两个可以连接 `Player_Attributes` 的候选键，gold 用后者，模型用了前者——这是纯粹的"多把相似钥匙选错一把"，attribute 表里两个 ID 字段并存但只有一个是 gold 惯用的连接键。

### 3.2 gold 的"必经中转表"假设——已被 F-Audit 实际执行推翻

> **2026-08-07 更正**：本节原判断"`thrombosis_prediction` 的必经 `Patient` 中转表可能是书写风格差异，模型答案大概率等价正确"，这只是基于读 SQL 文本的猜测。F-Audit（见 [`filter_audit.md`](filter_audit.md)）对这 3 题做了实际执行验证后，**这个假设是错的**：三题的预测结果集和 gold 完全不同（不是"形式不同、值相同"），全部是真实的逻辑错误，不是无谓的必经表约定。

- `bird_1175`：模型在 JOIN 条件里额外加了 `L.Date = E.[Examination Date]` 这个日期相等条件，实际执行返回 0 行（gold 非空）——这是一个会把结果过滤没的错误连接条件，不是风格差异。
- `bird_1251`：模型完全省略了到 `Examination` 表的连接，实际执行返回 136（gold 为 9）。差距如此悬殊说明 `Examination` 连接不是"多余的中转"，而是在过滤"确实有检查记录的患者"，模型省略它导致把没有 `Examination` 记录的患者也计入了。
- `bird_1252`：模型用 `EXISTS` 子查询替代 `Examination` 的 `INNER JOIN`，返回 1（gold 为 4）；差异主要来自 `IGG` 边界处理不一致（Evidence 原文写"IGG > 900 and IGG < 2000"是严格不等式，但 gold SQL 用的是包含边界的 `BETWEEN 900 AND 2000`——这是 Evidence 与 gold SQL 本身不一致，属于数据集问题；预测忠实按 Evidence 走了 `>900 AND <2000`，但差距的量级不能完全用边界值解释，`EXISTS` 和 `JOIN` 的语义差异也贡献了一部分）。

结论：这 3 题应从"可能是数据集噪声"移出，计入真实的 Agent 错误（`bird_1175`/`bird_1251` 高置信度；`bird_1252` 部分是 Evidence/gold 不一致、部分是真实逻辑差异，中等置信度）。教训是：**判断"gold 的额外 JOIN 是否必要"不能只读 SQL 文本，必须实际执行两边 SQL 比较结果集**——这也是 F-Audit 方法论的核心，本节的错误恰好证明了为什么这一步不能省略。

### 3.3 过度连接（防御性过 Join）

- `toxicology` 的 `bird_207`：gold 只需 `atom` JOIN `bond`（2 表），模型额外引入了 `connected` 表并用 UNION 处理双向原子引用，逻辑上是在"能想到的所有相关表"里都连了一遍，而不是精确判断哪张表是回答问题真正需要的。
- `thrombosis_prediction` 的 `bird_1175`：模型比 gold 多连了一张 `Examination`，同时使用的日期字段来源也和 gold 不同。

这类模式和 3.1 相反：3.1 是"该连的近义表连错了"，3.3 是"不确定的时候倾向于多连一张表兜底"，两者都指向同一个更底层的问题——**模型没有一个显式的、可核查的"当前问题到底需要哪些表、哪些表不需要"的判断步骤**，而是隐式地在生成 SQL 的同时做表选择，容易被字面相似性带偏，或者用"多连表更安全"的直觉代替精确判断。

### 3.4 纯语义/逻辑错误（与 Schema 选择无关，只是恰好也导致表集合不同）

- `debit_card_specializing` 的 `bird_1524`：模型把问题理解成了"哪个客户的货币"而不是"哪个加油站所在国家"，连带选错了 `customers` 而不是 `gasstations`——这是题意理解错误，表选择错误只是下游症状。
- `financial`/`debit_card_specializing` 的几个复杂聚合题（`bird_145`、`bird_1481`）里，模型构造了逻辑上更复杂（用 CTE 分步计算）但过滤条件、时间范围处理方式与 gold 不同的查询——这类更接近聚合/过滤语义错误，只是恰好在表选择上也有细微出入，不是纯粹的 Schema 问题。

## 4. 诊断结论

1. **不是检索问题。** 93.5% 的 Schema/Join 失败发生在检索完整的情况下，扩大检索范围/提高召回率不会改善这批失败。
2. **主要是"近义表/近义字段消歧"问题，且高度集中、可枚举。** `formula_1` 的 results/driverStandings、`codebase_community` 的 comments/postHistory、`european_football_2` 的 player_api_id/player_fifa_api_id 是三个具体、可复现、可针对性修复的混淆点，而不是笼统的"模型不会读 schema"。
3. ~~至少一部分（`thrombosis_prediction` 的必经中转表模式）可能根本不是 Agent 错误~~ ——**已通过 F-Audit 实际执行验证推翻**，这 3 题确认是真实的 Agent 逻辑错误（错误 JOIN 条件、遗漏必要 JOIN），不是数据集噪声。教训：Schema 层面"这个 JOIN 是否必要"的判断必须靠实际执行验证，不能只读 SQL 文本猜测。
4. **存在一个尚未被现有机制覆盖的具体倾向：模型在"该不该连这张表"上没有显式判断步骤**，导致近义表被字面相似性带偏（3.1）或被防御性过度连接（3.3）掩盖。

## 5. 建议的下一步（按性价比排序）

1. **优先（低成本，直接可做）**：把 3.1 节识别出的具体近义表/字段消歧信息，作为数据库级 Offline Schema metadata 的补充条目（而不是重新设计检索或引入新的在线机制）——针对 `formula_1` 的 results vs driverStandings、`codebase_community` 的 comments vs postHistory、`european_football_2` 的两个候选 player key，各写一句简短消歧说明，挂在对应表的 metadata 上，只有这些表被选中时才注入。这是对已确认最大残留错误类别的直接干预，成本远低于 E4-A 那种全局 QueryPlan。
2. ~~并行：把 `thrombosis_prediction` 这 3 题纳入 F-Audit 抽样~~ ——**已完成**，见 [`filter_audit.md`](filter_audit.md)；结论是这 3 题都是真实 Agent 错误，不是 gold 书写风格差异，应计入待修复错误而非剔除。
3. **验证方式**：先在 `formula_1`、`codebase_community`、`european_football_2` 这三个数据库的题目子集上做消歧信息的最小可行测试（不需要跑满 197 题），确认能恢复对应的失败题、且不引入新回退后，再决定是否扩展到全部数据库的近义表模式挖掘。

这个方向和 E3-D/E3-F 的 Query Mining（挖掘 SQL 结构模式）是两件不同的事——这里要挖的是 **schema 层面的消歧知识**，不是 SQL 结构模式，属于 E3-C 范畴内的补充，不需要等 Query Mining 的跨库门禁通过。
