"""Evaluator for A2 fundamentals-only ranking records."""

from __future__ import annotations

from math import floor
from typing import Any


def _ranking_metadata(ranking: list[str] | None, expected_codes: list[str]) -> tuple[bool | None, bool | None, bool | None]:
    """Compute structural ranking checks."""
    if ranking is None:
        return None, None, None
    ranking_length_match = len(ranking) == len(expected_codes)
    duplicate_free = len(ranking) == len(set(ranking))
    exact_set_match = set(ranking) == set(expected_codes)
    return exact_set_match, ranking_length_match, duplicate_free


def _ranks_from_order(order: list[str]) -> dict[str, int]:
    """Convert an ordered list into 1-indexed ranks."""
    return {code: index + 1 for index, code in enumerate(order)}


def _spearman_rho(pred_order: list[str], actual_order: list[str]) -> float | None:
    """Compute Spearman rank correlation without third-party libraries."""
    if not pred_order or len(pred_order) != len(actual_order):
        return None
    pred_ranks = _ranks_from_order(pred_order)
    actual_ranks = _ranks_from_order(actual_order)
    if set(pred_ranks) != set(actual_ranks):
        return None
    n = len(pred_order)
    if n < 2:
        return None
    diff_sq = sum((pred_ranks[code] - actual_ranks[code]) ** 2 for code in pred_ranks)
    return 1 - (6 * diff_sq) / (n * (n**2 - 1))


def evaluate_a2(parsed: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an A2-F ranking prediction against actual returns."""
    stock_list = record.get("seed", {}).get("stock_list", [])
    expected_codes = [stock["code"] for stock in stock_list]
    ranking = parsed.get("ranking")

    exact_set_match, ranking_length_match, duplicate_free = _ranking_metadata(ranking, expected_codes)

    ground_truth = record.get("ground_truth") or {}
    actual_returns = ground_truth.get("actual_returns")
    actual_ranking = ground_truth.get("actual_ranking")

    n = len(expected_codes)
    k_value = floor(n / 3) if n else None

    pred_top_k: list[str] | None = None
    pred_bottom_k: list[str] | None = None
    actual_top_k: list[str] | None = None
    spearman_rho: float | None = None
    top_k_hit_rate: float | None = None
    long_short_spread: float | None = None

    structurally_valid = (
        bool(parsed.get("format_valid"))
        and ranking is not None
        and exact_set_match is True
        and ranking_length_match is True
        and duplicate_free is True
    )

    if (
        structurally_valid
        and isinstance(actual_returns, dict)
        and isinstance(actual_ranking, list)
        and k_value is not None
        and k_value >= 1
    ):
        pred_top_k = ranking[:k_value]
        pred_bottom_k = ranking[-k_value:]
        actual_top_k = actual_ranking[:k_value]

        spearman_rho = _spearman_rho(ranking, actual_ranking)
        top_k_hit_rate = len(set(pred_top_k) & set(actual_top_k)) / k_value

        long_returns = [float(actual_returns[code]) for code in pred_top_k]
        short_returns = [float(actual_returns[code]) for code in pred_bottom_k]
        long_short_spread = (sum(long_returns) / k_value) - (sum(short_returns) / k_value)

    return {
        "format_valid": bool(parsed.get("format_valid")),
        "exact_set_match": exact_set_match,
        "ranking_length_match": ranking_length_match,
        "duplicate_free": duplicate_free,
        "spearman_rho": spearman_rho,
        "top_k_hit_rate": top_k_hit_rate,
        "long_short_spread": long_short_spread,
        "k_value": k_value,
        "pred_top_k": pred_top_k,
        "pred_bottom_k": pred_bottom_k,
        "actual_top_k": actual_top_k,
    }
