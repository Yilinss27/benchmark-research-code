"""Mock agent for local benchmark smoke tests."""

from __future__ import annotations

import json
from typing import Any


def _build_a1_mock_response(record: dict[str, Any]) -> str:
    """Construct a deterministic A1 response from ground truth prices."""
    ground_truth = record.get("ground_truth") or {}
    cutoff_price = ground_truth.get("cutoff_price")
    actual_prices = ground_truth.get("actual_prices") or {}

    base_source = cutoff_price
    if base_source in (None, 0):
        for key in ("90", "180", "30", "365"):
            if actual_prices.get(key) is not None:
                base_source = actual_prices[key]
                break
    if base_source is None:
        raise ValueError("A1 record missing usable price for mock response")

    base = float(base_source)
    response = {
        "bull": round(base * 1.10, 4),
        "base": round(base, 4),
        "bear": round(base * 0.90, 4),
        "reversion_horizon": "3-6个月",
    }
    return json.dumps(response, ensure_ascii=False)


def mock_agent(prompt: str, record: dict[str, Any]) -> str:
    """Return deterministic JSON responses from record ground truth."""
    del prompt

    category = record.get("category")
    ground_truth = record.get("ground_truth") or {}

    if category == "A1":
        return _build_a1_mock_response(record)

    if category == "A2":
        actual_ranking = ground_truth.get("actual_ranking")
        if isinstance(actual_ranking, list) and all(isinstance(item, str) for item in actual_ranking):
            return json.dumps(actual_ranking, ensure_ascii=False)
        stock_list = record.get("seed", {}).get("stock_list", [])
        fallback_ranking = [stock["code"] for stock in stock_list]
        return json.dumps(fallback_ranking, ensure_ascii=False)

    if category == "D":
        direction = ground_truth.get("logic_direction")
        if direction is None:
            raise ValueError("D record missing ground_truth.logic_direction")
        return json.dumps(
            {
                "direction": direction,
                "reasoning": "根据虚构事件的基本定价逻辑判断。",
            },
            ensure_ascii=False,
        )

    if category == "E":
        correct_answer = ground_truth.get("correct_answer")
        correct_formula = ground_truth.get("correct_formula")
        answer_unit = ground_truth.get("answer_unit")
        if correct_answer is None or correct_formula is None or answer_unit is None:
            raise ValueError("E record missing complete ground truth")
        return json.dumps(
            {
                "formula_used": correct_formula,
                "answer": correct_answer,
                "unit": answer_unit,
            },
            ensure_ascii=False,
        )

    if category == "C":
        future_value = ground_truth.get("future_value")
        if future_value is None:
            raise ValueError("C record missing ground_truth.future_value")
        return json.dumps({"predicted_value": future_value}, ensure_ascii=False)

    if category == "B":
        actual_direction = ground_truth.get("actual_direction")
        if actual_direction not in {"up", "down"}:
            raise ValueError("B record missing ground_truth.actual_direction")
        probability_up = 1.0 if actual_direction == "up" else 0.0
        return json.dumps(
            {"direction": actual_direction, "probability_up": probability_up},
            ensure_ascii=False,
        )

    raise ValueError(f"Unsupported category for mock agent: {category}")
