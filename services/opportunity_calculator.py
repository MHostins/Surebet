"""Read-only calculator for simple multi-leg arbitrage opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field


SUPPORTED_MODELS = {"simple_2_way", "simple_3_way"}
COMPLEX_MARKET_MARKERS = (
    "asian",
    "handicap",
    "push",
    "tempo extra",
    "extra time",
    "overtime",
    "complex",
    "matrix",
)


@dataclass
class OpportunityLeg:
    bookmaker: str
    selection: str
    odds: float
    commission: float = 0.0
    net_odds: float | None = None
    side: str = "back"
    market_type: str = ""
    liquidity: float | None = None

    def with_computed_net_odds(self) -> "OpportunityLeg":
        if self.net_odds is not None:
            return self
        net_odds = 1.0 + (self.odds - 1.0) * (1.0 - self.commission)
        return OpportunityLeg(
            bookmaker=self.bookmaker,
            selection=self.selection,
            odds=self.odds,
            commission=self.commission,
            net_odds=net_odds,
            side=self.side,
            market_type=self.market_type,
            liquidity=self.liquidity,
        )


@dataclass
class Opportunity:
    opportunity_id: str
    sport: str
    event_name: str
    start_time: str
    market_type: str
    result_count: int
    legs: list[OpportunityLeg]
    calculation_model: str


@dataclass
class StakePlan:
    stake_total: float
    stakes_by_selection: dict[str, float]
    stakes_by_bookmaker: dict[str, float]


@dataclass
class CalculationResult:
    opportunity: Opportunity
    total_implied_probability: float = 0.0
    roi_percent: float = 0.0
    stake_total: float = 0.0
    stake_plan: StakePlan = field(default_factory=lambda: StakePlan(0.0, {}, {}))
    return_by_outcome: dict[str, float] = field(default_factory=dict)
    guaranteed_profit: float = 0.0
    worst_case_profit: float = 0.0
    is_surebet: bool = False
    calculation_warnings: list[str] = field(default_factory=list)


class OpportunityCalculator:
    """Calculates simple 2-way and 3-way back-only arbitrage simulations."""

    def calculate(self, opportunity: Opportunity, stake_total: float = 100.0) -> CalculationResult:
        computed_opportunity = Opportunity(
            opportunity_id=opportunity.opportunity_id,
            sport=opportunity.sport,
            event_name=opportunity.event_name,
            start_time=opportunity.start_time,
            market_type=opportunity.market_type,
            result_count=opportunity.result_count,
            calculation_model=opportunity.calculation_model,
            legs=[leg.with_computed_net_odds() for leg in opportunity.legs],
        )
        warnings = self._validate(computed_opportunity, stake_total)
        if warnings:
            return CalculationResult(
                opportunity=computed_opportunity,
                stake_total=stake_total,
                stake_plan=StakePlan(stake_total, {}, {}),
                calculation_warnings=warnings,
            )

        implied_probabilities = {
            leg.selection: 1.0 / float(leg.net_odds)
            for leg in computed_opportunity.legs
        }
        implied_sum = sum(implied_probabilities.values())
        roi_percent = (1.0 / implied_sum - 1.0) * 100.0

        stakes_by_selection: dict[str, float] = {}
        stakes_by_bookmaker: dict[str, float] = {}
        return_by_outcome: dict[str, float] = {}
        for leg in computed_opportunity.legs:
            probability = implied_probabilities[leg.selection]
            stake = stake_total * probability / implied_sum
            stakes_by_selection[leg.selection] = stake
            stakes_by_bookmaker[leg.bookmaker] = stakes_by_bookmaker.get(leg.bookmaker, 0.0) + stake
            return_by_outcome[leg.selection] = stake * float(leg.net_odds)

        worst_case_profit = min(return_by_outcome.values()) - stake_total
        is_surebet = implied_sum < 1.0
        if not is_surebet:
            warnings.append("implied_probability_not_profitable")

        return CalculationResult(
            opportunity=computed_opportunity,
            total_implied_probability=implied_sum,
            roi_percent=roi_percent if is_surebet else 0.0,
            stake_total=stake_total,
            stake_plan=StakePlan(stake_total, stakes_by_selection, stakes_by_bookmaker),
            return_by_outcome=return_by_outcome,
            guaranteed_profit=worst_case_profit if is_surebet else 0.0,
            worst_case_profit=worst_case_profit,
            is_surebet=is_surebet,
            calculation_warnings=warnings,
        )

    def _validate(self, opportunity: Opportunity, stake_total: float) -> list[str]:
        warnings: list[str] = []

        if opportunity.calculation_model not in SUPPORTED_MODELS:
            warnings.append("unsupported_calculation_model")

        if len(opportunity.legs) < 2:
            warnings.append("not_enough_legs")
        if len(opportunity.legs) > 3:
            warnings.append("too_many_legs")

        if opportunity.calculation_model == "simple_2_way" and len(opportunity.legs) != 2:
            warnings.append("result_count_mismatch")
        if opportunity.calculation_model == "simple_3_way" and len(opportunity.legs) != 3:
            warnings.append("result_count_mismatch")
        if opportunity.result_count != len(opportunity.legs):
            warnings.append("result_count_mismatch")

        if stake_total <= 0:
            warnings.append("invalid_stake_total")

        if self._is_complex_market(opportunity.market_type):
            warnings.append("unsupported_market_type")

        seen_selections: set[str] = set()
        for leg in opportunity.legs:
            if leg.selection in seen_selections:
                warnings.append("duplicate_selection")
            seen_selections.add(leg.selection)

            if leg.side.lower() != "back":
                warnings.append("unsupported_side")
            if leg.odds <= 1.0 or leg.net_odds is None or leg.net_odds <= 1.0:
                warnings.append("invalid_odds")
            if leg.commission < 0.0 or leg.commission >= 1.0:
                warnings.append("invalid_commission")
            if self._is_complex_market(leg.market_type):
                warnings.append("unsupported_market_type")

        return list(dict.fromkeys(warnings))

    def _is_complex_market(self, market_type: str) -> bool:
        normalized = (market_type or "").strip().lower()
        return any(marker in normalized for marker in COMPLEX_MARKET_MARKERS)
