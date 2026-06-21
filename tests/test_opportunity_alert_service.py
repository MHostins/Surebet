from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.opportunity_alert_service import OpportunityAlertService


class OpportunityAlertServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output_dir = Path(self.temp_dir.name)

    def write_calculated_report(self, opportunities: list[dict]) -> None:
        payload = {
            "timestamp": "2026-06-21T12:00:00+00:00",
            "status": "success",
            "opportunities": opportunities,
        }
        (self.output_dir / "calculated_opportunities.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def opportunity(
        self,
        *,
        event_name: str,
        is_surebet: bool = False,
        distance: float = 1.0,
        roi: float = 0.0,
    ) -> dict:
        return {
            "event_name": event_name,
            "sport": "baseball",
            "market_type": "Money Line",
            "start_time": "2026-06-21T22:00:00Z",
            "bookmaker_pair": ["pinnacle", "matchbook-br"],
            "is_cross_bookmaker": True,
            "implied_sum": 0.999 if is_surebet else 1.0 + distance / 100.0,
            "roi_percent": roi,
            "distance_to_surebet_percent": distance,
            "guaranteed_profit": 0.1 if is_surebet else 0.0,
            "worst_case_profit": 0.1 if is_surebet else -distance,
            "stake_plan": {"stake_total": 100.0},
            "calculation_model": "simple_2_way",
            "optimization_model": "best_net_odds_per_selection",
            "is_surebet": is_surebet,
        }

    def test_generates_surebet_alert(self) -> None:
        self.write_calculated_report([
            self.opportunity(event_name="Surebet Game", is_surebet=True, distance=0.0, roi=0.2),
        ])

        report = OpportunityAlertService(self.output_dir, near_miss_threshold_percent=2.0).generate()

        self.assertEqual(report["summary"]["total_surebet_alerts"], 1)
        self.assertEqual(report["summary"]["total_near_miss_alerts"], 0)
        alert = report["rankings"]["top_surebets"][0]
        self.assertEqual(alert["alert_type"], "surebet")
        self.assertEqual(alert["event_name"], "Surebet Game")
        self.assertEqual(alert["stake_plan"], {"stake_total": 100.0})

    def test_generates_near_miss_alert_within_threshold(self) -> None:
        self.write_calculated_report([
            self.opportunity(event_name="Near Miss Game", is_surebet=False, distance=1.9),
            self.opportunity(event_name="Far Game", is_surebet=False, distance=2.1),
        ])

        report = OpportunityAlertService(self.output_dir, near_miss_threshold_percent=2.0).generate()

        self.assertEqual(report["summary"]["total_alerts"], 1)
        self.assertEqual(report["summary"]["total_near_miss_alerts"], 1)
        alert = report["rankings"]["top_near_misses"][0]
        self.assertEqual(alert["alert_type"], "near_miss")
        self.assertEqual(alert["event_name"], "Near Miss Game")

    def test_respects_custom_near_miss_threshold(self) -> None:
        self.write_calculated_report([
            self.opportunity(event_name="Near Miss Game", is_surebet=False, distance=1.9),
        ])

        report = OpportunityAlertService(self.output_dir, near_miss_threshold_percent=1.0).generate()

        self.assertEqual(report["summary"]["total_alerts"], 0)

    def test_writes_json_csv_and_jsonl(self) -> None:
        self.write_calculated_report([
            self.opportunity(event_name="Surebet Game", is_surebet=True, distance=0.0, roi=0.2),
            self.opportunity(event_name="Near Miss Game", is_surebet=False, distance=1.5),
        ])

        OpportunityAlertService(self.output_dir, near_miss_threshold_percent=2.0).generate()

        self.assertTrue((self.output_dir / "opportunity_alerts.json").exists())
        self.assertTrue((self.output_dir / "opportunity_alerts.csv").exists())
        history_lines = (self.output_dir / "opportunity_alert_history.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(history_lines), 1)
        history = json.loads(history_lines[0])
        self.assertEqual(history["total_surebet_alerts"], 1)
        self.assertEqual(history["total_near_miss_alerts"], 1)

    def test_missing_files_generate_empty_report(self) -> None:
        report = OpportunityAlertService(self.output_dir, near_miss_threshold_percent=2.0).generate()

        self.assertEqual(report["summary"]["total_alerts"], 0)
        self.assertEqual(report["rankings"]["top_surebets"], [])
        self.assertEqual(report["rankings"]["top_near_misses"], [])
        self.assertTrue((self.output_dir / "opportunity_alerts.json").exists())

    def test_invalid_json_generates_empty_report(self) -> None:
        (self.output_dir / "calculated_opportunities.json").write_text("{bad", encoding="utf-8")

        report = OpportunityAlertService(self.output_dir, near_miss_threshold_percent=2.0).generate()

        self.assertEqual(report["summary"]["total_alerts"], 0)

    def test_keeps_read_only_scope_to_alert_outputs(self) -> None:
        self.write_calculated_report([
            self.opportunity(event_name="Near Miss Game", is_surebet=False, distance=1.5),
        ])

        OpportunityAlertService(self.output_dir, near_miss_threshold_percent=2.0).generate()

        created = {path.name for path in self.output_dir.iterdir()}
        self.assertIn("calculated_opportunities.json", created)
        self.assertIn("opportunity_alerts.json", created)
        self.assertIn("opportunity_alerts.csv", created)
        self.assertIn("opportunity_alert_history.jsonl", created)
        self.assertNotIn("odds_history.db", created)


if __name__ == "__main__":
    unittest.main()
