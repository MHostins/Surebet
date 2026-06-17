"""Read-only Moneyline and head-to-head match pairing discovery service."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from clients.betfair_client import BetfairClient
from config.settings import Settings
from services.comparison_service import ComparisonService

LOGGER = logging.getLogger(__name__)


# Supported sports configurations for Matchbook BR and Betfair
SPORTS_REGISTRY = {
    "soccer": {
        "name": "Soccer",
        "matchbook_sport_id": "15",
        "betfair_event_type_id": "1",
        "matchbook_market_types": ["one_x_two"],
        "betfair_market_types": ["MATCH_ODDS"],
    },
    "tennis": {
        "name": "Tennis",
        "matchbook_sport_id": "9",
        "betfair_event_type_id": "2",
        "matchbook_market_types": ["money_line"],
        "betfair_market_types": ["MATCH_ODDS"],
    },
    "basketball": {
        "name": "Basketball",
        "matchbook_sport_id": "4",
        "betfair_event_type_id": "7522",
        "matchbook_market_types": ["money_line"],
        "betfair_market_types": ["MATCH_ODDS"],
    },
    "baseball": {
        "name": "Baseball",
        "matchbook_sport_id": "3",
        "betfair_event_type_id": "7511",
        "matchbook_market_types": ["money_line"],
        "betfair_market_types": ["MATCH_ODDS"],
    },
    "mma": {
        "name": "MMA",
        "matchbook_sport_id": "126",
        "betfair_event_type_id": "26420387",
        "matchbook_market_types": ["money_line"],
        "betfair_market_types": ["MATCH_ODDS"],
    },
    "american_football": {
        "name": "American Football",
        "matchbook_sport_id": "1",
        "betfair_event_type_id": "6423",
        "matchbook_market_types": ["money_line"],
        "betfair_market_types": ["MATCH_ODDS"],
    },
}


class MoneylineDiscoveryService:
    """Discovers Matchbook BR money_line events and matches them with Betfair equivalents."""

    def __init__(
        self,
        output_dir: Path,
        settings: Settings,
        active_sports: list[str] | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.settings = settings
        if active_sports is None:
            # By default, exclude soccer as requested for this phase
            self.active_sports = ["tennis", "basketball", "baseball", "mma", "american_football"]
        else:
            self.active_sports = active_sports

        self.comparison_service = ComparisonService(
            output_dir=self.output_dir,
            max_start_delta_minutes=self.settings.max_start_time_delta_minutes,
            min_event_match_confidence=self.settings.min_event_match_confidence,
            aliases_path=self.settings.team_aliases_path,
        )

    def run_discovery(self) -> dict[str, Any]:
        """Runs pairing discovery on active sports and returns a summary report."""
        LOGGER.info("Initializing Betfair Client authentication...")
        betfair_client = BetfairClient(self.settings)
        if not betfair_client.authenticate():
            raise RuntimeError("Failed to authenticate with Betfair API: " + "; ".join(betfair_client.errors))

        sports_summary = []
        paired_events_all = []
        unpaired_matchbook_all = []
        unpaired_betfair_all = []

        now = datetime.now(timezone.utc)
        days_ahead = 7
        total_mb_events = 0
        total_bf_events = 0

        for sport_key in self.active_sports:
            if sport_key not in SPORTS_REGISTRY:
                LOGGER.warning("Sport '%s' is not registered in the system.", sport_key)
                continue

            config = SPORTS_REGISTRY[sport_key]
            sport_name = config["name"]
            mb_sport_id = config["matchbook_sport_id"]
            bf_event_type_id = config["betfair_event_type_id"]
            mb_market_types = config["matchbook_market_types"]
            bf_market_types = config["betfair_market_types"]

            LOGGER.info("Starting discovery for Sport: %s", sport_name)

            # 1. Fetch Matchbook BR Events
            mb_events = self._fetch_matchbook_events(mb_sport_id, mb_market_types)
            total_mb_events += len(mb_events)
            LOGGER.info("  Matchbook BR: Found %d events for %s", len(mb_events), sport_name)

            # 2. Fetch Betfair Events
            bf_events = self._fetch_betfair_events(betfair_client, bf_event_type_id, bf_market_types, now, days_ahead)
            total_bf_events += len(bf_events)
            LOGGER.info("  Betfair: Found %d events for %s", len(bf_events), sport_name)

            # 3. Perform Match Pairing
            paired, unmatched_mb, unmatched_bf = self._pair_events(sport_name, mb_events, bf_events)
            paired_events_all.extend(paired)
            unpaired_matchbook_all.extend(unmatched_mb)
            unpaired_betfair_all.extend(unmatched_bf)

            # 4. Generate Notes & Summary for Sport
            mb_count = len(mb_events)
            bf_count = len(bf_events)
            paired_count = len(paired)
            pairing_pct = (paired_count / mb_count * 100) if mb_count > 0 else 0.0

            notes = []
            if bf_count == 0:
                notes.append(
                    "Betfair returned 0 events/markets for this sport. Verify if MATCH_ODDS "
                    "is correct or try testing MONEY_LINE, WINNER, MATCH_ODDS_LO_TIE."
                )
            elif mb_count > 0 and paired_count == 0:
                notes.append(
                    "Matchbook and Betfair both returned events, but 0 were successfully paired. "
                    "Verify if name formats vary significantly or if team aliases are needed."
                )

            sports_summary.append(
                {
                    "sport_name": sport_name,
                    "matchbook_sport_id": mb_sport_id,
                    "betfair_event_type_id": bf_event_type_id,
                    "matchbook_events_count": mb_count,
                    "betfair_events_count": bf_count,
                    "paired_events_count": paired_count,
                    "pairing_percentage": round(pairing_pct, 2),
                    "notes": notes,
                }
            )

        if total_mb_events > 0 and total_bf_events == 0 and betfair_client.errors:
            raise RuntimeError("Failed to fetch Betfair events due to client errors: " + "; ".join(betfair_client.errors))

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sports_summary": sports_summary,
            "paired_events": paired_events_all,
            "unpaired_events": {
                "matchbook_br": unpaired_matchbook_all,
                "betfair": unpaired_betfair_all,
            },
        }

        # Save report to outputs/moneyline_pairing_report.json
        self.output_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.output_dir / "moneyline_pairing_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Saved moneyline pairing report to %s", report_path)

        return report

    def _fetch_matchbook_events(self, sport_id: str, market_types: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch and extract events from Matchbook BR endpoint."""
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
            "market-types": ",".join(market_types),
            "markets-limit": 30,
        }

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=self.settings.request_timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            LOGGER.error("Failed to fetch Matchbook BR events for sport ID %s: %s", sport_id, exc)
            return {}

        events_data = payload.get("events", []) or []
        extracted_events = {}

        for ev in events_data:
            ev_id = ev.get("id")
            ev_name = ev.get("name")
            start_time = ev.get("start") or ev.get("start-time") or ev.get("startTime")

            # Verify the event contains at least one of the target market types
            markets = ev.get("markets", []) or []
            has_valid_market = False
            for m in markets:
                m_type = m.get("market-type")
                if m_type in market_types:
                    has_valid_market = True
                    break

            if ev_id and ev_name and start_time and has_valid_market:
                extracted_events[str(ev_id)] = {
                    "event_id": str(ev_id),
                    "event_name": ev_name,
                    "start_time": start_time,
                }

        return extracted_events

    def _fetch_betfair_events(
        self,
        betfair_client: BetfairClient,
        event_type_id: str,
        market_types: list[str],
        now: datetime,
        days_ahead: int,
    ) -> dict[str, dict[str, Any]]:
        """Fetch and extract events from Betfair listMarketCatalogue/ endpoint."""
        market_filter = {
            "eventTypeIds": [event_type_id],
            "marketTypeCodes": market_types,
            "inPlayOnly": False,
            "marketStartTime": {
                "from": now.isoformat(),
                "to": (now + timedelta(days=days_ahead)).isoformat(),
            },
        }

        catalogue = betfair_client._post_betting(
            "listMarketCatalogue/",
            {
                "filter": market_filter,
                "maxResults": "200",
                "marketProjection": ["EVENT", "MARKET_START_TIME", "MARKET_DESCRIPTION"],
                "sort": "FIRST_TO_START",
            },
        )

        extracted_events = {}
        if not catalogue:
            return extracted_events

        for market in catalogue:
            event = market.get("event")
            if not event:
                continue
            event_id = event.get("id")
            event_name = event.get("name")
            start_time = market.get("marketStartTime") or event.get("openDate")

            if event_id and event_name and start_time:
                extracted_events[str(event_id)] = {
                    "event_id": str(event_id),
                    "event_name": event_name,
                    "start_time": start_time,
                }

        return extracted_events

    def _pair_events(
        self,
        sport_name: str,
        mb_events: dict[str, dict[str, Any]],
        bf_events: dict[str, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Pairs Matchbook BR and Betfair events using time delta and name confidence."""
        paired = []
        used_bf_ids = set()

        for mb_id, mb_event in mb_events.items():
            mb_name = mb_event["event_name"]
            mb_time = self.comparison_service._parse_datetime(mb_event["start_time"])

            best_bf_id = None
            best_confidence = 0.0
            best_bf_event = None

            for bf_id, bf_event in bf_events.items():
                if bf_id in used_bf_ids:
                    continue

                bf_time = self.comparison_service._parse_datetime(bf_event["start_time"])

                # Filter by start time delta
                if mb_time and bf_time:
                    delta_minutes = abs((mb_time - bf_time).total_seconds()) / 60
                    if delta_minutes > self.comparison_service.max_start_delta_minutes:
                        continue

                bf_name = bf_event["event_name"]
                confidence = self.comparison_service._event_confidence(mb_name, bf_name)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_bf_id = bf_id
                    best_bf_event = bf_event

            if best_bf_id and best_confidence >= self.comparison_service.min_event_match_confidence:
                used_bf_ids.add(best_bf_id)
                paired.append(
                    {
                        "sport": sport_name,
                        "matchbook_event_id": mb_id,
                        "matchbook_event_name": mb_name,
                        "matchbook_start_time": mb_event["start_time"],
                        "betfair_event_id": best_bf_id,
                        "betfair_event_name": best_bf_event["event_name"],
                        "betfair_start_time": best_bf_event["start_time"],
                        "match_confidence": round(best_confidence, 4),
                    }
                )

        # Identify unpaired events
        unpaired_mb = []
        paired_mb_ids = {p["matchbook_event_id"] for p in paired}
        for mb_id, mb_event in mb_events.items():
            if mb_id not in paired_mb_ids:
                unpaired_mb.append(
                    {
                        "sport": sport_name,
                        "event_id": mb_id,
                        "event_name": mb_event["event_name"],
                        "start_time": mb_event["start_time"],
                    }
                )

        unpaired_bf = []
        for bf_id, bf_event in bf_events.items():
            if bf_id not in used_bf_ids:
                unpaired_bf.append(
                    {
                        "sport": sport_name,
                        "event_id": bf_id,
                        "event_name": bf_event["event_name"],
                        "start_time": bf_event["start_time"],
                    }
                )

        return paired, unpaired_mb, unpaired_bf
