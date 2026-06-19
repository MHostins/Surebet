"""Transforms multi-bookmaker discrepancies into read-only calculated opportunities."""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

from services.opportunity_calculator import COMPLEX_MARKET_MARKERS, Opportunity, OpportunityCalculator, OpportunityLeg

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
        closest = min(
            (row["distance_to_surebet_percent"] for row in supported),
            default=None,
        )

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
            "closest_distance_to_surebet_percent": closest,
            "cross_bookmaker_candidates": sum(1 for row in opportunities if row["is_cross_bookmaker"]),
            "cross_bookmaker_surebets": sum(1 for row in surebets if row["is_cross_bookmaker"]),
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
            "closest_distance_to_surebet_percent": None,
            "cross_bookmaker_candidates": 0,
            "cross_bookmaker_surebets": 0,
            "opportunities": [],
        }

    def _build_candidates(self, comparisons: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}

        for row in comparisons:
            if str(row.get("side_matchbook", "")).lower() != "back":
                continue

            market_type = str(row.get("market_type") or "")
            if self._is_unsupported_market(market_type):
                continue

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
                    "source_candidate_count": 0,
                },
            )
            group["source_candidate_count"] += 1
            group["selections"].setdefault(selection, []).extend(self._available_back_legs(row))

        candidates: list[dict[str, Any]] = []
        for group in groups.values():
            if len(group["selections"]) != 2:
                continue
            optimized_legs = self._optimize_legs(group["selections"])
            if optimized_legs:
                candidates.append({**group, "legs": optimized_legs})
        return candidates

    def _available_back_legs(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        matchbook_net = self._float_or_zero(row.get("net_odd_matchbook") or row.get("odd_matchbook"))
        pinnacle_net = self._float_or_zero(row.get("net_odd_pinnacle") or row.get("odd_pinnacle"))

        legs: list[dict[str, Any]] = []
        if matchbook_net > 1.0:
            legs.append(
                {
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
            )
        if pinnacle_net > 1.0:
            legs.append(
                {
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
            )
        return legs

    def _optimize_legs(self, selections: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        selection_names = list(selections.keys())
        leg_options = [self._best_leg_by_bookmaker(selections[name]) for name in selection_names]
        if any(not options for options in leg_options):
            return []

        combinations = list(product(*leg_options))
        scored = [
            {
                "legs": list(combo),
                "implied_sum": sum(1.0 / leg["net_odds"] for leg in combo),
                "is_cross_bookmaker": len({leg["bookmaker"] for leg in combo}) > 1,
            }
            for combo in combinations
        ]
        min_implied = min(row["implied_sum"] for row in scored)
        best_equivalent = [
            row for row in scored
            if abs(row["implied_sum"] - min_implied) <= 1e-12
        ]
        cross_best = next((row for row in best_equivalent if row["is_cross_bookmaker"]), None)
        selected = cross_best or best_equivalent[0]
        return selected["legs"]

    def _best_leg_by_bookmaker(self, legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best: dict[str, dict[str, Any]] = {}
        for leg in legs:
            bookmaker = leg["bookmaker"]
            current = best.get(bookmaker)
            if current is None or leg["net_odds"] > current["net_odds"]:
                best[bookmaker] = leg
        return list(best.values())

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
        bookmaker_pair = [leg.bookmaker for leg in result.opportunity.legs]
        is_cross_bookmaker = len(set(bookmaker_pair)) > 1
        distance_to_surebet_percent = max(0.0, (result.total_implied_probability - 1.0) * 100.0)
        return {
            "opportunity_id": opportunity.opportunity_id,
            "sport": opportunity.sport,
            "event_name": opportunity.event_name,
            "start_time": opportunity.start_time,
            "market_type": opportunity.market_type,
            "result_count": opportunity.result_count,
            "calculation_model": opportunity.calculation_model,
            "optimization_model": "best_net_odds_per_selection",
            "source_candidate_count": candidate["source_candidate_count"],
            "selected_best_odds": {
                leg.selection: {
                    "bookmaker": leg.bookmaker,
                    "net_odds": leg.net_odds,
                }
                for leg in result.opportunity.legs
            },
            "bookmaker_pair": bookmaker_pair,
            "is_cross_bookmaker": is_cross_bookmaker,
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
            "distance_to_surebet_percent": distance_to_surebet_percent,
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
            "optimization_model",
            "source_candidate_count",
            "bookmaker_pair",
            "is_cross_bookmaker",
            "implied_sum",
            "roi_percent",
            "stake_total",
            "guaranteed_profit",
            "worst_case_profit",
            "is_surebet",
            "distance_to_surebet_percent",
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
                    "bookmaker_pair": " x ".join(row.get("bookmaker_pair", [])),
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
            "closest_distance_to_surebet_percent": report.get("closest_distance_to_surebet_percent"),
            "cross_bookmaker_candidates": report.get("cross_bookmaker_candidates", 0),
            "cross_bookmaker_surebets": report.get("cross_bookmaker_surebets", 0),
        }

    def _has_blocking_warning(self, warnings: list[str]) -> bool:
        return any(warning in BLOCKING_WARNINGS for warning in warnings)

    def _opportunity_id(self, candidate: dict[str, Any], index: int) -> str:
        raw = f"{candidate['sport']}-{candidate['event_name']}-{candidate['start_time']}-{candidate['market_type']}"
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").lower()
        return f"opp-{index:04d}-{slug[:80]}"

    def _is_unsupported_market(self, market_type: str) -> bool:
        normalized = (market_type or "").strip().lower()
        return any(marker in normalized for marker in COMPLEX_MARKET_MARKERS)

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
