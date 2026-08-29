#!/usr/bin/env python3
"""Bootstrap official disclosure fields for C from snapshot CSV values."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PERIODIC_FORMS = {"annual", "interim", "quarterly", "10-Q", "10-K"}
METRICS = {"operating_revenue", "net_profit"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/c_financial_snapshots.csv")
    parser.add_argument("--registry", default="configs/official_disclosures_v1.jsonl")
    return parser.parse_args()


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _load_registry(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry)
    rows = _load_registry(registry_path)
    csv_rows = _load_csv(Path(args.csv))

    values: dict[tuple[str, str, str, str], float] = {}
    for row in csv_rows:
        metric = str(row.get("metric_name") or "")
        if metric not in METRICS:
            continue
        stock = str(row.get("stock_code") or "")
        hist_p = str(row.get("report_period_historical") or "")
        fut_p = str(row.get("report_period_future") or "")
        hist_v = _as_float(str(row.get("historical_value") or ""))
        fut_v = _as_float(str(row.get("future_value") or ""))
        if hist_v is not None:
            values[("CN_A", stock, hist_p, metric)] = hist_v
        if fut_v is not None:
            values[("CN_A", stock, fut_p, metric)] = fut_v

    updated = 0
    touched = 0
    for row in rows:
        market = str(row.get("market") or "")
        stock = str(row.get("stock_code") or "")
        period = str(row.get("report_period") or "")
        form_type = str(row.get("form_type") or "")
        if form_type not in PERIODIC_FORMS:
            continue
        fields = dict(row.get("fields") or {})
        before = len(fields)
        for metric in METRICS:
            key = (market, stock, period, metric)
            if key in values and metric not in fields:
                fields[metric] = values[key]
        if len(fields) > before:
            row["fields"] = fields
            row["parser_version"] = "manual_official_registry_v1_bootstrap_from_c_csv"
            updated += len(fields) - before
            touched += 1

    registry_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "registry": str(registry_path),
                "rows_touched": touched,
                "field_values_written": updated,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
