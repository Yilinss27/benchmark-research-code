# Benchmark Research（代码仓库）

面向金融 Deep Research Agent 的评测**代码与造题**仓库。

> **数据与代码已解耦**：Hugging Face 上只发布标准化 ready seeds；GitHub 代码仓只保留 builder / prompt / runner / docs / 导出脚本，不上传本地下载的金融原始数据或 HF 导出数据包。

| 仓库 | 内容 | 地址 |
|------|------|------|
| **Hugging Face（仅数据）** | `data/<config>/train.jsonl` + dataset card | https://huggingface.co/datasets/sselaine27/benchmark-research |
| **GitHub（仅代码）** | `src/` `prompts/` `scripts/` `docs/` | 待创建 |

## 版本与状态

**v0.4.0 — temporal split metadata + data/code decoupled**

| 类别 | Ready | HF config | 本版变化 |
|------|------:|-----------|----------|
| A1 | 20 | `a1` | 不变（待更多行情 CSV） |
| A2-F | 2 | `a2_f` | 不变（待更多 cohort） |
| A2-T | 2 | `a2_t` | 不变 |
| A2-H | 2 | `a2_h` | 不变 |
| B | 10 | `b` | **新建** earnings×5 + macro×5 |
| C | 76 | `c` | 不变 |
| D | 12 | `d` | **6→12** |
| E | 12 | `e` | **5→12** |
| **合计** | **136** | — | — |

## HF 标准加载

```python
from datasets import load_dataset

a1 = load_dataset("sselaine27/benchmark-research", "a1")
b = load_dataset("sselaine27/benchmark-research", "b")
c = load_dataset("sselaine27/benchmark-research", "c")

print(a1["train"][0]["prompt"][:200])

# 例如只评估 T2
a1_t2 = a1["train"].filter(lambda x: x["time_band"] == "T2")
```

本地预览导出包：

```python
from datasets import load_dataset
ds = load_dataset("./hf_dataset", "a1")
```

## 时间泄漏评估分层

每条 ready seed 都带有：

- 顶层 `cutoff_date`
- 顶层 `time_band`
- `metadata.temporal_split`

默认发布切分参数：

- `model_training_cutoff = 2024-06-01`
- `reference_current_date = 2026-08-08`

规则：

- `T1`：`cutoff_date <= model_training_cutoff`，可能存在训练数据泄露
- `T2`：`model_training_cutoff < cutoff_date < reference_current_date`
- `T3`：`cutoff_date >= reference_current_date`，用于未来预测能力测试

当前分布：

| time_band | 条数 | 说明 |
|-----------|-----:|------|
| T1 | 16 | 主要是 atemporal formula 与部分 synthetic counterfactual |
| T2 | 116 | 当前大多数真实 cutoff/date-bearing 题 |
| T3 | 4 | synthetic future counterfactual；真实 T3 仍需未来标签补充 |

不同模型训练截止日不同；严谨评测时用脚本重算：

```bash
python scripts/assign_time_bands.py \
  --training-cutoff 2024-06-01 \
  --current-date 2026-08-08 \
  --in-place
```

随后重新导出 HF 数据包：

```bash
python scripts/export_hf_dataset.py --clean
```

## 导出并上传 HF（仅数据）

```bash
# 1) 从 seeds/ 导出纯数据包
python scripts/export_hf_dataset.py --clean

# 2) 上传 hf_dataset/ 内容到 HF，并删除远端旧代码文件
hf upload sselaine27/benchmark-research hf_dataset . --type dataset \
  --commit-message "v0.4.0: add temporal split metadata" \
  --delete "src/**" \
  --delete "scripts/**" \
  --delete "prompts/**" \
  --delete "docs/**" \
  --delete "configs/**" \
  --delete "seeds/**" \
  --delete "data/*.csv" \
  --delete "TODO.md" \
  --delete "manifest.json"
```

## 造题自动化

```bash
# A1 / A2 / B / C：CSV → ready JSONL
python -m src.builders.a1_from_csv_builder
python -m src.builders.a2_fundamentals_from_csv_builder
python -m src.builders.a2_technicals_from_csv_builder
python -m src.builders.a2_hybrid_from_csv_builder
python -m src.builders.b_event_from_csv_builder
python -m src.builders.c_financial_metric_from_csv_builder

# 校验 → 导出 HF 包
python scripts/validate.py
python scripts/export_hf_dataset.py --clean
```

## 文件结构（本仓库）

```
benchmark-research/
├── README.md                 # 本文件（代码仓说明）
├── manifest.json
├── TODO.md
├── prompts/                  # prompt 模板（不上 HF）
├── src/                      # builders / parsers / evaluators / runner
├── scripts/
│   ├── validate.py
│   ├── assign_time_bands.py
│   └── export_hf_dataset.py  # 本地生成 hf_dataset/，不上 GitHub
├── docs/
├── data/                     # 本地下载/接口拉取数据，gitignore
├── seeds/                    # 本地生成 ready seeds，gitignore
├── hf_dataset/               # 本地导出的 HF 数据包，gitignore
└── results/                  # benchmark 运行输出，gitignore
```

> 说明：`data/`、`seeds/`、`hf_dataset/` 是本地工作目录，不进入 GitHub 代码仓。公开数据请使用 Hugging Face 数据集。

## 任务总览

| ID | 任务 | 说明 | 状态 |
|----|------|------|------|
| A1 | 单股估值区间预测 | bull/base/bear + 修复期 | ready（20） |
| A2-F/T/H | 行业横截面排序 | 基本面 / 技术 / 混合 | ready（各 2） |
| B | 事件驱动方向预测 | earnings / macro | ready（10） |
| C | 财务指标前向预测 | MAPE / within_10pct | ready（76） |
| D | 反事实事件注入 | 逻辑方向判分 | ready（12） |
| E | 多步金融公式计算 | 精确数值 | ready（12） |

详细说明见 [`docs/task_cards.md`](docs/task_cards.md)。

## 本地运行 Benchmark

```bash
python -m src.run_benchmark \
  --seed seeds/e_formula.jsonl \
  --agent mock \
  --output results/mock_e
```

按模型训练截止日重算时间层，并在 `metrics_summary.json` 中输出 `by_time_band`：

```bash
python -m src.run_benchmark \
  --seed seeds/d_counterfactual.jsonl \
  --agent mock \
  --model-training-cutoff 2024-06-01 \
  --current-date 2026-08-08 \
  --output results/mock_d_temporal
```

只跑某个时间层：

```bash
python -m src.run_benchmark \
  --seed seeds/a1_valuation.jsonl \
  --agent mock \
  --model-training-cutoff 2026-01-01 \
  --current-date 2026-08-08 \
  --time-band T1 \
  --output results/mock_a1_t1
```

Hugging Face Inference baseline：

```bash
export HF_TOKEN=your_token_here
python -m src.run_benchmark \
  --seed seeds/e_formula.jsonl \
  --agent hf \
  --model Qwen/Qwen3-8B \
  --api-key-env HF_TOKEN \
  --output results/hf_e \
  --limit 2
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)

## 后续计划

- [ ] 扩充 A1/A2 源 CSV（行情与 cohort）
- [ ] 补齐 A2 fundamentals 历史快照，去掉 prototype fallback
- [ ] 公开版是否隐藏 A1 未来价格窗口
- [ ] 将本代码仓同步到独立 GitHub 仓库
