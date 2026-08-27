# C1 Pairing Contract (v0.8)

本文档冻结 C1（T1 vs T2）可比实验的配对键与声明边界，避免跨来源、跨窗口、跨样本口径混比。

## 1) 实验身份

- `backbone_model = gpt-4.1`
- `backbone_training_cutoff = 2024-06-30`（June 2024 按月末保守处理）
- `guard_days = 30`
- `experiment_as_of = 2026-08-17`

旧 Hub pin（339 题，`2024-06-01`）为 legacy identity，仅用于历史复现，不与本契约结果混表。

## 2) 配对范围

- A1 / A2 使用 `configs/aligned_panel_v1.json` 的 14 组显式 `panel_pair_id`。
- B / C 当前只冻结键定义，不宣称“全品类 paired C1 完成”。
- A2-F / A2-H 在官方 filing snapshot 完整前，作为研究附录，不作为 C1 主切片。

## 3) 冻结配对键

- A1 键：`(market, stock_code)`
- A2 键：`(market, cohort_key, variant)`
- B 键：`(market, stock_code, event_subtype, event_window)`
- C 键：`(market, stock_code, metric_name)`

分析层只允许以下两种横比方式：

1. 同一 `panel_pair_id` 内 T1 vs T2；
2. 同一任务键（上面的冻结键）内 T1 vs T2。

禁止跨键拼接、跨窗口拼接、或把 legacy pin 样本混入 v0.8 表。

## 4) C1 可宣称条件

- A1 / A2-T：严格配对，且两侧样本各 `>= 30`。
- B / C：同时满足
  - `outcome_available_at_source` 为 `observed_*`；
  - 有官方 `outcome_evidence_url`；
  - 通过 `review_status=reviewed`；
  - 配对后两侧样本各 `>= 30`。

## 5) 当前结论边界（本轮）

- 可以宣称：A1 / A2-T 已满足严格配对 C1 条件（基于 aligned panel）。
- 不可宣称：全品类 paired C1 完成。
- 不可宣称：C2 已解锁（已结算 T3 仍为 0；本轮仅修 T3 元数据一致性）。
