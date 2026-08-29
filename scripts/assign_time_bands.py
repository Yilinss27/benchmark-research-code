#!/usr/bin/env python3
"""Assign reproducible temporal bands (T1/T2/T3) to ready seeds."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


READY_FILES = [
    "seeds/a1_valuation.jsonl",
    "seeds/a2_fundamentals.jsonl",
    "seeds/a2_technical.jsonl",
    "seeds/a2_hybrid.jsonl",
    "seeds/b_event.jsonl",
    "seeds/c_financial_metric.jsonl",
    "seeds/d_counterfactual.jsonl",
    "seeds/e_formula.jsonl",
]

SYNTHETIC_DATE_BY_BAND = {
    "T1": "training_cutoff",
    "T2": "training_cutoff_plus_365d",
    "T3": "current_date_plus_180d",
}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Assign T1/T2/T3 temporal bands to ready seeds.")
    parser.add_argument(
        "--training-cutoff",
        default="2024-06-30",
        help="Model pretraining cutoff date. cutoff_date <= this date is T1.",
    )
    parser.add_argument(
        "--current-date",
        default="2026-08-17",
        help="Reference current date. training_cutoff < cutoff_date < current_date is T2; current_date and later is T3.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Rewrite seed files in place. Without this flag, only print the summary.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL rows."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write JSONL rows."""
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_date(value: str) -> date:
    """Parse an ISO date."""
    return date.fromisoformat(value)


def classify(cutoff_date: str, training_cutoff: str, current_date: str) -> str:
    """Classify a cutoff date into T1/T2/T3."""
    cutoff = parse_date(cutoff_date)
    training = parse_date(training_cutoff)
    current = parse_date(current_date)

    if cutoff <= training:
        return "T1"
    if cutoff < current:
        return "T2"
    return "T3"


def synthetic_cutoff_for_band(band: str, training_cutoff: str, current_date: str) -> str:
    """Return a synthetic cutoff date when a task has no natural cutoff date."""
    training = parse_date(training_cutoff)
    current = parse_date(current_date)
    if band == "T1":
        return training.isoformat()
    if band == "T2":
        return (training + timedelta(days=365)).isoformat()
    if band == "T3":
        return (current + timedelta(days=180)).isoformat()
    raise ValueError(f"Unsupported synthetic band: {band}")


def extract_cutoff(row: dict[str, Any], training_cutoff: str, current_date: str) -> tuple[str, str, bool]:
    """Extract or assign a cutoff date.

    Returns (cutoff_date, source, is_synthetic).
    """
    seed = row.setdefault("seed", {})
    metadata = row.setdefault("metadata", {})

    if seed.get("cutoff_date"):
        return str(seed["cutoff_date"]), "seed.cutoff_date", False
    if seed.get("event_date"):
        return str(seed["event_date"]), "seed.event_date", False

    existing_band = row.get("time_band")
    if row.get("category") == "D" and existing_band in {"T1", "T2", "T3"}:
        cutoff = synthetic_cutoff_for_band(existing_band, training_cutoff, current_date)
        seed["cutoff_date"] = cutoff
        return cutoff, f"synthetic_from_existing_{existing_band}", True

    if row.get("category") == "E":
        # Formula questions are atemporal. Keep them explicit but place them in T1
        # by convention because they do not depend on post-cutoff market facts.
        seed["cutoff_date"] = training_cutoff
        metadata["temporal_applicability"] = "atemporal_formula"
        return training_cutoff, "synthetic_atemporal_formula", True

    raise ValueError(f"{row.get('task_id')} has no cutoff_date/event_date and no supported synthetic policy")


def update_row(
    row: dict[str, Any],
    training_cutoff: str,
    current_date: str,
) -> dict[str, Any]:
    """Update one record with temporal metadata."""
    cutoff, source, is_synthetic = extract_cutoff(row, training_cutoff, current_date)
    band = classify(cutoff, training_cutoff, current_date)

    row["cutoff_date"] = cutoff
    row["time_band"] = band
    metadata = row.setdefault("metadata", {})
    metadata["temporal_split"] = {
        "time_band": band,
        "cutoff_date": cutoff,
        "cutoff_date_source": source,
        "is_synthetic_cutoff_date": is_synthetic,
        "model_training_cutoff": training_cutoff,
        "reference_current_date": current_date,
        "rule": "T1: cutoff_date <= model_training_cutoff; T2: model_training_cutoff < cutoff_date < reference_current_date; T3: cutoff_date >= reference_current_date",
    }
    return row


def main() -> int:
    """Assign temporal bands to all ready files."""
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    summary: dict[str, dict[str, int]] = {}

    for rel in READY_FILES:
        path = root / rel
        rows = load_jsonl(path)
        updated = [update_row(row, args.training_cutoff, args.current_date) for row in rows]
        counts: dict[str, int] = {"T1": 0, "T2": 0, "T3": 0}
        for row in updated:
            counts[row["time_band"]] += 1
        summary[rel] = counts
        if args.in_place:
            write_jsonl(path, updated)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
