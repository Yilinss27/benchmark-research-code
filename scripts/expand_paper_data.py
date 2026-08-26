#!/usr/bin/env python3
"""Expand paper-ready data: A1 T1, A2 cohorts, and forward T3 seeds."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.assign_time_bands import update_row as update_temporal_band
from src.builders.c_financial_metric_from_csv_builder import _read_prompt_template as read_c_prompt
from src.data.universe import A1_UNIVERSE, C_METRICS
from src.data_generator import generate
from src.temporal.paper_bands import DEFAULT_EXPERIMENT_CONFIG

A1_T1_CUTOFFS = [
    "2022-06-30",
    "2022-12-30",
    "2023-03-31",
    "2023-06-30",
    "2023-09-29",
    "2023-12-29",
    "2024-03-29",
]

A2_CUTOFFS = [
    "2019-06-28",
    "2020-03-31",
    "2020-12-31",
    "2021-06-30",
    "2022-03-31",
    "2022-12-30",
    "2023-03-31",
    "2023-06-30",
    "2023-09-29",
    "2023-12-29",
    "2024-03-29",
    "2024-07-15",
    "2024-12-31",
    "2025-03-31",
    "2025-06-06",
    "2025-09-30",
    "2025-12-31",
    "2026-01-30",
    "2026-03-31",
    "2026-06-01",
]

T3_ORIGIN = DEFAULT_EXPERIMENT_CONFIG.experiment_as_of
T3_CUTOFFS = ["2026-08-20", "2026-09-15", "2026-10-31"]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Expand paper temporal datasets.")
    parser.add_argument("--a1-t1", action="store_true", help="Expand A1 paper T1 cutoffs.")
    parser.add_argument("--a2-all", action="store_true", help="Expand A2-F/T/H across cutoffs.")
    parser.add_argument("--t3-forward", action="store_true", help="Create forward T3 seed file.")
    parser.add_argument("--b-earnings", action="store_true", help="Expand B earnings across T1/T2 cutoffs.")
    parser.add_argument(
        "--aligned-panel",
        action="store_true",
        help="Generate configs/aligned_panel_v1 into seeds/aligned (does not touch main seeds).",
    )
    parser.add_argument("--all", action="store_true", help="Run all expansion steps.")
    return parser.parse_args()


def _assign(path: Path, records: list[dict[str, Any]]) -> None:
    """Rewrite a seed file with temporal bands assigned."""
    assigned = [
        update_temporal_band(record, "2024-06-30", "2026-08-08")
        for record in records
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in assigned:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def expand_a1_t1(root: Path) -> dict[str, Any]:
    """Generate additional A1 records for paper T1 windows."""
    output = root / "seeds/a1_valuation.jsonl"
    summaries = []
    for cutoff in A1_T1_CUTOFFS:
        for market in ("CN_A", "US", "HK"):
            summary = generate(
                "A1",
                market,
                cutoff,
                output=output,
                append=True,
                training_cutoff="2024-06-30",
                current_date="2026-08-08",
            )
            summaries.append(summary)
    return {"step": "a1_t1", "jobs": summaries}


def expand_a2_all(root: Path) -> dict[str, Any]:
    """Generate A2-F/T/H across historical cutoffs."""
    outputs = {
        "A2-F": root / "seeds/a2_fundamentals.jsonl",
        "A2-T": root / "seeds/a2_technical.jsonl",
        "A2-H": root / "seeds/a2_hybrid.jsonl",
    }
    summaries = []
    for cutoff in A2_CUTOFFS:
        for task, output in outputs.items():
            for market in ("CN_A", "US", "HK"):
                summary = generate(
                    task,
                    market,
                    cutoff,
                    output=output,
                    append=True,
                    replace=True,
                    training_cutoff="2024-06-30",
                    current_date="2026-08-08",
                )
                summaries.append(summary)
    return {"step": "a2_all", "jobs": summaries}


def build_t3_forward(root: Path) -> dict[str, Any]:
    """Create forward-looking T3 C-task template seeds with pending outcomes."""
    output = root / "seeds/t3_forward.jsonl"
    template = read_c_prompt()
    records: list[dict[str, Any]] = []
    index = 1
    currency_map = {"CN_A": "CNY", "US": "USD", "HK": "HKD"}
    for cutoff in T3_CUTOFFS:
        for market, names in A1_UNIVERSE.items():
            subset = names[:8] if market == "CN_A" else names
            for item in subset:
                for metric in C_METRICS:
                    compact = cutoff.replace("-", "")
                    code = item["stock_code"]
                    task_id = f"T3C-{market}-{compact}-{code}-{metric}-{index:04d}"
                    historical_financials = f"{cutoff}：{metric} = pending"
                    prompt = template
                    prompt = prompt.replace("{stock_name}", item["stock_name"])
                    prompt = prompt.replace("{cutoff_date}", cutoff)
                    prompt = prompt.replace("{metric_name}", metric)
                    prompt = prompt.replace("{historical_financials}", historical_financials)
                    prompt = prompt.replace("{third_party_info}", "无")
                    record = {
                        "task_id": task_id,
                        "category": "C",
                        "variant": None,
                        "cutoff_date": cutoff,
                        "time_band": "T3",
                        "status": "template",
                        "seed": {
                            "stock_code": code,
                            "stock_name": item["stock_name"],
                            "cutoff_date": cutoff,
                            "metric_name": metric,
                            "report_period_historical": cutoff,
                            "historical_value": None,
                            "report_period_future": "pending",
                            "historical_financials": historical_financials,
                            "third_party_info": "无",
                            "market": market,
                            "currency": currency_map[market],
                        },
                        "prompt": prompt,
                        "expected_output": {"predicted_value": "float"},
                        "ground_truth": None,
                        "metadata": {
                            "source": "t3_forward_builder",
                            "is_template": True,
                            "builder_version": "t3_forward_v1",
                            "t3_forward": True,
                            "outcome_status": "pending",
                            "market": market,
                            "currency": currency_map[market],
                        },
                    }
                    record = update_temporal_band(record, "2024-06-30", "2026-08-08")
                    records.append(record)
                    index += 1
    _assign(output, records)
    return {"step": "t3_forward", "records_written": len(records), "output": str(output)}


def expand_b_earnings(root: Path) -> dict[str, Any]:
    """Regenerate B earnings for expanded universe and T1/T2 anchors."""
    output = root / "seeds/b_event.jsonl"
    summaries = []
    for cutoff in ("2023-12-29", "2024-07-15", "2025-06-06", "2026-01-30"):
        for market in ("CN_A", "US", "HK"):
            summary = generate(
                "B",
                market,
                cutoff,
                output=output,
                append=True,
                training_cutoff="2024-06-30",
                current_date="2026-08-08",
            )
            summaries.append(summary)
    return {"step": "b_earnings", "jobs": summaries}


def expand_aligned_panel(root: Path) -> dict[str, Any]:
    """Generate the cross-time aligned A1/A2 panel without touching main seeds."""
    from scripts.generate_aligned_panel import load_config
    from src.data_generator import generate_panel

    config = load_config(root / "configs/aligned_panel_v1.json")
    output_dir = root / config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for cutoff in (config["cutoffs"]["T1"], config["cutoffs"]["T2"]):
        jobs.append(
            generate_panel(
                cutoff,
                markets=config["markets"],
                tasks=config["tasks"],
                horizon_days=int(config["horizon_days"]),
                provider_name=config.get("provider", "yahoo"),
                output_dir=output_dir,
                panel_id=config["panel_id"],
                append=True,
                replace=True,
            )
        )
    return {"step": "aligned_panel", "jobs": jobs}


def main() -> int:
    """Run selected expansion steps."""
    args = parse_args()
    root = ROOT
    run_all = args.all
    reports: list[dict[str, Any]] = []
    if run_all or args.a1_t1:
        reports.append(expand_a1_t1(root))
    if run_all or args.a2_all:
        reports.append(expand_a2_all(root))
    if run_all or args.t3_forward:
        reports.append(build_t3_forward(root))
    if run_all or args.b_earnings:
        reports.append(expand_b_earnings(root))
    if args.aligned_panel:
        reports.append(expand_aligned_panel(root))
    if not reports:
        print("No steps selected. Use --all or individual flags.")
        return 1
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
