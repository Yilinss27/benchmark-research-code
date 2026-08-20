"""Utilities for loading and filtering benchmark seed records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.temporal.paper_bands import load_temporal_index, merge_index_by_task_id


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dictionaries."""
    file_path = Path(path)
    records: list[dict[str, Any]] = []

    with file_path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{file_path}:{line_no} invalid JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{file_path}:{line_no} expected JSON object per line")
            records.append(obj)

    return records


def filter_records(
    records: list[dict[str, Any]],
    category: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Filter records by category and/or status."""
    filtered = records
    if category is not None:
        filtered = [record for record in filtered if record.get("category") == category]
    if status is not None:
        filtered = [record for record in filtered if record.get("status") == status]
    return filtered


def attach_temporal_index(
    records: list[dict[str, Any]],
    index_path: str | Path,
) -> list[dict[str, Any]]:
    """Attach paper temporal fields from a task-temporal-index file."""
    index = load_temporal_index(index_path)
    return merge_index_by_task_id(records, index)


def filter_paper_band(
    records: list[dict[str, Any]],
    paper_band: str | None = None,
    *,
    exclude_quarantine: bool = False,
) -> list[dict[str, Any]]:
    """Filter records by paper_band attached via attach_temporal_index."""
    filtered = records
    if exclude_quarantine:
        filtered = [
            record
            for record in filtered
            if record.get("paper_band") not in {None, "quarantine"}
        ]
    if paper_band is not None:
        filtered = [record for record in filtered if record.get("paper_band") == paper_band]
    return filtered
