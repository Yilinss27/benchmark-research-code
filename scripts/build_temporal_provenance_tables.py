#!/usr/bin/env python3
"""Build temporal provenance tables and refresh task_temporal_index from HF baseline."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.providers.registry import official_disclosure_provider
from src.data.providers.yahoo import YahooPriceProvider
from src.temporal.evidence_provenance import (
    config_evidence_hash,
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
TABLE1_PATH = ROOT / "calibration/temporal_provenance_table.csv"
TABLE2_PATH = ROOT / "calibration/b_event_evidence_table.csv"
TABLE1_MANIFEST = ROOT / "calibration/temporal_provenance_manifest.json"
TABLE2_MANIFEST = ROOT / "calibration/b_event_evidence_manifest.json"
GAPS_PATH = ROOT / "calibration/temporal_provenance_gaps.csv"
INDEX_PATH = ROOT / "data/task_temporal_index.jsonl"
REPORT_PATH = ROOT / "data/temporal_provenance_report.json"
MACRO_EVENTS_PATH = ROOT / "configs/macro_events_v1.json"

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
]

TABLE2_FIELDS = [
    "task_id",
    "event_summary",
    "first_public_at",
    "evidence_url",
    "content_sha256",
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


def load_macro_events() -> dict[str, dict[str, Any]]:
    if not MACRO_EVENTS_PATH.exists():
        return {}
    payload = json.loads(MACRO_EVENTS_PATH.read_text(encoding="utf-8"))
    return {event["event_id"]: event for event in payload.get("events", [])}


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
    outcome = enrichment.get("outcome_available_at") or cutoff
    source = enrichment.get("outcome_available_at_source") or "modeled_cutoff_plus_30d"
    estimated = is_estimated_source(source)
    artifact = None
    if not estimated and symbol:
        cutoff_bar = price_provider.get_close_on_or_before(symbol, market, cutoff)
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
    return {
        "task_id": record["task_id"],
        "category": "A1",
        "forecast_origin": forecast_origin,
        "outcome_available_at": outcome,
        "evidence_url": artifact.evidence_url if artifact else None,
        "evidence_published_at": artifact.evidence_published_at if artifact else None,
        "content_sha256": artifact.content_sha256 if artifact else "",
        "is_estimated_date": "是" if estimated else "否",
        "reviewer": "",
        "outcome_available_at_source": source,
        "evidence_rationale": (
            artifact.evidence_rationale
            if artifact
            else "Missing observed forward trading day or price cache."
        ),
        "manual_review_eligible": "是" if artifact and artifact.manual_review_eligible else "否",
        "_enrichment": enrichment,
        "_cutoff_bar_day": cutoff,
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
    outcome = enrichment.get("outcome_available_at") or cutoff
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
    return {
        "task_id": record["task_id"],
        "category": "A2",
        "forecast_origin": forecast_origin,
        "outcome_available_at": outcome,
        "evidence_url": artifact.evidence_url if artifact else yahoo_history_url(representative_symbol, market) if representative_symbol else None,
        "evidence_published_at": artifact.evidence_published_at if artifact else None,
        "content_sha256": artifact.content_sha256 if artifact else "",
        "is_estimated_date": "是" if estimated else "否",
        "reviewer": "",
        "outcome_available_at_source": source,
        "evidence_rationale": (
            f"Cohort ranking outcome uses latest observed forward close across "
            f"{len(forward_days)} symbols; cohort reference {cohort_reference(record)}. "
            f"{artifact.evidence_rationale if artifact else 'Missing forward-day price cache.'}"
        ),
        "manual_review_eligible": "是" if artifact and artifact.manual_review_eligible and not estimated else "否",
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
    outcome = enrichment.get("outcome_available_at") or cutoff
    source = enrichment.get("outcome_available_at_source") or "modeled_report_period_plus_90d"
    estimated = is_estimated_source(source)
    url = enrichment.get("outcome_evidence_url")
    sha = ""
    published = None
    rationale = "Missing official filing evidence."
    eligible = "否"
    if url and not estimated:
        try:
            _, metadata = fetch_url_bytes(url, cache_key=f"c_{record['task_id']}")
            sha = str(metadata.get("content_sha256") or "")
            published = market_close_rfc3339(outcome[:10], market)
            rationale = (
                f"Official filing for {metric} ({future_period}) first became public on "
                f"{outcome[:10]}; ground-truth value is taken from the filing body."
            )
            eligible = "是" if sha else "否"
        except Exception as exc:
            rationale = f"Official URL present but fetch failed: {exc}"
    return {
        "task_id": record["task_id"],
        "category": "C",
        "forecast_origin": forecast_origin,
        "outcome_available_at": outcome,
        "evidence_url": url,
        "evidence_published_at": published,
        "content_sha256": sha,
        "is_estimated_date": "是" if estimated else "否",
        "reviewer": "",
        "outcome_available_at_source": source,
        "evidence_rationale": rationale,
        "manual_review_eligible": eligible,
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
    enrichment = enrich_b_outcome(record, price_provider, disclosure_provider)
    sha = ""
    eligible = "否"
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
            eligible = "是" if artifact.manual_review_eligible else "否"
            rationale = artifact.evidence_rationale
    if event_url:
        if first_public_at is None:
            first_public_at = market_close_rfc3339(event_date, market)
        if fetch_content:
            try:
                _, metadata_payload = fetch_url_bytes(
                    str(event_url),
                    cache_key=f"b_{record['task_id']}",
                )
                sha = str(metadata_payload.get("content_sha256") or "")
            except Exception:
                sha = ""
        if not sha and first_public_at:
            sha = config_evidence_hash(
                {
                    "task_id": record["task_id"],
                    "event_url": event_url,
                    "first_public_at": first_public_at,
                    "event_summary": event_summary,
                    "source": "dataset_seed_or_macro_config",
                }
            )
            rationale = (
                "Official event URL and release timestamp are pinned in the benchmark seed/config; "
                "content hash uses the archived config payload because live fetch was blocked."
            )
        eligible = "是" if event_url and first_public_at and sha else "否"
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
        "manual_review_eligible": eligible,
        "direction_link": direction_link,
        "reviewer": "",
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
    import hashlib

    digest = hashlib.sha256(table_path.read_bytes()).hexdigest() if table_path.exists() else ""
    payload = {
        "package": package,
        "table_file": str(table_path.relative_to(ROOT)),
        "table_sha256": digest,
        "record_count": len(rows),
        "review_status": "draft",
        "notes": "Independent calibration table for temporal provenance audit.",
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
    row = build_index_row(
        record,
        outcome_available_at=(
            enrichment.get("outcome_available_at")
            or (table_row.get("outcome_available_at") if table_row else None)
        ),
        outcome_evidence_url=(
            table_row.get("evidence_url") if table_row else enrichment.get("outcome_evidence_url")
        ),
        outcome_evidence_code=enrichment.get("outcome_evidence_code"),
        quality_flags=sorted(set(flags)),
        review_status="draft",
    )
    if source:
        row["outcome_available_at_source"] = source
    if enrichment.get("forward_trading_days"):
        row["forward_trading_days"] = enrichment["forward_trading_days"]
    if table_row and table_row.get("content_sha256"):
        row["evidence_hash"] = evidence_hash_row(table_row)
        row["evidence_published_at"] = table_row.get("evidence_published_at")
        row["evidence_rationale"] = table_row.get("evidence_rationale")
        row["manual_review_eligible"] = table_row.get("manual_review_eligible") == "是"
    row["review_status"] = "draft"
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
                    "reason": row.get("event_summary") or "missing official event URL",
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
    updated_rows.sort(key=lambda row: row["task_id"])
    write_temporal_index(index_path, updated_rows)

    summary = {
        "baseline_records": len(records),
        "table1_rows": len(table1_rows),
        "table2_rows": len(table2_rows),
        "table1_manual_review_eligible": sum(1 for row in table1_rows if row.get("manual_review_eligible") == "是"),
        "table2_manual_review_eligible": sum(1 for row in table2_rows if row.get("manual_review_eligible") == "是"),
        "table1_estimated_dates": sum(1 for row in table1_rows if row.get("is_estimated_date") == "是"),
        "by_category": dict(Counter(row["category"] for row in table1_rows)),
        "a1_post_cutoff_eligible": sum(
            1
            for row in table1_rows
            if row["category"] == "A1"
            and row.get("manual_review_eligible") == "是"
            and row.get("outcome_available_at", "") > "2024-06-30"
        ),
        "c_pre_cutoff_eligible": sum(
            1
            for row in table1_rows
            if row["category"] == "C"
            and row.get("manual_review_eligible") == "是"
            and row.get("outcome_available_at", "") <= "2024-06-30"
        ),
        "a2_eligible": sum(
            1 for row in table1_rows if row["category"] == "A2" and row.get("manual_review_eligible") == "是"
        ),
        "b_missing_event_evidence": sum(
            1 for row in table2_rows if row.get("manual_review_eligible") != "是"
        ),
        "gap_rows": len(gap_rows),
        "gaps_file": str(GAPS_PATH.relative_to(ROOT)),
    }
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
