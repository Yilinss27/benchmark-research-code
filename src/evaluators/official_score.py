"""Official benchmark score: task-equal average on paper T2 records."""

from __future__ import annotations

from statistics import mean
from typing import Any


OFFICIAL_TASKS = ("A1", "A2-F", "A2-T", "A2-H", "B", "C")


def _task_key(prediction: dict[str, Any]) -> str | None:
    """Map a prediction to an official task bucket."""
    category = prediction.get("category")
    if category == "A1":
        return "A1"
    if category == "A2":
        variant = prediction.get("variant")
        if variant in {"F", "T", "H"}:
            return f"A2-{variant}"
    if category == "B":
        return "B"
    if category == "C":
        return "C"
    return None


def primary_task_score(metrics: dict[str, Any], task_key: str) -> float | None:
    """Return a 0-1 primary score for one evaluated record."""
    if not metrics.get("format_valid"):
        return 0.0

    if task_key == "A1":
        window = metrics.get("by_window", {}).get("90", {})
        hit = window.get("range_hit")
        return 1.0 if hit is True else (0.0 if hit is False else None)

    if task_key.startswith("A2-"):
        rho = metrics.get("spearman_rho")
        if rho is None:
            match = metrics.get("exact_set_match")
            return 1.0 if match is True else (0.0 if match is False else None)
        return max(0.0, min(1.0, (float(rho) + 1.0) / 2.0))

    if task_key == "B":
        acc = metrics.get("directional_accuracy")
        return 1.0 if acc is True else (0.0 if acc is False else None)

    if task_key == "C":
        within = metrics.get("within_10pct")
        return 1.0 if within is True else (0.0 if within is False else None)

    return None


def aggregate_official_score(
    predictions: list[dict[str, Any]],
    *,
    paper_band: str = "T2",
) -> dict[str, Any]:
    """Compute task-equal official score using only the requested paper band."""
    eligible = [
        prediction
        for prediction in predictions
        if prediction.get("paper_band") == paper_band
        and prediction.get("official_temporal_eligible", True)
    ]

    by_task: dict[str, list[float]] = {task: [] for task in OFFICIAL_TASKS}
    for prediction in eligible:
        task_key = _task_key(prediction)
        if task_key is None or task_key not in by_task:
            continue
        score = primary_task_score(prediction.get("metrics") or {}, task_key)
        if score is not None:
            by_task[task_key].append(score)

    per_task = {
        task: {
            "count": len(scores),
            "mean_score": mean(scores) if scores else None,
        }
        for task, scores in by_task.items()
    }
    task_means = [item["mean_score"] for item in per_task.values() if item["mean_score"] is not None]
    official_score = mean(task_means) if task_means else None

    return {
        "paper_band": paper_band,
        "official_score": official_score,
        "task_equal_task_count": len(task_means),
        "per_task": per_task,
        "eligible_records": len(eligible),
    }
