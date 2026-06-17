"""Read-only market and sport discovery service."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from clients.betfair_client import BetfairClient
from clients.matchbook_br_client import MatchbookBRClient

LOGGER = logging.getLogger(__name__)


class MarketDiscoveryService:
    """Maps sports and market types offered by Betfair and Matchbook BR."""

    def __init__(
        self,
        output_dir: Path,
        betfair_client: BetfairClient,
        matchbook_br_client: MatchbookBRClient,
    ) -> None:
        self.output_dir = output_dir
        self.betfair_client = betfair_client
        self.matchbook_br_client = matchbook_br_client

    def discover(self) -> dict[str, Any]:
        """Discovers sports and market types from both exchanges and saves catalogs."""
        LOGGER.info("Starting market discovery process...")

        # 1. Betfair Discovery
        bf_sports_list = []
        bf_market_types_list = []
        try:
            LOGGER.info("Authenticating Betfair...")
            if self.betfair_client.authenticate():
                # Fetch sports (event types)
                event_types = self.betfair_client._post_betting("listEventTypes/", {"filter": {}}) or []
                LOGGER.info("Betfair: found %d event types.", len(event_types))

                # Build dictionary for sports
                bf_sports_map = {}
                for et in event_types:
                    ev_type = et.get("eventType", {})
                    sp_id = str(ev_type.get("id"))
                    sp_name = ev_type.get("name")
                    bf_sports_map[sp_id] = {
                        "sport_id": sp_id,
                        "sport_name": sp_name,
                        "event_ids": set(),
                        "market_types": set(),
                        "selection_count": 0,
                        "total_markets_on_exchange": et.get("marketCount", 0),
                    }

                # Fetch market catalogue sample to aggregate event/selection counts
                LOGGER.info("Betfair: fetching market catalogue sample (max 1000)...")
                now = datetime.now(timezone.utc)
                payload = {
                    "filter": {
                        "marketStartTime": {
                            "from": now.isoformat(),
                            "to": (now + timedelta(days=7)).isoformat()
                        }
                    },
                    "maxResults": 200,
                    "marketProjection": ["EVENT", "RUNNER_DESCRIPTION", "MARKET_DESCRIPTION", "EVENT_TYPE"],
                    "sort": "FIRST_TO_START",
                }
                catalogue = self.betfair_client._post_betting("listMarketCatalogue/", payload) or []
                LOGGER.info("Betfair: retrieved %d markets for analysis.", len(catalogue))

                for market in catalogue:
                    sp_id = str(market.get("eventType", {}).get("id"))
                    if sp_id in bf_sports_map:
                        sport_data = bf_sports_map[sp_id]
                        if market.get("event"):
                            sport_data["event_ids"].add(market["event"].get("id"))
                        if market.get("description", {}).get("marketType"):
                            sport_data["market_types"].add(market["description"]["marketType"])
                        sport_data["selection_count"] += len(market.get("runners", []))

                # Convert sets to serializable formats
                for sp_id, data in bf_sports_map.items():
                    data["event_count"] = len(data["event_ids"])
                    data["market_types"] = sorted(list(data["market_types"]))
                    del data["event_ids"]
                    bf_sports_list.append(data)

                # Fetch market types catalog
                LOGGER.info("Betfair: fetching market types...")
                market_types = self.betfair_client._post_betting("listMarketTypes/", {"filter": {}}) or []
                for mt in market_types:
                    bf_market_types_list.append(
                        {
                            "market_type": mt.get("marketType"),
                            "market_count": mt.get("marketCount", 0),
                        }
                    )
            else:
                LOGGER.warning("Betfair authentication failed. Skipping Betfair discovery.")
        except Exception as exc:
            LOGGER.exception("Error during Betfair discovery: %s", exc)

        # Sort Betfair sports by event_count descending, then by name
        bf_sports_list.sort(key=lambda x: (-x.get("event_count", 0), x.get("sport_name") or ""))
        # Sort Betfair market types by market_count descending
        bf_market_types_list.sort(key=lambda x: -x.get("market_count", 0))

        # 2. Matchbook BR Discovery
        mb_sports_list = []
        mb_market_types_list = []
        try:
            LOGGER.info("Matchbook BR: fetching navigation tree...")
            # Fetch navigation to map sport IDs to names
            nav_url = f"{self.matchbook_br_client.settings.matchbook_br_api_base_url.rstrip('/')}/api/navigation"
            headers = {
                "accept": "application/json",
                "origin": "https://mexchange.matchbook.bet.br",
                "referer": "https://mexchange.matchbook.bet.br/",
                "user-agent": "SurebetDiagnostic/1.0",
            }
            nav_response = self.matchbook_br_client.settings.request_timeout
            import requests
            resp = requests.get(nav_url, headers=headers, timeout=nav_response)
            resp.raise_for_status()
            nav_data = resp.json()

            mb_sports_map = {}
            for item in nav_data:
                for tag in item.get("meta-tags", []) or []:
                    if tag.get("type") == "SPORT":
                        sp_id = str(tag.get("id"))
                        sp_name = tag.get("name")
                        mb_sports_map[sp_id] = {
                            "sport_id": sp_id,
                            "sport_name": sp_name,
                            "event_ids": set(),
                            "market_types": set(),
                            "selection_count": 0,
                        }

            LOGGER.info("Matchbook BR: found %d sports in navigation.", len(mb_sports_map))

            # Fetch active events to extract counts and market types
            LOGGER.info("Matchbook BR: fetching events sample...")
            events_url = f"{self.matchbook_br_client.settings.matchbook_br_api_base_url.rstrip('/')}/api/events"
            
            # Fetch 2 pages of 100 events to get a solid sample
            events = []
            for offset in [0, 100]:
                params = {
                    "offset": offset,
                    "per-page": 100,
                    "sort-by": "start",
                    "sort-direction": "asc",
                }
                resp_events = requests.get(events_url, headers=headers, params=params, timeout=nav_response)
                if resp_events.status_code == 200:
                    payload = resp_events.json()
                    page_events = payload.get("events", []) or []
                    events.extend(page_events)
                    if len(page_events) < 100:
                        break
                else:
                    LOGGER.warning("Matchbook BR events query offset=%d failed with status %d", offset, resp_events.status_code)
                    break

            LOGGER.info("Matchbook BR: retrieved %d events for analysis.", len(events))

            mb_market_types_counter = Counter()

            for ev in events:
                sp_id = str(ev.get("sport-id"))
                if sp_id not in mb_sports_map:
                    # Dynamically add sport if not found in navigation
                    sp_name = ev.get("sport-name") or f"Unknown (ID: {sp_id})"
                    mb_sports_map[sp_id] = {
                        "sport_id": sp_id,
                        "sport_name": sp_name,
                        "event_ids": set(),
                        "market_types": set(),
                        "selection_count": 0,
                    }
                
                sport_data = mb_sports_map[sp_id]
                sport_data["event_ids"].add(ev.get("id"))
                
                for market in ev.get("markets", []) or []:
                    m_type = market.get("market-type") or market.get("name")
                    if m_type:
                        sport_data["market_types"].add(m_type)
                        mb_market_types_counter[m_type] += 1
                    sport_data["selection_count"] += len(market.get("runners", []) or [])

            # Convert sets to serializable formats
            for sp_id, data in mb_sports_map.items():
                data["event_count"] = len(data["event_ids"])
                data["market_types"] = sorted(list(data["market_types"]))
                del data["event_ids"]
                mb_sports_list.append(data)

            # Build market types list
            for mt_name, count in mb_market_types_counter.items():
                mb_market_types_list.append(
                    {
                        "market_type": mt_name,
                        "market_count": count,
                    }
                )

        except Exception as exc:
            LOGGER.exception("Error during Matchbook BR discovery: %s", exc)

        # Sort Matchbook BR sports by event_count descending, then by name
        mb_sports_list.sort(key=lambda x: (-x.get("event_count", 0), x.get("sport_name") or ""))
        # Sort Matchbook BR market types by market_count descending
        mb_market_types_list.sort(key=lambda x: -x.get("market_count", 0))

        # 3. Save Catalogs
        sports_catalog = {
            "betfair": bf_sports_list,
            "matchbook_br": mb_sports_list,
        }
        market_types_catalog = {
            "betfair": bf_market_types_list,
            "matchbook_br": mb_market_types_list,
        }

        self._save_json("sports_catalog.json", sports_catalog)
        self._save_json("market_types_catalog.json", market_types_catalog)

        return {
            "sports": sports_catalog,
            "market_types": market_types_catalog,
        }

    def _save_json(self, filename: str, data: Any) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / filename
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Saved catalog to %s", path)
