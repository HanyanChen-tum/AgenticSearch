# 本周报告：从「修尺子」到「找到真正的瓶颈」（2026-08-18 ~ 08-24）

一句话概括：**这七天做完了两件事——把判分口径修干净（准确率 84.5% → 88.1%，
全是测量偏差不是能力提升），以及用四条互相独立的证据锁定了同一个瓶颈：
剩下的失败几乎全是语义与约定问题，方法栈和推理预算都碰不到它。**

---

## 零、七天的产出一览

| 日期 | 产出 | 性质 |
|---|---|---|
| 08-18/19 | 五层对照链跑完，八臂各两次 | 主结果 |
| 08-18 | 三个 harness 缺陷诊断 + 66 个运行配置逐字段核对 | 修尺子 |
| 08-20 | RLM 由「递归」更正为三机制；术语 harness 拆成三层 | 概念更正 |
| 08-20 | 四项历史消融在修正数据集上重跑 | 复核 |
| 08-21 | 拆开「其它」424 道失败；推理强度四档各跑两次 | 深化 |
| 08-23 | Phase A 首轮定位 29 道 + 漏斗固化；SQL 超时误判诊断 | 新方向 |
| 08-24 | 全仓回填 121 条超时误判；`final_execution_gate` 对照实验 | 修尺子 + 新机制 |
| 08-24 | 递归失败 15 道逐题追踪；并列约定 train/dev 审计 | 机制解释 |
| 08-24 | Phase A 轮次级反事实重采样首批 5 道 | 新方法 |

---

## 一、数字口径：三次修正，累计 +3.6pp，全部与模型能力无关

本周所有数字变动都来自**评测框架污染了它本该只观测的结果**，不是模型变强了。

| 缺陷 | 影响 | 处理 |
|---|---|---|
| 控制台 cp936 编码崩溃 | 111 道题被静默判错 | 已修（`shared/console.py`），全部重跑 |
| SQL 执行 30 秒超时 | 全仓 178 条候选中 **121 条实际答对** | 用临时索引副本核实并回填，47 个结果文件、120 处修正 |
| 异常误分类 | harness 崩溃记为模型答错 | 已翻转为白名单（只有 `MaxIterationsError` 算模型结果） |

**超时的根因不是「查询太慢」，是 BIRD 原始库除主键外一个二级索引都没有。**
`Player_Attributes`（18 万行）、`trans`（105 万行）、`legalities`（42 万行）全裸。
121 条里有 68 条是 **gold_sql 自己跑不完**——旧诊断脚本只测 predicted 的耗时，
于是把 gold 侧的问题记成了「模型答错」。

口径变化：arcwise 全集 84.5% → **86.7%**；最高分臂 `e3-c-recursive-db` → **88.10%**。
**所有已发布数字都必须注明口径**，否则会再制造一次不可比。

防复发：新增 `shared/timeout_recovery.py`，判分超时时自动用同一套临时索引副本重试一次，
已接入全部五个 `run_one()`；执行超时 30s → 180s。
**不给 benchmark 原始 `.sqlite` 加索引**——技术上可行且不会让历史运行作废，但那会让所有
跑分建立在一个被我们动过的基准上。

---

## 二、主结果：RLM 的三个机制里，只有一支在付账

五层对照链，每层各跑两次（修正口径）：

| 层 | 新增的是什么 | 准确率 | 增量 |
|---|---|---:|---:|
| 0 | B1：单次生成，不许查库 | 70.5% | — |
| 1 | **+ agent 工具循环（能真的查库、看结果再改）** | 83.9% | **+13.4** |
| 2 | + 离线 schema 检索 | 86.5% | +2.5 |
| 3 | + convention 后处理 | 86.9% | +0.4 |
| 4 | + RLM depth-1 递归 | 87.2% | +0.3 |

按 RLM 三机制归位（`README.md` §2.3）：

| RLM 机制 | 承载层 | 增量 | 判读 |
|---|---|---:|---|
| ② 可执行环境 + ③ 自我改进 | 第 1 层 | **+13.4pp** | 主要贡献，远超噪声带 |
| ① 程序化探索（弱化版：离线检索） | 第 2 层 | +2.5pp | 超过噪声；完整版 context store 另测无收益（上下文利用率仅 4%） |
| ③ 分而治之（depth-1 递归） | 第 4 层 | +0.3pp | 噪声内，测不出 |
| （非 RLM）convention 后处理 | 第 3 层 | +0.4pp | 噪声内 |

