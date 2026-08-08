# FINAL 前未核实字面量警告：机制实现与 N=8 Smoke 结果（2026-08-07）

## 机制实现

源自 F-Audit（`filter_audit.md`）发现的具体模式：7 道确认的真实 Agent 错误里，多道涉及"把 Hint 里的字面量/编码值直接照抄进 SQL，没有用 `db.sample_values` 核实过实际存储格式"（`bird_1267`、`bird_1265`、`bird_1350`）。这不是 E1 已被拒绝的"强制 verified-final"（那个是无差别拦截所有 FINAL，成本翻倍且无收益）；这是一个窄得多、纯软提示、不涉及重新执行的机制：

- **实现位置**：`ours/agent/state.py`（`find_unverified_literal_columns`、`AgentExecutionState.record_sample_values`/`unverified_literal_warning`）+ `ours/recursive_db_rlm.py`（在 `db.sample_values` 事件里记录已核实列；在每次 `db.execute` 后，若刚执行的 SQL 包含"某列 = 字符串字面量"或"某列 IN ('a','b',...)"、且该列此前未被 `sample_values` 核实过，追加一条 WARNING，每列每条 trace 只提醒一次，从不阻断）。
- **新 profile**：`e3-c-literal-check`，与 `e3-c` 唯一差异是 `literal_verification_nudge=True`（测试见 `tests/test_agent_profiles.py` 的 `test_literal_check_profile_only_adds_the_nudge_flag_to_e3_c`）。
- **测试**：`AgentExecutionStateTests` 新增 5 个单测（未核实触发/核实后静默/表别名按裸列名匹配/`IN` 列表触发但子查询不触发/每列每 trace 只提醒一次）+ `LiteralVerificationNudgeLoopTests` 2 个完整 loop 集成测试（含 fake LLM，验证 warning 真的出现在 transcript 里、开关关闭时不出现）。全部 91 个仓库测试通过。

机制一（近义表结构提醒）按讨论暂缓，留作 E5/E6 递归计划重启时再设计，本轮不实现。

## Smoke 范围与结果

8 题：F-Audit 定位的 2 道字面量目标题（`bird_1267`、`bird_1265`，均为 e3-c 基线下失败且明确是"取值字面量未核实"模式）+ 6 道 e3-c 基线下已经正确的对照题（防回归，覆盖 `thrombosis_prediction`/`student_club`/`codebase_community`）。

| ID | e3-c 基线 | +literal-check | 变化 |
|---|---|---|---|
| `bird_1267` | 错 | 错 | 无变化，但见下方细节 |
| `bird_1265` | 错 | 错 | 无变化，但见下方细节 |
| `bird_1350` | 对 | 对 | 无变化 |
| `bird_1171` | **对** | **错** | **回退** |
| `bird_598` | 对 | 对 | 无变化 |
| `bird_1155` | 对 | 对 | 无变化 |
| `bird_1169` | 对 | 对 | 无变化 |
| `bird_531` | 对 | 对 | 无变化 |

准确率 5/8=62.5%（基线在这 8 题上是 6/8=75%，因为两道目标题本来就是失败的，对照 6 题全对）。**净变化：0 恢复，1 回退，总分 -1**。

## 细节：机制确实按设计生效，但不足以让题目整体转对

- **`bird_1267`**：模型这次调用了 `db.sample_values("Laboratory","SM")`，返回 `['0','1','negative','2','8']`，最终 SQL 用 `SM IN ('negative','0')`——**和 gold 的取值完全一致**，机制在这道题上精确达成了设计目标。但仍然判错：模型这次的 SQL 多连了一张 `Patient` 表（`INNER JOIN Patient AS P ON P.ID = L.ID`），这是 Schema/Join 层面的问题（不必要的额外 JOIN 改变了 COUNT 语义），和字面量无关，是另一个未被此机制覆盖的 bug。
- **`bird_1265`**：模型调用了 `db.sample_values("Laboratory","RNP")`，但真实返回是 `['0','1','256','negative','16','64','4','15']`——这张表的 RNP 列实际上混合了数值型滴度值和文本标签，比 Hint 暗示的"就是 -/+-两种编码"复杂得多。模型看到这个真实分布后选择把 `'-'、'+-'、'negative'、'0'` 全部塞进 `IN` 列表（合理的不确定性应对），但仍未命中。另外这道题的 gold SQL 本身有 F-Audit 已确认的 AND/OR 优先级 bug，"正确答案"本身存疑。
- **`bird_1171`（唯一回退）**：基线版本的年龄计算是 `strftime(Examination Date) - strftime(Birthday) < 18`（正确减法）；加了警告机制后，模型这次写成了 `strftime(Birthday) < 18`（直接拿出生年份和18比较，漏掉减法）——这是 F-Audit 里 `bird_1171` 原本记录的那个经典 bug 的复现，且这道题完全不涉及字符串字面量，警告机制没有理由影响这道题的逻辑。目前只能归为提示文本改变了上下文长度/结构后，模型在无关问题上的输出发生了漂移，样本量太小无法判断是偶然波动还是系统性副作用。

## 结论

**这次 smoke 不支持"机制有效"的结论**：0 道目标题被完全修复（其中 1 道的字面量子问题被精确解决，但暴露了另一个独立 bug）；1 道回退且回退原因与本机制的设计意图无关。N=8 太小，任何方向的结论都只能算趋势，但至少可以说：**没有观察到预期的净收益，出现了 1 个无法用机制本身解释的回退**。

按项目一贯的判定标准（净变化方向不明确、样本太小不能外推），当前不满足"接受"条件，也不足以直接"拒绝"——需要更大样本才能分辨这个回退是噪声还是真实副作用。

## 下一步建议

1. **不要现在就下结论**（正面或负面都不行）。样本量是唯一的硬约束，不是机制方向本身的问题——机制在 `bird_1267` 上展示了明确按设计工作的证据。
2. 如果要继续验证，应该扩大到 F-Audit 全部 7 道"确认为真实 Agent 错误"的题（尤其是 `bird_598`、`bird_1350` 这类日期/枚举字面量模式），加上更大的回归对照集（至少 20-30 题，覆盖更多数据库），才能把 `bird_1171` 这类回退和噪声区分开。
3. `bird_1267`残留的"额外JOIN"问题和`bird_1265`的"gold本身有精度bug"提醒：字面量核实只解决了F-Audit发现的一部分根因，Schema/Join层面的过度连接问题（`schema_join_diagnosis_2026-08-07.md`里的"防御性过Join"模式）依然独立存在，两个问题可能需要分开针对。
