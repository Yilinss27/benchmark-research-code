"""CNINFO disclosure adapter backed by reviewed official announcement rows."""

from __future__ import annotations

from pathlib import Path

from src.data.providers.base import OfficialDisclosure
from src.data.providers.official import OfficialRegistryProvider


class CninfoProvider:
    """Resolve A-share filings without relying on unstable search endpoints."""

    def __init__(
        self, index_path: Path | str = "configs/official_disclosures_v1.jsonl"
    ) -> None:
        self.registry = OfficialRegistryProvider(index_path)

    def find_disclosure(
        self,
        symbol: str,
        market: str,
        report_period: str,
        *,
        form_types: tuple[str, ...] = (),
    ) -> OfficialDisclosure | None:
        if market != "CN_A":
            return None
        return self.registry.find_disclosure(
            symbol,
            market,
            report_period,
            form_types=form_types,
        )

    def find_event_disclosure(
        self,
        symbol: str,
        market: str,
        event_date: str,
        *,
        max_days: int = 7,
    ) -> OfficialDisclosure | None:
        if market != "CN_A":
            return None
        return self.registry.find_event_disclosure(
            symbol, market, event_date, max_days=max_days
        )
