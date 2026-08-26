"""Enrich B/C temporal fields from Yahoo prices and financials."""

from __future__ import annotations

from typing import Any

from src.data.providers.base import add_calendar_days
from src.data.providers.yahoo import YahooPriceProvider
from src.data.yahoo_fundamentals import ANNUAL_LAG_DAYS, QUARTER_LAG_DAYS, YahooFundamentals


def enrich_b_outcome(record: dict[str, Any], provider: YahooPriceProvider | None = None) -> dict[str, Any]:
    """Return outcome_available_at and evidence for a B earnings record."""
    seed = record.get("seed") or {}
    market = seed.get("market") or record.get("metadata", {}).get("market") or "CN_A"
    code = str(seed.get("stock_code", ""))
    event_date = str(seed.get("event_date") or seed.get("cutoff_date"))
    price_provider = provider or YahooPriceProvider()

    start = add_calendar_days(event_date, -5)
    end = add_calendar_days(event_date, 10)
    bars = price_provider.get_price_history(code, market, start, end)
    next_bars = [bar for bar in bars if bar.trading_day > event_date]
    if next_bars:
        outcome = next_bars[0].trading_day
        return {
            "outcome_available_at": outcome,
            "outcome_available_at_source": "observed_yahoo_next_session_close",
            "outcome_evidence_code": "yahoo_next_session_close",
            "outcome_evidence_url": None,
            "quality_flags": [],
        }
    return {
        "outcome_available_at": add_calendar_days(event_date, 1),
        "outcome_available_at_source": "heuristic_event_plus_1d",
        "outcome_evidence_code": "heuristic_event_plus_1d",
        "outcome_evidence_url": None,
        "quality_flags": ["modeled_outcome_availability"],
    }


def enrich_c_outcome(record: dict[str, Any], fundamentals: YahooFundamentals | None = None) -> dict[str, Any]:
    """Estimate C availability from period end plus a documented filing lag.

    This is deliberately labeled modeled, not an observed first-publication date.
    """
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}
    future_period = str(seed.get("report_period_future") or "")
    if not future_period:
        return {
            "outcome_available_at": add_calendar_days(str(seed.get("cutoff_date")), 90),
            "outcome_available_at_source": "modeled_cutoff_plus_90d",
            "outcome_evidence_code": "heuristic_cutoff_plus_90d",
            "outcome_evidence_url": None,
            "quality_flags": ["modeled_outcome_availability"],
        }

    freq = metadata.get("statement_freq") or "quarterly"
    lag = QUARTER_LAG_DAYS if freq == "quarterly" else ANNUAL_LAG_DAYS
    if len(future_period) == 10 and future_period[5:] in {"12-31"}:
        lag = ANNUAL_LAG_DAYS
    outcome = add_calendar_days(future_period, lag)
    return {
        "outcome_available_at": outcome,
        "outcome_available_at_source": f"modeled_report_period_plus_{lag}d",
        "outcome_evidence_code": f"report_period_future_plus_{lag}d",
        "outcome_evidence_url": None,
        "quality_flags": ["modeled_outcome_availability"],
    }
