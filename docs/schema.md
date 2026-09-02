# Benchmark Seed Schema

本文档定义 `benchmark-research` 数据集中所有 JSONL 记录的统一结构。

## JSONL 格式要求

- 每个文件必须是 **JSONL**（JSON Lines）格式
- **一行一个 JSON object**，禁止使用 JSON 数组包裹多条记录
- 文件编码为 UTF-8

## 统一记录字段

每条记录必须包含以下顶层字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `str` | 全局唯一标识，如 `A1-TPL-00001`、`D-T2-00003` |
| `category` | `str` | 任务类别：`A1` / `A2` / `B` / `C` / `D` / `E` |
| `variant` | `str \| null` | 子变体，如 `F`/`T`/`H`、`earnings`/`macro`；无则 `null` |
| `cutoff_date` | `str` | 用于时间分层的截止日期（YYYY-MM-DD） |
| `time_band` | `str` | 时间带：`T1` / `T2` / `T3` |
| `status` | `str` | 记录状态，见下文 |
| `seed` | `object` | 结构化输入字段，供造题脚本与复现使用 |
| `prompt` | `str` | **已渲染**的完整 prompt 字符串，Agent 黑盒直接消费 |
| `expected_output` | `object` | 期望输出 JSON 的字段说明 |
| `ground_truth` | `object \| null` | 评测标签；template 可为 `null`，ready seed 必须完整 |
| `metadata` | `object` | 附加元信息，至少包含 `is_template` |

### `metadata` 建议字段

```json
{
  "is_template": true,
  "prompt_template": "prompts/a1_valuation.txt",
  "temporal_split": {
    "time_band": "T2",
    "cutoff_date": "2025-06-06",
    "cutoff_date_source": "seed.cutoff_date",
    "is_synthetic_cutoff_date": false,
    "model_training_cutoff": "2024-06-30",
    "reference_current_date": "2026-08-17",
    "rule": "T1: cutoff_date <= model_training_cutoff; T2: model_training_cutoff < cutoff_date < reference_current_date; T3: cutoff_date >= reference_current_date"
  },
  "notes": "可选说明"
}
```

- `is_template: true` — 模板样例，不用于正式评测
- `is_template: false` — 可用于 baseline / 正式评测
- `temporal_split` — ready seeds 必填，用于复现 T1/T2/T3 时间泄漏切分

### `seed` 市场字段（A1 / A2 / B / C）

价格与 Yahoo 生成题型应包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `market` | `str` | `CN_A` / `US` / `HK` |
| `currency` | `str` | `CNY` / `USD` / `HKD` |

A1 prompt 使用 `{currency_unit}`（`元` / `USD` / `HKD`），避免美股/港股仍写「元/股」。`time_band` 不在造题脚本里写死，由 `scripts/assign_time_bands.py` 或 runner 按 `--model-training-cutoff` 判定。

## 时间分层（T1/T2/T3）

默认发布参数：

- `model_training_cutoff = 2024-06-30`
- `reference_current_date = 2026-08-17`

切分规则：

- `T1`：`cutoff_date <= model_training_cutoff`
- `T2`：`model_training_cutoff < cutoff_date < reference_current_date`
- `T3`：`cutoff_date >= reference_current_date`

注意：严格来说，T1/T2 取决于具体模型的训练截止日期。评测不同模型时，应使用 `scripts/assign_time_bands.py` 按该模型训练截止日重新计算。

`2024-06-01` / 339 题旧 Hub pin 属于 legacy identity，仅用于历史复现，不能与当前 v0.8（`gpt-4.1` + `2024-06-30`）结果混表比较。

## 论文时间几何（paper_band）

论文实验**不得**直接使用 legacy `time_band`。应使用侧车文件 `data/task_temporal_index.jsonl`（由 `scripts/classify_paper_temporal.py` 生成），字段包括：

| 字段 | 说明 |
|------|------|
| `forecast_origin` | 预测锁定时点（日精度） |
| `outcome_available_at` | 结果可用日；是否为观测值须结合 `outcome_available_at_source`，T3 可为 `pending` |
| `outcome_available_at_source` | `observed_*` 为观测日期；`modeled_*` / `heuristic_*` 为估计日期 |
| `paper_band` | `T1` / `T2` / `T3` / `quarantine` / `D` / `E` |
| `review_status` | `draft` / `reviewed` |
| `review_method` | 审核方式；自动审核为 `automated_evidence_validation` |
| `reviewed_at` | 审核时间 |
| `evidence_hash` | 审核时关键证据字段的 SHA-256 |
| `quality_flags` | 如 `modeled_outcome_availability`、`fundamentals_after_origin` |
| `official_temporal_eligible` | 是否具备进入官方分所需的时间证据 |

### Path B / v2 review ledger

`calibration/review_ledger_v2.csv` 固定覆盖基线 commit
`736273f4d211c0c31fab43da1fbfd49509598e85` 中的 A1、A2-T、B，共 543 个
唯一 `task_id`。T1/T2 发布包只包含 A1、A2-T、B-earnings，共 530 行；
B-macro 仅用于 calibration。

审核字段和允许值：