**结论不是「RLM 没有贡献」，而是「三个机制的收益极不均衡，几乎全在一支上」。**
这比原表述更强：是有方向的正面结论，且每一支都有独立证据说明为什么划算或不划算。
`config_inventory` §六 原本的「论证 RLM 递归的贡献」是一处窄化，已更正。

**噪声带实测 0.2~1.4pp**（此前记的「1~2pp」两个来源都不成立：一对差在 `max_iterations`，
一对崩溃数不等）。而且噪声随推理强度单调下降：同题集准确率差 5.4pp（minimal）→ 2.2pp（low）
→ 2.2pp（medium）→ 0.2pp（high），逐题翻转 15.9% → 9.9% → 7.9% → 5.5%。
**调低推理强度不只是拿准确率换成本，也是拿可复现性换成本。**

### 替代关系成立（路线 B 的地基）

三个独立估计——`clean-e0 × minimal` 69.1%、B1 均值 70.4%、`e3-c-conv-rules × minimal` 69.45%
——挤在不到 1.5pp 的窄带里。**agent 工具循环与模型内部推理在很大程度上是彼此的替代品。**
直接证据：推理量↓则工具调用次数↑（2.27 → 3.34）。

所以第 1 层那 +13.4pp 买到的**可能不是「有工具」，而是「能试错」**。

---

## 三、四条独立证据指向同一个瓶颈：语义与约定，不是执行

本周最重要的收敛：四条方法完全不同的线，得到了同一个结论。

### 证据一：约定类失败对方法层和推理预算双重免疫

沿方法栈往上：20 → 24 → 25 → 22 道；沿推理强度往上：22 → 13 → 16 → 12 道，**绝对数几乎不动**。
被消灭的全是「没想明白」那一类（132 → 95；116 → 52）。
更讽刺的是第 3 层那个专为约定错误设计的后处理，把这类错误从 24 道变成 25 道，一道没减。

### 证据二：递归为什么没用——leaf 通常是对的，而且不重要

新注册 `e3-c-recursive-db-reasoning`（单变量加 `reasoning_capture`），两次运行 87.9% / 87.3%，
15 道失败逐题读完：

| 真实原因 | 题数 |
|---|---:|
| 递归正常工作，失败在**约定不匹配** | 6 |
| 递归正常工作，失败在最终 SQL 的**聚合/过滤口径** | 5 |
| 委托的子问题本身就问错了 | 2 |
| leaf 没答出来 | 2 |

**11/15 的失败里 leaf 是答对的。没有一道是「leaf 答对但 root 没采纳」。**
最锋利的是 `bird_263`：leaf 把两种可能的计算口径各算了一个具体数值交回去，root 选错了。
**信息完整送达，仍然选错——这不是信息传递的问题。**

> 递归能帮模型把事实查清楚，但失败早就不在「事实没查清」这一层了。

### 证据三：把执行错误修干净后，剩余失败的 98% 是语义错

最好 profile 在全量 498 上的 61 道失败中：**有执行错误的只有 1 道，`error=None` 的有 60 道。**

新增 `final_execution_gate`（控制器在 `FINAL(sql)` 时直接执行一次，只在真实失败时带着
具体原因拦回给模型）。24 道单变量对照：

| | 控制组 | 实验组 |
|---|---:|---:|
| 准确率 | 91.7% | 91.7%（**+0.0pp**，逐题翻转 0 道） |
| 触发率 | — | 8.3%（对比：E1 `verified_final` 被否决时是 90%） |
| 触发后模型真的改写 SQL | — | 2/2 |
| LLM 调用 / token | — | 1.10× |

**机制按设计工作，但天花板本来就只有 ~1pp。** `bird_529` 是干净案例：模型读懂了
「外键无索引，改用 JOIN」并照做；但控制组那道题本来也会被判分侧救回来。
`bird_416` 是反例：gate 成功把超时查询变成跑得完的查询，答案仍错——错在比例公式的分母选择。

