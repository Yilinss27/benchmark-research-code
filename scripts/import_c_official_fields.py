#!/usr/bin/env python3
"""Import filled CN/HK official metric fields back into disclosure registry."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PERIODIC_FORMS = {"annual", "interim", "quarterly", "10-Q", "10-K"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/c_official_fields_template.csv")
    parser.add_argument("--registry", default="configs/official_disclosures_v1.jsonl")
    return parser.parse_args()


def _as_float(value: str) -> float | None:
    stripped = value.strip().replace(",", "")
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry)
    if not registry_path.exists():
        raise FileNotFoundError(f"Registry not found: {registry_path}")
    rows = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    with Path(args.input).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        filled = list(reader)

    updated = 0
    skipped = 0
    missing_registry = 0
    for item in filled:
        market = str(item.get("market") or "").strip()
        stock = str(item.get("stock_code") or "").strip()
        period = str(item.get("report_period") or "").strip()
        op = _as_float(str(item.get("operating_revenue") or ""))
        np = _as_float(str(item.get("net_profit") or ""))
        if op is None and np is None:
            skipped += 1
            continue
        candidates = [
            idx
            for idx, row in enumerate(rows)
            if str(row.get("market")) == market
            and str(row.get("stock_code")) == stock
            and str(row.get("report_period")) == period
            and str(row.get("form_type") or "") in PERIODIC_FORMS
        ]
        if not candidates:
            missing_registry += 1
            continue
        index = min(
            candidates,
            key=lambda idx: str(rows[idx].get("published_at") or "9999-99-99"),
        )
        target = dict(rows[index])
        fields = dict(target.get("fields") or {})
        if op is not None:
            fields["operating_revenue"] = op
        if np is not None:
            fields["net_profit"] = np
        target["fields"] = fields
        target["parser_version"] = "manual_official_registry_v1_c_fields_import"
        rows[index] = target
        updated += 1

    registry_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "registry": str(registry_path),
                "updated": updated,
                "skipped_empty": skipped,
                "missing_registry_rows": missing_registry,
                "input_rows": len(filled),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
