#!/usr/bin/env python3
"""Report per-task official evidence coverage without promoting weak records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default="data/task_temporal_index.jsonl")
    parser.add_argument("--output", default="data/official_evidence_gaps.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = [
        json.loads(line)
        for line in Path(args.index).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    details = []
    counts: Counter[str] = Counter()
    for row in rows:
        category = row.get("category")
        variant = row.get("variant")
        if category not in {"B", "C"}:
            continue
        flags = set(row.get("quality_flags") or [])
        if category == "B":
            status = "verified" if "missing_event_evidence" not in flags else "missing"
            scope = f"B-{variant}"
        elif "modeled_outcome_availability" in flags:
            status = "missing"
            scope = "C-disclosure"
        elif "non_pit_fundamentals" in flags:
            status = "ambiguous"
            scope = "C-values"
        else:
            status = "verified"
            scope = "C"
        counts[f"{scope}:{status}"] += 1
        details.append(
            {
                "task_id": row["task_id"],
                "scope": scope,
                "status": status,
                "source": row.get("outcome_available_at_source"),
                "source_url": row.get("outcome_evidence_url"),
                "quality_flags": sorted(flags),
                "error": row.get("enrichment_error"),
            }
        )
    payload = {
        "summary": dict(sorted(counts.items())),
        "records": details,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
