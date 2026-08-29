#!/usr/bin/env python3
"""Generate D counterfactual records from archetype templates + specs CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.assign_time_bands import update_row as update_temporal_band
from src.data.providers.yahoo import YahooPriceProvider
from src.data.universe import A1_UNIVERSE

DEFAULT_TRAINING_CUTOFF = "2024-06-30"
DEFAULT_CURRENT_DATE = "2026-08-17"
BENCHMARK_BY_MARKET = {"CN_A": "沪深300", "US": "S&P500", "HK": "恒生指数"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs", default="data/d_counterfactual_specs.csv")
    parser.add_argument("--archetypes", default="configs/d_event_archetypes_v1.json")
    parser.add_argument("--output", default="seeds/d_counterfactual.jsonl")
    parser.add_argument("--training-cutoff", default=DEFAULT_TRAINING_CUTOFF)
    parser.add_argument("--current-date", default=DEFAULT_CURRENT_DATE)
    return parser.parse_args()


def _read_prompt_template() -> str:
    return (ROOT / "prompts" / "d_counterfactual.txt").read_text(encoding="utf-8")


def _load_specs(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_archetypes(path: Path) -> dict[str, dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {x["archetype_id"]: x for x in payload["archetypes"]}


def _stock_name(market: str, stock_code: str) -> str:
    for row in A1_UNIVERSE[market]:
        if row["stock_code"] == stock_code:
            return row["stock_name"]
    return stock_code


def _render_news(template: str, spec: dict[str, str]) -> str:
    rendered = template
    for key in ("duration", "amount", "regulator", "pct"):
        value = spec.get(key) or "若干"
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _render_prompt(template: str, stock_name: str, prices: list[float], news: str) -> str:
    out = template.replace("{stock_name}", stock_name)
    out = out.replace("{historical_price_series}", str(prices))
    out = out.replace("{counterfactual_news}", news)
    return out


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    args = parse_args()
    specs = _load_specs(ROOT / args.specs)
    archetypes = _load_archetypes(ROOT / args.archetypes)
    prompt_template = _read_prompt_template()
    provider = YahooPriceProvider()
    records: list[dict[str, Any]] = []
    warnings: list[str] = []

    for idx, spec in enumerate(specs, 1):
        market = str(spec["market"])
        stock_code = str(spec["stock_code"])
        cutoff_date = str(spec["cutoff_date"])
        archetype_id = str(spec["archetype_id"])
        archetype = archetypes.get(archetype_id)
        if archetype is None:
            warnings.append(f"missing archetype: {archetype_id}")
            continue
        stock_name = _stock_name(market, stock_code)
        try:
            bars = provider.get_price_history(stock_code, market, "2023-01-01", cutoff_date)
        except Exception as exc:
            warnings.append(f"{market} {stock_code} {cutoff_date}: {exc}")
            continue
        series = [round(bar.close, 4) for bar in bars[-30:]]
        if len(series) < 30:
            warnings.append(f"{market} {stock_code} {cutoff_date}: only {len(series)} bars")
            continue
        direction = archetype["direction"]
        news = _render_news(archetype["template"], spec)
        row = {
            "task_id": f"D-{market}-{idx:05d}",
            "category": "D",
            "variant": None,
            "time_band": "T1",
            "status": "ready",
            "seed": {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "historical_price_series": series,
                "counterfactual_news": news,
                "expected_logic_direction": direction,
                "benchmark_id": BENCHMARK_BY_MARKET[market],
                "cutoff_date": cutoff_date,
                "market": market,
            },
            "prompt": _render_prompt(prompt_template, stock_name, series, news),
            "expected_output": {"direction": "positive|negative", "reasoning": "str"},
            "ground_truth": {"logic_direction": direction},
            "metadata": {
                "is_template": False,
                "prompt_template": "prompts/d_counterfactual.txt",
                "archetype_id": archetype_id,
                "generation_source": "configs/d_event_archetypes_v1.json + data/d_counterfactual_specs.csv",
                "market": market,
            },
        }
        records.append(update_temporal_band(row, args.training_cutoff, args.current_date))

    _write_jsonl(ROOT / args.output, records)
    print(
        json.dumps(
            {"output": args.output, "records": len(records), "warnings": warnings[:20]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
