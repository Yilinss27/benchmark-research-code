#!/usr/bin/env python3
"""Backfill official disclosure registry rows for unresolved C/B gaps."""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.providers.official import DEFAULT_DISCLOSURE_INDEX
from src.data.providers.sec_edgar import SEC_SUBMISSIONS_URL, SecEdgarProvider

HKEX_BASE = "https://www1.hkexnews.hk"
HKEX_PARSER_VERSION = "manual_official_registry_v1_hkex_gap_backfill"
US_PARSER_VERSION = "manual_official_registry_v1_sec_gap_backfill"


@dataclass(frozen=True)
class HkexCandidate:
    stock_code: str
    title: str
    published_at: str
    source_url: str
    news_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(DEFAULT_DISCLOSURE_INDEX))
    parser.add_argument("--gaps", default="calibration/temporal_provenance_gaps.csv")
    parser.add_argument("--c-seed", default="seeds/c_financial_metric.jsonl")
    parser.add_argument("--b-seed", default="seeds/b_event.jsonl")
    parser.add_argument("--sec-user-agent", default="benchmark-research yilin@example.com")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def month_iter(start: date, end: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        out.append((cursor.year, cursor.month))
        cursor = date(cursor.year + (cursor.month // 12), (cursor.month % 12) + 1, 1)
    return out


def clean_title(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()


def load_hkex_rows(year: int, month: int, *, keyword: str) -> list[dict[str, Any]]:
    last_day = calendar.monthrange(year, month)[1]
    params = {
        "sortDir": "0",
        "sortByOptions": "DateTime",
        "category": "0",
        "market": "SEHK",
        "stockId": "",
        "documentType": "",
        "fromDate": f"{year}{month:02d}01",
        "toDate": f"{year}{month:02d}{last_day:02d}",
        "title": keyword,
        "searchType": "1",
        "t1code": "-2",
        "t2Gcode": "-2",
        "t2code": "-2",
        "rowRange": "10000",
        "lang": "E",
    }
    payload = requests.get(
        f"{HKEX_BASE}/search/titleSearchServlet.do",
        params=params,
        timeout=90,
    ).json()
    raw = payload.get("result")
    if not raw:
        return []
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, list) else []


def stock_codes_from_row(row: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for raw in str(row.get("STOCK_CODE") or "").split("<br/>"):
        code = raw.strip()
        if len(code) == 5 and code.isdigit():
            result.append(code.lstrip("0") or "0")
    return result


def collect_hkex_pool(months: list[tuple[int, int]]) -> dict[str, list[dict[str, Any]]]:
    by_code: dict[str, list[dict[str, Any]]] = {}
    for year, month in sorted(set(months)):
        for keyword in ("RESULTS", "EARNINGS"):
            for row in load_hkex_rows(year, month, keyword=keyword):
                for code in stock_codes_from_row(row):
                    by_code.setdefault(code, []).append(row)
    return by_code


def pick_hk_c_candidate(rows: list[dict[str, Any]], report_period: str) -> HkexCandidate | None:
    target = date.fromisoformat(report_period)
    scored: list[tuple[int, datetime, dict[str, Any]]] = []
    for row in rows:
        title = clean_title(str(row.get("TITLE") or ""))
        upper = title.upper()
        if "RESULT" not in upper and "EARNING" not in upper:
            continue
        if "DELAY IN PUBLICATION" in upper:
            continue
        try:
            dt = datetime.strptime(str(row.get("DATE_TIME")), "%d/%m/%Y %H:%M")
        except ValueError:
            continue
        score = 0
        year = str(target.year)
        if year in upper:
            score += 1
        if target.month == 12 and "ANNUAL" in upper:
            score += 3
        if target.month == 3 and ("MARCH" in upper or "ANNUAL" in upper):
            score += 3
        if target.month == 12 and f"31 DECEMBER {target.year}" in upper:
            score += 5
        if target.month == 3 and f"31 MARCH {target.year}" in upper:
            score += 5
        # Prefer plausible publication windows after period close.
        if 0 <= (dt.date() - target).days <= 220:
            score += 2
        scored.append((score, dt, row))
    if not scored:
        return None
    score, dt, row = sorted(scored, key=lambda item: (-item[0], item[1]))[0]
    if score < 2:
        return None
    return HkexCandidate(
        stock_code="",
        title=clean_title(str(row.get("TITLE") or "")),
        published_at=dt.date().isoformat(),
        source_url=f"{HKEX_BASE}{row.get('FILE_LINK')}",
        news_id=str(row.get("NEWS_ID") or ""),
    )


def pick_hk_b_candidate(rows: list[dict[str, Any]], event_date: str) -> HkexCandidate | None:
    target = date.fromisoformat(event_date)
    scored: list[tuple[int, int, datetime, dict[str, Any]]] = []
    for row in rows:
        title = clean_title(str(row.get("TITLE") or ""))
        upper = title.upper()
        if "RESULT" not in upper and "EARNING" not in upper:
            continue
        if "DELAY IN PUBLICATION" in upper:
            continue
        try:
            dt = datetime.strptime(str(row.get("DATE_TIME")), "%d/%m/%Y %H:%M")
        except ValueError:
            continue
        gap = abs((dt.date() - target).days)
        if gap > 20:
            continue
        bonus = 0
        if "ANNOUNCEMENT OF THE" in upper:
            bonus += 1
        scored.append((gap, -bonus, dt, row))
    if not scored:
        return None
    _, _, dt, row = sorted(scored, key=lambda item: (item[0], item[1], item[2]))[0]
    return HkexCandidate(
        stock_code="",
        title=clean_title(str(row.get("TITLE") or "")),
        published_at=dt.date().isoformat(),
        source_url=f"{HKEX_BASE}{row.get('FILE_LINK')}",
        news_id=str(row.get("NEWS_ID") or ""),
    )


def c_window(report_period: str) -> tuple[date, date]:
    period = date.fromisoformat(report_period)
    if period.month == 12 and period.day == 31:
        return date(period.year + 1, 1, 1), date(period.year + 1, 6, 30)
    if period.month == 3 and period.day == 31:
        return date(period.year, 4, 1), date(period.year, 8, 31)
    return date(period.year, period.month, 1), date(period.year, period.month, calendar.monthrange(period.year, period.month)[1])


def parse_form_type(title: str) -> str:
    upper = title.upper()
    if "ANNUAL" in upper:
        return "annual"
    if "INTERIM" in upper or "HALF" in upper:
        return "interim"
    return "quarterly"


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def sec_filing_rows(
    provider: SecEdgarProvider,
    symbol: str,
    *,
    start_date: date,
    end_date: date,
    forms: set[str],
) -> list[dict[str, str]]:
    """Collect SEC filing rows from recent + archived submissions slices."""
    cik = provider._cik_for_ticker(symbol)  # noqa: SLF001 - controlled internal usage
    if cik is None:
        return []

    def rows_from_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
        filings: list[dict[str, str]] = []
        for idx, filed in enumerate(payload.get("filingDate", [])):
            form = str(payload.get("form", [""])[idx])
            if form not in forms:
                continue
            filed_date = _parse_iso_date(str(filed))
            if filed_date is None or filed_date < start_date or filed_date > end_date:
                continue
            filings.append(
                {
                    "form": form,
                    "filed": str(filed),
                    "reportDate": str(payload.get("reportDate", [""])[idx]),
                    "accessionNumber": str(payload.get("accessionNumber", [""])[idx]),
                    "primaryDocument": str(payload.get("primaryDocument", [""])[idx]),
                    "cik": cik,
                }
            )
        return filings

    root_payload, _ = provider._get_json(  # noqa: SLF001 - controlled internal usage
        SEC_SUBMISSIONS_URL.format(cik=cik),
        f"submissions_{cik}",
    )
    results: list[dict[str, str]] = []
    recent = root_payload.get("filings", {}).get("recent", {})
    if isinstance(recent, dict):
        results.extend(rows_from_payload(recent))

    for file_info in root_payload.get("filings", {}).get("files", []):
        from_date = _parse_iso_date(str(file_info.get("filingFrom") or ""))
        to_date = _parse_iso_date(str(file_info.get("filingTo") or ""))
        if from_date is None or to_date is None:
            continue
        if to_date < start_date or from_date > end_date:
            continue
        name = str(file_info.get("name") or "")
        if not name:
            continue
        payload, _ = provider._get_json(  # noqa: SLF001 - controlled internal usage
            f"https://data.sec.gov/submissions/{name}",
            name.replace(".json", ""),
        )
        if isinstance(payload, dict):
            results.extend(rows_from_payload(payload))
    return results


def best_us_disclosure(provider: SecEdgarProvider, symbol: str, report_period: str) -> dict[str, Any] | None:
    exact = provider.find_disclosure(symbol, "US", report_period, form_types=("10-Q", "10-K"))
    if exact is not None:
        return {
            "published_at": exact.published_at[:10],
            "source_url": exact.source_url,
            "document_id": exact.document_id,
            "title": exact.title or "",
            "form_type": "10-K" if "10-K" in (exact.title or "") else "10-Q",
            "source_report_period": None,
        }

    target = date.fromisoformat(report_period)
    candidates: list[tuple[int, str, dict[str, str]]] = []
    filings = sec_filing_rows(
        provider,
        symbol,
        start_date=target - timedelta(days=120),
        end_date=target + timedelta(days=120),
        forms={"10-Q", "10-K"},
    )
    for filing in filings:
        rp = str(filing.get("reportDate") or "")
        rp_date = _parse_iso_date(rp)
        if rp_date is None:
            continue
        gap = abs((rp_date - target).days)
        if gap > 45:
            continue
        candidates.append(
            (
                gap,
                str(filing["filed"]),
                {
                    "form": str(filing["form"]),
                    "report_period": rp,
                    "filed": str(filing["filed"]),
                    "accession": str(filing["accessionNumber"]),
                    "primary": str(filing["primaryDocument"]),
                    "cik": str(filing["cik"]),
                },
            )
        )
    if not candidates:
        return None
    _, _, best = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
    compact = best["accession"].replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(best['cik'])}/{compact}/{best['primary']}"
    return {
        "published_at": best["filed"][:10],
        "source_url": url,
        "document_id": best["accession"],
        "title": f"{best['form']} for {best['report_period']}",
        "form_type": best["form"],
        "source_report_period": best["report_period"],
    }


def main() -> int:
    args = parse_args()
    registry_path = ROOT / args.registry
    gaps_path = ROOT / args.gaps
    c_seed_path = ROOT / args.c_seed
    b_seed_path = ROOT / args.b_seed

    registry_rows = load_jsonl(registry_path)
    key_existing = {
        (
            str(row.get("market")),
            str(row.get("stock_code")),
            str(row.get("report_period")),
            str(row.get("source_url")),
        )
        for row in registry_rows
    }

    c_seed = {row["task_id"]: row for row in load_jsonl(c_seed_path)}
    b_seed = {row["task_id"]: row for row in load_jsonl(b_seed_path)}

    hk_c_targets: set[tuple[str, str]] = set()
    us_c_targets: set[tuple[str, str]] = set()
    hk_b_targets: set[tuple[str, str]] = set()
    us_b_targets: set[tuple[str, str]] = set()

    with gaps_path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            task_id = row["task_id"]
            category = row["category"]
            if category == "C" and task_id in c_seed:
                seed = c_seed[task_id]["seed"]
                market = str(seed.get("market"))
                code = str(seed.get("stock_code"))
                period = str(seed.get("report_period_future"))
                if market == "HK":
                    hk_c_targets.add((code, period))
                elif market == "US":
                    us_c_targets.add((code, period))
            if category == "B" and task_id in b_seed:
                seed = b_seed[task_id]["seed"]
                market = str(seed.get("market"))
                code = str(seed.get("stock_code"))
                event_date = str(seed.get("event_date") or seed.get("cutoff_date"))
                if market == "HK":
                    hk_b_targets.add((code, event_date))
                elif market == "US":
                    us_b_targets.add((code, event_date))

    months: list[tuple[int, int]] = []
    for code, period in sorted(hk_c_targets):
        start, end = c_window(period)
        months.extend(month_iter(start, end))
    for code, event_date in sorted(hk_b_targets):
        d = date.fromisoformat(event_date)
        months.append((d.year, d.month))

    hk_pool = collect_hkex_pool(months)

    additions: list[dict[str, Any]] = []
    misses: list[str] = []

    for code, period in sorted(hk_c_targets):
        rows = hk_pool.get(code.lstrip("0") or "0", [])
        pick = pick_hk_c_candidate(rows, period)
        if pick is None:
            misses.append(f"C HK miss {code} {period}")
            continue
        title = pick.title
        row = {
            "market": "HK",
            "stock_code": code,
            "report_period": period,
            "published_at": pick.published_at,
            "source_url": pick.source_url,
            "source": "hkex",
            "document_id": pick.news_id or None,
            "title": title,
            "form_type": parse_form_type(title),
            "parser_version": HKEX_PARSER_VERSION,
        }
        key = ("HK", code, period, pick.source_url)
        if key not in key_existing:
            additions.append(row)
            key_existing.add(key)

    for code, event_date in sorted(hk_b_targets):
        rows = hk_pool.get(code.lstrip("0") or "0", [])
        pick = pick_hk_b_candidate(rows, event_date)
        if pick is None:
            misses.append(f"B HK miss {code} {event_date}")
            continue
        key = ("HK", code, event_date, pick.source_url)
        row = {
            "market": "HK",
            "stock_code": code,
            "report_period": event_date,
            "published_at": pick.published_at,
            "source_url": pick.source_url,
            "source": "hkex",
            "document_id": pick.news_id or None,
            "title": pick.title,
            "form_type": "earnings_release",
            "parser_version": HKEX_PARSER_VERSION,
        }
        if key not in key_existing:
            additions.append(row)
            key_existing.add(key)

    sec_provider = SecEdgarProvider(user_agent=args.sec_user_agent)
    for code, period in sorted(us_c_targets):
        pick = best_us_disclosure(sec_provider, code, period)
        if pick is None:
            misses.append(f"C US miss {code} {period}")
            continue
        row = {
            "market": "US",
            "stock_code": code,
            "report_period": period,
            "published_at": pick["published_at"],
            "source_url": pick["source_url"],
            "source": "sec_edgar",
            "document_id": pick["document_id"],
            "title": pick["title"],
            "form_type": pick["form_type"],
            "parser_version": US_PARSER_VERSION,
        }
        if pick.get("source_report_period"):
            row["source_report_period"] = pick["source_report_period"]
        key = ("US", code, period, pick["source_url"])
        if key not in key_existing:
            additions.append(row)
            key_existing.add(key)

    for code, event_date in sorted(us_b_targets):
        disclosure = sec_provider.find_event_disclosure(code, "US", event_date, max_days=14)
        if disclosure is None:
            target = date.fromisoformat(event_date)
            filings = sec_filing_rows(
                sec_provider,
                code,
                start_date=target - timedelta(days=20),
                end_date=target + timedelta(days=20),
                forms={"8-K", "10-Q", "10-K"},
            )
            if not filings:
                misses.append(f"B US miss {code} {event_date}")
                continue
            best = sorted(
                filings,
                key=lambda item: (
                    abs((date.fromisoformat(item["filed"]) - target).days),
                    0 if item["form"] == "8-K" else 1,
                    item["filed"],
                ),
            )[0]
            compact = best["accessionNumber"].replace("-", "")
            source_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(best['cik'])}/"
                f"{compact}/{best['primaryDocument']}"
            )
            row = {
                "market": "US",
                "stock_code": code,
                "report_period": event_date,
                "source_report_period": best["reportDate"],
                "published_at": best["filed"][:10],
                "source_url": source_url,
                "source": "sec_edgar",
                "document_id": best["accessionNumber"],
                "title": f"{best['form']} near earnings event {event_date}",
                "form_type": best["form"],
                "parser_version": US_PARSER_VERSION,
            }
            key = ("US", code, event_date, source_url)
            if key not in key_existing:
                additions.append(row)
                key_existing.add(key)
            continue
        row = {
            "market": "US",
            "stock_code": code,
            "report_period": event_date,
            "source_report_period": disclosure.report_period,
            "published_at": disclosure.published_at[:10],
            "source_url": disclosure.source_url,
            "source": "sec_edgar",
            "document_id": disclosure.document_id,
            "title": disclosure.title,
            "form_type": "8-K",
            "parser_version": US_PARSER_VERSION,
        }
        key = ("US", code, event_date, disclosure.source_url)
        if key not in key_existing:
            additions.append(row)
            key_existing.add(key)

    summary = {
        "additions": len(additions),
        "hk_c_targets": len(hk_c_targets),
        "hk_b_targets": len(hk_b_targets),
        "us_c_targets": len(us_c_targets),
        "us_b_targets": len(us_b_targets),
        "misses": misses,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    if additions:
        with registry_path.open("a", encoding="utf-8") as handle:
            for row in additions:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
