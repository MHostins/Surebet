"""Read-only comparison service for moneyline odds between Matchbook BR and Betfair."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests

from clients.betfair_client import BetfairClient
from config.settings import Settings
from services.comparison_service import ComparisonService

LOGGER = logging.getLogger(__name__)


class MoneylineComparisonService:
    """Loads paired moneyline events and compares real-time odds and liquidity."""

    def __init__(self, output_dir: Path, settings: Settings) -> None:
        self.output_dir = output_dir
        self.settings = settings
        self.comparison_service = ComparisonService(
            output_dir=self.output_dir,
            max_start_delta_minutes=self.settings.max_start_time_delta_minutes,
            min_event_match_confidence=self.settings.min_event_match_confidence,
            aliases_path=self.settings.team_aliases_path,
        )

    def compare(self) -> dict[str, Any]:
        """Runs the comparison on Basketball, Baseball, and MMA paired events."""
        # 1. Protection: Load or regenerate pairing report
        report_path = self.output_dir / "moneyline_pairing_report.json"
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
            LOGGER.info("moneyline_pairing_report.json is missing or out-of-date. Regenerating first...")
            from services.moneyline_discovery_service import MoneylineDiscoveryService
            discovery_service = MoneylineDiscoveryService(self.output_dir, self.settings)
            report_data = discovery_service.run_discovery()
        else:
            LOGGER.info("Loading existing moneyline_pairing_report.json...")
            report_data = json.loads(report_path.read_text(encoding="utf-8"))

        # 2. Filter active paired events (Basketball, Baseball, MMA only)
        paired_events = report_data.get("paired_events", [])
        active_pairs = [
            p for p in paired_events
            if p.get("sport", "").lower() in {"basketball", "baseball", "mma"}
        ]
        LOGGER.info("Found %d paired events for Basketball, Baseball, MMA in the report.", len(active_pairs))

        if not active_pairs:
            LOGGER.warning("No paired events found for target sports. Moneyline comparison cannot run.")
            result = {"timestamp": datetime.now(timezone.utc).isoformat(), "comparisons": []}
            self._save_reports(result, [])
            return result

        # 3. Authenticate Betfair
        betfair_client = BetfairClient(self.settings)
        if not betfair_client.authenticate():
            raise RuntimeError("Failed to authenticate with Betfair API: " + "; ".join(betfair_client.errors))

        # 4. Fetch Betfair odds for paired event IDs
        bf_event_ids = {p["betfair_event_id"] for p in active_pairs}
        bf_odds_by_event = self._fetch_betfair_odds(betfair_client, bf_event_ids)
        if bf_event_ids and not bf_odds_by_event and betfair_client.errors:
            raise RuntimeError("Failed to fetch Betfair odds due to client errors: " + "; ".join(betfair_client.errors))

        # 5. Fetch Matchbook BR events with prices
        mb_events_by_sport = {}
        for sport_key, sport_id in [("basketball", "4"), ("baseball", "3"), ("mma", "126")]:
            mb_events_by_sport[sport_key] = self._fetch_matchbook_events_with_prices(sport_id)

        # Protect against completely empty Matchbook BR events
        total_mb_events = sum(len(evs) for evs in mb_events_by_sport.values())
        if active_pairs and total_mb_events == 0:
            raise RuntimeError("Failed to fetch Matchbook BR events (0 events returned).")

        # 6. Compare selections and calculate metrics
        comparison_rows = []

        for pair in active_pairs:
            mb_event_id = pair["matchbook_event_id"]
            bf_event_id = pair["betfair_event_id"]
            sport_name = pair["sport"]
            event_pair_confidence = pair["match_confidence"]

            sport_key = sport_name.lower().replace(" ", "_")
            mb_event = mb_events_by_sport.get(sport_key, {}).get(mb_event_id)
            if not mb_event:
                LOGGER.debug("Matchbook event %s not found in current API results.", mb_event_id)
                continue

            bf_runner_odds = bf_odds_by_event.get(bf_event_id)
            if not bf_runner_odds:
                LOGGER.debug("Betfair event %s not found in current API results.", bf_event_id)
                continue

            # Find moneyline market in Matchbook event
            money_line_market = None
            for m in mb_event.get("markets", []) or []:
                if m.get("market-type") == "money_line":
                    money_line_market = m
                    break

            if not money_line_market:
                continue

            for mb_runner in money_line_market.get("runners", []) or []:
                mb_runner_name = mb_runner.get("name")
                if not mb_runner_name:
                    continue

                # Find best matching Betfair runner
                bf_runner_name = None
                best_ratio = 0.0
                mb_norm = self.comparison_service._basic_normalize(mb_runner_name)
                for bf_name in bf_runner_odds:
                    bf_norm = self.comparison_service._basic_normalize(bf_name)
                    ratio = SequenceMatcher(None, mb_norm, bf_norm).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        bf_runner_name = bf_name

                if not bf_runner_name or best_ratio < 0.60:
                    continue

                selection_match_confidence = round(best_ratio, 4)

                # Matchbook BR best back / lay odds
                mb_prices = mb_runner.get("prices", []) or []
                mb_backs = [p for p in mb_prices if p.get("side") == "back"]
                mb_best_back = max(mb_backs, key=lambda p: p.get("odds")) if mb_backs else None

                mb_lays = [p for p in mb_prices if p.get("side") == "lay"]
                mb_best_lay = min(mb_lays, key=lambda p: p.get("odds")) if mb_lays else None

                # Betfair best back / lay odds
                bf_prices = bf_runner_odds[bf_runner_name]
                bf_best_back_odd, bf_best_back_liq = bf_prices["back"]
                bf_best_lay_odd, bf_best_lay_liq = bf_prices["lay"]

                # Compare Back odds
                if mb_best_back and bf_best_back_odd > 0:
                    mb_odd = float(mb_best_back.get("odds"))
                    mb_liq = float(mb_best_back.get("available-amount") or mb_best_back.get("availableAmount") or 0)

                    abs_diff = abs(mb_odd - bf_best_back_odd)
                    pct_diff = (abs_diff / min(mb_odd, bf_best_back_odd)) * 100

                    comparison_rows.append(
                        {
                            "sport_name": sport_name,
                            "market_type": "money_line",
                            "event_name_matchbook": mb_event.get("name"),
                            "event_name_betfair": pair["betfair_event_name"],
                            "start_time_matchbook": mb_event.get("start"),
                            "start_time_betfair": pair["betfair_start_time"],
                            "selection_matchbook": mb_runner_name,
                            "selection_betfair": bf_runner_name,
                            "side": "back",
                            "odd_matchbook": mb_odd,
                            "odd_betfair": bf_best_back_odd,
                            "liquidity_matchbook": mb_liq,
                            "liquidity_betfair": bf_best_back_liq,
                            "absolute_difference": round(abs_diff, 6),
                            "percentage_difference": round(pct_diff, 6),
                            "event_pair_confidence": event_pair_confidence,
                            "selection_match_confidence": selection_match_confidence,
                        }
                    )

                # Compare Lay odds
                if mb_best_lay and bf_best_lay_odd > 0:
                    mb_odd = float(mb_best_lay.get("odds"))
                    mb_liq = float(mb_best_lay.get("available-amount") or mb_best_lay.get("availableAmount") or 0)

                    abs_diff = abs(mb_odd - bf_best_lay_odd)
                    pct_diff = (abs_diff / min(mb_odd, bf_best_lay_odd)) * 100

                    comparison_rows.append(
                        {
                            "sport_name": sport_name,
                            "market_type": "money_line",
                            "event_name_matchbook": mb_event.get("name"),
                            "event_name_betfair": pair["betfair_event_name"],
                            "start_time_matchbook": mb_event.get("start"),
                            "start_time_betfair": pair["betfair_start_time"],
                            "selection_matchbook": mb_runner_name,
                            "selection_betfair": bf_runner_name,
                            "side": "lay",
                            "odd_matchbook": mb_odd,
                            "odd_betfair": bf_best_lay_odd,
                            "liquidity_matchbook": mb_liq,
                            "liquidity_betfair": bf_best_lay_liq,
                            "absolute_difference": round(abs_diff, 6),
                            "percentage_difference": round(pct_diff, 6),
                            "event_pair_confidence": event_pair_confidence,
                            "selection_match_confidence": selection_match_confidence,
                        }
                    )

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "comparisons": comparison_rows,
        }

        self._save_reports(result, comparison_rows)
        return result

    def _fetch_matchbook_events_with_prices(self, sport_id: str) -> dict[str, dict[str, Any]]:
        """Fetch active events and markets for a sport ID from Matchbook BR."""
        url = f"{self.settings.matchbook_br_api_base_url.rstrip('/')}/api/events"
        headers = {
            "accept": "application/json",
            "origin": "https://mexchange.matchbook.bet.br",
            "referer": "https://mexchange.matchbook.bet.br/",
            "user-agent": "SurebetDiagnostic/1.0",
        }
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
            LOGGER.error("Failed to fetch Matchbook BR events with prices for sport ID %s: %s", sport_id, exc)
            return {}

        events_data = payload.get("events", []) or []
        extracted_events = {}

        for ev in events_data:
            ev_id = ev.get("id")
            if ev_id:
                extracted_events[str(ev_id)] = ev
        return extracted_events

    def _fetch_betfair_odds(self, betfair_client: BetfairClient, event_ids: set[str]) -> dict[str, dict[str, Any]]:
        """Query Betfair listMarketCatalogue/ and listMarketBook/ to extract price book details."""
        if not event_ids:
            return {}

        market_filter = {
            "eventIds": list(event_ids),
            "marketTypeCodes": ["MATCH_ODDS"],
        }

        catalogue = betfair_client._post_betting(
            "listMarketCatalogue/",
            {
                "filter": market_filter,
                "maxResults": "200",
                "marketProjection": ["EVENT", "RUNNER_DESCRIPTION", "MARKET_START_TIME", "MARKET_DESCRIPTION"],
            },
        )

        bf_odds_by_event = {}
        if not catalogue:
            return bf_odds_by_event

        market_ids = [m["marketId"] for m in catalogue]
        books = betfair_client._fetch_market_books(market_ids)
        books_by_id = {book["marketId"]: book for book in books}

        for market in catalogue:
            market_id = market["marketId"]
            event_id = str(market.get("event", {}).get("id"))
            book = books_by_id.get(market_id)
            if not book:
                continue

            runners_by_id = {runner["selectionId"]: runner for runner in market.get("runners", [])}
            runner_prices = {}

            for runner_book in book.get("runners", []):
                runner_meta = runners_by_id.get(runner_book.get("selectionId"), {})
                runner_name = runner_meta.get("runnerName", str(runner_book.get("selectionId")))

                # Best back price (highest odds)
                back_prices = runner_book.get("ex", {}).get("availableToBack", [])
                best_back = (0.0, 0.0)
                if back_prices:
                    best_back = (float(back_prices[0].get("price", 0)), float(back_prices[0].get("size", 0)))

                # Best lay price (lowest odds)
                lay_prices = runner_book.get("ex", {}).get("availableToLay", [])
                best_lay = (0.0, 0.0)
                if lay_prices:
                    best_lay = (float(lay_prices[0].get("price", 0)), float(lay_prices[0].get("size", 0)))

                runner_prices[runner_name] = {"back": best_back, "lay": best_lay}

            bf_odds_by_event[event_id] = runner_prices

        return bf_odds_by_event

    def _save_reports(self, report: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        """Saves JSON and CSV comparison reports."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        json_path = self.output_dir / "moneyline_comparison_report.json"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Saved moneyline comparison JSON to %s", json_path)

        # Save CSV
        csv_path = self.output_dir / "moneyline_comparison_report.csv"
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
            "event_pair_confidence",
            "selection_match_confidence",
        ]

        try:
            with csv_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            LOGGER.info("Saved moneyline comparison CSV to %s", csv_path)
        except Exception as exc:
            LOGGER.error("Failed to write moneyline comparison CSV: %s", exc)
