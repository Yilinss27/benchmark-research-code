"""Enrich temporal fields from observed prices and first-party disclosures."""

from __future__ import annotations

from typing import Any

from src.data.providers.base import DisclosureProvider, PriceProvider, add_calendar_days
from src.data.providers.yahoo import YahooPriceProvider
from src.data.yahoo_fundamentals import ANNUAL_LAG_DAYS, QUARTER_LAG_DAYS


def enrich_b_outcome(
    record: dict[str, Any],
    provider: PriceProvider | None = None,
    disclosure_provider: DisclosureProvider | None = None,
) -> dict[str, Any]:
    """Return release-adjusted outcome availability and official event evidence."""
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}
    market = str(seed.get("market") or metadata.get("market") or "CN_A")
    code = str(seed.get("stock_code", ""))
    event_date = str(seed.get("event_date") or seed.get("cutoff_date"))
    price_provider = provider or YahooPriceProvider()
    event_url = str(seed.get("event_url") or metadata.get("event_evidence_url") or "")
    if not event_url and disclosure_provider is not None:
        try:
            disclosure = disclosure_provider.find_event_disclosure(
                code, market, event_date
            )
        except Exception:
            disclosure = None
        if disclosure is not None:
            event_url = disclosure.source_url

    start = add_calendar_days(event_date, -21)
    end = add_calendar_days(event_date, 21)
    bars = price_provider.get_price_history(code, market, start, end)
    phase = str(seed.get("release_phase") or "after_market")
    if phase in {"pre_market", "market_hours"}:
        reaction_bars = [bar for bar in bars if bar.trading_day >= event_date]
    else:
        reaction_bars = [bar for bar in bars if bar.trading_day > event_date]
    if reaction_bars:
        outcome = reaction_bars[0].trading_day
        flags = [] if event_url else ["missing_event_evidence"]
        return {
            "outcome_available_at": outcome,
            "outcome_available_at_source": "observed_yahoo_release_adjusted_close",
            "outcome_evidence_code": f"observed_close:{outcome}",
            "outcome_evidence_url": event_url or None,
            "quality_flags": flags,
        }
    return {
        "outcome_available_at": add_calendar_days(event_date, 1),
        "outcome_available_at_source": "heuristic_event_plus_1d",
        "outcome_evidence_code": "heuristic_event_plus_1d",
        "outcome_evidence_url": event_url or None,
        "quality_flags": [
            "modeled_outcome_availability",
            *(["missing_event_evidence"] if not event_url else []),
        ],
    }


def enrich_c_outcome(
    record: dict[str, Any],
    disclosure_provider: DisclosureProvider | None = None,
) -> dict[str, Any]:
    """Use a first-party filing date, falling back to a clearly modeled lag."""
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}
    future_period = str(seed.get("report_period_future") or "")
    market = str(seed.get("market") or metadata.get("market") or "CN_A")
    code = str(seed.get("stock_code") or "")
    if future_period and disclosure_provider is not None:
        try:
            disclosure = disclosure_provider.find_disclosure(
                code, market, future_period, form_types=("10-Q", "10-K", "annual", "interim", "quarterly")
            )
        except Exception:
            disclosure = None
        if disclosure is not None:
            return {
                "outcome_available_at": disclosure.published_at[:10],
                "outcome_available_at_source": f"observed_{disclosure.source}_first_publication",
                "outcome_evidence_code": disclosure.document_id or "official_filing",
                "outcome_evidence_url": disclosure.source_url,
                "quality_flags": [],
            }
    if not future_period:
        return {
            "outcome_available_at": add_calendar_days(str(seed.get("cutoff_date")), 90),
            "outcome_available_at_source": "modeled_cutoff_plus_90d",
            "outcome_evidence_code": "heuristic_cutoff_plus_90d",
            "outcome_evidence_url": None,
            "quality_flags": [
                "modeled_outcome_availability",
                "official_disclosure_lookup_failed",
                "non_pit_fundamentals",
            ],
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
        "quality_flags": [
            "modeled_outcome_availability",
            "official_disclosure_lookup_failed",
            "non_pit_fundamentals",
        ],
    }


def enrich_price_outcome(
    record: dict[str, Any],
    provider: PriceProvider | None = None,
) -> dict[str, Any]:
    """Resolve A1/A2 availability to the actual forward trading day."""
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}
    market = str(seed.get("market") or metadata.get("market") or "CN_A")
    cutoff = str(seed.get("cutoff_date") or record.get("cutoff_date"))
    category = record.get("category")
    window = int(
        (record.get("ground_truth") or {}).get("primary_eval_window_days")
        or seed.get("prediction_window_days")
        or metadata.get("panel_horizon_days")
        or 30
    )
    price_provider = provider or YahooPriceProvider()
    if category == "A1":
        codes = [str(seed.get("stock_code") or "")]
    else:
        codes = [
            str(item.get("code"))
            for item in seed.get("stock_list", [])
            if item.get("code")
        ]
    observed: dict[str, str] = {}
    for code in codes:
        try:
            bar = price_provider.get_forward_close(code, market, cutoff, window)
        except Exception:
            bar = None
        if bar is not None:
            observed[code] = bar.trading_day
    if codes and len(observed) == len(codes):
        outcome = max(observed.values())
        return {
            "outcome_available_at": outcome,
            "outcome_available_at_source": "observed_yahoo_forward_trading_day",
            "outcome_evidence_code": (
                f"forward_close_{window}d:"
                + ",".join(f"{code}={day}" for code, day in sorted(observed.items()))
            ),
            "outcome_evidence_url": None,
            "quality_flags": [],
            "forward_trading_days": observed,
        }
    return {
        "outcome_available_at": add_calendar_days(cutoff, window),
        "outcome_available_at_source": f"modeled_cutoff_plus_{window}d",
        "outcome_evidence_code": f"forward_close_{window}d_incomplete",
        "outcome_evidence_url": None,
        "quality_flags": [
            "missing_forward_trading_day",
            "modeled_outcome_availability",
        ],
        "forward_trading_days": observed,
    }
