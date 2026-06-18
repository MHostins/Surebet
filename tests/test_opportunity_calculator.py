from __future__ import annotations

import unittest

from services.opportunity_calculator import (
    Opportunity,
    OpportunityCalculator,
    OpportunityLeg,
)


class OpportunityCalculatorTests(unittest.TestCase):
    def make_opportunity(
        self,
        odds: list[float],
        *,
        commissions: list[float] | None = None,
        calculation_model: str = "simple_2_way",
        market_type: str = "Match Odds",
    ) -> Opportunity:
        commissions = commissions or [0.0 for _ in odds]
        return Opportunity(
            opportunity_id="test-opportunity",
            sport="football",
            event_name="Team A v Team B",
            start_time="2026-06-18T18:00:00Z",
            market_type=market_type,
            result_count=len(odds),
            calculation_model=calculation_model,
            legs=[
                OpportunityLeg(
                    bookmaker=f"bookmaker-{index}",
                    selection=f"selection-{index}",
                    odds=odd,
                    commission=commissions[index],
                    side="back",
                    market_type=market_type,
                    liquidity=1000.0,
                )
                for index, odd in enumerate(odds)
            ],
        )

    def test_two_way_even_202_returns_roughly_one_percent_roi(self) -> None:
        result = OpportunityCalculator().calculate(self.make_opportunity([2.02, 2.02]), stake_total=100)

        self.assertTrue(result.is_surebet)
        self.assertAlmostEqual(result.total_implied_probability, 0.990099, places=6)
        self.assertAlmostEqual(result.roi_percent, 1.0, places=2)
        self.assertAlmostEqual(result.guaranteed_profit, 1.0, places=2)
        self.assertAlmostEqual(result.stake_plan.stakes_by_selection["selection-0"], 50.0, places=2)
        self.assertAlmostEqual(result.stake_plan.stakes_by_selection["selection-1"], 50.0, places=2)

    def test_two_way_380_185_returns_roughly_2442_percent_roi(self) -> None:
        result = OpportunityCalculator().calculate(self.make_opportunity([3.80, 1.85]), stake_total=100)

        self.assertTrue(result.is_surebet)
        self.assertAlmostEqual(result.total_implied_probability, 0.803698, places=6)
        self.assertAlmostEqual(result.roi_percent, 24.4248, places=4)
        self.assertAlmostEqual(result.guaranteed_profit, 24.4248, places=4)
        self.assertAlmostEqual(result.stake_plan.stakes_by_selection["selection-0"], 32.7434, places=4)
        self.assertAlmostEqual(result.stake_plan.stakes_by_selection["selection-1"], 67.2566, places=4)

    def test_two_way_136_400_returns_roughly_149_percent_roi(self) -> None:
        result = OpportunityCalculator().calculate(self.make_opportunity([1.36, 4.00]), stake_total=100)

        self.assertTrue(result.is_surebet)
        self.assertAlmostEqual(result.total_implied_probability, 0.985294, places=6)
        self.assertAlmostEqual(result.roi_percent, 1.4925, places=4)
        self.assertAlmostEqual(result.guaranteed_profit, 1.4925, places=4)

    def test_valid_three_way_market(self) -> None:
        opportunity = self.make_opportunity([3.4, 3.5, 3.6], calculation_model="simple_3_way")

        result = OpportunityCalculator().calculate(opportunity, stake_total=150)

        self.assertTrue(result.is_surebet)
        self.assertAlmostEqual(result.total_implied_probability, 0.85761, places=6)
        self.assertAlmostEqual(result.roi_percent, 16.6032, places=4)
        self.assertEqual(set(result.return_by_outcome), {"selection-0", "selection-1", "selection-2"})

    def test_invalid_odds_are_unsupported(self) -> None:
        result = OpportunityCalculator().calculate(self.make_opportunity([2.0, 1.0]), stake_total=100)

        self.assertFalse(result.is_surebet)
        self.assertIn("invalid_odds", result.calculation_warnings)
        self.assertEqual(result.roi_percent, 0.0)

    def test_implied_sum_above_or_equal_one_is_not_surebet(self) -> None:
        result = OpportunityCalculator().calculate(self.make_opportunity([1.90, 1.90]), stake_total=100)

        self.assertFalse(result.is_surebet)
        self.assertGreaterEqual(result.total_implied_probability, 1.0)
        self.assertIn("implied_probability_not_profitable", result.calculation_warnings)

    def test_back_commission_is_applied_to_net_odds(self) -> None:
        result = OpportunityCalculator().calculate(
            self.make_opportunity([2.0, 2.2], commissions=[0.05, 0.0]),
            stake_total=100,
        )

        leg = result.opportunity.legs[0]
        self.assertAlmostEqual(leg.net_odds, 1.95)
        self.assertAlmostEqual(result.opportunity.legs[1].net_odds, 2.2)

    def test_complex_market_is_marked_unsupported(self) -> None:
        opportunity = self.make_opportunity(
            [2.1, 2.1],
            calculation_model="complex_payoff_matrix",
            market_type="Asian Handicap 0.0",
        )

        result = OpportunityCalculator().calculate(opportunity, stake_total=100)

        self.assertFalse(result.is_surebet)
        self.assertIn("unsupported_calculation_model", result.calculation_warnings)
        self.assertIn("unsupported_market_type", result.calculation_warnings)


if __name__ == "__main__":
    unittest.main()
