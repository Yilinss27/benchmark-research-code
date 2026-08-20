"""Generate A1 / A2 / B / C seeds from a market data provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.builders.a1_from_csv_builder import build_records as build_a1_records
from src.builders.a2_fundamentals_from_csv_builder import _read_prompt_template as read_a2f_prompt
from src.builders.a2_fundamentals_from_csv_builder import build_records as build_a2f_records
from src.builders.a2_fundamentals_loader import FUNDAMENTAL_OUTPUT_KEYS
from src.builders.a2_hybrid_from_csv_builder import _read_prompt_template as read_a2h_prompt
from src.builders.a2_hybrid_from_csv_builder import build_records as build_a2h_records
from src.builders.a2_technical_metrics import LOOKBACK_TRADING_DAYS, MIN_TRADING_DAYS_FOR_READY
from src.builders.a2_technicals_from_csv_builder import _read_prompt_template as read_a2t_prompt
from src.builders.a2_technicals_from_csv_builder import build_records as build_a2t_records
from src.builders.b_event_from_csv_builder import _read_prompt_template as read_b_prompt
from src.builders.b_event_from_csv_builder import build_record as build_b_record
from src.builders.c_financial_metric_from_csv_builder import _read_prompt_template as read_c_prompt
from src.builders.c_financial_metric_from_csv_builder import build_record as build_c_record
from src.data.providers.base import PriceBar, PriceProvider, add_calendar_days, parse_iso_date
from src.data.providers.yahoo import YahooPriceProvider
from src.data.universe import (
    A1_UNIVERSE,
    A2_T_COHORTS,
    B_EVENT_WINDOWS,
    B_UNIVERSE,
    C_METRICS,
    currency_for_market,
    currency_unit,
)
from src.data.yahoo_fundamentals import YahooFundamentals
from scripts.assign_time_bands import update_row as update_temporal_band


SUPPORTED_TASKS = ("A1", "A2-T", "A2-F", "A2-H", "B", "C")
SUPPORTED_MARKETS = ("CN_A", "US", "HK")
A1_HORIZONS = (30, 90, 180, 365)
A2_PREDICTION_WINDOW_DAYS = 30
A2_LOOKBACK_CALENDAR_DAYS = 150
A2_MIN_STOCKS = 6
DEFAULT_TRAINING_CUTOFF = "2024-06-01"
DEFAULT_CURRENT_DATE = "2026-08-08"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for data_generator."""
    parser = argparse.ArgumentParser(
        description="Generate A1 / A2 / B / C seeds for a market and cutoff date.",
    )
    parser.add_argument("--task", required=True, choices=SUPPORTED_TASKS, help="Task type.")
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


def _record_market(record: dict[str, Any]) -> str:
    """Market on a generated or legacy record."""
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}
    return str(seed.get("market") or metadata.get("market") or "CN_A")


def a1_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """Identity used to skip duplicate A1 records."""
    seed = record.get("seed") or {}
    return (
        str(seed.get("stock_code", "")),
        str(seed.get("cutoff_date", "")),
        _record_market(record),
    )


def a2_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    """Identity used to skip duplicate A2 cohort records."""
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}
    return (
        str(metadata.get("cohort_id") or record.get("task_id", "")),
        str(seed.get("cutoff_date", "")),
        _record_market(record),
    )


def b_identity(record: dict[str, Any]) -> tuple[str, str, str, str]:
    """Identity used to skip duplicate B records."""
    seed = record.get("seed") or {}
    return (
        str(seed.get("stock_code", "")),
        str(seed.get("event_date") or seed.get("cutoff_date", "")),
        str(seed.get("event_subtype") or record.get("variant") or ""),
        _record_market(record),
    )


