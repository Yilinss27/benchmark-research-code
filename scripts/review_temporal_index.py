#!/usr/bin/env python3
"""Promote temporal rows only when deterministic evidence checks pass."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


BLOCKING_FLAGS = {
    "fundamentals_after_origin",
    "missing_event_evidence",
    "missing_outcome_evidence",
    "missing_forward_trading_day",
    "modeled_outcome_availability",
    "non_pit_fundamentals",
    "official_disclosure_lookup_failed",
    "official_event_lookup_failed",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default="data/task_temporal_index.jsonl")
    return parser.parse_args()


def evidence_valid(row: dict) -> bool:
    flags = set(row.get("quality_flags") or [])
    if row.get("official_temporal_eligible") is not True or flags & BLOCKING_FLAGS:
        return False
    source = str(row.get("outcome_available_at_source") or "")
    category = row.get("category")
    source_valid = source.startswith("observed_") or source in {
        "formula_static",
        "synthetic_same_as_origin",
    }
    if not source_valid:
        return False
    if not row.get("outcome_evidence_code") and not row.get("outcome_evidence_url"):
        return False
    if category in {"B", "C"} and not row.get("outcome_evidence_url"):
        return False
    return True


def evidence_hash(row: dict) -> str:
    payload = {
        key: row.get(key)
        for key in (
            "task_id",
            "forecast_origin",
            "outcome_available_at",
            "outcome_available_at_source",
            "outcome_evidence_url",
            "outcome_evidence_code",
            "quality_flags",
        )
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def main() -> int:
    args = parse_args()
    path = Path(args.index)
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    reviewed_at = datetime.now(timezone.utc).isoformat()
    reviewed = 0
    for row in rows:
        if evidence_valid(row):
            row["review_status"] = "reviewed"
            row["review_method"] = "automated_evidence_validation"
            row["reviewed_at"] = reviewed_at
            row["evidence_hash"] = evidence_hash(row)
            reviewed += 1
        else:
            row["review_status"] = "draft"
            row.pop("review_method", None)
            row.pop("reviewed_at", None)
            row.pop("evidence_hash", None)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(json.dumps({"total": len(rows), "reviewed": reviewed, "draft": len(rows) - reviewed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
