#!/usr/bin/env python3
"""Expand A/B market coverage until each market-task count reaches target."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_generator import DEFAULT_CURRENT_DATE, DEFAULT_TRAINING_CUTOFF, generate

TASK_TO_FILE = {
    "A1": "seeds/a1_valuation.jsonl",
    "A2-F": "seeds/a2_fundamentals.jsonl",
    "A2-H": "seeds/a2_hybrid.jsonl",
    "B": "seeds/b_event.jsonl",
}
MARKETS = ("US", "HK")

A1_CUTOFFS = [
    "2022-06-30",
    "2022-12-30",
    "2023-06-30",
    "2023-12-29",
    "2024-03-29",
    "2025-03-31",
    "2026-01-30",
]
A2_CUTOFFS = [
    "2023-03-31",
    "2023-06-30",
    "2023-12-29",
    "2024-03-29",
    "2024-12-31",
    "2025-06-06",
    "2026-01-30",
]
B_CUTOFFS = [
    "2023-12-29",
    "2024-03-29",
    "2024-12-31",
    "2025-06-06",
    "2026-01-30",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=30, help="Minimum records per market per task.")
    parser.add_argument(
        "--tasks",
        default="A1,A2-F,A2-H,B",
        help="Comma-separated tasks to expand.",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _task_counts(task: str) -> dict[str, int]:
    rows = _load_jsonl(ROOT / TASK_TO_FILE[task])
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.get("status") != "ready":
            continue
        seed = row.get("seed") or {}
        market = str(seed.get("market") or (row.get("metadata") or {}).get("market") or "CN_A")
        counts[market] += 1
    return counts


def _cutoffs(task: str) -> list[str]:
    if task == "A1":
        return A1_CUTOFFS
    if task in {"A2-F", "A2-H"}:
        return A2_CUTOFFS
    return B_CUTOFFS


def main() -> int:
    args = parse_args()
    tasks = [x.strip() for x in args.tasks.split(",") if x.strip()]
    all_runs: list[dict] = []
    final_counts: dict[str, dict[str, int]] = {}

    for task in tasks:
        if task not in TASK_TO_FILE:
            raise ValueError(f"Unsupported task: {task}")
        output = ROOT / TASK_TO_FILE[task]
        cutoffs = _cutoffs(task)
        progressed = True
        while progressed:
            progressed = False
            counts = _task_counts(task)
            for market in MARKETS:
                while counts.get(market, 0) < args.target:
                    ran = False
                    for cutoff in cutoffs:
                        summary = generate(
                            task,
                            market,
                            cutoff,
                            output=output,
                            provider_name="yahoo",
                            append=True,
                            replace=False,
                            training_cutoff=DEFAULT_TRAINING_CUTOFF,
                            current_date=DEFAULT_CURRENT_DATE,
                        )
                        all_runs.append(summary)
                        if summary["added"] > 0:
                            counts[market] = counts.get(market, 0) + summary["added"]
                            progressed = True
                            ran = True
                            break
                    if not ran:
                        break
        final_counts[task] = _task_counts(task)

    print(
        json.dumps(
            {
                "target": args.target,
                "tasks": tasks,
                "markets": list(MARKETS),
                "final_counts": final_counts,
                "runs": len(all_runs),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
