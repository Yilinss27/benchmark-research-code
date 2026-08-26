# Benchmark Research 数据现状（v0.7.0）

**版本：** v0.7.0（release candidate）  
**代码仓：** [Yilinss27/benchmark-research-code](https://github.com/Yilinss27/benchmark-research-code)  
**数据仓：** [sselaine27/benchmark-research](https://huggingface.co/datasets/sselaine27/benchmark-research)  
**统计日：** 2026-08-27

---

## 1. 概览

当前正式题库 **849** 条 `ready`（已剔除 quarantine）。另有跨时间对齐实验面板 **aligned_v1**（100 条，不覆盖主库）。

| 能力 | 现状 |
|------|------|
| 时间戳 | 每题有 `forecast_origin`、`outcome_available_at` |
| 自动分层 | 评测按 `paper_band`（T1 / T2 / …）筛选，不依赖 legacy `time_band` |
| 市场 | `CN_A` / `US` / `HK` |
| 单题生成 | `python -m src.data_generator --task … --market … --cutoff-date …` |
| **面板生成** | `python -m src.data_generator --panel --cutoff-date … --horizon 30` |
| 官方分 | 仅聚合 **T2**，任务等权 |

论文时间带原始规模：**T1 = 404**，**T2 = 421**；其中具备官方时间证据的
**T1 = 356、T2 = 288**。A2-F / A2-H 的论文 T1 各 **32**（≥30）。

主库 T1/T2 **总量够但结构不对称**（详见 [`docs/t1_t2_alignment_gaps.md`](t1_t2_alignment_gaps.md)）。可横比实验请用 aligned panel。

---

## 2. 分题型规模（主库）

| 题型 | ready | 论文 T1 | 论文 T2 | 说明 |
|------|------:|--------:|--------:|------|
| A1 | 228 | 182 | 46 | 估值预测 |
| A2-F | 98 | **32** | 66 | 基本面排序 |
| A2-T | 161 | 95 | 66 | 技术面排序 |
| A2-H | 96 | **32** | 64 | 混合排序 |
| B | 66 | 15 | 51 | 事件（earnings 为主） |
| C | 176 | 48 | 128 | 财务指标 |
| D | 12 | — | — | 反事实探针（`paper_band=D`） |
| E | 12 | — | — | 公式探针（`paper_band=E`） |
| **合计** | **849** | **404** | **421** | quarantine = 0 |

`python scripts/validate.py`：通过。

### 市场分布

| 题型 | CN_A | US | HK |
|------|-----:|---:|---:|
| A1 | 180 | 24 | 24 |
| A2-F | 50 | 24 | 24 |
| A2-T | 82 | 40 | 39 |
| A2-H | 48 | 24 | 24 |
| B | 43 | 11 | 12 |
| C | 156 | 10 | 10 |

---

## 3. 时间分层（论文口径）

| 参数 | 取值 |
|------|------|
| 基础模型 | `gpt-4.1` |
| 训练截止日 | `2024-06-30`（官方仅给出 “June 2024”，按月末保守处理） |
| Guard days | 30 |
| 实验日 as-of | `2026-08-17` |
| T1 | `outcome_available_at` ≤ `2024-05-31` |
| T2 | `forecast_origin` ≥ `2024-07-30` 且 `outcome_available_at` ≤ `2026-07-18` |
| T3 | `forecast_origin` ≥ `2026-08-17` |

**Guard days：** 训练截止日与实验日两侧各留 30 天缓冲，避免边界泄漏。GPT-4.1 的知识截止只精确到月份，因此不能假设为 6 月 1 日；改用 6 月 30 日后，新增落入空白带的 26 条题已删除，当前无 quarantine。

| 字段 | 用途 |
|------|------|
| legacy `time_band` | 仅按 `cutoff_date` 粗分，兼容旧流程 |
| **`paper_band`** | 论文实验与官方分使用（由 origin / outcome + guard 判定） |

索引与分类：`data/task_temporal_index.jsonl`，`scripts/classify_paper_temporal.py`。

---

## 4. Aligned panel（跨时间可横比）

配置：[`configs/aligned_panel_v1.json`](../configs/aligned_panel_v1.json)

| 项 | 取值 |
|----|------|
| 题型 | A1, A2-F, A2-T, A2-H |
| 市场 | CN_A / US / HK |
| T1 cutoff | `2023-12-29` |
| T2 cutoff | `2025-12-31`（25 年底窗） |
| horizon | 30 天 |
| 产出 | `seeds/aligned/`（**不改主库 849**） |
| 规模 | **T1=50 / T2=50**，结构对称 |

| 题型 | T1 | T2 |
|------|---:|---:|
| A1 | 26 | 26 |
| A2-F | 8 | 8 |
| A2-T | 8 | 8 |
| A2-H | 8 | 8 |

同一股票池 / cohort，仅 cutoff 不同，可直接做 T1↔T2 横比。

```bash
# 生成（换 cutoff 只改配置或 CLI）
python scripts/generate_aligned_panel.py --clean

# 或：API + cutoff → 全题型
python -m src.data_generator --panel --cutoff-date 2025-12-31 \
  --markets CN_A,US,HK --tasks A1,A2-F,A2-T,A2-H --horizon 30 \
  --output-dir seeds/aligned --panel-id aligned_v1

# 分类 + 对称校验
python scripts/classify_paper_temporal.py \
  --seed-dir seeds/aligned \
  --output data/aligned_task_temporal_index.jsonl \
  --report data/aligned_paper_temporal_report.json
python scripts/validate_aligned_panel.py

# mock 冒烟（T1 / T2 各 50 题，结构一致）
python -m src.run_benchmark --seed seeds/aligned/all.jsonl --agent mock \
  --temporal-index data/aligned_task_temporal_index.jsonl --paper-band T1 \
  --output results/aligned_smoke_t1
python -m src.run_benchmark --seed seeds/aligned/all.jsonl --agent mock \
  --temporal-index data/aligned_task_temporal_index.jsonl --paper-band T2 \
  --output results/aligned_smoke_t2
```

---

## 5. A2 cohort

每组约 12 只股票；成题门槛 ≥6 只有效。

| 市场 | cohort |
|------|--------|
| CN_A | 大金融 / 消费 / 科技 / 医药 |
| US | `us_mega`（超大市值龙头）/ `us_tech`（科技龙头） |
| HK | 港股蓝筹 / 港股科技 |

**mega-cap：** 超大市值公司（美股语境常指约 $2000 亿以上巨头）。`us_mega` 跨行业，`us_tech` 偏科技赛道。

---

## 6. 官方分

| 约定 | 实现 |
|------|------|
| 主榜只看 T2 | `official_score` 过滤 `paper_band == T2` |
| 时间证据 | 同时要求 `official_temporal_eligible == true` |
| 任务等权 | 各题型先均值，再跨题型等权 |

当前官方 T2 可用 **288** 条：A1=46、A2-F=66、A2-T=66、A2-H=64、
B-earnings=46。C 的 128 条 T2 因结果可用日仍是 filing-lag 估计，不进入官方分；
B-macro 5 条同样因缺少 outcome 证据被排除。

```bash
python -m src.run_benchmark \
  --seed seeds/aligned/all.jsonl \
  --temporal-index data/aligned_task_temporal_index.jsonl \
  --paper-band T2
```

---

## 7. D / E 与后续

| 项 | 现状 |
|----|------|
| D / E | 各 12 条，探针用途；一般不必为规模再扩 |
| T3 | 有前瞻模板；已结算正式题几乎为空；真 T3 应按「当日生成后 1–2 天内回测」 |
| 泄漏校准 | draft 样例，非正式大规模标注集 |
| B | earnings 的 outcome 为观测到的下一交易日；5 条 macro 缺证据，不进官方分 |
| C | 176 条保留作研究集；availability 为 filing-lag 模型估计，**不进官方分**，待补真实首次披露日 |
| Yahoo 基本面 | 非真 PIT；季报 +45 天 / 年报 +100 天近似 |

后续优先：按需扩 aligned cutoff 对数 → B/C 对齐面板 → 已结算 T3 → 泄漏校准。

---

## 8. 仓库边界

| 位置 | 内容 |
|------|------|
| GitHub | 代码、脚本、文档、`configs/`、manifest |
| Hugging Face | 仅主库 ready 评测数据（849 条）；每行直接携带 paper temporal 字段 |
| 本地不进代码仓 | `seeds/`（含 `aligned/`）、`data/`、`hf_dataset/`、`results/` |
