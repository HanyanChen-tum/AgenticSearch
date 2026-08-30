# 工具循环为什么会死，以及修好它（2026-08-30）

承接 [`reasoning_cost_2026-08-28.md`](reasoning_cost_2026-08-28.md) §四。那篇只查到
"11 个运行的工具循环是死的"并把它当成外部事实记下，**这一步是不够的**：
症状描述完了没有修，而该修的东西在我们这边。本文补上根因与修复。

---

## 一、先排除三个错误猜想

### 1.1 不是换模型、不是换 effort

死掉的运行里有和健康期**配置完全相同**的：

| 日期 | 运行 | 模型 | effort | profile | `exec/q` |
|---|---|---|---|---|---:|
| 08-17 | `chain_e3_c_conv_rules_corrected_run1` | mini | high | `e3-c-conv-rules` | **1.29** |
| 08-18 | `chain_e3_c_conv_rules_corrected_run2` | mini | high | `e3-c-conv-rules` | 1.24 |
| 08-28 | `modelcmp_mini_run1` | mini | high | `e3-c-conv-rules` | **0.00** |
| 08-30 | `loopcheck_0830_mini` | mini | high | `e3-c-conv-rules` | **0.00** |

同模型、同 effort、同 profile，08-17 活、08-28 死。`gpt-5.4` 是 08-28 才第一次跑，
不可能是原因；08-20/21 死的那批全是 mini，且横跨 high/low/medium/minimal 四档。

### 1.2 不是我们把 prompt 改坏了

对 `bird_100` 逐字节比对健康运行与失效运行**实际发出的消息**：

| | system | 第一条 user |
|---|---|---|
| `chain_e3_c_conv_rules_corrected_run1`（08-17，活） | sha `cdb54d8211898e78`，1238 字节 | sha `69687c98cabdf4ae`，5861 字节 |
| `modelcmp_mini_run1`（08-28，死） | sha `cdb54d8211898e78`，1238 字节 | sha `69687c98cabdf4ae`，5861 字节 |

**完全相同。** 输入端不存在可回滚的回归。

### 1.3 不是新毛病，是老毛病失控

根因写在本仓库自己的代码注释里。`ours/agent/config.py` 中
`e3-c-conv-rules-toolconfirm` 的说明记载：08-17 那次运行，读取全部 496 道题的
推理记录，**模型在 113 道（22.8%）里认定自己无法执行、或看不到结果**，
该组得分 57.5%，其余 70.0%。

也就是说"模型不相信工具是真的"这个现象，**在健康期就已经占 22.8%**。
现在只是涨到了约 75%。不是冒出新故障，是同一个失效模式恶化。
这也解释了为什么 toolconfirm 那句"这些调用真的会执行"能一击见效。

---

## 二、三个症状，一个病根：我们的解析太脆

模型的输出格式变了，这是外部事实；**而我们的循环对每一种变化都零容错，
并且失败时静默降级成单次生成器——这是我们的缺陷。**

