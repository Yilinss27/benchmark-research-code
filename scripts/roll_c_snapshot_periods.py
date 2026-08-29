#!/usr/bin/env python3
"""Roll C snapshot CSV to latest available official filing periods."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

PERIODIC_FORMS = {"annual", "interim", "quarterly", "10-Q", "10-K"}
METRICS = {"operating_revenue", "net_profit"}
AS_OF_DEFAULT = "2026-08-17"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/c_financial_snapshots.csv")
    parser.add_argument("--registry", default="configs/official_disclosures_v1.jsonl")
    parser.add_argument("--as-of", default=AS_OF_DEFAULT)
    return parser.parse_args()


def _as_date(raw: str) -> date:
    return date.fromisoformat(raw[:10])


def _load_registry(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _latest_pair(
    rows: list[dict],
    *,
    market: str,
    stock_code: str,
    metric_name: str,
    as_of: date,
) -> tuple[dict, dict] | None:
    candidates = []
    for row in rows:
        if str(row.get("market")) != market or str(row.get("stock_code")) != stock_code:
            continue
        if str(row.get("form_type") or "") not in PERIODIC_FORMS:
            continue
        fields = row.get("fields")
        if not isinstance(fields, dict):
            continue
        metric_value = _to_float(fields.get(metric_name))
        published = str(row.get("published_at") or "")[:10]
        period = str(row.get("report_period") or "")[:10]
        if metric_value is None or not published or not period:
            continue
        try:
            published_d = _as_date(published)
            period_d = _as_date(period)
        except ValueError:
            continue
        if published_d > as_of:
            continue
        candidates.append((period_d, published_d, metric_value, row))
    if len(candidates) < 2:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    _, _, _, hist = candidates[-2]
    _, _, _, fut = candidates[-1]
    return hist, fut


def main() -> int:
    args = parse_args()
    as_of = _as_date(args.as_of)
    csv_path = Path(args.csv)
    registry_rows = _load_registry(Path(args.registry))
    csv_rows = _load_csv(csv_path)

    updated = 0
    unchanged = 0
    for row in csv_rows:
        metric = str(row.get("metric_name") or "")
        if metric not in METRICS:
            unchanged += 1
            continue
        pair = _latest_pair(
            registry_rows,
            market="CN_A",
            stock_code=str(row.get("stock_code") or ""),
            metric_name=metric,
            as_of=as_of,
        )
        if pair is None:
            unchanged += 1
            continue
        hist, fut = pair
        hist_fields = hist.get("fields") or {}
        fut_fields = fut.get("fields") or {}
        hist_value = _to_float(hist_fields.get(metric))
        fut_value = _to_float(fut_fields.get(metric))
        if hist_value is None or fut_value is None:
            unchanged += 1
            continue
        future_pub = _as_date(str(fut.get("published_at"))[:10])
        cutoff = future_pub - timedelta(days=1)
        row["cutoff_date"] = cutoff.isoformat()
        row["report_period_historical"] = str(hist.get("report_period"))[:10]
        row["historical_value"] = f"{hist_value:.4f}"
        row["report_period_future"] = str(fut.get("report_period"))[:10]
        row["future_value"] = f"{fut_value:.4f}"
        updated += 1

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(
        json.dumps(
            {
                "csv": str(csv_path),
                "updated_rows": updated,
                "unchanged_rows": unchanged,
                "as_of": args.as_of,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
