# 剩余失败的逐题根因审计（2026-08-08）

## 对象与方法

基线为当前最优配置 **e3-c + 确定性约定后处理 = 82/197 (41.62%)**，对其 115 题失败逐题定性。
其中 32 题在 [stable_failure_audit_2026-08-08.md](stable_failure_audit_2026-08-08.md) 已审计，
本文补齐剩余 **83 题**。

方法上强制执行两边 SQL 并比对实际结果集，不允许只读 SQL 文本下结论——
上一轮审计正是因为只读 SQL 而把三道 thrombosis_prediction 失败误判为「gold 风格噪声」，执行后证明全是模型真错。
每题记录 pred/gold 的行列形状、结果集包含关系与前若干行取值。

## 结论

| 类别 | 本轮 83 题 | 先前 32 题 | 合计 | 占比 |
|---|---:|---:|---:|---:|
| 模型真实错误 | 7 | 3 | 10 | 8.7% |
| gold 缺陷 | 34 | 10 | 44 | 38.3% |
| Hint 与 gold 矛盾 | 12 | 2 | 14 | 12.2% |
| 输出约定未指定 | 14 | 8 | 22 | 19.1% |
| 指代歧义 | 14 | 4 | 18 | 15.7% |
| 标注约定残留（改写规则不适用） | 2 | 5 | 7 | 6.1% |
| **合计** | **83** | **32** | **115** | |

**115 题失败中只有 10 题（8.7%）是模型的 SQL 能力问题。**
这与先前基于 31 题样本外推的「约 10%」完全吻合，现在是全量普查而非抽样。

剩余 105 题若按题意公正评判本应算对，对应的名义上限为 187/197 = 94.9%。
该数字不是可达目标，只用于说明：**在这个 197 题子集上，准确率的主要决定因素已不是模型能力。**

## 本轮发现的系统性 gold 缺陷模式

gold 缺陷占比从先前抽样的 32% 升到全量的 38.3%，且呈现可归纳的模式：

| 模式 | 题目 | 说明 |
|---|---|---|
| AND/OR 优先级 bug | `bird_1247`、`bird_234`、`bird_1265` | `A OR B AND C AND D` 中第一个析取项不受任何其他条件约束 |
| 条件恒真 | `bird_529` | `language = 'Korean' AND language NOT LIKE '%Japanese%'` 写在同一行上，后半恒真 |
| 经 postHistory 连接放大计数 | `bird_637`、`bird_639`、`bird_640` | 同一帖子按历史记录条数重复累加 |
| 数值列按字符串排序 | `bird_115`（另见先前的 `bird_879`） | `ORDER BY A4 DESC` 对文本型人口数做字典序 |
| 排序未排除 NULL | `bird_847` | SQLite 升序把 NULL 排最前，选中空值行 |
| gold 答非所问 | `bird_1322`、`bird_951`、`bird_682`、`bird_129`、`bird_231`、`bird_402`、`bird_967`、`bird_125` | 返回的量或列与题目要求不符 |
| gold 自身不可执行 | `bird_518`（超时 30s）、`bird_944`（返回 None） | 该题实际不可评分 |

## Hint 与 gold 矛盾从 6% 升到 12.2%

这是本轮相对先前抽样变化最大的一类。共同结构是：**模型严格照 Hint 的字面公式实现，gold 却没有照自己的 Hint 写**。

| 题目 | Hint 字面要求 | gold 实际做法 |
|---|---|---|
| `bird_474` | 文字说 under 100，公式却写 `baseSetSize < 10` | 用 `< 100` |
| `bird_604` | `average age = Divide(Sum(Age), Count(UserId))` | 用 `AVG(Age)`，自动跳过空值 |
| `bird_1242` | 年龄按 `current_timestamp` 计算 | 按化验当年（1984）计算 |
| `bird_1239` | `COUNT(ID) > 2` | 按题干用 `>= 2` |
| `bird_1254` | `YEAR(First Date) >= 1990` | 用 `strftime > '1990'`，实为 >= 1991 |
| `bird_486` | 分母 `SUM(convertedManaCost)` | 用 `COUNT(id)` |
| `bird_197`、`bird_198` | `AVG(element='o')` / `DIVIDE(SUM(...), COUNT(atom_id))` | 另算每分子计数的均值 |
| `bird_1225` | `List refers to GROUP_CONCAT(DISTINCT ID)` | 逐行返回 |

