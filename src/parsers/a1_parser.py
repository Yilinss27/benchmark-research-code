"""Parser for task A1 valuation-range outputs."""

from __future__ import annotations

from typing import Any

from src.parsers.common import extract_json_from_response


VALID_HORIZONS = {
    "1-4周",
    "1-3个月",
    "3-6个月",
    "6-12个月",
    "超过12个月",
}


def parse_a1_response(response: str) -> dict[str, Any]:
    """Parse an A1 response into normalized fields."""
    try:
        parsed = extract_json_from_response(response)
        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object")

        try:
            bull = float(parsed.get("bull"))
            base = float(parsed.get("base"))
            bear = float(parsed.get("bear"))
        except (TypeError, ValueError) as exc:
            raise ValueError("bull/base/bear must be numeric") from exc

        reversion_horizon = parsed.get("reversion_horizon")
        if reversion_horizon not in VALID_HORIZONS:
            raise ValueError("reversion_horizon is not in the allowed enum")

        monotonic_valid = bear <= base <= bull
        return {
            "format_valid": True,
            "bull": bull,
            "base": base,
            "bear": bear,
            "reversion_horizon": reversion_horizon,
            "monotonic_valid": monotonic_valid,
            "error": None,
        }
    except ValueError as exc:
        return {
            "format_valid": False,
            "bull": None,
            "base": None,
            "bear": None,
            "reversion_horizon": None,
            "monotonic_valid": None,
            "error": str(exc),
        }
