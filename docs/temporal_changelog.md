# Temporal Changelog (paper_band)

Generated from `scripts/classify_paper_temporal.py --enrich-yahoo`.

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

## Ready record counts (v0.7 paper index)

| File | Ready rows |
|------|----------:|
| `seeds/a1_valuation.jsonl` | 228 |
| `seeds/a2_fundamentals.jsonl` | 98 |
| `seeds/a2_technical.jsonl` | 161 |
| `seeds/a2_hybrid.jsonl` | 96 |
| `seeds/b_event.jsonl` | 66 |
| `seeds/c_financial_metric.jsonl` | 176 |
| `seeds/d_counterfactual.jsonl` | 12 |
| `seeds/e_formula.jsonl` | 12 |
| **Total ready** | **849** |

Forward T3 templates (not in ready total): `seeds/t3_forward.jsonl` (84 templates, `outcome_status=pending`).

## paper_band distribution (849 ready)

| Band | Count |
|------|------:|
| T1 | 404 |
| T2 | 421 |
| quarantine | 0 |
| D | 12 |
| E | 12 |

Official temporal eligibility (observed/evidenced outcome availability):

| Band | Eligible | Raw |
|------|---------:|----:|
| T1 | 356 | 404 |
| T2 | 288 | 421 |

C remains available as a research set, but its filing-lag availability is modeled rather
than an observed first-publication date, so it is excluded from the official score.

## By category (paper_band)

| Category | T1 | T2 | quarantine | Notes |
|----------|---:|---:|-----------:|-------|
| A1 | 182 | 46 | 0 | T1 target met |
| A2-F | 32 | 66 | 0 | T1/T2 targets met |
| A2-T | 95 | 66 | 0 | Both bands ≥30 |
| A2-H | 32 | 64 | 0 | T1/T2 targets met |
| B earnings | 15 | 46 | 0 | Observed next-session outcomes |
| B macro | 0 | 5 | 0 | Legacy CSV only |
| C | 48 | 128 | 0 | Filing-lag availability is modeled; excluded from official score |
| D | — | — | — | 12 × `D` band |
| E | — | — | — | 12 × `E` band |

## Quality flags

| Flag | Count | Action |
|------|------:|--------|
| `modeled_outcome_availability` | 181 | C (176) + B macro (5); excluded from official score |
| `missing_outcome_evidence` | 5 | B macro; excluded from official score |

## Artifacts

- Index: `data/task_temporal_index.jsonl`
- Report: `data/paper_temporal_report.json`
- Leakage calibration: `calibration/leakage_probe_v1.json` + `calibration/leakage_probe_manifest.json`

## Usage

```bash
python scripts/classify_paper_temporal.py --enrich-yahoo
python -m src.run_benchmark \
  --seed seeds/a1_valuation.jsonl \
  --temporal-index data/task_temporal_index.jsonl \
  --paper-band T2 \
  --agent mock
```

Official leaderboard score: `metrics_summary.json` → `official_score` (task-equal mean on paper T2).