**这从完全不同的路径复现了 E1 的结论**：瓶颈是语义判断，不是执行验证。
一个此前没被记录的事实：模型在提交前**从不执行自己的最终查询**（24 道 `events` 全空），
所以这个 gate 是 agent 循环里唯一的一次真实执行。

顺带量化：`no_answer` 21 → **6**（降 71%），且这 6 条只涉及 4 道题，重跑后控制组也全都出了答案。
**`no_answer` 是随机现象，不是一批固定的坏题**，「把这 N 道修掉」这个说法本身不成立。

### 证据四：`ties` 那一类不该修——BIRD 自己就不一致

`ties` 是 `confident_miss` 的主体（11~12/14）。形状完全一致：题面用单数问，模型写
`ORDER BY … LIMIT 1`，gold 返回所有并列行。自然的想法是加一条「遇到并列要全返回」的规则。

按项目规矩先查 **official train（9428 道，模型从未训练过）**的 gold **写法**：

| 形式 | n | 在两种可判定形式间的占比 |
|---|---:|---:|
| `ORDER BY … LIMIT 1`（丢掉并列） | 1255 | **90.0%** |
| `WHERE x = (SELECT MAX(…))`（保留并列） | 139 | **10.0%** |

dev500 上同一类题，按 gold 用哪种约定分开看模型正确率：

| gold 的约定 | n | 正确率 |
|---|---:|---:|
| `LIMIT1` | 50 | **94.0%** |
| `MAX-subquery` | 14 | **50.0%** |

**44 个百分点的落差，而两组题在英文上无法区分。** 并排看就明白：
`Which country produced the car with the lowest price?` → gold 用 `LIMIT 1`；
`What is the order priority of the order with the highest total price?` → gold 用 `= (SELECT MAX(…))`。

机制闭环：gold 用 `MAX-subquery` 而模型答错的 7 道，**7/7 全部是 triage 的 `ties` 命中，
且 7/7 的预测里都含 `LIMIT 1`**——没有「这些题恰好更难」的剩余解释空间。

**三条结论**：

1. 「遇到并列要全返回」这条规则**不能做**。它会与 train gold 的约 90% 冲突，
   比当年被否掉的布尔规则（29% 冲突）严重得多。**这是第六次触到同一个坑，
   这次在写代码之前就拦住了。**
2. **模型不是坏掉的那一环。** 它选了 BIRD 自己 90% 的多数约定，然后在 10% 的少数约定上被扣分。
   这解释了为什么「让模型事后复核」五次全部净负（`verify_before_limit` 恢复 1、打坏 9、净 −8）
   ——**修一个不在模型里的东西，当然只会越修越差。**
3. **正确的产出是测量，不是修复。** `ties` 应作为**基准约定不一致**报告。

---

## 四、新方向：Phase A 从「LLM 判断」升级为「测量」

Phase A 首轮的定位是一次 LLM 判断，属于观察性证据。本周开始用**反事实重采样**代替判断：
在每个轮次边界截断，重采样 N=10，看 P(答对 | 前 k 轮固定) 怎么变
（Thought Anchors 的 resampling importance，轮次粒度）。

首批 5 道，**分成三种形态，不是一种**：

| 形态 | 例 | 含义 |
|---|---|---|
| **锁死型** | `bird_637` 78% → 0% → 0% | 干净的因果承诺点，跌落 0.78 就是测得重要性 |
| **非单调型** | `bird_587` 10% → 71% → 0% → 20% | **这道题没有「第一个错误承诺点」**，Phase A 定位脚本的前提在此不成立 |
| **平零型** | `bird_1068`/`bird_465`/`bird_173` | 处处接近 0，重采样测不到任何东西，**必须换介入臂** |

