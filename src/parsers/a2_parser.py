"""Parser for A2 ranking outputs."""

from __future__ import annotations

from typing import Any

from src.parsers.common import extract_json_from_response


def parse_a2_response(response: str) -> dict[str, Any]:
    """Parse an A2 response into a ranking list."""
    try:
        parsed = extract_json_from_response(response)
        ranking: Any
        if isinstance(parsed, list):
            ranking = parsed
        elif isinstance(parsed, dict):
            ranking = parsed.get("ranking")
        else:
            raise ValueError("Expected JSON array or object with ranking field")

        if not isinstance(ranking, list):
            raise ValueError("ranking must be a list")
        if not all(isinstance(item, str) for item in ranking):
            raise ValueError("ranking items must all be strings")

        return {
            "format_valid": True,
            "ranking": ranking,
            "error": None,
        }
    except ValueError as exc:
        return {
            "format_valid": False,
            "ranking": None,
            "error": str(exc),
        }
