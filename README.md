# Benchmark Research Code

This repository contains the code used to build and evaluate **Benchmark Research**, a small financial benchmark for Deep Research Agents and LLMs.

The benchmark is designed around one main question:

> Can a model reason about financial tasks without relying on leaked future knowledge?

To make that test easier, each ready record in the published dataset has a `cutoff_date` and a `time_band` (`T1` / `T2` / `T3`).

## Repository Split

Data and code are intentionally separated.

| Where | What It Contains | Link |
|------|------------------|------|
| Hugging Face dataset | Published ready benchmark records only | https://huggingface.co/datasets/sselaine27/benchmark-research |
| GitHub code repo | Builders, prompts, parsers, evaluators, runner, docs | https://github.com/Yilinss27/benchmark-research-code |

This GitHub repo does **not** publish local downloaded market data, generated seed files, benchmark outputs, or the Hugging Face export package. Those directories are ignored by Git:

- `data/`
- `seeds/`
- `hf_dataset/`
- `results/`

## What This Project Does

The codebase supports three workflows:

1. Build benchmark records from local financial CSV files.
2. Run LLM / agent baselines on ready records.
3. Export a data-only Hugging Face package.

The current public dataset contains 339 ready records:

| Task | Description | HF config | Ready |
|------|-------------|-----------|------:|
| A1 | Single-stock valuation range prediction | `a1` | 72 |
| A2-F | Cross-sectional ranking with fundamentals | `a2_f` | 10 |
| A2-T | Cross-sectional ranking with technicals | `a2_t` | 10 |
| A2-H | Cross-sectional ranking with hybrid signals | `a2_h` | 10 |
| B | Event-driven direction prediction | `b` | 33 |
| C | Forward financial metric prediction | `c` | 180 |
| D | Counterfactual event reasoning | `d` | 12 |
| E | Multi-step financial formula calculation | `e` | 12 |

Detailed task definitions are in [`docs/task_cards.md`](docs/task_cards.md). The record schema is described in [`docs/schema.md`](docs/schema.md).

## Quick Start: Load The Dataset

If you only want to inspect or use the data, load it from Hugging Face:

```python
from datasets import load_dataset

a1 = load_dataset("sselaine27/benchmark-research", "a1")
print(a1["train"][0]["task_id"])
print(a1["train"][0]["prompt"][:300])

# Example: keep only T2 records
a1_t2 = a1["train"].filter(lambda x: x["time_band"] == "T2")
```

Available configs:

```text
a1, a2_f, a2_t, a2_h, b, c, d, e
```

## Quick Start: Run A Local Benchmark

This repo does not include generated seed files. To run the local runner on the published data, first download the data files from Hugging Face:

```bash
hf download sselaine27/benchmark-research \
  --repo-type dataset \
  --local-dir hf_dataset \
  --include "data/e/train.jsonl" \
  --include "README.md"
```

Then run the mock baseline:

```bash
python -m src.run_benchmark \
  --seed hf_dataset/data/e/train.jsonl \
  --agent mock \
  --output results/mock_e
```

For Hugging Face Inference:

```bash
export HF_TOKEN=your_token_here

python -m src.run_benchmark \
  --seed hf_dataset/data/e/train.jsonl \
  --agent hf \
  --model Qwen/Qwen3-8B \
  --api-key-env HF_TOKEN \
  --output results/hf_e \
  --limit 2
```

## Temporal Split: T1 / T2 / T3

Each ready record has:

- `cutoff_date`
- `time_band`
- `metadata.temporal_split`

Default split parameters in the current release:

- `model_training_cutoff = 2024-06-01`
- `reference_current_date = 2026-08-08`

Rules:

- `T1`: `cutoff_date <= model_training_cutoff`
- `T2`: `model_training_cutoff < cutoff_date < reference_current_date`
- `T3`: `cutoff_date >= reference_current_date`

Published Hugging Face distribution (v0.6.0, 339 records):

| Time Band | Count | Notes |
|-----------|------:|-------|
| T1 | 118 | Includes A1/A2/B/C pairs around `2023-12-29`, plus formula and synthetic D |
| T2 | 217 | Includes legacy CSV rows and Yahoo pairs around `2026-01-30` |
| T3 | 4 | Synthetic future counterfactuals; real T3 labels need future data |

A1 records for `2026-01-30` leave the 365-day window as null because that date is not realized yet. A2-F/H, B (earnings), and C now have Yahoo-backed T1/T2 pairs on CN_A / US / HK in addition to the older CSV rows.

For a model with a different training cutoff, recompute the split:

```bash
python scripts/assign_time_bands.py \
  --training-cutoff 2024-06-01 \
  --current-date 2026-08-08 \
  --in-place
```

The runner can also recompute the split in memory without changing files:

```bash
python -m src.run_benchmark \
  --seed hf_dataset/data/e/train.jsonl \
  --agent mock \
  --model-training-cutoff 2024-06-01 \
  --current-date 2026-08-08 \
  --output results/mock_e_temporal
```