> **入库前发现的一批未记录数据**（`analysisDetail/phaseA_resample/all28_run1_turn1.json`，
> 22 道的 k=1，本次一并提交；`phase_a_turn_resampling_2026-08-24.md` 只写了其中 5 道）。
> 两个直接影响：
>
> 1. **平零型是多数**：22 道里 **14 道 k=1 全零**，8 道有非零样本。「重采样在多数题上测不到
>    东西、介入臂是必需的」这个判断，从 5 道扩到 22 道后依然成立，而且更强。
> 2. **`bird_637` 的 k=1 在两批之间不一致**：7/9（78%）对 2/6（33%）。「锁死型」这个形态
>    仍然成立（第 1 轮固定后归零），但 **0.78 这个具体数值不能引用**——它是单批 n≈6~9 的
>    点估计。`bird_587`（1/10 对 2/9）、`bird_1068`、`bird_465` 两批一致。
>
> **k≥2 的曲线目前仍然只有那 5 道。**

`bird_637` 的机制完全可见：模型**在看到任何工具结果之前**就提交了 `WITH RECURSIVE` 的临时
`FINAL()`（承诺先于观察）；诱因很可能是 prompt 里检索到的 few-shot 例子
（一个「标签在独立表里、一行一个」的模板，run2 的 `INNER JOIN tags` 几乎是逐字模仿）；
第 2 轮真跑了递归查询、返回只有一行，模型看到之后**原样提交了**。

**这给出了第二步介入臂的具体设计**：臂 B = 删掉或替换检索到的 few-shot 例子，其余不变。
B 显著高于 A → few-shot 检索器是失败的因果来源之一。这比「注入事实」更有价值，
因为它检验的是 e3-c 自己的一个**可消融部件**。

**`locate_first_wrong_sentence.py` 假设「存在第一个承诺错误的句子」——这个前提本身
应当逐题检验，而不是默认。** 轮次曲线正好是检验它的工具。

---

## 五、方法学：机械判定本周又被推翻两次（累计第五、第六次）

| 这次是谁 | 怎么错的 | 已改成 |
|---|---|---|
| `verify_located_claims.py` | 「`check_sql` 返回非空即算 confirmed」跑出 28/29（97%）——**假的**。真正严谨验证的只有 8~9 道，且有 1 道（`bird_637`）自动判为 confirmed 实际是**反驳** | 自动分类只用于筛硬故障，标签不能当结论 |
| `analyze_recursion_traces.py` 第一版 | 按 leaf 答案与最终 SQL 的 **token 重叠**判 `leaf_unused`，run1 六道里五道标错——leaf 答 "Geoff Dalgas"、SQL 写 `SELECT u.DisplayName … LIMIT 1`，无共同 token 但显然被用上了 | 只输出可复算事实，判断留给人 |

**共同教训：表面重叠 / 非空返回，替代不了语义判断。**
分诊脚本「只出可复算事实、不出结论」的设计约束必须保持。

另外，可复算检查的覆盖率封顶在约 30%（165/549）。「其它」里 28%（30/107）已定位为
**比例公式分子分母选择**子模式，但**判定不值得机械化**——修法需要理解题意，
与已废弃的 `count_no_distinct` 后处理规则是同一类风险。**下一步只能是人工判读。**

---

## 六、本周新增的代码资产

| 文件 | 用途 |
|---|---|
| `shared/console.py` | 编码修复；**任何新 agent 入口都必须调用 `force_utf8_console()`** |
| `shared/timeout_recovery.py` | 判分超时自动用临时索引副本重试；已接入全部 5 个 `run_one()` |
| `scripts/audit_run_configs.py` | 逐字段核对运行配置；**`cfg_sha` 两个方向都不可靠，比较前用它** |
| `scripts/triage_failure_causes.py` | 失败分诊；新增 `column_permutation` / `concat_columns` |
| `scripts/build_phase_a_funnel.py` | 498 → 29 的逐题漏斗固化 |
| `scripts/analyze_recursion_traces.py` | root/leaf 推理切分 + 事实输出 |
| `scripts/resample_turn.py` | 轮次级反事实重采样 |
| `scripts/audit_tie_convention.py` | train/dev 并列约定审计 |
| `scripts/compare_final_gate.py` | gate 两臂对比 |
| `ours/agent/config.py` | 新增 `final_execution_gate` 字段；profile `e3-c-recursive-db-final-gate`（**新运行推荐默认**）、`e3-c-conv-rules-final-gate`、`e3-c-recursive-db-reasoning` |
| `tests/test_timeout_recovery.py`、`tests/test_final_execution_gate.py` | 8 个新测试 |

