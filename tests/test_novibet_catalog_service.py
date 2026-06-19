from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.novibet_catalog_service import NovibetCatalogService


class FakeNovibetClient:
    def inspect_public_page(self) -> dict:
        return {
            "timestamp": "2026-06-19T12:00:00Z",
            "status": "success",
            "target_url": "https://www.novibet.bet.br/apostas-esportivas",
            "final_url": "https://www.novibet.bet.br/apostas-esportivas",
            "page_title": "Novibet",
            "raw_events_count": 1,
            "normalized_odds_count": 1,
            "blocked_action_selectors_detected": 0,
            "betting_actions_performed": False,
            "errors": [],
            "raw_sample": {"visible_text_prefix": "Team A x Team B"},
            "normalized_odds": [
                {
                    "bookmaker": "novibet",
                    "sport": "Futebol",
                    "league": "Liga",
                    "event_name": "Team A x Team B",
                    "start_time": None,
                    "market_type": "Match Odds",
                    "selection": "Team A",
                    "odds": 2.1,
                    "source_url": "https://example.test",
                    "scraped_at": "2026-06-19T12:00:00Z",
                }
            ],
        }


class NovibetCatalogServiceTests(unittest.TestCase):
    def test_writes_read_only_samples_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            report = NovibetCatalogService(output_dir=output_dir, client=FakeNovibetClient()).inspect()

            self.assertFalse(report["betting_actions_performed"])
            self.assertTrue((output_dir / "novibet_raw_sample.json").exists())
            self.assertTrue((output_dir / "novibet_normalized_sample.json").exists())
            self.assertTrue((output_dir / "novibet_inspection_report.json").exists())
            normalized = json.loads((output_dir / "novibet_normalized_sample.json").read_text(encoding="utf-8"))
            self.assertEqual(normalized[0]["bookmaker"], "novibet")
            self.assertNotIn("odds_history.db", {path.name for path in output_dir.iterdir()})


if __name__ == "__main__":
    unittest.main()
