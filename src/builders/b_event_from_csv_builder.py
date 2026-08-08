"""Build B event-driven direction seeds from local events CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PROMPT_FALLBACK = """信息截止日期：{cutoff_date}

事件：{event_description}

股票：{stock_name}（{stock_code}）

请预测该股票在事件发生后短期内的价格方向。

以下面 JSON 格式输出：
{{
  "direction": "up" 或 "down",
  "probability_up": <0到1的浮点数>
}}

请严格输出 JSON，不要输出任何额外文字、解释或 markdown 代码块。
"""

SUPPORTED_SUBTYPES = {"earnings", "macro"}
SUBTYPE_TO_VARIANT = {
    "earnings": "earnings",
    "macro": "macro",
}

REQUIRED_COLUMNS = {
    "event_id",
    "event_subtype",
    "stock_code",
    "stock_name",
    "event_date",
    "event_description",
    "cutoff_date",
    "actual_direction",
    "actual_return_pct",
}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the B builder."""
    parser = argparse.ArgumentParser(description="Build B seeds from events CSV.")
    parser.add_argument(
        "--csv",
        default="data/b_events.csv",
        help="Input events CSV path.",
    )
    parser.add_argument(
        "--output",
        default="seeds/b_event.jsonl",
        help="Output JSONL path.",
    )
    return parser.parse_args()


def _read_prompt_template() -> str:
    """Load the B prompt template or fall back to a built-in version."""
    template_path = Path(__file__).resolve().parents[2] / "prompts" / "b_event.txt"
    if not template_path.exists():
        return PROMPT_FALLBACK
    return template_path.read_text(encoding="utf-8")


def _infer_time_band(cutoff_date: str) -> str:
    """Infer a simple time band from cutoff date."""
    year = int(cutoff_date[:4])
    return "T2" if year >= 2024 else "T1"


def _render_prompt(
    template: str,
    cutoff_date: str,
    event_description: str,
    stock_name: str,
    stock_code: str,
) -> str:
    """Render the B prompt template."""
    rendered = template
    rendered = rendered.replace("{cutoff_date}", cutoff_date)
    rendered = rendered.replace("{event_date}", cutoff_date)
    rendered = rendered.replace("{event_description}", event_description)
    rendered = rendered.replace("{stock_name}", stock_name)
    rendered = rendered.replace("{stock_code}", stock_code)
    rendered = rendered.replace("{target_identifier}", stock_code)
    rendered = rendered.replace("{prediction_window}", "短期")
    return rendered


def load_rows(path: Path) -> list[dict[str, str]]:
    """Load event CSV rows."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV header is missing")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")
        return list(reader)


def build_record(row: dict[str, str], template: str, source_name: str) -> dict[str, Any]:
    """Build one B ready record from a CSV row."""
    subtype = row["event_subtype"].strip()
    variant = SUBTYPE_TO_VARIANT[subtype]
    actual_direction = row["actual_direction"].strip()
    actual_return_pct = float(row["actual_return_pct"])

    seed = {
        "event_id": row["event_id"].strip(),
        "event_subtype": subtype,
        "stock_code": row["stock_code"].strip(),
        "stock_name": row["stock_name"].strip(),
        "event_date": row["event_date"].strip(),
        "event_description": row["event_description"].strip(),
        "cutoff_date": row["cutoff_date"].strip(),
    }

    return {
        "task_id": row["event_id"].strip(),
        "category": "B",
        "variant": variant,
        "time_band": _infer_time_band(row["cutoff_date"].strip()),
        "status": "ready",
        "seed": seed,
        "prompt": _render_prompt(
            template,
            cutoff_date=seed["cutoff_date"],
            event_description=seed["event_description"],
            stock_name=seed["stock_name"],
            stock_code=seed["stock_code"],
        ),
        "expected_output": {
            "direction": "up|down",
            "probability_up": "float",
        },
        "ground_truth": {
            "actual_direction": actual_direction,
            "actual_return_pct": actual_return_pct,
            "actual_up": 1.0 if actual_direction == "up" else 0.0,
        },
        "metadata": {
            "source": source_name,
            "is_template": False,
            "builder_version": "b_event_csv_builder_v1",
        },
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write records to JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    """Build B seeds from CSV and write them to JSONL."""
    args = parse_args()
    csv_path = Path(args.csv)
    output_path = Path(args.output)

    if not csv_path.exists():
        raise FileNotFoundError(f"Events CSV not found: {csv_path}")

    template = _read_prompt_template()
    rows = load_rows(csv_path)
    filtered_rows = [row for row in rows if row["event_subtype"].strip() in SUPPORTED_SUBTYPES]
    skipped_subtypes = sorted(
        {row["event_subtype"].strip() for row in rows if row["event_subtype"].strip() not in SUPPORTED_SUBTYPES}
    )
    records = [build_record(row, template, csv_path.name) for row in filtered_rows]
    write_jsonl(output_path, records)

    subtype_counts: dict[str, int] = {}
    for row in filtered_rows:
        subtype = row["event_subtype"].strip()
        subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1

    summary = {
        "csv": str(csv_path),
        "output": str(output_path),
        "records_written": len(records),
        "ready_records": len(records),
        "earnings_records": subtype_counts.get("earnings", 0),
        "macro_records": subtype_counts.get("macro", 0),
        "skipped_subtypes": skipped_subtypes,
        "csv_total_rows": len(rows),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
