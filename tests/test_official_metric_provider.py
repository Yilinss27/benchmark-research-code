from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.data.providers.official_values import (
    OfficialMetricObservation,
    OfficialMetricProvider,
)


class OfficialMetricProviderTests(unittest.TestCase):
    def test_registry_fields_for_cn_hk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.jsonl"
            row = {
                "market": "CN_A",
                "stock_code": "600519",
                "report_period": "2025-12-31",
                "published_at": "2026-04-17",
                "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
                "source": "cninfo",
                "document_id": "1225114741",
                "form_type": "annual",
                "fields": {
                    "operating_revenue": 123.45,
                    "net_profit": 67.89,
                },
            }
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            provider = OfficialMetricProvider(index_path=path)

            revenue = provider.find_metric_value("600519", "CN_A", "2025-12-31", "operating_revenue")
            profit = provider.find_metric_value("600519", "CN_A", "2025-12-31", "net_profit")

            self.assertIsNotNone(revenue)
            self.assertIsNotNone(profit)
            self.assertEqual(revenue.value, 123.45)
            self.assertEqual(profit.value, 67.89)
            self.assertEqual(revenue.source, "cninfo")

    def test_us_falls_back_to_sec_companyfacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.jsonl"
            path.write_text("", encoding="utf-8")
            provider = OfficialMetricProvider(index_path=path)

            provider.sec_companyfacts.find_metric_value = lambda *_args, **_kwargs: OfficialMetricObservation(
                metric_name="operating_revenue",
                value=999.0,
                report_period="2025-12-31",
                published_at="2026-01-30",
                source="sec_companyfacts",
                source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                evidence_code="10-Q:Revenues:gap0d",
            )

            obs = provider.find_metric_value("AAPL", "US", "2025-12-31", "operating_revenue")
            self.assertIsNotNone(obs)
            self.assertEqual(obs.source, "sec_companyfacts")
            self.assertEqual(obs.value, 999.0)


if __name__ == "__main__":
    unittest.main()
