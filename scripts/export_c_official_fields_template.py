#!/usr/bin/env python3
"""Export a fill-in template for CN/HK official C metric fields."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PERIODIC_FORMS = {"annual", "interim", "quarterly", "10-Q", "10-K"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="seeds/c_financial_metric.jsonl")
    parser.add_argument("--registry", default="configs/official_disclosures_v1.jsonl")
    parser.add_argument(
        "--output",
        default="data/c_official_fields_template.csv",
        help="Output CSV to fill operating_revenue/net_profit.",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _pick_periodic_row(rows: list[dict], market: str, stock: str, period: str) -> dict | None:
    matches = [
        row
        for row in rows
        if str(row.get("market")) == market
        and str(row.get("stock_code")) == stock
        and str(row.get("report_period")) == period
        and str(row.get("form_type") or "") in PERIODIC_FORMS
    ]
    if not matches:
        return None
    return min(matches, key=lambda item: str(item.get("published_at") or "9999-99-99"))


def main() -> int:
    args = parse_args()
    seed_rows = _load_jsonl(Path(args.seed))
    registry_rows = _load_jsonl(Path(args.registry))

    keys: set[tuple[str, str, str]] = set()
    for row in seed_rows:
        if row.get("category") != "C":
            continue
        seed = row.get("seed") or {}
        market = str(seed.get("market") or "")
        if market not in {"CN_A", "HK"}:
            continue
        keys.add((market, str(seed.get("stock_code") or ""), str(seed.get("report_period_future") or "")))

    output_rows: list[dict[str, str]] = []
    missing_disclosure = 0
    already_filled = 0
    for market, stock, period in sorted(keys):
        disclosure = _pick_periodic_row(registry_rows, market, stock, period)
        if disclosure is None:
            output_rows.append(
                {
                    "market": market,
                    "stock_code": stock,
                    "report_period": period,
                    "published_at": "",
                    "form_type": "",
                    "source_url": "",
                    "operating_revenue": "",
                    "net_profit": "",
                    "status": "missing_disclosure",
                    "notes": "registry中无对应periodic行，需先补官方披露记录",
                }
            )
            missing_disclosure += 1
            continue

        fields = disclosure.get("fields") if isinstance(disclosure.get("fields"), dict) else {}
        op = fields.get("operating_revenue")
        np = fields.get("net_profit")
        if op is not None and np is not None:
            already_filled += 1
        output_rows.append(
            {
                "market": market,
                "stock_code": stock,
                "report_period": period,
                "published_at": str(disclosure.get("published_at") or "")[:10],
                "form_type": str(disclosure.get("form_type") or ""),
                "source_url": str(disclosure.get("source_url") or ""),
                "operating_revenue": "" if op is None else str(op),
                "net_profit": "" if np is None else str(np),
                "status": "fill_required" if (op is None or np is None) else "already_filled",
                "notes": "",
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "market",
                "stock_code",
                "report_period",
                "published_at",
                "form_type",
                "source_url",
                "operating_revenue",
                "net_profit",
                "status",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(output_rows)

    print(
        json.dumps(
            {
                "output": str(output_path),
                "rows": len(output_rows),
                "missing_disclosure": missing_disclosure,
                "already_filled": already_filled,
                "fill_required": len(output_rows) - missing_disclosure - already_filled,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