| 字段 | 规则 |
|------|------|
| `scope_role` | `temporal_t1_t2` / `b_calibration` / `both` |
| `review_status` | `reviewed` / `draft` |
| `review_method` | 必须来自 `configs/path_b_v2_review_contract.json` 的正式枚举；正式值尚未提供时留空 |
| `event_evidence_status` | `not_applicable` / `reviewed` / `draft` / `missing` |
| `price_evidence_status` | `not_applicable` / `reviewed` / `draft` / `missing` |
| `exclusion_reason_code` | reviewed 行必须为空；draft 行必须为稳定非空枚举 |
| `evidence_package_sha256` | 对 `calibration/evidence_packages_v2.jsonl` 中该 task 的排序证据项做规范化 JSON SHA-256 |

自动构建默认全部为 `draft`。`official_temporal_eligible=true` 还要求：

- `calibration/review_attestations_v2.csv` 存在独立人工签核；
- 签核中的 task、证据包 SHA、审核人、正式 review method 与 ledger 完全一致；
- `attestation_sha256` 可由签核字段规范化重算；
- 所有适用证据状态为 `reviewed`，且不存在 blocking flags 或排除原因；
- `reviewed_at` 严格晚于包内所有 snapshot 的 `fetched_at`。

原始证据按内容寻址保存为
`hf_dataset_path_b_v2/evidence/snapshots/<SHA 前两位>/<完整 SHA-256>`。
Validator 会打开每个文件并重算 SHA，不能只信 sidecar。当前需求文本未包含其
引用的正式 `review_method` 枚举，因此 contract 暂为空；在正式值补入前，
任何记录都不能晋升为 `reviewed`。

默认论文参数（`gpt-4.1` backbone）：

- `backbone_training_cutoff = 2024-06-30`（GPT-4.1 的 “June 2024” 按月末保守处理）
- `guard_days = 30`
- `experiment_as_of = 2026-08-17`

分类规则：

- `T1`：`outcome_available_at <= 2024-05-31`
- `T2`：`forecast_origin >= 2024-07-30` 且 `outcome_available_at <= 2026-07-18`
- `T3`：`forecast_origin >= 2026-08-17`
- `quarantine`：其余 A1–C

Runner 用法：

```bash
python -m src.run_benchmark \
  --seed seeds/a1_valuation.jsonl \
  --temporal-index data/task_temporal_index.jsonl \
  --paper-band T2 \
  --agent mock
```

官方分（任务等权）只接受 T2、`official_temporal_eligible=true` 且
`review_status=reviewed` 的记录。`modeled_*` / `heuristic_*` 可用日、
`non_pit_fundamentals`、缺失官方事件证据等 blocking flags 均不可晋升 reviewed。

## `status` 枚举

| 值 | 含义 | 用途 |
|----|------|------|
| `template` | 模板样例 | 仅用于 schema 验证与 prompt 对齐，**不能**用于 baseline |
| `ready` | 就绪 | 字段完整，可用于 baseline 测试 |
| `validated` | 已校验 | 经过数据与指标校验，可用于正式 leaderboard 评测 |

## 本阶段（v0.2.0）状态约定

| 任务 | 文件位置 | `status` | `ground_truth` |
|------|----------|----------|----------------|
| A1 | `seeds/a1_valuation.jsonl` | `ready` | **必须完整** |
| A2-F | `seeds/a2_fundamentals.jsonl` | `ready` | **必须完整** |
| A2-T | `seeds/a2_technical.jsonl` | `ready` | **必须完整** |
| A2-H | `seeds/a2_hybrid.jsonl` | `ready` | **必须完整** |
| B | `seeds/b_event.jsonl` | `ready`（当前 0 条） | **必须完整** |
| C | `seeds/c_financial_metric.jsonl` | `ready` | **必须完整** |
| D | `seeds/d_counterfactual.jsonl` | `ready` | **必须完整** |
| E | `seeds/e_formula.jsonl` | `ready` | **必须完整** |
| 模板样例 | `seeds/templates/*.jsonl` | `template` | 可为 `null` |

### D 题 `ground_truth` 格式

```json
{"logic_direction": "positive"}
```
或
```json
{"logic_direction": "negative"}
```

### E 题 `ground_truth` 格式

```json
{
  "correct_answer": 1714.29,
  "correct_formula": "Gordon Growth Model",
  "answer_unit": "CNY million"
}
```

`correct_answer` 必须为可核验的 `float`，不允许为 `null`。

## Prompt 与模板文件

- 未渲染的 prompt 模板存放在 `prompts/*.txt`
- 模板使用 `{variable_name}` 作为占位符
- JSONL 记录中的 `prompt` 字段必须是**渲染后**的完整字符串
- `metadata.prompt_template` 可记录对应的模板文件路径

## 本地校验

运行 `python scripts/validate.py` 可自动检查：

- 所有 `seeds/**/*.jsonl` 逐行可解析
- 统一字段完整性
- template / ready 状态与 `metadata.is_template` 一致
- D/E ready 文件不含 `PLACEHOLDER`
- D 题 `historical_price_series` 长度为 30
- `task_id` 全局唯一

## 任务类别速查

详见 [task_cards.md](./task_cards.md)。

| Category | 输出格式 |
|----------|----------|
| A1 | `bull`, `base`, `bear`, `reversion_horizon` |
| A2 | JSON 数组，股票代码排名 |
| B | `direction`, `probability_up` |
| C | `predicted_value` |
| D | `direction`, `reasoning` |
| E | `formula_used`, `answer`, `unit` |
