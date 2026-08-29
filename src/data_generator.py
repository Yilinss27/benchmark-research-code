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
from src.data.providers.official import is_official_url
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
DEFAULT_TRAINING_CUTOFF = "2024-06-30"
DEFAULT_CURRENT_DATE = "2026-08-17"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for data_generator."""
    parser = argparse.ArgumentParser(
        description="Generate A1 / A2 / B / C seeds for a market and cutoff date.",
    )
    parser.add_argument(
        "--panel",
        action="store_true",
        help="Generate a full task panel for one cutoff (all markets/tasks).",
    )
    parser.add_argument("--task", default=None, choices=SUPPORTED_TASKS, help="Task type (single-task mode).")
    parser.add_argument("--market", default=None, choices=SUPPORTED_MARKETS, help="Market (single-task mode).")
    parser.add_argument("--cutoff-date", required=True, help="Information cutoff date YYYY-MM-DD.")
    parser.add_argument(
        "--markets",
        default="CN_A,US,HK",
        help="Comma-separated markets for --panel (default: CN_A,US,HK).",
    )
    parser.add_argument(
        "--tasks",
        default="A1,A2-F,A2-T,A2-H",
        help="Comma-separated tasks for --panel (default: A1,A2-F,A2-T,A2-H).",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=A2_PREDICTION_WINDOW_DAYS,
        help="Prediction / outcome horizon in calendar days (default: 30).",
    )
    parser.add_argument(
        "--panel-id",
        default=None,
        help="Optional panel tag written into metadata.panel.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for --panel mode (writes per-task JSONL files).",
    )
    parser.add_argument("--provider", default="yahoo", choices=("yahoo",), help="Price provider.")
    parser.add_argument("--output", default=None, help="Output JSONL path (single-task mode).")
    parser.add_argument("--append", action="store_true", help="Append to existing output; skip duplicates.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="When appending, replace matching identities with newly generated rows.",
    )
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
    primary_horizon_days: int = 30,
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
                "primary_eval_window_days": str(primary_horizon_days),
                **{
                    f"forward_trading_day_{horizon}": (
                        bar.trading_day if bar is not None else ""
                    )
                    for horizon, bar in forward.items()
                },
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
    *,
    prediction_window_days: int = A2_PREDICTION_WINDOW_DAYS,
) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    """Collect usable A2 cohort stocks with lookback prices and forward returns."""
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
                prediction_window_days,
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
            "forward_trading_day": forward_bar.trading_day,
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


def _stamp_fundamentals_source(
    records: list[dict[str, Any]],
    fundamentals: Any,
) -> list[dict[str, Any]]:
    """Record whether fundamentals are official PIT or research-only."""
    tier = str(getattr(fundamentals, "source_tier", "unknown"))
    for record in records:
        metadata = record.setdefault("metadata", {})
        metadata["fundamentals_source_tier"] = tier
        metadata["fundamentals_source"] = fundamentals.__class__.__name__
    return records


def generate_a2_t(
    market: str,
    cutoff_date: str,
    provider: PriceProvider,
    *,
    source_name: str = "yahoo",
    prediction_window_days: int = A2_PREDICTION_WINDOW_DAYS,
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
            spec,
            market,
            cutoff_date,
            provider,
            "A2-T",
            prediction_window_days=prediction_window_days,
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
            "prediction_window_days": prediction_window_days,
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
    prediction_window_days: int = A2_PREDICTION_WINDOW_DAYS,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build A2-F records from Yahoo valuation snapshots and forward returns."""
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
            spec,
            market,
            cutoff_date,
            provider,
            "A2-F",
            prediction_window_days=prediction_window_days,
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
            "prediction_window_days": prediction_window_days,
            "stocks": [
                {
                    "code": stock["code"],
                    "name": stock["name"],
                    "forward_trading_day": stock["forward_trading_day"],
                }
                for stock in usable.values()
            ],
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
    records = _stamp_fundamentals_source(records, fund)
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
    prediction_window_days: int = A2_PREDICTION_WINDOW_DAYS,
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
            spec,
            market,
            cutoff_date,
            provider,
            "A2-H",
            prediction_window_days=prediction_window_days,
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
            "prediction_window_days": prediction_window_days,
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
    records = _stamp_fundamentals_source(records, fund)
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