---

## 七、目前最好的详细配置

**实测最高分臂：`e3-c-recursive-db`** —— 修正 dev500 上两次运行 **87.70% / 88.51%，均值 88.10%**
（498 题中 496 可计分）。
**新运行推荐默认：`e3-c-recursive-db-final-gate`** —— 同一配置 + FINAL 执行门（单变量），
理由是防复发而非提准（见 §三 证据三）。

### Agent 配置（取自 `trace/chain_e3_c_recursive_db_corrected_run1/run_manifest.json`）

| 字段 | 值 | 含义 |
|---|---|---|
| `prompt_profile` | `conventions-recursive-v1` | prompt_id `conventions-plus-recursive-leaf-v1`，来源 train-mined-conventions，**不含示例**，含任务级 SQL 规则，sha `9b605cf1…` |
| `capability_gate` | `true` | 通用 `recursive_llm` 关闭，context store 不可读，**只暴露 depth-1 递归** |
| `allowed_db_methods` | `("execute", "sample_values")` | 模型只有这两个数据库动作 |
| `few_shot_mode` | `train-retrieval`，**k = 1** | `TrainFewShotRetriever`，池 `data/train_pool.json`（9428 道，sha `80c03262…`），嵌入 `all-MiniLM-L6-v2`，**source_split = bird-train** |
| `schema_context_mode` | `offline-retrieval` | 不再把全库 schema 塞进 prompt |
| `offline_metadata_mode` | `e3-f-schema-v4` | `data/processed/e3_f_schema_v4.json`，artifact sha `ed713b06…` |
| `sql_convention_mode` | `train-conventions-v1` | 三条规则里**只开一条**，见下 |
| `recursion_mode` | `leaf-db-v1` | depth-1 leaf **共享父级那个受控的数据库句柄**（v1 的纯文本 leaf 知道的更少，实测 0.00pp） |
| `verified_final` | `false` | E1 已否决（42.14% → 40.00%） |
| `final_execution_gate` | `false`（最高分臂）／ `true`（推荐默认） | 与 `verified_final` 在 `__post_init__` 里互斥 |
| `use_db_hints` / `context_mode` / `planner_mode` / `reasoning_mode` / `query_pattern_mode` / `reasoning_capture` / `literal_verification_nudge` | `false` / `direct` / `none` / `none` / `none` / `none` / `false` | 其余能力全关 |
| `agent_config_sha256` | `656e7cb19bf177b352b6b1becb04e857600783c04abb2125c2d883f5ba23cbb5` | **比较前用 `audit_run_configs.py` 逐字段 diff，不要只信这个 sha** |

### 三条 convention 规则：只有一条是开的

| 规则 | train 支持度 | 状态 | 关掉的理由 |
|---|---:|---|---|
| `no_select_concat`（`a \|\| b` 拆成独立列） | **0.9999**（9427/9428） | **启用** | — |
| `count_no_distinct`（JOIN 时去掉 COUNT 的 DISTINCT） | 0.891 | 禁用 | 改变了 COUNT 在数什么（实体 → 行） |
| `superlative_order_limit`（`= (SELECT MAX…)` 改写成 `ORDER BY … LIMIT 1`） | **0.9034** | 禁用 | 改变了计算本身，且可能丢掉 WHERE 条件 |

**注意第三条**：它的 train 支持度 0.9034，与本周并列约定审计独立测到的 **90.0%** 完全吻合——
同一个 90:10 的分布被两条不同路径量到了。这也再次说明为什么反方向的那条规则
（「遇到并列要全返回」）不能做：它要对抗的正是这 90%。

### 运行时参数

| 项 | 值 |
|---|---|
| 模型 | `azure/seminar-gpt-5.4-mini`，`api_version 2024-12-01-preview` |
| `max_iterations` | **8**（该字段**不进** `agent_config_sha256`，是历史上「假重复」的来源） |
| `reasoning_effort` | `high` |
| temperature | 请求 0.0，**实际未发送**（`drop_params` 生效，`temperature_sent: false`）——采样未被固定 |
| 数据集 | `data/processed/bird_dev_500_corrected_full.json`，sha `59dba552…`，498 题 |
| 数据库 | `data/raw/bird/minidev/MINIDEV/dev_databases` |
| 判分超时 | 该次运行是 30s；**现已改为 180s + `timeout_recovery`**（见 §一） |

