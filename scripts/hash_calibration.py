#!/usr/bin/env python3
"""Compute SHA-256 for the leakage calibration package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Return hex digest for a file."""
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    """Print calibration manifest with SHA-256."""
    parser = argparse.ArgumentParser(description="Hash leakage calibration package.")
    parser.add_argument(
        "--calibration",
        default="calibration/leakage_probe_v1.json",
        help="Calibration JSON path.",
    )
    parser.add_argument(
        "--output",
        default="calibration/leakage_probe_manifest.json",
        help="Manifest output path.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    calibration_path = root / args.calibration
    manifest = {
        "package": "leakage_probe_v1",
        "calibration_file": str(calibration_path.relative_to(root)),
        "calibration_sha256": sha256_file(calibration_path),
        "record_count": len(json.loads(calibration_path.read_text(encoding="utf-8"))),
        "review_status": "draft",
        "notes": "Independent calibration set for cutoff vs unrestricted experiments.",
    }
    output_path = root / args.output
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
