# Temporal Changelog (paper_band)

Generated from `scripts/classify_paper_temporal.py --enrich-yahoo`.

## Experiment constants

| Parameter | Value |
|-----------|-------|
| `backbone_training_cutoff` | `2024-06-01` |
| `guard_days` | `30` |
| `experiment_as_of` | `2026-08-17` |
| T1 `outcome_available_at` max | `2024-05-02` |
| T2 `forecast_origin` min | `2024-07-01` |
| T2 `outcome_available_at` max | `2026-07-18` |

## Ready record counts (v0.7 paper index)

| File | Ready rows |
|------|----------:|
| `seeds/a1_valuation.jsonl` | 228 |
| `seeds/a2_fundamentals.jsonl` | 55 |
| `seeds/a2_technical.jsonl` | 93 |
| `seeds/a2_hybrid.jsonl` | 55 |
| `seeds/b_event.jsonl` | 68 |
| `seeds/c_financial_metric.jsonl` | 180 |
| `seeds/d_counterfactual.jsonl` | 12 |
| `seeds/e_formula.jsonl` | 12 |
| **Total ready** | **703** |

Forward T3 templates (not in ready total): `seeds/t3_forward.jsonl` (84 templates, `outcome_status=pending`).

## paper_band distribution (703 ready)

| Band | Count |
|------|------:|
| T1 | 322 |
| T2 | 339 |
| quarantine | 18 |
| D | 12 |
| E | 12 |

## By category (paper_band)

| Category | T1 | T2 | quarantine | Notes |
|----------|---:|---:|-----------:|-------|
| A1 | 182 | 46 | 0 | T1 target met |
| A2-F | 13 | 38 | 4 | T2 target met; 4 legacy/fundamentals quarantine |
| A2-T | 51 | 38 | 4 | Both bands ≥30 |
| A2-H | 13 | 36 | 6 | T2 ≥30; legacy snapshot pollution quarantined |
| B earnings | 15 | 48 | 0 | Expanded universe |
| B macro | 0 | 5 | 0 | Legacy CSV only |
| C | 48 | 128 | 4 | Yahoo filing-lag outcomes |
| D | — | — | — | 12 × `D` band |
| E | — | — | — | 12 × `E` band |

## Quality flags

| Flag | Count | Action |
|------|------:|--------|
| `fundamentals_after_origin` | 2 | Legacy A2-H rows quarantined |
| `prototype_fallback_fundamentals` | 2 | Legacy A2-F CSV rows |
| `missing_outcome_evidence` | 5 | Needs manual review URLs |

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
