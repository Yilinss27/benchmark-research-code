#!/usr/bin/env python3
"""Replace legacy B-macro rows with curated official-source events."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.providers.yahoo import YahooPriceProvider
from src.data_generator import (
    DEFAULT_CURRENT_DATE,
    DEFAULT_TRAINING_CUTOFF,
    generate_b_macro,
)
from scripts.assign_time_bands import update_row as update_temporal_band


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/macro_events_v1.json")
    parser.add_argument("--seed", default="seeds/b_event.jsonl")
    parser.add_argument(
        "--min-generated",
        type=int,
        default=7,
        help="Minimum number of verified macro rows required.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    args = parse_args()
    seed_path = ROOT / args.seed
    existing = load_jsonl(seed_path)
    generated, warnings = generate_b_macro(
        ROOT / args.config,
        YahooPriceProvider(),
    )
    generated = [
        update_temporal_band(
            row,
            DEFAULT_TRAINING_CUTOFF,
            DEFAULT_CURRENT_DATE,
        )
        for row in generated
    ]
    if len(generated) < args.min_generated:
        raise SystemExit(
            f"Expected at least {args.min_generated} verified macro rows, generated {len(generated)}; "
            f"warnings={warnings}"
        )
    retained = [row for row in existing if row.get("variant") != "macro"]
    output = retained + generated
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in output),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "removed_macro": len(existing) - len(retained),
                "added_macro": len(generated),
                "total_b": len(output),
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
