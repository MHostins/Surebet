"""Transforms multi-bookmaker discrepancies into read-only calculated opportunities."""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.opportunity_calculator import Opportunity, OpportunityCalculator, OpportunityLeg

LOGGER = logging.getLogger(__name__)

DISCREPANCY_REPORT_NAME = "multi_bookmaker_discrepancy_report.json"
JSON_REPORT_NAME = "calculated_opportunities.json"
CSV_REPORT_NAME = "calculated_opportunities.csv"
HISTORY_NAME = "opportunity_watch_history.jsonl"

BLOCKING_WARNINGS = {
    "unsupported_calculation_model",
    "unsupported_market_type",
    "unsupported_side",
    "invalid_odds",
    "invalid_commission",
    "invalid_stake_total",
    "not_enough_legs",
    "too_many_legs",
    "result_count_mismatch",
    "duplicate_selection",
}


class OpportunityEngineService:
    """Calculates simple Back/Back opportunities from an existing discrepancy report."""

    def __init__(self, output_dir: Path, stake_total: float = 100.0) -> None:
        self.output_dir = output_dir
        self.stake_total = stake_total
        self.calculator = OpportunityCalculator()

    def calculate(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        input_path = self.output_dir / DISCREPANCY_REPORT_NAME
        timestamp = datetime.now(timezone.utc).isoformat()

        if not input_path.exists():
            report = self._empty_report(timestamp, status="missing_input")
            self._write_outputs(report)
            return report

        try:
            source_report = json.loads(input_path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.error("Failed to read discrepancy report %s: %s", input_path, exc)
            report = self._empty_report(timestamp, status="invalid_input")
            report["error"] = str(exc)
            self._write_outputs(report)
            return report

        comparisons = source_report.get("comparisons", []) or []
        candidates = self._build_candidates(comparisons)
        opportunities = [self._calculate_candidate(candidate, index) for index, candidate in enumerate(candidates, start=1)]

        supported = [row for row in opportunities if not self._has_blocking_warning(row["calculation_warnings"])]
        surebets = [row for row in supported if row["is_surebet"]]
        best = max(surebets, key=lambda row: row["roi_percent"], default=None)

        report = {
            "timestamp": timestamp,
            "status": "success",
            "source_report": str(input_path),
            "stake_total": self.stake_total,
            "total_input_comparisons": len(comparisons),
            "total_candidates": len(candidates),
            "total_supported": len(supported),
            "total_surebets": len(surebets),
            "best_roi_percent": best["roi_percent"] if best else None,
            "best_event": best["event_name"] if best else None,
            "best_market": best["market_type"] if best else None,
            "best_guaranteed_profit": best["guaranteed_profit"] if best else None,
            "opportunities": opportunities,
        }
        self._write_outputs(report)
        return report

    def _empty_report(self, timestamp: str, status: str) -> dict[str, Any]:
        return {
            "timestamp": timestamp,
            "status": status,
            "source_report": str(self.output_dir / DISCREPANCY_REPORT_NAME),
            "stake_total": self.stake_total,
            "total_input_comparisons": 0,
            "total_candidates": 0,
            "total_supported": 0,
            "total_surebets": 0,
            "best_roi_percent": None,
            "best_event": None,
            "best_market": None,
            "best_guaranteed_profit": None,
            "opportunities": [],
        }

    def _build_candidates(self, comparisons: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}

        for row in comparisons:
            if str(row.get("side_matchbook", "")).lower() != "back":
                continue

            market_type = str(row.get("market_type") or "")
            event_name = str(row.get("event_name_matchbook") or row.get("event_name_pinnacle") or "")
            start_time = str(row.get("start_time_matchbook") or row.get("start_time_pinnacle") or "")
            sport = str(row.get("sport_name") or "")
            selection = str(row.get("selection_matchbook") or row.get("selection_pinnacle") or "")
            if not event_name or not start_time or not market_type or not selection:
                continue

            key = (sport, event_name, start_time, market_type)
            group = groups.setdefault(
                key,
                {
                    "sport": sport,
                    "event_name": event_name,
                    "start_time": start_time,
                    "market_type": market_type,
                    "selections": {},
                },
            )
            selected_leg = self._best_back_leg(row)
            current = group["selections"].get(selection)
            if current is None or selected_leg["net_odds"] > current["net_odds"]:
                group["selections"][selection] = selected_leg

        candidates: list[dict[str, Any]] = []
        for group in groups.values():
            selections = list(group["selections"].values())
            if len(selections) == 2:
                candidates.append({**group, "legs": selections})
        return candidates

    def _best_back_leg(self, row: dict[str, Any]) -> dict[str, Any]:
        matchbook_net = self._float_or_zero(row.get("net_odd_matchbook") or row.get("odd_matchbook"))
        pinnacle_net = self._float_or_zero(row.get("net_odd_pinnacle") or row.get("odd_pinnacle"))

        if matchbook_net >= pinnacle_net:
            return {
                "bookmaker": "matchbook-br",
                "selection": str(row.get("selection_matchbook") or row.get("selection_pinnacle") or ""),
                "odds": self._float_or_zero(row.get("odd_matchbook") or matchbook_net),
                "net_odds": matchbook_net,
                "commission": 0.0,
                "side": "back",
                "market_type": str(row.get("market_type") or ""),
                "liquidity": self._float_or_none(row.get("liquidity_matchbook")),
                "source_row": "matchbook",
            }

        return {
            "bookmaker": "pinnacle",
            "selection": str(row.get("selection_pinnacle") or row.get("selection_matchbook") or ""),
            "odds": self._float_or_zero(row.get("odd_pinnacle") or pinnacle_net),
            "net_odds": pinnacle_net,
            "commission": 0.0,
            "side": "back",
            "market_type": str(row.get("market_type") or ""),
            "liquidity": None,
            "source_row": "pinnacle",
        }

    def _calculate_candidate(self, candidate: dict[str, Any], index: int) -> dict[str, Any]:
        legs = [
            OpportunityLeg(
                bookmaker=leg["bookmaker"],
                selection=leg["selection"],
                odds=leg["odds"],
                commission=leg["commission"],
                net_odds=leg["net_odds"],
                side=leg["side"],
                market_type=leg["market_type"],
                liquidity=leg["liquidity"],
            )
            for leg in candidate["legs"]
        ]
        opportunity = Opportunity(
            opportunity_id=self._opportunity_id(candidate, index),
            sport=candidate["sport"],
            event_name=candidate["event_name"],
            start_time=candidate["start_time"],
            market_type=candidate["market_type"],
            result_count=len(legs),
            legs=legs,
            calculation_model="simple_2_way",
        )
        result = self.calculator.calculate(opportunity, stake_total=self.stake_total)
        return {
            "opportunity_id": opportunity.opportunity_id,
            "sport": opportunity.sport,
            "event_name": opportunity.event_name,
            "start_time": opportunity.start_time,
            "market_type": opportunity.market_type,
            "result_count": opportunity.result_count,
            "calculation_model": opportunity.calculation_model,
            "legs": [
                {
                    "bookmaker": leg.bookmaker,
                    "selection": leg.selection,
                    "odds": leg.odds,
                    "net_odds": leg.net_odds,
                    "commission": leg.commission,
                    "side": leg.side,
                    "market_type": leg.market_type,
                    "liquidity": leg.liquidity,
                }
                for leg in result.opportunity.legs
            ],
            "implied_sum": result.total_implied_probability,
            "total_implied_probability": result.total_implied_probability,
            "roi_percent": result.roi_percent,
            "stake_total": result.stake_total,
            "stake_plan": {
                "stake_total": result.stake_plan.stake_total,
                "stakes_by_selection": result.stake_plan.stakes_by_selection,
                "stakes_by_bookmaker": result.stake_plan.stakes_by_bookmaker,
            },
            "return_by_outcome": result.return_by_outcome,
            "guaranteed_profit": result.guaranteed_profit,
            "worst_case_profit": result.worst_case_profit,
            "is_surebet": result.is_surebet,
            "calculation_warnings": result.calculation_warnings,
        }

    def _write_outputs(self, report: dict[str, Any]) -> None:
        json_path = self.output_dir / JSON_REPORT_NAME
        csv_path = self.output_dir / CSV_REPORT_NAME
        history_path = self.output_dir / HISTORY_NAME

        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_csv(csv_path, report.get("opportunities", []))
        with history_path.open("a", encoding="utf-8") as history_file:
            history_file.write(json.dumps(self._history_entry(report), ensure_ascii=False) + "\n")

    def _write_csv(self, csv_path: Path, opportunities: list[dict[str, Any]]) -> None:
        fieldnames = [
            "opportunity_id",
            "sport",
            "event_name",
            "start_time",
            "market_type",
            "calculation_model",
            "implied_sum",
            "roi_percent",
            "stake_total",
            "guaranteed_profit",
            "worst_case_profit",
            "is_surebet",
            "calculation_warnings",
            "stake_plan",
            "return_by_outcome",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in opportunities:
                writer.writerow({
                    **row,
                    "calculation_warnings": ";".join(row.get("calculation_warnings", [])),
                    "stake_plan": json.dumps(row.get("stake_plan", {}), ensure_ascii=False),
                    "return_by_outcome": json.dumps(row.get("return_by_outcome", {}), ensure_ascii=False),
                })

    def _history_entry(self, report: dict[str, Any]) -> dict[str, Any]:
        return {
            "timestamp": report.get("timestamp"),
            "total_candidates": report.get("total_candidates", 0),
            "total_supported": report.get("total_supported", 0),
            "total_surebets": report.get("total_surebets", 0),
            "best_roi_percent": report.get("best_roi_percent"),
            "best_event": report.get("best_event"),
            "best_market": report.get("best_market"),
            "best_guaranteed_profit": report.get("best_guaranteed_profit"),
        }

    def _has_blocking_warning(self, warnings: list[str]) -> bool:
        return any(warning in BLOCKING_WARNINGS for warning in warnings)

    def _opportunity_id(self, candidate: dict[str, Any], index: int) -> str:
        raw = f"{candidate['sport']}-{candidate['event_name']}-{candidate['start_time']}-{candidate['market_type']}"
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").lower()
        return f"opp-{index:04d}-{slug[:80]}"

    def _float_or_zero(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _float_or_none(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
