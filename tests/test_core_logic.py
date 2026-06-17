from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.comparison_service import ComparisonService
from services.moneyline_arbitrage_service import MoneylineArbitrageService
from services.multi_bookmaker_comparison_service import MultiBookmakerComparisonService


class ComparisonServiceTests(unittest.TestCase):
    def make_service(self, aliases: dict[str, list[str]] | None = None) -> ComparisonService:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        aliases_path = root / "aliases.json"
        aliases_path.write_text(json.dumps(aliases or {}, ensure_ascii=False), encoding="utf-8")
        return ComparisonService(
            output_dir=root,
            max_start_delta_minutes=30,
            min_event_match_confidence=0.85,
            aliases_path=aliases_path,
        )

    def test_name_normalization_removes_accents_hyphens_and_standardizes_versus(self) -> None:
        service = self.make_service()

        self.assertEqual(
            service._basic_normalize("São-Paulo FC vs  Colo-Colo"),
            "sao paulo fc v colo colo",
        )
        self.assertEqual(service._canonical_name("São-Paulo FC"), "sao paulo")

    def test_event_pairing_accepts_swapped_teams_inside_time_delta(self) -> None:
        service = self.make_service({"colo colo": ["colo-colo"]})
        source = ("Colo-Colo v Cobresal", "2026-06-18T12:00:00Z")
        candidates = {
            ("Cobresal vs Colo Colo", "2026-06-18T12:20:00Z"): [],
            ("Qatar v Switzerland", "2026-06-18T12:10:00Z"): [],
        }

        matched_key, confidence = service._find_matching_event(source, candidates, set())

        self.assertEqual(matched_key, ("Cobresal vs Colo Colo", "2026-06-18T12:20:00Z"))
        self.assertGreaterEqual(confidence, 0.99)


class MoneylineMathTests(unittest.TestCase):
    def test_commission_net_back_and_lay_odds(self) -> None:
        service = MoneylineArbitrageService.__new__(MoneylineArbitrageService)

        self.assertAlmostEqual(service._net_back_odds(3.0, 0.05), 2.9)
        self.assertAlmostEqual(service._net_lay_odds(3.0, 0.05), 3.1052631579)

    def test_multi_bookmaker_discrepancy_and_audit_threshold(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)

        service = MultiBookmakerComparisonService.__new__(MultiBookmakerComparisonService)
        service.output_dir = root
        service.settings = SimpleNamespace(
            max_start_time_delta_minutes=60,
            min_event_match_confidence=0.85,
            team_aliases_path=root / "aliases.json",
            commissions=SimpleNamespace(matchbook_br=0.02),
        )
        (root / "aliases.json").write_text("{}", encoding="utf-8")
        service.comparison_service = ComparisonService(
            output_dir=root,
            max_start_delta_minutes=60,
            min_event_match_confidence=0.85,
            aliases_path=root / "aliases.json",
        )

        mb_rows = [
            {
                "event_id": "mb1",
                "bookmaker": "matchbook-br",
                "sport": "mma",
                "event_name": "Fighter A vs Fighter B",
                "start_time": "2026-07-12T03:30:00Z",
                "market_type": "Money Line",
                "selection": "Fighter A",
                "side": "back",
                "odds": 2.2,
                "available_liquidity": 100.0,
            },
            {
                "event_id": "mb1",
                "bookmaker": "matchbook-br",
                "sport": "mma",
                "event_name": "Fighter A vs Fighter B",
                "start_time": "2026-07-12T03:30:00Z",
                "market_type": "Money Line",
                "selection": "Fighter B",
                "side": "lay",
                "odds": 1.5,
                "available_liquidity": 100.0,
            },
        ]
        pin_rows = [
            {
                "event_id": "pin1",
                "bookmaker": "pinnacle",
                "sport": "mma",
                "event_name": "Fighter A v Fighter B",
                "start_time": "2026-07-12T03:30:00Z",
                "market_type": "Money Line",
                "selection": "Fighter A",
                "side": "back",
                "odds": 2.0,
                "available_liquidity": None,
            },
            {
                "event_id": "pin1",
                "bookmaker": "pinnacle",
                "sport": "mma",
                "event_name": "Fighter A v Fighter B",
                "start_time": "2026-07-12T03:30:00Z",
                "market_type": "Money Line",
                "selection": "Fighter B",
                "side": "back",
                "odds": 3.0,
                "available_liquidity": None,
            },
        ]

        comparisons, audit_rows = service._pair_and_compare(mb_rows, pin_rows)
        by_selection = {row["selection_matchbook"]: row for row in comparisons}

        self.assertAlmostEqual(by_selection["Fighter A"]["net_odd_matchbook"], 2.176)
        self.assertAlmostEqual(by_selection["Fighter A"]["discrepancy_percent"], 8.8)
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(audit_rows[0]["selection_matchbook"], "Fighter B")
        self.assertGreater(audit_rows[0]["discrepancy_percent"], 20.0)


if __name__ == "__main__":
    unittest.main()
