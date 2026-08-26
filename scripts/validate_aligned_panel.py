#!/usr/bin/env python3
"""Validate T1/T2 structural symmetry for an aligned panel."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Validate aligned panel symmetry.")
    parser.add_argument("--config", default="configs/aligned_panel_v1.json")
    parser.add_argument(
        "--temporal-index",
        default=None,
        help="Override temporal index path (default from config).",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL rows."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cell_key(task_id: str, market: str) -> tuple[str, str, str]:
    """Return (family, market, cohort_or_stockbucket)."""
    parts = task_id.split("-")
    if task_id.startswith("A1-"):
        return ("A1", market, "all")
    if task_id.startswith(("A2F-", "A2T-", "A2H-")):
        family = parts[0]
        cohort = parts[-1]
        return (family, market, cohort)
    return (parts[0], market, "all")


def main() -> int:
    """Compare T1 vs T2 cell counts for the aligned panel."""
    args = parse_args()
    config = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    index_path = ROOT / (args.temporal_index or config["temporal_index"])
    index = {row["task_id"]: row for row in load_jsonl(index_path)}
    if not index:
        print(f"Missing temporal index: {index_path}", file=sys.stderr)
        return 1

    seed_dir = ROOT / config["output_dir"]
    records: list[dict[str, Any]] = []
    for path in sorted(seed_dir.glob("*.jsonl")):
        if path.name in {"all.jsonl"}:
            continue
        records.extend(load_jsonl(path))

    t1_cutoff = config["cutoffs"]["T1"]
    t2_cutoff = config["cutoffs"]["T2"]
    max_diff = int(config.get("symmetry", {}).get("max_count_diff_per_cell", 2))

    cells: dict[str, Counter[tuple[str, str, str]]] = {
        "T1": Counter(),
        "T2": Counter(),
    }
    band_counts: Counter[str] = Counter()
    skipped = 0
    for record in records:
        task_id = record["task_id"]
        temporal = index.get(task_id)
        if temporal is None:
            skipped += 1
            continue
        band = temporal["paper_band"]
        band_counts[band] += 1
        if band not in {"T1", "T2"}:
            continue
        origin = temporal.get("forecast_origin")
        expected = t1_cutoff if band == "T1" else t2_cutoff
        # Allow panel rows whose origin equals the configured cutoff.
        if origin not in {t1_cutoff, t2_cutoff}:
            continue
        if band == "T1" and origin != t1_cutoff:
            continue
        if band == "T2" and origin != t2_cutoff:
            continue
        market = str((record.get("metadata") or {}).get("market") or (record.get("seed") or {}).get("market") or "")
        cells[band][cell_key(task_id, market)] += 1

    all_keys = sorted(set(cells["T1"]) | set(cells["T2"]))
    diffs: list[dict[str, Any]] = []
    for key in all_keys:
        c1 = cells["T1"][key]
        c2 = cells["T2"][key]
        diff = abs(c1 - c2)
        if diff > max_diff or c1 == 0 or c2 == 0:
            diffs.append(
                {
                    "cell": {"family": key[0], "market": key[1], "bucket": key[2]},
                    "T1": c1,
                    "T2": c2,
                    "abs_diff": diff,
                }
            )

    report = {
        "panel_id": config["panel_id"],
        "t1_cutoff": t1_cutoff,
        "t2_cutoff": t2_cutoff,
        "max_count_diff_per_cell": max_diff,
        "seed_records": len(records),
        "indexed_skipped": skipped,
        "by_paper_band": dict(band_counts),
        "t1_cells": len(cells["T1"]),
        "t2_cells": len(cells["T2"]),
        "failing_cells": diffs,
        "ok": len(diffs) == 0 and band_counts.get("T1", 0) > 0 and band_counts.get("T2", 0) > 0,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
