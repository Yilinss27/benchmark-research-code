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

## Ready record counts (v0.9 paper index)

| File | Ready rows |
|------|----------:|
| `seeds/a1_valuation.jsonl` | 244 |
| `seeds/a2_fundamentals.jsonl` | 112 |
| `seeds/a2_technical.jsonl` | 161 |
| `seeds/a2_hybrid.jsonl` | 110 |
| `seeds/b_event.jsonl` | 139 |
| `seeds/c_financial_metric.jsonl` | 294 |
| `seeds/d_counterfactual.jsonl` | 30 |
| `seeds/e_formula.jsonl` | 30 |
| **Total ready** | **1120** |

Forward T3 templates (not in ready total): `seeds/t3_forward.jsonl` (84 templates, `outcome_status=pending`).

## paper_band distribution (1120 ready)

| Band | Count |
|------|------:|
| T1 | 437 |
| T2 | 622 |
| quarantine | 1 |
| D | 30 |
| E | 30 |

Official temporal eligibility (observed/evidenced outcome availability):

| Band | Eligible | Raw |
|------|---------:|----:|
| T1 | 33 | 437 |
| T2 | 136 | 622 |

“Eligible” 同时要求观测证据、`official_temporal_eligible=true` 和
`review_status=reviewed`。Yahoo 基本面不是 point-in-time 数据，因此 A2-F/H
与 C 默认仅保留为研究集。

## By category (paper_band)

| Category | T1 | T2 | quarantine | Notes |
|----------|---:|---:|-----------:|-------|
| A1 | 198 | 46 | 0 | T1 target met |
| A2-F | 46 | 66 | 0 | T1/T2 targets met |
| A2-T | 95 | 66 | 0 | Both bands ≥30 |
| A2-H | 46 | 64 | 0 | T1/T2 targets met |
| B earnings | 52 | 73 | 1 | Expanded cross-market earnings windows |
| B macro | 0 | 13 | 0 | 13 first-party releases with observed reaction closes |
| C | 0 | 294 | 0 | Official + Yahoo dual-track merged |
| D | — | — | — | 30 × `D` band |
| E | — | — | — | 30 × `E` band |

## By category (reviewed + official eligible)

| Category | T1 | T2 | Notes |
|----------|---:|---:|-------|
| A1 | 33 | 46 | Reviewed subset remains eligible |
| A2-F | 0 | 2 | Only reviewed rows without `non_pit_fundamentals` remain eligible |
| A2-T | 0 | 66 | Reviewed subset remains eligible |
| A2-H | 0 | 0 | Yahoo fundamentals keep all rows research-only |
| B earnings | 0 | 21 | Only rows with complete official evidence are eligible |
| B macro | 0 | 1 | Expanded rows are present; strict review keeps subset eligible |
| C | 0 | 0 | Official value snapshots still incomplete for most rows |

## Quality flags

| Flag | Count | Action |
|------|------:|--------|
| `modeled_outcome_availability` | 721 | Outcome timing still modeled for many rows |
| `non_pit_fundamentals` | 437 | Yahoo-based A2-F/H/C; research-only |
| `missing_event_evidence` | 63 | B rows missing final official event evidence |
| `official_disclosure_lookup_failed` | 110 | C rows need more registry coverage |

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