这类失败对「提高准确率」有直接含义：**让模型更严格地遵守 Hint 会降低分数**，因为 Hint 本身与基准不一致。
先前 hint 消融实验（[hint_ablation_2026-08-08.md](hint_ablation_2026-08-08.md)）只测了去掉 Hint 的影响，未触及这一层。

## 输出约定中新识别的子类：纯列序差异

`bird_50`、`bird_85`、`bird_1235`、`bird_37` 四题的 pred 与 gold **取值完全相同，只是列的先后顺序不同**。
官方评测按结果集比对，列序不同即判错。三题中 gold 的列序与题干中实体出现的先后一致，
提示这可能是一条可挖掘的书写约定；但列序无法在不看 gold 的情况下确定性地修正，风险高于已实现的两条规则。

`bird_228` 是另一个纯格式差异：pred 经 `printf` 返回字符串 `'45.4545'`，gold 返回浮点 `45.4545`，数值完全相同。

## 模型真实错误逐题

这 10 题是全部审计范围内唯一属于模型 SQL 能力的失败。

| 题目 | 错因 |
|---|---|
| `bird_1265` | hint 说 '-' means 'negative'、'+-' refers to '0'，库中实际存 negative/0；pred 却按字面用 IN ('-','+-') 得 0 行且未察觉 |
| `bird_1472` | least consumption in 2012 应按客户对全年求和后取最小，pred 取了单月消费最小的那一行 |
| `bird_173` | how often request account statement 对应 account.frequency 列，pred 却去数 trans 中 k_symbol='SLUZBY' 的条数；第二问子查询漏了按账户分组返回 None |
| `bird_352` | 卡片语言应查 foreign_data，pred 查了 set_translations；且照 hint 字面 SUM(id) 把 id 值相加得 6010 |
| `bird_465` | 问的是 the set 有无韩文版，应查 set_translations，pred 查了单卡的 foreign_data |
| `bird_92` | 问 no. of districts，需 COUNT(DISTINCT district_id)，pred 漏了 DISTINCT 得 2009。注：此题正是后处理去 DISTINCT 规则的 14% 反例，会被本规则改坏 |
| `bird_959` | hint 已用时间格式定义 champion 为每场冠军，pred 却理解为赛季总冠军 |
| `bird_1498` | 问「最高的月度消费」，模型用 `MAX(Consumption)` 取单条记录最大值，未按月聚合（先前审计） |
| `bird_95` | 「最年轻且平均工资最高」，模型用 `= MAX(...)` 的合取条件导致空集（先前审计） |
| `bird_1175` | JOIN 条件多加一个日期相等约束，导致结果集为空（先前审计） |

可归纳的只有两条：**聚合粒度**（`bird_1472`、`bird_1498` 都是该按实体聚合却取了单条记录最大值）
和 **schema 消歧**（`bird_352`、`bird_465` 都是在 `foreign_data` 与 `set_translations` 之间选错）。
其余各不相同，不构成可针对性优化的模式。

## 对后续工作的意义

1. **约定后处理仍是唯一验证有效的加分手段**，但可挖空间比预期小：本轮识别出的可机械改写候选（纯格式、纯列序）合计约 5 题，且列序规则风险高。
2. **`bird_92` 是去 DISTINCT 规则的反例**，本轮确认其 gold 确实需要 `COUNT(DISTINCT)`。该规则 89.10% 的 train 支持度意味着约 11% 的题会被改坏，净收益 +5 已包含这一代价。
3. **不要再投入针对「模型推理能力」的机制**。10 题的总盘子里没有可归纳的共性，而四种 Prompt 机制已分别证明无效。
4. **Hint 矛盾类（14 题）值得单独立项**，它是继 gold 缺陷之后第二大的基准质量问题，且先前完全被低估（6% → 12.2%）。

## 完整逐题判定

### 模型真实错误（本轮 7 题）

| 题目 | 库 | 判定依据 |
|---|---|---|
| `bird_1265` | thrombosis_prediction | hint 说 '-' means 'negative'、'+-' refers to '0'，库中实际存 negative/0；pred 却按字面用 IN ('-','+-') 得 0 行且未察觉 |
| `bird_1472` | debit_card_specializing | least consumption in 2012 应按客户对全年求和后取最小，pred 取了单月消费最小的那一行 |
| `bird_173` | financial | how often request account statement 对应 account.frequency 列，pred 却去数 trans 中 k_symbol='SLUZBY' 的条数；第二问子查询漏了按账户分组返回 None |
| `bird_352` | card_games | 卡片语言应查 foreign_data，pred 查了 set_translations；且照 hint 字面 SUM(id) 把 id 值相加得 6010 |
| `bird_465` | card_games | 问的是 the set 有无韩文版，应查 set_translations，pred 查了单卡的 foreign_data |
| `bird_92` | financial | 问 no. of districts，需 COUNT(DISTINCT district_id)，pred 漏了 DISTINCT 得 2009。注：此题正是后处理去 DISTINCT 规则的 14% 反例，会被本规则改坏 |
| `bird_959` | formula_1 | hint 已用时间格式定义 champion 为每场冠军，pred 却理解为赛季总冠军 |

