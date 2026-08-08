"""Evaluator for task C financial metric prediction records."""

from __future__ import annotations

from typing import Any


def evaluate_c(parsed: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a parsed C-task prediction against future_value ground truth."""
    ground_truth = record.get("ground_truth") or {}
    future_value = ground_truth.get("future_value")
    predicted_value = parsed.get("predicted_value")
    format_valid = bool(parsed.get("format_valid"))

    mape: float | None = None
    within_10pct: bool | None = None

    if format_valid and predicted_value is not None and future_value is not None:
        denominator = abs(float(future_value))
        if denominator == 0:
            mape = 0.0 if float(predicted_value) == 0 else None
        else:
            mape = abs(float(predicted_value) - float(future_value)) / denominator
        if mape is not None:
            within_10pct = mape <= 0.10

    return {
        "format_valid": format_valid,
        "mape": mape,
        "within_10pct": within_10pct,
        "predicted_value": predicted_value,
        "future_value": future_value,
        "metric_name": record.get("seed", {}).get("metric_name"),
    }
