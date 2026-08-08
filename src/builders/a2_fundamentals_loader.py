"""Shared fundamentals snapshot loading and cutoff matching for A2 builders."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FUNDAMENTAL_FIELD_MAP = {
    "PRICE": "price",
    "PE": "pe",
    "PB": "pb",
    "PEG": "peg",
    "PS": "ps",
    "DIVIDENDRATIO": "dividend_ratio",
    "EV_EXCLUDING_CASH": "ev_excluding_cash",
    "DEBT_TO_MARKET_CAP": "debt_to_market_cap",
    "PCF_OPERATING": "pcf_operating",
    "TRADINGDAY": "trading_day",
}

FUNDAMENTAL_OUTPUT_KEYS = (
    "price",
    "pe",
    "pb",
    "peg",
    "ps",
    "dividend_ratio",
    "ev_excluding_cash",
    "debt_to_market_cap",
    "pcf_operating",
    "trading_day",
)

MATCH_MODE_ON_OR_BEFORE = "on_or_before_cutoff"
MATCH_MODE_FALLBACK = "prototype_fallback_nearest"


@dataclass(frozen=True)
class FundamentalMatch:
    """Result of matching a fundamentals snapshot row to a cohort cutoff."""

    row: dict[str, Any]
    match_mode: str
    snapshot_date: str


def normalize_stock_code(value: str) -> str:
    """Normalize stock codes to 6-digit strings."""
    stripped = value.strip()
    if stripped.isdigit():
        return stripped.zfill(6)
    return stripped


def resolve_fundamentals_path(path_str: str) -> tuple[Path, list[str]]:
    """Resolve the fundamentals CSV path, with legacy-name fallback."""
    warnings: list[str] = []
    path = Path(path_str)
    if path.exists():
        return path, warnings

    legacy = Path("data/DZ_DIndicesForValuation_with_company_name.csv")
    if legacy.exists():
        warnings.append(
            f"Using legacy fundamentals file {legacy}; "
            "please rename/copy to data/a2_fundamentals_snapshot.csv"
        )
        return legacy, warnings

    raise FileNotFoundError(
        "Fundamentals CSV not found. 请先复制并重命名为 data/a2_fundamentals_snapshot.csv"
    )


def _to_float(value: str | None) -> float | None:
    """Convert a CSV value to float when present."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    return float(stripped)


def load_fundamentals_history(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load normalized fundamentals snapshot rows grouped by stock code."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("Fundamentals CSV header is missing")
        rows = list(reader)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        code = normalize_stock_code(row.get("STOCKCODE", ""))
        if not code:
            continue
        normalized: dict[str, Any] = {}
        for raw_key, new_key in FUNDAMENTAL_FIELD_MAP.items():
            value = row.get(raw_key)
            if raw_key == "TRADINGDAY":
                normalized[new_key] = value.strip() if value else None
            else:
                normalized[new_key] = _to_float(value)
        normalized["stock_name"] = (row.get("公司名称") or row.get("COMPANY_NAME") or "").strip() or None
        grouped.setdefault(code, []).append(normalized)
    return grouped


def select_fundamental_match(
    rows: list[dict[str, Any]],
    cutoff_date: str,
) -> FundamentalMatch | None:
    """Match fundamentals: on/before cutoff first, else nearest available snapshot."""
    dated_rows = [row for row in rows if row.get("trading_day")]
    if not dated_rows:
        return None

    on_or_before = [row for row in dated_rows if row["trading_day"] <= cutoff_date]
    if on_or_before:
        chosen = max(on_or_before, key=lambda row: row["trading_day"])
        return FundamentalMatch(
            row=chosen,
            match_mode=MATCH_MODE_ON_OR_BEFORE,
            snapshot_date=str(chosen["trading_day"]),
        )

    # Prototype fallback: use the nearest (latest) snapshot available in the table.
    chosen = max(dated_rows, key=lambda row: row["trading_day"])
    return FundamentalMatch(
        row=chosen,
        match_mode=MATCH_MODE_FALLBACK,
        snapshot_date=str(chosen["trading_day"]),
    )


def fundamentals_dict_from_match(match: FundamentalMatch) -> dict[str, Any]:
    """Extract the public fundamentals fields from a matched row."""
    return {key: match.row.get(key) for key in FUNDAMENTAL_OUTPUT_KEYS}
