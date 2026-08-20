# 指代歧义实验在修正数据集上的现状诊断（2026-08-20）

`rootcause/disambiguation_experiment_2026-08-08.md` 手工改写了 7 道题的一个歧义名词，
5/7 纠正了模型行为、2/7 整题转正。7 道题中 **6 道题面已被外部修正重写**，逐题核查：

## 逐题核查

| 题号 | 原歧义所指 | 题面是否重写 | gold 是否变化 | 判定 |
|---|---|---|---|---|
| `bird_902` | `driverStandings` | **否** | 否 | **原实验仍成立，直接可用** |
| `bird_584` | `postHistory.Comment`（"comments"→"revision-history comments"） | 是 | 否 | **外部修正独立收敛到同一处消歧**（"comments"→"edit comments"）——题面已经自带纠正，不用再改 |
| `bird_1166` | `Patient.Diagnosis`（"their"→"that patient's own"） | 是（"their diagnosis"→"the patient diagnosis"）| **是**：gold 改用 `DISTINCT` + `Birthday = (SELECT MAX(...))` | 题面方向一致但不如手工改写精确；更关键的是 **gold 新写法与原实验记录的"消歧后模型改用的等值写法"结构一致**——原实验判该写法为空结果失败，现在需要重新执行验证是否仍然为空 |
| `bird_906` | `driverStandings` | 是（语法澄清，不涉及该歧义） | **是**：gold 改用 `results` 表，不再是 `driverStandings` | **原歧义所指对象本身已被 gold 换掉**，原实验的消歧方向可能不再适用 |
| `bird_465` | `set_translations` | 是（问句从是非题"is there"改写成列表题"which sets"） | **是**：gold 从 `IIF(...,'YES','NO')` 改成 `SELECT DISTINCT T3.name` | 原实验记录的"第二层阻挡"（输出约定：是非题 vs 翻译文本）**已被题面重写连带解决**——问法本身不再是是非题 |
| `bird_145` | `trans.account_id` | 是（完整重写） | **是**：gold 改走 `disp` 表 `type='OWNER'`，不再是单纯 `trans.account_id` | **原歧义所指对象已被 gold 换成完全不同的表**，原实验的消歧目标物不再存在 |
| `bird_1529` | `Price`（"amount spent"→"total money spent"） | 是（但只改了"January"→"August"，与歧义无关） | **是**：gold 改用 `Amount * Price`——**与原实验记录的"模型失败原因"完全一致**（"模型仍然算 Amount × Price，没意识到 Price 本身就是金额"）| 原实验判定的模型失败，现在看更像是 **gold 缺陷**：模型当初的计算方式可能是对的 |

## 判读

**只有 1 道题（`bird_902`）原样成立**，可以直接用旧的手工改写版本重跑验证。

**3 道题（`bird_584`、`bird_1166`、`bird_465`）方向未变或已被独立解决**，不需要重新造消歧文本，
但需要用**当前**题面（已经是修正版）+ 现在的 harness 重新执行，看第二层阻挡是否也一并解开了：

- `bird_1166` 最值得关注——gold 现在用的正是原实验里"消歧后模型自己想出但被判空结果失败"的那个查询结构，
  说明当时判定的"新引入的查询结构错误"，很可能本来就是**该题的正确解法**，只是旧 gold 没写对
- `bird_465` 的是非题→列表题重写，直接解决了原实验记录的输出约定阻挡

**2 道题（`bird_906`、`bird_145`）原歧义所指对象被 gold 换掉了**，原实验的消歧方向可能已经不适用，
需要重新判读这两道题现在真正的歧义点是什么（如果还有的话），不能沿用旧改写。

**1 道题（`bird_1529`）原判定很可能是错的**：原实验记录"消歧后模型仍算错"，
但新 gold 恰好用了模型当初的算法（`Amount * Price`），指向**当初判给模型的失败其实是 gold 缺陷**，
与本项目"gold 修正前后模型答案不变、只是参考答案变对"这条主线（[`failure_adjudication_final_2026-08-16.md`](../failure_adjudication_final_2026-08-16.md) §3.7）是同一种模式。

## 建议

1. **不必重新手工改写**——7 道里 4 道（`bird_902`/`584`/`1166`/`465`）用当前题面直接跑
   `e3-c-conv-rules` 即可验证，`bird_1529` 也建议顺带跑一遍验证 gold 缺陷假设
2. **`bird_906`/`bird_145` 需要人工重新判读**新 gold 指向的表结构，暂不纳入这轮重跑
3. 因果证据链的价值不会因此减弱——**"改变一个歧义名词，模型行为随之改变"这条因果链本身不依赖任何具体题目**，
   本诊断说明的是"这 7 个具体样本"里哪些还能直接复用、哪些需要换新样本，不是推翻原结论

## 涉及文件

- [`rootcause/disambiguation_experiment_2026-08-08.md`](../rootcause/disambiguation_experiment_2026-08-08.md) —— 原实验
