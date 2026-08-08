"""Build A2-T ready seeds from local price-series CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from src.builders.a2_technical_metrics import (
    LOOKBACK_TRADING_DAYS,
    MIN_TRADING_DAYS_FOR_READY,
    TECHNICAL_KEYS,
    TECHNICAL_METRICS_VERSION,
    compute_technical_dict,
    null_technical_keys,
)


PROMPT_FALLBACK = """以下是 {industry_name} 行业 {n_stocks} 只股票，信息截止日期 {cutoff_date}。

【技术指标（已预计算）】
{technical_dict}
（含：RSI-14、MACD histogram、20日价格动量、布林带 Z-score）

请综合上述信号，预测这 {n_stocks} 只股票未来 {prediction_window_days} 天收益率从高到低的排名，输出 JSON 数组（代码顺序即排名）：
["code_rank_1", "code_rank_2", ..., "code_rank_N"]

请严格输出 JSON，不要输出任何额外文字、解释或 markdown 代码块。
"""


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the A2-T builder."""
    parser = argparse.ArgumentParser(description="Build A2-T seeds from price-series CSV.")
    parser.add_argument(
        "--price-series-csv",
        default="data/a2_price_series.csv",
        help="Price series CSV path.",
    )
    parser.add_argument(
        "--output",
        default="seeds/a2_technical.jsonl",
        help="Output JSONL path.",
    )
    return parser.parse_args()


def _normalize_stock_code(value: str) -> str:
    """Normalize stock codes to 6-digit strings."""
    stripped = value.strip()
    if stripped.isdigit():
        return stripped.zfill(6)
    return stripped


def _read_prompt_template() -> str:
    """Load the A2-T prompt template or fall back to a built-in version."""
    template_path = Path(__file__).resolve().parents[2] / "prompts" / "a2_ranking_t.txt"
    if not template_path.exists():
        return PROMPT_FALLBACK
    return template_path.read_text(encoding="utf-8")


def _render_prompt(
    template: str,
    industry_name: str,
    n_stocks: int,
    cutoff_date: str,
    technical_dict: dict[str, Any],
    prediction_window_days: int,
) -> str:
    """Render the A2-T prompt using the prompt template text."""
    rendered = template
    rendered = rendered.replace("{industry_name}", industry_name)
    rendered = rendered.replace("{N}", str(n_stocks))
    rendered = rendered.replace("{n_stocks}", str(n_stocks))
    rendered = rendered.replace("{cutoff_date}", cutoff_date)
    rendered = rendered.replace("{technical_dict}", json.dumps(technical_dict, ensure_ascii=False))
    rendered = rendered.replace("{prediction_window_days}", str(prediction_window_days))
    return rendered


