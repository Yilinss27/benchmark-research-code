"""Generate A1 / A2-T seeds from a market data provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.builders.a1_from_csv_builder import build_records as build_a1_records
from src.builders.a2_technical_metrics import LOOKBACK_TRADING_DAYS, MIN_TRADING_DAYS_FOR_READY
from src.builders.a2_technicals_from_csv_builder import _read_prompt_template as read_a2t_prompt
from src.builders.a2_technicals_from_csv_builder import build_records as build_a2t_records
from src.data.providers.base import PriceProvider, add_calendar_days, parse_iso_date
from src.data.providers.yahoo import YahooPriceProvider
from src.data.universe import (
    A1_UNIVERSE,
    A2_T_COHORTS,
    currency_for_market,
    currency_unit,
)
from scripts.assign_time_bands import update_row as update_temporal_band


SUPPORTED_TASKS = ("A1", "A2-T")
SUPPORTED_MARKETS = ("CN_A", "US", "HK")
A1_HORIZONS = (30, 90, 180, 365)
A2_PREDICTION_WINDOW_DAYS = 30
A2_LOOKBACK_CALENDAR_DAYS = 150
DEFAULT_TRAINING_CUTOFF = "2024-06-01"
DEFAULT_CURRENT_DATE = "2026-08-08"
RESERVED_TASKS = {
    "A2-F": "Yahoo fundamentals are not point-in-time; A2-F is reserved this round.",
    "A2-H": "Yahoo fundamentals are not point-in-time; A2-H is reserved this round.",
    "B": "Yahoo news/events are unstable; B is reserved this round.",
    "C": "Yahoo financials are not point-in-time; C is reserved this round.",
}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for data_generator."""
    parser = argparse.ArgumentParser(
        description="Generate A1 / A2-T seeds for a market and cutoff date.",
    )
    parser.add_argument("--task", required=True, help="Task type: A1 or A2-T.")
    parser.add_argument("--market", required=True, choices=SUPPORTED_MARKETS, help="Market universe.")
    parser.add_argument("--cutoff-date", required=True, help="Information cutoff date YYYY-MM-DD.")
    parser.add_argument("--provider", default="yahoo", choices=("yahoo",), help="Price provider.")
    parser.add_argument("--output", required=True, help="Output JSONL path.")
    parser.add_argument("--append", action="store_true", help="Append to existing output; skip duplicates.")
    parser.add_argument(
        "--training-cutoff",
        default=DEFAULT_TRAINING_CUTOFF,
        help="Model training cutoff used to assign time_band.",
    )
    parser.add_argument(
        "--current-date",
        default=DEFAULT_CURRENT_DATE,
        help="Reference current date used to assign time_band.",
    )
    return parser.parse_args()


def _provider(name: str) -> PriceProvider:
    """Construct a price provider."""
    if name == "yahoo":
        return YahooPriceProvider()
    raise ValueError(f"Unsupported provider: {name}")


def _compact_date(cutoff_date: str) -> str:
    """Return YYYYMMDD."""
    return cutoff_date.replace("-", "")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL records if the file exists."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSONL records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _optional_price(bar: Any) -> str:
    """Format a close as a CSV-like string, or empty if missing."""
    if bar is None:
        return ""
    return f"{bar.close:.4f}"


def a1_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """Identity used to skip duplicate A1 records."""
    seed = record.get("seed") or {}
    return (
        str(seed.get("stock_code", "")),
        str(seed.get("cutoff_date", "")),
        str(seed.get("market") or record.get("metadata", {}).get("market") or "CN_A"),
    )


def a2t_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """Identity used to skip duplicate A2-T records."""
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}
    return (
        str(metadata.get("cohort_id") or record.get("task_id", "")),
        str(seed.get("cutoff_date", "")),
        str(seed.get("market") or metadata.get("market") or "CN_A"),
    )


def _assign_bands(
    records: list[dict[str, Any]],
    training_cutoff: str,
    current_date: str,
) -> list[dict[str, Any]]:
    """Stamp cutoff_date / time_band / temporal_split onto generated records."""
    return [update_temporal_band(record, training_cutoff, current_date) for record in records]


