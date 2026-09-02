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
EXPECTED_EXCLUDED = {
    "data/a2_f/train.jsonl": "2258a0c7ef13c93da1d995b7d8739178b4dff141c0082603f0d6a2ba7f43f4d0",
    "data/a2_h/train.jsonl": "c7fe4a2f2c38a729c4cdd46b99ce59c7eb496ba37f7409d561ac5f8687ed257d",
    "data/c/train.jsonl": "2698e0fda7c3b35312a183f1a117bd68398cbe372fcdf69b56b9fa28abc9ee02",
    "data/d/train.jsonl": "a0c339d0ada9e05472173ceaa7580a490f1f845651321bd496d8f4efb57f1527",
    "data/e/train.jsonl": "bc4ee2f25b2e68f1e15603f52621320c4def26f7890abeae4d3b8205ac0b77a1",
}
REVIEW_METHODS = {
    "manual_first_party_snapshot_review",
    "manual_price_snapshot_review",
    "manual_event_and_price_review",
    "excluded_unfetchable_official_source",
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


def validate() -> list[str]:
    errors: list[str] = []
    for path in (LEDGER, PACKAGES, MANIFEST, EXCLUSIONS):
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
    package_by_id = {row["task_id"]: row for row in packages}
    ledger_ids = [row["task_id"] for row in ledger]
    if len(ledger) != 543 or len(set(ledger_ids)) != 543:
        errors.append(f"ledger must have 543 unique rows, got {len(ledger)}/{len(set(ledger_ids))}")

    baseline_ids: set[str] = set()
    for config in ("a1", "a2_t", "b"):
        baseline_ids.update(
            row["task_id"] for row in load_jsonl(BASELINE / f"data/{config}/train.jsonl")
        )
    if set(ledger_ids) != baseline_ids:
        errors.append("ledger task_ids do not exactly match frozen A1+A2-T+B scope")

    for row in ledger:
        task_id = row["task_id"]
        if row["review_status"] not in {"reviewed", "draft"}:
            errors.append(f"{task_id}: invalid review_status")
        if row["review_method"] not in REVIEW_METHODS:
            errors.append(f"{task_id}: invalid review_method")
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

        reviewed = row["review_status"] == "reviewed"
        eligible = row["official_temporal_eligible"] == "true"
        if reviewed != eligible:
            errors.append(f"{task_id}: reviewed/eligible mismatch")
        if reviewed:
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
        else:
            if not row["exclusion_reason_code"]:
                errors.append(f"{task_id}: draft row lacks exclusion reason")
            if row["reviewed_at"]:
                errors.append(f"{task_id}: draft row must not have reviewed_at")
        if not row["review_notes"] or row["review_notes"].strip().lower() == "ok":
            errors.append(f"{task_id}: invalid review_notes")

    if set(package_by_id) != set(ledger_ids):
        errors.append("evidence package task_ids do not match ledger")

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
    for rel, expected in manifest.get("files", {}).items():
        path = ROOT / rel
        if rel.startswith("data/"):
            path = OUTPUT / rel
        if not path.exists() or sha256_file(path) != expected:
            errors.append(f"manifest file hash mismatch: {rel}")
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
