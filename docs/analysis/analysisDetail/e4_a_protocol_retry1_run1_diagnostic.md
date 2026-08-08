# E4-A protocol retry1 run1 诊断

运行：`results/e4_a_protocol_retry1_run1.json`；轨迹：`trace/e4_a_protocol_retry1_run1/`；题目：`bird_1031`。

## 结论

严格协议审计返回 `passed=true`：只有一个合法初始 QueryPlan、一个结构化执行、正常 FINAL，且没有协议事件失败。它与 smoke4 run3 另外三题的直接通过记录一起证明 schema-v3 的 block/执行协议能够完成。

但本次同时暴露了一个类型校验漏洞：计划把 `limit` 写成 `[]`，旧解析器仍接受；adherence 将任何非 `null` limit 解释为必须出现 `LIMIT`，因此唯一失败检查为 `limit_presence=false`。这不是问题语义导致的差异，而是 QueryPlan schema 对 `limit` 缺少 `null | positive integer` 约束。

代码现已补充该类型约束和测试，Prompt 也明确 `limit` 不是数组。因为配置哈希已经改变，必须使用新的 retry run2 路径验证，不能复用本次 trace。

## 语义与控制流

- 初始计划正确保持 `answer_scope=per_entity_rows`、`aggregation_scope=none`，没有恢复 run2 的错误全局 AVG；
- 执行 SQL 返回重复年龄；FINAL 加入 `DISTINCT` 子查询，但没有重新执行，因此外层标签为 `UNVERIFIED_FINAL`；
- 该标签只表示 FINAL 控制流，不改变底层语义仍需与 gold 人工复核的结论；
- E4-A 不启用 E1 的 strict verified-final，否则会同时改变第二个机制并破坏消融边界。

本题使用 19,907 tokens、2 次 LLM call，准确率 0/1。单题准确率不作为 E4-A 效果判断。
