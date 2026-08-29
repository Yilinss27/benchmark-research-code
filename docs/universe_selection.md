# Universe Selection Standard (v1)

This document defines a unified cross-market stock selection contract for `A1/A2/B/C`.

## Scope

- Markets: `CN_A`, `US`, `HK`
- Applies to: `A1`, `A2-F`, `A2-T`, `A2-H`, `B (earnings)`, `C`
- Source of truth: `configs/universes_v1.json`

## Selection Principles

- Use liquid, large-cap leaders that have stable price and filing coverage.
- Keep market structures symmetric whenever possible.
- Keep category mapping consistent:
  - `B` earnings universe must be a subset of `A1` core universe.
  - `C` uses the same stock universe as `A1`.
  - `A2` cohorts use shared cohort keys across all markets.

## Universe Contract

- `A1`/`C` (`a1_universe`): 12 names per market in v1.
- `B` earnings (`b_earnings_universe`): 12 names per market, subset of `a1_universe`.
- `A2` (`a2_cohorts`): 7 unified cohort keys:
  - `financial`
  - `consumer`
  - `tech`
  - `healthcare`
  - `energy`
  - `industrial`
  - `communications`
- Each cohort targets 12 names per market.

## Data Source and Runtime Rules

- Price and basic earnings generation runs through `src.data_generator` with Yahoo provider.
- Official disclosure evidence for `B/C` is enriched separately through temporal scripts and registry providers.
- Non-PIT fundamentals remain research-only and are excluded from official scoring by temporal quality flags.

## Maintenance Rules

- Do not edit stock pools directly in Python constants.
- Update `configs/universes_v1.json`, then regenerate seeds.
- Keep every change auditable in changelog and count reports.
