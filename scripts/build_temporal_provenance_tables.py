#!/usr/bin/env python3
"""Build temporal provenance tables and refresh task_temporal_index from HF baseline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.providers.registry import official_disclosure_provider
from src.data.providers.yahoo import YahooPriceProvider
from src.temporal.evidence_provenance import (
    disclosure_artifact,
    evidence_hash_row,
    fetch_url_bytes,
    hash_price_bar,
    is_estimated_source,
    market_close_rfc3339,
    sec_user_agent,
    yahoo_history_url,
)
from src.temporal.outcome_enrichment import enrich_b_outcome, enrich_c_outcome, enrich_price_outcome
from src.temporal.paper_bands import DEFAULT_EXPERIMENT_CONFIG, build_index_row, write_temporal_index

HF_BASELINE = ROOT / "artifacts/hf_941370f/data"
SEED_OVERLAY_FILES = {
    "seeds/c_financial_metric.jsonl",
}
READY_SEED_FILES = (
    "seeds/a1_valuation.jsonl",
    "seeds/a2_fundamentals.jsonl",
    "seeds/a2_technical.jsonl",
    "seeds/a2_hybrid.jsonl",
    "seeds/b_event.jsonl",
    "seeds/c_financial_metric.jsonl",
    "seeds/d_counterfactual.jsonl",
    "seeds/e_formula.jsonl",
)
TABLE1_PATH = ROOT / "calibration/temporal_provenance_table.csv"
TABLE2_PATH = ROOT / "calibration/b_event_evidence_table.csv"
TABLE1_MANIFEST = ROOT / "calibration/temporal_provenance_manifest.json"
TABLE2_MANIFEST = ROOT / "calibration/b_event_evidence_manifest.json"
GAPS_PATH = ROOT / "calibration/temporal_provenance_gaps.csv"
INDEX_PATH = ROOT / "data/task_temporal_index.jsonl"
REPORT_PATH = ROOT / "data/temporal_provenance_report.json"
MACRO_EVENTS_PATH = ROOT / "configs/macro_events_v1.json"
REVIEWER = "DeepFinEval audit"
B_EVENT_OVERRIDES = {
    "B-MACRO-CN_A-20250109-CPI-600519": {
        "event_url": "https://www.stats.gov.cn/xxgk/sjfb/zxfb2020/202501/t20250109_1958170.html",
        "first_public_at": "2025-01-09T01:30:00Z",
        "timeout_seconds": 45,
        "rationale": "国家统计局 2025-01-09 09:30（Asia/Shanghai）发布 2024 年 12 月 CPI 数据。",
    },
    "B-MACRO-CN_A-20250127-PMI-601318": {
        "event_url": "https://www.stats.gov.cn/xxgk/sjfb/zxfb2020/202501/t20250127_1958493.html",
        "first_public_at": "2025-01-27T01:30:00Z",
        "timeout_seconds": 45,
        "rationale": "国家统计局 2025-01-27 09:30（Asia/Shanghai）发布 2025 年 1 月 PMI 数据。",
    },
    "B-MACRO-HK-20250123-CPI-1299": {
        "event_url": "https://www.info.gov.hk/gia/general/202501/21/P2025012100279.htm",
        "first_public_at": "2025-01-21T08:30:00Z",
        "rationale": "香港政府新闻公报 2025-01-21 16:30（Asia/Hong_Kong）发布 2024 年 12 月消费物价指数。",
    },
    "B-MACRO-HK-20250131-GDP-0700": {
        "event_url": "https://www.info.gov.hk/gia/general/202502/03/P2025020300248.htm",
        "first_public_at": "2025-02-03T08:30:00Z",
        "rationale": "香港政府新闻公报 2025-02-03 16:30（Asia/Hong_Kong）发布 2024 年第四季及全年 GDP 预先估计。",
    },
}

TABLE1_FIELDS = [
    "task_id",
    "category",
    "forecast_origin",
    "outcome_available_at",
    "evidence_url",
    "evidence_published_at",
    "content_sha256",
    "is_estimated_date",
    "reviewer",
    "outcome_available_at_source",
    "evidence_rationale",
    "manual_review_eligible",
    "predicted_metric",
    "unit",
    "final_value",
]

TABLE2_FIELDS = [
    "task_id",
    "event_summary",
    "first_public_at",
    "evidence_url",
    "content_sha256",
    "evidence_rationale",
    "price_evidence_url",
    "price_evidence_published_at",
    "price_content_sha256",
    "manual_review_eligible",
    "direction_link",
    "reviewer",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=str(HF_BASELINE))
    parser.add_argument("--index", default=str(INDEX_PATH))
    parser.add_argument(
        "--overlay-seeds",
        action="store_true",
        help="Replace HF baseline rows with matching local seed JSONL records (e.g. aligned C).",
    )
    parser.add_argument("--fetch-content", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_hf_records(baseline: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(baseline.glob("*/train.jsonl")):
        records.extend(load_jsonl(path))
    records.sort(key=lambda row: row["task_id"])
    return records


def load_records(baseline: Path, *, overlay_seeds: bool) -> list[dict[str, Any]]:
    """Load HF pin records, optionally overlaying local seed files by task_id."""
    by_id = {row["task_id"]: row for row in load_hf_records(baseline)}
    if overlay_seeds:
        for rel in SEED_OVERLAY_FILES:
            for row in load_jsonl(ROOT / rel):
                by_id[row["task_id"]] = row
    return sorted(by_id.values(), key=lambda row: row["task_id"])


def load_ready_seed_records() -> dict[str, dict[str, Any]]:
    """Load current ready seed rows keyed by task_id."""
    by_id: dict[str, dict[str, Any]] = {}
    for rel in READY_SEED_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        for row in load_jsonl(path):
            if row.get("status") == "ready" and row.get("task_id"):
                by_id[str(row["task_id"])] = row
    return by_id


def load_macro_events() -> dict[str, dict[str, Any]]:
    if not MACRO_EVENTS_PATH.exists():
        return {}
    payload = json.loads(MACRO_EVENTS_PATH.read_text(encoding="utf-8"))
    return {event["event_id"]: event for event in payload.get("events", [])}


def _is_rfc3339(value: str | None) -> bool:
    raw = str(value or "")
    if not raw or "T" not in raw:
        return False
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _normalize_market_timestamp(value: str | None, market: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if _is_rfc3339(raw):
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return market_close_rfc3339(raw[:10], market)


def _normalize_release_timestamp(value: str | None, release_timezone: str | None, market: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if _is_rfc3339(raw):
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if " " in raw and release_timezone:
        try:
            local = datetime.fromisoformat(raw)
            localized = local.replace(tzinfo=ZoneInfo(str(release_timezone)))
            return localized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            pass
    return market_close_rfc3339(raw[:10], market)


def _strict_eligible(
    *,
    evidence_url: str | None,
    evidence_published_at: str | None,
    content_sha256: str | None,
    estimated: bool,
) -> bool:
    sha = str(content_sha256 or "")
    return (
        not estimated
        and str(evidence_url or "").startswith("http")
        and _is_rfc3339(evidence_published_at)
        and len(sha) == 64
        and all(ch in "0123456789abcdef" for ch in sha.lower())
    )


def _url_embedded_date(url: str | None) -> str:
    raw = str(url or "")
    patterns = [
        r"/(\d{4})-(\d{2})-(\d{2})/",
        r"/(\d{4})/(\d{2})/(\d{2})/",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            return "-".join(match.groups())
    return ""


def cohort_reference(record: dict[str, Any]) -> str:
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}
    cohort_id = metadata.get("cohort_id")
    if cohort_id:
        return f"configs/universes_v1.json#{cohort_id}"
    codes = [item.get("code") for item in seed.get("stock_list", []) if item.get("code")]
    if codes:
        return f"seed.stock_list={','.join(codes)}"
    return "seed.stock_list"


def build_a1_row(
    record: dict[str, Any],
    *,
    price_provider: YahooPriceProvider,
    fetch_content: bool,
) -> dict[str, Any]:
    seed = record.get("seed") or {}
    market = str(seed.get("market") or (record.get("metadata") or {}).get("market") or "CN_A")
    symbol = str(seed.get("stock_code") or "")
    cutoff = str(seed.get("cutoff_date") or record.get("cutoff_date"))
    enrichment = enrich_price_outcome(record, price_provider)
    forecast_origin = cutoff
    outcome = str(enrichment.get("outcome_available_at") or cutoff)
    source = enrichment.get("outcome_available_at_source") or "modeled_cutoff_plus_30d"
    estimated = is_estimated_source(source)
    artifact = None
    if not estimated and symbol:
        forward_days = enrichment.get("forward_trading_days") or {}
        primary_day = forward_days.get(symbol) or outcome
        forward_bar = price_provider.get_close_on_or_before(symbol, market, primary_day)
        if forward_bar is not None:
            artifact = hash_price_bar(
                symbol=symbol,
                market=market,
                bar=forward_bar,
                role="primary_forward_close",
            )
    outcome_ts = _normalize_market_timestamp(outcome, market)
    evidence_url = artifact.evidence_url if artifact else (yahoo_history_url(symbol, market) if symbol else None)
    evidence_published_at = artifact.evidence_published_at if artifact else outcome_ts
    content_sha256 = artifact.content_sha256 if artifact else ""
    eligible = _strict_eligible(
        evidence_url=evidence_url,
        evidence_published_at=evidence_published_at,
        content_sha256=content_sha256,
        estimated=estimated,
    )
    forward_days = enrichment.get("forward_trading_days") or {}
    return {
        "task_id": record["task_id"],
        "category": "A1",
        "forecast_origin": forecast_origin,
        "outcome_available_at": outcome_ts,
        "evidence_url": evidence_url,
        "evidence_published_at": evidence_published_at,
        "content_sha256": content_sha256,
        "is_estimated_date": "是" if estimated else "否",
        "reviewer": REVIEWER,
        "outcome_available_at_source": source,
        "evidence_rationale": (
            (
                f"{artifact.evidence_rationale} Cutoff date {cutoff}; forward trading day "
                f"resolved as {','.join(f'{k}={v}' for k, v in sorted(forward_days.items())) or 'missing'}."
            )
            if artifact
            else "Missing observed forward trading day or price cache from Yahoo local history."
        ),
        "manual_review_eligible": "是" if eligible else "否",
        "_enrichment": enrichment,
    }


def build_a2_row(
    record: dict[str, Any],
    *,
    price_provider: YahooPriceProvider,
) -> dict[str, Any]:
    seed = record.get("seed") or {}
    market = str(seed.get("market") or (record.get("metadata") or {}).get("market") or "CN_A")
    cutoff = str(seed.get("cutoff_date") or record.get("cutoff_date"))
    enrichment = enrich_price_outcome(record, price_provider)
    forecast_origin = cutoff
    outcome = str(enrichment.get("outcome_available_at") or cutoff)
    source = enrichment.get("outcome_available_at_source") or "modeled_cutoff_plus_30d"
    estimated = is_estimated_source(source)
    forward_days = enrichment.get("forward_trading_days") or {}
    representative_symbol = sorted(forward_days.keys())[0] if forward_days else ""
    artifact = None
    if representative_symbol and representative_symbol in forward_days:
        trading_day = forward_days[representative_symbol]
        bar = price_provider.get_close_on_or_before(
            representative_symbol, market, trading_day
        )
        if bar is not None:
            artifact = hash_price_bar(
                symbol=representative_symbol,
                market=market,
                bar=bar,
                role="cohort_forward_close",
            )
    outcome_ts = _normalize_market_timestamp(outcome, market)
    evidence_url = (
        artifact.evidence_url
        if artifact
        else yahoo_history_url(representative_symbol, market) if representative_symbol else None
    )
    evidence_published_at = artifact.evidence_published_at if artifact else outcome_ts
    content_sha256 = artifact.content_sha256 if artifact else ""
    eligible = _strict_eligible(
        evidence_url=evidence_url,
        evidence_published_at=evidence_published_at,
        content_sha256=content_sha256,
        estimated=estimated,
    )
    symbols = [str(item.get("code")) for item in seed.get("stock_list", []) if item.get("code")]
    return {
        "task_id": record["task_id"],
        "category": "A2",
        "forecast_origin": forecast_origin,
        "outcome_available_at": outcome_ts,
        "evidence_url": evidence_url,
        "evidence_published_at": evidence_published_at,
        "content_sha256": content_sha256,
        "is_estimated_date": "是" if estimated else "否",
        "reviewer": REVIEWER,
        "outcome_available_at_source": source,
        "evidence_rationale": (
            f"Cohort ranking outcome uses latest observed forward close across "
            f"{len(forward_days)} symbols; cohort reference {cohort_reference(record)}. "
            f"Symbols={','.join(symbols)}. "
            f"{artifact.evidence_rationale if artifact else 'Missing forward-day price cache.'}"
        ),
        "manual_review_eligible": "是" if eligible else "否",
        "_enrichment": enrichment,
    }


def build_c_row(
    record: dict[str, Any],
    *,
    disclosure_provider: Any,
    fetch_content: bool,
) -> dict[str, Any]:
    seed = record.get("seed") or {}
    market = str(seed.get("market") or (record.get("metadata") or {}).get("market") or "CN_A")
    cutoff = str(seed.get("cutoff_date") or record.get("cutoff_date"))
    future_period = str(seed.get("report_period_future") or "")
    metric = str(seed.get("metric_name") or (record.get("ground_truth") or {}).get("metric_name") or "")
    enrichment = enrich_c_outcome(record, disclosure_provider)
    forecast_origin = cutoff
    outcome = str(enrichment.get("outcome_available_at") or cutoff)
    source = enrichment.get("outcome_available_at_source") or "modeled_report_period_plus_90d"
    estimated = is_estimated_source(source)
    url = str(enrichment.get("outcome_evidence_url") or "")
    sha = ""
    published = _normalize_market_timestamp(outcome, market)
    rationale = "Missing official filing evidence."
    eligible = False
    if url and not estimated:
        try:
            _, metadata = fetch_url_bytes(
                url,
                cache_key=f"c_{record['task_id']}",
                published_at=published,
                parser_version="c_official_disclosure_v2",
            )
            sha = str(metadata.get("content_sha256") or "")
            rationale = (
                f"Official filing for {metric} ({future_period}) first became public on "
                f"{published}; ground-truth value is taken from the filing body."
            )
            eligible = _strict_eligible(
                evidence_url=url,
                evidence_published_at=published,
                content_sha256=sha,
                estimated=estimated,
            )
        except Exception as exc:
            rationale = f"Official URL present but fetch failed: {exc}"
            eligible = False
    return {
        "task_id": record["task_id"],
        "category": "C",
        "forecast_origin": forecast_origin,
        "outcome_available_at": published,
        "evidence_url": url or None,
        "evidence_published_at": published,
        "content_sha256": sha,
        "is_estimated_date": "是" if estimated else "否",
        "reviewer": REVIEWER,
        "outcome_available_at_source": source,
        "evidence_rationale": rationale,
        "manual_review_eligible": "是" if eligible else "否",
        "predicted_metric": metric,
        "unit": (
            "%"
            if metric in {"gross_margin", "net_margin", "operating_margin"}
            else str(seed.get("currency") or "")
        ),
        "final_value": (record.get("ground_truth") or {}).get("future_value", ""),
        "_enrichment": enrichment,
    }


def build_b_row(
    record: dict[str, Any],
    *,
    price_provider: YahooPriceProvider,
    disclosure_provider: Any,
    macro_events: dict[str, dict[str, Any]],
    fetch_content: bool,
) -> dict[str, Any]:
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}
    market = str(seed.get("market") or metadata.get("market") or "CN_A")
    event_id = str(seed.get("event_id") or record["task_id"])
    event_date = str(seed.get("event_date") or seed.get("cutoff_date") or record.get("cutoff_date"))
    event_summary = str(seed.get("event_description") or metadata.get("event_description") or "")
    macro = macro_events.get(event_id) or {}
    event_url = (
        seed.get("event_url")
        or metadata.get("event_evidence_url")
        or macro.get("event_url")
        or record.get("outcome_evidence_url")
    )
    first_public_at = macro.get("release_timestamp") or seed.get("release_timestamp")
    release_timezone = seed.get("release_timezone") or macro.get("release_timezone")
    override = B_EVENT_OVERRIDES.get(record["task_id"], {})
    if override:
        event_url = override["event_url"]
        first_public_at = override["first_public_at"]
    enrichment = enrich_b_outcome(record, price_provider, disclosure_provider)
    sha = ""
    eligible = False
    rationale = "Missing official event evidence."
    if not event_url:
        disclosure = disclosure_provider.find_event_disclosure(
            str(seed.get("stock_code") or ""),
            market,
            event_date,
            max_days=14,
        )
        if disclosure is not None:
            artifact = disclosure_artifact(
                disclosure,
                rationale="Official event disclosure matched to the earnings announcement date.",
                fetch_content=fetch_content,
            )
            event_url = artifact.evidence_url
            first_public_at = artifact.evidence_published_at
            sha = artifact.content_sha256
            eligible = bool(artifact.manual_review_eligible)
            rationale = artifact.evidence_rationale
    if event_url:
        first_public_at = _normalize_release_timestamp(first_public_at or event_date, release_timezone, market)
        url_date = _url_embedded_date(str(event_url))
        if url_date and first_public_at[:10] < url_date:
            first_public_at = _normalize_market_timestamp(url_date, market)
            rationale = (
                "Evidence URL contains a later publication date than seed release timestamp; "
                "first_public_at is pinned to the earliest date visible in the first-party URL path."
            )
        if fetch_content:
            try:
                _, metadata_payload = fetch_url_bytes(
                    str(event_url),
                    user_agent="Mozilla/5.0 (compatible; DeepFinEval benchmark evidence audit)",
                    cache_key=f"b_{record['task_id']}",
                    published_at=first_public_at,
                    parser_version="b_event_evidence_v2",
                    timeout_seconds=int(override.get("timeout_seconds", 15)) if override else 15,
                )
                sha = str(metadata_payload.get("content_sha256") or "")
            except Exception as exc:
                sha = ""
                rationale = f"Official event URL present but fetch failed: {exc}"
        if override and sha:
            rationale = str(override["rationale"])
        eligible = _strict_eligible(
            evidence_url=str(event_url),
            evidence_published_at=first_public_at,
            content_sha256=sha,
            estimated=False,
        )
    price_evidence_url = ""
    price_evidence_published_at = ""
    price_content_sha256 = ""
    price_eligible = record.get("variant") != "earnings"
    if record.get("variant") == "earnings":
        outcome_day = str(enrichment.get("outcome_available_at") or "")[:10]
        symbol = str(seed.get("stock_code") or "")
        try:
            reaction_bar = price_provider.get_close_on_or_before(
                symbol, market, outcome_day
            )
        except Exception:
            reaction_bar = None
        if reaction_bar is not None and reaction_bar.trading_day == outcome_day:
            price_artifact = hash_price_bar(
                symbol=symbol,
                market=market,
                bar=reaction_bar,
                role="event_reaction_close",
            )
            price_evidence_url = price_artifact.evidence_url
            price_evidence_published_at = price_artifact.evidence_published_at
            price_content_sha256 = price_artifact.content_sha256
            price_eligible = price_artifact.manual_review_eligible
    eligible = eligible and price_eligible
    ground_truth = record.get("ground_truth") or {}
    direction = ground_truth.get("actual_direction")
    outcome_day = enrichment.get("outcome_available_at")
    direction_link = (
        f"observed {direction} excess return available from {outcome_day} close"
        if direction and outcome_day
        else "missing outcome linkage"
    )
    return {
        "task_id": record["task_id"],
        "event_summary": event_summary,
        "first_public_at": first_public_at,
        "evidence_url": event_url,
        "content_sha256": sha,
        "evidence_rationale": rationale,
        "price_evidence_url": price_evidence_url,
        "price_evidence_published_at": price_evidence_published_at,
        "price_content_sha256": price_content_sha256,
        "manual_review_eligible": "是" if eligible else "否",
        "direction_link": direction_link,
        "reviewer": REVIEWER,
        "_enrichment": enrichment,
        "_event_rationale": rationale,
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_manifest(manifest_path: Path, table_path: Path, rows: list[dict[str, Any]], package: str) -> None:
    digest = hashlib.sha256(table_path.read_bytes()).hexdigest() if table_path.exists() else ""
    eligible_rows = sum(1 for row in rows if row.get("manual_review_eligible") == "是")
    review_status = "reviewed" if eligible_rows == len(rows) and len(rows) > 0 else "draft"
    payload = {
        "package": package,
        "table_file": str(table_path.relative_to(ROOT)),
        "table_sha256": digest,
        "record_count": len(rows),
        "eligible_count": eligible_rows,
        "ineligible_count": len(rows) - eligible_rows,
        "review_status": review_status,
        "notes": "Temporal provenance calibration generated under strict evidence requirements.",
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def index_row_from_table(
    record: dict[str, Any],
    table_row: dict[str, Any] | None,
    *,
    enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enrichment = enrichment or ((table_row or {}).get("_enrichment") if table_row else None) or {}
    flags: list[str] = list(enrichment.get("quality_flags") or [])
    source = enrichment.get("outcome_available_at_source") or (
        table_row.get("outcome_available_at_source") if table_row else None
    )
    if is_estimated_source(str(source or "")):
        flags.append("modeled_outcome_availability")
    if record.get("category") == "B" and (not table_row or not table_row.get("evidence_url")):
        flags.append("missing_event_evidence")
    if (
        record.get("category") in {"A1", "A2", "C"}
        and table_row
        and table_row.get("manual_review_eligible") != "是"
    ):
        if record.get("category") in {"A1", "A2"} and is_estimated_source(str(source or "")):
            flags.append("missing_outcome_evidence")
    seed = record.get("seed") or {}
    market = str(seed.get("market") or (record.get("metadata") or {}).get("market") or "CN_A")
    outcome_at = (table_row.get("outcome_available_at") if table_row else None) or enrichment.get(
        "outcome_available_at"
    )
    if isinstance(outcome_at, str) and outcome_at and "T" not in outcome_at:
        outcome_at = _normalize_market_timestamp(outcome_at, market)
    row = build_index_row(
        record,
        outcome_available_at=outcome_at,
        outcome_evidence_url=(
            table_row.get("evidence_url") if table_row else enrichment.get("outcome_evidence_url")
        ),
        outcome_evidence_code=enrichment.get("outcome_evidence_code"),
        quality_flags=sorted(set(flags)),
        review_status="draft",
    )
    if source:
        row["outcome_available_at_source"] = source
    if isinstance(outcome_at, str) and outcome_at:
        row["outcome_available_at"] = outcome_at
    else:
        inferred_outcome = row.get("outcome_available_at")
        if isinstance(inferred_outcome, str) and inferred_outcome and "T" not in inferred_outcome:
            row["outcome_available_at"] = _normalize_market_timestamp(inferred_outcome, market)
    if enrichment.get("forward_trading_days"):
        row["forward_trading_days"] = enrichment["forward_trading_days"]
    manual_ok = False
    if table_row and table_row.get("content_sha256"):
        row["evidence_hash"] = evidence_hash_row(table_row)
        row["evidence_published_at"] = table_row.get("evidence_published_at") or table_row.get("first_public_at")
        row["evidence_rationale"] = table_row.get("evidence_rationale")
    if table_row:
        manual_ok = table_row.get("manual_review_eligible") == "是"
    row["manual_review_eligible"] = manual_ok
    category = str(record.get("category") or "")
    if category in {"D", "E"}:
        row["official_temporal_eligible"] = False
        row["review_status"] = "draft"
    else:
        row["official_temporal_eligible"] = bool(row.get("official_temporal_eligible")) and manual_ok
        row["review_status"] = "reviewed" if row["official_temporal_eligible"] else "draft"
        if not row["official_temporal_eligible"]:
            flags = set(row.get("quality_flags") or [])
            flags.add("manual_review_incomplete")
            row["quality_flags"] = sorted(flags)
    row.pop("review_method", None)
    row.pop("reviewed_at", None)
    return row


def main() -> int:
    args = parse_args()
    records = load_records(Path(args.baseline), overlay_seeds=args.overlay_seeds)
    if args.limit:
        records = records[: args.limit]

    price_provider = YahooPriceProvider()
    disclosure_providers = {
        market: official_disclosure_provider(market, sec_user_agent=sec_user_agent())
        for market in ("CN_A", "US", "HK")
    }
    macro_events = load_macro_events()

    table1_rows: list[dict[str, Any]] = []
    table2_rows: list[dict[str, Any]] = []
    table1_by_id: dict[str, dict[str, Any]] = {}
    table2_by_id: dict[str, dict[str, Any]] = {}

    for record in records:
        category = record.get("category")
        if category == "A1":
            row = build_a1_row(record, price_provider=price_provider, fetch_content=args.fetch_content)
            table1_rows.append(row)
            table1_by_id[record["task_id"]] = row
        elif category == "A2":
            row = build_a2_row(record, price_provider=price_provider)
            table1_rows.append(row)
            table1_by_id[record["task_id"]] = row
        elif category == "C":
            market = str((record.get("seed") or {}).get("market") or "CN_A")
            row = build_c_row(
                record,
                disclosure_provider=disclosure_providers[market],
                fetch_content=args.fetch_content,
            )
            table1_rows.append(row)
            table1_by_id[record["task_id"]] = row
        elif category == "B":
            market = str((record.get("seed") or {}).get("market") or "CN_A")
            row = build_b_row(
                record,
                price_provider=price_provider,
                disclosure_provider=disclosure_providers[market],
                macro_events=macro_events,
                fetch_content=args.fetch_content,
            )
            table2_rows.append(row)
            table2_by_id[record["task_id"]] = row

    write_csv(TABLE1_PATH, TABLE1_FIELDS, table1_rows)
    write_csv(TABLE2_PATH, TABLE2_FIELDS, table2_rows)
    write_manifest(TABLE1_MANIFEST, TABLE1_PATH, table1_rows, "temporal_provenance_v1")
    write_manifest(TABLE2_MANIFEST, TABLE2_PATH, table2_rows, "b_event_evidence_v1")

    gap_rows: list[dict[str, Any]] = []
    for row in table1_rows:
        if row.get("manual_review_eligible") != "是":
            gap_rows.append(
                {
                    "task_id": row["task_id"],
                    "category": row["category"],
                    "status": "missing_or_estimated",
                    "reason": row.get("evidence_rationale") or row.get("outcome_available_at_source"),
                }
            )
    for row in table2_rows:
        if row.get("manual_review_eligible") != "是":
            gap_rows.append(
                {
                    "task_id": row["task_id"],
                    "category": "B",
                    "status": "missing_event_evidence",
                    "reason": row.get("_event_rationale") or "missing official event URL",
                }
            )
    write_csv(
        GAPS_PATH,
        ["task_id", "category", "status", "reason"],
        gap_rows,
    )

    updated_rows: list[dict[str, Any]] = []
    index_path = Path(args.index)
    for record in records:
        table_row = table1_by_id.get(record["task_id"]) or table2_by_id.get(record["task_id"])
        enrichment = (table_row or {}).get("_enrichment")
        updated_rows.append(index_row_from_table(record, table_row, enrichment=enrichment))
    # Keep temporal index aligned with current ready seed library, even when
    # the pinned HF artifact has fewer rows.
    ready_seed_by_id = load_ready_seed_records()
    indexed_ids = {row["task_id"] for row in updated_rows}
    ready_missing_ids = sorted(set(ready_seed_by_id) - indexed_ids)
    for task_id in ready_missing_ids:
        record = ready_seed_by_id[task_id]
        updated_rows.append(index_row_from_table(record, None, enrichment=None))
    updated_rows.sort(key=lambda row: row["task_id"])
    write_temporal_index(index_path, updated_rows)

    a2_rows = [row for row in table1_rows if row["category"] == "A2"]
    a2_missing_ids = sorted(
        row["task_id"] for row in a2_rows if row.get("manual_review_eligible") != "是"
    )
    a1_post_cutoff_ids = sorted(
        row["task_id"]
        for row in table1_rows
        if row["category"] == "A1"
        and row.get("manual_review_eligible") == "是"
        and str(row.get("outcome_available_at", ""))[:10] > "2024-06-30"
    )
    c_pre_cutoff_ids = sorted(
        row["task_id"]
        for row in table1_rows
        if row["category"] == "C"
        and row.get("manual_review_eligible") == "是"
        and str(row.get("outcome_available_at", ""))[:10] <= "2024-06-30"
    )
    b_missing_ids = sorted(
        row["task_id"] for row in table2_rows if row.get("manual_review_eligible") != "是"
    )

    summary = {
        "baseline_records": len(records),
        "ready_seed_records": len(ready_seed_by_id),
        "index_rows": len(updated_rows),
        "ready_seed_missing_in_hf_artifact": ready_missing_ids,
        "table1_rows": len(table1_rows),
        "table2_rows": len(table2_rows),
        "table1_manual_review_eligible": sum(1 for row in table1_rows if row.get("manual_review_eligible") == "是"),
        "table2_manual_review_eligible": sum(1 for row in table2_rows if row.get("manual_review_eligible") == "是"),
        "table1_estimated_dates": sum(1 for row in table1_rows if row.get("is_estimated_date") == "是"),
        "by_category": dict(Counter(row["category"] for row in table1_rows)),
        "a1_post_cutoff_eligible": sum(
            1 for _ in a1_post_cutoff_ids
        ),
        "a1_post_cutoff_eligible_task_ids": a1_post_cutoff_ids,
        "c_pre_cutoff_eligible": sum(
            1 for _ in c_pre_cutoff_ids
        ),
        "c_pre_cutoff_eligible_task_ids": c_pre_cutoff_ids,
        "c_pre_cutoff_limitation": (
            "Pinned 941370f C records have outcome periods in 2025/2026; no pre-2024-06-30 "
            "C result can be added without changing an existing question or task_id."
        ),
        "a2_eligible": sum(
            1 for row in table1_rows if row["category"] == "A2" and row.get("manual_review_eligible") == "是"
        ),
        "a2_missing_task_ids": a2_missing_ids,
        "b_missing_event_evidence": sum(
            1 for _ in b_missing_ids
        ),
        "b_missing_event_evidence_task_ids": b_missing_ids,
        "b_table_scope": (
            "All 138 pinned B tasks are retained because the approximate 62-task missing-event "
            "cohort is not uniquely encoded in the 941370f artifact; the artifact has 125 earnings "
            "rows without embedded event URLs and 13 macro rows with embedded event URLs."
        ),
        "table1_missing_reviewer": sum(1 for row in table1_rows if not row.get("reviewer")),
        "table2_missing_reviewer": sum(1 for row in table2_rows if not row.get("reviewer")),
        "table1_bad_outcome_tz": sum(1 for row in table1_rows if not _is_rfc3339(row.get("outcome_available_at"))),
        "table1_bad_evidence_tz": sum(1 for row in table1_rows if not _is_rfc3339(row.get("evidence_published_at"))),
        "table2_bad_first_public_tz": sum(1 for row in table2_rows if not _is_rfc3339(row.get("first_public_at"))),
        "index_reviewed_rows": sum(1 for row in updated_rows if row.get("review_status") == "reviewed"),
        "index_official_temporal_eligible_true": sum(
            1 for row in updated_rows if row.get("official_temporal_eligible") is True
        ),
        "index_date_only_outcome": sum(
            1 for row in updated_rows if "T" not in str(row.get("outcome_available_at") or "")
        ),
        "gap_rows": len(gap_rows),
        "gaps_file": str(GAPS_PATH.relative_to(ROOT)),
    }
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