### gold 缺陷（本轮 34 题）

| 题目 | 库 | 判定依据 |
|---|---|---|
| `bird_1092` | european_football_2 | 问 the league(单数)，gold 返回并列 4 个联赛；其 HAVING 子查询未分组，MAX 取的是总场次 |
| `bird_1094` | european_football_2 | 问两名球员的 overall rating 之差，gold 把两人全部历史评分行求和后相减 |
| `bird_1107` | european_football_2 | 问 the first time，pred 取最早日期 2013-02-15；gold 外层 ORDER BY date DESC 取最晚日期，且该排序完全覆盖了内层按 crossing 的排序 |
| `bird_115` | financial | A4(人口数)是文本列，gold 直接 ORDER BY A4 DESC 做字符串排序；pred 先 CAST 为整数 |
| `bird_1241` | thrombosis_prediction | 问 number of patients，gold 对 Laboratory 化验记录计数而非患者去重计数 |
| `bird_1247` | thrombosis_prediction | gold 的 WHERE 存在 AND/OR 优先级 bug：FG<=150 OR (FG>=450 AND WBC.. AND SEX..)，第一个析取项不受任何其他条件约束；pred 正确加了括号 |
| `bird_125` | financial | 问题明确要求 list the district and the state，gold 只返回百分比一列 |
| `bird_1251` | thrombosis_prediction | gold 多连一张 Examination 表，把答案从 136 压到 9；问题只问 IgG 超标的患者数，该 JOIN 无依据 |
| `bird_129` | financial | 问 top ten withdrawals，gold 是 ORDER BY A2 ASC 取字母序前十，完全未实现按取款额排序 |
| `bird_1322` | student_club | 问 how many are meetings，gold 用 EXCEPT 取的是非 Meeting 事件，且返回名称列表而非计数 |
| `bird_1481` | debit_card_specializing | gold 三个分段共用同一分母 COUNT(CustomerID)，且未过滤 2013、未过滤 CZK、未取 least consumption 客户 |
| `bird_1531` | debit_card_specializing | hint 明写 average = Total(price)/Total(amount)，gold 却写 SUM(Price/Amount)，与自身 hint 矛盾；top spender 取表也不同 |
| `bird_186` | financial | gold 额外强加 client.district_id = account.district_id 的同区约束，问题未要求 |
| `bird_231` | toxicology | 问题要求 state whether carcinogenic，gold 只返回 bond_type，漏答第二问 |
| `bird_234` | toxicology | gold 用 '_1'/'_2' 而非 hint 指定的 '_12'，且 AND/OR 优先级 bug 使分子过滤对第二个析取项失效，答案 1041 明显失真 |
| `bird_281` | toxicology | 问题说 Tally(计数)，gold 只 DISTINCT element 不给计数 |
| `bird_37` | california_schools | gold 未排除 NumTstTakr=0，除零行排在最前导致选错学校；列序也与题干 Street,City,Zip,State 不符 |
| `bird_402` | card_games | 问题要求 List them by their ID，gold 只返回百分比 |
| `bird_518` | card_games | gold SQL 执行超时 30 秒，gold_answer 为 None，该题实际不可评分 |
| `bird_529` | card_games | gold 把 language='Korean' 与 language NOT LIKE '%Japanese%' 写在同一行上，后者恒真，等于没实现'没有日文版'的要求 |
| `bird_595` | codebase_community | gold 用 COUNT(DISTINCT PostHistoryTypeId)=1 并不表达'每帖只有一条历史'；且 hint 说 Views>=1000 指 users.Views，gold 用了 posts.ViewCount |
| `bird_637` | codebase_community | gold 经 postHistory 连接产生 5 条重复 '<books>'；pred 已拆分标签串 |
| `bird_639` | codebase_community | gold 用 tags.ExcerptPostId = postHistory.PostId 关联，这不是'带 r 标签的帖子'；pred 另漏乘 100 |
| `bird_640` | codebase_community | gold 经 postHistory 连接使同一帖子的 ViewCount 按历史条数重复累加 |
| `bird_682` | codebase_community | 问 post 的 id，gold 返回 OwnerUserId；且年份过滤加在 users.CreationDate 而非帖子上 |
| `bird_694` | codebase_community | 问最新 10 条评论及留言者，gold 按 users.CreationDate 排序（而非评论时间）且关联 posts.OwnerUserId（帖主而非留言者） |
| `bird_710` | codebase_community | 题问 the comments have 0 score，gold 过滤的是帖子的 Score 而非评论的 Score |
| `bird_83` | california_schools | 题目三问，gold 只答一问；另 pred 用 GSserved、gold 用 GSoffered |
| `bird_847` | formula_1 | gold 的 ORDER BY q2 ASC 未排除 NULL，SQLite 升序把 NULL 排在最前，选中 q2 为空的车手 |
| `bird_944` | formula_1 | gold 自身返回 [None]，pred 返回空集，该题无有效基准 |
| `bird_951` | formula_1 | 问 how many constructors，gold 返回的是某个 constructor 的 raceId 计数 2，答非所问 |
| `bird_955` | formula_1 | 25 行数值与 pred 仅在小数位不同，源于 gold 的毫秒 SUBSTR 解析口径 |
| `bird_963` | formula_1 | pred 用 milliseconds<120000，gold 用 SUBSTR 解析时间串，仅 3 行差异，源于 gold 的毫秒截取口径 |
| `bird_967` | formula_1 | 问题要求 State code numbers，gold 只返回计数，漏答第一问 |

