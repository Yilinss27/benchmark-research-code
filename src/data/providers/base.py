"""Provider interfaces for historical prices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol


@dataclass(frozen=True)
class PriceBar:
    """One daily close observation."""

    trading_day: str
    close: float


def parse_iso_date(value: str) -> date:
    """Parse YYYY-MM-DD."""
    return date.fromisoformat(value)


def add_calendar_days(iso_date: str, days: int) -> str:
    """Add calendar days to an ISO date string."""
    return (parse_iso_date(iso_date) + timedelta(days=days)).isoformat()


FORWARD_COVERAGE_GAP_DAYS = 14


def has_forward_coverage(last_available: str, target_date: str, max_gap_days: int = FORWARD_COVERAGE_GAP_DAYS) -> bool:
    """Return True if history reaches near the target date (holiday gaps allowed)."""
    return parse_iso_date(last_available) >= parse_iso_date(target_date) - timedelta(days=max_gap_days)


def as_iso(value: date | datetime | str) -> str:
    """Normalize a date-like value to YYYY-MM-DD."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


class PriceProvider(Protocol):
    """Minimal price history interface used by data_generator."""

    def get_price_history(
        self,
        symbol: str,
        market: str,
        start_date: str,
        end_date: str,
    ) -> list[PriceBar]:
        """Return daily closes in [start_date, end_date], ascending by trading_day."""

    def get_close_on_or_before(
        self,
        symbol: str,
        market: str,
        as_of_date: str,
    ) -> PriceBar | None:
        """Latest close on or before as_of_date."""

    def get_forward_close(
        self,
        symbol: str,
        market: str,
        cutoff_date: str,
        horizon_days: int,
    ) -> PriceBar | None:
        """Close on or before cutoff_date + horizon_days, strictly after cutoff close date if possible."""
