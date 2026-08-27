"""Build A1 ready seeds from a local CSV price snapshot file."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = {
    "task_id",
    "stock_code",
    "stock_name",
    "cutoff_date",
    "cutoff_price",
    "price_30d",
    "price_90d",
    "price_180d",
    "price_365d",
}

DEFAULT_PROMPT_TEMPLATE = """你是一位专业的股票分析师。
请仅基于 {cutoff_date} 之前的公开信息，对 {stock_name}（{stock_code}）进行分析。
截至 {cutoff_date}，该股收盘价约 {cutoff_price} {currency_unit}/股。

请给出 market_value_range（市场价值回归目标价，{currency_unit}/股，考虑当前市场环境，非内生价值），
以及价格回归至该区间所需的修复期。

以下面 JSON 格式输出，不要附加任何其他内容：
{
  "bull": <乐观情景目标价（{currency_unit}，浮点数）>,
  "base": <基准情景目标价（{currency_unit}，浮点数）>,
  "bear": <悲观情景目标价（{currency_unit}，浮点数）>,
  "reversion_horizon": "<从以下选项选一：1-4周 / 1-3个月 / 3-6个月 / 6-12个月 / 超过12个月>"
}

请严格输出 JSON，不要输出任何额外文字、解释或 markdown 代码块。
"""


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the A1 CSV builder."""
    parser = argparse.ArgumentParser(description="Build A1 ready seeds from CSV.")
    parser.add_argument("--csv", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output JSONL path.")
    return parser.parse_args()


def _read_prompt_template() -> str:
    """Load the A1 prompt template or fall back to a built-in version."""
    template_path = Path(__file__).resolve().parents[2] / "prompts" / "a1_valuation.txt"
    if not template_path.exists():
        return DEFAULT_PROMPT_TEMPLATE
    content = template_path.read_text(encoding="utf-8")
    required_vars = {"{stock_name}", "{stock_code}", "{cutoff_date}", "{cutoff_price}"}
    if not all(token in content for token in required_vars):
        return DEFAULT_PROMPT_TEMPLATE
    return content


def _parse_optional_float(value: str | None) -> float | None:
    """Convert a CSV string to float or null."""
    if value is None:
        return None
    stripped = str(value).strip()
    if stripped == "" or stripped.lower() == "none":
        return None
    return float(stripped)


def _infer_time_band(cutoff_date: str) -> str:
    """Infer a simple time band from cutoff date."""
    year = int(cutoff_date[:4])
    return "T2" if year >= 2024 else "T1"


def _render_prompt(
    template: str,
    row: dict[str, str],
    cutoff_price: float,
    currency_unit: str = "元",
) -> str:
    """Render the A1 prompt template with row values."""
    rendered = template
    rendered = rendered.replace("{stock_name}", row["stock_name"])
    rendered = rendered.replace("{stock_code}", row["stock_code"])
    rendered = rendered.replace("{cutoff_date}", row["cutoff_date"])
    rendered = rendered.replace("{cutoff_price}", f"{cutoff_price:.2f}")
    rendered = rendered.replace("{currency_unit}", currency_unit)
    return rendered


def build_record(
    row: dict[str, str],
    template: str,
    source_name: str,
    market: str = "CN_A",
    currency: str = "CNY",
    currency_unit: str = "元",
) -> dict[str, Any]:
    """Build one A1 ready record from a CSV-like row."""
    cutoff_price = float(row["cutoff_price"])
    actual_prices = {
        "30": _parse_optional_float(row.get("price_30d")),
        "90": _parse_optional_float(row.get("price_90d")),
        "180": _parse_optional_float(row.get("price_180d")),
        "365": _parse_optional_float(row.get("price_365d")),
    }
    primary_window = int(row.get("primary_eval_window_days") or 30)
    forward_trading_days = {
        key.removeprefix("forward_trading_day_"): str(value)
        for key, value in row.items()
        if key.startswith("forward_trading_day_") and value
    }
    return {
        "task_id": row["task_id"],
        "category": "A1",
        "variant": None,
        "cutoff_date": row["cutoff_date"],
        "time_band": _infer_time_band(row["cutoff_date"]),
        "status": "ready",
        "seed": {
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "cutoff_date": row["cutoff_date"],
            "cutoff_price": cutoff_price,
            "market": market,
            "currency": currency,
            "primary_eval_window_days": primary_window,
        },
        "prompt": _render_prompt(template, row, cutoff_price, currency_unit=currency_unit),
        "expected_output": {
            "bull": "float",
            "base": "float",
            "bear": "float",
            "reversion_horizon": "str",
        },
        "ground_truth": {
            "cutoff_price": cutoff_price,
            "actual_prices": actual_prices,
            "eval_windows_days": [30, 90, 180, 365],
            "primary_eval_window_days": primary_window,
            "forward_trading_days": forward_trading_days,
        },
        "metadata": {
            "source": source_name,
            "is_template": False,
            "builder_version": "a1_csv_builder_v2",
            "market": market,
            "currency": currency,
            "primary_eval_window_days": primary_window,
            "forward_trading_days": forward_trading_days,
        },
    }


def build_records(
    rows: list[dict[str, str]],
    source_name: str,
    market: str = "CN_A",
    currency: str = "CNY",
    currency_unit: str = "元",
) -> list[dict[str, Any]]:
    """Build A1 records from CSV-like rows."""
    template = _read_prompt_template()
    return [
        build_record(
            row,
            template,
            source_name,
            market=market,
            currency=currency,
            currency_unit=currency_unit,
        )
        for row in rows
    ]


def load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    """Load and validate CSV rows for A1 building."""
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV header is missing")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")

        rows = list(reader)

    seen_ids: set[str] = set()
    for index, row in enumerate(rows, 2):
        task_id = row["task_id"].strip()
        if not task_id:
            raise ValueError(f"{csv_path}:{index} task_id is empty")
        if task_id in seen_ids:
            raise ValueError(f"{csv_path}:{index} duplicate task_id: {task_id}")
        seen_ids.add(task_id)
        try:
            float(row["cutoff_price"])
            for key in ("price_30d", "price_90d", "price_180d", "price_365d"):
                _parse_optional_float(row[key])
        except ValueError as exc:
            raise ValueError(f"{csv_path}:{index} invalid price value: {exc}") from exc
    return rows


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write records to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    """Build A1 seeds from CSV and write them to JSONL."""
    args = parse_args()
    csv_path = Path(args.csv)
    output_path = Path(args.output)

    rows = load_csv_rows(csv_path)
    records = build_records(rows, csv_path.name)
    write_jsonl(output_path, records)

    print(
        json.dumps(
            {
                "csv": str(csv_path),
                "output": str(output_path),
                "records_written": len(records),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
