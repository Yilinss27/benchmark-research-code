"""Load cross-market universes from configs/universes_v1.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict


class UniverseName(TypedDict):
    """One listed name in a market universe."""

    stock_code: str
    stock_name: str


class CohortSpec(TypedDict):
    """A2 ranking cohort definition."""

    cohort_key: str
    industry_name: str
    stocks: list[UniverseName]


def _load_payload() -> dict:
    config_path = Path(__file__).resolve().parents[2] / "configs" / "universes_v1.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("version") != "universes_v1":
        raise ValueError(f"Unexpected universes version: {payload.get('version')}")
    return payload


_PAYLOAD = _load_payload()
MARKET_CURRENCY: dict[str, str] = _PAYLOAD["market_currency"]
CURRENCY_UNIT: dict[str, str] = _PAYLOAD["currency_unit"]
A1_UNIVERSE: dict[str, list[UniverseName]] = _PAYLOAD["a1_universe"]
B_UNIVERSE: dict[str, list[UniverseName]] = _PAYLOAD["b_earnings_universe"]
C_METRICS = tuple(_PAYLOAD["c_metrics"])
B_EVENT_WINDOWS = {
    key: (value[0], value[1]) for key, value in _PAYLOAD["b_event_windows"].items()
}
A2_T_COHORTS: dict[str, list[CohortSpec]] = _PAYLOAD["a2_cohorts"]


def currency_for_market(market: str) -> str:
    """Return ISO currency code for a market."""
    if market not in MARKET_CURRENCY:
        raise ValueError(f"Unsupported market: {market}")
    return MARKET_CURRENCY[market]


def currency_unit(currency: str) -> str:
    """Return display unit used in A1 prompts."""
    return CURRENCY_UNIT.get(currency, currency)
