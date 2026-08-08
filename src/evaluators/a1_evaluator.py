"""Evaluator for task A1 valuation-range records."""

from __future__ import annotations

from typing import Any


HORIZON_TO_DAYS: dict[str, tuple[int, int]] = {
    "1-4周": (7, 28),
    "1-3个月": (30, 90),
    "3-6个月": (90, 180),
    "6-12个月": (180, 365),
    "超过12个月": (365, 100000),
}

WINDOW_DAYS = ("30", "90", "180", "365")


def _compute_error(actual: float, base: float) -> tuple[float, str]:
    """Compute target price error under normal or zero-base handling."""
    if base == 0:
        return abs(actual - base), "absolute_error_base_zero"
    return abs(actual - base) / abs(base), "relative_error"


def _compute_monotonic_valid(parsed: dict[str, Any]) -> bool | None:
    """Compute monotonic validity from parsed A1 values."""
    bull = parsed.get("bull")
    base = parsed.get("base")
    bear = parsed.get("bear")
    if bull is None or base is None or bear is None:
        return None
    return bear <= base <= bull


def _compute_reversion_horizon_hit(
    parsed: dict[str, Any],
    actual_prices: dict[str, Any],
) -> bool | None:
    """Check whether observed prices enter the predicted range within the mapped horizon."""
    horizon = parsed.get("reversion_horizon")
    bear = parsed.get("bear")
    bull = parsed.get("bull")
    if horizon not in HORIZON_TO_DAYS or bear is None or bull is None:
        return None

    start_day, end_day = HORIZON_TO_DAYS[horizon]
    candidates: list[float] = []
    for day_str, price in actual_prices.items():
        if price is None:
            continue
        day = int(day_str)
        if start_day <= day <= end_day:
            candidates.append(float(price))

    if not candidates:
        return None
    return any(bear <= price <= bull for price in candidates)


def evaluate_a1(parsed: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a parsed A1 prediction against future price windows."""
    ground_truth = record.get("ground_truth") or {}
    actual_prices = ground_truth.get("actual_prices") or {}
    base = parsed.get("base")
    bear = parsed.get("bear")
    bull = parsed.get("bull")

    by_window: dict[str, Any] = {}
    for day_str in WINDOW_DAYS:
        actual = actual_prices.get(day_str)
        if actual is None or base is None or bear is None or bull is None:
            by_window[day_str] = {
                "target_price_error_abs": None,
                "target_price_error_mode": None,
                "range_hit": None,
            }
            continue

        actual_float = float(actual)
        error_value, error_mode = _compute_error(actual_float, float(base))
        by_window[day_str] = {
            "target_price_error_abs": error_value,
            "target_price_error_mode": error_mode,
            "range_hit": bear <= actual_float <= bull,
        }

    monotonic_valid = parsed.get("monotonic_valid")
    if monotonic_valid is None:
        monotonic_valid = _compute_monotonic_valid(parsed)

    return {
        "format_valid": bool(parsed.get("format_valid")),
        "monotonic_valid": monotonic_valid,
        "by_window": by_window,
        "reversion_horizon_hit": _compute_reversion_horizon_hit(parsed, actual_prices),
    }
