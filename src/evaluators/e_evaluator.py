"""Evaluator for task E formula-calculation records."""

from __future__ import annotations

from typing import Any


def _formula_text_match(parsed_formula: str | None, correct_formula: str | None) -> bool | None:
    if not parsed_formula or not correct_formula:
        return None
    left = parsed_formula.lower()
    right = correct_formula.lower()
    return left in right or right in left


def _unit_match(parsed_unit: str | None, answer_unit: str | None) -> bool | None:
    if not parsed_unit or not answer_unit:
        return None
    return parsed_unit == answer_unit or parsed_unit.lower() == answer_unit.lower()


def evaluate_e(parsed: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a parsed E-task prediction against its ground truth."""
    ground_truth = record.get("ground_truth") or {}
    answer = parsed.get("answer")
    correct_answer = ground_truth.get("correct_answer")
    format_valid = bool(parsed.get("format_valid"))

    relative_error: float | None = None
    exact_match_0_2pct: bool | None = None

    if isinstance(answer, float) and isinstance(correct_answer, (int, float)):
        correct_answer_float = float(correct_answer)
        abs_error = abs(answer - correct_answer_float)
        if correct_answer_float == 0.0:
            relative_error = abs_error
            exact_match_0_2pct = abs_error < 1e-9
        else:
            relative_error = abs_error / abs(correct_answer_float)
            exact_match_0_2pct = relative_error < 0.002

    return {
        "format_valid": format_valid,
        "relative_error": relative_error,
        "exact_match_0_2pct": exact_match_0_2pct,
        "formula_text_match": _formula_text_match(
            parsed.get("formula_used"),
            ground_truth.get("correct_formula"),
        ),
        "unit_match": _unit_match(parsed.get("unit"), ground_truth.get("answer_unit")),
    }
