#!/usr/bin/env python3
"""Generate paired T1/T2 A1 and A2-T records across CN_A / US / HK."""

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

from src.data_generator import generate


T1_CUTOFF = "2023-12-29"
T2_CUTOFF = "2026-01-30"
A1_OUTPUT = "seeds/a1_valuation.jsonl"
A2T_OUTPUT = "seeds/a2_technical.jsonl"
DEFAULT_TRAINING_CUTOFF = "2024-06-01"
DEFAULT_CURRENT_DATE = "2026-08-08"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate paired T1/T2 A1 and A2-T seeds.")
    parser.add_argument("--t1-cutoff", default=T1_CUTOFF, help="T1 cutoff date.")
    parser.add_argument("--t2-cutoff", default=T2_CUTOFF, help="T2 cutoff date.")
    parser.add_argument("--provider", default="yahoo", help="Price provider.")
    parser.add_argument(
        "--training-cutoff",
        default=DEFAULT_TRAINING_CUTOFF,
        help="Model training cutoff for time_band assignment.",
    )
    parser.add_argument(
        "--current-date",
        default=DEFAULT_CURRENT_DATE,
        help="Reference current date for time_band assignment.",
    )
    parser.add_argument("--skip-validate", action="store_true", help="Skip validate.py after generation.")
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL rows."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write JSONL rows."""
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def backfill_legacy_market(path: Path, default_market: str = "CN_A", default_currency: str = "CNY") -> int:
    """Fill market/currency on older records that predate those fields."""
    rows = _load_jsonl(path)
    changed = 0
    for row in rows:
        seed = row.setdefault("seed", {})
        metadata = row.setdefault("metadata", {})
        if not seed.get("market"):
            seed["market"] = default_market
            changed += 1
        if not seed.get("currency"):
            seed["currency"] = default_currency
            changed += 1
        if not metadata.get("market"):
            metadata["market"] = seed["market"]
        if not metadata.get("currency"):
            metadata["currency"] = seed["currency"]
    if changed:
        _write_jsonl(path, rows)
    return changed


def main() -> int:
    """Generate T1/T2 pairs, assign time bands, and validate."""
    args = parse_args()
    root = ROOT
    a1_path = root / A1_OUTPUT
    a2_path = root / A2T_OUTPUT

    backfilled = {
        A1_OUTPUT: backfill_legacy_market(a1_path),
        A2T_OUTPUT: backfill_legacy_market(a2_path),
    }

    jobs = []
    for cutoff in (args.t1_cutoff, args.t2_cutoff):
        for market in ("CN_A", "US", "HK"):
            jobs.append(("A1", market, cutoff, a1_path))
        for market in ("CN_A", "US", "HK"):
            jobs.append(("A2-T", market, cutoff, a2_path))

    summaries: list[dict[str, Any]] = []
    for task, market, cutoff, output in jobs:
        summary = generate(
            task,
            market,
            cutoff,
            provider_name=args.provider,
            output=output,
            append=True,
            training_cutoff=args.training_cutoff,
            current_date=args.current_date,
        )
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)

    assign = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "assign_time_bands.py"),
            "--training-cutoff",
            args.training_cutoff,
            "--current-date",
            args.current_date,
            "--in-place",
        ],
        cwd=root,
        check=False,
    )
    validate_code = 0
    if not args.skip_validate:
        validate = subprocess.run(
            [sys.executable, str(root / "scripts" / "validate.py")],
            cwd=root,
            check=False,
        )
        validate_code = validate.returncode

    report = {
        "backfilled_fields": backfilled,
        "jobs": summaries,
        "added_total": sum(item["added"] for item in summaries),
        "assign_time_bands_exit": assign.returncode,
        "validate_exit": validate_code,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if assign.returncode != 0:
        return assign.returncode
    return validate_code


if __name__ == "__main__":
    raise SystemExit(main())
