#!/usr/bin/env python3
"""Generate the aligned T1/T2 panel from configs/aligned_panel_v1.json."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_generator import generate_panel
from src.builders.a2_fundamentals_from_csv_builder import (
    _read_prompt_template as read_a2f_prompt,
    _render_prompt as render_a2f_prompt,
)
from src.builders.a2_hybrid_from_csv_builder import (
    _read_prompt_template as read_a2h_prompt,
    _render_prompt as render_a2h_prompt,
)
from src.builders.a2_technicals_from_csv_builder import (
    _read_prompt_template as read_a2t_prompt,
    _render_prompt as render_a2t_prompt,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Generate aligned_panel_v1 seeds.")
    parser.add_argument(
        "--config",
        default="configs/aligned_panel_v1.json",
        help="Panel config JSON path.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing output_dir before generation.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    """Load panel config."""
    return json.loads(path.read_text(encoding="utf-8"))


def _pairing_key(record: dict[str, Any]) -> tuple[str, str, str]:
    seed = record.get("seed") or {}
    market = str(seed.get("market") or (record.get("metadata") or {}).get("market"))
    if record.get("category") == "A1":
        return ("A1", market, str(seed.get("stock_code")))
    return (
        f"A2-{record.get('variant')}",
        market,
        str(record["task_id"]).split("-")[-1],
    )


def _normalize_a2(record: dict[str, Any], common_codes: set[str]) -> dict[str, Any]:
    """Restrict both sides of a pair to the same evaluable stock set."""
    seed = record["seed"]
    seed["stock_list"] = [
        item for item in seed["stock_list"] if str(item.get("code")) in common_codes
    ]
    for key in ("fundamentals_dict", "technical_dict"):
        if key in seed:
            seed[key] = {
                code: value
                for code, value in seed[key].items()
                if code in common_codes
            }
    ground_truth = record.get("ground_truth") or {}
    returns = {
        code: value
        for code, value in (ground_truth.get("actual_returns") or {}).items()
        if code in common_codes
    }
    ground_truth["actual_returns"] = returns
    ground_truth["actual_ranking"] = [
        code
        for code, _ in sorted(returns.items(), key=lambda item: (-item[1], item[0]))
    ]
    if ground_truth.get("forward_trading_days"):
        ground_truth["forward_trading_days"] = {
            code: day
            for code, day in ground_truth["forward_trading_days"].items()
            if code in common_codes
        }
        record["metadata"]["outcome_trading_day"] = max(
            ground_truth["forward_trading_days"].values(), default=None
        )
    record["ground_truth"] = ground_truth
    n_stocks = len(seed["stock_list"])
    window = int(seed["prediction_window_days"])
    if record["variant"] == "F":
        record["prompt"] = render_a2f_prompt(
            read_a2f_prompt(),
            seed["industry_name"],
            n_stocks,
            seed["cutoff_date"],
            seed["fundamentals_dict"],
            window,
        )
    elif record["variant"] == "T":
        record["prompt"] = render_a2t_prompt(
            read_a2t_prompt(),
            seed["industry_name"],
            n_stocks,
            seed["cutoff_date"],
            seed["technical_dict"],
            window,
        )
    else:
        record["prompt"] = render_a2h_prompt(
            read_a2h_prompt(),
            seed["industry_name"],
            n_stocks,
            seed["cutoff_date"],
            seed["fundamentals_dict"],
            seed["technical_dict"],
            window,
        )
    return record


def align_generated_pairs(
    output_dir: Path,
    cutoff_pairs: list[dict[str, Any]],
) -> dict[str, int]:
    """Drop one-sided cells and normalize paired A2 stock sets."""
    cutoff_map = {
        str(pair[band]): (str(pair["pair_id"]), band)
        for pair in cutoff_pairs
        for band in ("T1", "T2")
    }
    summary = {"dropped_unpaired": 0, "normalized_a2": 0}
    for path in sorted(output_dir.glob("*.jsonl")):
        if path.name == "all.jsonl":
            continue
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        grouped: dict[tuple[str, tuple[str, str, str]], dict[str, dict[str, Any]]] = {}
        for row in rows:
            cutoff = str(row.get("cutoff_date"))
            if cutoff not in cutoff_map:
                continue
            pair_id, band = cutoff_map[cutoff]
            grouped.setdefault((pair_id, _pairing_key(row)), {})[band] = row
        kept: list[dict[str, Any]] = []
        for sides in grouped.values():
            if set(sides) != {"T1", "T2"}:
                summary["dropped_unpaired"] += len(sides)
                continue
            left, right = sides["T1"], sides["T2"]
            if left.get("category") == "A2":
                left_codes = {
                    str(item.get("code")) for item in left["seed"]["stock_list"]
                }
                right_codes = {
                    str(item.get("code")) for item in right["seed"]["stock_list"]
                }
                common = left_codes & right_codes
                if len(common) < 6:
                    summary["dropped_unpaired"] += 2
                    continue
                if common != left_codes or common != right_codes:
                    left = _normalize_a2(left, common)
                    right = _normalize_a2(right, common)
                    summary["normalized_a2"] += 2
            kept.extend((left, right))
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept),
            encoding="utf-8",
        )
    return summary


def main() -> int:
    """Generate both cutoffs into seeds/aligned."""
    args = parse_args()
    config = load_config(ROOT / args.config)
    output_dir = ROOT / config["output_dir"]
    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cutoff_pairs = config.get("cutoff_pairs")
    if not cutoff_pairs:
        legacy = config["cutoffs"]
        cutoff_pairs = [{"pair_id": "p01", "T1": legacy["T1"], "T2": legacy["T2"]}]
    jobs = [
        (str(pair["pair_id"]), band, str(pair[band]))
        for pair in cutoff_pairs
        for band in ("T1", "T2")
    ]
    cutoffs = [cutoff for _, _, cutoff in jobs]
    if len(cutoffs) != len(set(cutoffs)):
        raise SystemExit("cutoff_pairs must not reuse a cutoff date")
    reports: list[dict[str, Any]] = []
    for pair_id, expected_band, cutoff in jobs:
        summary = generate_panel(
            cutoff,
            markets=config["markets"],
            tasks=config["tasks"],
            horizon_days=int(config["horizon_days"]),
            provider_name=config.get("provider", "yahoo"),
            output_dir=output_dir,
            panel_id=config["panel_id"],
            pair_id=pair_id,
            append=True,
            replace=True,
        )
        reports.append(summary)
        summary["pair_id"] = pair_id
        summary["expected_band"] = expected_band
        print(
            json.dumps(
                {
                    "cutoff_date": cutoff,
                    "pair_id": pair_id,
                    "expected_band": expected_band,
                    "generated_total": summary["generated_total"],
                    "added_total": summary["added_total"],
                },
                ensure_ascii=False,
            )
        )

    alignment_summary = align_generated_pairs(output_dir, cutoff_pairs)

    manifest_path = output_dir / "panel_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "config": config,
                "cutoffs": cutoffs,
                "cutoff_pairs": cutoff_pairs,
                "reports": reports,
                "alignment_summary": alignment_summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Combined seed file for runner smoke tests.
    combined = output_dir / "all.jsonl"
    chunks: list[str] = []
    for rel in config.get("outputs", {}).values():
        path = ROOT / rel
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if text and not text.endswith("\n"):
                text += "\n"
            chunks.append(text)
    combined.write_text("".join(chunks), encoding="utf-8")

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "cutoffs": cutoffs,
                "combined": str(combined),
                "alignment_summary": alignment_summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
