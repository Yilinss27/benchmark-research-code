#!/usr/bin/env python3
"""Validate T1/T2 structural symmetry for an aligned panel."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
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


def task_family(record: dict[str, Any]) -> str:
    """Return the configured task family."""
    if record.get("category") == "A1":
        return "A1"
    return f"A2-{record.get('variant')}"


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

    cutoff_pairs = config.get("cutoff_pairs") or [
        {"pair_id": "p01", **config["cutoffs"]}
    ]
    pair_by_cutoff = {
        str(pair[band]): (str(pair["pair_id"]), band)
        for pair in cutoff_pairs
        for band in ("T1", "T2")
    }
    max_diff = int(config.get("symmetry", {}).get("max_count_diff_per_cell", 2))
    min_cumulative = int(
        config.get("symmetry", {}).get("min_cumulative_per_market_task", 0)
    )
    min_gap = int(
        config.get("symmetry", {}).get("min_cutoff_gap_days_same_band", 0)
    )

    cells: dict[tuple[str, str], Counter[tuple[str, str, str]]] = defaultdict(Counter)
    pairing_sets: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    cumulative: Counter[tuple[str, str, str]] = Counter()
    band_counts: Counter[str] = Counter()
    skipped = 0
    temporal_errors: list[str] = []
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
        cutoff = str((record.get("seed") or {}).get("cutoff_date") or record.get("cutoff_date"))
        expected_pair = pair_by_cutoff.get(cutoff)
        if expected_pair is None:
            temporal_errors.append(f"{task_id}: cutoff {cutoff} is not configured")
            continue
        pair_id, expected_band = expected_pair
        if band != expected_band:
            temporal_errors.append(
                f"{task_id}: expected {expected_band} for {pair_id}, got {band}"
            )
            continue
        metadata_pair = str((record.get("metadata") or {}).get("panel_pair_id") or "")
        if metadata_pair != pair_id:
            temporal_errors.append(
                f"{task_id}: metadata pair {metadata_pair!r} != {pair_id}"
            )
        market = str((record.get("metadata") or {}).get("market") or (record.get("seed") or {}).get("market") or "")
        cells[(pair_id, band)][cell_key(task_id, market)] += 1
        family = task_family(record)
        cumulative[(band, family, market)] += 1
        if family == "A1":
            pairing_sets[(pair_id, band, family, market)].add(
                str((record.get("seed") or {}).get("stock_code"))
            )
        else:
            seed = record.get("seed") or {}
            cohort = task_id.split("-")[-1]
            stock_codes = ",".join(
                sorted(str(item.get("code")) for item in seed.get("stock_list", []))
            )
            pairing_sets[(pair_id, band, f"{family}:{cohort}", market)].add(
                stock_codes
            )

    diffs: list[dict[str, Any]] = []
    pairing_errors: list[dict[str, Any]] = []
    for pair in cutoff_pairs:
        pair_id = str(pair["pair_id"])
        all_keys = sorted(set(cells[(pair_id, "T1")]) | set(cells[(pair_id, "T2")]))
        for key in all_keys:
            c1 = cells[(pair_id, "T1")][key]
            c2 = cells[(pair_id, "T2")][key]
            diff = abs(c1 - c2)
            if diff > max_diff or c1 == 0 or c2 == 0:
                diffs.append(
                    {
                        "pair_id": pair_id,
                        "cell": {"family": key[0], "market": key[1], "bucket": key[2]},
                        "T1": c1,
                        "T2": c2,
                        "abs_diff": diff,
                    }
                )
        pairing_keys = {
            (family, market)
            for pid, _, family, market in pairing_sets
            if pid == pair_id
        }
        for family, market in sorted(pairing_keys):
            left = pairing_sets.get((pair_id, "T1", family, market), set())
            right = pairing_sets.get((pair_id, "T2", family, market), set())
            if left != right:
                pairing_errors.append(
                    {
                        "pair_id": pair_id,
                        "family": family,
                        "market": market,
                        "T1_only": sorted(left - right),
                        "T2_only": sorted(right - left),
                    }
                )

    cumulative_failures = []
    for family in config["tasks"]:
        for market in config["markets"]:
            t1 = cumulative[("T1", family, market)]
            t2 = cumulative[("T2", family, market)]
            if min(t1, t2) < min_cumulative:
                cumulative_failures.append(
                    {"family": family, "market": market, "T1": t1, "T2": t2}
                )

    gap_failures = []
    for band in ("T1", "T2"):
        ordered = sorted(date.fromisoformat(str(pair[band])) for pair in cutoff_pairs)
        for previous, current in zip(ordered, ordered[1:]):
            if (current - previous).days < min_gap:
                gap_failures.append(
                    {
                        "band": band,
                        "previous": previous.isoformat(),
                        "current": current.isoformat(),
                        "gap_days": (current - previous).days,
                    }
                )

    report = {
        "panel_id": config["panel_id"],
        "cutoff_pairs": cutoff_pairs,
        "max_count_diff_per_cell": max_diff,
        "seed_records": len(records),
        "indexed_skipped": skipped,
        "by_paper_band": dict(band_counts),
        "failing_cells": diffs,
        "pairing_errors": pairing_errors,
        "cumulative_failures": cumulative_failures,
        "gap_failures": gap_failures,
        "temporal_errors": temporal_errors,
        "ok": not any(
            (diffs, pairing_errors, cumulative_failures, gap_failures, temporal_errors)
        )
        and band_counts.get("T1", 0) > 0
        and band_counts.get("T2", 0) > 0,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
