from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.opportunity_engine_service import OpportunityEngineService


class OpportunityEngineServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output_dir = Path(self.temp_dir.name)

    def write_discrepancy_report(self, comparisons: list[dict]) -> None:
        payload = {
            "timestamp": "2026-06-19T12:00:00+00:00",
            "status": "success",
            "comparisons": comparisons,
        }
        (self.output_dir / "multi_bookmaker_discrepancy_report.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def comparison_row(
        self,
        *,
        event: str = "Team A at Team B",
        selection: str,
        side: str = "back",
        market_type: str = "Money Line",
        net_matchbook: float,
        net_pinnacle: float,
    ) -> dict:
        return {
            "sport_name": "baseball",
            "market_type": market_type,
            "event_name_matchbook": event,
            "event_name_pinnacle": event.replace(" at ", " v "),
            "start_time_matchbook": "2026-06-19T22:40:00Z",
            "start_time_pinnacle": "2026-06-19T22:41:00Z",
            "selection_matchbook": selection,
            "selection_pinnacle": selection,
            "side_matchbook": side,
            "odd_matchbook": net_matchbook,
            "odd_pinnacle": net_pinnacle,
            "net_odd_matchbook": net_matchbook,
            "net_odd_pinnacle": net_pinnacle,
            "liquidity_matchbook": 1000.0,
            "event_pair_confidence": 1.0,
            "selection_match_confidence": 1.0,
        }

    def test_creates_empty_report_when_no_candidates(self) -> None:
        self.write_discrepancy_report([])

        report = OpportunityEngineService(self.output_dir, stake_total=100).calculate()

        self.assertEqual(report["total_candidates"], 0)
        self.assertEqual(report["total_supported"], 0)
        self.assertEqual(report["total_surebets"], 0)
        self.assertEqual(report["opportunities"], [])
        self.assertTrue((self.output_dir / "calculated_opportunities.json").exists())
        self.assertTrue((self.output_dir / "calculated_opportunities.csv").exists())
        self.assertEqual(len((self.output_dir / "opportunity_watch_history.jsonl").read_text().splitlines()), 1)

    def test_missing_discrepancy_report_does_not_break(self) -> None:
        report = OpportunityEngineService(self.output_dir, stake_total=100).calculate()

        self.assertEqual(report["status"], "missing_input")
        self.assertEqual(report["total_candidates"], 0)
        self.assertTrue((self.output_dir / "calculated_opportunities.json").exists())

    def test_calculates_two_way_back_back_opportunity(self) -> None:
        self.write_discrepancy_report(
            [
                self.comparison_row(selection="Team A", net_matchbook=2.02, net_pinnacle=2.0),
                self.comparison_row(selection="Team B", net_matchbook=2.0, net_pinnacle=2.02),
            ]
        )

        report = OpportunityEngineService(self.output_dir, stake_total=100).calculate()

        self.assertEqual(report["total_candidates"], 1)
        self.assertEqual(report["total_supported"], 1)
        self.assertEqual(report["total_surebets"], 1)
        opportunity = report["opportunities"][0]
        self.assertTrue(opportunity["is_surebet"])
        self.assertAlmostEqual(opportunity["implied_sum"], 0.990099, places=6)
        self.assertAlmostEqual(opportunity["roi_percent"], 1.0, places=2)
        self.assertAlmostEqual(opportunity["guaranteed_profit"], 1.0, places=2)
        self.assertEqual(opportunity["calculation_model"], "simple_2_way")
        self.assertEqual(opportunity["calculation_warnings"], [])

    def test_ignores_unsupported_market(self) -> None:
        self.write_discrepancy_report(
            [
                self.comparison_row(selection="Team A", market_type="Asian Handicap", net_matchbook=2.2, net_pinnacle=2.1),
                self.comparison_row(selection="Team B", market_type="Asian Handicap", net_matchbook=2.2, net_pinnacle=2.1),
            ]
        )

        report = OpportunityEngineService(self.output_dir, stake_total=100).calculate()

        self.assertEqual(report["total_candidates"], 1)
        self.assertEqual(report["total_supported"], 0)
        self.assertEqual(report["total_surebets"], 0)
        self.assertIn("unsupported_market_type", report["opportunities"][0]["calculation_warnings"])

    def test_lay_rows_are_not_considered(self) -> None:
        self.write_discrepancy_report(
            [
                self.comparison_row(selection="Team A", side="lay", net_matchbook=3.0, net_pinnacle=2.0),
                self.comparison_row(selection="Team B", side="back", net_matchbook=2.02, net_pinnacle=2.02),
            ]
        )

        report = OpportunityEngineService(self.output_dir, stake_total=100).calculate()

        self.assertEqual(report["total_candidates"], 0)
        self.assertEqual(report["total_supported"], 0)
        self.assertEqual(report["total_surebets"], 0)

    def test_keeps_read_only_scope_to_report_files(self) -> None:
        self.write_discrepancy_report(
            [
                self.comparison_row(selection="Team A", net_matchbook=2.02, net_pinnacle=2.0),
                self.comparison_row(selection="Team B", net_matchbook=2.0, net_pinnacle=2.02),
            ]
        )

        OpportunityEngineService(self.output_dir, stake_total=100).calculate()

        created_names = {path.name for path in self.output_dir.iterdir()}
        self.assertIn("multi_bookmaker_discrepancy_report.json", created_names)
        self.assertIn("calculated_opportunities.json", created_names)
        self.assertIn("calculated_opportunities.csv", created_names)
        self.assertIn("opportunity_watch_history.jsonl", created_names)
        self.assertNotIn("odds_history.db", created_names)


if __name__ == "__main__":
    unittest.main()
