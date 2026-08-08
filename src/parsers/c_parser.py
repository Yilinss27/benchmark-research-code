"""Parser for task C financial metric prediction outputs."""

from __future__ import annotations

from typing import Any

from src.parsers.common import extract_json_from_response


def parse_c_response(response: str) -> dict[str, Any]:
    """Parse a C-task response into predicted_value."""
    try:
        parsed = extract_json_from_response(response)
        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object")

        predicted_value = parsed.get("predicted_value")
        if predicted_value is None:
            raise ValueError("predicted_value is required")
        predicted_float = float(predicted_value)

        metric = parsed.get("metric")
        return {
            "format_valid": True,
            "predicted_value": predicted_float,
            "metric": metric if isinstance(metric, str) else None,
            "error": None,
        }
    except (ValueError, TypeError) as exc:
        return {
            "format_valid": False,
            "predicted_value": None,
            "metric": None,
            "error": str(exc),
        }
