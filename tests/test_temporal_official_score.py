from __future__ import annotations

import unittest

from src.evaluators.official_score import aggregate_official_score
from src.temporal.paper_bands import build_index_row, merge_index_by_task_id


class TemporalPropagationTests(unittest.TestCase):
    def test_merge_flattens_official_fields(self) -> None:
        records = [{"task_id": "C-1", "category": "C"}]
        index = {
            "C-1": {
                "task_id": "C-1",
                "paper_band": "T2",
                "review_status": "draft",
                "quality_flags": ["modeled_outcome_availability"],
                "official_temporal_eligible": False,
                "outcome_available_at": "2025-05-15",
            }
        }

        merged = merge_index_by_task_id(records, index)[0]

        self.assertEqual(merged["paper_band"], "T2")
        self.assertEqual(merged["review_status"], "draft")
        self.assertFalse(merged["official_temporal_eligible"])
        self.assertEqual(
            merged["quality_flags"], ["modeled_outcome_availability"]
        )
        self.assertEqual(merged["paper_temporal"], index["C-1"])

    def test_official_date_does_not_make_yahoo_values_pit(self) -> None:
        record = {
            "task_id": "C-US-1",
            "category": "C",
            "variant": None,
            "time_band": "T2",
            "seed": {
                "stock_code": "AAPL",
                "market": "US",
                "cutoff_date": "2025-01-01",
                "report_period_future": "2025-03-31",
            },
            "metadata": {"source": "yahoo"},
        }

        row = build_index_row(
            record,
            outcome_available_at="2025-05-01",
            outcome_evidence_url="https://www.sec.gov/example",
            outcome_evidence_code="official-filing",
        )

        self.assertIn("non_pit_fundamentals", row["quality_flags"])
        self.assertFalse(row["official_temporal_eligible"])


class OfficialScoreEligibilityTests(unittest.TestCase):
    @staticmethod
    def _prediction(**overrides: object) -> dict[str, object]:
        prediction: dict[str, object] = {
            "task_id": "C-1",
            "category": "C",
            "paper_band": "T2",
            "official_temporal_eligible": True,
            "review_status": "reviewed",
            "metrics": {"format_valid": True, "within_10pct": True},
        }
        prediction.update(overrides)
        return prediction

    def test_modeled_or_draft_records_do_not_score(self) -> None:
        result = aggregate_official_score(
            [
                self._prediction(
                    official_temporal_eligible=False,
                    quality_flags=["modeled_outcome_availability"],
                ),
                self._prediction(task_id="C-2", review_status="draft"),
                self._prediction(
                    task_id="C-3", official_temporal_eligible=None
                ),
            ]
        )

        self.assertEqual(result["eligible_records"], 0)
        self.assertIsNone(result["official_score"])

    def test_reviewed_verified_record_scores(self) -> None:
        result = aggregate_official_score([self._prediction()])

        self.assertEqual(result["eligible_records"], 1)
        self.assertEqual(result["official_score"], 1.0)
        self.assertEqual(result["per_task"]["C"]["count"], 1)

    def test_a1_uses_declared_primary_window(self) -> None:
        result = aggregate_official_score(
            [
                {
                    "task_id": "A1-1",
                    "category": "A1",
                    "paper_band": "T2",
                    "official_temporal_eligible": True,
                    "review_status": "reviewed",
                    "metrics": {
                        "format_valid": True,
                        "primary_eval_window_days": 30,
                        "by_window": {
                            "30": {"range_hit": True},
                            "90": {"range_hit": False},
                        },
                    },
                }
            ]
        )

        self.assertEqual(result["per_task"]["A1"]["mean_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
