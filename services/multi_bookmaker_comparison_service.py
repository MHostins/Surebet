"""Service to compare Matchbook BR odds against Pinnacle odds retrieved from The Odds API."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests

from clients.the_odds_api_client import TheOddsAPIClient
from config.settings import Settings
from services.comparison_service import ComparisonService
from services.odds_history_service import OddsHistoryService

LOGGER = logging.getLogger(__name__)


class MultiBookmakerComparisonService:
    """Pairs events and compares moneyline odds between Matchbook BR and Pinnacle."""

    SPORTS_CONFIG = {
        "basketball": {"matchbook_sport_id": "4", "odds_api_key": "basketball_wnba"},
        "baseball": {"matchbook_sport_id": "3", "odds_api_key": "baseball_mlb"},
        "mma": {"matchbook_sport_id": "126", "odds_api_key": "mma_mixed_martial_arts"},
    }

    def __init__(self, output_dir: Path, settings: Settings) -> None:
        self.output_dir = output_dir
        self.settings = settings
        self.comparison_service = ComparisonService(
            output_dir=self.output_dir,
            max_start_delta_minutes=self.settings.max_start_time_delta_minutes,
            min_event_match_confidence=self.settings.min_event_match_confidence,
            aliases_path=self.settings.team_aliases_path,
        )
        self.db_service = OddsHistoryService(self.settings)

    def compare(self) -> dict[str, Any]:
        """Runs the comparison POC between Matchbook BR and Pinnacle for MMA, Baseball, Basketball."""
        # Verification 1: Check API Key
        if not self.settings.the_odds_api_key:
            LOGGER.warning("THE_ODDS_API_KEY is not configured. Aborting comparison.")
            return {"status": "error", "message": "THE_ODDS_API_KEY is not configured.", "comparisons": []}

        # Verification 2: Check if Pinnacle is listed/known (optional check from diagnostics)
        bookmakers_file = self.output_dir / "the_odds_api_bookmakers.json"
        if bookmakers_file.exists():
            try:
                bookmakers = json.loads(bookmakers_file.read_text(encoding="utf-8"))
                bookmaker_rows = bookmakers.get("bookmakers_found", []) if isinstance(bookmakers, dict) else bookmakers
                pinnacle_supported = any(
                    isinstance(b, dict) and b.get("key", "").lower() == "pinnacle"
                    for b in bookmaker_rows
                )
                if not pinnacle_supported:
                    LOGGER.warning("Pinnacle is not reported as supported in the diagnostics list.")
            except Exception as exc:
                LOGGER.debug("Could not verify supported bookmakers from JSON file: %s", exc)

        # 1. Fetch and normalize Matchbook BR odds for target sports
        mb_rows = self._fetch_and_normalize_matchbook()
        LOGGER.info("Fetched %d normalized Matchbook BR rows.", len(mb_rows))

        # 2. Fetch and normalize Pinnacle odds (via The Odds API) for target sports
        odds_api_client = TheOddsAPIClient(self.settings)
        pinnacle_rows: list[dict[str, Any]] = []
        for sport, config in self.SPORTS_CONFIG.items():
            sport_key = config["odds_api_key"]
            rows = odds_api_client.get_normalized_odds(sport_key, target_bookmaker="pinnacle")
            pinnacle_rows.extend(rows)

        LOGGER.info("Fetched %d normalized Pinnacle rows.", len(pinnacle_rows))

        # Protection: If Pinnacle returns 0 odds, abort to prevent overwriting with empty reports
        if not pinnacle_rows:
            msg = "Pinnacle returned 0 odds from The Odds API. Aborting multi-bookmaker comparison to protect existing reports."
            LOGGER.warning(msg)
            return {"status": "error", "message": msg, "comparisons": []}

        # 3. Log all raw collected odds to the SQLite database
        self.db_service.log_odds(mb_rows, source_type="exchange", source_provider="matchbook-br")
        self.db_service.log_odds(pinnacle_rows, source_type="odds_feed", source_provider="the-odds-api")

        # 4. Pair events and selections
        comparison_rows, audit_rows = self._pair_and_compare(mb_rows, pinnacle_rows)

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "total_matchbook_rows": len(mb_rows),
            "total_pinnacle_rows": len(pinnacle_rows),
            "paired_comparisons_count": len(comparison_rows),
            "comparisons": comparison_rows,
        }

        # 5. Save reports
        self._save_reports(result, comparison_rows, audit_rows)

        return result

    def _fetch_and_normalize_matchbook(self) -> list[dict[str, Any]]:
        """Fetch active events and markets for MMA, Baseball, and Basketball from Matchbook BR and normalize them."""
        rows: list[dict[str, Any]] = []
        headers = {
            "accept": "application/json",
            "origin": "https://mexchange.matchbook.bet.br",
            "referer": "https://mexchange.matchbook.bet.br/",
            "user-agent": "SurebetDiagnostic/1.0",
        }

        for sport_name, config in self.SPORTS_CONFIG.items():
            sport_id = config["matchbook_sport_id"]
            url = f"{self.settings.matchbook_br_api_base_url.rstrip('/')}/api/events"
            params = {
                "offset": 0,
                "per-page": 100,
                "sort-by": "start",
                "sort-direction": "asc",
                "sport-ids": sport_id,
                "market-types": "money_line",
                "markets-limit": 30,
            }

            try:
                resp = requests.get(url, headers=headers, params=params, timeout=self.settings.request_timeout)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                LOGGER.error("Failed to fetch Matchbook BR events for sport=%s: %s", sport_name, exc)
                continue

            events = payload.get("events", []) or []
            for event in events:
                event_name = event.get("name", "")
                start_time = event.get("start") or event.get("start-time") or event.get("startTime")

                markets = event.get("markets", []) or []
                for market in markets:
                    m_type = market.get("market-type")
                    if m_type != "money_line":
                        continue

                    runners = market.get("runners", []) or []
                    for runner in runners:
                        selection = runner.get("name", "")
                        prices = runner.get("prices", []) or []
                        for price in prices:
                            odds = price.get("decimal-odds") or price.get("decimalOdds") or price.get("odds")
                            side = str(price.get("side", "")).lower()
                            liquidity = price.get("available-amount") or price.get("availableAmount") or 0.0

                            if not selection or odds is None or odds <= 1.0 or side not in {"back", "lay"}:
                                continue

                            rows.append({
                                "event_id": str(event.get("id", "")),
                                "bookmaker": "matchbook-br",
                                "sport": sport_name,
                                "event_name": event_name,
                                "start_time": start_time,
                                "market_type": "Money Line",
                                "selection": selection,
                                "side": side,
                                "odds": float(odds),
                                "available_liquidity": float(liquidity),
                            })
        return rows

    def _pair_and_compare(self, mb_rows: list[dict[str, Any]], pin_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Pair Matchbook BR events with Pinnacle events and compare odds."""
        comparison_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []

        # Group Matchbook events by sport
        mb_by_sport: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in mb_rows:
            sport = row["sport"]
            event_name = row["event_name"]
            mb_by_sport.setdefault(sport, {}).setdefault(event_name, []).append(row)

        # Group Pinnacle events by sport
        pin_by_sport: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in pin_rows:
            sport = row["sport"]
            event_name = row["event_name"]
            pin_by_sport.setdefault(sport, {}).setdefault(event_name, []).append(row)

        # Pair sport-by-sport
        for sport in self.SPORTS_CONFIG:
            mb_events = mb_by_sport.get(sport, {})
            pin_events = pin_by_sport.get(sport, {})

            if not mb_events or not pin_events:
                continue

            # We match each Matchbook event to the best Pinnacle event
            for mb_name, mb_event_rows in mb_events.items():
                first_mb_row = mb_event_rows[0]
                mb_time = self.comparison_service._parse_datetime(first_mb_row["start_time"])

                best_pin_name = None
                best_ratio = 0.0

                for pin_name, pin_event_rows in pin_events.items():
                    first_pin_row = pin_event_rows[0]
                    pin_time = self.comparison_service._parse_datetime(first_pin_row["start_time"])

                    # Time check
                    if mb_time and pin_time:
                        delta = abs((mb_time - pin_time).total_seconds()) / 60.0
                        if delta > self.settings.max_start_time_delta_minutes:
                            continue

                    ratio = self.comparison_service._event_confidence(mb_name, pin_name)
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_pin_name = pin_name

                if best_pin_name and best_ratio >= self.settings.min_event_match_confidence:
                    # Found event pair! Match runners
                    matched_mb_rows = mb_event_rows
                    matched_pin_rows = pin_events[best_pin_name]

                    # Match runner names
                    for mb_row in matched_mb_rows:
                        mb_selection = mb_row["selection"]
                        mb_side = mb_row["side"]

                        # Find matching Pinnacle selection
                        best_pin_sel = None
                        best_sel_ratio = 0.0
                        mb_sel_norm = self.comparison_service._basic_normalize(mb_selection)

                        for pin_row in matched_pin_rows:
                            pin_sel = pin_row["selection"]
                            pin_sel_norm = self.comparison_service._basic_normalize(pin_sel)
                            sel_ratio = SequenceMatcher(None, mb_sel_norm, pin_sel_norm).ratio()
                            if sel_ratio > best_sel_ratio:
                                best_sel_ratio = sel_ratio
                                best_pin_sel = pin_sel

                        if best_pin_sel and best_sel_ratio >= 0.60:
                            # Selection matched! Get the Pinnacle Back row
                            pinnacle_back_row = None
                            for pin_row in matched_pin_rows:
                                if pin_row["selection"] == best_pin_sel and pin_row["side"] == "back":
                                    pinnacle_back_row = pin_row
                                    break

                            if pinnacle_back_row:
                                mb_odd = mb_row["odds"]
                                pin_odd = pinnacle_back_row["odds"]

                                # Calculate net odds
                                # Pinnacle has 0% commission (bookmaker)
                                pin_net_back = pin_odd
                                mb_commission = self.settings.commissions.matchbook_br

                                if mb_side == "back":
                                    mb_net = 1.0 + (mb_odd - 1.0) * (1.0 - mb_commission)
                                    # For Back-Back comparison: discrepancy %
                                    abs_diff = abs(mb_net - pin_net_back)
                                    pct_diff = (abs_diff / min(mb_net, pin_net_back)) * 100.0
                                else:
                                    # mb_side == "lay"
                                    mb_net = 1.0 + (mb_odd - 1.0) / (1.0 - mb_commission)
                                    # Gap: lay vs back
                                    # We want Pinnacle Back Net Odd > Matchbook Lay Net Odd
                                    # Gap % = ((Pin Back / MB Lay) - 1.0) * 100
                                    abs_diff = pin_net_back - mb_net
                                    pct_diff = ((pin_net_back / mb_net) - 1.0) * 100.0

                                comparison_rows.append({
                                    "sport_name": sport,
                                    "market_type": "Money Line",
                                    "event_name_matchbook": mb_name,
                                    "event_name_pinnacle": best_pin_name,
                                    "start_time_matchbook": first_mb_row["start_time"],
                                    "start_time_pinnacle": pinnacle_back_row["start_time"],
                                    "selection_matchbook": mb_selection,
                                    "selection_pinnacle": best_pin_sel,
                                    "side_matchbook": mb_side,
                                    "odd_matchbook": mb_odd,
                                    "odd_pinnacle": pin_odd,
                                    "net_odd_matchbook": round(mb_net, 4),
                                    "net_odd_pinnacle": round(pin_net_back, 4),
                                    "liquidity_matchbook": mb_row["available_liquidity"],
                                    "absolute_difference": round(abs_diff, 6),
                                    "discrepancy_percent": round(pct_diff, 6),
                                    "event_pair_confidence": round(best_ratio, 4),
                                    "selection_match_confidence": round(best_sel_ratio, 4),
                                })

                                # Audit abnormal pairings (> 20% discrepancy)
                                if abs(pct_diff) > 20.0:
                                    audit_rows.append({
                                        "event_id_matchbook": str(mb_row.get("event_id", "")),
                                        "event_name_matchbook": mb_name,
                                        "event_id_pinnacle": str(pinnacle_back_row.get("event_id", "")),
                                        "event_name_pinnacle": best_pin_name,
                                        "selection_matchbook": mb_selection,
                                        "selection_pinnacle": best_pin_sel,
                                        "discrepancy_percent": round(pct_diff, 6),
                                        "odd_matchbook": mb_odd,
                                        "odd_pinnacle": pin_odd,
                                    })

        return comparison_rows, audit_rows

    def _save_reports(self, report: dict[str, Any], results: list[dict[str, Any]], audit_rows: list[dict[str, Any]]) -> None:
        """Save results to multi_bookmaker_discrepancy_report JSON and CSV files and matching_audit_report.json."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        json_path = self.output_dir / "multi_bookmaker_discrepancy_report.json"
        try:
            json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            LOGGER.info("Saved multi-bookmaker discrepancy report JSON to %s", json_path)
        except Exception as exc:
            LOGGER.error("Failed to write multi-bookmaker JSON report: %s", exc)

        # Save Audit JSON
        audit_path = self.output_dir / "matching_audit_report.json"
        try:
            audit_path.write_text(json.dumps(audit_rows, indent=2, ensure_ascii=False), encoding="utf-8")
            LOGGER.info("Saved multi-bookmaker matching audit report JSON to %s", audit_path)
        except Exception as exc:
            LOGGER.error("Failed to write matching audit JSON report: %s", exc)

        # Save CSV
        csv_path = self.output_dir / "multi_bookmaker_discrepancy_report.csv"
        fieldnames = [
            "sport_name",
            "market_type",
            "event_name_matchbook",
            "event_name_pinnacle",
            "start_time_matchbook",
            "start_time_pinnacle",
            "selection_matchbook",
            "selection_pinnacle",
            "side_matchbook",
            "odd_matchbook",
            "odd_pinnacle",
            "net_odd_matchbook",
            "net_odd_pinnacle",
            "liquidity_matchbook",
            "absolute_difference",
            "discrepancy_percent",
            "event_pair_confidence",
            "selection_match_confidence",
        ]

        try:
            with csv_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(results)
            LOGGER.info("Saved multi-bookmaker discrepancy report CSV to %s", csv_path)
        except Exception as exc:
            LOGGER.error("Failed to write multi-bookmaker CSV report: %s", exc)
