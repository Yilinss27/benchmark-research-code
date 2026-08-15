# Task Cards

本文档为 Benchmark Research 各任务类别的详细说明卡片。

---

## A1 — 单股估值区间预测

**任务目的**  
考察 Agent 综合财务、市场、行业多源信息，对单只股票给出 bull/base/bear 三情景市场价值回归目标价及修复期判断。

**输入 seed 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `stock_code` | `str` | 股票代码 |
| `stock_name` | `str` | 股票名称 |
| `cutoff_date` | `str` | 信息截止日期（YYYY-MM-DD） |
| `cutoff_price` | `float \| null` | cutoff 日收盘价（写入 seed，非 Agent 输出） |
| `market` | `str` | 市场：`CN_A` / `US` / `HK` |
| `currency` | `str` | 报价货币：`CNY` / `USD` / `HKD` |

**输出格式**

```json
{
  "bull": 50.0,
  "base": 45.0,
  "bear": 40.0,
  "reversion_horizon": "3-6个月"
}
```

**Ground Truth 来源**  
cutoff 后 30/90/180/365 天真实收盘价；cutoff 日收盘价。需通过行情数据离线填充。

**评测指标**

- Target Price Error（对 base）
- Convergence Rate
- Range Hit Rate
- Reversion Horizon Hit Rate
- Format Valid Rate

**当前实现状态**：ready（`seeds/a1_valuation.jsonl`）。可用 `python -m src.data_generator --task A1 --market CN_A|US|HK --cutoff-date YYYY-MM-DD` 按 cutoff 成对生成；价格单位随 `currency` 渲染（元 / USD / HKD）。

---

## A2 — 行业横截面排序

**任务目的**  
在同行业 N 只股票中判断相对优劣，预测短期收益率排名。通过 F/T/H 三变体诊断 Agent 对基本面 vs 技术信号 vs 混合信号的利用能力。

**变体**

| Variant | 信号 | Ready 文件 | Template 样例 |
|---------|------|------------|---------------|
| F | 仅财务基本面 | `seeds/a2_fundamentals.jsonl` | `seeds/templates/a2_fundamentals_template.jsonl` |
| T | 仅技术指标 | `seeds/a2_technical.jsonl` | `seeds/templates/a2_technical_template.jsonl` |
| H | 基本面 + 技术 | `seeds/a2_hybrid.jsonl` | `seeds/templates/a2_hybrid_template.jsonl` |

**本地数据文件（`data/`）**

| 文件 | 用途 |
|------|------|
| `a2_price_series.csv` | A2-T/H 价格序列与收益 |
| `a2_fundamentals_snapshot.csv` | A2-F/H 基本面（估值快照） |
| `a2_cohorts_manual.csv` | A2-F cohort 定义 |
| `a1_price_snapshots.csv` | A1 单股估值快照 |
| `c_financial_snapshots.csv` | C 财务指标快照 |
| `b_events.csv` | B 事件驱动方向预测 |

**Fundamentals 匹配（A2-F/H）**

- 优先：`trading_day <= cutoff_date` 的最近一条（`on_or_before_cutoff`）
- Prototype fallback：无历史快照时使用全表最近一条（`prototype_fallback_nearest`），写入 `metadata.fundamentals_match_mode`
- 正式数据补齐 cutoff 当日或之前的历史估值后，fallback 将自动不再触发

**技术指标口径（A2-T/H）**

- 输入：cutoff 前最近 40 个交易日收盘价，升序，P0 为最后一根
- `rsi_14`：14 期简单平均 RSI（非 Wilder）
- `macd_histogram`：EMA12/26，DIF-DEA（9 日 EMA of DIF）
- `momentum_20d`：(P0-P_-20)/P_-20，P_-20 为倒数第 21 点
- `bollinger_zscore`：样本标准差 ddof=1；STD20==0 时为 null

**输入 seed 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `industry_name` | `str` | 行业名称 |
| `stock_list` | `list[{code, name}]` | 股票列表，建议 N ∈ [6, 15] |
| `cutoff_date` | `str` | 信息截止日期 |
| `prediction_window_days` | `int` | 预测窗口（交易日） |
| `signal_variant` | `str` | `F` / `T` / `H` |
| `market` | `str` | `CN_A` / `US` / `HK` |
| `currency` | `str` | `CNY` / `USD` / `HKD` |
| `fundamentals_dict` | `dict` | F/H 变体提供 |
| `technical_dict` | `dict` | T/H 变体提供 |

**输出格式**

```json
["688981", "688167", "002463", "002475", "000936", "002050"]
```

**Ground Truth 来源**  
`actual_returns[code] = (P_T - P_0) / P_0`，P_0 为 cutoff 日收盘价，P_T 为窗口结束日收盘价。

**评测指标**

- Spearman ρ
- Top-K Hit Rate（K = floor(N/3)）
- Long-Short Spread

**当前实现状态**：ready（`seeds/a2_fundamentals.jsonl`、`seeds/a2_technical.jsonl`、`seeds/a2_hybrid.jsonl`）。A2-F/T/H 均可由 `data_generator` 按市场/cutoff 配对生成。Yahoo 财务使用报告滞后期（季报 +45 天、年报 +100 天）近似 PIT；季报窗口不足时回退年报。CSV 路径仍可用于旧 cohort。

