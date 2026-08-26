#!/usr/bin/env python3
"""Generate the aligned T1/T2 panel from configs/aligned_panel_v1.json."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_generator import generate_panel


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Generate aligned_panel_v1 seeds.")
    parser.add_argument(
        "--config",
        default="configs/aligned_panel_v1.json",
        help="Panel config JSON path.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing output_dir before generation.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    """Load panel config."""
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    """Generate both cutoffs into seeds/aligned."""
    args = parse_args()
    config = load_config(ROOT / args.config)
    output_dir = ROOT / config["output_dir"]
    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cutoffs = [config["cutoffs"]["T1"], config["cutoffs"]["T2"]]
    reports: list[dict[str, Any]] = []
    for cutoff in cutoffs:
        summary = generate_panel(
            cutoff,
            markets=config["markets"],
            tasks=config["tasks"],
            horizon_days=int(config["horizon_days"]),
            provider_name=config.get("provider", "yahoo"),
            output_dir=output_dir,
            panel_id=config["panel_id"],
            append=True,
            replace=True,
        )
        reports.append(summary)
        print(
            json.dumps(
                {
                    "cutoff_date": cutoff,
                    "generated_total": summary["generated_total"],
                    "added_total": summary["added_total"],
                },
                ensure_ascii=False,
            )
        )

    manifest_path = output_dir / "panel_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "config": config,
                "cutoffs": cutoffs,
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Combined seed file for runner smoke tests.
    combined = output_dir / "all.jsonl"
    chunks: list[str] = []
    for rel in config.get("outputs", {}).values():
        path = ROOT / rel
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if text and not text.endswith("\n"):
                text += "\n"
            chunks.append(text)
    combined.write_text("".join(chunks), encoding="utf-8")

    print(
        json.dumps(
            {"output_dir": str(output_dir), "cutoffs": cutoffs, "combined": str(combined)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
