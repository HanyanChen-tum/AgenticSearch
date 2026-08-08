# E4-A protocol retry1 run2 诊断

运行：`results/e4_a_protocol_retry1_run2.json`；轨迹：`trace/e4_a_protocol_retry1_run2/`；题目：`bird_1031`。

## 结论

最终 schema-v3 协议门禁通过，可以冻结 E4-A 配置并启动 core197：

- `audit_e4_a_smoke.py` 返回 `passed=true`；
- 一个合法初始 QueryPlan，`limit=null`，没有 protocol failure；
- 两次结构化 `db.execute` 均有对应 adherence，2 pass / 0 fail；
- 所有 projection、group/having/order/limit presence 和 required tables 检查均通过；
- 正常终止为 FINAL。

本题准确率仍为 0/1、`ever_correct=false`，但单题 smoke 不用于判断 E4-A 准确率。其作用是证明配置、计划解析、工具执行和 trace 管道可运行。正式有效性必须由固定 core197 的目标错误净变化、recovered/regressed 和成本决定。

## 保留的诊断现象

初始响应包含两个内容不同但执行同一 SQL 的 Python blocks，因此记录了两次相同执行。当前协议显式采用 `execute-all-dedupe-consecutive`：只去除内容完全相同的相邻 block，不静默丢弃不同 block。这里是冗余 DB 成本，不是语义或协议失败，正式分析应统计。

FINAL 将 `year >= 2013 AND year <= 2015` 改写为等价 `BETWEEN 2013 AND 2015`，但未重新执行，因此控制流标签仍为 `UNVERIFIED_FINAL`。E4-A 保持 `verified_final=false`，不重新引入已被 E1 拒绝的 strict verified-final，避免改变第二个实验变量。

该题使用 22,514 tokens、4 次 LLM call。初始计划继续保持 `answer_scope=per_entity_rows`、`aggregation_scope=none`，没有重新引入错误 AVG。