### 复现命令

```bash
python scripts/run_bird_train_fewshot.py \
  --agent-profile e3-c-recursive-db-final-gate \
  --dataset data/processed/bird_dev_500_corrected_full.json \
  --model azure/seminar-gpt-5.4-mini \
  --max-iterations 8 --k 1 --reasoning-effort high \
  --output results/<name>.json
```

### 引用这个数字时必须一起说的三件事

1. **88.10% 是修正 gold + 超时回填之后的口径**，与任何 08-23 之前发布的数字不可直接比。
2. **走 Chat Completions 路径**；带 `reasoning_capture` 的臂走 Responses API，两者不可比
   （`e3-c-recursive-db-reasoning` 的 87.9% / 87.3% 属于后者）。
3. **498 题里 2 道不可计分**，分母是 496。

---

# 后面的计划（2026-08-25 起）

## 优先级排序的理由

上周的四项任务全部完成，`WEEK_PLAN_2026-08-20.md` 已结案。本周四条证据把瓶颈锁在
**语义 + 基准约定**上，所以下一阶段的排序原则是：**凡是绕开这个瓶颈的投入一律降级。**

---

## P0：人工基准校准（唯一的阻塞项，需要你本人）

这是本轮**唯一没有完成的一步**，而且必须由人做——不能由我做，因为
「同一个 AI 系统内部的复核」不能替代独立基准。两份材料已经准备好，逐题排版可直接读：

| 材料 | 内容 | 要判什么 |
|---|---|---|
| `tie_convention_manual_review.md` | 28 道并列约定题的对照表（题面 / gold 返回行数 / gold SQL / 模型 SQL），两组分开排 | **人能不能从题面看出该返回一个还是全部并列？** |
| `located_phaseA_all29.json` + `phase_a_first_pass` 末节 | 29 道 Phase A 定位的 claim 与 check_result | 定位是否命中；断言是否被真正验证 |

**为什么这件事阻塞其余**：

- 并列那份决定论文里 `ties` 到底写成「模型错误」还是「基准歧义」。
  若人也看不出区分依据，`ties` 就是干净的 benchmark 缺陷证据（44pp 落差 + 7/7 机制闭环），
  可以直接进讨论章节；若人看得出，「题面完全无法区分」这个更强的说法要收窄
  （规则仍不可做——train 的 90:10 摆在那里）。
- Phase A 那份决定 29 道语料还能不能用于因果分析。

**建议做法**：并列那份只需读题面并盲判「一个 / 全部」，再对答案，约 30 分钟；
Phase A 那份逐条读 claim 与返回值打分，约 1 小时。

---

## P1：Phase A 介入臂（本周主要新实验，成本低）

由 `bird_637` 直接给出的设计，检验的是**我们自己的部件**：

| 臂 | 内容 |
|---|---|
| A | 原样重采样（k=1 列，已有） |
| B | **删掉或替换检索到的 few-shot 例子**，其余不变，同样次数 |

B 显著高于 A → few-shot 检索器是失败的因果来源之一，且可消融、可改。

**铺开前必须先修三个已知会毁掉预算的问题**（各 10~30 分钟）：

1. ~~`resample_turn.py` 加 **per-sample 兜底**~~ —— **已在工作树中修好**（每个样本单独 try/except，
   失败记为无效样本而非抛出）。原问题：`bird_173` 的 Azure `invalid_prompt` 误判会让 `f.result()`
   直接抛出，**掀掉整个 k 批次**，turn1.json 只存下先完成的 4 道。
2. 回填 `bird_518`、`bird_701` 的 `gold_answer`（现为 `None`）。30 秒超时修正走
   `indexed_reexecution` 时没回填，而 `shared/evaluator.py:46` 对 `None` 一律返回 `False`——
   跑了会得到一个看起来很漂亮的 0/10，实际是评分函数在跟 `None` 比较。
