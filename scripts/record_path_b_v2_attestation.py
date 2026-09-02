#!/usr/bin/env python3
"""Record one explicit Path B / v2 manual review attestation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "calibration/evidence_packages_v2.jsonl"
ATTESTATIONS = ROOT / "calibration/review_attestations_v2.csv"
CONTRACT = ROOT / "configs/path_b_v2_review_contract.json"
OUTPUT = ROOT / "hf_dataset_path_b_v2"
FIELDS = (
    "task_id",
    "decision",
    "reviewer_id",
    "review_method",
    "reviewed_at",
    "evidence_package_sha256",
    "review_notes",
    "attestation_sha256",
)


def canonical_sha(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--review-method", required=True)
    parser.add_argument("--reviewed-at", required=True, help="Timezone-aware RFC3339 timestamp")
    parser.add_argument("--notes", required=True)
    parser.add_argument(
        "--confirm-manual-review",
        action="store_true",
        help="Confirm that the reviewer opened and checked every applicable snapshot",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_manual_review:
        raise SystemExit("--confirm-manual-review is required; scripts cannot attest automatically")
    if not args.notes.strip() or args.notes.strip().lower() == "ok":
        raise SystemExit("--notes must describe what was manually checked")
    try:
        reviewed_at = datetime.fromisoformat(args.reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit("--reviewed-at must be RFC3339") from exc
    if reviewed_at.tzinfo is None:
        raise SystemExit("--reviewed-at must include a timezone")

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    allowed = set(contract.get("review_method_enum", []))
    if args.review_method not in allowed:
        raise SystemExit(
            f"review method is not in the formal contract: {args.review_method!r}; "
            f"allowed={sorted(allowed)}"
        )

    packages = {
        row["task_id"]: row
        for line in PACKAGES.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for row in [json.loads(line)]
    }
    package = packages.get(args.task_id)
    if package is None:
        raise SystemExit(f"unknown task_id: {args.task_id}")
    for item in package["items"]:
        if not item.get("snapshot_path"):
            continue
        path = OUTPUT / item["snapshot_path"]
        if not path.is_file():
            raise SystemExit(f"snapshot missing: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["snapshot_sha256"]:
            raise SystemExit(f"snapshot SHA mismatch: {path}")
        fetched_at = item.get("fetched_at")
        if fetched_at:
            fetched = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
            if reviewed_at <= fetched:
                raise SystemExit("--reviewed-at must be later than every snapshot fetched_at")

    row = {
        "task_id": args.task_id,
        "decision": "reviewed",
        "reviewer_id": args.reviewer_id,
        "review_method": args.review_method,
        "reviewed_at": args.reviewed_at,
        "evidence_package_sha256": package["evidence_package_sha256"],
        "review_notes": args.notes.strip(),
    }
    row["attestation_sha256"] = canonical_sha(row)

    existing: dict[str, dict[str, str]] = {}
    if ATTESTATIONS.exists():
        with ATTESTATIONS.open(encoding="utf-8", newline="") as handle:
            existing = {item["task_id"]: item for item in csv.DictReader(handle)}
    existing[args.task_id] = row
    with ATTESTATIONS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(existing[key] for key in sorted(existing))
    print(f"Recorded attestation for {args.task_id}: {row['attestation_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
