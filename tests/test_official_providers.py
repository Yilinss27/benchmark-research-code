from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.data.provenance import read_provenance, write_provenance
from src.data.providers.official import OfficialRegistryProvider, is_official_url


class OfficialProviderTests(unittest.TestCase):
    def test_registry_rejects_non_official_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.jsonl"
            rows = [
                {
                    "market": "US",
                    "stock_code": "AAPL",
                    "report_period": "2025-06-30",
                    "published_at": "2025-08-01",
                    "source_url": "https://example.com/aapl",
                },
                {
                    "market": "US",
                    "stock_code": "AAPL",
                    "report_period": "2025-06-30",
                    "published_at": "2025-08-02",
                    "source_url": "https://www.sec.gov/Archives/aapl.htm",
                    "source": "sec_edgar",
                },
            ]
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )

            disclosure = OfficialRegistryProvider(path).find_disclosure(
                "AAPL", "US", "2025-06-30"
            )

            self.assertIsNotNone(disclosure)
            self.assertEqual(disclosure.published_at, "2025-08-02")
            self.assertTrue(is_official_url(disclosure.source_url, "US"))

    def test_provenance_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            write_provenance(
                "sample",
                source_url="https://www.sec.gov/sample",
                content='{"ok": true}',
                parser_version="test_v1",
                cache_dir=cache_dir,
            )
            self.assertIsNotNone(read_provenance("sample", cache_dir=cache_dir))
            (cache_dir / "sample.source").write_text("changed", encoding="utf-8")
            self.assertIsNone(read_provenance("sample", cache_dir=cache_dir))


if __name__ == "__main__":
    unittest.main()