3. **平零型题不能只靠重采样**（`bird_1068`/`bird_465`/`bird_173` 处处接近 0），
   要么排除出臂 B 样本，要么单独设计介入。

**样本量**：k=1 现在已有 22 道（见 §四 的补记，14 道平零 / 8 道非零），**缺的是 k≥2 的曲线**——
那部分仍然只有 5 道。先把这 22 道的 k=2/3/4 补齐，形态占比才算测出来，再谈臂 B 的样本选择。

---

## P2：论文结构落定（三块，共用已有数据）

| 路线 | 主张 | 证据状态 |
|---|---|---|
| **A 机制归因（主线）** | RLM 三机制的收益分布，及每一支为什么是这个结果 | **齐了**——五层链两次重复 + 三机制归位 + context store 4% 利用率 + 递归 15 道逐题追踪 |
| **B 结构 vs 推理量（深化 A）** | 第 1 层的收益有多少是「能试错」而非「有工具」；它与内部推理是替代品 | **齐了**——三个独立估计挤在 1.5pp 内 + 调用次数反向变化 + 四档强度各两次 |
| **C 约定不匹配（讨论章节）** | 一类失败对方法层和推理量双重免疫，需要别的工具 | **等 P0**——train 90:10 审计 + 44pp 落差 + 7/7 机制闭环已备，缺人工判读那一环 |

本周新增的两条证据（递归逐题追踪、`final_execution_gate` 天花板分析）都归入 A，
它们把「效应太小」升级成了**机制层面的解释**。

**命名整改**：`confident_miss` 这个标签现在有两处不成立——推理量 0.79× 签名在本人群上
是 0.87×/1.24×（run2 方向相反），且「失误」对其主体也不准确。
建议在 Phase A 语境下改名 **`mechanically_repairable`**（描述测试做了什么），
论文里把 `ties` 从「模型错误」移到「基准歧义」一节。

---

## P3：收尾与卫生

- **提交本周未入库的工作**：4 份文档（`phase_a_turn_resampling`、`tie_convention_audit`、
  `tie_convention_manual_review`、以及本报告）、2 个脚本
  （`audit_tie_convention.py`、`resample_turn.py` 的改动）、`analysisDetail/phaseA_resample/`。
- **`INDEX.md` 补三条**：08-24 后半天的三份文档还没进索引。
- **两份 `HanyanChen_CV.pdf`** 落在仓库根目录和 `src/` 下，与项目无关，建议移出或加 `.gitignore`。
- 文档更正尾巴：`NEXT_PHASE_PROMPT.md` 的「比较前先查 `agent_config_sha256`」
  需改为逐字段 diff；`config_inventory_2026-08-17.md` §七 的「递归调用率波动近 4 倍」
  实为 `dev200_run1` 用了不同 prompt，实测稳定在 12.9%~14.9%。

---

## 明确不做

| 不做什么 | 为什么 |
|---|---|
| 继续在**执行验证**方向投入 | 剩余失败 60/61 是语义错，gate 天花板 ~1pp、实测 0.0pp |
| 加「遇到并列要全返回」的后处理规则 | 与 train gold 的 90% 冲突；第六次触到同一个坑 |
| 为救回递归效应加配置或调 prompt | +0.3pp 是在两次重复、1.4pp 噪声带下测出的，加臂只增加多重比较风险 |
| 用 LLM 标注器出结论 | 本项目 LLM judge 只有 2/15 正确；机械判定已被证伪六次 |
| 继续给「其它」加机械检查 | 覆盖率封顶 30%，比例公式那 30 道已是最后一块安全子模式 |
| 给 benchmark 原始 `.sqlite` 加索引 | 技术上可行且不会让历史运行作废，但会让所有跑分建立在被我们动过的基准上 |
| 改数据源重新生成数据集 | 会改变 `dataset_sha256`，链上所有 manifest 校验失败，已跑完的全部作废 |

---

## 一句话总结下一阶段

**方法栈这条线已经测到头了——四条独立证据都指向同一个瓶颈，而它不在方法栈上。
下一步的价值全部集中在两件事：让人来校准那两份判读，以及用介入臂把
「few-shot 检索器带偏了模型」这个假设做成因果结论。**
