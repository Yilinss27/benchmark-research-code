"""Build A2-F ready seeds from local fundamentals, cohort, and returns CSV files."""

from __future__ import annotations

import argparse
import csv
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


PROMPT_FALLBACK = """以下是 {industry_name} 行业 {N} 只股票，信息截止日期 {cutoff_date}。

【财务基本面指标】
{fundamentals_dict}

请综合上述信号，预测这 {N} 只股票未来 {prediction_window_days} 天收益率从高到低的排名，输出 JSON 数组（代码顺序即排名）：
["code_rank_1", "code_rank_2", ..., "code_rank_N"]

请严格输出 JSON，不要输出任何额外文字、解释或 markdown 代码块。
"""


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the A2-F builder."""
    parser = argparse.ArgumentParser(description="Build A2-F seeds from CSV files.")
    parser.add_argument(
        "--fundamentals-csv",
        default="data/a2_fundamentals_snapshot.csv",
        help="Fundamentals CSV path.",
    )
    parser.add_argument(
        "--cohorts-csv",
        default="data/a2_cohorts_manual.csv",
        help="Manual cohort CSV path.",
    )
    parser.add_argument(
        "--returns-csv",
        default="data/a2_returns.manual.csv",
        help="Returns CSV path.",
    )
    parser.add_argument(
        "--output",
        default="seeds/a2_fundamentals.jsonl",
        help="Output JSONL path.",
    )
    return parser.parse_args()


def _resolve_cohorts_path(path_str: str) -> Path:
    """Resolve cohort CSV path, supporting dot and underscore filenames."""
    candidates = [Path(path_str), Path("data/a2_cohorts_manual.csv")]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Cohort CSV not found: {path_str} or data/a2_cohorts_manual.csv")


def _read_prompt_template() -> str:
    """Load the A2-F prompt template or fall back to a built-in version."""
    template_path = Path(__file__).resolve().parents[2] / "prompts" / "a2_ranking_f.txt"
    if not template_path.exists():
        return PROMPT_FALLBACK
    content = template_path.read_text(encoding="utf-8")
    required_tokens = {"{industry_name}", "{cutoff_date}", "{fundamentals_dict}", "{prediction_window_days}"}
    if not all(token in content for token in required_tokens):
        return PROMPT_FALLBACK
    return content


def _normalize_stock_code(value: str) -> str:
    """Normalize stock codes to 6-digit strings."""
    stripped = value.strip()
    if stripped.isdigit():
        return stripped.zfill(6)
    return stripped


def load_cohorts(path: Path) -> dict[str, dict[str, Any]]:
    """Load manual cohort definitions grouped by cohort_id."""
    required = {
        "cohort_id",
        "industry_name",
        "cutoff_date",
        "prediction_window_days",
        "stock_code",
        "stock_name",
    }
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("Cohort CSV header is missing")
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Cohort CSV missing required columns: {sorted(missing)}")

        grouped: dict[str, dict[str, Any]] = {}
        for row in reader:
            cohort_id = row["cohort_id"].strip()
            group = grouped.setdefault(
                cohort_id,
                {
                    "cohort_id": cohort_id,
                    "industry_name": row["industry_name"].strip(),
                    "cutoff_date": row["cutoff_date"].strip(),
                    "prediction_window_days": int(row["prediction_window_days"]),
                    "stocks": [],
                },
            )
            group["stocks"].append(
                {
                    "code": _normalize_stock_code(row["stock_code"]),
                    "name": row["stock_name"].strip(),
                }
            )
    return grouped


def load_returns(path: Path) -> dict[str, dict[str, float]]:
    """Load actual returns by cohort and stock code."""
    required = {"cohort_id", "stock_code", "actual_return"}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("Returns CSV header is missing")
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Returns CSV missing required columns: {sorted(missing)}")

        grouped: dict[str, dict[str, float]] = {}
        for row in reader:
            cohort_id = row["cohort_id"].strip()
            grouped.setdefault(cohort_id, {})[_normalize_stock_code(row["stock_code"])] = float(
                row["actual_return"]
            )
    return grouped


def _render_prompt(
    template: str,
    industry_name: str,
    n_stocks: int,
    cutoff_date: str,
    fundamentals_dict: dict[str, Any],
    prediction_window_days: int,
) -> str:
    """Render the A2-F prompt using the prompt template text."""
    rendered = template
    rendered = rendered.replace("{industry_name}", industry_name)
    rendered = rendered.replace("{N}", str(n_stocks))
    rendered = rendered.replace("{n_stocks}", str(n_stocks))
    rendered = rendered.replace("{cutoff_date}", cutoff_date)
    rendered = rendered.replace("{fundamentals_dict}", json.dumps(fundamentals_dict, ensure_ascii=False))
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


def build_records(
    fundamentals_history: dict[str, list[dict[str, Any]]],
    cohorts: dict[str, dict[str, Any]],
    returns_by_cohort: dict[str, dict[str, float]],
    prompt_template: str,
    source_name: str,
    *,
    market: str = "CN_A",
    currency: str = "CNY",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build A2-F records and collect warnings."""
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    record_index = 1

    for cohort_id, cohort in cohorts.items():
        stock_list = cohort["stocks"]
        fundamentals_dict: dict[str, dict[str, Any]] = {}
        fundamentals_match_by_stock: dict[str, dict[str, str]] = {}
        missing_fundamentals: list[str] = []

        for stock in stock_list:
            code = stock["code"]
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

        if missing_fundamentals or len(fundamentals_dict) != len(stock_list):
            warnings.append(f"Skipped cohort {cohort_id}: missing fundamentals for {missing_fundamentals}")
            continue

        match_modes = {item["match_mode"] for item in fundamentals_match_by_stock.values()}
        if MATCH_MODE_FALLBACK in match_modes and MATCH_MODE_ON_OR_BEFORE in match_modes:
            cohort_match_mode = "mixed"
        elif MATCH_MODE_FALLBACK in match_modes:
            cohort_match_mode = MATCH_MODE_FALLBACK
        else:
            cohort_match_mode = MATCH_MODE_ON_OR_BEFORE

        snapshot_dates = sorted({item["snapshot_date"] for item in fundamentals_match_by_stock.values()})
        fundamentals_snapshot_date = snapshot_dates[0] if len(snapshot_dates) == 1 else snapshot_dates

        actual_returns = returns_by_cohort.get(cohort_id)
        status = "ready"
        ground_truth: dict[str, Any] | None
        if actual_returns is None or any(stock["code"] not in actual_returns for stock in stock_list):
            status = "input_ready"
            ground_truth = None
            warnings.append(
                f"Cohort {cohort_id} missing complete returns; emitted as input_ready"
            )
        else:
            ordered_returns = {stock["code"]: float(actual_returns[stock["code"]]) for stock in stock_list}
            ground_truth = {
                "actual_returns": ordered_returns,
                "actual_ranking": _actual_ranking(ordered_returns),
                "prediction_window_days": cohort["prediction_window_days"],
                "forward_trading_days": {
                    stock["code"]: stock["forward_trading_day"]
                    for stock in stock_list
                    if stock.get("forward_trading_day")
                },
            }

        record = {
            "task_id": cohort.get("task_id") or f"A2F-{record_index:05d}",
            "category": "A2",
            "variant": "F",
            "cutoff_date": cohort["cutoff_date"],
            "time_band": "T2",
            "status": status,
            "seed": {
                "industry_name": cohort["industry_name"],
                "cutoff_date": cohort["cutoff_date"],
                "prediction_window_days": cohort["prediction_window_days"],
                "signal_variant": "F",
                "stock_list": stock_list,
                "fundamentals_dict": fundamentals_dict,
                "market": market,
                "currency": currency,
                "outcome_trading_day": max(
                    (
                        stock["forward_trading_day"]
                        for stock in stock_list
                        if stock.get("forward_trading_day")
                    ),
                    default=None,
                ),
            },
            "prompt": _render_prompt(
                prompt_template,
                industry_name=cohort["industry_name"],
                n_stocks=len(stock_list),
                cutoff_date=cohort["cutoff_date"],
                fundamentals_dict=fundamentals_dict,
                prediction_window_days=cohort["prediction_window_days"],
            ),
            "expected_output": {
                "ranking": "list[str], permutation of stock codes",
            },
            "ground_truth": ground_truth,
            "metadata": {
                "source": source_name,
                "is_template": False,
                "builder_version": "a2_fundamentals_csv_builder_v2",
                "cohort_id": cohort_id,
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
    """Build A2-F seed records from local CSV files."""
    args = parse_args()
    fundamentals_path, path_warnings = resolve_fundamentals_path(args.fundamentals_csv)
    cohorts_path = _resolve_cohorts_path(args.cohorts_csv)
    returns_path = Path(args.returns_csv)
    output_path = Path(args.output)

    fundamentals_history = load_fundamentals_history(fundamentals_path)
    cohorts = load_cohorts(cohorts_path)
    returns_by_cohort = load_returns(returns_path) if returns_path.exists() else {}
    prompt_template = _read_prompt_template()

    records, warnings = build_records(
        fundamentals_history=fundamentals_history,
        cohorts=cohorts,
        returns_by_cohort=returns_by_cohort,
        prompt_template=prompt_template,
        source_name=fundamentals_path.name,
    )
    warnings = path_warnings + warnings
    write_jsonl(output_path, records)

    summary = {
        "fundamentals_csv": str(fundamentals_path),
        "cohorts_csv": str(cohorts_path),
        "returns_csv": str(returns_path) if returns_path.exists() else None,
        "output": str(output_path),
        "records_written": len(records),
        "ready_records": sum(1 for record in records if record["status"] == "ready"),
        "input_ready_records": sum(1 for record in records if record["status"] == "input_ready"),
        "prototype_fallback_cohorts": sum(
            1
            for record in records
            if record.get("metadata", {}).get("fundamentals_match_mode") == MATCH_MODE_FALLBACK
        ),
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
