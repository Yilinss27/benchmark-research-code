"""Manifest-driven, evidence-safe benchmark question generation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.assign_time_bands import update_row as update_temporal_band
from src.builders import a1_from_csv_builder as a1
from src.builders import a2_fundamentals_from_csv_builder as a2f
from src.builders import a2_hybrid_from_csv_builder as a2h
from src.builders import a2_technicals_from_csv_builder as a2t
from src.builders import b_event_from_csv_builder as b
from src.builders import c_financial_metric_from_csv_builder as c
from src.builders.a2_fundamentals_loader import (
    load_fundamentals_history,
    resolve_fundamentals_path,
)

SPEC_VERSION = "question_generation_v1"
SUPPORTED_TASKS = {"A1", "A2-F", "A2-T", "A2-H", "B", "C"}
SHA256_HEX_LENGTH = 64


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_sha(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(encoded)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no} must be a JSON object")
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def resolve_path(spec_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else spec_path.parent / path


def csv_values(path: Path, field: str) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or field not in reader.fieldnames:
            raise ValueError(f"{path} must contain a {field!r} column")
        return [str(row.get(field) or "").strip() for row in reader]


def require_task_ids(path: Path, field: str) -> set[str]:
    values = csv_values(path, field)
    if not values or any(not value for value in values):
        raise ValueError(f"{path} contains an empty {field}")
    return set(values)


def build_job(job: dict[str, Any], spec_path: Path) -> tuple[list[dict[str, Any]], list[str], list[Path]]:
    task_type = str(job.get("task_type") or "")
    if task_type not in SUPPORTED_TASKS:
        raise ValueError(f"unsupported task_type: {task_type!r}")
    market = str(job.get("market") or "CN_A")
    currency = str(job.get("currency") or "CNY")
    warnings: list[str] = []
    inputs: list[Path] = []

    if task_type == "A1":
        source = resolve_path(spec_path, str(job["input_csv"]))
        inputs.append(source)
        expected_ids = require_task_ids(source, "task_id")
        rows = a1.load_csv_rows(source)
        records = a1.build_records(
            rows,
            source_name=source.name,
            market=market,
            currency=currency,
            currency_unit=str(job.get("currency_unit") or "元"),
        )
    elif task_type == "B":
        source = resolve_path(spec_path, str(job["input_csv"]))
        inputs.append(source)
        expected_ids = require_task_ids(source, "event_id")
        rows = b.load_rows(source)
        unsupported = sorted(
            {row["event_subtype"].strip() for row in rows} - b.SUPPORTED_SUBTYPES
        )
        if unsupported:
            raise ValueError(f"{source} contains unsupported B subtypes: {unsupported}")
        template = b._read_prompt_template()
        records = [
            b.build_record(row, template, source.name, market=market, currency=currency)
            for row in rows
        ]
    elif task_type == "C":
        source = resolve_path(spec_path, str(job["input_csv"]))
        inputs.append(source)
        expected_ids = require_task_ids(source, "task_id")
        rows = c.load_rows(source)
        template = c._read_prompt_template()
        records = [
            c.build_record(row, template, source.name, market=market, currency=currency)
            for row in rows
        ]
    elif task_type in {"A2-T", "A2-H"}:
        prices = resolve_path(spec_path, str(job["price_series_csv"]))
        inputs.append(prices)
        expected_ids = require_task_ids(prices, "task_id")
        cohorts = a2t.load_price_series(prices)
        if task_type == "A2-T":
            records, warnings = a2t.build_records(
                cohorts,
                a2t._read_prompt_template(),
                prices.name,
                market=market,
                currency=currency,
            )
        else:
            fundamentals = resolve_path(spec_path, str(job["fundamentals_csv"]))
            inputs.append(fundamentals)
            fundamentals_path, path_warnings = resolve_fundamentals_path(str(fundamentals))
            history = load_fundamentals_history(fundamentals_path)
            records, warnings = a2h.build_records(
                cohorts,
                history,
                a2h._read_prompt_template(),
                fundamentals_path.name,
                prices.name,
                market=market,
                currency=currency,
            )
            warnings = path_warnings + warnings
    else:
        fundamentals = resolve_path(spec_path, str(job["fundamentals_csv"]))
        cohorts_path = resolve_path(spec_path, str(job["cohorts_csv"]))
        returns_path = resolve_path(spec_path, str(job["returns_csv"]))
        inputs.extend((fundamentals, cohorts_path, returns_path))
        expected_ids = require_task_ids(cohorts_path, "task_id")
        fundamentals_path, path_warnings = resolve_fundamentals_path(str(fundamentals))
        records, warnings = a2f.build_records(
            load_fundamentals_history(fundamentals_path),
            a2f.load_cohorts(cohorts_path),
            a2f.load_returns(returns_path),
            a2f._read_prompt_template(),
            fundamentals_path.name,
            market=market,
            currency=currency,
        )
        warnings = path_warnings + warnings

    actual_ids = {str(record["task_id"]) for record in records}
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        unexpected = sorted(actual_ids - expected_ids)
        raise ValueError(
            f"{task_type} did not preserve provided task_ids; "
            f"missing={missing[:10]}, unexpected={unexpected[:10]}"
        )
    incomplete = [
        str(record["task_id"])
        for record in records
        if record.get("status") != "ready"
    ]
    if incomplete and not bool(job.get("allow_incomplete", False)):
        raise ValueError(
            f"{task_type} produced non-ready records: {incomplete[:10]}; "
            "fix the inputs or set allow_incomplete=true for local inspection"
        )
    return records, warnings, inputs


def validate_published_at(value: str, context: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context}: published_at must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{context}: published_at must include a timezone")


def load_evidence(
    path: Path | None,
    *,
    output_dir: Path,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if path is None:
        return {}, []
    package_by_id: dict[str, dict[str, Any]] = {}
    packages: list[dict[str, Any]] = []
    for row_no, row in enumerate(read_jsonl(path), 1):
        task_id = str(row.get("task_id") or "")
        if not task_id or task_id in package_by_id:
            raise ValueError(f"{path}:{row_no} has empty or duplicate task_id")
        normalized_items: list[dict[str, Any]] = []
        for item_no, item in enumerate(row.get("items") or [], 1):
            context = f"{path}:{row_no}:items[{item_no}]"
            source_url = str(item.get("source_url") or "")
            published_at = str(item.get("published_at") or "")
            expected_sha = str(item.get("content_sha256") or item.get("snapshot_sha256") or "")
            snapshot_file = str(item.get("snapshot_file") or "")
            if not source_url.startswith(("https://", "http://")):
                raise ValueError(f"{context}: source_url must be HTTP(S)")
            validate_published_at(published_at, context)
            if len(expected_sha) != SHA256_HEX_LENGTH:
                raise ValueError(f"{context}: invalid SHA-256")
            source = resolve_path(path, snapshot_file)
            if not source.is_file():
                raise ValueError(f"{context}: snapshot_file does not exist: {source}")
            actual_sha = sha256_file(source)
            if actual_sha != expected_sha:
                raise ValueError(f"{context}: snapshot SHA mismatch")
            destination_rel = f"evidence/snapshots/{actual_sha[:2]}/{actual_sha}"
            destination = output_dir / destination_rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(source, destination)
            normalized_items.append(
                {
                    "kind": str(item.get("kind") or "source_snapshot"),
                    "source_url": source_url,
                    "published_at": published_at,
                    "snapshot_sha256": actual_sha,
                    "snapshot_path": destination_rel,
                }
            )
        ordered = sorted(
            normalized_items,
            key=lambda item: (item["kind"], item["source_url"], item["snapshot_sha256"]),
        )
        package = {
            "task_id": task_id,
            "items": ordered,
            "evidence_package_sha256": canonical_sha(ordered),
        }
        package_by_id[task_id] = package
        packages.append(package)
    return package_by_id, sorted(packages, key=lambda row: row["task_id"])


def stamp_record(
    record: dict[str, Any],
    *,
    package: dict[str, Any] | None,
    training_cutoff: str,
    current_date: str,
    input_hashes: dict[str, str],
) -> dict[str, Any]:
    row = update_temporal_band(record, training_cutoff, current_date)
    flags = set(row.get("quality_flags") or [])
    flags.add("manual_review_required")
    if package is None:
        flags.add("missing_generation_evidence")
    row["quality_flags"] = sorted(flags)
    row["review_status"] = "draft"
    row["official_temporal_eligible"] = False
    row["reviewer_id"] = ""
    row["review_method"] = ""
    row["reviewed_at"] = ""
    row["evidence_package_sha256"] = (
        package["evidence_package_sha256"] if package else ""
    )
    metadata = dict(row.get("metadata") or {})
    metadata["generation"] = {
        "schema_version": SPEC_VERSION,
        "input_sha256": input_hashes,
        "review_policy": "draft_until_independent_manual_attestation",
    }
    row["metadata"] = metadata
    return row


def generate(spec_path: Path, *, clean: bool = False) -> dict[str, Any]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != SPEC_VERSION:
        raise ValueError(f"schema_version must be {SPEC_VERSION!r}")
    output_dir = resolve_path(spec_path, str(spec["output_dir"]))
    resolved_output = output_dir.resolve()
    resolved_spec = spec_path.resolve()
    if clean and (
        resolved_output == Path(resolved_output.anchor)
        or resolved_spec == resolved_output
        or resolved_spec.is_relative_to(resolved_output)
    ):
        raise ValueError(
            f"refusing to clean output_dir that contains the spec or filesystem root: "
            f"{output_dir}"
        )
    if output_dir.exists() and clean:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    evidence_path = (
        resolve_path(spec_path, str(spec["evidence_jsonl"]))
        if spec.get("evidence_jsonl")
        else None
    )
    evidence_by_id, evidence_packages = load_evidence(
        evidence_path, output_dir=output_dir
    )
    strict_evidence = bool(spec.get("require_evidence", False))
    training_cutoff = str(spec.get("training_cutoff") or "2024-06-30")
    current_date = str(spec.get("current_date") or "2026-08-17")
    generated_ids: set[str] = set()
    outputs: dict[str, str] = {}
    jobs_summary: list[dict[str, Any]] = []

    for job in spec.get("jobs") or []:
        records, warnings, input_paths = build_job(job, spec_path)
        input_hashes = {str(path): sha256_file(path) for path in input_paths}
        stamped: list[dict[str, Any]] = []
        for record in records:
            task_id = str(record["task_id"])
            if task_id in generated_ids:
                raise ValueError(f"duplicate task_id across jobs: {task_id}")
            generated_ids.add(task_id)
            package = evidence_by_id.get(task_id)
            if strict_evidence and package is None:
                raise ValueError(f"{task_id}: evidence package is required")
            stamped.append(
                stamp_record(
                    record,
                    package=package,
                    training_cutoff=training_cutoff,
                    current_date=current_date,
                    input_hashes=input_hashes,
                )
            )
        relative_output = Path(str(job["output_jsonl"]))
        if relative_output.is_absolute() or ".." in relative_output.parts:
            raise ValueError("output_jsonl must stay inside output_dir")
        output_path = output_dir / relative_output
        if output_path.exists() and not clean:
            raise FileExistsError(f"output already exists; use --clean: {output_path}")
        write_jsonl(output_path, stamped)
        outputs[relative_output.as_posix()] = sha256_file(output_path)
        jobs_summary.append(
            {
                "task_type": job["task_type"],
                "output_jsonl": relative_output.as_posix(),
                "records": len(stamped),
                "warnings": warnings,
                "input_sha256": input_hashes,
            }
        )

    unknown_evidence = sorted(set(evidence_by_id) - generated_ids)
    if unknown_evidence:
        raise ValueError(f"evidence contains unknown task_ids: {unknown_evidence[:10]}")
    packages_path = output_dir / "calibration/evidence_packages.jsonl"
    write_jsonl(packages_path, evidence_packages)
    outputs["calibration/evidence_packages.jsonl"] = sha256_file(packages_path)
    manifest = {
        "schema_version": SPEC_VERSION,
        "spec_sha256": sha256_file(spec_path),
        "record_count": len(generated_ids),
        "unique_task_ids": len(generated_ids),
        "review_status": {"draft": len(generated_ids), "reviewed": 0},
        "evidence_package_count": len(evidence_packages),
        "jobs": jobs_summary,
        "files": outputs,
    }
    manifest_path = output_dir / "generation_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = generate(args.spec, clean=args.clean)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
