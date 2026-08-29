#!/usr/bin/env python3
"""Report per-market coverage and enforce minimum counts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_FILES = {
    "A1": "seeds/a1_valuation.jsonl",
    "A2-F": "seeds/a2_fundamentals.jsonl",
    "A2-T": "seeds/a2_technical.jsonl",
    "A2-H": "seeds/a2_hybrid.jsonl",
    "B": "seeds/b_event.jsonl",
}
MARKETS = ("CN_A", "US", "HK")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=30)
    return parser.parse_args()


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    args = parse_args()
    matrix: dict[str, dict[str, int]] = {}
    errors: list[str] = []
    for task, rel in TASK_FILES.items():
        counts = Counter()
        for row in _load(ROOT / rel):
            if row.get("status") != "ready":
                continue
            seed = row.get("seed") or {}
            market = str(seed.get("market") or (row.get("metadata") or {}).get("market") or "CN_A")
            counts[market] += 1
        matrix[task] = {m: int(counts.get(m, 0)) for m in MARKETS}
        for market in MARKETS:
            if counts.get(market, 0) < args.target:
                errors.append(f"{task} {market}={counts.get(market, 0)} < {args.target}")
    print(json.dumps({"target": args.target, "coverage": matrix, "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
