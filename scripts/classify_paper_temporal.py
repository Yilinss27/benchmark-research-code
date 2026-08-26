#!/usr/bin/env python3
"""Build task-temporal-index.jsonl and a paper-band summary report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.providers.yahoo import YahooPriceProvider
from src.data.yahoo_fundamentals import YahooFundamentals
from src.temporal.outcome_enrichment import enrich_b_outcome, enrich_c_outcome
from src.temporal.paper_bands import (
    DEFAULT_EXPERIMENT_CONFIG,
    PaperExperimentConfig,
    build_index_row,
    write_temporal_index,
)

READY_FILES = [
    "seeds/a1_valuation.jsonl",
    "seeds/a2_fundamentals.jsonl",
    "seeds/a2_technical.jsonl",
    "seeds/a2_hybrid.jsonl",
    "seeds/b_event.jsonl",
    "seeds/c_financial_metric.jsonl",
    "seeds/d_counterfactual.jsonl",
    "seeds/e_formula.jsonl",
]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Classify seeds into paper temporal bands.")
    parser.add_argument(
        "--output",
        default="data/task_temporal_index.jsonl",
        help="Output temporal index JSONL path.",
    )
    parser.add_argument(
        "--report",
        default="data/paper_temporal_report.json",
        help="Summary report JSON path.",
    )
    parser.add_argument(
        "--seed-dir",
        default=None,
        help="If set, classify all *.jsonl under this directory instead of default READY_FILES.",
    )
    parser.add_argument(
        "--training-cutoff",
        default=DEFAULT_EXPERIMENT_CONFIG.backbone_training_cutoff,
        help="Backbone training cutoff.",
    )
    parser.add_argument(
        "--guard-days",
        type=int,
        default=DEFAULT_EXPERIMENT_CONFIG.guard_days,
        help="Guard days around training cutoff.",
    )
    parser.add_argument(
        "--experiment-as-of",
        default=DEFAULT_EXPERIMENT_CONFIG.experiment_as_of,
        help="Experiment as-of date for T3 origin.",
    )
    parser.add_argument(
        "--enrich-yahoo",
        action="store_true",
        help="Use Yahoo to enrich B/C outcome_available_at.",
    )
    parser.add_argument(
        "--review-status",
        default="draft",
        choices=("draft", "reviewed"),
        help="Default review_status for generated rows.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL rows."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _enrich_record(
    record: dict[str, Any],
    *,
    enrich_yahoo: bool,
    price_provider: YahooPriceProvider | None,
    fundamentals: YahooFundamentals | None,
) -> dict[str, str | None]:
    """Optional Yahoo enrichment for B/C outcome dates."""
    if not enrich_yahoo:
        return {}
    category = record.get("category")
    if category == "B" and record.get("variant") == "earnings":
        return enrich_b_outcome(record, price_provider)
    if category == "C":
        return enrich_c_outcome(record, fundamentals)
    return {}


def main() -> int:
    """Generate temporal index and report."""
    args = parse_args()
    config = PaperExperimentConfig(
        backbone_training_cutoff=args.training_cutoff,
        guard_days=args.guard_days,
        experiment_as_of=args.experiment_as_of,
    )
    root = ROOT
    records: list[dict[str, Any]] = []
    if args.seed_dir:
        seed_dir = root / args.seed_dir
        paths = sorted(p for p in seed_dir.glob("*.jsonl") if p.name != "all.jsonl")
        if not paths:
            raise SystemExit(f"No JSONL files under {seed_dir}")
        for path in paths:
            records.extend(load_jsonl(path))
    else:
        for rel in READY_FILES:
            records.extend(load_jsonl(root / rel))

    price_provider = YahooPriceProvider() if args.enrich_yahoo else None
    fundamentals = YahooFundamentals() if args.enrich_yahoo else None

    index_rows: list[dict[str, Any]] = []
    for record in records:
        enrichment = _enrich_record(
            record,
            enrich_yahoo=args.enrich_yahoo,
            price_provider=price_provider,
            fundamentals=fundamentals,
        )
        index_rows.append(
            build_index_row(
                record,
                config=config,
                review_status=args.review_status,
                outcome_available_at=enrichment.get("outcome_available_at"),
                outcome_evidence_url=enrichment.get("outcome_evidence_url"),
                outcome_evidence_code=enrichment.get("outcome_evidence_code"),
            )
        )

    output_path = root / args.output
    report_path = root / args.report
    write_temporal_index(output_path, index_rows)

    by_band = Counter(row["paper_band"] for row in index_rows)
    by_category_band: dict[str, dict[str, int]] = {}
    for row in index_rows:
        key = row["category"]
        if row.get("variant"):
            key = f"{key}-{row['variant']}"
        by_category_band.setdefault(key, Counter())
        by_category_band[key][row["paper_band"]] += 1

    quality_counts = Counter(flag for row in index_rows for flag in row.get("quality_flags", []))
    report = {
        "config": {
            "backbone_training_cutoff": config.backbone_training_cutoff,
            "guard_days": config.guard_days,
            "experiment_as_of": config.experiment_as_of,
            "t1_outcome_max": config.t1_outcome_max,
            "t2_origin_min": config.t2_origin_min,
            "t2_outcome_max": config.t2_outcome_max,
        },
        "total_records": len(index_rows),
        "by_paper_band": dict(by_band),
        "by_category_band": {k: dict(v) for k, v in sorted(by_category_band.items())},
        "quality_flag_counts": dict(quality_counts),
        "output": str(output_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
