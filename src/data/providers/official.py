"""Curated first-party disclosure registry with strict source validation."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from src.data.providers.base import OfficialDisclosure


DEFAULT_DISCLOSURE_INDEX = Path("configs/official_disclosures_v1.jsonl")
OFFICIAL_HOSTS = {
    "CN_A": ("cninfo.com.cn", "sse.com.cn", "szse.cn"),
    "US": ("sec.gov",),
    "HK": ("hkexnews.hk", "hkex.com.hk"),
    "MACRO": ("bls.gov", "stats.gov.cn", "info.gov.hk", "federalreserve.gov"),
}


def is_official_url(url: str, market: str) -> bool:
    """Return whether URL belongs to an allow-listed first-party host."""
    host = (urlparse(url).hostname or "").lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in OFFICIAL_HOSTS[market])


class OfficialRegistryProvider:
    """Resolve disclosures from a reviewed local JSONL registry."""

    def __init__(self, path: Path | str = DEFAULT_DISCLOSURE_INDEX) -> None:
        self.path = Path(path)
        self._rows: list[dict[str, object]] | None = None

    def _load(self) -> list[dict[str, object]]:
        if self._rows is not None:
            return self._rows
        if not self.path.exists():
            self._rows = []
            return self._rows
        self._rows = [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return self._rows

    def find_disclosure(
        self,
        symbol: str,
        market: str,
        report_period: str,
        *,
        form_types: tuple[str, ...] = (),
    ) -> OfficialDisclosure | None:
        """Return the earliest exact stock/period match from official hosts."""
        matches = []
        for row in self._load():
            if (
                str(row.get("stock_code")) != symbol
                or str(row.get("market")) != market
                or str(row.get("report_period")) != report_period
            ):
                continue
            form_type = str(row.get("form_type") or "")
            if form_types and form_type not in form_types:
                continue
            source_url = str(row.get("source_url") or "")
            if not is_official_url(source_url, market):
                continue
            matches.append(row)
        if not matches:
            return None
        row = min(matches, key=lambda item: str(item.get("published_at") or "9999"))
        return OfficialDisclosure(
            market=market,
            stock_code=symbol,
            report_period=report_period,
            published_at=str(row["published_at"]),
            source_url=str(row["source_url"]),
            source=str(row.get("source") or "official_registry"),
            document_id=str(row["document_id"]) if row.get("document_id") else None,
            title=str(row["title"]) if row.get("title") else None,
            fetched_at=str(row["fetched_at"]) if row.get("fetched_at") else None,
            content_sha256=(
                str(row["content_sha256"]) if row.get("content_sha256") else None
            ),
            parser_version=(
                str(row["parser_version"]) if row.get("parser_version") else None
            ),
            fields=row.get("fields") if isinstance(row.get("fields"), dict) else None,
        )

    def find_event_disclosure(
        self,
        symbol: str,
        market: str,
        event_date: str,
        *,
        max_days: int = 7,
    ) -> OfficialDisclosure | None:
        """Return the closest official announcement within max_days."""
        target = date.fromisoformat(event_date)
        matches = []
        for row in self._load():
            if str(row.get("stock_code")) != symbol or str(row.get("market")) != market:
                continue
            source_url = str(row.get("source_url") or "")
            published = str(row.get("published_at") or "")[:10]
            if not published or not is_official_url(source_url, market):
                continue
            gap = abs((date.fromisoformat(published) - target).days)
            if gap <= max_days:
                matches.append((gap, published, row))
        if not matches:
            return None
        _, _, row = min(matches, key=lambda item: (item[0], item[1]))
        return OfficialDisclosure(
            market=market,
            stock_code=symbol,
            report_period=str(row.get("report_period") or ""),
            published_at=str(row["published_at"]),
            source_url=str(row["source_url"]),
            source=str(row.get("source") or "official_registry"),
            document_id=str(row["document_id"]) if row.get("document_id") else None,
            title=str(row["title"]) if row.get("title") else None,
            fetched_at=str(row["fetched_at"]) if row.get("fetched_at") else None,
            content_sha256=(
                str(row["content_sha256"]) if row.get("content_sha256") else None
            ),
            parser_version=(
                str(row["parser_version"]) if row.get("parser_version") else None
            ),
            fields=row.get("fields") if isinstance(row.get("fields"), dict) else None,
        )


class OfficialFundamentalsProvider:
    """Read normalized, reviewed filing values available by a cutoff."""

    source_tier = "official_filing"

    def __init__(self, path: Path | str = DEFAULT_DISCLOSURE_INDEX) -> None:
        self.registry = OfficialRegistryProvider(path)

    def fundamentals_snapshot(
        self,
        symbol: str,
        market: str,
        cutoff_date: str,
        cutoff_price: float,
    ) -> dict[str, object] | None:
        candidates = []
        for row in self.registry._load():
            fields = row.get("fields")
            published_at = str(row.get("published_at") or "")[:10]
            source_url = str(row.get("source_url") or "")
            if (
                str(row.get("stock_code")) == symbol
                and str(row.get("market")) == market
                and isinstance(fields, dict)
                and published_at
                and published_at <= cutoff_date
                and is_official_url(source_url, market)
            ):
                candidates.append(row)
        if not candidates:
            return None
        row = max(candidates, key=lambda item: str(item["published_at"]))
        snapshot = dict(row["fields"])
        snapshot.update(
            {
                "price": cutoff_price,
                "trading_day": cutoff_date,
                "snapshot_date": str(row["published_at"])[:10],
                "source_url": row["source_url"],
                "source_tier": self.source_tier,
            }
        )
        return snapshot
