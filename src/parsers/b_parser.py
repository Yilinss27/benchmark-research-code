"""Parser for task B event-driven direction outputs."""

from __future__ import annotations

from typing import Any

from src.parsers.common import extract_json_from_response


VALID_DIRECTIONS = {"up", "down"}


def parse_b_response(response: str) -> dict[str, Any]:
    """Parse a B-task response into direction and probability_up."""
    try:
        parsed = extract_json_from_response(response)
        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object")

        direction = parsed.get("direction")
        probability_up = parsed.get("probability_up")

        if direction not in VALID_DIRECTIONS:
            raise ValueError("direction must be up or down")
        if probability_up is None:
            raise ValueError("probability_up is required")

        probability_float = float(probability_up)
        if not 0.0 <= probability_float <= 1.0:
            raise ValueError("probability_up must be between 0 and 1")

        return {
            "format_valid": True,
            "direction": direction,
            "probability_up": probability_float,
            "error": None,
        }
    except (ValueError, TypeError) as exc:
        return {
            "format_valid": False,
            "direction": None,
            "probability_up": None,
            "error": str(exc),
        }