### Hint 与 gold 矛盾（本轮 12 题）

| 题目 | 库 | 判定依据 |
|---|---|---|
| `bird_1179` | thrombosis_prediction | hint 明写 anti-Cardiolipin refers to aCL IgM，gold 返回 IgA/IgG/IgM 三列。pred 严格照 hint |
| `bird_1225` | thrombosis_prediction | hint 明写 List refers to GROUP_CONCAT(DISTINCT ID)，pred 照做，gold 却逐行返回 |
| `bird_1239` | thrombosis_prediction | 题干 two or more 即 >=2，hint 写 COUNT(ID) > 2，pred 照 hint 用 >2，gold 照题干用 >=2 |
| `bird_1242` | thrombosis_prediction | hint 明写年龄按 current_timestamp 计算，pred 照做得 5 人；gold 按化验当年(1984)计算年龄得 76 人 |
| `bird_1254` | thrombosis_prediction | hint 明写 YEAR(First Date) >= 1990，pred 照做；gold 用 strftime > '1990' 实为 >=1991 |
| `bird_197` | toxicology | hint 明写 average = AVG(element='o')，pred 照做得 0.081；gold 另算每分子氧原子数均值，且 bond 连接产生笛卡尔放大得 99.68 |
| `bird_198` | toxicology | hint 明写 average = DIVIDE(SUM(bond_type='-'), COUNT(atom_id))，pred 照做得 0.83；gold 另算每分子单键数均值得 732 |
| `bird_247` | toxicology | hint 明写 atom_id NOT in connected，pred 照做；gold 改为排除'出现过成键的元素种类'，是另一个问题。pred 另漏 DISTINCT |
| `bird_371` | card_games | hint 分母为 Count(id) where isStorySpotlight=1（全部该类卡），pred 用 LEFT JOIN 保留全部；gold 用 INNER JOIN 只算有译文的卡 |
| `bird_474` | card_games | hint 自身矛盾：文字说 under 100 却写 baseSetSize < 10；pred 照 hint 用 <10 得 0，gold 照题干用 <100 |
| `bird_486` | card_games | hint 分母字面为 SUM(convertedManaCost)，pred 照做；gold 用 COUNT(id) |
| `bird_604` | codebase_community | hint 明写 average age = Divide(Sum(Age), Count(UserId))，pred 照做（含 Age 为空的用户）；gold 用 AVG 自动跳过空值。UpVotes 一列两者完全相同 |

### 输出约定未指定（本轮 14 题）