The output `metrics_summary.json` includes `by_time_band`.

## Build New Records

Builders read local CSV files from `data/` and write JSONL records to `seeds/`. These directories are local working directories and are not committed to GitHub.

Example builder commands:

```bash
python -m src.builders.a1_from_csv_builder \
  --csv data/a1_price_snapshots.csv \
  --output seeds/a1_valuation.jsonl

python -m src.builders.b_event_from_csv_builder \
  --csv data/b_events.csv \
  --output seeds/b_event.jsonl
```

After building records:

```bash
python scripts/assign_time_bands.py --in-place
python scripts/validate.py
python scripts/export_hf_dataset.py --clean
```

The export script writes a data-only package to `hf_dataset/`, which can then be uploaded to Hugging Face.

## Generate Paired T1 / T2 Records

Price-driven tasks can also be generated from Yahoo Finance (`yfinance`) without hand-built CSVs.

```bash
pip install -r requirements.txt

python -m src.data_generator \
  --task A1 \
  --market CN_A \
  --cutoff-date 2023-12-29 \
  --provider yahoo \
  --output seeds/a1_valuation.jsonl \
  --append
```

Supported this round:

- `--task A1 | A2-T | A2-F | A2-H | B | C`
- `--market CN_A | US | HK`

To fill paired cutoffs for the default universes (T1 `2023-12-29`, T2 `2026-01-30`) and keep existing legacy records:

```bash
python scripts/generate_t1_t2_pairs.py
```

### Paper temporal index (do not use legacy `time_band` for papers)

```bash
python scripts/classify_paper_temporal.py --enrich-yahoo
python scripts/expand_paper_data.py --all   # optional: expand A1/A2/B and T3 templates
```

Runner with official T2 filter:

```bash
python -m src.run_benchmark \
  --seed seeds/a1_valuation.jsonl \
  --temporal-index data/task_temporal_index.jsonl \
  --paper-band T2 \
  --agent mock
```

See [`docs/temporal_changelog.md`](docs/temporal_changelog.md) for paper_band counts.

Yahoo ticker mapping:

| Market | Example | Yahoo ticker |
|--------|---------|--------------|
| `CN_A` | `600519` / `000858` | `600519.SS` / `000858.SZ` |
| `US` | `AAPL` | `AAPL` |
| `HK` | `0700` | `0700.HK` |

Daily closes, statements, and earnings dates are cached under `data/cache/yahoo/` (gitignored). Yahoo is unofficial and not a true point-in-time fundamentals feed. This round approximates filing availability with a reporting lag: quarterly statements are treated as public 45 calendar days after period end, annual statements after 100 days. Yahoo quarterly history is short (~5 periods), so T1 A2-F/H/C usually fall back to annual statements.

Out of scope this round: real T3 labels (future prices are not realized yet) and a large B macro set.

## Temporal Leakage Papers

These papers motivate storing `cutoff_date` on every record and assigning `T1`/`T2`/`T3` at evaluation time:

- [Profit Mirage: Revisiting Information Leakage in LLM-based Financial Agents](https://arxiv.org/abs/2510.07920)
- [Time Travel is Cheating: DeepFund](https://arxiv.org/abs/2505.11065)
- [The Memorization Problem: Can We Trust LLMs' Economic Forecasts?](https://arxiv.org/abs/2504.14765)
- [A Test of Lookahead Bias in LLM Forecasts](https://arxiv.org/abs/2512.23847)

Records store `cutoff_date` only. `time_band` is recomputed with `scripts/assign_time_bands.py` or `python -m src.run_benchmark --model-training-cutoff ...`.

## Code Structure

```text
benchmark-research/
├── README.md
├── TODO.md
├── requirements.txt
├── manifest.json
├── docs/
│   ├── schema.md
│   └── task_cards.md
├── prompts/
│   ├── a1_valuation.txt
│   └── ...
├── scripts/
│   ├── assign_time_bands.py
│   ├── generate_t1_t2_pairs.py
│   ├── export_hf_dataset.py
│   └── validate.py
└── src/
    ├── agents/
    ├── builders/
    ├── data/
    │   ├── providers/
    │   └── universe.py
    ├── evaluators/
    ├── parsers/
    ├── data_generator.py
    ├── load_seeds.py
    └── run_benchmark.py
```

Local-only working directories:

```text
data/        # downloaded or API-fetched source data
seeds/       # generated ready JSONL records
hf_dataset/  # data-only package for Hugging Face
results/     # benchmark outputs
```

## Future Data Interface Plan

A1 / A2 / B (earnings) / C can be generated from Yahoo Finance (`python -m src.data_generator`). Yahoo financials are lagged, not a vendor PIT tape; B macro events and true T3 labels are still out of scope. Candidate paid PIT providers are tracked in [`TODO.md`](TODO.md).

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
