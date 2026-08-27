#!/usr/bin/env python3
"""Export ready seeds into an HF Hub–compatible dataset folder (data only)."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


# config_name -> source seed file (relative to repo root)
CONFIGS: dict[str, str] = {
    "a1": "seeds/a1_valuation.jsonl",
    "a2_f": "seeds/a2_fundamentals.jsonl",
    "a2_t": "seeds/a2_technical.jsonl",
    "a2_h": "seeds/a2_hybrid.jsonl",
    "b": "seeds/b_event.jsonl",
    "c": "seeds/c_financial_metric.jsonl",
    "d": "seeds/d_counterfactual.jsonl",
    "e": "seeds/e_formula.jsonl",
}

TEMPORAL_INDEX = "data/task_temporal_index.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    """Load non-empty JSONL rows."""
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write JSONL rows (UTF-8, one object per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def attach_paper_temporal_fields(
    rows: list[dict],
    temporal_index: dict[str, dict],
) -> list[dict]:
    """Publish auditable paper-time fields with every HF row."""
    fields = (
        "forecast_origin",
        "forecast_origin_source",
        "outcome_available_at",
        "outcome_available_at_source",
        "outcome_evidence_url",
        "outcome_evidence_code",
        "paper_band",
        "paper_band_reason",
        "review_status",
        "review_method",
        "reviewed_at",
        "evidence_hash",
        "quality_flags",
        "official_temporal_eligible",
        "backbone_training_cutoff",
        "guard_days",
        "experiment_as_of",
    )
    enriched: list[dict] = []
    for row in rows:
        temporal = temporal_index.get(row["task_id"])
        if temporal is None:
            raise ValueError(f"Missing temporal index row for {row['task_id']}")
        item = dict(row)
        item.update({field: temporal.get(field) for field in fields})
        enriched.append(item)
    return enriched


def build_readme(counts: dict[str, int]) -> str:
    """Build the HF dataset card with multi-config YAML."""
    total = sum(counts.values())
    config_yaml = "\n".join(
        [
            f"- config_name: {name}\n"
            f"  data_files:\n"
            f"  - split: train\n"
            f"    path: data/{name}/train.jsonl"
            + ("\n  default: true" if name == "a1" else "")
            for name in CONFIGS
        ]
    )
    table = "\n".join(
        f"| `{name}` | {counts[name]} |" for name in CONFIGS
    )
    return f"""---
license: cc-by-4.0
language:
- zh
pretty_name: Benchmark Research
tags:
- finance
- benchmark
- deep-research
- agent-evaluation
size_categories:
- n<1K
configs:
{config_yaml}
---

# Benchmark Research

面向金融 Deep Research Agent 的评测数据集（**仅数据**）。

代码、builder、prompt 模板与评测脚本在独立代码仓库维护；本 Hub 仓库只发布标准化 ready seeds，支持按子集按需加载。

## 快速开始

```python
from datasets import load_dataset

# 按题型子集加载（推荐）
a1 = load_dataset("sselaine27/benchmark-research", "a1")
c = load_dataset("sselaine27/benchmark-research", "c")
d = load_dataset("sselaine27/benchmark-research", "d")

print(a1["train"][0]["task_id"])
print(a1["train"][0]["prompt"][:200])

# 按时间层筛选
t2 = a1["train"].filter(lambda x: x["time_band"] == "T2")
```

可用 config：`a1` / `a2_f` / `a2_t` / `a2_h` / `b` / `c` / `d` / `e`  
默认 config 为 `a1`。

## 规模（v0.8.0）

| config | ready 条数 |
|--------|-----------|
{table}
| **合计** | **{total}** |

### 实验身份（paper 主口径）

- `backbone_model = gpt-4.1`
- `backbone_training_cutoff = 2024-06-30`（OpenAI 仅声明 “June 2024”；本库按月末保守处理）
- `guard_days = 30` → T1 outcome ≤ `2024-05-31`，T2 origin ≥ `2024-07-30`
- `experiment_as_of = 2026-08-17`

**不兼容声明：** 旧 Hub pin（339 题 / `model_training_cutoff=2024-06-01`）为 legacy identity，不得与 v0.8 paper_band / C1 表混比。

## 字段说明

每行一条评测题（JSON object）：

| 字段 | 说明 |
|------|------|
| `task_id` | 全局唯一 ID |
| `category` | A1 / A2 / B / C / D / E |
| `variant` | 子变体（如 F/T/H、earnings） |
| `cutoff_date` | 用于时间分层的截止日期 |
| `time_band` | T1 / T2 / T3（legacy；论文请用 `paper_band`） |
| `forecast_origin` | 预测时点 |
| `outcome_available_at` | 结果可用日；结合 `outcome_available_at_source` 判断是否为观测值或估计值 |
| `paper_band` | GPT-4.1 论文口径 T1 / T2 / T3 / D / E |
| `status` | ready |
| `seed` | 结构化输入 |
| `prompt` | 已渲染完整 prompt |
| `expected_output` | 输出 schema 说明 |
| `ground_truth` | 评测标签 |
| `metadata` | 元信息 |

## 时间分层

本数据集按可复算规则标注 legacy `time_band`（仅按 `cutoff_date`）：

- `T1`：`cutoff_date <= model_training_cutoff`，可能存在预训练数据泄露
- `T2`：`model_training_cutoff < cutoff_date < reference_current_date`
- `T3`：`cutoff_date >= reference_current_date`，用于未来预测能力测试

默认 legacy 参数（与 paper 身份对齐 cutoff 月，但规则不同）：

- `model_training_cutoff = 2024-06-30`
- `reference_current_date = 2026-08-17`

论文实验请使用侧车 `paper_band`（见代码仓 `docs/schema.md` / `docs/c1_pairing_contract.md`），不要直接用 legacy `time_band` 做 C1。

## 仓库边界

本仓库**只包含**：

- `README.md`（dataset card）
- `data/<config>/train.jsonl`（ready seeds）

**不包含**代码、scripts、prompts、原始构建 CSV、运行结果等。

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Export HF-only dataset folder.")
    parser.add_argument(
        "--output",
        default="hf_dataset",
        help="Output directory for the HF data-only package.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing output directory before export.",
    )
    return parser.parse_args()


def main() -> int:
    """Export ready seeds into hf_dataset/."""
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    out = root / args.output

    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    temporal_rows = load_jsonl(root / TEMPORAL_INDEX)
    temporal_index = {row["task_id"]: row for row in temporal_rows}
    if not temporal_index:
        raise SystemExit(
            f"Missing {TEMPORAL_INDEX}; run scripts/classify_paper_temporal.py before export."
        )

    counts: dict[str, int] = {}
    for config_name, rel in CONFIGS.items():
        rows = load_jsonl(root / rel)
        # Only export ready records
        rows = [r for r in rows if r.get("status") == "ready"]
        rows = attach_paper_temporal_fields(rows, temporal_index)
        rows = [r for r in rows if r.get("paper_band") != "quarantine"]
        write_jsonl(out / "data" / config_name / "train.jsonl", rows)
        counts[config_name] = len(rows)
        print(f"  {config_name}: {len(rows)}")

    (out / "README.md").write_text(build_readme(counts), encoding="utf-8")

    print(f"Exported to {out} (total ready={sum(counts.values())})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
