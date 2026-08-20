# Benchmark Research 数据现状总结（v0.7.0）

> 统计截止：2026-08-20  
> 代码仓：[Yilinss27/benchmark-research-code](https://github.com/Yilinss27/benchmark-research-code)  
> 数据仓：[sselaine27/benchmark-research](https://huggingface.co/datasets/sselaine27/benchmark-research)  
> 说明：本版已**删除全部 quarantine 题**（18 条），正式 ready = **875**。

---

## 1. 一句话结论

当前发布候选为 **v0.7.0**，共 **875** 条 `ready` 题目。论文实验应使用 `paper_band`（来自 `data/task_temporal_index.jsonl`），**不要**直接用 seed 里的 legacy `time_band`。A2-F / A2-H 论文 T1 均已达到 **32** 题（≥30 目标）。

---

## 2. 总体规模

| 题型 | ready 条数 | HF config |
|------|-----------|-----------|
| A1 | 228 | `a1` |
| A2-F | 106 | `a2_f` |
| A2-T | 169 | `a2_t` |
| A2-H | 104 | `a2_h` |
| B | 68 | `b` |
| C | 176 | `c` |
| D | 12 | `d` |
| E | 12 | `e` |
| **合计** | **875** | — |

`python scripts/validate.py`：通过。

---

## 3. 论文时间带（官方口径）

### 3.1 参数

| 参数 | 值 |
|------|-----|
| backbone training cutoff | `2024-06-01` |
| guard days | 30 |
| experiment as-of | `2026-08-17` |
| T1：`outcome_available_at` ≤ | `2024-05-02` |
| T2：`forecast_origin` ≥ | `2024-07-01` |
| T2：`outcome_available_at` ≤ | `2026-07-18` |
| T3：`forecast_origin` ≥ | `2026-08-17` |

#### 注解：guard days 是什么？

**guard days（30 天）** 是围绕关键时间点的安全缓冲，避免「刚好踩在 cutoff 边上」的题被误分进 T1/T2：

| 边界 | 计算 | 含义 |
|------|------|------|
| T1 上沿 | `2024-06-01 − 30d` → `2024-05-02` | 结果须在训练截止前至少 30 天已公开 |
| T2 下沿 | `2024-06-01 + 30d` → `2024-07-01` | 预测起点须在训练截止后至少 30 天 |
| T2 上沿 | `2026-08-17 − 30d` → `2026-07-18` | 结果须在实验日前至少 30 天已结算 |

落在中间空白带（如 `2024-05-03`～`2024-06-30`）的题原先会进 quarantine；**v0.7.0 已从题库删除这类题**。

### 3.2 全库分布

| paper_band | 条数 |
|------------|------|
| T1 | 404 |
| T2 | 447 |
| D | 12 |
| E | 12 |
| quarantine | **0**（已删除） |

#### 注解：quarantine 曾是什么？为何删除？

**quarantine** = 进不了干净 T1 / T2 / T3 的题，不当论文主结果。删除前共 18 条，主要两类：

1. **guard 空白带**（如 `2024-06-28` 的 A2 题）：既不满足 T1，也不满足 T2  
2. **质量问题**（如 A2-H `fundamentals_after_origin`）：基本面晚于预测起点，有泄漏风险  

已从 `seeds/` 物理删除并重新分类；当前 index 中 **quarantine = 0**。

### 3.3 分题型 × paper_band

| 题型 | T1 | T2 | 其他 |
|------|----|----|------|
| A1 | 182 | 46 | — |
| A2-F | **32** | 74 | — |
| A2-T | 95 | 74 | — |
| A2-H | **32** | 72 | — |
| B-earnings | 15 | 48 | — |
| B-macro | — | 5 | — |
| C | 48 | 128 | — |
| D | — | — | D=12 |
| E | — | — | E=12 |

质量标记（非阻断）：`missing_outcome_evidence`×5。

#### 注解：D / E 要不要再扩？

一般 **不必为冲规模去扩**，除非论文专门写这两类：

| 题型 | 现在 | 角色 | 建议 |
|------|------|------|------|
| **D** 反事实 | 12 | 能力/对照探针，非主榜 | 小样本即可；写专节时可扩到 ~20–30 |
| **E** 公式 | 12 | 近乎确定性检查 / 校准 | 小样本够用 |

它们在 `paper_band` 里直接标成 `D` / `E`，**不走 T1/T2 时间几何**，也不进官方 T2 任务等权主分。若还要加数据，优先：主任务 T2、已结算 T3、泄漏校准扩量。

### 3.4 与 legacy `time_band` 的关系

- Seed 上的 `time_band` 仅按 `cutoff_date` 粗分，用于兼容旧流程。
- 论文实验、官方分、泄漏分析请用：
  - `data/task_temporal_index.jsonl`
  - `python scripts/classify_paper_temporal.py`
  - `src/run_benchmark.py --paper-band T2` + 任务等权官方分

---

## 4. 市场覆盖

| 题型 | CN_A | US | HK | 备注 |
|------|------|----|----|------|
| A1 | 180 | 24 | 24 | — |
| A2-F | 54 | 26 | 26 | 删 quarantine 后略减 |
| A2-T | 86 | 42 | 41 | 同上 |
| A2-H | 52 | 26 | 26 | 同上 |
| B | 44 | 12 | 12 | 多为 earnings |
| C | 156 | 10 | 10 | 删 4 条 quarantine |
| D / E | — | — | — | 无市场字段 |

---

## 5. A2 cohort 结构（v0.7 扩量后）

每个 cohort 目标 **12** 只股票；成题门槛仍为 ≥6 只有价格（A2-T）或价格+基本面（A2-F/H）。

### CN_A（4 个）

| cohort_key | 行业 |
|------------|------|
| `financial` | 大金融 |
| `consumer` | 消费龙头 |
| `tech` | 科技成长 |
| `pharma` | 医药健康 |

### US（2 个）

| cohort_key | 行业 | 说明 |
|------------|------|------|
| `us_mega` | US mega-cap | 见下方注解 |
| `us_tech` | US tech leaders | 科技龙头组 |

### HK（2 个）

| cohort_key | 行业 |
|------------|------|
| `hk_bluechip` | 港股蓝筹 |
| `hk_tech` | 港股科技 |

#### 注解：mega-cap 是什么？

**mega-cap（超大市值）** 一般指市值处于市场最顶层的公司（美股语境常指约 **$2000 亿以上** 的巨头，具体门槛随市场变化）。本库的 `us_mega` cohort 放的是 Apple、Microsoft、Alphabet、Amazon、JPM、JNJ、Meta、NVIDIA 等跨行业超级大盘股，用来做「美股龙头组内排序」，与更聚焦半导体/软件的 `us_tech` 区分。

### 论文 T1 按 cohort（A2-F / A2-H）

各 **32** 题 = **8 cohort × 4 个 T1 cutoff**（每个 cohort 4 题）：

`2023-06-30`、`2023-09-29`、`2023-12-29`、`2024-03-29`

| cohort | A2-F T1 | A2-H T1 |
|--------|---------|---------|
| financial / consumer / tech / pharma | 各 4 | 各 4 |
| us_mega / us_tech | 各 4 | 各 4 |
| hk_bluechip / hk_tech | 各 4 | 各 4 |

A2-T 论文 T1 为 **95**（技术面不依赖 Yahoo 估值快照，历史 cutoff 成题更多）。

---

## 6. 仓库边界

| 位置 | 内容 |
|------|------|
| GitHub 代码仓 | `src/`、`prompts/`、`scripts/`、`docs/`、`calibration/`、`manifest.json` |
| Hugging Face 数据仓 | `README.md` + `data/<config>/train.jsonl`（仅 ready seeds） |
| 本地不提交 | `data/`（含 temporal index、Yahoo cache）、`seeds/`、`hf_dataset/`、`results/` |

---

## 7. 仍为脚手架 / 未完全闭环项

| 项 | 状态 |
|----|------|
| T3 前瞻题 | `seeds/t3_forward.jsonl` 有模板；已结算 T3 几乎为空 |
| 泄漏校准包 | `calibration/leakage_probe_v1.json` 为 draft 样例，非正式大规模标注集 |
| B/C outcome | 多数已 heuristic / Yahoo 回填；少数仍有 `missing_outcome_evidence` |
| quarantine | **已删除**（原 A2-H 污染题一并移除） |

---

## 8. 常用命令

```bash
# 校验
python scripts/validate.py

# 论文时间带分类（可 --enrich-yahoo）
python scripts/classify_paper_temporal.py --enrich-yahoo

# 仅跑论文 T2 + 官方任务等权分
python -m src.run_benchmark --temporal-index data/task_temporal_index.jsonl --paper-band T2

# 导出 HF 包
python scripts/export_hf_dataset.py --clean
```

---

## 9. 版本对照（简）

| 版本 | ready | 要点 |
|------|-------|------|
| v0.5.x | ~196–339 | Yahoo 多市场 A1 / A2-T 配对起步 |
| v0.6.0 | 339 | A2-F/H、B、C 扩美股/港股；legacy time_band |
| **v0.7.0** | **875** | 论文时间几何 + A2 cohort 扩宽/加行业；A2-F/H 论文 T1≥30；删除 quarantine；官方 T2 等权分 |
