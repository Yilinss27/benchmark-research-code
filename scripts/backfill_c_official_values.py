#!/usr/bin/env python3
"""Backfill C records with official filing value provenance when available."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.providers.official_values import OfficialMetricProvider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="seeds/c_financial_metric.jsonl")
    parser.add_argument(
        "--registry",
        default="configs/official_disclosures_v1.jsonl",
        help="Disclosure registry JSONL used by OfficialMetricProvider.",
    )
    parser.add_argument("--output", default=None, help="Output JSONL path (default: overwrite --seed)")
    parser.add_argument(
        "--max-relative-error",
        type=float,
        default=0.02,
        help="Maximum relative error allowed when validating seed values against official values.",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _close_enough(seed_value: float, official_value: float, max_relative_error: float) -> bool:
    denom = max(abs(official_value), 1e-6)
    return abs(seed_value - official_value) / denom <= max_relative_error


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def main() -> int:
    args = parse_args()
    seed_path = Path(args.seed)
    output_path = Path(args.output) if args.output else seed_path
    rows = _load_jsonl(seed_path)
    provider = OfficialMetricProvider(index_path=args.registry)

    checked = 0
    updated = 0
    missing_observation = 0
    mismatched = 0

    for row in rows:
        if row.get("category") != "C" or row.get("status") != "ready":
            continue
        seed = row.get("seed") or {}
        metric = str(seed.get("metric_name") or "")
        market = str(seed.get("market") or (row.get("metadata") or {}).get("market") or "CN_A")
        symbol = str(seed.get("stock_code") or "")
        report_hist = str(seed.get("report_period_historical") or "")
        report_future = str(seed.get("report_period_future") or "")
        hist_seed = _as_float(seed.get("historical_value"))
        future_seed = _as_float((row.get("ground_truth") or {}).get("future_value"))
        if not all([metric, market, symbol, report_hist, report_future]):
            continue
        if hist_seed is None or future_seed is None:
            continue

        checked += 1
        try:
            hist_obs = provider.find_metric_value(symbol, market, report_hist, metric)
            future_obs = provider.find_metric_value(symbol, market, report_future, metric)
        except Exception:
            missing_observation += 1
            continue
        if hist_obs is None or future_obs is None:
            missing_observation += 1
            continue
        if not (
            _close_enough(hist_seed, hist_obs.value, args.max_relative_error)
            and _close_enough(future_seed, future_obs.value, args.max_relative_error)
        ):
            mismatched += 1
            continue

        metadata = dict(row.get("metadata") or {})
        metadata["fundamentals_source"] = "official_filing_snapshot"
        metadata["fundamentals_source_tier"] = "official_filing"
        metadata["statement_freq"] = (
            "annual" if report_future.endswith("12-31") else "quarterly"
        )
        metadata["official_metric_snapshot"] = {
            "metric_name": metric,
            "historical": {
                "report_period": report_hist,
                "value": hist_obs.value,
                "published_at": hist_obs.published_at,
                "source": hist_obs.source,
                "source_url": hist_obs.source_url,
                "evidence_code": hist_obs.evidence_code,
            },
            "future": {
                "report_period": report_future,
                "value": future_obs.value,
                "published_at": future_obs.published_at,
                "source": future_obs.source,
                "source_url": future_obs.source_url,
                "evidence_code": future_obs.evidence_code,
            },
            "max_relative_error": args.max_relative_error,
        }
        row["metadata"] = metadata
        updated += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "seed": str(seed_path),
                "registry": args.registry,
                "output": str(output_path),
                "checked_ready_c_records": checked,
                "updated_to_official_filing_snapshot": updated,
                "missing_official_observation": missing_observation,
                "value_mismatched": mismatched,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
