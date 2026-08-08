"""Parser for task D counterfactual outputs."""

from __future__ import annotations

from typing import Any

from .common import extract_json_from_response


VALID_DIRECTIONS = {"positive", "negative"}


def parse_d_response(response: str) -> dict[str, Any]:
    """Parse a D-task response into a normalized structure."""
    try:
        parsed = extract_json_from_response(response)
        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object")

        direction = parsed.get("direction")
        reasoning = parsed.get("reasoning")

        if direction not in VALID_DIRECTIONS:
            return {
                "format_valid": False,
                "direction": None,
                "reasoning": reasoning if isinstance(reasoning, str) else None,
                "error": "direction must be positive or negative",
            }

        return {
            "format_valid": True,
            "direction": direction,
            "reasoning": reasoning if isinstance(reasoning, str) else None,
            "error": None,
        }
    except ValueError as exc:
        return {
            "format_valid": False,
            "direction": None,
            "reasoning": None,
            "error": str(exc),
        }
