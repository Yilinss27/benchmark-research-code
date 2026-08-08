"""Evaluator for task D counterfactual records."""

from __future__ import annotations

from typing import Any


def evaluate_d(parsed: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a parsed D-task prediction against its record."""
    ground_truth = record.get("ground_truth") or {}
    expected_direction = ground_truth.get("logic_direction")
    predicted_direction = parsed.get("direction")
    format_valid = bool(parsed.get("format_valid"))

    logic_adherence: bool | None
    if expected_direction is None:
        logic_adherence = None
    else:
        logic_adherence = format_valid and predicted_direction == expected_direction

    return {
        "format_valid": format_valid,
        "logic_adherence": logic_adherence,
        "time_band": record.get("time_band"),
        "expected_direction": expected_direction,
        "predicted_direction": predicted_direction,
    }
