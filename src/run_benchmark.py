"""Minimal benchmark runner for A1/A2/B/C/D/E ready seeds."""

from __future__ import annotations

import argparse
import copy
import json
import os
import time
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from src.agents.hf_inference_agent import hf_inference_agent
from src.agents.mock_agent import mock_agent
from src.evaluators.a1_evaluator import evaluate_a1
from src.evaluators.a2_evaluator import evaluate_a2
from src.evaluators.b_evaluator import evaluate_b
from src.evaluators.c_evaluator import evaluate_c
from src.evaluators.d_evaluator import evaluate_d
from src.evaluators.e_evaluator import evaluate_e
from src.evaluators.official_score import aggregate_official_score
from src.load_seeds import attach_temporal_index, filter_paper_band, filter_records, load_jsonl
from src.parsers.a1_parser import parse_a1_response
from src.parsers.a2_parser import parse_a2_response
from src.parsers.b_parser import parse_b_response
from src.parsers.c_parser import parse_c_response
from src.parsers.d_parser import parse_d_response
from src.parsers.e_parser import parse_e_response

from scripts.assign_time_bands import update_row as update_temporal_band


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the benchmark runner."""
    parser = argparse.ArgumentParser(description="Run a benchmark on A1/A2/B/C/D/E ready seeds.")
    parser.add_argument("--seed", required=True, help="Path to seed JSONL file.")
    parser.add_argument("--category", default=None, help="Optional category filter.")
    parser.add_argument("--status", default="ready", help="Status filter, default is ready.")
    parser.add_argument("--agent", default="mock", help="Agent name: mock or hf.")
    parser.add_argument("--model", default="Qwen/Qwen3-8B", help="Model name for hf agent.")
    parser.add_argument("--api-key-env", default="HF_TOKEN", help="Environment variable for HF token.")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")
    parser.add_argument("--max-tokens", type=int, default=1024, help="Maximum new tokens.")
    parser.add_argument("--timeout-seconds", type=float, default=60.0, help="Request timeout in seconds.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of records to run.")
    parser.add_argument(
        "--model-training-cutoff",
        default=None,
        help="Optional model training cutoff date (YYYY-MM-DD). If set, recompute T1/T2/T3 in memory.",
    )
    parser.add_argument(
        "--current-date",
        default=None,
        help="Reference current date for temporal split. Defaults to today's date when --model-training-cutoff is set.",
    )
    parser.add_argument(
        "--time-band",
        choices=["T1", "T2", "T3"],
        default=None,
        help="Optional legacy temporal split filter after recomputing time bands.",
    )
    parser.add_argument(
        "--temporal-index",
        default=None,
        help="Optional task-temporal-index JSONL for paper_band filtering.",
    )
    parser.add_argument(
        "--paper-band",
        choices=["T1", "T2", "T3", "quarantine", "D", "E"],
        default=None,
        help="Filter by paper_band from --temporal-index.",
    )
    parser.add_argument(
        "--exclude-quarantine",
        action="store_true",
        help="Exclude quarantine records when --temporal-index is set.",
    )
    parser.add_argument(
        "--continue-on-error",
        dest="continue_on_error",
        action="store_true",
        default=True,
        help="Continue when a single record fails. Default: enabled.",
    )
    parser.add_argument(
        "--fail-on-error",
        dest="continue_on_error",
        action="store_false",
        help="Stop the run when a single record fails.",
    )
    parser.add_argument("--output", default="results/run", help="Output directory.")
    return parser.parse_args()


def get_agent(agent_name: str):
    """Resolve the configured agent function."""
    if agent_name == "mock":
        return mock_agent
    if agent_name == "hf":
        return hf_inference_agent
    raise ValueError(f"Unsupported agent: {agent_name}")


def parse_prediction(category: str, response: str) -> dict[str, Any]:
    """Dispatch to the correct parser by category."""
    if category == "A1":
        return parse_a1_response(response)
    if category == "A2":
        return parse_a2_response(response)
    if category == "B":
        return parse_b_response(response)
    if category == "C":
        return parse_c_response(response)
    if category == "D":
        return parse_d_response(response)
    if category == "E":
        return parse_e_response(response)
    raise ValueError(f"Unsupported category for parsing: {category}")


def evaluate_prediction(category: str, parsed: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to the correct evaluator by category."""
    if category == "A1":
        return evaluate_a1(parsed, record)
    if category == "A2":
        return evaluate_a2(parsed, record)
    if category == "B":
        return evaluate_b(parsed, record)
    if category == "C":
        return evaluate_c(parsed, record)
    if category == "D":
        return evaluate_d(parsed, record)
    if category == "E":
        return evaluate_e(parsed, record)
    raise ValueError(f"Unsupported category for evaluation: {category}")