def _event_reaction_closes(
    provider: PriceProvider,
    symbol: str,
    market: str,
    event_date: str,
    release_phase: str,
) -> tuple[PriceBar | None, PriceBar | None]:
    """Return the pre-event baseline and first close able to reflect the release."""
    bars = provider.get_price_history(
        symbol,
        market,
        add_calendar_days(event_date, -21),
        add_calendar_days(event_date, 21),
    )
    previous = [bar for bar in bars if bar.trading_day < event_date]
    baseline = previous[-1] if previous else provider.get_close_on_or_before(
        symbol, market, add_calendar_days(event_date, -1)
    )
    if release_phase in {"pre_market", "market_hours"}:
        reactions = [bar for bar in bars if bar.trading_day >= event_date]
    else:
        reactions = [bar for bar in bars if bar.trading_day > event_date]
    return baseline, reactions[0] if reactions else None


def generate_b_macro(
    config_path: Path | str,
    provider: PriceProvider,
    *,
    source_name: str = "official_macro_v1",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build curated macro records using first-party releases and observed closes."""
    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    template = read_b_prompt()
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    for event in payload.get("events", []):
        task_id = str(event.get("event_id") or "")
        market = str(event.get("market") or "")
        code = str(event.get("stock_code") or "")
        event_date = str(event.get("event_date") or "")
        event_url = str(event.get("event_url") or "")
        if not task_id or task_id in seen_ids:
            warnings.append(f"B macro duplicate/missing event_id: {task_id!r}; skipped")
            continue
        if market not in SUPPORTED_MARKETS or not event_date:
            warnings.append(f"B macro {task_id}: invalid market/date; skipped")
            continue
        if not is_official_url(event_url, "MACRO"):
            warnings.append(f"B macro {task_id}: non-official event URL; skipped")
            continue
        try:
            parse_iso_date(event_date)
            baseline, reaction = _event_reaction_closes(
                provider,
                code,
                market,
                event_date,
                str(event.get("release_phase") or "after_market"),
            )
        except Exception as exc:
            warnings.append(f"B macro {task_id}: price error ({exc}); skipped")
            continue
        if baseline is None or reaction is None or baseline.close == 0:
            warnings.append(f"B macro {task_id}: missing baseline/reaction close; skipped")
            continue
        return_pct = (reaction.close - baseline.close) / baseline.close * 100.0
        if return_pct == 0:
            warnings.append(f"B macro {task_id}: zero event return; skipped")
            continue
        row = {
            **{key: str(value) for key, value in event.items() if value is not None},
            "event_id": task_id,
            "event_subtype": "macro",
            "cutoff_date": event_date,
            "actual_direction": "up" if return_pct > 0 else "down",
            "actual_return_pct": f"{return_pct:.6f}",
            "baseline_trading_day": baseline.trading_day,
            "reaction_trading_day": reaction.trading_day,
        }
        record = build_b_record(
            row,
            template,
            source_name,
            market=market,
            currency=str(event.get("currency") or currency_for_market(market)),
        )
        record["metadata"]["outcome_available_at_source"] = (
            "observed_yahoo_release_adjusted_close"
        )
        records.append(record)
        seen_ids.add(task_id)
    return records, warnings


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
            record = build_c_record(
                row, template, source_name, market=market, currency=currency
            )
            record["metadata"]["fundamentals_source"] = fund.__class__.__name__
            record["metadata"]["fundamentals_source_tier"] = str(
                getattr(fund, "source_tier", "unknown")
            )
            record["metadata"]["track"] = (
                "research_yahoo" if source_name == "yahoo" else "official_filing_primary"
            )
            record["metadata"]["statement_freq"] = pair.get(
                "statement_freq", "quarterly"
            )
            records.append(record)

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

PANEL_TASK_FILES = {
    "A1": "a1_valuation.jsonl",
    "A2-F": "a2_fundamentals.jsonl",
    "A2-T": "a2_technical.jsonl",
    "A2-H": "a2_hybrid.jsonl",
    "B": "b_event.jsonl",
    "C": "c_financial_metric.jsonl",
}


def _stamp_panel_metadata(
    records: list[dict[str, Any]],
    *,
    panel_id: str | None,
    horizon_days: int,
    cutoff_date: str,
    pair_id: str | None = None,
) -> list[dict[str, Any]]:
    """Attach panel tags used by aligned-panel validation."""
    if not panel_id:
        return records
    stamped: list[dict[str, Any]] = []
    for record in records:
        row = dict(record)
        metadata = dict(row.get("metadata") or {})
        metadata["panel"] = panel_id
        metadata["panel_horizon_days"] = horizon_days
        metadata["panel_cutoff_date"] = cutoff_date
        if pair_id:
            metadata["panel_pair_id"] = pair_id
        row["metadata"] = metadata
        stamped.append(row)
    return stamped


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
    horizon_days: int = A2_PREDICTION_WINDOW_DAYS,
    panel_id: str | None = None,
    pair_id: str | None = None,
) -> dict[str, Any]:
    """Generate records and write them to output."""
    if task not in TASK_HANDLERS:
        raise ValueError(f"Unsupported task: {task}. This round supports {SUPPORTED_TASKS}.")
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}")

    provider = _provider(provider_name)
    handler, identity_fn = TASK_HANDLERS[task]
    handler_kwargs: dict[str, Any] = {"source_name": provider_name}
    if task == "A1":
        handler_kwargs["primary_horizon_days"] = horizon_days
    if task in {"A2-T", "A2-F", "A2-H"}:
        handler_kwargs["prediction_window_days"] = horizon_days
    generated, warnings = handler(market, cutoff_date, provider, **handler_kwargs)
    generated = _stamp_panel_metadata(
        generated,
        panel_id=panel_id,
        horizon_days=horizon_days,
        cutoff_date=cutoff_date,
        pair_id=pair_id,
    )
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
        "horizon_days": horizon_days,
        "panel_id": panel_id,
        "output": str(output_path),
        "generated": len(generated),
        "added": added,
        "output_records": len(merged),
        "warnings": warnings,
    }


def generate_panel(
    cutoff_date: str,
    *,
    markets: list[str] | tuple[str, ...] = SUPPORTED_MARKETS,
    tasks: list[str] | tuple[str, ...] = ("A1", "A2-F", "A2-T", "A2-H"),
    horizon_days: int = A2_PREDICTION_WINDOW_DAYS,
    provider_name: str = "yahoo",
    output_dir: str | Path = "seeds/aligned",
    panel_id: str = "aligned_v1",
    pair_id: str | None = None,
    append: bool = True,
    replace: bool = True,
    training_cutoff: str = DEFAULT_TRAINING_CUTOFF,
    current_date: str = DEFAULT_CURRENT_DATE,
) -> dict[str, Any]:
    """Generate all configured tasks/markets for one cutoff into output_dir."""
    parse_iso_date(cutoff_date)
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    jobs: list[dict[str, Any]] = []
    for task in tasks:
        if task not in PANEL_TASK_FILES:
            raise ValueError(f"Unsupported panel task: {task}")
        output = out_root / PANEL_TASK_FILES[task]
        for market in markets:
            if market not in SUPPORTED_MARKETS:
                raise ValueError(f"Unsupported market: {market}")
            summary = generate(
                task,
                market,
                cutoff_date,
                provider_name=provider_name,
                output=output,
                append=append,
                replace=replace,
                training_cutoff=training_cutoff,
                current_date=current_date,
                horizon_days=horizon_days,
                panel_id=panel_id,
                pair_id=pair_id,
            )
            jobs.append(summary)
    return {
        "mode": "panel",
        "cutoff_date": cutoff_date,
        "markets": list(markets),
        "tasks": list(tasks),
        "horizon_days": horizon_days,
        "panel_id": panel_id,
        "output_dir": str(out_root),
        "jobs": jobs,
        "generated_total": sum(job["generated"] for job in jobs),
        "added_total": sum(job["added"] for job in jobs),
    }


def main() -> int:
    """CLI entry for data_generator."""
    args = parse_args()
    if args.panel:
        markets = [item.strip() for item in args.markets.split(",") if item.strip()]
        tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
        output_dir = args.output_dir or "seeds/aligned"
        summary = generate_panel(
            args.cutoff_date,
            markets=markets,
            tasks=tasks,
            horizon_days=args.horizon,
            provider_name=args.provider,
            output_dir=output_dir,
            panel_id=args.panel_id or "aligned_v1",
            append=True,
            replace=True,
            training_cutoff=args.training_cutoff,
            current_date=args.current_date,
        )
    else:
        if not args.task or not args.market or not args.output:
            raise SystemExit("Single-task mode requires --task, --market, and --output.")
        summary = generate(
            args.task,
            args.market,
            args.cutoff_date,
            provider_name=args.provider,
            output=args.output,
            append=args.append,
            replace=args.replace,
            training_cutoff=args.training_cutoff,
            current_date=args.current_date,
            horizon_days=args.horizon,
            panel_id=args.panel_id,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
