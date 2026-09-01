#!/usr/bin/env python3
"""Align C-task T1/T2 pairs: re-cut 2025-06-06 overlap rows to T1 @ 2023-12-29.

HF pin 941370f ships 294 C records, all T2 (cutoffs 2025-06-06 / 2025-12-31 / 2026-01-30).
86 stock×metric pairs appear at both 2025-06-06 and 2025-12-31; this script converts the
2025-06-06 copy to T1 (forecast origin 2023-12-29, outcome before 2024-06-30 when filings
exist) while keeping task_id unchanged and linking to the 2025-12-31 T2 anchor via metadata.

Pairing rule (see docs/t1_t2_alignment_gaps.md): T1 cutoff 2023-12-29 ↔ T2 anchor 2025-12-31.
The 36 CN_A-only extras at 2025-06-06 and all 2026-01-30 rows stay T2.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.assign_time_bands import update_row as update_temporal_band
from src.builders.c_financial_metric_from_csv_builder import build_record as build_c_record
from src.data.universe import currency_for_market
from src.data_generator import read_c_prompt
from src.data.yahoo_fundamentals import YahooFundamentals

T1_CUTOFF = "2023-12-29"
T2_ANCHOR_CUTOFF = "2025-12-31"
OVERLAP_SOURCE_CUTOFF = "2025-06-06"
DEFAULT_TRAINING_CUTOFF = "2024-06-30"
DEFAULT_CURRENT_DATE = "2026-08-17"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="seeds/c_financial_metric.jsonl")
    parser.add_argument("--output", default=None, help="Output path (default: overwrite --seed)")
    parser.add_argument("--t1-cutoff", default=T1_CUTOFF)
    parser.add_argument("--t2-anchor-cutoff", default=T2_ANCHOR_CUTOFF)
    parser.add_argument("--overlap-source-cutoff", default=OVERLAP_SOURCE_CUTOFF)
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing")
    parser.add_argument(
        "--reassign-bands",
        action="store_true",
        help="Run assign_time_bands.py --in-place after conversion",
    )
    parser.add_argument("--training-cutoff", default=DEFAULT_TRAINING_CUTOFF)
    parser.add_argument("--current-date", default=DEFAULT_CURRENT_DATE)
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _cutoff(record: dict[str, Any]) -> str:
    return str(record.get("cutoff_date") or (record.get("seed") or {}).get("cutoff_date") or "")


def _stock_metric_key(record: dict[str, Any]) -> tuple[str, str, str]:
    seed = record.get("seed") or {}
    return (
        str(seed.get("market") or (record.get("metadata") or {}).get("market") or "CN_A"),
        str(seed.get("stock_code") or ""),
        str(seed.get("metric_name") or ""),
    )


def _overlap_keys(rows: list[dict[str, Any]], left: str, right: str) -> set[tuple[str, str, str]]:
    by_cutoff: dict[str, set[tuple[str, str, str]]] = {}
    for row in rows:
        cutoff = _cutoff(row)
        by_cutoff.setdefault(cutoff, set()).add(_stock_metric_key(row))
    return by_cutoff.get(left, set()) & by_cutoff.get(right, set())


def _rebuild_t1_record(
    old: dict[str, Any],
    *,
    t1_cutoff: str,
    t2_task_id: str,
    fund: YahooFundamentals,
    template: str,
) -> tuple[dict[str, Any] | None, str | None]:
    seed = old.get("seed") or {}
    market = str(seed.get("market") or (old.get("metadata") or {}).get("market") or "CN_A")
    code = str(seed.get("stock_code") or "")
    metric = str(seed.get("metric_name") or "")
    name = str(seed.get("stock_name") or "")

    try:
        pair = fund.metric_pair(code, market, t1_cutoff, metric)
    except Exception as exc:
        return None, f"metric_pair error: {exc}"
    if pair is None:
        return None, "no public hist/future pair at T1 cutoff"

    row = {
        "task_id": old["task_id"],
        "stock_code": code,
        "stock_name": name,
        "cutoff_date": t1_cutoff,
        "metric_name": metric,
        "report_period_historical": pair["report_period_historical"],
        "historical_value": f"{pair['historical_value']:.4f}",
        "report_period_future": pair["report_period_future"],
        "future_value": f"{pair['future_value']:.4f}",
    }
    rebuilt = build_c_record(
        row,
        template,
        "yahoo",
        market=market,
        currency=currency_for_market(market),
    )
    metadata = dict(old.get("metadata") or {})
    metadata.update(rebuilt.get("metadata") or {})
    metadata["fundamentals_source"] = "YahooFundamentals"
    metadata["fundamentals_source_tier"] = "research_yahoo"
    metadata["track"] = "research_yahoo"
    metadata["statement_freq"] = pair.get("statement_freq", "quarterly")
    metadata["t1_t2_pair"] = {
        "t1_cutoff": t1_cutoff,
        "t2_cutoff": T2_ANCHOR_CUTOFF,
        "t2_task_id": t2_task_id,
        "stock_metric_key": [market, code, metric],
    }
    rebuilt["metadata"] = metadata
    rebuilt = update_temporal_band(rebuilt, DEFAULT_TRAINING_CUTOFF, DEFAULT_CURRENT_DATE)
    return rebuilt, None


def main() -> int:
    args = parse_args()
    seed_path = ROOT / args.seed
    output_path = Path(args.output) if args.output else seed_path
    rows = _load_jsonl(seed_path)
    if not rows:
        print(json.dumps({"error": f"no records in {seed_path}"}, ensure_ascii=False))
        return 1

    overlap = _overlap_keys(rows, args.overlap_source_cutoff, args.t2_anchor_cutoff)
    t2_by_key = {
        _stock_metric_key(row): row
        for row in rows
        if _cutoff(row) == args.t2_anchor_cutoff
    }

    fund = YahooFundamentals()
    template = read_c_prompt()
    converted: list[str] = []
    skipped: list[dict[str, str]] = []
    out_rows: list[dict[str, Any]] = []

    for row in rows:
        cutoff = _cutoff(row)
        key = _stock_metric_key(row)
        if cutoff == args.overlap_source_cutoff and key in overlap:
            t2_anchor = t2_by_key.get(key)
            if t2_anchor is None:
                skipped.append({"task_id": row["task_id"], "reason": "missing T2 anchor"})
                out_rows.append(row)
                continue
            rebuilt, err = _rebuild_t1_record(
                row,
                t1_cutoff=args.t1_cutoff,
                t2_task_id=str(t2_anchor["task_id"]),
                fund=fund,
                template=template,
            )
            if rebuilt is None:
                skipped.append({"task_id": row["task_id"], "reason": err or "unknown"})
                out_rows.append(row)
                continue
            out_rows.append(rebuilt)
            converted.append(row["task_id"])
        else:
            out_rows.append(row)

    summary = {
        "input_records": len(rows),
        "overlap_pairs": len(overlap),
        "converted_to_t1": len(converted),
        "skipped": len(skipped),
        "t1_cutoff": args.t1_cutoff,
        "t2_anchor_cutoff": args.t2_anchor_cutoff,
        "converted_task_ids": converted,
        "skipped_details": skipped,
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0 if not skipped else 1

    _write_jsonl(output_path, out_rows)

    if args.reassign_bands:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "assign_time_bands.py"),
                "--training-cutoff",
                args.training_cutoff,
                "--current-date",
                args.current_date,
                "--in-place",
            ],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode

    return 0 if not skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
