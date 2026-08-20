扫描 66 个 run_manifest.json

## A. manifest sha ≠ 当前同名 profile 的 sha

`sha256` 是派生字段，已从比较中剔除。**新增字段**在那次运行时并不存在，
不可能影响其行为；**值变更**才需要判读。

| 运行 | profile | 值变更（需判读） | 新增字段数 |
|---|---|---|---:|
| `e3_c_core197_run1` | `e3-c` | `capabilities.gate_enabled`: False → True; `capabilities.generic_recursive_llm`: True → False; `capability_gate`: False  | 8 |
| `e3_c_core197_run2` | `e3-c` | `capabilities.gate_enabled`: False → True; `capabilities.generic_recursive_llm`: True → False; `capability_gate`: False  | 7 |
| `e3_c_recursive_db_dev200_run1` | `e3-c-recursive-db` | `prompt.contains_task_specific_sql_rules`: False → True; `prompt.prompt_id`: 'recursive-leaf-protocol-v1' → 'conventions | 1 |
| `e3_f_core197_run1` | `e3-f` | `offline_metadata_mode`: 'e3-f-schema-v3' → 'e3-f-schema-v4'; `query_pattern_mode`: 'train-mined-v1' → 'train-mined-v2' | 7 |
| `e3_f_smoke` | `e3-f` | `offline_metadata_mode`: 'e3-f-schema-v3' → 'e3-f-schema-v4'; `query_pattern_mode`: 'train-mined-v1' → 'train-mined-v2' | 7 |
| `e4_a_smoke4_run1` | `e4-a` | `prompt.prompt_id`: 'query-plan-protocol-v1' → 'query-plan-protocol-v3'; `query_plan.required_initial_fields`: ['aggrega | 9 |
| `e4_a_smoke4_run2` | `e4-a` | `prompt.prompt_id`: 'query-plan-protocol-v1' → 'query-plan-protocol-v3'; `query_plan.required_initial_fields`: ['aggrega | 6 |

**7 个运行有值变更（需人工判读），41 个只是新增字段（纯漂移，行为未变）。**

## B. 相同 agent_config_sha256，但运行参数不同

**`01fb1b456bd9`** —— 差异字段：`ids_file`

| 运行 | ids_file |
|---|---|
| `e3_c_literal_check_smoke1` | C:\Users\Irene\AgenticSearch\data\processed\e3_c_literal_check_smoke_ids.json |
| `e3_c_literal_check_smoke2` | C:\Users\Irene\AgenticSearch\data\processed\e3_c_literal_check_smoke2_ids.json |

**`03c10637dc9a`** —— 差异字段：`max_iterations`, `temperature_requested`

| 运行 | max_iterations | temperature_requested |
|---|---|---|
| `e3_c_conv_rules_dev500_iter15` | 15 | None |
| `e3_c_conv_rules_dev500_run1` | 8 | None |
| `e3_c_conv_rules_dev500_run2` | 8 | 0.0 |

**`19f41065aa4a`** —— 差异字段：`limit`

| 运行 | limit |
|---|---|
| `e3_f_core197_run1` | None |
| `e3_f_smoke` | 3 |

**`1a372781e175`** —— 差异字段：`ids_file`

| 运行 | ids_file |
|---|---|
| `e3_c_conv_core197_run1` | C:\Users\Irene\AgenticSearch\data\processed\bird_cleancore_ids.json |
| `e3_c_conv_dev500_run1` | None |

**`43103165edbd`** —— 差异字段：`limit`

| 运行 | limit |
|---|---|
| `e1_verified_run1` | None |
| `e1_verified_smoke` | 3 |

**`46deed1647a6`** —— 差异字段：`limit`

| 运行 | limit |
|---|---|
| `e0_clean_smoke_v2` | 3 |
| `e0_core_run1` | None |
| `e0_core_run2` | None |

**`67193467d29a`** —— 差异字段：`limit`

| 运行 | limit |
|---|---|
| `e3_a_core197_run1` | None |
| `e3_a_run1` | 50 |

**`671e8010a65c`** —— 差异字段：`dataset`

| 运行 | dataset |
|---|---|
| `chain_e3_c_conv_rules_corrected_run1` | bird_dev_500_corrected_full.json |
| `chain_e3_c_conv_rules_corrected_run2` | bird_dev_500_corrected_full.json |
| `e3_c_arcwise_full_dev500_run1` | bird_dev_500_corrected_full.json |
| `e3_c_conv_rules_v2_dev500_run1` | bird_dev_500.json |

**`e5435e0700bc`** —— 差异字段：`temperature_requested`

| 运行 | temperature_requested |
|---|---|
| `e3_c_rc_ctl_dev500_run1` | 0.0 |
| `e3_c_rules_reasoning_dev500_run1` | 0 |

**`eafdf5cd9112`** —— 差异字段：`dataset`, `ids_file`

| 运行 | dataset | ids_file |
|---|---|---|
| `rootcause_ambiguity_control` | bird_dev_500.json | C:\Users\Irene\AgenticSearch\data\processed\rootcause_disambiguation_ids.json |
| `rootcause_ambiguity_disambiguated` | bird_dev_500_disambiguated.json | C:\Users\Irene\AgenticSearch\data\processed\rootcause_disambiguation_ids.json |
| `rootcause_hint_ablated` | bird_dev_500_nohint.json | C:\Users\Irene\AgenticSearch\data\processed\rootcause_hint_ablation_ids.json |
| `rootcause_hint_control` | bird_dev_500.json | C:\Users\Irene\AgenticSearch\data\processed\rootcause_hint_ablation_ids.json |
| `rootcause_hint_valueenc_ablated` | bird_dev_500_nohint_valueenc.json | C:\Users\Irene\AgenticSearch\data\processed\rootcause_hint_valueenc_ids.json |

**`ed1828cf3a71`** —— 差异字段：`ids_file`

| 运行 | ids_file |
|---|---|
| `e4_a_core197_run1` | C:\Users\Irene\AgenticSearch\data\processed\bird_cleancore_ids.json |
| `e4_a_protocol_retry1_run2` | C:\Users\Irene\AgenticSearch\data\processed\e4_a_protocol_retry_ids.json |

**`fdb0963b9481`** —— 差异字段：`model`, `limit`

| 运行 | model | limit |
|---|---|---|
| `e3_c_schema_v4_core197_run1` | azure/seminar-gpt-5.4-mini | None |
| `e3_c_schema_v4_core197_run2` | azure/seminar-gpt-5.4-  ni8098··········································· | None |
| `e3_c_schema_v4_core197_run3` | azure/seminar-gpt-5.4-mini | None |
| `e3_c_schema_v4_smoke_v2` | azure/seminar-gpt-5.4-mini | 1 |

## C. trace 覆盖不全（transcripts 少于 results）

| 运行 | results | trace | 覆盖 |
|---|---:|---:|---:|
| `e3_c_semantic_dev500_run1` | 492 | 198 | 40% |