def _actual_ranking(actual_returns: dict[str, float]) -> list[str]:
    """Compute actual ranking from highest to lowest return."""
    return [
        code
        for code, _ in sorted(
            actual_returns.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def load_price_series(path: Path) -> dict[str, dict[str, Any]]:
    """Load price series rows grouped by cohort_id."""
    required = {
        "cohort_id",
        "industry_name",
        "cutoff_date",
        "prediction_window_days",
        "stock_code",
        "stock_name",
        "trading_day",
        "close_price",
        "actual_return",
    }
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("Price series CSV header is missing")
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Price series CSV missing required columns: {sorted(missing)}")

        grouped: dict[str, dict[str, Any]] = {}
        for row in reader:
            cohort_id = row["cohort_id"].strip()
            stock_code = _normalize_stock_code(row["stock_code"])
            cohort = grouped.setdefault(
                cohort_id,
                {
                    "cohort_id": cohort_id,
                    "industry_name": row["industry_name"].strip(),
                    "cutoff_date": row["cutoff_date"].strip(),
                    "prediction_window_days": int(row["prediction_window_days"]),
                    "stocks": {},
                },
            )
            stock = cohort["stocks"].setdefault(
                stock_code,
                {
                    "code": stock_code,
                    "name": row["stock_name"].strip(),
                    "prices": [],
                    "actual_return": None,
                },
            )
            stock["prices"].append(
                {
                    "trading_day": row["trading_day"].strip(),
                    "close_price": float(row["close_price"]),
                }
            )
            stock["actual_return"] = float(row["actual_return"])
    return grouped


def _closes_for_technicals(
    prices: list[dict[str, Any]],
    max_days: int = LOOKBACK_TRADING_DAYS,
) -> list[float]:
    """Return ascending closes using the last `max_days` trading days before cutoff."""
    ordered = sorted(prices, key=lambda item: item["trading_day"])
    tail = ordered[-max_days:]
    return [item["close_price"] for item in tail]


def _has_min_trading_days(prices: list[dict[str, Any]], min_days: int = MIN_TRADING_DAYS_FOR_READY) -> bool:
    """Check whether a stock has enough trading days for momentum_20d."""
    return len(prices) >= min_days


def build_records(
    cohorts: dict[str, dict[str, Any]],
    prompt_template: str,
    source_name: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build A2-T records and collect warnings."""
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    record_index = 1

    for cohort_id, cohort in sorted(cohorts.items()):
        stock_items = list(cohort["stocks"].values())
        stock_list = [{"code": stock["code"], "name": stock["name"]} for stock in stock_items]

        technical_dict: dict[str, dict[str, float | None]] = {}
        actual_returns: dict[str, float] = {}
        missing_returns: list[str] = []
        insufficient_history: list[str] = []
        null_metrics_by_stock: dict[str, list[str]] = {}

        for stock in stock_items:
            code = stock["code"]
            if stock["actual_return"] is None:
                missing_returns.append(code)
                continue
            actual_returns[code] = float(stock["actual_return"])

            if not _has_min_trading_days(stock["prices"]):
                insufficient_history.append(code)
                warnings.append(
                    f"Cohort {cohort_id} stock {code}: fewer than {MIN_TRADING_DAYS_FOR_READY} trading days"
                )
                continue

            closes = _closes_for_technicals(stock["prices"])
            metrics = compute_technical_dict(closes)
            technical_dict[code] = metrics
            null_keys = null_technical_keys(metrics)
            if null_keys:
                null_metrics_by_stock[code] = null_keys
                warnings.append(f"Cohort {cohort_id} stock {code}: null technical metrics {null_keys}")

        status = "ready"
        ground_truth: dict[str, Any] | None
        if (
            missing_returns
            or insufficient_history
            or len(actual_returns) != len(stock_list)
            or len(technical_dict) != len(stock_list)
        ):
            status = "input_ready"
            ground_truth = None
            warnings.append(
                f"Cohort {cohort_id} missing returns or insufficient trading history; emitted as input_ready"
            )
        else:
            ordered_returns = {stock["code"]: actual_returns[stock["code"]] for stock in stock_items}
            ground_truth = {
                "actual_returns": ordered_returns,
                "actual_ranking": _actual_ranking(ordered_returns),
                "prediction_window_days": cohort["prediction_window_days"],
            }

        record = {
            "task_id": f"A2T-{record_index:05d}",
            "category": "A2",
            "variant": "T",
            "time_band": "T2",
            "status": status,
            "seed": {
                "industry_name": cohort["industry_name"],
                "cutoff_date": cohort["cutoff_date"],
                "prediction_window_days": cohort["prediction_window_days"],
                "signal_variant": "T",
                "stock_list": stock_list,
                "technical_dict": technical_dict,
            },
            "prompt": _render_prompt(
                prompt_template,
                industry_name=cohort["industry_name"],
                n_stocks=len(stock_list),
                cutoff_date=cohort["cutoff_date"],
                technical_dict=technical_dict,
                prediction_window_days=cohort["prediction_window_days"],
            ),
            "expected_output": {
                "ranking": "list[str], permutation of stock codes",
            },
            "ground_truth": ground_truth,
            "metadata": {
                "source": source_name,
                "is_template": False,
                "builder_version": "a2_technicals_csv_builder_v1",
                "cohort_id": cohort_id,
                "technical_keys": list(TECHNICAL_KEYS),
                "technical_metrics_version": TECHNICAL_METRICS_VERSION,
                "technical_null_metrics": null_metrics_by_stock,
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
    """Build A2-T seed records from local price-series CSV."""
    args = parse_args()
    price_series_path = Path(args.price_series_csv)
    output_path = Path(args.output)

    if not price_series_path.exists():
        raise FileNotFoundError(f"Price series CSV not found: {price_series_path}")

    cohorts = load_price_series(price_series_path)
    prompt_template = _read_prompt_template()
    records, warnings = build_records(
        cohorts=cohorts,
        prompt_template=prompt_template,
        source_name=price_series_path.name,
    )
    write_jsonl(output_path, records)

    summary = {
        "price_series_csv": str(price_series_path),
        "output": str(output_path),
        "records_written": len(records),
        "ready_records": sum(1 for record in records if record["status"] == "ready"),
        "input_ready_records": sum(1 for record in records if record["status"] == "input_ready"),
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
