"""Read-only discrepancy scanner for paired odds."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


class OpportunityScanner:
    """Ranks relevant odds discrepancies without stake or arbitrage calculations."""

    def __init__(
        self,
        output_dir: Path,
        min_match_confidence: float = 0.90,
        min_difference_percent: float = 5.0,
        min_liquidity_betfair: float = 50.0,
        min_liquidity_matchbook_br: float = 50.0,
        betfair_commission: float = 0.05,
        matchbook_br_commission: float = 0.02,
        limit: int = 50,
    ) -> None:
        self.output_dir = output_dir
        self.min_match_confidence = min_match_confidence
        self.min_difference_percent = min_difference_percent
        self.min_liquidity_betfair = min_liquidity_betfair
        self.min_liquidity_matchbook_br = min_liquidity_matchbook_br
        self.betfair_commission = betfair_commission
        self.matchbook_br_commission = matchbook_br_commission
        self.limit = limit

    def scan(self) -> dict[str, Any]:
        comparison_path = self.output_dir / "comparison_report.json"
        if not comparison_path.exists():
            raise FileNotFoundError(
                f"Arquivo nao encontrado: {comparison_path}. Rode antes: py main.py --mode compare --api betfair-matchbook-br"
            )

        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        rows = comparison.get("selection_comparisons", [])
        opportunities = []
        for row in rows:
            confidence = float(row.get("match_confidence") or 0)
            if confidence < self.min_match_confidence:
                continue

            betfair_odds = float(row.get("betfair_odds") or 0)
            matchbook_odds = float(row.get("matchbook_br_odds") or 0)
            if betfair_odds <= 0 or matchbook_odds <= 0:
                continue

            betfair_liquidity = float(row.get("betfair_liquidity") or 0)
            matchbook_liquidity = float(row.get("matchbook_br_liquidity") or 0)
            liquidity_status = self._liquidity_status(betfair_liquidity, matchbook_liquidity)
            if liquidity_status != "ok":
                continue

            betfair_net_odds = self._net_odds(betfair_odds, self.betfair_commission)
            matchbook_net_odds = self._net_odds(matchbook_odds, self.matchbook_br_commission)
            net_absolute_difference = abs(betfair_net_odds - matchbook_net_odds)
            net_difference_percent = (net_absolute_difference / min(betfair_net_odds, matchbook_net_odds)) * 100
            if net_difference_percent < self.min_difference_percent:
                continue

            absolute_difference = abs(betfair_odds - matchbook_odds)
            percentage_difference = (absolute_difference / min(betfair_odds, matchbook_odds)) * 100
            opportunities.append(
                {
                    "event": row.get("event_name_betfair") or row.get("event_name_matchbook_br"),
                    "event_name_betfair": row.get("event_name_betfair"),
                    "event_name_matchbook_br": row.get("event_name_matchbook_br"),
                    "start_time_betfair": row.get("start_time_betfair"),
                    "start_time_matchbook_br": row.get("start_time_matchbook_br"),
                    "match_confidence": confidence,
                    "selection": row.get("selection_betfair") or row.get("selection_matchbook_br"),
                    "selection_betfair": row.get("selection_betfair"),
                    "selection_matchbook_br": row.get("selection_matchbook_br"),
                    "side": row.get("side"),
                    "odd_betfair": betfair_odds,
                    "odd_matchbook": matchbook_odds,
                    "betfair_net_odds": round(betfair_net_odds, 6),
                    "matchbook_br_net_odds": round(matchbook_net_odds, 6),
                    "absolute_difference": round(absolute_difference, 6),
                    "percentage_difference": round(percentage_difference, 6),
                    "net_difference_percent": round(net_difference_percent, 6),
                    "liquidity_betfair": betfair_liquidity,
                    "liquidity_matchbook": matchbook_liquidity,
                    "liquidity_status": liquidity_status,
                    "better_source": "betfair" if betfair_net_odds > matchbook_net_odds else "matchbook-br",
                }
            )

        opportunities.sort(key=lambda item: item["net_difference_percent"], reverse=True)
        top_opportunities = opportunities[: self.limit]
        report = {
            "source_report": str(comparison_path),
            "market_filter": "Match Odds",
            "min_match_confidence": self.min_match_confidence,
            "min_difference_percent": self.min_difference_percent,
            "min_liquidity_betfair": self.min_liquidity_betfair,
            "min_liquidity_matchbook_br": self.min_liquidity_matchbook_br,
            "betfair_commission": self.betfair_commission,
            "matchbook_br_commission": self.matchbook_br_commission,
            "total_compared_selections": len(rows),
            "total_candidates_after_filters": len(opportunities),
            "top_limit": self.limit,
            "top_opportunities": top_opportunities,
        }
        self._save(report, top_opportunities)
        return report

    def _net_odds(self, odds: float, commission: float) -> float:
        return 1 + (odds - 1) * (1 - commission)

    def _liquidity_status(self, betfair_liquidity: float, matchbook_liquidity: float) -> str:
        betfair_ok = betfair_liquidity >= self.min_liquidity_betfair
        matchbook_ok = matchbook_liquidity >= self.min_liquidity_matchbook_br
        if betfair_ok and matchbook_ok:
            return "ok"
        if not betfair_ok and not matchbook_ok:
            return "low_both"
        if not betfair_ok:
            return "low_betfair"
        return "low_matchbook_br"

    def _save(self, report: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "opportunities.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._write_csv(self.output_dir / "opportunities.csv", rows)

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        fieldnames = [
            "event",
            "selection",
            "side",
            "odd_betfair",
            "odd_matchbook",
            "betfair_net_odds",
            "matchbook_br_net_odds",
            "absolute_difference",
            "percentage_difference",
            "net_difference_percent",
            "liquidity_betfair",
            "liquidity_matchbook",
            "liquidity_status",
            "match_confidence",
            "better_source",
            "start_time_betfair",
            "start_time_matchbook_br",
            "event_name_betfair",
            "event_name_matchbook_br",
            "selection_betfair",
            "selection_matchbook_br",
        ]
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
