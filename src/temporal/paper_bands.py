"""Paper temporal bands from forecast_origin and outcome_available_at."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from src.data.providers.base import add_calendar_days, parse_iso_date
from src.data.yahoo_fundamentals import ANNUAL_LAG_DAYS, QUARTER_LAG_DAYS


PAPER_BANDS = frozenset({"T1", "T2", "T3", "quarantine", "D", "E"})
REVIEW_STATUSES = frozenset({"draft", "reviewed"})
TEMPORAL_FLATTEN_FIELDS = (
    "forecast_origin",
    "forecast_origin_source",
    "outcome_available_at",
    "outcome_available_at_source",
    "outcome_evidence_url",
    "outcome_evidence_code",
    "paper_band",
    "paper_band_reason",
    "review_status",
    "review_method",
    "reviewed_at",
    "evidence_hash",
    "quality_flags",
    "official_temporal_eligible",
)

CATEGORY_TO_HF_CONFIG = {
    "A1": "a1",
    "A2": {"F": "a2_f", "T": "a2_t", "H": "a2_h"},
    "B": "b",
    "C": "c",
    "D": "d",
    "E": "e",
}

A1_OUTCOME_HORIZON_DAYS = 30
A2_PREDICTION_WINDOW_DAYS = 30


@dataclass(frozen=True)
class PaperExperimentConfig:
    """Constants for paper temporal geometry."""

    # GPT-4.1 documents its knowledge cutoff at month granularity ("June 2024").
    # Use month-end conservatively rather than assuming knowledge stopped June 1.
    backbone_training_cutoff: str = "2024-06-30"
    guard_days: int = 30
    experiment_as_of: str = "2026-08-17"

    @property
    def t1_outcome_max(self) -> str:
        """Latest outcome date that still counts as T1."""
        return (
            parse_iso_date(self.backbone_training_cutoff) - timedelta(days=self.guard_days)
        ).isoformat()

    @property
    def t2_origin_min(self) -> str:
        """Earliest forecast origin that counts as T2."""
        return (
            parse_iso_date(self.backbone_training_cutoff) + timedelta(days=self.guard_days)
        ).isoformat()

    @property
    def t2_outcome_max(self) -> str:
        """Latest outcome date that still counts as T2."""
        return (
            parse_iso_date(self.experiment_as_of) - timedelta(days=self.guard_days)
        ).isoformat()


DEFAULT_EXPERIMENT_CONFIG = PaperExperimentConfig()


def _hf_config(record: dict[str, Any]) -> str:
    """Map a seed record to its HF config name."""
    category = record.get("category")
    if category == "A1":
        return "a1"
    if category == "A2":
        variant = record.get("variant")
        mapping = CATEGORY_TO_HF_CONFIG["A2"]
        if variant not in mapping:
            raise ValueError(f"Unsupported A2 variant: {variant}")
        return mapping[variant]
    if category in {"B", "C", "D", "E"}:
        return CATEGORY_TO_HF_CONFIG[category]
    raise ValueError(f"Unsupported category: {category}")


def _cutoff_date(record: dict[str, Any]) -> str:
    """Extract cutoff_date from a seed record."""
    if record.get("cutoff_date"):
        return str(record["cutoff_date"])
    seed = record.get("seed") or {}
    if seed.get("cutoff_date"):
        return str(seed["cutoff_date"])
    if seed.get("event_date"):
        return str(seed["event_date"])
    raise ValueError(f"Missing cutoff_date for {record.get('task_id')}")


def _quality_flags(
    record: dict[str, Any],
    forecast_origin: str,
    *,
    outcome_evidence_url: str | None = None,
    outcome_evidence_code: str | None = None,
) -> list[str]:
    """Detect data-quality issues relevant to paper bands."""
    flags: list[str] = []
    category = record.get("category")
    metadata = record.get("metadata") or {}

    if category == "A2" and record.get("variant") in {"F", "H"}:
        snapshot = metadata.get("fundamentals_snapshot_date")
        if isinstance(snapshot, list):
            snapshot_dates = [str(item) for item in snapshot]
        elif snapshot:
            snapshot_dates = [str(snapshot)]
        else:
            snapshot_dates = []
        for snapshot_date in snapshot_dates:
            if snapshot_date > forecast_origin:
                flags.append("fundamentals_after_origin")
                break
        if metadata.get("fundamentals_match_mode") == "prototype_fallback_nearest":
            flags.append("prototype_fallback_fundamentals")
        source = str(metadata.get("fundamentals_source") or metadata.get("source") or "")
        if "yahoo" in source.lower() and metadata.get("fundamentals_source_tier") != "official_filing":
            flags.append("non_pit_fundamentals")

    if category in {"B", "C"}:
        has_evidence = bool(
            metadata.get("outcome_evidence_url")
            or metadata.get("outcome_evidence_code")
            or outcome_evidence_url
            or outcome_evidence_code
        )
        if not has_evidence:
            flags.append("missing_outcome_evidence")
    if category == "C":
        tier = str(metadata.get("fundamentals_source_tier") or "")
        source = str(metadata.get("fundamentals_source") or metadata.get("source") or "")
        if (tier and tier != "official_filing") or "yahoo" in source.lower():
            flags.append("non_pit_fundamentals")

    return sorted(set(flags))


def infer_temporal_fields(
    record: dict[str, Any],
    *,
    outcome_available_at: str | None = None,
    forecast_origin: str | None = None,
    outcome_evidence_url: str | None = None,
    outcome_evidence_code: str | None = None,
) -> dict[str, Any]:
    """Infer forecast_origin / outcome_available_at from a seed record."""
    category = record.get("category")
    seed = record.get("seed") or {}
    metadata = record.get("metadata") or {}

    if category == "D":
        origin = forecast_origin or _cutoff_date(record)
        outcome = outcome_available_at or origin
        return {
            "forecast_origin": origin,
            "forecast_origin_source": "seed.cutoff_date",
            "outcome_available_at": outcome,
            "outcome_available_at_source": "synthetic_same_as_origin",
            "outcome_evidence_url": outcome_evidence_url,
            "outcome_evidence_code": outcome_evidence_code or "counterfactual_logic",
        }

    if category == "E":
        origin = forecast_origin or _cutoff_date(record)
        outcome = outcome_available_at or origin
        return {
            "forecast_origin": origin,
            "forecast_origin_source": "seed.cutoff_date",
            "outcome_available_at": outcome,
            "outcome_available_at_source": "formula_static",
            "outcome_evidence_url": outcome_evidence_url,
            "outcome_evidence_code": outcome_evidence_code or "formula_ground_truth",
        }

    if category == "B":
        origin = forecast_origin or str(seed.get("event_date") or seed.get("cutoff_date"))
        if outcome_available_at:
            outcome = outcome_available_at
            source = "provided"
        elif metadata.get("outcome_available_at"):
            outcome = str(metadata["outcome_available_at"])
            source = "metadata.outcome_available_at"
        else:
            outcome = add_calendar_days(origin, 1)
            source = "heuristic_event_plus_1d"
        return {
            "forecast_origin": origin,
            "forecast_origin_source": "seed.event_date",
            "outcome_available_at": outcome,
            "outcome_available_at_source": source,
            "outcome_evidence_url": outcome_evidence_url or metadata.get("outcome_evidence_url"),
            "outcome_evidence_code": outcome_evidence_code or metadata.get("outcome_evidence_code"),
        }

    if category == "C":
        origin = forecast_origin or str(seed.get("cutoff_date"))
        future_period = str(seed.get("report_period_future") or "")
        if outcome_available_at:
            outcome = outcome_available_at
            source = "provided"
        elif metadata.get("outcome_available_at"):
            outcome = str(metadata["outcome_available_at"])
            source = "metadata.outcome_available_at"
        elif future_period:
            lag = QUARTER_LAG_DAYS if len(future_period) == 10 else ANNUAL_LAG_DAYS
            outcome = add_calendar_days(future_period, lag)
            source = f"report_period_future_plus_{lag}d"
        else:
            outcome = add_calendar_days(origin, 90)
            source = "heuristic_cutoff_plus_90d"
        return {
            "forecast_origin": origin,
            "forecast_origin_source": "seed.cutoff_date",
            "outcome_available_at": outcome,
            "outcome_available_at_source": source,
            "outcome_evidence_url": outcome_evidence_url or metadata.get("outcome_evidence_url"),
            "outcome_evidence_code": outcome_evidence_code or metadata.get("outcome_evidence_code"),
        }

    if category == "A1":
        origin = forecast_origin or str(seed.get("cutoff_date"))
        ground_truth = record.get("ground_truth") or {}
        primary_window = int(
            ground_truth.get("primary_eval_window_days")
            or seed.get("primary_eval_window_days")
            or metadata.get("panel_horizon_days")
            or A1_OUTCOME_HORIZON_DAYS
        )
        observed_days = ground_truth.get("forward_trading_days") or metadata.get(
            "forward_trading_days"
        ) or {}
        observed = observed_days.get(str(primary_window))
        if outcome_available_at:
            outcome = outcome_available_at
            source = "provided"
        elif observed:
            outcome = str(observed)
            source = "observed_forward_trading_day"
        else:
            outcome = add_calendar_days(origin, primary_window)
            source = f"modeled_cutoff_plus_{primary_window}d"
        return {
            "forecast_origin": origin,
            "forecast_origin_source": "seed.cutoff_date",
            "outcome_available_at": outcome,
            "outcome_available_at_source": source,
            "outcome_evidence_url": outcome_evidence_url,
            "outcome_evidence_code": outcome_evidence_code or "price_forward_close",
        }

    if category == "A2":
        origin = forecast_origin or str(seed.get("cutoff_date"))
        window = int(seed.get("prediction_window_days") or A2_PREDICTION_WINDOW_DAYS)
        observed = metadata.get("outcome_trading_day")
        if outcome_available_at:
            outcome = outcome_available_at
            source = "provided"
        elif observed:
            outcome = str(observed)
            source = "observed_forward_trading_day"
        else:
            outcome = add_calendar_days(origin, window)
            source = f"modeled_cutoff_plus_{window}d"
        return {
            "forecast_origin": origin,
            "forecast_origin_source": "seed.cutoff_date",
            "outcome_available_at": outcome,
            "outcome_available_at_source": source,
            "outcome_evidence_url": outcome_evidence_url,
            "outcome_evidence_code": outcome_evidence_code or "price_forward_return",
        }

    raise ValueError(f"Unsupported category for temporal inference: {category}")


def classify_paper_band(
    record: dict[str, Any],
    forecast_origin: str,
    outcome_available_at: str | None,
    config: PaperExperimentConfig = DEFAULT_EXPERIMENT_CONFIG,
) -> tuple[str, str]:
    """Classify a record into paper_band with an audit reason."""
    category = record.get("category")
    if category == "D":
        return "D", "category_D_counterfactual"
    if category == "E":
        return "E", "category_E_formula"

    if outcome_available_at in (None, "", "pending"):
        if parse_iso_date(forecast_origin) >= parse_iso_date(config.experiment_as_of):
            return "T3", "forecast_origin_on_or_after_experiment_as_of_pending_outcome"
        return "quarantine", "missing_outcome_available_at"

    origin = parse_iso_date(forecast_origin)
    outcome = parse_iso_date(outcome_available_at)
    t1_outcome_max = parse_iso_date(config.t1_outcome_max)
    t2_origin_min = parse_iso_date(config.t2_origin_min)
    t2_outcome_max = parse_iso_date(config.t2_outcome_max)
    experiment_as_of = parse_iso_date(config.experiment_as_of)

    if origin >= experiment_as_of:
        return "T3", "forecast_origin_on_or_after_experiment_as_of"

    if outcome <= t1_outcome_max:
        return "T1", f"outcome_available_at<={config.t1_outcome_max}"

    if origin >= t2_origin_min and outcome <= t2_outcome_max:
        return "T2", (
            f"forecast_origin>={config.t2_origin_min} and "
            f"outcome_available_at<={config.t2_outcome_max}"
        )

    return "quarantine", "outside_T1_T2_T3_windows"


def build_index_row(
    record: dict[str, Any],
    *,
    config: PaperExperimentConfig = DEFAULT_EXPERIMENT_CONFIG,
    review_status: str = "draft",
    outcome_available_at: str | None = None,
    forecast_origin: str | None = None,
    outcome_evidence_url: str | None = None,
    outcome_evidence_code: str | None = None,
    quality_flags: list[str] | None = None,
) -> dict[str, Any]:
    """Build one task-temporal-index row for a seed record."""
    temporal = infer_temporal_fields(
        record,
        outcome_available_at=outcome_available_at,
        forecast_origin=forecast_origin,
        outcome_evidence_url=outcome_evidence_url,
        outcome_evidence_code=outcome_evidence_code,
    )
    origin = temporal["forecast_origin"]
    outcome = temporal["outcome_available_at"]
    flags = sorted(
        set(
            (quality_flags or [])
            + _quality_flags(
                record,
                origin,
                outcome_evidence_url=outcome_evidence_url or temporal.get("outcome_evidence_url"),
                outcome_evidence_code=outcome_evidence_code or temporal.get("outcome_evidence_code"),
            )
        )
    )
    availability_source = str(temporal.get("outcome_available_at_source") or "")
    if availability_source.startswith(("heuristic_", "modeled_")):
        flags = sorted(set(flags + ["modeled_outcome_availability"]))
    paper_band, reason = classify_paper_band(record, origin, outcome, config)

    if "fundamentals_after_origin" in flags and paper_band == "T2":
        paper_band = "quarantine"
        reason = "fundamentals_after_origin"

    official_temporal_eligible = not any(
        flag in {
            "fundamentals_after_origin",
            "missing_outcome_evidence",
            "modeled_outcome_availability",
            "non_pit_fundamentals",
            "official_disclosure_lookup_failed",
            "official_event_lookup_failed",
            "missing_event_evidence",
            "missing_forward_trading_day",
        }
        for flag in flags
    )

    row = {
        "task_id": record["task_id"],
        "category": record.get("category"),
        "variant": record.get("variant"),
        "hf_config": _hf_config(record),
        "forecast_origin": origin,
        "forecast_origin_source": temporal["forecast_origin_source"],
        "outcome_available_at": outcome,
        "outcome_available_at_source": temporal["outcome_available_at_source"],
        "outcome_evidence_url": temporal.get("outcome_evidence_url"),
        "outcome_evidence_code": temporal.get("outcome_evidence_code"),
        "paper_band": paper_band,
        "paper_band_reason": reason,
        "review_status": review_status,
        "quality_flags": flags,
        "official_temporal_eligible": official_temporal_eligible,
        "backbone_training_cutoff": config.backbone_training_cutoff,
        "guard_days": config.guard_days,
        "experiment_as_of": config.experiment_as_of,
        "legacy_time_band": record.get("time_band"),
    }
    return row


def load_temporal_index(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load temporal index rows keyed by task_id."""
    file_path = Path(path)
    if not file_path.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    with file_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            rows[row["task_id"]] = row
    return rows


def merge_index_by_task_id(
    records: list[dict[str, Any]],
    index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach paper temporal fields from index onto seed records."""
    merged: list[dict[str, Any]] = []
    for record in records:
        row = dict(record)
        temporal = index.get(record["task_id"])
        if temporal:
            row["paper_temporal"] = temporal
            for field in TEMPORAL_FLATTEN_FIELDS:
                if field in temporal:
                    row[field] = temporal[field]
        merged.append(row)
    return merged


def write_temporal_index(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write temporal index JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
