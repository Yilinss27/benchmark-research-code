#!/usr/bin/env python3
"""Lightweight validator for benchmark-research dataset structure."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = {
    "task_id",
    "category",
    "variant",
    "time_band",
    "status",
    "seed",
    "prompt",
    "expected_output",
    "ground_truth",
    "metadata",
}

REQUIRED_PATHS = [
    "README.md",
    "manifest.json",
    "docs/schema.md",
    "docs/task_cards.md",
    "prompts/a1_valuation.txt",
    "prompts/a2_ranking_f.txt",
    "prompts/a2_ranking_t.txt",
    "prompts/a2_ranking_h.txt",
    "prompts/b_event.txt",
    "prompts/c_financial_metric.txt",
    "prompts/d_counterfactual.txt",
    "prompts/e_formula.txt",
]

READY_FILES = [
    "seeds/a1_valuation.jsonl",
    "seeds/a2_fundamentals.jsonl",
    "seeds/a2_technical.jsonl",
    "seeds/a2_hybrid.jsonl",
    "seeds/b_event.jsonl",
    "seeds/c_financial_metric.jsonl",
    "seeds/d_counterfactual.jsonl",
    "seeds/e_formula.jsonl",
]

TEMPLATE_GLOB = "seeds/templates/*.jsonl"
TIME_BANDS = {"T1", "T2", "T3"}


def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL rows from a file."""
    rows = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{i} invalid JSON: {exc}") from exc
    return rows


def validate() -> list[str]:
    """Validate repository structure and seed records."""
    errors: list[str] = []
    root = Path(__file__).resolve().parents[1]
    task_ids: list[str] = []

    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            errors.append(f"Missing required file: {rel}")

    for rel in READY_FILES:
        if not (root / rel).exists():
            errors.append(f"Missing ready seed file: {rel}")

    for path in sorted(root.glob("seeds/**/*.jsonl")):
        rel = path.relative_to(root).as_posix()
        for i, row in enumerate(load_jsonl(path), 1):
            prefix = f"{rel}:{i}"
            missing = REQUIRED_FIELDS - row.keys()
            if missing:
                errors.append(f"{prefix} missing fields: {sorted(missing)}")

            metadata = row.get("metadata", {})
            if "is_template" not in metadata:
                errors.append(f"{prefix} metadata.is_template missing")

            task_ids.append(row["task_id"])

            if row["category"] == "D":
                series = row["seed"].get("historical_price_series", [])
                if len(series) != 30:
                    errors.append(f"{prefix} D historical_price_series must have 30 values, got {len(series)}")
                gt = row.get("ground_truth") or {}
                expected = row["seed"].get("expected_logic_direction")
                if gt.get("logic_direction") != expected:
                    errors.append(f"{prefix} D logic_direction mismatch with expected_logic_direction")

            if row["category"] == "A2":
                n = len(row["seed"].get("stock_list", []))
                if n < 6:
                    errors.append(f"{prefix} A2 stock_list N={n} < 6")

    if len(task_ids) != len(set(task_ids)):
        dup = {x for x in task_ids if task_ids.count(x) > 1}
        errors.append(f"Duplicate task_id values: {sorted(dup)}")

    for rel in READY_FILES:
        path = root / rel
        content = path.read_text(encoding="utf-8")
        if "PLACEHOLDER" in content:
            errors.append(f"{rel} contains PLACEHOLDER (not allowed in ready seeds)")

        for i, row in enumerate(load_jsonl(path), 1):
            prefix = f"{rel}:{i}"
            if row["status"] != "ready":
                errors.append(f"{prefix} status must be ready")
            if row.get("time_band") not in TIME_BANDS:
                errors.append(f"{prefix} time_band must be one of {sorted(TIME_BANDS)}")
            if not row.get("cutoff_date"):
                errors.append(f"{prefix} top-level cutoff_date missing")
            if row["metadata"].get("is_template") is not False:
                errors.append(f"{prefix} metadata.is_template must be false")
            temporal = row["metadata"].get("temporal_split")
            if not temporal:
                errors.append(f"{prefix} metadata.temporal_split missing")
            else:
                if temporal.get("time_band") != row.get("time_band"):
                    errors.append(f"{prefix} metadata.temporal_split.time_band mismatch")
                if temporal.get("cutoff_date") != row.get("cutoff_date"):
                    errors.append(f"{prefix} metadata.temporal_split.cutoff_date mismatch")
                for key in ("model_training_cutoff", "reference_current_date", "rule"):
                    if not temporal.get(key):
                        errors.append(f"{prefix} metadata.temporal_split.{key} missing")
            if row["ground_truth"] is None:
                errors.append(f"{prefix} ground_truth must not be null")
            if row["category"] == "E" and row["ground_truth"].get("correct_answer") is None:
                errors.append(f"{prefix} E ground_truth.correct_answer must be float")

    for path in sorted(root.glob(TEMPLATE_GLOB)):
        rel = path.relative_to(root).as_posix()
        for i, row in enumerate(load_jsonl(path), 1):
            prefix = f"{rel}:{i}"
            if row["status"] != "template":
                errors.append(f"{prefix} status must be template")
            if row["metadata"].get("is_template") is not True:
                errors.append(f"{prefix} metadata.is_template must be true")

    return errors


def main() -> int:
    """Run validation and print a summary."""
    errors = validate()
    if errors:
        print("VALIDATION FAILED")
        for err in errors:
            print(f"  - {err}")
        return 1

    root = Path(__file__).resolve().parents[1]
    template_count = sum(len(load_jsonl(p)) for p in root.glob(TEMPLATE_GLOB))
    ready_counts: dict[str, int] = {}
    for rel in READY_FILES:
        ready_counts[rel] = len(load_jsonl(root / rel))

    print("VALIDATION PASSED")
    print(f"  templates: {template_count}")
    for rel, count in ready_counts.items():
        print(f"  {rel}: {count}")
    print(f"  total ready: {sum(ready_counts.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
