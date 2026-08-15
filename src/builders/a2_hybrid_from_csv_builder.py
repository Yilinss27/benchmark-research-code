"""Build A2-H ready seeds from fundamentals snapshot and price-series CSV."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.builders.a2_fundamentals_loader import (
    MATCH_MODE_FALLBACK,
    MATCH_MODE_ON_OR_BEFORE,
    fundamentals_dict_from_match,
    load_fundamentals_history,
    resolve_fundamentals_path,
    select_fundamental_match,
)
from src.builders.a2_technical_metrics import (
    TECHNICAL_KEYS,
    TECHNICAL_METRICS_VERSION,
    compute_technical_dict,
    null_technical_keys,
)
from src.builders.a2_technicals_from_csv_builder import (
    _actual_ranking,
    _closes_for_technicals,
    _has_min_trading_days,
    load_price_series,
)


PROMPT_FALLBACK = """以下是 {industry_name} 行业 {n_stocks} 只股票，信息截止日期 {cutoff_date}。

【财务基本面指标】
{fundamentals_dict}

【技术指标（已预计算）】
{technical_dict}
（含：RSI-14、MACD histogram、20日价格动量、布林带 Z-score）

请综合上述信号，预测这 {n_stocks} 只股票未来 {prediction_window_days} 天收益率从高到低的排名，输出 JSON 数组（代码顺序即排名）：
["code_rank_1", "code_rank_2", ..., "code_rank_N"]

请严格输出 JSON，不要输出任何额外文字、解释或 markdown 代码块。
"""


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the A2-H builder."""
    parser = argparse.ArgumentParser(description="Build A2-H seeds from CSV files.")
    parser.add_argument(
        "--fundamentals-csv",
        default="data/a2_fundamentals_snapshot.csv",
        help="Fundamentals CSV path.",
    )
    parser.add_argument(
        "--price-series-csv",
        default="data/a2_price_series.csv",
        help="Price series CSV path.",
    )
    parser.add_argument(
        "--output",
        default="seeds/a2_hybrid.jsonl",
        help="Output JSONL path.",
    )
    return parser.parse_args()


def _read_prompt_template() -> str:
    """Load the A2-H prompt template or fall back to a built-in version."""
    template_path = Path(__file__).resolve().parents[2] / "prompts" / "a2_ranking_h.txt"
    if not template_path.exists():
        return PROMPT_FALLBACK
    return template_path.read_text(encoding="utf-8")


def _render_prompt(
    template: str,
    industry_name: str,
    n_stocks: int,
    cutoff_date: str,
    fundamentals_dict: dict[str, Any],
    technical_dict: dict[str, Any],
    prediction_window_days: int,
) -> str:
    """Render the A2-H prompt using the prompt template text."""
    rendered = template
    rendered = rendered.replace("{industry_name}", industry_name)
    rendered = rendered.replace("{N}", str(n_stocks))
    rendered = rendered.replace("{n_stocks}", str(n_stocks))
    rendered = rendered.replace("{cutoff_date}", cutoff_date)
    rendered = rendered.replace("{fundamentals_dict}", json.dumps(fundamentals_dict, ensure_ascii=False))
    rendered = rendered.replace("{technical_dict}", json.dumps(technical_dict, ensure_ascii=False))
    rendered = rendered.replace("{prediction_window_days}", str(prediction_window_days))
    return rendered


