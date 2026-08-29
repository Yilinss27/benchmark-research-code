# Benchmark Research 数据现状（v0.9.0）

**版本：** v0.9.0（release candidate）
**代码仓：** [Yilinss27/benchmark-research-code](https://github.com/Yilinss27/benchmark-research-code)  
**数据仓：** [sselaine27/benchmark-research](https://huggingface.co/datasets/sselaine27/benchmark-research)  
**统计日：** 2026-08-27

---

## 1. 概览

当前正式题库 **1120** 条 `ready`。另有跨时间对齐实验面板 **aligned_v1**（1,744 条，不覆盖主库）。

| 能力 | 现状 |
|------|------|
| 时间戳 | 每题有 `forecast_origin`、`outcome_available_at` |
| 自动分层 | 评测按 `paper_band`（T1 / T2 / …）筛选，不依赖 legacy `time_band` |
| 市场 | `CN_A` / `US` / `HK` |
| 单题生成 | `python -m src.data_generator --task … --market … --cutoff-date …` |
| **面板生成** | `python -m src.data_generator --panel --cutoff-date … --horizon 30` |
| 官方分 | 仅聚合 **T2**，任务等权 |

论文时间带原始规模：**T1 = 404**，**T2 = 423**。同时满足观测证据、
`official_temporal_eligible=true` 与 `review_status=reviewed` 的记录为
**T1 = 292、T2 = 243**。A2-F / A2-H 的论文 T1 各 **32**（≥30）。

主库 T1/T2 **总量够但结构不对称**（详见 [`docs/t1_t2_alignment_gaps.md`](t1_t2_alignment_gaps.md)）。可横比实验请用 aligned panel。

---

## 2. 分题型规模（主库）

| 题型 | ready | 论文 T1 | 论文 T2 | 说明 |
|------|------:|--------:|--------:|------|
| A1 | 244 | 198 | 46 | 估值预测 |
| A2-F | 112 | 46 | 66 | 基本面排序 |
| A2-T | 161 | 95 | 66 | 技术面排序 |
| A2-H | 110 | 46 | 64 | 混合排序 |
| B | 139 | 52 | 86 | earnings + 13 条官方 macro |
| C | 294 | 0 | 294 | 财务指标（官方+Yahoo 双轨） |
| D | 30 | — | — | 反事实探针（`paper_band=D`） |
| E | 30 | — | — | 公式探针（`paper_band=E`） |
| **合计** | **1120** | **437** | **622** | quarantine = 1 |

`python scripts/validate.py`：通过。

### 市场分布

| 题型 | CN_A | US | HK |
|------|-----:|---:|---:|
| A1 | 180 | 31 | 33 |
| A2-F | 50 | 30 | 32 |
| A2-T | 82 | 40 | 39 |
| A2-H | 48 | 30 | 32 |
| B | 43 | 49 | 47 |
| C | 156 | 66 | 72 |

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

旧 Hub pin（339 题，`model_training_cutoff=2024-06-01`）属于 legacy identity，仅用于历史复现，不与当前 v0.8 结果混表。

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
| cutoff | 14 组显式 T1↔T2 配对，包含 `2025-12-31` 锚点 |
| horizon | 30 天 |
| 产出 | `seeds/aligned/`（**不改主库 1120**） |
| 规模 | **T1=872 / T2=872**，逐 pair 结构对称 |

| 题型 | T1 | T2 |
|------|---:|---:|
| A1 | 392 | 392 |
| A2-F | 156 | 156 |
| A2-T | 168 | 168 |
| A2-H | 156 | 156 |

同一 `panel_pair_id` 内股票集合和 cohort 完全对齐，仅 cutoff 不同；同一 band
的 30 天窗口内部不重叠。每个市场×题型两侧累计均 ≥50。

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
  --report data/aligned_paper_temporal_report.json \
  --enrich-yahoo --enrich-official
python scripts/review_temporal_index.py \
  --index data/aligned_task_temporal_index.jsonl
python scripts/validate_aligned_panel.py

# mock 冒烟（T1 / T2 结构一致）
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
| CN_A | 大金融 / 消费 / 科技 / 医药 / 能源 / 制造基建 / 通信 |
| US | mega / tech / financial / healthcare / consumer / industrial / energy |
| HK | 蓝筹 / 科技 / 金融 / 消费 / 央企 / 医药 / 公用通信 |

**mega-cap：** 超大市值公司（美股语境常指约 $2000 亿以上巨头）。`us_mega` 跨行业，`us_tech` 偏科技赛道。

---

## 6. 官方分

| 约定 | 实现 |
|------|------|
| 主榜只看 T2 | `official_score` 过滤 `paper_band == T2` |
| 时间证据 | 同时要求 `official_temporal_eligible == true` 且 `review_status == reviewed` |
| 任务等权 | 各题型先均值，再跨题型等权 |

当前官方 T2 可用 **136** 条（`official_temporal_eligible=true` 且 `review_status=reviewed`）；
13 条 macro 均保存官方发布页与 release-adjusted 反应交易日。
C 目前为双轨：`official_filing_primary` 与 `research_yahoo` 并行，后者保留
`non_pit_fundamentals` 标记，不进入官方分。

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
| D / E | 各 30 条，支持脚本化量产与抽检 |
| T3 | D 已覆盖 T3 切片；其他主任务仍以 T1/T2 为主 |
| 泄漏校准 | draft 样例，非正式大规模标注集 |
| B | 13 条 macro 使用 BLS / 国家统计局 / 香港政府统计处官方来源；earnings 主体已补齐官方 URL |
| C | 294 条 C 题完成双轨标记；官方轨持续通过 filing snapshot 管线补值 |
| Yahoo 基本面 | 明确标记 `non_pit_fundamentals`、仅作 research；官方分不再默认接受 |

后续优先：按需扩 aligned cutoff 对数 → B/C 对齐面板 → 已结算 T3 → 泄漏校准。

---

## 8. 仓库边界

| 位置 | 内容 |
|------|------|
| GitHub | 代码、脚本、文档、`configs/`、manifest |
| Hugging Face | 仅主库 ready 评测数据（1119 条，剔除 quarantine 后导出）；每行直接携带 paper temporal 字段 |
| 本地不进代码仓 | `seeds/`（含 `aligned/`）、`data/`、`hf_dataset/`、`results/` |
