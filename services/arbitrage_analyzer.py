"""Read-only arbitrage analyzer service with gap diagnostics."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


class ArbitrageAnalyzer:
    """Evaluates theoretical arbitrage (surebets) and calculates gap diagnostics."""

    def __init__(
        self,
        output_dir: Path,
        min_liquidity_betfair: float = 50.0,
        min_liquidity_matchbook_br: float = 50.0,
        betfair_commission: float = 0.05,
        matchbook_br_commission: float = 0.02,
    ) -> None:
        self.output_dir = output_dir
        self.min_liquidity_betfair = min_liquidity_betfair
        self.min_liquidity_matchbook_br = min_liquidity_matchbook_br
        self.betfair_commission = betfair_commission
        self.matchbook_br_commission = matchbook_br_commission

    def analyze(self) -> dict[str, Any]:
        opportunities_path = self.output_dir / "opportunities.json"
        if not opportunities_path.exists():
            raise FileNotFoundError(
                f"Arquivo nao encontrado: {opportunities_path}. Rode antes: py main.py --mode scan-opportunities"
            )

        opp_data = json.loads(opportunities_path.read_text(encoding="utf-8"))
        opportunities = opp_data.get("top_opportunities", [])

        source_report_path = Path(opp_data.get("source_report", "outputs/comparison_report.json"))
        # Fallback if path is not found directly
        if not source_report_path.exists():
            source_report_path = self.output_dir / source_report_path.name

        if not source_report_path.exists():
            raise FileNotFoundError(
                f"Arquivo de comparacao nao encontrado: {source_report_path}. Rode antes: py main.py --mode compare --api betfair-matchbook-br"
            )

        comparison_data = json.loads(source_report_path.read_text(encoding="utf-8"))
        comparisons_by_key = {}
        for row in comparison_data.get("selection_comparisons", []):
            key = (row.get("event_name_betfair"), row.get("selection_betfair"), row.get("side"))
            comparisons_by_key[key] = row

        commissions = {
            "betfair": self.betfair_commission,
            "matchbook-br": self.matchbook_br_commission,
        }

        min_liquidities = {
            "betfair": self.min_liquidity_betfair,
            "matchbook-br": self.min_liquidity_matchbook_br,
        }

        analysis_results = []

        for opp in opportunities:
            side = opp.get("side")
            event_bf = opp.get("event_name_betfair")
            selection_bf = opp.get("selection_betfair")

            back_source = None
            lay_source = None
            back_odd_raw = None
            lay_odd_raw = None
            back_net_odds = None
            lay_net_odds = None
            back_liquidity = None
            lay_liquidity = None
            possible_arbitrage = False
            arbitrage_score = None
            reason = ""

            # Check if back and lay net odds are computable
            if side == "back":
                bf_back_net = self._net_back_odds(float(opp.get("odd_betfair", 0)), commissions["betfair"])
                mb_back_net = self._net_back_odds(float(opp.get("odd_matchbook", 0)), commissions["matchbook-br"])

                if bf_back_net >= mb_back_net:
                    back_source = "betfair"
                    back_odd_raw = float(opp.get("odd_betfair", 0))
                    back_net_odds = bf_back_net
                    back_liquidity = float(opp.get("liquidity_betfair", 0))

                    lay_source = "matchbook-br"
                    lay_key = (event_bf, selection_bf, "lay")
                    comp_row = comparisons_by_key.get(lay_key)
                    if comp_row:
                        lay_odd_raw = float(comp_row.get("matchbook_br_odds", 0))
                        lay_liquidity = float(comp_row.get("matchbook_br_liquidity", 0))
                        lay_net_odds = self._net_lay_odds(lay_odd_raw, commissions[lay_source])
                    else:
                        reason = "Opposite side (lay) odds not found in comparison report"
                else:
                    back_source = "matchbook-br"
                    back_odd_raw = float(opp.get("odd_matchbook", 0))
                    back_net_odds = mb_back_net
                    back_liquidity = float(opp.get("liquidity_matchbook", 0))

                    lay_source = "betfair"
                    lay_key = (event_bf, selection_bf, "lay")
                    comp_row = comparisons_by_key.get(lay_key)
                    if comp_row:
                        lay_odd_raw = float(comp_row.get("betfair_odds", 0))
                        lay_liquidity = float(comp_row.get("betfair_liquidity", 0))
                        lay_net_odds = self._net_lay_odds(lay_odd_raw, commissions[lay_source])
                    else:
                        reason = "Opposite side (lay) odds not found in comparison report"

            elif side == "lay":
                bf_lay_net = self._net_lay_odds(float(opp.get("odd_betfair", 0)), commissions["betfair"])
                mb_lay_net = self._net_lay_odds(float(opp.get("odd_matchbook", 0)), commissions["matchbook-br"])

                if bf_lay_net <= mb_lay_net:
                    lay_source = "betfair"
                    lay_odd_raw = float(opp.get("odd_betfair", 0))
                    lay_net_odds = bf_lay_net
                    lay_liquidity = float(opp.get("liquidity_betfair", 0))

                    back_source = "matchbook-br"
                    back_key = (event_bf, selection_bf, "back")
                    comp_row = comparisons_by_key.get(back_key)
                    if comp_row:
                        back_odd_raw = float(comp_row.get("matchbook_br_odds", 0))
                        back_liquidity = float(comp_row.get("matchbook_br_liquidity", 0))
                        back_net_odds = self._net_back_odds(back_odd_raw, commissions[back_source])
                    else:
                        reason = "Opposite side (back) odds not found in comparison report"
                else:
                    lay_source = "matchbook-br"
                    lay_odd_raw = float(opp.get("odd_matchbook", 0))
                    lay_net_odds = mb_lay_net
                    lay_liquidity = float(opp.get("liquidity_matchbook", 0))

                    back_source = "betfair"
                    back_key = (event_bf, selection_bf, "back")
                    comp_row = comparisons_by_key.get(back_key)
                    if comp_row:
                        back_odd_raw = float(comp_row.get("betfair_odds", 0))
                        back_liquidity = float(comp_row.get("betfair_liquidity", 0))
                        back_net_odds = self._net_back_odds(back_odd_raw, commissions[back_source])
                    else:
                        reason = "Opposite side (back) odds not found in comparison report"

            # Compute gap fields and evaluate
            gap_to_arbitrage = None
            gap_to_arbitrage_percent = None
            required_back_net_odds = None

            if back_net_odds is not None and lay_net_odds is not None:
                if back_net_odds <= 0 or lay_net_odds <= 0:
                    reason = "invalid_net_odds"
                    possible_arbitrage = False
                else:
                    required_back_net_odds = round(lay_net_odds, 4)
                    if back_net_odds > lay_net_odds:
                        gap_to_arbitrage = 0.0
                        gap_to_arbitrage_percent = 0.0
                        arbitrage_score = round(((back_net_odds / lay_net_odds) - 1.0) * 100, 4)

                        back_min_liq = min_liquidities[back_source]
                        lay_min_liq = min_liquidities[lay_source]

                        if back_liquidity >= back_min_liq and lay_liquidity >= lay_min_liq:
                            possible_arbitrage = True
                            reason = "Positive net margin and sufficient liquidity"
                        else:
                            reasons = []
                            if back_liquidity < back_min_liq:
                                reasons.append(f"back ({back_source}) liquidity {back_liquidity:.2f} < {back_min_liq:.2f}")
                            if lay_liquidity < lay_min_liq:
                                reasons.append(f"lay ({lay_source}) liquidity {lay_liquidity:.2f} < {lay_min_liq:.2f}")
                            reason = "Insufficient liquidity: " + ", ".join(reasons)
                    else:
                        gap_to_arbitrage = round(lay_net_odds - back_net_odds, 4)
                        gap_to_arbitrage_percent = round(((lay_net_odds / back_net_odds) - 1.0) * 100, 4)
                        possible_arbitrage = False
                        if not reason:
                            reason = "back_net_odds_not_greater_than_lay_net_odds"
                        arbitrage_score = None
            else:
                possible_arbitrage = False
                if not reason:
                    reason = "Unable to evaluate"

            analysis_results.append(
                {
                    "event": opp.get("event"),
                    "selection": opp.get("selection"),
                    "back_source": back_source,
                    "lay_source": lay_source,
                    "back_odd_raw": round(back_odd_raw, 2) if back_odd_raw is not None else None,
                    "lay_odd_raw": round(lay_odd_raw, 2) if lay_odd_raw is not None else None,
                    "current_back_net_odds": round(back_net_odds, 4) if back_net_odds is not None else None,
                    "current_lay_net_odds": round(lay_net_odds, 4) if lay_net_odds is not None else None,
                    "required_back_net_odds": required_back_net_odds,
                    "gap_to_arbitrage": gap_to_arbitrage,
                    "gap_to_arbitrage_percent": gap_to_arbitrage_percent,
                    "back_liquidity": round(back_liquidity, 2) if back_liquidity is not None else None,
                    "lay_liquidity": round(lay_liquidity, 2) if lay_liquidity is not None else None,
                    "possible_arbitrage": possible_arbitrage,
                    "arbitrage_score": arbitrage_score,
                    "reason": reason,
                    "match_confidence": opp.get("match_confidence"),
                }
            )

        # Sort main analysis
        analysis_results.sort(
            key=lambda x: (
                1 if x["possible_arbitrage"] else 0,
                x["arbitrage_score"] if x["arbitrage_score"] is not None else -99999.0,
                -(x["gap_to_arbitrage_percent"]) if x["gap_to_arbitrage_percent"] is not None else -99999.0,
                x["event"] or "",
            ),
            reverse=True,
        )

        # Create Gap report sorted by gap_to_arbitrage_percent ascending (smallest gap first)
        gap_results = [dict(r) for r in analysis_results]
        
        def sort_key_gap(x):
            gap = x["gap_to_arbitrage_percent"]
            if gap is None:
                return (99999.0, x["event"] or "")
            return (gap, x["event"] or "")
            
        gap_results.sort(key=sort_key_gap)

        report = {
            "source_opportunities": str(opportunities_path),
            "total_evaluated": len(opportunities),
            "total_possible_arbitrages": sum(1 for r in analysis_results if r["possible_arbitrage"]),
            "results": analysis_results,
        }

        self._save_report(report, analysis_results)
        self._save_gap_report(opportunities_path, len(opportunities), gap_results)
        return report

    def _net_back_odds(self, odds: float, commission: float) -> float:
        if odds <= 1:
            return 0.0
        return 1.0 + (odds - 1.0) * (1.0 - commission)

    def _net_lay_odds(self, odds: float, commission: float) -> float:
        if odds <= 1:
            return 0.0
        if commission >= 1.0:
            return 0.0
        return 1.0 + (odds - 1.0) / (1.0 - commission)

    def _save_report(self, report: dict[str, Any], results: list[dict[str, Any]]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "arbitrage_analysis.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        
        # Write CSV
        fieldnames = [
            "event",
            "selection",
            "back_source",
            "lay_source",
            "back_odd_raw",
            "lay_odd_raw",
            "current_back_net_odds",
            "current_lay_net_odds",
            "required_back_net_odds",
            "gap_to_arbitrage",
            "gap_to_arbitrage_percent",
            "back_liquidity",
            "lay_liquidity",
            "possible_arbitrage",
            "arbitrage_score",
            "reason",
        ]
        with (self.output_dir / "arbitrage_analysis.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)

    def _save_gap_report(self, opportunities_path: Path, total_evaluated: int, results: list[dict[str, Any]]) -> None:
        gap_report = {
            "source_opportunities": str(opportunities_path),
            "total_evaluated": total_evaluated,
            "closest_to_arbitrage": results,
        }
        (self.output_dir / "arbitrage_gap_report.json").write_text(
            json.dumps(gap_report, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        fieldnames = [
            "event",
            "selection",
            "back_source",
            "lay_source",
            "raw_back_odd",      # raw_back_odd
            "raw_lay_odd",       # raw_lay_odd
            "current_back_net_odds",
            "current_lay_net_odds",
            "required_back_net_odds",
            "gap_to_arbitrage",
            "gap_to_arbitrage_percent",
            "back_liquidity",
            "lay_liquidity",
            "possible_arbitrage",
            "reason",
            "match_confidence",
        ]
        
        # Prepare rows for CSV with specific key mapping if needed
        csv_rows = []
        for r in results:
            row = dict(r)
            row["raw_back_odd"] = r.get("back_odd_raw")
            row["raw_lay_odd"] = r.get("lay_odd_raw")
            csv_rows.append(row)

        with (self.output_dir / "arbitrage_gap_report.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(csv_rows)
