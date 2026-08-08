"""Utilities for loading and filtering benchmark seed records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