def build_records(
    cohorts: dict[str, dict[str, Any]],
    fundamentals_history: dict[str, list[dict[str, Any]]],
    prompt_template: str,
    fundamentals_source: str,
    price_source: str,
    *,
    market: str = "CN_A",
    currency: str = "CNY",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build A2-H records and collect warnings."""
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    record_index = 1

    for cohort_id, cohort in sorted(cohorts.items()):
        stock_items = list(cohort["stocks"].values())
        stock_list = [{"code": stock["code"], "name": stock["name"]} for stock in stock_items]

        fundamentals_dict: dict[str, dict[str, Any]] = {}
        technical_dict: dict[str, dict[str, float | None]] = {}
        actual_returns: dict[str, float] = {}
        missing_fundamentals: list[str] = []
        insufficient_history: list[str] = []
        missing_returns: list[str] = []
        null_metrics_by_stock: dict[str, list[str]] = {}
        fundamentals_match_by_stock: dict[str, dict[str, str]] = {}

        for stock in stock_items:
            code = stock["code"]
            if stock["actual_return"] is None:
                missing_returns.append(code)
                continue
            actual_returns[code] = float(stock["actual_return"])

            history = fundamentals_history.get(code, [])
            match = select_fundamental_match(history, cohort["cutoff_date"])
            if match is None:
                missing_fundamentals.append(code)
                warnings.append(f"Cohort {cohort_id} stock {code}: missing fundamentals snapshot")
                continue

            fundamentals_dict[code] = fundamentals_dict_from_match(match)
            fundamentals_match_by_stock[code] = {
                "snapshot_date": match.snapshot_date,
                "match_mode": match.match_mode,
            }
            if match.match_mode == MATCH_MODE_FALLBACK:
                warnings.append(
                    f"Cohort {cohort_id} stock {code}: prototype fallback; "
                    f"no fundamentals on/before {cohort['cutoff_date']}; used {match.snapshot_date}"
                )

            if not _has_min_trading_days(stock["prices"]):
                insufficient_history.append(code)
                warnings.append(f"Cohort {cohort_id} stock {code}: insufficient trading history")
                continue

            closes = _closes_for_technicals(stock["prices"])
            metrics = compute_technical_dict(closes)
            technical_dict[code] = metrics
            null_keys = null_technical_keys(metrics)
            if null_keys:
                null_metrics_by_stock[code] = null_keys
                warnings.append(f"Cohort {cohort_id} stock {code}: null technical metrics {null_keys}")

        match_modes = {item["match_mode"] for item in fundamentals_match_by_stock.values()}
        if MATCH_MODE_FALLBACK in match_modes and MATCH_MODE_ON_OR_BEFORE in match_modes:
            cohort_match_mode = "mixed"
        elif MATCH_MODE_FALLBACK in match_modes:
            cohort_match_mode = MATCH_MODE_FALLBACK
        elif match_modes:
            cohort_match_mode = MATCH_MODE_ON_OR_BEFORE
        else:
            cohort_match_mode = "missing"

        snapshot_dates = sorted({item["snapshot_date"] for item in fundamentals_match_by_stock.values()})
        fundamentals_snapshot_date = snapshot_dates[0] if len(snapshot_dates) == 1 else snapshot_dates

        status = "ready"
        ground_truth: dict[str, Any] | None
        if (
            missing_returns
            or missing_fundamentals
            or insufficient_history
            or len(actual_returns) != len(stock_list)
            or len(fundamentals_dict) != len(stock_list)
            or len(technical_dict) != len(stock_list)
        ):
            status = "input_ready"
            ground_truth = None
            warnings.append(
                f"Cohort {cohort_id} missing returns, fundamentals, or trading history; emitted as input_ready"
            )
        else:
            ordered_returns = {stock["code"]: actual_returns[stock["code"]] for stock in stock_items}
            ground_truth = {
                "actual_returns": ordered_returns,
                "actual_ranking": _actual_ranking(ordered_returns),
                "prediction_window_days": cohort["prediction_window_days"],
            }

        record = {
            "task_id": cohort.get("task_id") or f"A2H-{record_index:05d}",
            "category": "A2",
            "variant": "H",
            "cutoff_date": cohort["cutoff_date"],
            "time_band": "T2",
            "status": status,
            "seed": {
                "industry_name": cohort["industry_name"],
                "cutoff_date": cohort["cutoff_date"],
                "prediction_window_days": cohort["prediction_window_days"],
                "signal_variant": "H",
                "stock_list": stock_list,
                "fundamentals_dict": fundamentals_dict,
                "technical_dict": technical_dict,
                "market": market,
                "currency": currency,
            },
            "prompt": _render_prompt(
                prompt_template,
                industry_name=cohort["industry_name"],
                n_stocks=len(stock_list),
                cutoff_date=cohort["cutoff_date"],
                fundamentals_dict=fundamentals_dict,
                technical_dict=technical_dict,
                prediction_window_days=cohort["prediction_window_days"],
            ),
            "expected_output": {
                "ranking": "list[str], permutation of stock codes",
            },
            "ground_truth": ground_truth,
            "metadata": {
                "source": f"{fundamentals_source}+{price_source}",
                "is_template": False,
                "builder_version": "a2_hybrid_csv_builder_v2",
                "cohort_id": cohort_id,
                "technical_keys": list(TECHNICAL_KEYS),
                "technical_metrics_version": TECHNICAL_METRICS_VERSION,
                "technical_null_metrics": null_metrics_by_stock,
                "fundamentals_snapshot_date": fundamentals_snapshot_date,
                "fundamentals_match_mode": cohort_match_mode,
                "fundamentals_match_by_stock": fundamentals_match_by_stock,
                "market": market,
                "currency": currency,
            },
        }
        records.append(record)
        record_index += 1

    return records, warnings


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write records to JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    """Build A2-H seed records from local CSV files."""
    args = parse_args()
    fundamentals_path, path_warnings = resolve_fundamentals_path(args.fundamentals_csv)
    price_series_path = Path(args.price_series_csv)
    output_path = Path(args.output)

    if not price_series_path.exists():
        raise FileNotFoundError(f"Price series CSV not found: {price_series_path}")

    cohorts = load_price_series(price_series_path)
    fundamentals_history = load_fundamentals_history(fundamentals_path)
    prompt_template = _read_prompt_template()
    records, warnings = build_records(
        cohorts=cohorts,
        fundamentals_history=fundamentals_history,
        prompt_template=prompt_template,
        fundamentals_source=fundamentals_path.name,
        price_source=price_series_path.name,
    )
    warnings = path_warnings + warnings
    write_jsonl(output_path, records)

    fallback_cohorts = sum(
        1
        for record in records
        if record.get("metadata", {}).get("fundamentals_match_mode") == MATCH_MODE_FALLBACK
    )
    summary = {
        "fundamentals_csv": str(fundamentals_path),
        "price_series_csv": str(price_series_path),
        "output": str(output_path),
        "records_written": len(records),
        "ready_records": sum(1 for record in records if record["status"] == "ready"),
        "input_ready_records": sum(1 for record in records if record["status"] == "input_ready"),
        "prototype_fallback_cohorts": fallback_cohorts,
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
