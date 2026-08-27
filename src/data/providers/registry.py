"""Official disclosure provider selection by market."""

from __future__ import annotations

from pathlib import Path

from src.data.providers.base import DisclosureProvider, OfficialDisclosure
from src.data.providers.cninfo import CninfoProvider
from src.data.providers.hkex import HkexProvider
from src.data.providers.official import OfficialRegistryProvider
from src.data.providers.sec_edgar import SecEdgarProvider


class CompositeDisclosureProvider:
    """Use reviewed registry rows before a live official provider."""

    def __init__(self, providers: list[DisclosureProvider]) -> None:
        self.providers = providers

    def find_disclosure(
        self,
        symbol: str,
        market: str,
        report_period: str,
        *,
        form_types: tuple[str, ...] = (),
    ) -> OfficialDisclosure | None:
        for provider in self.providers:
            result = provider.find_disclosure(
                symbol, market, report_period, form_types=form_types
            )
            if result is not None:
                return result
        return None

    def find_event_disclosure(
        self,
        symbol: str,
        market: str,
        event_date: str,
        *,
        max_days: int = 7,
    ) -> OfficialDisclosure | None:
        for provider in self.providers:
            result = provider.find_event_disclosure(
                symbol, market, event_date, max_days=max_days
            )
            if result is not None:
                return result
        return None


def official_disclosure_provider(
    market: str,
    *,
    index_path: Path | str = "configs/official_disclosures_v1.jsonl",
    sec_user_agent: str | None = None,
) -> DisclosureProvider:
    """Return the first-party disclosure provider for a market."""
    if market == "CN_A":
        return CninfoProvider(index_path)
    if market == "HK":
        return HkexProvider(index_path)
    if market == "US":
        return CompositeDisclosureProvider(
            [
                OfficialRegistryProvider(index_path),
                SecEdgarProvider(user_agent=sec_user_agent),
            ]
        )
    raise ValueError(f"Unsupported market: {market}")
