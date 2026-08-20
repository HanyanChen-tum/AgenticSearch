# 失败逐题判读：方法、标准与进度（2026-08-16）

## 为什么必须人工判读

机械方法已被写法差异**四次**欺骗，每次都产生过错误结论：

| 方法 | 失效形式 | 规模 |
|---|---|---|
| 分层比对 SQL | 别名 `T1.Currency` vs `Currency`、`SUBSTR(d,1,4)` vs `STRFTIME('%Y',d)` 被当成差异 | WHERE 层 **42%** 是假差异 |
| JOIN 键比对 | 模型用 `IN`/`EXISTS`、gold 用 `JOIN` 时指标失效，报"无差异"把真差异漏到下游 | JOIN 层 **16/24** 判定无效 |
| 用 `predicted_sql` 做归因 | 它是 后处理改写**之后**的 SQL，把去 DISTINCT 的选择记成模型的选择 | 计数口径方向判反 |
| 答案级子集/超集规则 | "模型结果是 gold 真子集 → 单复数歧义"、"真超集 → 模型多返回行"**带方向假设**；实际常是 gold 逐行输出 NULL、或 gold 只取 LIMIT 1 | 落入该两条的 **6/11 判反** |

**结论：SQL 结构比较不足以判定责任，必须读题面 + 两条 SQL + 执行结果。**

## 判读标准

对每道失败题，读【题面】【hint】【模型 SQL】【gold SQL】【双方执行结果】，判定为下列之一：

| 判定 | 标准 |
|---|---|
| `gold` | gold 逻辑有 bug、多返回题面未要求的列、违背自己的 hint、因 JOIN 重复放大聚合、答非所问 |
| `模型` | 模型误读 hint、算错公式、用错列、遗漏题面明确要求的条件 |
| `题面歧义` | 题面单复数未定、未指明取哪张表的同名列、未指定输出粒度 |
| `题面/schema缺失` | 题目问了数据库里不存在的属性 |
| `评测口径` | 取值完全相同，仅类型（字符串 vs 数值）、列序、拼接与否不同 |
| `不可评分` | gold 自身执行失败或返回全 NULL——任何模型都不可能答对 |
| `基础设施` | 模型 SQL 未产出结果（执行失败/超时），与语义无关 |
| `双方` | 两边各有独立问题 |
| `后处理改写` | 模型改写**前**的原始 SQL 本可判对，是 `sql_convention_rewrite` 改错的（2026-08-16 新增第 10 类，6 道，涉 count_no_distinct 与 no_select_concat 两条规则） |
| `待定` | 需查数据才能定（已归零） |

**冲突时以题面为准**：gold 答对题面而 hint 公式有缺陷、模型照抄 hint 出错 → 记 `模型` 并加
`[hint缺陷]` 标记（9 道）；只有 gold 的答案本身背离题面才记 `gold`。此口径比
`error_origin_chain` 旧文档（"违背 hint 即算 gold 侧"）更严，故 gold 数为下界。

**基数**：`bird_dev_500.json` 有两道重复题（`bird_137`、`bird_138`），
唯一题数为 **498** 而非 500；两道重复题均答对，按 500 计会把准确率抬高 0.13pp。
报数请用 498 基数（外部审计工作亦按 498 计）。

**重要**：`不可评分` 和 `基础设施` 两类应从准确率分母中剔除，**共 5 道**
（不可评分 4 + 基础设施 1），分母 498 → 493，准确率 67.27% → **67.95%**。

判 `基础设施` 前**必须给模型 SQL 计时并对 gold 比对**：超时不等于与语义无关。
`bird_1490`(48.1s) 与 `bird_383`(357.5s) 的 SQL 语义都对，只是超出 30 秒预算，
已改判 `模型`——写出计算上不可行的查询是模型的问题，不该从分母剔除。

这两类**必须逐道打开 `error` 字段核实**，不能沿用机械判定的标签。首次机械判定给出 9 道，
其中 2 道贴错（`bird_1011` 实为 后处理改写、`bird_760` 是模型写了无效 SQL），
早前据此报出的 491 分母 / 68.64% 因而作废。

