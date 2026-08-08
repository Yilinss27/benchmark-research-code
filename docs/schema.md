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
    "model_training_cutoff": "2024-06-01",
    "reference_current_date": "2026-08-08",
    "rule": "T1: cutoff_date <= model_training_cutoff; T2: model_training_cutoff < cutoff_date < reference_current_date; T3: cutoff_date >= reference_current_date"
  },
  "notes": "可选说明"
}
```

- `is_template: true` — 模板样例，不用于正式评测
- `is_template: false` — 可用于 baseline / 正式评测
- `temporal_split` — ready seeds 必填，用于复现 T1/T2/T3 时间泄漏切分

## 时间分层（T1/T2/T3）

默认发布参数：

- `model_training_cutoff = 2024-06-01`
- `reference_current_date = 2026-08-08`

切分规则：

- `T1`：`cutoff_date <= model_training_cutoff`
- `T2`：`model_training_cutoff < cutoff_date < reference_current_date`
- `T3`：`cutoff_date >= reference_current_date`

注意：严格来说，T1/T2 取决于具体模型的训练截止日期。评测不同模型时，应使用 `scripts/assign_time_bands.py` 按该模型训练截止日重新计算。

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