---

## B — 事件驱动方向预测

**任务目的**  
在特定事件后预测市场短期方向，核心考察 expectation gap 与事件逻辑推理。

**变体（当前 builder 支持）**

| Variant | 事件类型 |
|---------|----------|
| `earnings` | 财报发布 |
| `macro` | CPI/非农等宏观数据 |

**本地数据**：`data/b_events.csv`

**输入 seed 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `event_subtype` | `str` | `earnings` / `macro` |
| `event_description` | `str` | 事件完整描述 |
| `event_date` | `str` | 事件日期 |
| `cutoff_date` | `str` | 信息截止日期 |
| `stock_code` | `str` | 股票代码 |
| `stock_name` | `str` | 股票名称 |
| `market` | `str` | `CN_A` / `US` / `HK` |
| `currency` | `str` | `CNY` / `USD` / `HKD` |

**输出格式**

```json
{
  "direction": "up",
  "probability_up": 0.75
}
```

**Ground Truth 来源**  
`actual_direction`（`up`/`down`）与 `actual_return_pct`。

**评测指标**

- Directional Accuracy
- Brier Score

**当前实现状态**：ready。保留原 CSV 的 earnings/macro 题；Yahoo 路径为 CN_A/US/HK 补 T1/T2 财报事件（`cutoff_date = event_date`，收益用事件日前收盘到下一交易日收盘）。macro 大规模扩充仍待补。

---

## C — 财务指标前向预测

**任务目的**  
从非结构化文本中推断下一季度特定财务指标数值，重点选取需跨表推理的「非直觉」指标。

**本地数据**：`data/c_financial_snapshots.csv`

**输入 seed 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `stock_code` | `str` | 股票代码 |
| `stock_name` | `str` | 股票名称 |
| `cutoff_date` | `str` | 信息截止日期 |
| `metric_name` | `str` | 目标指标名称 |
| `report_period_historical` | `str` | 历史报告期 |
| `historical_value` | `float` | 历史指标值 |
| `report_period_future` | `str` | 目标报告期 |
| `market` | `str` | `CN_A` / `US` / `HK` |
| `currency` | `str` | `CNY` / `USD` / `HKD` |

**输出格式**

```json
{
  "predicted_value": 91.5
}
```

**Ground Truth 来源**  
`future_value`（目标报告期实际值）；为空则 `status=template`。

**评测指标**

- MAPE
- within_10pct（MAPE ≤ 10%）

**当前实现状态**：builder 可从 CSV 批量生成 ready/template seeds；`data_generator` 可用 Yahoo 财报为 A1 股票池补 T1/T2 与 US/HK。T1 因 Yahoo 季报窗口短，通常回退到相邻年报。

---

## D — 反事实事件注入

**任务目的**  
给定价格序列 + 虚构新闻，评估 Agent 是否按金融逻辑推理，而非调用训练记忆或事后真实走势。Ground Truth 由假新闻逻辑方向预设，与真实历史行情无关。

**时间带**

| Band | 说明 |
|------|------|
| T1 | cutoff 早于模型知识截止日，检测记忆泄露 |
| T2 | 2024 年后切片，测纯逻辑 |
| T3 | 当前最新 K 线，可即时出题判卷 |

**输入 seed 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `stock_code` | `str` | 股票代码 |
| `stock_name` | `str` | 股票名称 |
| `historical_price_series` | `list[float]` | 30 日收盘价（从旧到新） |
| `counterfactual_news` | `str` | 虚构新闻，方向明确 |
| `expected_logic_direction` | `str` | `positive` / `negative` |
| `benchmark_id` | `str` | 超额基准（如沪深300） |

**输出格式**

```json
{
  "direction": "positive",
  "reasoning": "大额订单提升未来盈利预期，利好股价"
}
```

**Ground Truth 来源**  
由出题人按基本定价逻辑预设：`logic_direction = expected_logic_direction`，**非**事后行情反推。

**评测指标**

- Logic Adherence Rate（主指标）
- Leakage Score（T1 集）
- T1-T2 Gap
- Format Valid Rate

**当前实现状态**：`ready`（`seeds/d_counterfactual.jsonl`，6 条，覆盖 T1/T2/T3）

---

## E — 多步金融公式计算

**任务目的**  
给定完整财务/市场参数，Agent 需选择正确金融公式并精确执行多步计算。与 C 的区别：输入完全确定，答案有唯一数学真值。

**输入 seed 字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `problem_text` | `str` | 含全部必要参数的题目描述 |
| `topic_category` | `str` | `derivatives` / `fixed_income` / `corporate_finance` / `portfolio` |
| `difficulty` | `str` | `easy` / `medium` / `hard` |

**输出格式**

```json
{
  "formula_used": "Gordon Growth Model",
  "answer": 1714.29,
  "unit": "CNY million"
}
```

**Ground Truth 来源**  
Python 函数精确计算 + 人工核验，存储于 `correct_answer` / `correct_formula` / `answer_unit`。

**评测指标**

- Exact Match（±0.2%）
- Formula Accuracy（LLM judge）
- Hard Subset Acc

**当前实现状态**：`ready`（`seeds/e_formula.jsonl`，5 条，覆盖四类 topic）