def _rate(values: list[bool | None]) -> float | None:
    """Compute a boolean rate while ignoring null values."""
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return sum(1 for value in valid if value) / len(valid)


def _mean_metric(metrics_list: list[dict[str, Any]], key: str) -> float | None:
    """Mean for a flat numeric metric key."""
    values = [
        metrics[key]
        for metrics in metrics_list
        if isinstance(metrics.get(key), (int, float))
    ]
    return mean(values) if values else None


def _summarize_time_band(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize common metrics for one temporal band."""
    metrics_list = [prediction["metrics"] for prediction in predictions]
    categories: dict[str, int] = {}
    for prediction in predictions:
        category = prediction["category"]
        categories[category] = categories.get(category, 0) + 1

    return {
        "count": len(predictions),
        "categories": categories,
        "format_valid_rate": _rate([metrics.get("format_valid") for metrics in metrics_list]),
        "api_error_count": sum(1 for prediction in predictions if prediction.get("api_error")),
        "a1_monotonic_valid_rate": _rate([metrics.get("monotonic_valid") for metrics in metrics_list]),
        "a2_exact_set_match_rate": _rate([metrics.get("exact_set_match") for metrics in metrics_list]),
        "a2_mean_spearman_rho": _mean_metric(metrics_list, "spearman_rho"),
        "b_directional_accuracy_rate": _rate([metrics.get("directional_accuracy") for metrics in metrics_list]),
        "b_mean_brier_score": _mean_metric(metrics_list, "brier_score"),
        "c_within_10pct_rate": _rate([metrics.get("within_10pct") for metrics in metrics_list]),
        "c_mean_mape": _mean_metric(metrics_list, "mape"),
        "d_logic_adherence_rate": _rate([metrics.get("logic_adherence") for metrics in metrics_list]),
        "e_exact_match_0_2pct_rate": _rate([metrics.get("exact_match_0_2pct") for metrics in metrics_list]),
        "e_mean_relative_error": _mean_metric(metrics_list, "relative_error"),
    }


def _summarize_paper_band(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize common metrics for one paper temporal band."""
    return _summarize_time_band(predictions)


def summarize_results(
    predictions: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    agent: str,
    model: str,
    temporal_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build aggregate metrics for the completed run."""
    by_category: dict[str, Any] = {}
    categories = sorted({prediction["category"] for prediction in predictions})
    api_error_count = sum(1 for prediction in predictions if prediction.get("api_error"))
    parse_error_count = sum(
        1
        for prediction in predictions
        if isinstance(prediction.get("parsed"), dict) and prediction["parsed"].get("format_valid") is False
    )
    latencies = [
        prediction["latency_seconds"]
        for prediction in predictions
        if isinstance(prediction.get("latency_seconds"), (int, float))
    ]

    for category in categories:
        category_predictions = [prediction for prediction in predictions if prediction["category"] == category]
        metrics_list = [prediction["metrics"] for prediction in category_predictions]
        summary: dict[str, Any] = {
            "count": len(category_predictions),
            "format_valid_rate": _rate([metrics.get("format_valid") for metrics in metrics_list]),
        }

        if category == "A1":
            summary["monotonic_valid_rate"] = _rate(
                [metrics.get("monotonic_valid") for metrics in metrics_list]
            )
            by_window: dict[str, Any] = {}
            for window in ("30", "90", "180", "365"):
                window_metrics = [
                    metrics.get("by_window", {}).get(window, {}) for metrics in metrics_list
                ]
                errors = [
                    item.get("target_price_error_abs")
                    for item in window_metrics
                    if item.get("target_price_error_abs") is not None
                ]
                by_window[window] = {
                    "mean_target_price_error_abs": mean(errors) if errors else None,
                    "range_hit_rate": _rate([item.get("range_hit") for item in window_metrics]),
                }
            summary["by_window"] = by_window
            summary["reversion_horizon_hit_rate"] = _rate(
                [metrics.get("reversion_horizon_hit") for metrics in metrics_list]
            )

        if category == "A2":
            summary["exact_set_match_rate"] = _rate(
                [metrics.get("exact_set_match") for metrics in metrics_list]
            )
            spearman_values = [
                metrics["spearman_rho"]
                for metrics in metrics_list
                if metrics.get("spearman_rho") is not None
            ]
            top_k_values = [
                metrics["top_k_hit_rate"]
                for metrics in metrics_list
                if metrics.get("top_k_hit_rate") is not None
            ]
            long_short_values = [
                metrics["long_short_spread"]
                for metrics in metrics_list
                if metrics.get("long_short_spread") is not None
            ]
            summary["mean_spearman_rho"] = mean(spearman_values) if spearman_values else None
            summary["mean_top_k_hit_rate"] = mean(top_k_values) if top_k_values else None
            summary["mean_long_short_spread"] = mean(long_short_values) if long_short_values else None

            by_variant: dict[str, Any] = {}
            for variant in sorted({prediction.get("variant") for prediction in category_predictions}):
                variant_predictions = [
                    prediction
                    for prediction in category_predictions
                    if prediction.get("variant") == variant
                ]
                variant_metrics = [prediction["metrics"] for prediction in variant_predictions]
                by_variant[str(variant)] = {
                    "count": len(variant_predictions),
                    "format_valid_rate": _rate(
                        [metrics.get("format_valid") for metrics in variant_metrics]
                    ),
                    "exact_set_match_rate": _rate(
                        [metrics.get("exact_set_match") for metrics in variant_metrics]
                    ),
                    "mean_spearman_rho": mean(
                        [
                            metrics["spearman_rho"]
                            for metrics in variant_metrics
                            if metrics.get("spearman_rho") is not None
                        ]
                    )
                    if any(metrics.get("spearman_rho") is not None for metrics in variant_metrics)
                    else None,
                    "mean_top_k_hit_rate": mean(
                        [
                            metrics["top_k_hit_rate"]
                            for metrics in variant_metrics
                            if metrics.get("top_k_hit_rate") is not None
                        ]
                    )
                    if any(metrics.get("top_k_hit_rate") is not None for metrics in variant_metrics)
                    else None,
                    "mean_long_short_spread": mean(
                        [
                            metrics["long_short_spread"]
                            for metrics in variant_metrics
                            if metrics.get("long_short_spread") is not None
                        ]
                    )
                    if any(metrics.get("long_short_spread") is not None for metrics in variant_metrics)
                    else None,
                }
            summary["by_variant"] = by_variant

        if category == "B":
            summary["directional_accuracy_rate"] = _rate(
                [metrics.get("directional_accuracy") for metrics in metrics_list]
            )
            brier_values = [
                metrics["brier_score"]
                for metrics in metrics_list
                if metrics.get("brier_score") is not None
            ]
            summary["mean_brier_score"] = mean(brier_values) if brier_values else None
            by_variant: dict[str, Any] = {}
            for variant in sorted({prediction.get("variant") for prediction in category_predictions}):
                variant_predictions = [
                    prediction
                    for prediction in category_predictions
                    if prediction.get("variant") == variant
                ]
                variant_metrics = [prediction["metrics"] for prediction in variant_predictions]
                by_variant[str(variant)] = {
                    "count": len(variant_predictions),
                    "format_valid_rate": _rate(
                        [metrics.get("format_valid") for metrics in variant_metrics]
                    ),
                    "directional_accuracy_rate": _rate(
                        [metrics.get("directional_accuracy") for metrics in variant_metrics]
                    ),
                    "mean_brier_score": mean(
                        [
                            metrics["brier_score"]
                            for metrics in variant_metrics
                            if metrics.get("brier_score") is not None
                        ]
                    )
                    if any(metrics.get("brier_score") is not None for metrics in variant_metrics)
                    else None,
                }
            summary["by_variant"] = by_variant

        if category == "C":
            mape_values = [
                metrics["mape"]
                for metrics in metrics_list
                if metrics.get("mape") is not None
            ]
            summary["within_10pct_rate"] = _rate(
                [metrics.get("within_10pct") for metrics in metrics_list]
            )
            summary["mean_mape"] = mean(mape_values) if mape_values else None

        if category == "D":
            summary["logic_adherence_rate"] = _rate(
                [metrics.get("logic_adherence") for metrics in metrics_list]
            )
            by_time_band: dict[str, Any] = {}
            for time_band in sorted({metrics.get("time_band") for metrics in metrics_list}):
                band_metrics = [
                    metrics for metrics in metrics_list if metrics.get("time_band") == time_band
                ]
                by_time_band[str(time_band)] = {
                    "count": len(band_metrics),
                    "logic_adherence_rate": _rate(
                        [metrics.get("logic_adherence") for metrics in band_metrics]
                    ),
                }
            summary["by_time_band"] = by_time_band

        if category == "E":
            relative_errors = [
                metrics["relative_error"]
                for metrics in metrics_list
                if metrics.get("relative_error") is not None
            ]
            summary["exact_match_0_2pct_rate"] = _rate(
                [metrics.get("exact_match_0_2pct") for metrics in metrics_list]
            )
            summary["mean_relative_error"] = mean(relative_errors) if relative_errors else None
            summary["formula_text_match_rate"] = _rate(
                [metrics.get("formula_text_match") for metrics in metrics_list]
            )
            summary["unit_match_rate"] = _rate(
                [metrics.get("unit_match") for metrics in metrics_list]
            )

        by_category[category] = summary

    by_time_band = {
        str(time_band): _summarize_time_band(
            [prediction for prediction in predictions if prediction.get("time_band") == time_band]
        )
        for time_band in sorted({prediction.get("time_band") for prediction in predictions})
    }

    by_paper_band = {
        str(paper_band): _summarize_paper_band(
            [prediction for prediction in predictions if prediction.get("paper_band") == paper_band]
        )
        for paper_band in sorted({prediction.get("paper_band") for prediction in predictions if prediction.get("paper_band")})
    }
    official = aggregate_official_score(predictions, paper_band="T2")

    return {
        "agent": agent,
        "model": model,
        "temporal_config": temporal_config,
        "total_records": len(predictions) + len(skipped),
        "evaluated_records": len(predictions),
        "skipped_records": len(skipped),
        "api_error_count": api_error_count,
        "parse_error_count": parse_error_count,
        "total_latency_seconds": sum(latencies) if latencies else 0.0,
        "mean_latency_seconds": mean(latencies) if latencies else None,
        "by_time_band": by_time_band,
        "by_paper_band": by_paper_band,
        "official_score": official,
        "by_category": by_category,
    }


def maybe_recompute_temporal_bands(records: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    """Recompute temporal bands for a model-specific cutoff without changing files."""
    if not args.model_training_cutoff:
        return records

    current_date = args.current_date or date.today().isoformat()
    return [
        update_temporal_band(copy.deepcopy(record), args.model_training_cutoff, current_date)
        for record in records
    ]


def write_predictions(path: Path, predictions: list[dict[str, Any]]) -> None:
    """Write per-record predictions to a JSONL file."""
    with path.open("w", encoding="utf-8") as f:
        for row in predictions:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _empty_parsed(category: str, error: str) -> dict[str, Any]:
    """Build a parser-compatible error payload for failed requests."""
    if category == "A1":
        return {
            "format_valid": False,
            "bull": None,
            "base": None,
            "bear": None,
            "reversion_horizon": None,
            "monotonic_valid": None,
            "error": error,
        }
    if category == "A2":
        return {
            "format_valid": False,
            "ranking": None,
            "error": error,
        }
    if category == "B":
        return {
            "format_valid": False,
            "direction": None,
            "probability_up": None,
            "error": error,
        }
    if category == "C":
        return {
            "format_valid": False,
            "predicted_value": None,
            "metric": None,
            "error": error,
        }
    if category == "D":
        return {
            "format_valid": False,
            "direction": None,
            "reasoning": None,
            "error": error,
        }
    if category == "E":
        return {
            "format_valid": False,
            "formula_used": None,
            "answer": None,
            "unit": None,
            "error": error,
        }
    raise ValueError(f"Unsupported category for fallback parser payload: {category}")


def main() -> int:
    """Run the benchmark smoke test and write outputs."""
    args = parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(args.seed)
    records = maybe_recompute_temporal_bands(records, args)
    if args.temporal_index:
        records = attach_temporal_index(records, args.temporal_index)
        records = filter_paper_band(
            records,
            paper_band=args.paper_band,
            exclude_quarantine=args.exclude_quarantine,
        )
    records = filter_records(records, category=args.category, status=None)
    if args.time_band is not None:
        records = [record for record in records if record.get("time_band") == args.time_band]
    if args.limit is not None:
        records = records[: args.limit]
    agent_fn = get_agent(args.agent)
    api_key: str | None = None

    if args.agent == "hf":
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise ValueError(f"Missing Hugging Face token env var: {args.api_key_env}")

    predictions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for record in records:
        category = record.get("category")
        if record.get("status") != args.status:
            skipped.append(
                {
                    "task_id": record.get("task_id"),
                    "category": category,
                    "reason": f"status {record.get('status')} != requested {args.status}",
                }
            )
            continue

        if category == "A2" and record.get("variant") not in {"F", "T", "H"}:
            skipped.append(
                {
                    "task_id": record.get("task_id"),
                    "category": category,
                    "reason": f"unsupported A2 variant: {record.get('variant')}",
                }
            )
            continue

        if category not in {"A1", "A2", "B", "C", "D", "E"}:
            skipped.append(
                {
                    "task_id": record.get("task_id"),
                    "category": category,
                    "reason": "unsupported category for this benchmark runner",
                }
            )
            continue

        prompt = record["prompt"]
        raw_response: str | None = None
        api_error: str | None = None
        started_at = time.perf_counter()

        try:
            if args.agent == "mock":
                raw_response = agent_fn(prompt, record)
            else:
                raw_response = agent_fn(
                    prompt,
                    record,
                    model=args.model,
                    api_key=api_key or "",
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    timeout_seconds=args.timeout_seconds,
                )
            if not raw_response.strip():
                raise RuntimeError("Empty response from agent")

            parsed = parse_prediction(category, raw_response)
            metrics = evaluate_prediction(category, parsed, record)
        except Exception as exc:
            api_error = str(exc)
            if not args.continue_on_error:
                raise
            parsed = _empty_parsed(category, api_error)
            metrics = evaluate_prediction(category, parsed, record)

        latency_seconds = time.perf_counter() - started_at

        predictions.append(
            {
                "task_id": record.get("task_id"),
                "category": category,
                "variant": record.get("variant"),
                "cutoff_date": record.get("cutoff_date"),
                "time_band": record.get("time_band"),
                "paper_band": record.get("paper_band"),
                "paper_temporal": record.get("paper_temporal"),
                "temporal_split": record.get("metadata", {}).get("temporal_split"),
                "agent": args.agent,
                "model": args.model,
                "prompt": prompt,
                "raw_response": raw_response,
                "api_error": api_error,
                "latency_seconds": latency_seconds,
                "parsed": parsed,
                "metrics": metrics,
            }
        )

    temporal_config = None
    if args.model_training_cutoff:
        temporal_config = {
            "model_training_cutoff": args.model_training_cutoff,
            "current_date": args.current_date or date.today().isoformat(),
            "time_band_filter": args.time_band,
            "mode": "runtime_recomputed",
        }
    else:
        temporal_config = {
            "mode": "seed_embedded",
            "time_band_filter": args.time_band,
        }
    summary = summarize_results(
        predictions,
        skipped,
        agent=args.agent,
        model=args.model,
        temporal_config=temporal_config,
    )
    run_config = {
        "seed": args.seed,
        "category": args.category,
        "status": args.status,
        "agent": args.agent,
        "model": args.model,
        "api_key_env": args.api_key_env,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "timeout_seconds": args.timeout_seconds,
        "limit": args.limit,
        "model_training_cutoff": args.model_training_cutoff,
        "current_date": args.current_date,
        "time_band": args.time_band,
        "temporal_index": args.temporal_index,
        "paper_band": args.paper_band,
        "exclude_quarantine": args.exclude_quarantine,
        "continue_on_error": args.continue_on_error,
        "output": str(output_dir),
    }

    write_predictions(output_dir / "predictions.jsonl", predictions)
    with (output_dir / "metrics_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with (output_dir / "run_config.json").open("w", encoding="utf-8") as f:
        json.dump(run_config, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
