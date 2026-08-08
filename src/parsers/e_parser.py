"""Parser for task E formula-calculation outputs."""

from __future__ import annotations

from typing import Any

from .common import extract_json_from_response


def parse_e_response(response: str) -> dict[str, Any]:
    """Parse an E-task response into a normalized structure."""
    try:
        parsed = extract_json_from_response(response)
        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object")

        formula_used = parsed.get("formula_used")
        answer = parsed.get("answer")
        unit = parsed.get("unit")

        try:
            answer_float = float(answer)
        except (TypeError, ValueError):
            return {
                "format_valid": False,
                "formula_used": formula_used if isinstance(formula_used, str) else None,
                "answer": None,
                "unit": unit if isinstance(unit, str) else None,
                "error": "answer must be numeric",
            }

        return {
            "format_valid": True,
            "formula_used": formula_used if isinstance(formula_used, str) else None,
            "answer": answer_float,
            "unit": unit if isinstance(unit, str) else None,
            "error": None,
        }
    except ValueError as exc:
        return {
            "format_valid": False,
            "formula_used": None,
            "answer": None,
            "unit": None,
            "error": str(exc),
        }
