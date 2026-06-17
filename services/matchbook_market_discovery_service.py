"""Read-only Matchbook Brasil regional market and sport discovery service."""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any
import requests

from clients.matchbook_br_client import MatchbookBRClient

LOGGER = logging.getLogger(__name__)


class MatchbookMarketDiscoveryService:
    """Discovers sports, events, markets, and selections on the regional Matchbook Brasil API."""

    def __init__(self, output_dir: Path, client: MatchbookBRClient) -> None:
        self.output_dir = output_dir
        self.client = client

    def discover(self) -> dict[str, Any]:
        LOGGER.info("Starting Matchbook BR regional market discovery...")

        headers = {
            "accept": "application/json",
            "origin": "https://mexchange.matchbook.bet.br",
            "referer": "https://mexchange.matchbook.bet.br/",
            "user-agent": "SurebetDiagnostic/1.0",
        }
        timeout = self.client.settings.request_timeout

        # 1. Fetch & Save Navigation Tree
        nav_url = f"{self.client.settings.matchbook_br_api_base_url.rstrip('/')}/api/navigation"
        LOGGER.info("Matchbook BR: fetching navigation tree from %s", nav_url)
        
        try:
            resp = requests.get(nav_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            nav_data = resp.json()
            self._save_json("matchbook_navigation_tree.json", nav_data)
        except Exception as exc:
            LOGGER.exception("Failed to fetch Matchbook BR navigation tree: %s", exc)
            raise RuntimeError(f"Failed to fetch navigation tree: {exc}")

        # Extract sports from navigation tree (type == "SPORT" under item 0)
        sports_map = {}
        if isinstance(nav_data, list) and len(nav_data) > 0:
            item_zero_tags = nav_data[0].get("meta-tags", []) or []
            for tag in item_zero_tags:
                if tag.get("type") == "SPORT":
                    sp_id = str(tag.get("id"))
                    sp_name = tag.get("name")
                    sports_map[sp_id] = {
                        "sport_id": sp_id,
                        "sport_name": sp_name,
                        "event_count": 0,
                        "market_count": 0,
                        "selection_count": 0,
                        "market_types": set(),
                        "events": []
                    }

        LOGGER.info("Matchbook BR: found %d sports in navigation tree.", len(sports_map))

        # 2. Query Events Per Sport
        events_url = f"{self.client.settings.matchbook_br_api_base_url.rstrip('/')}/api/events"
        global_market_types_counter = Counter()

        for sp_id, sport_data in sports_map.items():
            LOGGER.info("Matchbook BR: querying events for sport '%s' (ID: %s)...", sport_data["sport_name"], sp_id)
            params = {
                "offset": 0,
                "per-page": 100,
                "sort-by": "start",
                "sort-direction": "asc",
                "sport-ids": sp_id
            }
            try:
                resp_events = requests.get(events_url, headers=headers, params=params, timeout=timeout)
                if resp_events.status_code == 200:
                    payload = resp_events.json()
                    events_list = payload.get("events", []) or []
                    
                    sport_data["event_count"] = len(events_list)
                    
                    for ev in events_list:
                        ev_id = ev.get("id")
                        ev_name = ev.get("name")
                        markets_list = ev.get("markets", []) or []
                        
                        event_record = {
                            "event_id": ev_id,
                            "event_name": ev_name,
                            "markets": []
                        }
                        
                        for market in markets_list:
                            m_id = market.get("id")
                            m_name = market.get("name")
                            m_type = market.get("market-type") or m_name
                            runners = market.get("runners", []) or []
                            
                            # Update counters
                            sport_data["market_count"] += 1
                            sport_data["selection_count"] += len(runners)
                            if m_type:
                                sport_data["market_types"].add(m_type)
                                global_market_types_counter[m_type] += 1
                                
                            runner_names = [r.get("name") for r in runners if r.get("name")]
                            
                            event_record["markets"].append({
                                "market_id": m_id,
                                "market_name": m_name,
                                "market_type": m_type,
                                "selections_count": len(runners),
                                "selections": runner_names
                            })
                            
                        sport_data["events"].append(event_record)
                        
                    LOGGER.info("Matchbook BR: processed %d events, %d markets for sport '%s'.", 
                                sport_data["event_count"], sport_data["market_count"], sport_data["sport_name"])
                else:
                    LOGGER.warning("Matchbook BR: failed to fetch events for sport ID %s (Status: %d)", sp_id, resp_events.status_code)
            except Exception as e:
                LOGGER.error("Matchbook BR: error querying events for sport ID %s: %s", sp_id, e)

        # 3. Compile Catalogs
        sports_catalog = []
        market_catalog = []

        for sp_id, sport_data in sports_map.items():
            # Sports Catalog Entry
            sports_catalog.append({
                "sport_id": sport_data["sport_id"],
                "sport_name": sport_data["sport_name"],
                "event_count": sport_data["event_count"],
                "market_count": sport_data["market_count"],
                "selection_count": sport_data["selection_count"],
                "market_types": sorted(list(sport_data["market_types"]))
            })

            # Market Catalog Entry
            if sport_data["event_count"] > 0:
                market_catalog.append({
                    "sport_id": sport_data["sport_id"],
                    "sport_name": sport_data["sport_name"],
                    "events": sport_data["events"]
                })

        # Sort sports catalog: sports with active events first, then alphabetically
        sports_catalog.sort(key=lambda x: (-x["event_count"], x["sport_name"]))
        # Sort market catalog: alphabetically by sport name
        market_catalog.sort(key=lambda x: x["sport_name"])

        # Market Types Summary dictionary
        market_types_summary = dict(global_market_types_counter.most_common())

        # Save files
        self._save_json("matchbook_sports_catalog.json", sports_catalog)
        self._save_json("matchbook_market_catalog.json", market_catalog)
        self._save_json("matchbook_market_types_summary.json", market_types_summary)

        return {
            "sports": sports_catalog,
            "markets": market_catalog,
            "market_types_summary": market_types_summary
        }

    def _save_json(self, filename: str, data: Any) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / filename
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Matchbook BR Discovery: saved catalog to %s", path)