| 症状 | 模型做了什么 | 判定 |
|---|---|---|
| 第一轮直接 `FINAL()` | 认定工具用不了 | 模型信念，prompt 可解 |
| 输出裸 SQL，无围栏 | 少写了 ```` ```python ```` | **我们解析太窄** |
| `db.execute("...")` 里 SQL 跨行 | 写了**完全正确**的调用 | **我们的 bug** |

第三个最能说明问题。模型写的是：

```python
print(db.execute("SELECT T.team_long_name
FROM Match AS M
INNER JOIN League AS L ON M.league_id = L.id
..."))
```

逻辑毫无问题——但 Python 的 `"..."` 字面量不能含换行，于是
`SyntaxError: unterminated string literal`，查询一次也没跑。
**多行写 SQL 是常识，是我们的 REPL 不接受。**

历史频次：08-18 之前每轮 0~1 次，今天 16 题里 3 次。所以它不是长期损耗，
而是同一次格式漂移的第三面。

---

## 三、修复

### 3.1 埋点：记录服务端真正返回的模型版本

`src/rlm/core.py` 与 `ours/recursive_db_rlm.py` 的 `_record_llm_call` 增加
`served_model` 字段。此前 trace 只记我们**请求时写的**模型名，而部署名在底层
版本更换时是不变的——所以"行为变化是不是伴随模型版本更换"这个问题，
**对 08-30 之前的所有运行已永久无法回溯**。实测现在记录到
`gpt-5.4-mini-2026-03-17`。纯观测，不改预测。

### 3.2 输入恢复：`repl_input_recovery`

`_recover_repl_input` = `_recover_bare_sql` + `_recover_multiline_execute`，
与既有的 `_convert_sql_blocks`（把 ```` ```sql ```` 转成 `db.execute()`）同一条思路：
**把模型明显想表达的东西变成可执行的，其余原样返回。**

刻意写窄，因为它改写模型的输出：

- 裸 SQL：仅当整条响应是单个 `SELECT`/`WITH`、无任何围栏、不含 `FINAL(` 时才包装
- 多行：仅当 `db.execute()` 的参数含换行时提升为三引号；参数内不得含自身定界符，
  以免匹配跨到后面另一个调用的引号

按仓库规矩（"任何能改变预测的东西都必须可消融"）做成 `AgentConfig` 开关，
**默认 `False`，所有既有 profile 行为不变**；新 profile `e3-c-conv-rules-liveloop`
同时打开它与 toolconfirm prompt。命中写 `repl_input.recovered` 事件进 trace。

`tests/test_agent_profiles.py` 新增 9 个用例，含用 `compile()` 真正验证
三引号提升后的代码可编译、两个 `db.execute` 不会跨引号粘连、
以及老 profile 的开关必须为关。

---

## 四、效果（16 题冒烟，high）

| mini 配置 | `exec/q` | `py/q` | 裸 SQL | REPL 报错 | 一轮率 |
|---|---:|---:|---:|---:|---:|
| `e3-c-conv-rules`（坏） | 0.00 | 0.00 | 5 | 5 | 75% |
| `+toolconfirm` | 0.19 | 0.19 | 5 | 5 | 12% |
| `+`裸 SQL 恢复 | 0.25 | 0.44 | 0 | 3 | 31% |
| **`liveloop`（完整）** | **0.81** | **0.81** | **0** | **0** | **12%** |

`gpt-5.4` 单靠 toolconfirm 就已恢复（`exec/q` 0.94、`py/q` 1.00、裸 SQL 0、
一轮率 6%）——**两个模型坏的方式不同**：normal 是"不肯查"，mini 是
"不肯查 + 不会写"，所以两个修复缺一不可。

准确率在 16 题上全是 14/16，**n 太小，不作任何解读**。

---

## 五、这对已有结论意味着什么

1. **`reasoning_cost_2026-08-28.md` §四 的作废清单依然成立**，但结论要改写：
   那不是"模型漂移了、无能为力"，而是**我们的 harness 缺少格式容错**。
   11 个运行仍然作废，原因换成一句可执行的：它们跑在没有 `repl_input_recovery`
   的代码上。
2. **`model_ceiling_2x2_2026-08-28.md` 的四格仍是单次生成器**，结论
   （"天花板不是模型能力"）在那个层面成立。现在循环可以活了，
   **这个 2×2 值得用 `e3-c-conv-rules-liveloop` 重跑一遍**，
   把论断从"作为单次生成器"升级到"作为真正会探索的 agent"。
3. **`e3-c-conv-rules-liveloop` 一次动了两个变量**（prompt + 恢复开关），
   它的用途是"让循环活起来以便测模型"，**本身不是任何东西的对照组**。
   要归因就把两个开关分别消融。

---

## 六、附：三个既有测试失败

`tests/test_agent_profiles.py` 中 `SqlConventionRewriteTests` 的三个用例
（`count_distinct` / `superlative` / `convention rewrite`）在**本轮改动之前
就是红的**——已 stash 全部改动在 HEAD 上复验。与本文修复无关，未改动。
