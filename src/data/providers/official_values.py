"""Official filing metric lookup for C-task value provenance."""

from __future__ import annotations

import json
import os
import ssl
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from src.data.provenance import read_provenance, write_provenance
from src.data.providers.official import DEFAULT_DISCLOSURE_INDEX, OfficialRegistryProvider

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
PARSER_VERSION = "official_metric_sec_companyfacts_v1"
US_FORMS = {"10-Q", "10-K", "20-F", "6-K"}

METRIC_TAGS = {
    "operating_revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ),
    "net_profit": (
        "NetIncomeLoss",
        "ProfitLoss",
    ),
}


@dataclass(frozen=True)
class OfficialMetricObservation:
    """One official filing metric value with provenance."""

    metric_name: str
    value: float
    report_period: str
    published_at: str
    source: str
    source_url: str
    evidence_code: str


class SecCompanyFactsProvider:
    """Resolve US filing values from SEC companyfacts JSON."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        cache_dir: Path | str = "data/cache/official/sec",
    ) -> None:
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT", "")
        self.cache_dir = Path(cache_dir)
        self._ticker_map: dict[str, str] | None = None

    def _get_json(self, url: str, cache_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
        cached = read_provenance(cache_key, cache_dir=self.cache_dir)
        if cached:
            content, provenance = cached
            return json.loads(content), provenance
        if not self.user_agent:
            raise RuntimeError(
                "SEC_USER_AGENT is required for live SEC requests "
                "(for example: 'project-name contact@example.com')"
            )
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "identity",
                "Host": "data.sec.gov" if "data.sec.gov" in url else "www.sec.gov",
            },
        )
        try:
            import certifi

            ssl_context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ssl_context = ssl.create_default_context()
        with urlopen(request, timeout=30, context=ssl_context) as response:
            content = response.read().decode("utf-8")
        provenance = write_provenance(
            cache_key,
            source_url=url,
            content=content,
            parser_version=PARSER_VERSION,
            cache_dir=self.cache_dir,
        )
        return json.loads(content), provenance

    def _cik_for_ticker(self, symbol: str) -> str | None:
        if self._ticker_map is None:
            payload, _ = self._get_json(SEC_TICKERS_URL, "company_tickers")
            self._ticker_map = {
                str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
                for row in payload.values()
            }
        return self._ticker_map.get(symbol.upper())

    @staticmethod
    def _day_gap(a: str, b: str) -> int:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)

    def find_metric_value(
        self,
        symbol: str,
        report_period: str,
        metric_name: str,
        *,
        max_report_period_gap_days: int = 7,
    ) -> OfficialMetricObservation | None:
        tags = METRIC_TAGS.get(metric_name)
        if not tags:
            return None
        cik = self._cik_for_ticker(symbol)
        if cik is None:
            return None
        url = SEC_COMPANY_FACTS_URL.format(cik=cik)
        payload, _ = self._get_json(url, f"companyfacts_{cik}")
        gaap = payload.get("facts", {}).get("us-gaap", {})

        candidates: list[tuple[int, str, float, str, str]] = []
        for tag in tags:
            fact = gaap.get(tag)
            if not isinstance(fact, dict):
                continue
            units = fact.get("units", {})
            for unit_name, rows in units.items():
                if unit_name not in {"USD", "USDm", "USD/shares", "shares"}:
                    continue
                for row in rows or []:
                    end = str(row.get("end") or "")[:10]
                    filed = str(row.get("filed") or "")[:10]
                    form = str(row.get("form") or "")
                    val = row.get("val")
                    if (
                        not end
                        or not filed
                        or form not in US_FORMS
                        or not isinstance(val, (int, float))
                    ):
                        continue
                    gap = self._day_gap(end, report_period)
                    if gap > max_report_period_gap_days:
                        continue
                    candidates.append((gap, filed, float(val), form, tag))
        if not candidates:
            return None
        gap, filed, value, form, tag = min(candidates, key=lambda item: (item[0], item[1]))
        return OfficialMetricObservation(
            metric_name=metric_name,
            value=value,
            report_period=report_period,
            published_at=filed,
            source="sec_companyfacts",
            source_url=url,
            evidence_code=f"{form}:{tag}:gap{gap}d",
        )


class OfficialMetricProvider:
    """Market-aware official metric lookup for C-task values."""

    def __init__(
        self,
        *,
        index_path: Path | str = DEFAULT_DISCLOSURE_INDEX,
        sec_user_agent: str | None = None,
    ) -> None:
        self.registry = OfficialRegistryProvider(index_path)
        self.sec_companyfacts = SecCompanyFactsProvider(user_agent=sec_user_agent)

    @staticmethod
    def _as_float(value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip().replace(",", "")
            if not stripped:
                return None
            try:
                return float(stripped)
            except ValueError:
                return None
        return None

    def _registry_metric_value(
        self,
        symbol: str,
        market: str,
        report_period: str,
        metric_name: str,
    ) -> OfficialMetricObservation | None:
        disclosure = self.registry.find_disclosure(
            symbol,
            market,
            report_period,
            form_types=("10-Q", "10-K", "annual", "interim", "quarterly"),
        )
        if disclosure is None or not isinstance(disclosure.fields, dict):
            return None
        value = self._as_float(disclosure.fields.get(metric_name))
        if value is None:
            return None
        return OfficialMetricObservation(
            metric_name=metric_name,
            value=value,
            report_period=report_period,
            published_at=disclosure.published_at[:10],
            source=str(disclosure.source or "official_registry"),
            source_url=disclosure.source_url,
            evidence_code=disclosure.document_id or "official_registry_fields",
        )

    def find_metric_value(
        self,
        symbol: str,
        market: str,
        report_period: str,
        metric_name: str,
    ) -> OfficialMetricObservation | None:
        from_registry = self._registry_metric_value(symbol, market, report_period, metric_name)
        if from_registry is not None:
            return from_registry
        if market == "US":
            return self.sec_companyfacts.find_metric_value(
                symbol,
                report_period,
                metric_name,
            )
        return None