| 题目 | 库 | 判定依据 |
|---|---|---|
| `bird_1011` | formula_1 | gold 额外返回 lap time 列；pred 用 || 拼接姓名（别名被 ORDER BY 引用，改写规则正确拒绝）。排序口径亦不同，待复核 |
| `bird_1014` | formula_1 | 问题说 circuits(复数)，pred 返回 3 个赛道各自记录；gold 收缩为单值。pred 首值与 gold 唯一值相同 |
| `bird_1144` | european_football_2 | 问 finishing 与 curve 两项，gold 额外返回 id；两项数值完全一致 |
| `bird_1205` | thrombosis_prediction | 针对单个患者的是非题，pred 返回单行 Yes，gold 逐条化验记录返回 67 行 0；另 hint 把 UA>8.0 说成 within normal range 本身有误 |
| `bird_1235` | thrombosis_prediction | 73 行数值完全相同，仅列序不同；题干先问 diagnosis，gold 列序与题干一致 |
| `bird_215` | toxicology | gold 拆成 iodine/sulfur 两列，pred 合并计数；另 pred 经 molecule 关联、gold 经 connected 精确关联 |
| `bird_228` | toxicology | 数值完全相同(45.4545)，pred 经 printf 返回字符串，gold 返回浮点数，纯类型差异 |
| `bird_469` | card_games | 是非题，pred 返回单行 Yes，gold 逐匹配行返回 15 个 YES；另有大小写差异 |
| `bird_50` | california_schools | 同样两个值，pred 列序 (校名, 地址)，gold 列序 (地址, 校名)，纯列序差异 |
| `bird_530` | card_games | 未命中禁卡时 pred 返回 None、gold 返回字符串 'NO'；且 pred LEFT JOIN、gold INNER JOIN legalities 决定了不同行集 |
| `bird_72` | california_schools | 问 how many students(单一数值)，pred 求和得 375，gold 返回未聚合的两行 40/335 |
| `bird_728` | superhero | gold 多返回 RANK() 列，问题未要求显式名次；前两列数值完全一致 |
| `bird_85` | california_schools | 两值完全相同，仅列序相反；题干先问百分比后问 district code，gold 列序与题干一致 |
| `bird_87` | california_schools | 同样两个邮箱，pred 两行一列、gold 一行两列，纯形状差异 |

### 指代歧义（本轮 14 题）

| 题目 | 库 | 判定依据 |
|---|---|---|
| `bird_1243` | thrombosis_prediction | 百分比分母：pred 取 PT>=14 的行，gold 取全部 55 岁以上行（其 COUNT(CASE..ELSE 0) 恰好等于全部行） |
| `bird_145` | financial | account holder identification numbers 可指 client_id(pred) 或 account_id(gold)；且均值口径一个限信用卡交易一个全年交易 |
| `bird_1529` | debit_card_specializing | spent 取 Price(gold) 还是 Amount*Price(pred)；January 花费取 yearmonth.Consumption(pred) 还是交易 Price(gold) |
| `bird_25` | california_schools | 校名取 schools.School(pred，全为 NULL) 还是 satscores.sname(gold)；Riverside 取 County(pred) 还是 District Name(gold) |
| `bird_408` | card_games | hint 只说 text contains，cards.text(pred) 与 rulings.text(gold) 都存在 |
| `bird_533` | codebase_community | after 2014/9/1 的边界：pred 直接比较日期时间串，gold 先 date() 截断，二者仅在 9 月 1 日当天不同 |
| `bird_587` | codebase_community | average view count of each post 可理解为整体均值(pred)或按帖分组均值(gold)；标签匹配 LIKE(pred) vs 精确等于(gold) |
| `bird_685` | codebase_community | 最后发帖/编辑的用户：pred 取 postHistory 最新一条的 UserId，gold 取 posts.LastEditorUserId；ViewCount 一列相同 |
| `bird_896` | formula_1 | position 取 results(单场名次) 还是 driverStandings(积分榜名次)，题干英文本身残缺 |
| `bird_897` | formula_1 | the most winning：pred 取单赛季最大 wins，gold 取 wins>=1 的记录条数，hint 的 MAX(COUNT(wins)) 两读皆通 |
| `bird_902` | formula_1 | 同上 results vs driverStandings，结果集有 4 条重合 |
| `bird_906` | formula_1 | 同上；赛事名一致，仅积分 8 vs 14 因取表不同 |
| `bird_928` | formula_1 | ranked the first：pred 取 results.position=1，gold 取 results.rank=1，两列都存在且都讲得通 |
| `bird_937` | formula_1 | ranked second：pred 取 results.position=2，gold 取 results.rank=2，同 bird_928 |

### 标注约定残留（改写规则不适用）（本轮 2 题）

| 题目 | 库 | 判定依据 |
|---|---|---|
| `bird_1135` | european_football_2 | 最值写法：pred 用 potential = (SELECT MIN(potential)) 只得 1 行，gold 用 ORDER BY potential ASC LIMIT 4 |
| `bird_671` | codebase_community | 最值写法：pred 用 Date = (SELECT MIN(Date)) 返回 12 个并列，gold 用 ORDER BY Date LIMIT 1 |

