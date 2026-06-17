"""Read-only opportunities scanner for Moneyline odds discrepancies."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import Settings

LOGGER = logging.getLogger(__name__)


class MoneylineOpportunityScanner:
    """Filters and ranks moneyline odds discrepancies after applying commissions and liquidity filters."""

    def __init__(
        self,
        output_dir: Path,
        settings: Settings,
        min_difference_percent: float = 5.0,
        min_liquidity_betfair: float = 50.0,
        min_liquidity_matchbook_br: float = 50.0,
    ) -> None:
        self.output_dir = output_dir
        self.settings = settings
        self.min_difference_percent = min_difference_percent
        self.min_liquidity_betfair = min_liquidity_betfair
        self.min_liquidity_matchbook_br = min_liquidity_matchbook_br

        self.betfair_commission = self.settings.commissions.betfair
        self.matchbook_br_commission = self.settings.commissions.matchbook_br

    def scan(self) -> dict[str, Any]:
        """Loads moneyline comparison report, filters, ranks, and saves opportunities."""
        # 1. Load or regenerate comparison report
        report_path = self.output_dir / "moneyline_comparison_report.json"
        regenerate = False

        if not report_path.exists():
            regenerate = True
        else:
            try:
                report_data = json.loads(report_path.read_text(encoding="utf-8"))
                ts_str = report_data.get("timestamp")
                if ts_str:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    delta = (now - ts).total_seconds()
                    # Regenerate if older than 1 hour (3600 seconds)
                    if delta > 3600 or delta < 0:
                        regenerate = True
                else:
                    regenerate = True
            except Exception:
                regenerate = True

        if regenerate:
            LOGGER.info("moneyline_comparison_report.json is missing or out-of-date. Regenerating first...")
            from services.moneyline_comparison_service import MoneylineComparisonService
            comparison_service = MoneylineComparisonService(self.output_dir, self.settings)
            report_data = comparison_service.compare()
        else:
            LOGGER.info("Loading existing moneyline_comparison_report.json...")
            report_data = json.loads(report_path.read_text(encoding="utf-8"))

        comparisons = report_data.get("comparisons", []) or []
        opportunities = []

        for row in comparisons:
            odd_mb = float(row.get("odd_matchbook") or 0)
            odd_bf = float(row.get("odd_betfair") or 0)
            if odd_mb <= 0 or odd_bf <= 0:
                continue

            liq_mb = float(row.get("liquidity_matchbook") or 0)
            liq_bf = float(row.get("liquidity_betfair") or 0)

            # Apply liquidity filters
            if liq_mb < self.min_liquidity_matchbook_br or liq_bf < self.min_liquidity_betfair:
                continue

            # Apply raw difference filter
            raw_diff_pct = float(row.get("percentage_difference") or 0)
            if raw_diff_pct < self.min_difference_percent:
                continue

            # Calculate net odds
            bf_net = 1 + (odd_bf - 1) * (1 - self.betfair_commission)
            mb_net = 1 + (odd_mb - 1) * (1 - self.matchbook_br_commission)

            # Calculate net differences
            net_abs_diff = abs(bf_net - mb_net)
            net_diff_pct = (net_abs_diff / min(bf_net, mb_net)) * 100

            # Determine better/worse source based on net odds
            better_source = "betfair" if bf_net > mb_net else "matchbook-br"
            worse_source = "matchbook-br" if better_source == "betfair" else "betfair"

            opportunities.append(
                {
                    "sport_name": row.get("sport_name"),
                    "market_type": "money_line",
                    "event_name_matchbook": row.get("event_name_matchbook"),
                    "event_name_betfair": row.get("event_name_betfair"),
                    "start_time_matchbook": row.get("start_time_matchbook"),
                    "start_time_betfair": row.get("start_time_betfair"),
                    "selection_matchbook": row.get("selection_matchbook"),
                    "selection_betfair": row.get("selection_betfair"),
                    "side": row.get("side"),
                    "odd_matchbook": odd_mb,
                    "odd_betfair": odd_bf,
                    "liquidity_matchbook": liq_mb,
                    "liquidity_betfair": liq_bf,
                    "absolute_difference": float(row.get("absolute_difference") or 0),
                    "percentage_difference": raw_diff_pct,
                    "better_source": better_source,
                    "worse_source": worse_source,
                    "betfair_net_odds": round(bf_net, 4),
                    "matchbook_net_odds": round(mb_net, 4),
                    "net_difference_percent": round(net_diff_pct, 4),
                    "selection_match_confidence": float(row.get("selection_match_confidence") or 0),
                    "event_pair_confidence": float(row.get("event_pair_confidence") or 0),
                }
            )

        # Sort by net_difference_percent descending
        opportunities.sort(key=lambda x: x["net_difference_percent"], reverse=True)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "min_difference_percent": self.min_difference_percent,
            "min_liquidity_betfair": self.min_liquidity_betfair,
            "min_liquidity_matchbook_br": self.min_liquidity_matchbook_br,
            "total_compared_runners": len(comparisons),
            "total_opportunities": len(opportunities),
            "opportunities": opportunities,
        }

        self._save_reports(report, opportunities)
        return report

    def _save_reports(self, report: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        """Saves JSON and CSV opportunity reports."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        json_path = self.output_dir / "moneyline_opportunities.json"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Saved moneyline opportunities JSON to %s", json_path)

        # Save CSV
        csv_path = self.output_dir / "moneyline_opportunities.csv"
        fieldnames = [
            "sport_name",
            "market_type",
            "event_name_matchbook",
            "event_name_betfair",
            "start_time_matchbook",
            "start_time_betfair",
            "selection_matchbook",
            "selection_betfair",
            "side",
            "odd_matchbook",
            "odd_betfair",
            "liquidity_matchbook",
            "liquidity_betfair",
            "absolute_difference",
            "percentage_difference",
            "better_source",
            "worse_source",
            "betfair_net_odds",
            "matchbook_net_odds",
            "net_difference_percent",
            "selection_match_confidence",
            "event_pair_confidence",
        ]

        try:
            with csv_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            LOGGER.info("Saved moneyline opportunities CSV to %s", csv_path)
        except Exception as exc:
            LOGGER.error("Failed to write moneyline opportunities CSV: %s", exc)
