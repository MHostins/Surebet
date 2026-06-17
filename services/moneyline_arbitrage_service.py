"""Read-only arbitrage analyzer service for moneyline markets."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import Settings

LOGGER = logging.getLogger(__name__)


class MoneylineArbitrageService:
    """Evaluates theoretical moneyline back/lay arbitrage and computes gap diagnostics."""

    def __init__(
        self,
        output_dir: Path,
        settings: Settings,
        min_liquidity_betfair: float = 50.0,
        min_liquidity_matchbook_br: float = 50.0,
    ) -> None:
        self.output_dir = output_dir
        self.settings = settings
        self.min_liquidity_betfair = min_liquidity_betfair
        self.min_liquidity_matchbook_br = min_liquidity_matchbook_br

        self.betfair_commission = self.settings.commissions.betfair
        self.matchbook_br_commission = self.settings.commissions.matchbook_br

    def analyze(self) -> dict[str, Any]:
        """Loads opportunities, performs back/lay arbitrage checks, and ranks outcomes."""
        # 1. Load or regenerate opportunities report
        opp_path = self.output_dir / "moneyline_opportunities.json"
        regenerate = False

        if not opp_path.exists():
            regenerate = True
        else:
            try:
                opp_data = json.loads(opp_path.read_text(encoding="utf-8"))
                ts_str = opp_data.get("timestamp")
                if ts_str:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    delta = (now - ts).total_seconds()
                    # Regenerate if older than 1 hour
                    if delta > 3600 or delta < 0:
                        regenerate = True
                else:
                    regenerate = True
            except Exception:
                regenerate = True

        if regenerate:
            LOGGER.info("moneyline_opportunities.json is missing or out-of-date. Regenerating first...")
            from services.moneyline_opportunity_scanner import MoneylineOpportunityScanner
            scanner = MoneylineOpportunityScanner(self.output_dir, self.settings)
            opp_data = scanner.scan()
        else:
            LOGGER.info("Loading existing moneyline_opportunities.json...")
            opp_data = json.loads(opp_path.read_text(encoding="utf-8"))

        opportunities = opp_data.get("opportunities", []) or []

        # 2. Load the full comparison report
        comp_path = self.output_dir / "moneyline_comparison_report.json"
        if not comp_path.exists():
            raise FileNotFoundError(
                f"moneyline_comparison_report.json not found at {comp_path}. Please run comparison first."
            )

        comp_data = json.loads(comp_path.read_text(encoding="utf-8"))

        # Index comparisons by (sport_name, event_name_matchbook, selection_matchbook, side)
        comparisons_by_key = {}
        for row in comp_data.get("comparisons", []) or []:
            key = (
                row.get("sport_name"),
                row.get("event_name_matchbook"),
                row.get("selection_matchbook"),
                row.get("side"),
            )
            comparisons_by_key[key] = row

        analysis_results = []

        # 3. Analyze each opportunity
        for opp in opportunities:
            sport_name = opp.get("sport_name")
            event_mb = opp.get("event_name_matchbook")
            selection_mb = opp.get("selection_matchbook")
            event_pair_confidence = opp.get("event_pair_confidence")
            selection_match_confidence = opp.get("selection_match_confidence")

            # Look up back and lay rows
            back_key = (sport_name, event_mb, selection_mb, "back")
            lay_key = (sport_name, event_mb, selection_mb, "lay")
            back_row = comparisons_by_key.get(back_key)
            lay_row = comparisons_by_key.get(lay_key)

            # Default fields
            back_source = None
            lay_source = None
            back_raw_odd = None
            lay_raw_odd = None
            back_net_odds = None
            lay_net_odds = None
            back_liquidity = None
            lay_liquidity = None
            is_cross_exchange = False
            possible_arbitrage = False
            arbitrage_score = None
            gap_to_arbitrage = None
            gap_to_arbitrage_percent = None
            reason = ""

            # Protection 1: Check if both back and lay sides exist
            if not back_row or not lay_row:
                possible_arbitrage = False
                reason = "missing_back_or_lay_side"

                # Extract whatever fields are available
                if back_row:
                    mb_back = float(back_row.get("odd_matchbook") or 0)
                    bf_back = float(back_row.get("odd_betfair") or 0)
                    mb_back_net = self._net_back_odds(mb_back, self.matchbook_br_commission)
                    bf_back_net = self._net_back_odds(bf_back, self.betfair_commission)
                    if bf_back_net >= mb_back_net:
                        back_source = "betfair"
                        back_raw_odd = bf_back
                        back_net_odds = bf_back_net
                        back_liquidity = float(back_row.get("liquidity_betfair") or 0)
                    else:
                        back_source = "matchbook-br"
                        back_raw_odd = mb_back
                        back_net_odds = mb_back_net
                        back_liquidity = float(back_row.get("liquidity_matchbook") or 0)

                if lay_row:
                    mb_lay = float(lay_row.get("odd_matchbook") or 0)
                    bf_lay = float(lay_row.get("odd_betfair") or 0)
                    mb_lay_net = self._net_lay_odds(mb_lay, self.matchbook_br_commission)
                    bf_lay_net = self._net_lay_odds(bf_lay, self.betfair_commission)
                    if bf_lay_net <= mb_lay_net:
                        lay_source = "betfair"
                        lay_raw_odd = bf_lay
                        lay_net_odds = bf_lay_net
                        lay_liquidity = float(lay_row.get("liquidity_betfair") or 0)
                    else:
                        lay_source = "matchbook-br"
                        lay_raw_odd = mb_lay
                        lay_net_odds = mb_lay_net
                        lay_liquidity = float(lay_row.get("liquidity_matchbook") or 0)
            else:
                # 4. Both sides exist, calculate best net odds
                # Determine back details
                mb_back = float(back_row.get("odd_matchbook") or 0)
                bf_back = float(back_row.get("odd_betfair") or 0)
                mb_back_net = self._net_back_odds(mb_back, self.matchbook_br_commission)
                bf_back_net = self._net_back_odds(bf_back, self.betfair_commission)

                if bf_back_net >= mb_back_net:
                    back_source = "betfair"
                    back_raw_odd = bf_back
                    back_net_odds = bf_back_net
                    back_liquidity = float(back_row.get("liquidity_betfair") or 0)
                else:
                    back_source = "matchbook-br"
                    back_raw_odd = mb_back
                    back_net_odds = mb_back_net
                    back_liquidity = float(back_row.get("liquidity_matchbook") or 0)

                # Determine lay details
                mb_lay = float(lay_row.get("odd_matchbook") or 0)
                bf_lay = float(lay_row.get("odd_betfair") or 0)
                mb_lay_net = self._net_lay_odds(mb_lay, self.matchbook_br_commission)
                bf_lay_net = self._net_lay_odds(bf_lay, self.betfair_commission)

                if bf_lay_net <= mb_lay_net:
                    lay_source = "betfair"
                    lay_raw_odd = bf_lay
                    lay_net_odds = bf_lay_net
                    lay_liquidity = float(lay_row.get("liquidity_betfair") or 0)
                else:
                    lay_source = "matchbook-br"
                    lay_raw_odd = mb_lay
                    lay_net_odds = mb_lay_net
                    lay_liquidity = float(lay_row.get("liquidity_matchbook") or 0)

                # Update cross exchange status
                is_cross_exchange = (back_source != lay_source)

                # 5. Evaluate Back/Lay Arbitrage
                if back_net_odds <= 0 or lay_net_odds <= 0:
                    possible_arbitrage = False
                    reason = "invalid_net_odds"
                elif back_source == lay_source:
                    possible_arbitrage = False
                    reason = "same_source_back_lay_not_cross_exchange_arbitrage"
                    if back_net_odds > lay_net_odds:
                        arbitrage_score = round(((back_net_odds / lay_net_odds) - 1.0) * 100, 4)
                        gap_to_arbitrage = 0.0
                        gap_to_arbitrage_percent = 0.0
                    else:
                        gap_to_arbitrage = round(lay_net_odds - back_net_odds, 4)
                        gap_to_arbitrage_percent = round(((lay_net_odds / back_net_odds) - 1.0) * 100, 4)
                elif back_net_odds > lay_net_odds:
                    # Verify liquidity
                    back_min_liq = (
                        self.min_liquidity_betfair if back_source == "betfair" else self.min_liquidity_matchbook_br
                    )
                    lay_min_liq = (
                        self.min_liquidity_betfair if lay_source == "betfair" else self.min_liquidity_matchbook_br
                    )

                    if back_liquidity >= back_min_liq and lay_liquidity >= lay_min_liq:
                        possible_arbitrage = True
                        reason = "Positive net margin and sufficient liquidity"
                    else:
                        possible_arbitrage = False
                        liq_reasons = []
                        if back_liquidity < back_min_liq:
                            liq_reasons.append(
                                f"back ({back_source}) liquidity {back_liquidity:.2f} < {back_min_liq:.2f}"
                            )
                        if lay_liquidity < lay_min_liq:
                            liq_reasons.append(f"lay ({lay_source}) liquidity {lay_liquidity:.2f} < {lay_min_liq:.2f}")
                        reason = "Insufficient liquidity: " + ", ".join(liq_reasons)

                    arbitrage_score = round(((back_net_odds / lay_net_odds) - 1.0) * 100, 4)
                    gap_to_arbitrage = 0.0
                    gap_to_arbitrage_percent = 0.0
                else:
                    possible_arbitrage = False
                    gap_to_arbitrage = round(lay_net_odds - back_net_odds, 4)
                    gap_to_arbitrage_percent = round(((lay_net_odds / back_net_odds) - 1.0) * 100, 4)
                    reason = "back_net_odds_not_greater_than_lay_net_odds"

            analysis_results.append(
                {
                    "sport_name": sport_name,
                    "market_type": "money_line",
                    "event_name_matchbook": event_mb,
                    "event_name_betfair": opp.get("event_name_betfair"),
                    "start_time_matchbook": opp.get("start_time_matchbook"),
                    "start_time_betfair": opp.get("start_time_betfair"),
                    "selection_matchbook": selection_mb,
                    "selection_betfair": opp.get("selection_betfair"),
                    "back_source": back_source,
                    "lay_source": lay_source,
                    "is_cross_exchange": is_cross_exchange,
                    "back_raw_odd": back_raw_odd,
                    "lay_raw_odd": lay_raw_odd,
                    "back_net_odds": round(back_net_odds, 4) if back_net_odds is not None else None,
                    "lay_net_odds": round(lay_net_odds, 4) if lay_net_odds is not None else None,
                    "back_liquidity": back_liquidity,
                    "lay_liquidity": lay_liquidity,
                    "possible_arbitrage": possible_arbitrage,
                    "arbitrage_score": arbitrage_score,
                    "gap_to_arbitrage": gap_to_arbitrage,
                    "gap_to_arbitrage_percent": gap_to_arbitrage_percent,
                    "event_pair_confidence": event_pair_confidence,
                    "selection_match_confidence": selection_match_confidence,
                    "reason": reason,
                }
            )

        # 6. Sort Ranking: prioritize cross-exchange first, then possible_arbitrage (True first), then gap_to_arbitrage_percent (smallest first)
        def sort_key(x: dict[str, Any]) -> tuple[int, int, float, str]:
            is_cross = 1 if x.get("is_cross_exchange") else 0
            is_arb = 1 if x["possible_arbitrage"] else 0
            gap = x["gap_to_arbitrage_percent"]
            if gap is None:
                gap = 99999.0
            return (-is_cross, -is_arb, gap, x["event_name_matchbook"] or "")

        analysis_results.sort(key=sort_key)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_evaluated": len(opportunities),
            "total_possible_arbitrages": sum(1 for r in analysis_results if r["possible_arbitrage"]),
            "results": analysis_results,
        }

        self._save_reports(report, analysis_results)
        return report

    def _net_back_odds(self, odds: float, commission: float) -> float:
        if odds <= 1.0:
            return 0.0
        return 1.0 + (odds - 1.0) * (1.0 - commission)

    def _net_lay_odds(self, odds: float, commission: float) -> float:
        if odds <= 1.0:
            return 0.0
        if commission >= 1.0:
            return 0.0
        return 1.0 + (odds - 1.0) / (1.0 - commission)

    def _save_reports(self, report: dict[str, Any], results: list[dict[str, Any]]) -> None:
        """Saves JSON and CSV reports."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        json_path = self.output_dir / "moneyline_arbitrage_analysis.json"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Saved moneyline arbitrage analysis JSON to %s", json_path)

        # Save CSV
        csv_path = self.output_dir / "moneyline_arbitrage_analysis.csv"
        fieldnames = [
            "sport_name",
            "market_type",
            "event_name_matchbook",
            "event_name_betfair",
            "selection_matchbook",
            "selection_betfair",
            "back_source",
            "lay_source",
            "is_cross_exchange",
            "back_raw_odd",
            "lay_raw_odd",
            "back_net_odds",
            "lay_net_odds",
            "back_liquidity",
            "lay_liquidity",
            "possible_arbitrage",
            "arbitrage_score",
            "gap_to_arbitrage",
            "gap_to_arbitrage_percent",
            "event_pair_confidence",
            "selection_match_confidence",
            "reason",
        ]

        try:
            with csv_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(results)
            LOGGER.info("Saved moneyline arbitrage analysis CSV to %s", csv_path)
        except Exception as exc:
            LOGGER.error("Failed to write moneyline arbitrage analysis CSV: %s", exc)
