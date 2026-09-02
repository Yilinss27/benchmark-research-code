#!/usr/bin/env python3
"""Validate the frozen Path B / v2 ledger, evidence packages, and export."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "artifacts/hf_736273f"
OUTPUT = ROOT / "hf_dataset_path_b_v2"
LEDGER = ROOT / "calibration/review_ledger_v2.csv"
PACKAGES = ROOT / "calibration/evidence_packages_v2.jsonl"
MANIFEST = ROOT / "calibration/path_b_v2_manifest.json"
EXCLUSIONS = ROOT / "calibration/path_b_v2_exclusions.csv"
ATTESTATIONS = ROOT / "calibration/review_attestations_v2.csv"
REVIEW_CONTRACT = ROOT / "configs/path_b_v2_review_contract.json"
TEMPORAL_INDEX = ROOT / "data/task_temporal_index.jsonl"
ATTESTATION_FIELDS = (
    "task_id",
    "decision",
    "reviewer_id",
    "review_method",
    "reviewed_at",
    "evidence_package_sha256",
    "review_notes",
    "attestation_sha256",
)
BLOCKING_FLAGS = {
    "fundamentals_after_origin",
    "heuristic_outcome_availability",
    "missing_event_evidence",
    "missing_outcome_evidence",
    "modeled_outcome_availability",
    "non_pit_fundamentals",
    "official_disclosure_lookup_failed",
}
EXPECTED_EXCLUDED = {
    "data/a2_f/train.jsonl": "2258a0c7ef13c93da1d995b7d8739178b4dff141c0082603f0d6a2ba7f43f4d0",
    "data/a2_h/train.jsonl": "c7fe4a2f2c38a729c4cdd46b99ce59c7eb496ba37f7409d561ac5f8687ed257d",
    "data/c/train.jsonl": "2698e0fda7c3b35312a183f1a117bd68398cbe372fcdf69b56b9fa28abc9ee02",
    "data/d/train.jsonl": "a0c339d0ada9e05472173ceaa7580a490f1f845651321bd496d8f4efb57f1527",
    "data/e/train.jsonl": "bc4ee2f25b2e68f1e15603f52621320c4def26f7890abeae4d3b8205ac0b77a1",
}
def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_flags(*values: Any) -> set[str]:
    flags: set[str] = set()
    for value in values:
        if isinstance(value, str):
            flags.update(part.strip() for part in value.split(",") if part.strip())
        elif isinstance(value, list):
            flags.update(str(part).strip() for part in value if str(part).strip())
    return flags


def attestation_hash(row: dict[str, str]) -> str:
    return canonical_sha(
        {field: row.get(field, "") for field in ATTESTATION_FIELDS if field != "attestation_sha256"}
    )


def validate() -> list[str]:
    errors: list[str] = []
    for path in (LEDGER, PACKAGES, MANIFEST, EXCLUSIONS, ATTESTATIONS, REVIEW_CONTRACT):
        if not path.exists():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    for rel, expected in EXPECTED_EXCLUDED.items():
        actual = sha256_file(BASELINE / rel)
        if actual != expected:
            errors.append(f"frozen excluded file changed: {rel}: {actual}")

    ledger = load_csv(LEDGER)
    packages = load_jsonl(PACKAGES)
    attestations = load_csv(ATTESTATIONS)
    attestation_by_id = {row["task_id"]: row for row in attestations}
    contract = json.loads(REVIEW_CONTRACT.read_text(encoding="utf-8"))
    review_methods = {str(value) for value in contract.get("review_method_enum", [])}
    if len(attestation_by_id) != len(attestations):
        errors.append("attestations contain duplicate task_ids")
    package_by_id = {row["task_id"]: row for row in packages}
    ledger_ids = [row["task_id"] for row in ledger]
    if len(ledger) != 543 or len(set(ledger_ids)) != 543:
        errors.append(f"ledger must have 543 unique rows, got {len(ledger)}/{len(set(ledger_ids))}")

    baseline_ids: set[str] = set()
    baseline_by_id: dict[str, dict[str, Any]] = {}
    for config in ("a1", "a2_t", "b"):
        for baseline_row in load_jsonl(BASELINE / f"data/{config}/train.jsonl"):
            baseline_ids.add(baseline_row["task_id"])
            baseline_by_id[baseline_row["task_id"]] = baseline_row
    if set(ledger_ids) != baseline_ids:
        errors.append("ledger task_ids do not exactly match frozen A1+A2-T+B scope")
    unknown_attestations = set(attestation_by_id) - baseline_ids
    if unknown_attestations:
        errors.append(f"attestations contain unknown task_ids: {sorted(unknown_attestations)}")
    temporal_by_id = {
        row["task_id"]: row for row in load_jsonl(TEMPORAL_INDEX)
        if row.get("task_id") in baseline_ids
    }
    snapshot_paths: set[str] = set()

    for row in ledger:
        task_id = row["task_id"]
        if row["review_status"] not in {"reviewed", "draft"}:
            errors.append(f"{task_id}: invalid review_status")
        package = package_by_id.get(task_id)
        if package is None:
            errors.append(f"{task_id}: missing evidence package")
            continue
        actual_package_sha = canonical_sha(
            sorted(
                package.get("items", []),
                key=lambda item: (str(item["kind"]), str(item["cache_key"])),
            )
        )
        if actual_package_sha != row["evidence_package_sha256"]:
            errors.append(f"{task_id}: evidence package hash mismatch")
        if actual_package_sha != package.get("evidence_package_sha256"):
            errors.append(f"{task_id}: package sidecar hash mismatch")
        for item in package.get("items", []):
            snapshot_path = item.get("snapshot_path")
            if item.get("kind") == "baseline_task_identity":
                if snapshot_path:
                    errors.append(f"{task_id}: baseline identity must not claim a snapshot file")
                continue
            if not snapshot_path:
                errors.append(f"{task_id}: evidence item lacks content-addressed snapshot_path")
                continue
            snapshot_paths.add(str(snapshot_path))
            expected_path = (
                f"evidence/snapshots/{str(item['snapshot_sha256'])[:2]}/"
                f"{item['snapshot_sha256']}"
            )
            if snapshot_path != expected_path:
                errors.append(f"{task_id}: snapshot_path is not content-addressed")
                continue
            local_snapshot = OUTPUT / snapshot_path
            if not local_snapshot.is_file():
                errors.append(f"{task_id}: snapshot file missing: {snapshot_path}")
            elif sha256_file(local_snapshot) != item["snapshot_sha256"]:
                errors.append(f"{task_id}: snapshot file SHA mismatch: {snapshot_path}")

        reviewed = row["review_status"] == "reviewed"
        eligible = row["official_temporal_eligible"] == "true"
        if reviewed != eligible:
            errors.append(f"{task_id}: reviewed/eligible mismatch")
        if reviewed:
            attestation = attestation_by_id.get(task_id)
            if attestation is None:
                errors.append(f"{task_id}: reviewed row lacks independent attestation")
            else:
                if attestation.get("decision") != "reviewed":
                    errors.append(f"{task_id}: attestation decision is not reviewed")
                if attestation.get("reviewer_id") != row["reviewer_id"]:
                    errors.append(f"{task_id}: reviewer_id does not match attestation")
                if attestation.get("review_method") != row["review_method"]:
                    errors.append(f"{task_id}: review_method does not match attestation")
                if row["review_method"] not in review_methods:
                    errors.append(f"{task_id}: review_method is not in formal contract")
                if attestation.get("evidence_package_sha256") != actual_package_sha:
                    errors.append(f"{task_id}: attestation package hash mismatch")
                if attestation_hash(attestation) != attestation.get("attestation_sha256"):
                    errors.append(f"{task_id}: attestation hash mismatch")
            if row["exclusion_reason_code"]:
                errors.append(f"{task_id}: reviewed row has exclusion reason")
            if row["event_evidence_status"] not in {"reviewed", "not_applicable"}:
                errors.append(f"{task_id}: reviewed row lacks event evidence")
            if row["price_evidence_status"] not in {"reviewed", "not_applicable"}:
                errors.append(f"{task_id}: reviewed row lacks price evidence")
            if not row["reviewed_at"]:
                errors.append(f"{task_id}: reviewed row lacks reviewed_at")
            else:
                reviewed_at = datetime.fromisoformat(
                    row["reviewed_at"].replace("Z", "+00:00")
                )
                for item in package["items"]:
                    if item.get("fetched_at"):
                        fetched_at = datetime.fromisoformat(
                            str(item["fetched_at"]).replace("Z", "+00:00")
                        )
                        if reviewed_at <= fetched_at:
                            errors.append(
                                f"{task_id}: reviewed_at is not later than fetched_at"
                            )
                            break
            active_flags = normalize_flags(
                baseline_by_id.get(task_id, {}).get("quality_flags"),
                temporal_by_id.get(task_id, {}).get("quality_flags"),
            ) & BLOCKING_FLAGS
            if active_flags:
                errors.append(f"{task_id}: reviewed row has blocking flags: {sorted(active_flags)}")
        else:
            if not row["exclusion_reason_code"]:
                errors.append(f"{task_id}: draft row lacks exclusion reason")
            if row["reviewed_at"]:
                errors.append(f"{task_id}: draft row must not have reviewed_at")
            if row["reviewer_id"] or row["review_method"]:
                errors.append(f"{task_id}: draft row must not claim reviewer or review_method")
        if not row["review_notes"] or row["review_notes"].strip().lower() == "ok":
            errors.append(f"{task_id}: invalid review_notes")

    if set(package_by_id) != set(ledger_ids):
        errors.append("evidence package task_ids do not match ledger")
    reviewed_ids = {row["task_id"] for row in ledger if row["review_status"] == "reviewed"}
    if set(attestation_by_id) != reviewed_ids:
        errors.append("attestation task_ids must exactly match reviewed ledger rows")

    expected_counts = {"a1": 244, "a2_t": 161, "b_earnings": 125}
    export_ids: set[str] = set()
    for config, expected in expected_counts.items():
        rows = load_jsonl(OUTPUT / f"data/{config}/train.jsonl")
        if len(rows) != expected:
            errors.append(f"{config}: expected {expected}, got {len(rows)}")
        export_ids.update(row["task_id"] for row in rows)
        for row in rows:
            if row.get("scope_role") not in {"temporal_t1_t2", "both"}:
                errors.append(f"{row['task_id']}: invalid exported scope_role")
    if len(export_ids) != 530:
        errors.append(f"export must have 530 unique rows, got {len(export_ids)}")
    if any(
        (OUTPUT / f"data/{config}/train.jsonl").exists()
        for config in ("a2_f", "a2_h", "c", "d", "e", "b_macro")
    ):
        errors.append("excluded config present in Path B export")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("baseline", {}).get("commit") != "736273f4d211c0c31fab43da1fbfd49509598e85":
        errors.append("manifest baseline commit mismatch")
    if manifest.get("baseline", {}).get("tree") != "2ce364a577336f8bd88a960397ed7a692fb1a7b2":
        errors.append("manifest baseline tree mismatch")
    if manifest.get("review_methods") != sorted(review_methods):
        errors.append("manifest review_method enum does not match formal contract")
    if manifest.get("snapshot_count") != len(snapshot_paths):
        errors.append("manifest snapshot_count mismatch")
    for rel, expected in manifest.get("files", {}).items():
        path = ROOT / rel
        if rel.startswith("data/"):
            path = OUTPUT / rel
        if not path.exists() or sha256_file(path) != expected:
            errors.append(f"manifest file hash mismatch: {rel}")
        output_copy = OUTPUT / rel
        if rel.startswith(("calibration/", "configs/")) and (
            not output_copy.exists() or sha256_file(output_copy) != expected
        ):
            errors.append(f"exported package file hash mismatch: {rel}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("PATH B V2 VALIDATION FAILED")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PATH B V2 VALIDATION PASSED")
    print("  ledger: 543")
    print("  T1/T2 candidates: 530")
    print("  frozen excluded files: 5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
