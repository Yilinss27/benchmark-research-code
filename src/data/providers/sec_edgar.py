"""SEC EDGAR first-publication lookup for US issuers."""

from __future__ import annotations

import json
import os
import ssl
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from src.data.provenance import read_provenance, write_provenance
from src.data.providers.base import OfficialDisclosure


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
PARSER_VERSION = "sec_edgar_v1"


class SecEdgarProvider:
    """Resolve SEC filings by ticker and report period."""

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
                "SEC_USER_AGENT is required for live EDGAR requests "
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

    def find_disclosure(
        self,
        symbol: str,
        market: str,
        report_period: str,
        *,
        form_types: tuple[str, ...] = ("10-Q", "10-K", "8-K"),
    ) -> OfficialDisclosure | None:
        """Return the earliest SEC filing whose report date matches the period."""
        if market != "US":
            return None
        cik = self._cik_for_ticker(symbol)
        if cik is None:
            return None
        url = SEC_SUBMISSIONS_URL.format(cik=cik)
        payload, provenance = self._get_json(url, f"submissions_{cik}")
        recent = payload.get("filings", {}).get("recent", {})
        candidates: list[dict[str, str]] = []
        for index, report_date in enumerate(recent.get("reportDate", [])):
            form = str(recent.get("form", [""])[index])
            if report_date != report_period or (form_types and form not in form_types):
                continue
            candidates.append(
                {
                    "filed": str(recent["filingDate"][index]),
                    "accession": str(recent["accessionNumber"][index]),
                    "primary_document": str(recent["primaryDocument"][index]),
                    "form": form,
                }
            )
        if not candidates:
            return None
        filing = min(candidates, key=lambda row: row["filed"])
        accession_compact = filing["accession"].replace("-", "")
        document_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession_compact}/{filing['primary_document']}"
        )
        return OfficialDisclosure(
            market=market,
            stock_code=symbol,
            report_period=report_period,
            published_at=filing["filed"],
            source_url=document_url,
            source="sec_edgar",
            document_id=filing["accession"],
            title=f"{filing['form']} for {report_period}",
            fetched_at=str(provenance.get("fetched_at") or ""),
            content_sha256=str(provenance.get("content_sha256") or ""),
            parser_version=PARSER_VERSION,
        )

    def find_event_disclosure(
        self,
        symbol: str,
        market: str,
        event_date: str,
        *,
        max_days: int = 7,
    ) -> OfficialDisclosure | None:
        """Return the closest 8-K/10-Q/10-K filing near an earnings event."""
        if market != "US":
            return None
        cik = self._cik_for_ticker(symbol)
        if cik is None:
            return None
        url = SEC_SUBMISSIONS_URL.format(cik=cik)
        payload, provenance = self._get_json(url, f"submissions_{cik}")
        recent = payload.get("filings", {}).get("recent", {})
        target = date.fromisoformat(event_date)
        candidates: list[tuple[int, int, dict[str, str]]] = []
        form_priority = {"8-K": 0, "10-Q": 1, "10-K": 1}
        for index, filed in enumerate(recent.get("filingDate", [])):
            form = str(recent.get("form", [""])[index])
            if form not in form_priority:
                continue
            gap = abs((date.fromisoformat(str(filed)) - target).days)
            if gap > max_days:
                continue
            candidates.append(
                (
                    gap,
                    form_priority[form],
                    {
                        "filed": str(filed),
                        "accession": str(recent["accessionNumber"][index]),
                        "primary_document": str(recent["primaryDocument"][index]),
                        "report_date": str(recent["reportDate"][index]),
                        "form": form,
                    },
                )
            )
        if not candidates:
            return None
        filing = min(candidates, key=lambda item: (item[0], item[1]))[2]
        accession_compact = filing["accession"].replace("-", "")
        document_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession_compact}/{filing['primary_document']}"
        )
        return OfficialDisclosure(
            market=market,
            stock_code=symbol,
            report_period=filing["report_date"],
            published_at=filing["filed"],
            source_url=document_url,
            source="sec_edgar",
            document_id=filing["accession"],
            title=f"{filing['form']} near earnings event {event_date}",
            fetched_at=str(provenance.get("fetched_at") or ""),
            content_sha256=str(provenance.get("content_sha256") or ""),
            parser_version=PARSER_VERSION,
        )
