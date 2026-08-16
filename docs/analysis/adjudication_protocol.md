# 失败逐题判读：方法、标准与进度（2026-08-16）

## 为什么必须人工判读

机械方法已被写法差异**三次**欺骗，每次都产生过错误结论：

| 方法 | 失效形式 | 规模 |
|---|---|---|
| 分层比对 SQL | 别名 `T1.Currency` vs `Currency`、`SUBSTR(d,1,4)` vs `STRFTIME('%Y',d)` 被当成差异 | WHERE 层 **42%** 是假差异 |
| JOIN 键比对 | 模型用 `IN`/`EXISTS`、gold 用 `JOIN` 时指标失效，报"无差异"把真差异漏到下游 | JOIN 层 **16/24** 判定无效 |
| 用 `predicted_sql` 做归因 | 它是 harness 改写**之后**的 SQL，把去 DISTINCT 的选择记成模型的选择 | 计数口径方向判反 |

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
| `待定` | 需查数据才能定 |

**重要**：`不可评分` 和 `基础设施` 两类应从准确率分母中剔除。已确认 9 道，
分母 500 → 491，准确率 67.40% → **68.64%**。

## 进度

- 总失败 163 道
- 机械判定已定责 30 道（gold 多给列 12、题面歧义 10、评测口径 4、模型多返回行 4）
- **人工逐题判读已完成 33 道**（`manual_adjudication.json`）
- **剩余待判读约 101 道**

## 已判读 33 道的分布

| 判定 | 题数 |
|---|---:|
| **gold** | **16** |
| 模型 | 4 |
| 题面歧义 | 3 |
| 待定 | 3 |
| 基础设施 | 2 |
| 不可评分 | 2 |
| 评测口径 | 1 |
| 题面/schema 缺失 | 1 |
| 双方 | 1 |

**gold : 模型 = 16 : 4。** 该比值在 33 道上稳定，但样本尚未覆盖全部，
**不得外推至 163 道全体**。

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
```

判读时必须使用 `sql_convention_rewrite.original_sql`（若存在）作为模型 SQL，
而非 `predicted_sql`。