def c_identity(record: dict[str, Any]) -> tuple[str, str, str, str]:
    """Identity used to skip duplicate C records."""
    seed = record.get("seed") or {}
    return (
        str(seed.get("stock_code", "")),
        str(seed.get("cutoff_date", "")),
        str(seed.get("metric_name", "")),
        _record_market(record),
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


def _collect_a2_price_stocks(
    spec: dict[str, Any],
    market: str,
    cutoff_date: str,
    provider: PriceProvider,
    task_label: str,
) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    """Collect usable A2 cohort stocks with lookback prices and 30d forward returns."""
    stocks: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    warnings: list[str] = []
    cohort_key = spec["cohort_key"]

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
                f"{task_label} {market} {cohort_key} {code} {cutoff_date}: provider error ({exc}); skipped"
            )
            continue
        if cutoff_bar is None or forward_bar is None:
            skipped.append(code)
            warnings.append(
                f"{task_label} {market} {cohort_key} {code} {cutoff_date}: missing cutoff/forward close; skipped"
            )
            continue
        if len(bars) < MIN_TRADING_DAYS_FOR_READY:
            skipped.append(code)
            warnings.append(
                f"{task_label} {market} {cohort_key} {code} {cutoff_date}: "
                f"only {len(bars)} lookback days; skipped"
            )
            continue
        if cutoff_bar.close == 0:
            skipped.append(code)
            warnings.append(f"{task_label} {market} {cohort_key} {code}: zero cutoff close; skipped")
            continue

        stocks[code] = {
            "code": code,
            "name": item["stock_name"],
            "prices": [{"trading_day": bar.trading_day, "close_price": bar.close} for bar in bars],
            "actual_return": (forward_bar.close - cutoff_bar.close) / cutoff_bar.close,
            "cutoff_price": cutoff_bar.close,
        }
    return stocks, skipped, warnings


def _has_valuation_signal(snapshot: dict[str, Any]) -> bool:
    """True if a Yahoo snapshot has at least one usable valuation ratio."""
    return any(snapshot.get(key) is not None for key in ("pe", "pb", "ps", "debt_to_market_cap"))


