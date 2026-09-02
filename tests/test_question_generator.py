from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.question_generator import generate


class QuestionGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_a1_csv(self, task_id: str = "A1-TEST-00001") -> Path:
        path = self.root / "a1.csv"
        fields = [
            "task_id",
            "stock_code",
            "stock_name",
            "cutoff_date",
            "cutoff_price",
            "price_30d",
            "price_90d",
            "price_180d",
            "price_365d",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(
                {
                    "task_id": task_id,
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "cutoff_date": "2025-01-02",
                    "cutoff_price": "1500",
                    "price_30d": "1520",
                    "price_90d": "1510",
                    "price_180d": "1550",
                    "price_365d": "1600",
                }
            )
        return path

    def write_spec(self, *, evidence: bool = True) -> Path:
        snapshot = self.root / "price.json"
        snapshot.write_bytes(b'{"close":1520}')
        spec = {
            "schema_version": "question_generation_v1",
            "output_dir": "out",
            "require_evidence": evidence,
            "jobs": [
                {
                    "task_type": "A1",
                    "input_csv": "a1.csv",
                    "output_jsonl": "data/a1/train.jsonl",
                }
            ],
        }
        if evidence:
            evidence_path = self.root / "evidence.jsonl"
            evidence_path.write_text(
                json.dumps(
                    {
                        "task_id": "A1-TEST-00001",
                        "items": [
                            {
                                "kind": "price_snapshot",
                                "source_url": "https://example.org/price",
                                "published_at": "2025-02-03T07:00:00Z",
                                "snapshot_file": "price.json",
                                "content_sha256": hashlib.sha256(
                                    snapshot.read_bytes()
                                ).hexdigest(),
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            spec["evidence_jsonl"] = "evidence.jsonl"
        spec_path = self.root / "spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return spec_path

    def test_generates_draft_with_content_addressed_evidence(self) -> None:
        self.write_a1_csv()
        manifest = generate(self.write_spec(), clean=True)
        rows = [
            json.loads(line)
            for line in (self.root / "out/data/a1/train.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

        self.assertEqual(manifest["record_count"], 1)
        self.assertEqual(rows[0]["task_id"], "A1-TEST-00001")
        self.assertEqual(rows[0]["review_status"], "draft")
        self.assertFalse(rows[0]["official_temporal_eligible"])
        self.assertIn("manual_review_required", rows[0]["quality_flags"])
        package = json.loads(
            (self.root / "out/calibration/evidence_packages.jsonl")
            .read_text(encoding="utf-8")
            .strip()
        )
        snapshot = self.root / "out" / package["items"][0]["snapshot_path"]
        self.assertTrue(snapshot.is_file())
        self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), package["items"][0]["snapshot_sha256"])

    def test_rejects_missing_provided_task_id(self) -> None:
        self.write_a1_csv(task_id="")
        with self.assertRaisesRegex(ValueError, "empty task_id"):
            generate(self.write_spec(evidence=False), clean=True)

    def test_refuses_to_clean_directory_containing_spec(self) -> None:
        self.write_a1_csv()
        spec_path = self.write_spec(evidence=False)
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["output_dir"] = "."
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "refusing to clean"):
            generate(spec_path, clean=True)


if __name__ == "__main__":
    unittest.main()
