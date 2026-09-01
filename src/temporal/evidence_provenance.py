"""Fetch first-party evidence, hash archived content, and build audit rows."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from src.data.providers.base import OfficialDisclosure, PriceBar
from src.data.providers.yahoo import to_yahoo_ticker
from src.data.provenance import sha256_text, write_provenance

DEFAULT_CACHE_DIR = Path("data/cache/official/evidence")
DEFAULT_SEC_USER_AGENT = "DeepFinEval-benchmark-research/0.9 (academic research; contact: sselaine27@users.noreply.huggingface.co)"


def config_evidence_hash(payload: dict[str, Any]) -> str:
    """Hash a canonical config payload when live fetch is unavailable."""
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


@dataclass(frozen=True)
class EvidenceArtifact:
    """One auditable evidence bundle."""

    evidence_url: str
    evidence_published_at: str
    content_sha256: str
    evidence_rationale: str
    is_estimated_date: bool = False
    manual_review_eligible: bool = False
    cache_key: str | None = None


def is_estimated_source(source: str | None) -> bool:
    """Return True when a temporal source is heuristic or modeled."""
    value = str(source or "")
    return value.startswith(("modeled_", "heuristic_", "report_period_future_plus_"))


def market_close_rfc3339(trading_day: str, market: str) -> str:
    """Return the regular-session close timestamp for a trading day."""
    zones = {
        "CN_A": ("Asia/Shanghai", time(15, 0)),
        "US": ("America/New_York", time(16, 0)),
        "HK": ("Asia/Hong_Kong", time(16, 0)),
        "MACRO": ("UTC", time(0, 0)),
    }
    zone_name, close_time = zones.get(market, ("UTC", time(0, 0)))
    local = datetime.combine(
        datetime.fromisoformat(trading_day).date(),
        close_time,
        tzinfo=ZoneInfo(zone_name),
    )
    return local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def yahoo_history_url(symbol: str, market: str) -> str:
    """Return a stable Yahoo Finance history page for a symbol."""
    ticker = to_yahoo_ticker(symbol, market)
    return f"https://finance.yahoo.com/quote/{ticker}/history"


def canonical_price_payload(
    *,
    symbol: str,
    market: str,
    trading_day: str,
    close: float,
    role: str,
) -> dict[str, Any]:
    """Build a canonical JSON payload for hashing one close observation."""
    return {
        "symbol": symbol,
        "market": market,
        "trading_day": trading_day,
        "close": round(float(close), 6),
        "role": role,
        "source": "yahoo_finance_adjusted_close",
    }


def hash_price_bar(
    *,
    symbol: str,
    market: str,
    bar: PriceBar,
    role: str,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> EvidenceArtifact:
    """Hash a single cached close bar and persist provenance."""
    payload = canonical_price_payload(
        symbol=symbol,
        market=market,
        trading_day=bar.trading_day,
        close=bar.close,
        role=role,
    )
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    cache_key = f"price_{market}_{symbol}_{bar.trading_day}_{role}"
    provenance = write_provenance(
        cache_key,
        source_url=yahoo_history_url(symbol, market),
        content=serialized,
        parser_version="yahoo_price_bar_v1",
        metadata=payload,
        cache_dir=cache_dir,
    )
    return EvidenceArtifact(
        evidence_url=yahoo_history_url(symbol, market),
        evidence_published_at=market_close_rfc3339(bar.trading_day, market),
        content_sha256=str(provenance["content_sha256"]),
        evidence_rationale=(
            f"Adjusted close on {bar.trading_day} is the earliest public end-of-day "
            f"price observation used for {role}."
        ),
        is_estimated_date=False,
        manual_review_eligible=True,
        cache_key=cache_key,
    )


def fetch_url_bytes(
    url: str,
    *,
    user_agent: str | None = None,
    cache_key: str | None = None,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> tuple[bytes, dict[str, Any]]:
    """Fetch URL bytes once and persist provenance sidecar."""
    root = Path(cache_dir)
    safe_key = (cache_key or hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]).replace("/", "_").replace(":", "_")
    source_path = root / f"{safe_key}.source"
    binary_path = root / f"{safe_key}.bin"
    meta_path = root / f"{safe_key}.provenance.json"
    if meta_path.exists() and (source_path.exists() or binary_path.exists()):
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        content = binary_path.read_bytes() if binary_path.exists() else source_path.read_bytes()
        return content, metadata

    request = Request(
        url,
        headers={
            "User-Agent": user_agent or DEFAULT_SEC_USER_AGENT,
            "Accept-Encoding": "identity",
        },
    )
    try:
        import certifi

        ssl_context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ssl_context = ssl.create_default_context()
    with urlopen(request, timeout=45, context=ssl_context) as response:
        content = response.read()
    content_sha256 = hashlib.sha256(content).hexdigest()
    fetched_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "cache_key": safe_key,
        "source_url": url,
        "fetched_at": fetched_at,
        "content_sha256": content_sha256,
        "parser_version": "url_fetch_v1",
    }
    root.mkdir(parents=True, exist_ok=True)
    if url.lower().endswith((".htm", ".html", ".txt")):
        source_path.write_text(content.decode("utf-8", errors="replace"), encoding="utf-8")
    else:
        binary_path.write_bytes(content)
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return content, metadata


def disclosure_artifact(
    disclosure: OfficialDisclosure,
    *,
    rationale: str,
    published_at: str | None = None,
    fetch_content: bool = True,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> EvidenceArtifact:
    """Build an evidence artifact from an official disclosure row."""
    published = published_at or disclosure.published_at
    if "T" not in published:
        market = disclosure.market if disclosure.market in {"CN_A", "US", "HK"} else "MACRO"
        published = market_close_rfc3339(published[:10], market)
    content_sha256 = disclosure.content_sha256
    cache_key = f"disclosure_{disclosure.market}_{disclosure.stock_code}_{disclosure.document_id or disclosure.source_url}"
    if fetch_content and disclosure.source_url:
        try:
            _, metadata = fetch_url_bytes(
                disclosure.source_url,
                cache_key=cache_key,
                cache_dir=cache_dir,
            )
            content_sha256 = str(metadata.get("content_sha256") or content_sha256 or "")
        except Exception:
            content_sha256 = content_sha256 or ""
    return EvidenceArtifact(
        evidence_url=disclosure.source_url,
        evidence_published_at=published,
        content_sha256=str(content_sha256 or ""),
        evidence_rationale=rationale,
        is_estimated_date=False,
        manual_review_eligible=bool(disclosure.source_url and content_sha256),
        cache_key=cache_key,
    )


def evidence_hash_row(row: dict[str, Any]) -> str:
    """Hash the auditable temporal fields for one task."""
    payload = {
        key: row.get(key)
        for key in (
            "task_id",
            "category",
            "forecast_origin",
            "outcome_available_at",
            "outcome_available_at_source",
            "evidence_url",
            "evidence_published_at",
            "content_sha256",
            "is_estimated_date",
            "manual_review_eligible",
        )
    }
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def sec_user_agent() -> str:
    """Return the configured SEC user agent."""
    return os.getenv("SEC_USER_AGENT", DEFAULT_SEC_USER_AGENT)
