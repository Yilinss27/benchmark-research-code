"""Pure functions for A2 technical indicators from price closes."""

from __future__ import annotations

import math
from typing import Callable, Sequence

TECHNICAL_KEYS = ("rsi_14", "macd_histogram", "momentum_20d", "bollinger_zscore")
TECHNICAL_METRICS_VERSION = "a2_technical_v1"
MIN_TRADING_DAYS_FOR_READY = 21
LOOKBACK_TRADING_DAYS = 40


def ema(values: Sequence[float], period: int) -> list[float]:
    """Compute exponential moving average with SMA seed."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        raise ValueError(f"need at least {period} values for EMA{period}")

    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    result = [seed]
    for value in values[period:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


def rsi_14(closes: Sequence[float]) -> float:
    """Compute 14-day RSI using simple average gains/losses (not Wilder smoothing)."""
    if len(closes) < 15:
        raise ValueError("need at least 15 closes for RSI-14")

    window = closes[-15:]
    gains: list[float] = []
    losses: list[float] = []
    for prev, curr in zip(window[:-1], window[1:]):
        change = curr - prev
        if change >= 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-change)

    avg_gain = sum(gains) / 14.0
    avg_loss = sum(losses) / 14.0
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def ema_series(values: Sequence[float], period: int) -> list[float]:
    """Return a full-length EMA series aligned with the input values."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        raise ValueError(f"need at least {period} values for EMA{period}")

    alpha = 2.0 / (period + 1)
    series = [0.0] * len(values)
    series[period - 1] = sum(values[:period]) / period
    for index in range(period, len(values)):
        series[index] = alpha * values[index] + (1.0 - alpha) * series[index - 1]
    return series


def macd_histogram(closes: Sequence[float]) -> float:
    """Compute MACD histogram at cutoff: DIF - DEA with EMA12/EMA26 and 9-day DEA."""
    if len(closes) < 34:
        raise ValueError("need at least 34 closes for MACD histogram")

    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    dif_series = [a - b for a, b in zip(ema12, ema26)]
    dif_tail = dif_series[25:]
    if len(dif_tail) < 9:
        raise ValueError("insufficient DIF values for DEA")

    dea_tail = ema(dif_tail, 9)
    return dif_tail[-1] - dea_tail[-1]


def momentum_20d(closes: Sequence[float]) -> float:
    """Compute 20-day momentum: (P0 - P_-20) / P_-20, P_-20 is index -21."""
    if len(closes) < 21:
        raise ValueError("need at least 21 closes for momentum_20d")

    p0 = closes[-1]
    p_minus_20 = closes[-21]
    if p_minus_20 == 0:
        raise ValueError("P_-20 cannot be zero")
    return (p0 - p_minus_20) / p_minus_20


def bollinger_zscore(closes: Sequence[float]) -> float | None:
    """Compute Bollinger Z-score; return null when sample STD20 is zero."""
    if len(closes) < 20:
        raise ValueError("need at least 20 closes for bollinger_zscore")

    window = closes[-20:]
    mean_20 = sum(window) / 20.0
    # Sample standard deviation with ddof=1 (fixed口径).
    variance = sum((value - mean_20) ** 2 for value in window) / 19.0
    std_20 = math.sqrt(variance)
    if std_20 == 0:
        return None
    return (closes[-1] - mean_20) / std_20


def _safe_metric(
    metric_fn: Callable[[Sequence[float]], float | None],
    closes: Sequence[float],
) -> float | None:
    """Run a metric function and return null when inputs are insufficient."""
    try:
        value = metric_fn(closes)
        if value is None:
            return None
        return round(float(value), 6)
    except (ValueError, ZeroDivisionError):
        return None


def compute_technical_dict(closes: Sequence[float]) -> dict[str, float | None]:
    """Compute all A2 technical metrics; individual metrics may be null."""
    return {
        "rsi_14": _safe_metric(rsi_14, closes),
        "macd_histogram": _safe_metric(macd_histogram, closes),
        "momentum_20d": _safe_metric(momentum_20d, closes),
        "bollinger_zscore": _safe_metric(bollinger_zscore, closes),
    }


def null_technical_keys(metrics: dict[str, float | None]) -> list[str]:
    """Return technical metric keys that resolved to null."""
    return [key for key in TECHNICAL_KEYS if metrics.get(key) is None]
