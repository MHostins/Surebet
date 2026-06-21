from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.opportunity_quality_review_service import OpportunityQualityReviewService


class OpportunityQualityReviewServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output_dir = Path(self.temp_dir.name)

    def write_calculated_report(self, opportunities: list[dict]) -> None:
        payload = {
            "timestamp": "2026-06-21T12:00:00+00:00",
            "status": "success",
            "total_candidates": len(opportunities),
            "total_supported": len(opportunities),
            "total_surebets": sum(1 for row in opportunities if row.get("is_surebet")),
            "best_roi_percent": max((row.get("roi_percent") or 0.0 for row in opportunities), default=None),
            "best_event": "Boston Red Sox at Seattle Mariners",
            "best_market": "Money Line",
            "best_guaranteed_profit": 0.075,
            "closest_distance_to_surebet_percent": min((row.get("distance_to_surebet_percent", 0.0) for row in opportunities), default=None),
            "opportunities": opportunities,
        }
        (self.output_dir / "calculated_opportunities.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def write_history(self) -> None:
        lines = [
            {"timestamp": "2026-06-21T10:00:00+00:00", "total_surebets": 0, "best_roi_percent": None, "best_event": None},
            "not-json",
            {"timestamp": "2026-06-21T11:00:00+00:00", "total_surebets": 1, "best_roi_percent": 0.075, "best_event": "Boston Red Sox at Seattle Mariners"},
        ]
        with (self.output_dir / "opportunity_watch_history.jsonl").open("w", encoding="utf-8") as handle:
            for line in lines:
                if isinstance(line, str):
                    handle.write(line + "\n")
                else:
                    handle.write(json.dumps(line) + "\n")

    def opportunity(
        self,
        *,
        event_name: str,
        sport: str = "baseball",
        pair: list[str] | None = None,
        is_surebet: bool = False,
        roi: float = 0.0,
        distance: float = 1.0,
    ) -> dict:
        return {
            "event_name": event_name,
            "sport": sport,
            "market_type": "Money Line",
            "start_time": "2026-06-21T22:00:00Z",
            "bookmaker_pair": pair or ["pinnacle", "matchbook-br"],
            "is_cross_bookmaker": len(set(pair or ["pinnacle", "matchbook-br"])) > 1,
            "implied_sum": 1.0 + (distance / 100.0),
            "roi_percent": roi,
            "distance_to_surebet_percent": distance,
            "guaranteed_profit": 0.075 if is_surebet else 0.0,
            "worst_case_profit": 0.075 if is_surebet else -distance,
            "is_surebet": is_surebet,
        }

    def test_empty_report_when_source_files_are_missing(self) -> None:
        report = OpportunityQualityReviewService(self.output_dir).review()

        self.assertEqual(report["total_candidates"], 0)
        self.assertEqual(report["total_surebets"], 0)
        self.assertEqual(report["surebet_rate_percent"], 0.0)
        self.assertEqual(report["historical_analysis"]["total_history_rows"], 0)
        self.assertTrue((self.output_dir / "opportunity_quality_review.json").exists())
        self.assertTrue((self.output_dir / "opportunity_quality_review.csv").exists())

    def test_identifies_surebet_and_rates(self) -> None:
        self.write_calculated_report(
            [
                self.opportunity(event_name="Boston Red Sox at Seattle Mariners", is_surebet=True, roi=0.075, distance=0.0),
                self.opportunity(event_name="Near Miss A", roi=0.0, distance=1.5),
                self.opportunity(event_name="Near Miss B", roi=0.0, distance=3.0, pair=["matchbook-br", "matchbook-br"]),
            ]
        )

        report = OpportunityQualityReviewService(self.output_dir).review()

        self.assertEqual(report["total_candidates"], 3)
        self.assertEqual(report["total_surebets"], 1)
        self.assertAlmostEqual(report["surebet_rate_percent"], 33.333333, places=6)
        self.assertEqual(report["top_surebets"][0]["event_name"], "Boston Red Sox at Seattle Mariners")
        self.assertAlmostEqual(report["average_roi_percent_for_surebets"], 0.075, places=6)
        self.assertAlmostEqual(report["max_roi_percent_for_surebets"], 0.075, places=6)

    def test_calculates_distance_average_and_median(self) -> None:
        self.write_calculated_report(
            [
                self.opportunity(event_name="A", distance=0.0, is_surebet=True, roi=0.1),
                self.opportunity(event_name="B", distance=1.5),
                self.opportunity(event_name="C", distance=3.0),
            ]
        )

        report = OpportunityQualityReviewService(self.output_dir).review()

        self.assertAlmostEqual(report["average_distance_to_surebet_percent"], 1.5, places=6)
        self.assertAlmostEqual(report["median_distance_to_surebet_percent"], 1.5, places=6)
        self.assertEqual(report["min_distance_to_surebet_percent"], 0.0)
        self.assertEqual(report["max_distance_to_surebet_percent"], 3.0)

    def test_creates_near_miss_rankings(self) -> None:
        self.write_calculated_report(
            [
                self.opportunity(event_name="Surebet", is_surebet=True, roi=0.1, distance=0.0),
                self.opportunity(event_name="Near Miss Close", distance=0.8),
                self.opportunity(event_name="Near Miss Far", distance=2.5),
                self.opportunity(event_name="Same House", distance=0.2, pair=["pinnacle", "pinnacle"]),
            ]
        )

        report = OpportunityQualityReviewService(self.output_dir).review()

        self.assertEqual(report["top_near_misses"][0]["event_name"], "Same House")
        self.assertEqual(report["top_cross_bookmaker_near_misses"][0]["event_name"], "Near Miss Close")

    def test_groups_by_sport_and_bookmaker_pair(self) -> None:
        self.write_calculated_report(
            [
                self.opportunity(event_name="Baseball Surebet", sport="baseball", is_surebet=True, roi=0.2, distance=0.0),
                self.opportunity(event_name="Basketball Miss", sport="basketball", pair=["pinnacle", "pinnacle"], distance=2.0),
            ]
        )

        report = OpportunityQualityReviewService(self.output_dir).review()

        by_sport = {row["sport"]: row for row in report["by_sport"]}
        self.assertEqual(by_sport["baseball"]["total_surebets"], 1)
        self.assertEqual(by_sport["basketball"]["total_candidates"], 1)
        by_pair = {row["bookmaker_pair"]: row for row in report["by_bookmaker_pair"]}
        self.assertEqual(by_pair["pinnacle x matchbook-br"]["total_surebets"], 1)
        self.assertEqual(by_pair["pinnacle x pinnacle"]["total_candidates"], 1)

    def test_ignores_invalid_jsonl_lines(self) -> None:
        self.write_calculated_report([])
        self.write_history()

        report = OpportunityQualityReviewService(self.output_dir).review()

        history = report["historical_analysis"]
        self.assertEqual(history["total_history_rows"], 2)
        self.assertEqual(history["history_total_surebets_sum"], 1)
        self.assertEqual(history["history_best_event"], "Boston Red Sox at Seattle Mariners")
        self.assertEqual(len(history["trend_last_rows"]), 2)

    def test_keeps_read_only_scope_to_review_outputs(self) -> None:
        self.write_calculated_report([self.opportunity(event_name="A", distance=1.0)])

        OpportunityQualityReviewService(self.output_dir).review()

        created = {path.name for path in self.output_dir.iterdir()}
        self.assertIn("calculated_opportunities.json", created)
        self.assertIn("opportunity_quality_review.json", created)
        self.assertIn("opportunity_quality_review.csv", created)
        self.assertNotIn("odds_history.db", created)


if __name__ == "__main__":
    unittest.main()
