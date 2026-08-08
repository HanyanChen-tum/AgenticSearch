# E4-A smoke4 run1 协议诊断

> 结论：该运行未通过协议门禁，不能用于判断 E4-A 的准确率或拒绝 QueryPlan。`0/4` 中有 2 题因协议实现导致 `MaxIterationsError`，只有 2 题真正完成 FINAL。

## 结果

| ID | 终止 | 结果 | 诊断 |
|---|---|---|---|
| `bird_1011` | `MaxIterationsError` | 无 SQL | 初始 plan 已接受，但 plan block 清理破坏了相邻 Python opener，未产生 observation；后续 revision 被连续阻塞 |
| `bird_1166` | `MaxIterationsError` | 无 SQL | 模型输出多个 Python block，并把 observation ref 写成数字字符串；过严 action/ref 校验耗尽 8 轮 |
| `bird_1031` | `final` | 错误 | plan、执行和 adherence 正常；最终仍为聚合语义错误 |
| `bird_1251` | `final` | 错误 | plan、执行和 adherence 正常；最终仍为 Schema/Join 错误 |

门禁为 `passed=false`。run1 暴露的是两个不同层面：

1. **协议实现错误**：删除 plan block 时不应破坏 Python fence；审计器应从 final attempt 读取 `query_plan_state`。
2. **协议过严**：不能因为一条响应包含多个 Python block 就丢弃全部动作；数字字符串 observation ref 应规范化为整数。

## 修复

- QueryPlan 协议 manifest 升级为 version 2，确保 run1 与修复后运行配置哈希不同。
- 不再在交给 REPL 前删除 plan block；REPL 直接提取并执行 Python block。
- 执行全部 Python block，连续完全重复的 block 去重，不再静默丢弃或整体阻塞。
- 接受整数和纯数字字符串 observation ref，仍要求它等于最新结构化 observation sequence。
- BLOCKED 消息明确指出下一步需要 `queryplan` 还是 `plan-revision` 以及准确 observation ref。
- 顶层 trace 转发 `query_plan_state`；smoke auditor 同时支持 attempt 层状态。

修复后使用 run1 的四条真实首轮响应做离线重放，四题均成功接受 initial plan，并各产生 1 个结构化 `db.execute`。75 个单元/集成测试通过。

## 决策

run1 作为失败的协议 smoke 保留，不续跑、不合并、不计算 E4-A 机制收益。下一步使用新路径运行 `e4_a_smoke4_run2`；只有 version 2 门禁输出 `passed=true` 才启动 core197。
