# Temporal Changelog (paper_band)

Generated from `scripts/classify_paper_temporal.py --enrich-yahoo --enrich-official`
followed by `scripts/review_temporal_index.py`.

## Experiment constants

| Parameter | Value |
|-----------|-------|
| `backbone_model` | `gpt-4.1` |
| `backbone_training_cutoff` | `2024-06-30` (month-end conservative policy) |
| `guard_days` | `30` |
| `experiment_as_of` | `2026-08-17` |
| T1 `outcome_available_at` max | `2024-05-31` |
| T2 `forecast_origin` min | `2024-07-30` |
| T2 `outcome_available_at` max | `2026-07-18` |

## Ready record counts (v0.8 paper index)

| File | Ready rows |
|------|----------:|
| `seeds/a1_valuation.jsonl` | 228 |
| `seeds/a2_fundamentals.jsonl` | 98 |
| `seeds/a2_technical.jsonl` | 161 |
| `seeds/a2_hybrid.jsonl` | 96 |
| `seeds/b_event.jsonl` | 68 |
| `seeds/c_financial_metric.jsonl` | 176 |
| `seeds/d_counterfactual.jsonl` | 12 |
| `seeds/e_formula.jsonl` | 12 |
| **Total ready** | **851** |

Forward T3 templates (not in ready total): `seeds/t3_forward.jsonl` (84 templates, `outcome_status=pending`).

## paper_band distribution (851 ready)

| Band | Count |
|------|------:|
| T1 | 404 |
| T2 | 423 |
| quarantine | 0 |
| D | 12 |
| E | 12 |

Official temporal eligibility (observed/evidenced outcome availability):

| Band | Eligible | Raw |
|------|---------:|----:|
| T1 | 292 | 404 |
| T2 | 243 | 423 |

“Eligible” 同时要求观测证据、`official_temporal_eligible=true` 和
`review_status=reviewed`。Yahoo 基本面不是 point-in-time 数据，因此 A2-F/H
与 C 默认仅保留为研究集。

## By category (paper_band)

| Category | T1 | T2 | quarantine | Notes |
|----------|---:|---:|-----------:|-------|
| A1 | 182 | 46 | 0 | T1 target met |
| A2-F | 32 | 66 | 0 | T1/T2 targets met |
| A2-T | 95 | 66 | 0 | Both bands ≥30 |
| A2-H | 32 | 64 | 0 | T1/T2 targets met |
| B earnings | 15 | 46 | 0 | Observed next-session outcomes; 61/61 with official event URL |
| B macro | 0 | 7 | 0 | 7 first-party releases with observed reaction closes |
| C | 48 | 128 | 0 | Official first-publication dates resolved for all 176 rows |
| D | — | — | — | 12 × `D` band |
| E | — | — | — | 12 × `E` band |

## By category (reviewed + official eligible)

| Category | T1 | T2 | Notes |
|----------|---:|---:|-------|
| A1 | 182 | 46 | Fully reviewed and eligible |
| A2-F | 0 | 2 | Only reviewed rows without `non_pit_fundamentals` remain eligible |
| A2-T | 95 | 66 | Fully reviewed and eligible |
| A2-H | 0 | 0 | Yahoo fundamentals keep all rows research-only |
| B earnings | 15 | 46 | All rows reviewed and eligible |
| B macro | 0 | 7 | All 7 official macro rows reviewed and eligible |
| C | 0 | 76 | 100 Yahoo-sourced rows remain non-PIT (research-only) |

## Quality flags

| Flag | Count | Action |
|------|------:|--------|
| `non_pit_fundamentals` | 292 | Yahoo-based A2-F/H/C; research-only |

## Claim boundary (C1/C2)

- C1 can be claimed for strict paired A1/A2-T slices (`docs/c1_pairing_contract.md`).
- Full-category paired C1 is still blocked until B/C pairing panels are generated under the frozen contract.
- C2 is **not unlocked** in this round; T3 settlement remains pending.

## Artifacts

- Index: `data/task_temporal_index.jsonl`
- Report: `data/paper_temporal_report.json`
- Leakage calibration: `calibration/leakage_probe_v1.json` + `calibration/leakage_probe_manifest.json`

## Usage

```bash
python scripts/classify_paper_temporal.py --enrich-yahoo --enrich-official
python scripts/review_temporal_index.py
python -m src.run_benchmark \
  --seed seeds/a1_valuation.jsonl \
  --temporal-index data/task_temporal_index.jsonl \
  --paper-band T2 \
  --agent mock
```

Official leaderboard score: `metrics_summary.json` → `official_score` (task-equal mean on paper T2).
