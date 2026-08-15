"""Build C ready/template seeds from local financial snapshot CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PROMPT_FALLBACK = """以下是 {stock_name} 近两个季度的财务摘要：
{historical_financials}

截止 {cutoff_date} 之前获取的第三方参考信息：
{third_party_info}

请基于上述信息，预测下一季度财报中「{metric_name}」的数值。

以下面 JSON 格式输出：
{{"predicted_value": <浮点数>}}

请严格输出 JSON，不要输出任何额外文字、解释或 markdown 代码块。
"""

REQUIRED_COLUMNS = {
    "task_id",
    "stock_code",
    "stock_name",
    "cutoff_date",
    "metric_name",
    "report_period_historical",
    "historical_value",
    "report_period_future",
    "future_value",
}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the C builder."""
    parser = argparse.ArgumentParser(description="Build C seeds from financial snapshot CSV.")
    parser.add_argument(
        "--csv",
        default="data/c_financial_snapshots.csv",
        help="Input financial snapshot CSV path.",
    )
    parser.add_argument(
        "--output",
        default="seeds/c_financial_metric.jsonl",
        help="Output JSONL path.",
    )
    return parser.parse_args()


def _read_prompt_template() -> str:
    """Load the C prompt template or fall back to a built-in version."""
    template_path = Path(__file__).resolve().parents[2] / "prompts" / "c_financial_metric.txt"
    if not template_path.exists():
        return PROMPT_FALLBACK
    return template_path.read_text(encoding="utf-8")


def _parse_optional_float(value: str | None) -> float | None:
    """Convert a CSV value to float when present."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    return float(stripped)


def _infer_time_band(cutoff_date: str) -> str:
    """Infer a simple time band from cutoff date."""
    year = int(cutoff_date[:4])
    return "T2" if year >= 2024 else "T1"


def _format_historical_financials(row: dict[str, str]) -> str:
    """Format one historical financial observation for the prompt."""
    return (
        f"{row['report_period_historical']}：{row['metric_name']} = {row['historical_value']}"
    )


def _render_prompt(
    template: str,
    stock_name: str,
    cutoff_date: str,
    metric_name: str,
    historical_financials: str,
    third_party_info: str,
) -> str:
    """Render the C prompt template."""
    rendered = template
    rendered = rendered.replace("{stock_name}", stock_name)
    rendered = rendered.replace("{cutoff_date}", cutoff_date)
    rendered = rendered.replace("{metric_name}", metric_name)
    rendered = rendered.replace("{historical_financials}", historical_financials)
    rendered = rendered.replace("{third_party_info}", third_party_info)
    return rendered


def load_rows(path: Path) -> list[dict[str, str]]:
    """Load and validate financial snapshot CSV rows."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV header is missing")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")
        return list(reader)


def build_record(
    row: dict[str, str],
    template: str,
    source_name: str,
    *,
    market: str = "CN_A",
    currency: str = "CNY",
) -> dict[str, Any]:
    """Build one C record from a CSV row."""
    future_value = _parse_optional_float(row.get("future_value"))
    historical_value = _parse_optional_float(row.get("historical_value"))
    status = "ready" if future_value is not None else "template"
    historical_financials = _format_historical_financials(row)
    third_party_info = "无"

    seed = {
        "stock_code": row["stock_code"].strip(),
        "stock_name": row["stock_name"].strip(),
        "cutoff_date": row["cutoff_date"].strip(),
        "metric_name": row["metric_name"].strip(),
        "report_period_historical": row["report_period_historical"].strip(),
        "historical_value": historical_value,
        "report_period_future": row["report_period_future"].strip(),
        "historical_financials": historical_financials,
        "third_party_info": third_party_info,
        "market": market,
        "currency": currency,
    }

    ground_truth: dict[str, Any] | None
    if status == "ready":
        ground_truth = {
            "future_value": future_value,
            "report_period_future": row["report_period_future"].strip(),
            "metric_name": row["metric_name"].strip(),
        }
    else:
        ground_truth = None

    return {
        "task_id": row["task_id"].strip(),
        "category": "C",
        "variant": None,
        "cutoff_date": row["cutoff_date"].strip(),
        "time_band": _infer_time_band(row["cutoff_date"].strip()),
        "status": status,
        "seed": seed,
        "prompt": _render_prompt(
            template,
            stock_name=seed["stock_name"],
            cutoff_date=seed["cutoff_date"],
            metric_name=seed["metric_name"],
            historical_financials=historical_financials,
            third_party_info=third_party_info,
        ),
        "expected_output": {
            "predicted_value": "float",
        },
        "ground_truth": ground_truth,
        "metadata": {
            "source": source_name,
            "is_template": status == "template",
            "builder_version": "c_financial_metric_csv_builder_v2",
            "market": market,
            "currency": currency,
        },
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write records to JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    """Build C seeds from CSV and write them to JSONL."""
    args = parse_args()
    csv_path = Path(args.csv)
    output_path = Path(args.output)

    if not csv_path.exists():
        raise FileNotFoundError(f"Financial snapshot CSV not found: {csv_path}")

    template = _read_prompt_template()
    rows = load_rows(csv_path)
    records = [build_record(row, template, csv_path.name) for row in rows]
    write_jsonl(output_path, records)

    summary = {
        "csv": str(csv_path),
        "output": str(output_path),
        "records_written": len(records),
        "ready_records": sum(1 for record in records if record["status"] == "ready"),
        "template_records": sum(1 for record in records if record["status"] == "template"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