def _snapshot_history_row(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Convert a Yahoo snapshot into the A2 fundamentals-loader row shape."""
    return {key: snapshot.get(key) for key in FUNDAMENTAL_OUTPUT_KEYS}


def _attach_fundamentals(
    stocks: dict[str, dict[str, Any]],
    market: str,
    cutoff_date: str,
    fundamentals: YahooFundamentals,
    task_label: str,
    cohort_key: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], list[str]]:
    """Keep stocks that have a Yahoo valuation snapshot as of cutoff."""
    usable: dict[str, dict[str, Any]] = {}
    history: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    for code, stock in stocks.items():
        try:
            snapshot = fundamentals.fundamentals_snapshot(
                code,
                market,
                cutoff_date,
                float(stock["cutoff_price"]),
            )
        except Exception as exc:
            warnings.append(
                f"{task_label} {market} {cohort_key} {code} {cutoff_date}: "
                f"fundamentals error ({exc}); skipped"
            )
            continue
        if snapshot is None or not _has_valuation_signal(snapshot):
            warnings.append(
                f"{task_label} {market} {cohort_key} {code} {cutoff_date}: "
                "no usable Yahoo valuation snapshot; skipped"
            )
            continue
        usable[code] = stock
        history[code] = [_snapshot_history_row(snapshot)]
    return usable, history, warnings


def _ready_only(records: list[dict[str, Any]], task_label: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop non-ready builder output."""
    warnings: list[str] = []
    ready = []
    for record in records:
        if record["status"] == "ready":
            ready.append(record)
        else:
            warnings.append(f"{task_label} {record['task_id']} emitted as {record['status']}; dropped")
    return ready, warnings


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
        stocks, skipped, stock_warnings = _collect_a2_price_stocks(
            spec, market, cutoff_date, provider, "A2-T"
        )
        warnings.extend(stock_warnings)
        if len(stocks) < A2_MIN_STOCKS:
            warnings.append(
                f"A2-T {market} {cohort_key} {cutoff_date}: only {len(stocks)} usable stocks "
                f"(need >= {A2_MIN_STOCKS}); skipped {skipped}"
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
    ready, drop_warnings = _ready_only(records, "A2-T")
    warnings.extend(drop_warnings)
    return ready, warnings


def generate_a2_f(
    market: str,
    cutoff_date: str,
    provider: PriceProvider,
    *,
    source_name: str = "yahoo",
    fundamentals: YahooFundamentals | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build A2-F records from Yahoo valuation snapshots and 30d forward returns."""
    parse_iso_date(cutoff_date)
    currency = currency_for_market(market)
    compact = _compact_date(cutoff_date)
    fund = fundamentals or YahooFundamentals()
    warnings: list[str] = []
    cohorts: dict[str, dict[str, Any]] = {}
    history: dict[str, list[dict[str, Any]]] = {}
    returns_by_cohort: dict[str, dict[str, float]] = {}

    for spec in A2_T_COHORTS[market]:
        cohort_key = spec["cohort_key"]
        cohort_id = f"{market}_{cohort_key}_{compact}"
        stocks, skipped, stock_warnings = _collect_a2_price_stocks(
            spec, market, cutoff_date, provider, "A2-F"
        )
        warnings.extend(stock_warnings)
        usable, fund_history, fund_warnings = _attach_fundamentals(
            stocks, market, cutoff_date, fund, "A2-F", cohort_key
        )
        warnings.extend(fund_warnings)
        if len(usable) < A2_MIN_STOCKS:
            warnings.append(
                f"A2-F {market} {cohort_key} {cutoff_date}: only {len(usable)} stocks with "
                f"prices+fundamentals (need >= {A2_MIN_STOCKS}); skipped {skipped}"
            )
            continue
        history.update(fund_history)
        returns_by_cohort[cohort_id] = {
            code: float(stock["actual_return"]) for code, stock in usable.items()
        }
        cohorts[cohort_id] = {
            "cohort_id": cohort_id,
            "task_id": f"A2F-{market}-{compact}-{cohort_key}",
            "industry_name": spec["industry_name"],
            "cutoff_date": cutoff_date,
            "prediction_window_days": A2_PREDICTION_WINDOW_DAYS,
            "stocks": [{"code": stock["code"], "name": stock["name"]} for stock in usable.values()],
        }

    records, builder_warnings = build_a2f_records(
        history,
        cohorts,
        returns_by_cohort,
        read_a2f_prompt(),
        source_name,
        market=market,
        currency=currency,
    )
    warnings.extend(builder_warnings)
    ready, drop_warnings = _ready_only(records, "A2-F")
    warnings.extend(drop_warnings)
    return ready, warnings


def generate_a2_h(
    market: str,
    cutoff_date: str,
    provider: PriceProvider,
    *,
    source_name: str = "yahoo",
    fundamentals: YahooFundamentals | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build A2-H records from Yahoo valuation snapshots plus technicals."""
    parse_iso_date(cutoff_date)
    currency = currency_for_market(market)
    compact = _compact_date(cutoff_date)
    fund = fundamentals or YahooFundamentals()
    warnings: list[str] = []
    cohorts: dict[str, dict[str, Any]] = {}
    history: dict[str, list[dict[str, Any]]] = {}

    for spec in A2_T_COHORTS[market]:
        cohort_key = spec["cohort_key"]
        cohort_id = f"{market}_{cohort_key}_{compact}"
        stocks, skipped, stock_warnings = _collect_a2_price_stocks(
            spec, market, cutoff_date, provider, "A2-H"
        )
        warnings.extend(stock_warnings)
        usable, fund_history, fund_warnings = _attach_fundamentals(
            stocks, market, cutoff_date, fund, "A2-H", cohort_key
        )
        warnings.extend(fund_warnings)
        if len(usable) < A2_MIN_STOCKS:
            warnings.append(
                f"A2-H {market} {cohort_key} {cutoff_date}: only {len(usable)} stocks with "
                f"prices+fundamentals (need >= {A2_MIN_STOCKS}); skipped {skipped}"
            )
            continue
        history.update(fund_history)
        cohorts[cohort_id] = {
            "cohort_id": cohort_id,
            "task_id": f"A2H-{market}-{compact}-{cohort_key}",
            "industry_name": spec["industry_name"],
            "cutoff_date": cutoff_date,
            "prediction_window_days": A2_PREDICTION_WINDOW_DAYS,
            "stocks": usable,
        }

    records, builder_warnings = build_a2h_records(
        cohorts,
        history,
        read_a2h_prompt(),
        source_name,
        source_name,
        market=market,
        currency=currency,
    )
    warnings.extend(builder_warnings)
    ready, drop_warnings = _ready_only(records, "A2-H")
    warnings.extend(drop_warnings)
    return ready, warnings


def _b_window(cutoff_date: str) -> tuple[str, str]:
    """Return the earnings search window for a T1/T2 cutoff anchor."""
    if cutoff_date in B_EVENT_WINDOWS:
        return B_EVENT_WINDOWS[cutoff_date]
    return add_calendar_days(cutoff_date, -180), add_calendar_days(cutoff_date, 180)


def _pick_earnings_event(
    events: list[dict[str, Any]],
    window_start: str,
    window_end: str,
    anchor: str,
) -> dict[str, Any] | None:
    """Pick the reported-EPS event in window closest to the cutoff anchor."""
    eligible = [
        event
        for event in events
        if window_start <= event["event_date"] <= window_end and event.get("reported_eps") is not None
    ]
    if not eligible:
        return None
    anchor_date = parse_iso_date(anchor)
    return min(
        eligible,
        key=lambda event: abs((parse_iso_date(event["event_date"]) - anchor_date).days),
    )


def _adjacent_closes(
    provider: PriceProvider,
    symbol: str,
    market: str,
    event_date: str,
) -> tuple[PriceBar | None, PriceBar | None]:
    """Previous close strictly before event_date and next session close after it."""
    start = add_calendar_days(event_date, -21)
    end = add_calendar_days(event_date, 21)
    bars = provider.get_price_history(symbol, market, start, end)
    prev_bars = [bar for bar in bars if bar.trading_day < event_date]
    next_bars = [bar for bar in bars if bar.trading_day > event_date]
    prev = prev_bars[-1] if prev_bars else provider.get_close_on_or_before(
        symbol, market, add_calendar_days(event_date, -1)
    )
    nxt = next_bars[0] if next_bars else None
    if nxt is None:
        for horizon in (1, 2, 3, 4, 5, 7, 10):
            candidate = provider.get_forward_close(symbol, market, event_date, horizon)
            if candidate is not None:
                nxt = candidate
                break
    return prev, nxt


def _earnings_description(stock_name: str, stock_code: str, event: dict[str, Any]) -> str:
    """Render a short earnings surprise description for the B prompt."""
    parts = [f"{stock_name}（{stock_code}）发布财报"]
    reported = event.get("reported_eps")
    estimate = event.get("eps_estimate")
    surprise = event.get("surprise_pct")
    if reported is not None:
        parts.append(f"EPS 实际 {reported:.4g}")
    if estimate is not None:
        parts.append(f"一致预期 {estimate:.4g}")
    if surprise is not None:
        parts.append(f"surprise {surprise:.2f}%")
    return "，".join(parts) + "。"


def generate_b(
    market: str,
    cutoff_date: str,
    provider: PriceProvider,
    *,
    source_name: str = "yahoo",
    fundamentals: YahooFundamentals | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build B earnings-direction records around one T1/T2 cutoff anchor."""
    parse_iso_date(cutoff_date)
    currency = currency_for_market(market)
    fund = fundamentals or YahooFundamentals()
    window_start, window_end = _b_window(cutoff_date)
    template = read_b_prompt()
    warnings: list[str] = []
    records: list[dict[str, Any]] = []

    for item in B_UNIVERSE[market]:
        code = item["stock_code"]
        name = item["stock_name"]
        try:
            events = fund.earnings_events(code, market)
        except Exception as exc:
            warnings.append(f"B {market} {code} {cutoff_date}: earnings error ({exc}); skipped")
            continue
        event = _pick_earnings_event(events, window_start, window_end, cutoff_date)
        if event is None:
            warnings.append(
                f"B {market} {code} {cutoff_date}: no reported EPS in {window_start}..{window_end}; skipped"
            )
            continue
        event_date = event["event_date"]
        try:
            prev_bar, next_bar = _adjacent_closes(provider, code, market, event_date)
        except Exception as exc:
            warnings.append(f"B {market} {code} {event_date}: price error ({exc}); skipped")
            continue
        if prev_bar is None or next_bar is None or prev_bar.close == 0:
            warnings.append(f"B {market} {code} {event_date}: missing adjacent closes; skipped")
            continue
        return_pct = (next_bar.close - prev_bar.close) / prev_bar.close * 100.0
        if return_pct == 0:
            warnings.append(f"B {market} {code} {event_date}: zero event return; skipped")
            continue
        compact_event = _compact_date(event_date)
        task_id = f"B-EARN-{market}-{compact_event}-{code}"
        row = {
            "event_id": task_id,
            "event_subtype": "earnings",
            "stock_code": code,
            "stock_name": name,
            "event_date": event_date,
            "event_description": _earnings_description(name, code, event),
            "cutoff_date": event_date,
            "actual_direction": "up" if return_pct > 0 else "down",
            "actual_return_pct": f"{return_pct:.6f}",
        }
        records.append(build_b_record(row, template, source_name, market=market, currency=currency))

    return records, warnings


def generate_c(
    market: str,
    cutoff_date: str,
    provider: PriceProvider,
    *,
    source_name: str = "yahoo",
    fundamentals: YahooFundamentals | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build C next-period financial-metric records for one market and cutoff."""
    del provider  # prices are not required; signature matches the other generators
    parse_iso_date(cutoff_date)
    currency = currency_for_market(market)
    compact = _compact_date(cutoff_date)
    fund = fundamentals or YahooFundamentals()
    template = read_c_prompt()
    warnings: list[str] = []
    records: list[dict[str, Any]] = []

    for item in A1_UNIVERSE[market]:
        code = item["stock_code"]
        name = item["stock_name"]
        for metric in C_METRICS:
            try:
                pair = fund.metric_pair(code, market, cutoff_date, metric)
            except Exception as exc:
                warnings.append(
                    f"C {market} {code} {metric} {cutoff_date}: financials error ({exc}); skipped"
                )
                continue
            if pair is None:
                warnings.append(
                    f"C {market} {code} {metric} {cutoff_date}: no public hist/future pair; skipped"
                )
                continue
            task_id = f"C-{market}-{compact}-{code}-{metric}"
            row = {
                "task_id": task_id,
                "stock_code": code,
                "stock_name": name,
                "cutoff_date": cutoff_date,
                "metric_name": metric,
                "report_period_historical": pair["report_period_historical"],
                "historical_value": f"{pair['historical_value']:.4f}",
                "report_period_future": pair["report_period_future"],
                "future_value": f"{pair['future_value']:.4f}",
            }
            records.append(build_c_record(row, template, source_name, market=market, currency=currency))

    return records, warnings


def merge_records(
    existing: list[dict[str, Any]],
    generated: list[dict[str, Any]],
    identity_fn,
    *,
    replace: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Append generated records, skipping duplicate identities and task_ids."""
    if replace and generated:
        replace_ids = {record["task_id"] for record in generated}
        replace_keys = {identity_fn(record) for record in generated}
        existing = [
            row
            for row in existing
            if row["task_id"] not in replace_ids and identity_fn(row) not in replace_keys
        ]

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


TASK_HANDLERS = {
    "A1": (generate_a1, a1_identity),
    "A2-T": (generate_a2_t, a2_identity),
    "A2-F": (generate_a2_f, a2_identity),
    "A2-H": (generate_a2_h, a2_identity),
    "B": (generate_b, b_identity),
    "C": (generate_c, c_identity),
}


def generate(
    task: str,
    market: str,
    cutoff_date: str,
    *,
    provider_name: str = "yahoo",
    output: str | Path,
    append: bool = False,
    replace: bool = False,
    training_cutoff: str = DEFAULT_TRAINING_CUTOFF,
    current_date: str = DEFAULT_CURRENT_DATE,
) -> dict[str, Any]:
    """Generate records and write them to output."""
    if task not in TASK_HANDLERS:
        raise ValueError(f"Unsupported task: {task}. This round supports {SUPPORTED_TASKS}.")
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}")

    provider = _provider(provider_name)
    handler, identity_fn = TASK_HANDLERS[task]
    generated, warnings = handler(market, cutoff_date, provider, source_name=provider_name)
    generated = _assign_bands(generated, training_cutoff, current_date)
    output_path = Path(output)
    existing = _load_jsonl(output_path) if append else []
    merged, added = merge_records(existing, generated, identity_fn, replace=replace)
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