## 进度：已完成

163 道**全部定责**，其中 **150 道逐题人工判读**（`manual_adjudication.json`），
13 道停在**不含方向假设**的答案级规则上（取值完全相同 9、gold 不可评分 4）。

| 判定 | 题数 | 占失败 |
|---|---:|---:|
| **gold** | **61**（61/72 经修正 gold 执行验证） | 37.4% |
| 题面歧义 | 35（7 个子类型，见 `ambiguity_subtypes.json`） | 21.5% |
| **模型** | **30**（照抄缺陷 hint 9 + 纯推理错 21） | 18.4% |
| 双方 | 16 | 9.8% |
| 评测口径 | 9 | 5.5% |
| 后处理改写 | 6 | 3.7% |
| 不可评分 | 4 | 2.5% |
| 基础设施 | 1 | 0.6% |
| 题面/schema 缺失 | 1 | 0.6% |

**gold : 模型 = 61 : 30 ≈ 2.0 : 1**（严口径）。

**判为 `gold` 后必须做修正 gold 验证**：写一条忠于题面的修正 gold、执行、看模型是否随之判对
（`scripts/verify_gold_fix.py`）。首轮 72 道 gold 判定里 **11 道没通过**——2 道判反
（`bird_866`、`bird_247`，gold 其实无缺陷）、9 道是多因共同决定。
"gold 有缺陷"70/72 成立，"gold 缺陷即失分原因"只有 61/72 成立，两层不可混用。

> ⚠️ 2026-08-17：下面这段引用的 Arcwise 外部修正版**改写了 81 道题面**，与原题面不可比，数字待重算。

**但自写修正 gold 会朝模型拟合**——换成外部独立修正版（VLDB 2026 Arcwise-Plat-SQL，同一批
500 题）只有 34/61 仍判对。**优先用外部修正版，不要用自写的。**

⚠️ **绝不可由"gold 坏了 70 道"推出"真实准确率更高"。** 本判读只审计失败题，
看不见"gold 坏、模型恰好与坏 gold 一致"的送分题。外部修正版实测：送分 39、吃亏 38，
准确率 67.27% → **67.07%**，净额 −1。标注噪声在两个方向上对消。

**判定精度不均匀**：`verdict` 是责任归属而非机制。约 36 道到了机制级（跑过反证查询），
51 道止于差异描述，13 道仅机械规则。引用前先读
[`failure_adjudication_final_2026-08-16.md`](failure_adjudication_final_2026-08-16.md) §4.5。

完整结论、可外推与不可外推的边界见
[`failure_adjudication_final_2026-08-16.md`](failure_adjudication_final_2026-08-16.md)，
逐题归属见 `analysisDetail/final_responsibility_163.json`。

## 最有说服力的单条证据

`bird_1404` 与 `bird_1422` 同属 `student_club` 库、同涉 `event.type` 与 `budget.category` 两列：

- `bird_1404` 问"**expenses** 的类型"，gold 取 `event.type`
- `bird_1422` 问"**events** 的 category"，gold 取 `budget.category`

**两题的 gold 各自取了与题面相反的那一列。** 模型两次都按字面选择，两次都被判错。

## 复现命令

```bash
# 机械判定（答案优先，结构兜底）
python scripts/adjudicate_all_failures.py \
  --results results/e3_c_conv_rules_dev500_run1.json \
  --trace trace/e3_c_conv_rules_dev500_run1/transcripts.jsonl \
  --output docs/analysis/analysisDetail/adjudication_all_failures.json

# 全量根因（构造顺序定首因，注意上述失效条件）
python scripts/root_cause_every_failure.py --results ... --trace ... --output ...

# 修正 gold 验证：{"bird_xxx": "<忠于题面的修正gold SQL>"} -> PASS/FAIL
python scripts/verify_gold_fix.py <fixes.json>
```

判读时必须使用 `sql_convention_rewrite.original_sql`（若存在）作为模型 SQL，
而非 `predicted_sql`。