def generate_a1(
    market: str,
    cutoff_date: str,
    provider: PriceProvider,
    *,
    source_name: str = "yahoo",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build A1 records for one market and cutoff."""
    parse_iso_date(cutoff_date)
    names = A1_UNIVERSE[market]
    currency = currency_for_market(market)
    unit = currency_unit(currency)
    compact = _compact_date(cutoff_date)
    rows: list[dict[str, str]] = []
    warnings: list[str] = []

    for index, item in enumerate(names, 1):
        code = item["stock_code"]
        try:
            cutoff_bar = provider.get_close_on_or_before(code, market, cutoff_date)
            forward = {
                horizon: provider.get_forward_close(code, market, cutoff_date, horizon)
                for horizon in A1_HORIZONS
            }
        except Exception as exc:
            warnings.append(f"A1 {market} {code} {cutoff_date}: provider error ({exc}); skipped")
            continue
        if cutoff_bar is None:
            warnings.append(f"A1 {market} {code} {cutoff_date}: no cutoff close; skipped")
            continue
        forward = {
            horizon: provider.get_forward_close(code, market, cutoff_date, horizon)
            for horizon in A1_HORIZONS
        }
        rows.append(
            {
                "task_id": f"A1-{market}-{compact}-{index:05d}",
                "stock_code": code,
                "stock_name": item["stock_name"],
                "cutoff_date": cutoff_date,
                "cutoff_price": f"{cutoff_bar.close:.4f}",
                "price_30d": _optional_price(forward[30]),
                "price_90d": _optional_price(forward[90]),
                "price_180d": _optional_price(forward[180]),
                "price_365d": _optional_price(forward[365]),
            }
        )

    records = build_a1_records(
        rows,
        source_name=source_name,
        market=market,
        currency=currency,
        currency_unit=unit,
    )
    return records, warnings


def _lookback_bars(
    provider: PriceProvider,
    symbol: str,
    market: str,
    cutoff_date: str,
) -> list[Any]:
    """Return up to LOOKBACK_TRADING_DAYS closes on or before cutoff."""
    start = add_calendar_days(cutoff_date, -A2_LOOKBACK_CALENDAR_DAYS)
    history = provider.get_price_history(symbol, market, start, cutoff_date)
    return history[-LOOKBACK_TRADING_DAYS:]


def generate_a2_t(
    market: str,
    cutoff_date: str,
    provider: PriceProvider,
    *,
    source_name: str = "yahoo",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build A2-T records for one market and cutoff."""
    parse_iso_date(cutoff_date)
    currency = currency_for_market(market)
    compact = _compact_date(cutoff_date)
    warnings: list[str] = []
    cohorts: dict[str, dict[str, Any]] = {}

    for spec in A2_T_COHORTS[market]:
        cohort_key = spec["cohort_key"]
        cohort_id = f"{market}_{cohort_key}_{compact}"
        stocks: dict[str, dict[str, Any]] = {}
        skipped: list[str] = []

        for item in spec["stocks"]:
            code = item["stock_code"]
            try:
                cutoff_bar = provider.get_close_on_or_before(code, market, cutoff_date)
                forward_bar = provider.get_forward_close(
                    code,
                    market,
                    cutoff_date,
                    A2_PREDICTION_WINDOW_DAYS,
                )
                bars = _lookback_bars(provider, code, market, cutoff_date)
            except Exception as exc:
                skipped.append(code)
                warnings.append(
                    f"A2-T {market} {cohort_key} {code} {cutoff_date}: provider error ({exc}); skipped"
                )
                continue
            if cutoff_bar is None or forward_bar is None:
                skipped.append(code)
                warnings.append(
                    f"A2-T {market} {cohort_key} {code} {cutoff_date}: missing cutoff/forward close; skipped"
                )
                continue
            if len(bars) < MIN_TRADING_DAYS_FOR_READY:
                skipped.append(code)
                warnings.append(
                    f"A2-T {market} {cohort_key} {code} {cutoff_date}: "
                    f"only {len(bars)} lookback days; skipped"
                )
                continue
            if cutoff_bar.close == 0:
                skipped.append(code)
                warnings.append(f"A2-T {market} {cohort_key} {code}: zero cutoff close; skipped")
                continue

            stocks[code] = {
                "code": code,
                "name": item["stock_name"],
                "prices": [{"trading_day": bar.trading_day, "close_price": bar.close} for bar in bars],
                "actual_return": (forward_bar.close - cutoff_bar.close) / cutoff_bar.close,
            }

        if len(stocks) < 6:
            warnings.append(
                f"A2-T {market} {cohort_key} {cutoff_date}: only {len(stocks)} usable stocks "
                f"(need >= 6); skipped {skipped}"
            )
            continue

        cohorts[cohort_id] = {
            "cohort_id": cohort_id,
            "task_id": f"A2T-{market}-{compact}-{cohort_key}",
            "industry_name": spec["industry_name"],
            "cutoff_date": cutoff_date,
            "prediction_window_days": A2_PREDICTION_WINDOW_DAYS,
            "stocks": stocks,
        }

    records, builder_warnings = build_a2t_records(
        cohorts,
        read_a2t_prompt(),
        source_name,
        market=market,
        currency=currency,
    )
    warnings.extend(builder_warnings)
    ready = [record for record in records if record["status"] == "ready"]
    for record in records:
        if record["status"] != "ready":
            warnings.append(f"A2-T {record['task_id']} emitted as {record['status']}; dropped")
    return ready, warnings


def merge_records(
    existing: list[dict[str, Any]],
    generated: list[dict[str, Any]],
    identity_fn,
) -> tuple[list[dict[str, Any]], int]:
    """Append generated records, skipping duplicate identities and task_ids."""
    seen_ids = {row["task_id"] for row in existing}
    seen_keys = {identity_fn(row) for row in existing}
    added = 0
    merged = list(existing)
    for record in generated:
        key = identity_fn(record)
        if record["task_id"] in seen_ids or key in seen_keys:
            continue
        merged.append(record)
        seen_ids.add(record["task_id"])
        seen_keys.add(key)
        added += 1
    return merged, added


def generate(
    task: str,
    market: str,
    cutoff_date: str,
    *,
    provider_name: str = "yahoo",
    output: str | Path,
    append: bool = False,
    training_cutoff: str = DEFAULT_TRAINING_CUTOFF,
    current_date: str = DEFAULT_CURRENT_DATE,
) -> dict[str, Any]:
    """Generate records and write them to output."""
    if task in RESERVED_TASKS:
        raise ValueError(RESERVED_TASKS[task])
    if task not in SUPPORTED_TASKS:
        raise ValueError(f"Unsupported task: {task}. This round supports {SUPPORTED_TASKS}.")
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}")

    provider = _provider(provider_name)
    if task == "A1":
        generated, warnings = generate_a1(market, cutoff_date, provider, source_name=provider_name)
        identity_fn = a1_identity
    else:
        generated, warnings = generate_a2_t(market, cutoff_date, provider, source_name=provider_name)
        identity_fn = a2t_identity

    generated = _assign_bands(generated, training_cutoff, current_date)
    output_path = Path(output)
    existing = _load_jsonl(output_path) if append else []
    merged, added = merge_records(existing, generated, identity_fn)
    _write_jsonl(output_path, merged)
    return {
        "task": task,
        "market": market,
        "cutoff_date": cutoff_date,
        "provider": provider_name,
        "output": str(output_path),
        "generated": len(generated),
        "added": added,
        "output_records": len(merged),
        "warnings": warnings,
    }


def main() -> int:
    """CLI entry for data_generator."""
    args = parse_args()
    summary = generate(
        args.task,
        args.market,
        args.cutoff_date,
        provider_name=args.provider,
        output=args.output,
        append=args.append,
        training_cutoff=args.training_cutoff,
        current_date=args.current_date,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
