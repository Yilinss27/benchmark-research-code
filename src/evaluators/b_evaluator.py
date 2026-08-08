"""Evaluator for task B event-driven direction records."""

from __future__ import annotations

from typing import Any


def evaluate_b(parsed: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a parsed B-task prediction against actual direction."""
    ground_truth = record.get("ground_truth") or {}
    actual_direction = ground_truth.get("actual_direction")
    predicted_direction = parsed.get("direction")
    probability_up = parsed.get("probability_up")
    format_valid = bool(parsed.get("format_valid"))

    directional_accuracy: bool | None = None
    brier_score: float | None = None

    if actual_direction is not None and format_valid and predicted_direction is not None:
        directional_accuracy = predicted_direction == actual_direction

    if actual_direction is not None and format_valid and probability_up is not None:
        actual_up = 1.0 if actual_direction == "up" else 0.0
        brier_score = (float(probability_up) - actual_up) ** 2

    return {
        "format_valid": format_valid,
        "directional_accuracy": directional_accuracy,
        "brier_score": brier_score,
        "variant": record.get("variant"),
        "predicted_direction": predicted_direction,
        "actual_direction": actual_direction,
        "probability_up": probability_up,
    }
