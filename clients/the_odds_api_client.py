"""Client for the-odds-api.com to retrieve bookmakers and sports odds."""

from __future__ import annotations

import logging
from typing import Any

import requests

from config.settings import Settings

LOGGER = logging.getLogger(__name__)


class TheOddsAPIClient:
    """Read-only client for The Odds API (v4)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.errors: list[str] = []

    def fetch_odds_with_status(self, sport_key: str) -> tuple[list[dict[str, Any]], int | None]:
        """Fetch odds for a specific sport key and return the parsed JSON and HTTP status code."""
        if not self.settings.the_odds_api_key:
            self._record_error("THE_ODDS_API_KEY is not configured in settings.")
            return [], None

        url = f"{self.settings.the_odds_api_base_url.rstrip('/')}/sports/{sport_key}/odds"
        params = {
            "apiKey": self.settings.the_odds_api_key,
            "regions": self.settings.the_odds_api_regions,
            "markets": "h2h",
            "oddsFormat": "decimal",
        }

        try:
            response = requests.get(url, params=params, timeout=self.settings.request_timeout)
            status_code = response.status_code
            
            # Record API quota usage from headers
            self._record_quota_usage(response.headers)

            if status_code in {401, 403}:
                self._record_error(f"Erro de chave/plano na The Odds API (HTTP {status_code}). Verifique suas credenciais e plano.")
                return [], status_code
            if status_code == 404:
                self._record_error(f"Sport key '{sport_key}' inválido ou não suportado (HTTP 404).")
                return [], status_code

            response.raise_for_status()
            return response.json(), status_code
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            if getattr(exc, "response", None) is not None:
                self._record_quota_usage(exc.response.headers)
            if status in {401, 403}:
                self._record_error(f"Erro de chave/plano na The Odds API (HTTP {status}). Verifique suas credenciais.")
            elif status == 404:
                self._record_error(f"Sport key '{sport_key}' inválido ou não suportado (HTTP 404).")
            else:
                self._record_error(f"HTTP error for sport={sport_key}: {exc} (Status: {status})")
            return [], status
        except Exception as exc:
            self._record_error(f"Failed to fetch odds for sport={sport_key}: {exc}")
            return [], None

    def fetch_odds(self, sport_key: str) -> list[dict[str, Any]]:
        """Fetch odds for a specific sport key from The Odds API."""
        odds, _ = self.fetch_odds_with_status(sport_key)
        return odds

    def discover_bookmakers(self, sports_list: list[str]) -> dict[str, Any] | None:
        """Query odds for a list of sports, extract all seen bookmakers, and check against desired ones.

        Returns None if an authentication/plan error (401/403) occurs on all attempts or initially.
        """
        sports_checked: list[str] = []
        found_bookies: dict[str, tuple[str, set[str]]] = {}  # key -> (title, set(sports))
        auth_error_encountered = False
        successful_fetches = 0

        for sport in sports_list:
            events, status = self.fetch_odds_with_status(sport)
            if status in {401, 403}:
                auth_error_encountered = True
                continue
            if status == 404:
                # Logged as invalid but we continue
                continue

            # Successful or other response
            successful_fetches += 1
            sports_checked.append(sport)

            for event in events:
                bookmakers = event.get("bookmakers", []) or []
                for bookie in bookmakers:
                    b_key = bookie.get("key", "")
                    b_title = bookie.get("title", "")
                    if b_key:
                        if b_key not in found_bookies:
                            found_bookies[b_key] = (b_title, set())
                        found_bookies[b_key][1].add(sport)

        # If we encountered auth errors and made 0 successful fetches, return None to signal authentication error
        if auth_error_encountered and successful_fetches == 0:
            return None

        # Build bookmakers_found format
        bookmakers_found_list = []
        for b_key, (b_title, sports_seen) in found_bookies.items():
            bookmakers_found_list.append({
                "key": b_key,
                "title": b_title,
                "sports_seen": sorted(list(sports_seen)),
            })

        # Sort by key for stability
        bookmakers_found_list = sorted(bookmakers_found_list, key=lambda x: x["key"])

        # Desired checks
        desired_keys = {"pinnacle", "betano", "sportingbet", "novibet", "bet365"}
        found_keys = {b["key"].lower() for b in bookmakers_found_list}

        desired_found = sorted(list(desired_keys.intersection(found_keys)))
        desired_missing = sorted(list(desired_keys.difference(found_keys)))

        return {
            "sports_checked": sports_checked,
            "bookmakers_found": bookmakers_found_list,
            "desired_bookmakers": sorted(list(desired_keys)),
            "desired_found": desired_found,
            "desired_missing": desired_missing,
        }

    def get_normalized_odds(self, sport_key: str, target_bookmaker: str = "pinnacle") -> list[dict[str, Any]]:
        """Fetch odds for a sport and return normalized rows for the target bookmaker."""
        events = self.fetch_odds(sport_key)
        normalized_rows: list[dict[str, Any]] = []

        # Map Odds API sport keys to our internal sport names
        sport_mapping = {
            "mma_mixed_martial_arts": "mma",
            "baseball_mlb": "baseball",
            "basketball_wnba": "basketball",
        }
        sport_name = sport_mapping.get(sport_key, sport_key)

        for event in events:
            home_team = event.get("home_team", "")
            away_team = event.get("away_team", "")
            event_name = f"{home_team} v {away_team}" if home_team and away_team else event.get("sport_title", "Unknown Event")
            start_time = event.get("commence_time")

            bookmakers = event.get("bookmakers", []) or []
            for bookie in bookmakers:
                bookie_key = bookie.get("key", "").lower()
                if bookie_key != target_bookmaker:
                    continue

                markets = bookie.get("markets", []) or []
                for market in markets:
                    market_key = market.get("key", "").lower()
                    if market_key != "h2h":
                        continue

                    # Market type name
                    market_type = "Match Odds" if sport_name == "soccer" else "Money Line"

                    outcomes = market.get("outcomes", []) or []
                    for outcome in outcomes:
                        selection = outcome.get("name", "")
                        odds = outcome.get("price")
                        if not selection or odds is None or odds <= 0:
                            continue

                        normalized_rows.append({
                            "event_id": str(event.get("id", "")),
                            "bookmaker": bookie_key,
                            "sport": sport_name,
                            "event_name": event_name,
                            "start_time": start_time,
                            "market_type": market_type,
                            "selection": selection,
                            "side": "back",
                            "odds": float(odds),
                            "available_liquidity": None,
                        })

        return normalized_rows

    def _record_error(self, message: str) -> None:
        self.errors.append(message)
        LOGGER.error("The Odds API: %s", message)

    def _record_quota_usage(self, headers: dict[str, str] | Any) -> None:
        """Record API quota usage from HTTP headers into usage history file."""
        remaining = headers.get("x-requests-remaining") or headers.get("X-Requests-Remaining")
        used = headers.get("x-requests-used") or headers.get("X-Requests-Used")
        last = headers.get("x-requests-last") or headers.get("X-Requests-Last")

        if remaining is None and used is None:
            return

        import json
        from datetime import datetime, timezone
        
        remaining_val = int(remaining) if remaining is not None else None
        used_val = int(used) if used is not None else None
        last_val = int(last) if last is not None else None

        usage_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "x-requests-remaining": remaining_val,
            "x-requests-used": used_val,
            "x-requests-last": last_val,
        }

        usage_history_path = self.settings.output_dir / "the_odds_api_usage_history.jsonl"
        try:
            self.settings.output_dir.mkdir(parents=True, exist_ok=True)
            with usage_history_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(usage_entry, ensure_ascii=False) + "\n")
        except Exception as io_err:
            LOGGER.error("Failed to write to the_odds_api_usage_history.jsonl: %s", io_err)
