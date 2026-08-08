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

The current public dataset contains 136 ready records:

| Task | Description | HF config | Ready |
|------|-------------|-----------|------:|
| A1 | Single-stock valuation range prediction | `a1` | 20 |
| A2-F | Cross-sectional ranking with fundamentals | `a2_f` | 2 |
| A2-T | Cross-sectional ranking with technicals | `a2_t` | 2 |
| A2-H | Cross-sectional ranking with hybrid signals | `a2_h` | 2 |
| B | Event-driven direction prediction | `b` | 10 |
| C | Forward financial metric prediction | `c` | 76 |
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

Current distribution:

| Time Band | Count | Notes |
|-----------|------:|-------|
| T1 | 16 | Mostly formula tasks and synthetic counterfactuals |
| T2 | 116 | Most real date-bearing records |
| T3 | 4 | Synthetic future counterfactuals; real T3 labels need future data |

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

## Code Structure

```text
benchmark-research/
├── README.md
├── TODO.md
├── manifest.json
├── docs/
│   ├── schema.md
│   └── task_cards.md
├── prompts/
│   ├── a1_valuation.txt
│   └── ...
├── scripts/
│   ├── assign_time_bands.py
│   ├── export_hf_dataset.py
│   └── validate.py
└── src/
    ├── agents/
    ├── builders/
    ├── evaluators/
    ├── parsers/
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

The current builders start from manually downloaded CSV files. Future work will add provider interfaces for both A-shares and US stocks.

Planned abstractions:

- `get_price_history(symbol, start_date, end_date, market)`
- `get_fundamentals(symbol, as_of_date, market)`
- `get_events(symbol_or_index, start_date, end_date, market)`

Target markets:

- `CN_A` for A-shares
- `US` for US equities

Candidate providers are tracked in [`TODO.md`](TODO.md).

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
