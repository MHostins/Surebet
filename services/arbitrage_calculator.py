"""Arbitrage simulation for exchange odds."""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


class ArbitrageCalculator:
    def __init__(
        self,
        commissions: dict[str, float],
        stake_total: float,
        min_margin: float,
    ) -> None:
        self.commissions = commissions
        self.stake_total = stake_total
        self.min_margin = min_margin

    def find_opportunities(self, matched_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        opportunities: list[dict[str, Any]] = []
        for pair in matched_rows:
            rows = [pair["betfair"], pair["matchbook"]]
            for back_row in [row for row in rows if row["side"] == "back"]:
                for lay_row in [row for row in rows if row["side"] == "lay" and row["bookmaker"] != back_row["bookmaker"]]:
                    opportunity = self._evaluate_back_lay(back_row, lay_row)
                    if not opportunity:
                        continue
                    if opportunity["margin"] >= self.min_margin and opportunity["is_liquidity_sufficient"]:
                        LOGGER.info(
                            "Possível surebet: %s | %s | %s | margem %.2f%%",
                            back_row["event_name"],
                            back_row["market_type"],
                            back_row["selection"],
                            opportunity["margin"] * 100,
                        )
                        opportunities.append(opportunity)
                    else:
                        LOGGER.info(
                            "Surebet descartada por comissão ou baixa margem: %s | %s | %s | margem %.2f%%",
                            back_row["event_name"],
                            back_row["market_type"],
                            back_row["selection"],
                            opportunity["margin"] * 100,
                        )
        return opportunities

    def _evaluate_back_lay(self, back_row: dict[str, Any], lay_row: dict[str, Any]) -> dict[str, Any] | None:
        back_odds = float(back_row["odds"])
        lay_odds = float(lay_row["odds"])
        if back_odds <= 1 or lay_odds <= 1:
            return None

        back_commission = self.commissions.get(back_row["bookmaker"], 0.0)
        lay_commission = self.commissions.get(lay_row["bookmaker"], 0.0)
        effective_back_odds = 1 + (back_odds - 1) * (1 - back_commission)
        effective_lay_odds = lay_odds - lay_commission
        margin = (effective_back_odds / effective_lay_odds) - 1

        back_stake = min(self.stake_total, float(back_row["available_liquidity"]))
        lay_stake = (back_stake * back_odds) / max(lay_odds - lay_commission, 1.01)
        lay_liability = lay_stake * (lay_odds - 1)
        is_liquidity_sufficient = (
            back_stake > 0
            and lay_stake > 0
            and back_stake <= float(back_row["available_liquidity"])
            and lay_stake <= float(lay_row["available_liquidity"])
        )

        profit_if_selection_wins = back_stake * (back_odds - 1) * (1 - back_commission) - lay_liability
        profit_if_selection_loses = lay_stake * (1 - lay_commission) - back_stake

        return {
            "event_name": back_row["event_name"],
            "start_time": back_row["start_time"],
            "market_type": back_row["market_type"],
            "selection": back_row["selection"],
            "back_bookmaker": back_row["bookmaker"],
            "back_odds": back_odds,
            "back_stake": round(back_stake, 2),
            "lay_bookmaker": lay_row["bookmaker"],
            "lay_odds": lay_odds,
            "lay_stake": round(lay_stake, 2),
            "lay_liability": round(lay_liability, 2),
            "margin": round(margin, 6),
            "profit_if_selection_wins": round(profit_if_selection_wins, 2),
            "profit_if_selection_loses": round(profit_if_selection_loses, 2),
            "back_liquidity": back_row["available_liquidity"],
            "lay_liquidity": lay_row["available_liquidity"],
            "is_liquidity_sufficient": is_liquidity_sufficient,
        }
