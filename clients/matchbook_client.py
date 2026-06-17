"""Read-only Matchbook API client."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from config.settings import Settings

LOGGER = logging.getLogger(__name__)


class MatchbookClient:
    """Read-only wrapper around Matchbook event and market endpoints."""

    FOOTBALL_SPORT_ID = "15"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session_token: str | None = None
        self.errors: list[str] = []

    def authenticate(self) -> bool:
        """Authenticate with username/password and store session-token for read-only calls."""
        if not self.settings.matchbook_username or not self.settings.matchbook_password:
            self._record_error("Authentication failed: missing Matchbook environment credentials.")
            return False

        payload = {
            "username": self.settings.matchbook_username,
            "password": self.settings.matchbook_password,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SurebetDiagnostic/1.0",
        }
        try:
            response = self.session.post(
                f"{self.settings.matchbook_api_base_url.rstrip('/')}/bpapi/rest/security/session",
                json=payload,
                headers=headers,
                timeout=self.settings.request_timeout,
                allow_redirects=False,
            )
            if self._is_redirect(response):
                self._record_error(self._redirect_error("Authentication", response))
                return False
            response.raise_for_status()
            if "json" not in response.headers.get("content-type", "").lower():
                self._record_error(self._non_json_error("Authentication", response))
                return False
            data = response.json()
        except requests.RequestException as exc:
            self._record_error(f"Authentication failed: HTTP error: {self._format_http_error(exc)}")
            return False
        except ValueError as exc:
            self._record_error(f"Authentication failed: invalid response: {exc}")
            return False

        token = data.get("session-token") or data.get("sessionToken") or data.get("token")
        if not token:
            self._record_error(f"Authentication failed: missing session-token in response: {self._safe_payload(data)}")
            return False

        self.session_token = token
        self.session.headers.update(
            {
                "session-token": token,
                "Accept": "application/json",
                "User-Agent": "SurebetDiagnostic/1.0",
            }
        )
        return True

    def fetch_future_football_markets(self, days_ahead: int = 7) -> list[dict[str, Any]]:
        """Fetch future non-live football markets and return normalized odds rows."""
        diagnostic = self.fetch_diagnostic_data(days_ahead=days_ahead)
        return diagnostic["normalized_odds"]

    def fetch_diagnostic_data(self, days_ahead: int = 7) -> dict[str, Any]:
        """Fetch raw diagnostic data without placing or preparing any bets."""
        if not self.session_token and not self.authenticate():
            return {"events": [], "normalized_odds": []}

        now = datetime.now(timezone.utc)
        params = {
            "sport-ids": self.FOOTBALL_SPORT_ID,
            "states": "open",
            "exchange-type": "back-lay",
            "odds-type": "DECIMAL",
            "include-prices": "true",
            "per-page": 200,
            "after": now.isoformat(),
            "before": (now + timedelta(days=days_ahead)).isoformat(),
        }
        try:
            response = self.session.get(
                f"{self.settings.matchbook_api_base_url.rstrip('/')}/edge/rest/events",
                params=params,
                timeout=self.settings.request_timeout,
                allow_redirects=False,
            )
            if self._is_redirect(response):
                self._record_error(self._redirect_error("Events endpoint", response))
                return {"events": [], "normalized_odds": []}
            response.raise_for_status()
            if "json" not in response.headers.get("content-type", "").lower():
                self._record_error(self._non_json_error("Events endpoint", response))
                return {"events": [], "normalized_odds": []}
            data = response.json()
        except requests.RequestException as exc:
            self._record_error(f"Events endpoint HTTP error: {self._format_http_error(exc)}")
            return {"events": [], "normalized_odds": []}
        except ValueError as exc:
            self._record_error(f"Events endpoint invalid response: {exc}")
            return {"events": [], "normalized_odds": []}

        events = data.get("events", data if isinstance(data, list) else [])
        future_events = [event for event in events if not event.get("in-running-flag") and not event.get("inRunningFlag")]
        return {
            "events": future_events,
            "normalized_odds": self._normalize_events(future_events),
        }

    def _normalize_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for event in events:
            event_name = event.get("name", "")
            start_time = event.get("start") or event.get("start-time") or event.get("startTime")
            for market in event.get("markets", []):
                market_type = self._market_type(market)
                if not market_type:
                    continue
                for runner in market.get("runners", []):
                    selection = runner.get("name", "")
                    prices = runner.get("prices", [])
                    if not prices:
                        LOGGER.info("Matchbook market without liquidity: %s | %s | %s", event_name, market_type, selection)
                        continue
                    for side, price in self._best_prices_by_side(prices).items():
                        odds = self._price_odds(price)
                        if odds <= 0:
                            continue
                        rows.append(
                            {
                                "bookmaker": "matchbook",
                                "event_name": event_name,
                                "start_time": start_time,
                                "market_type": market_type,
                                "selection": selection,
                                "side": side,
                                "odds": odds,
                                "available_liquidity": self._price_liquidity(price),
                            }
                        )
        return rows

    def _market_type(self, market: dict[str, Any]) -> str | None:
        name = (market.get("name") or market.get("market-type") or market.get("marketType") or "").lower()
        if "match odds" in name or name in {"winner", "1x2", "moneyline"}:
            return "Match Odds"
        if "over/under 2.5" in name or "total goals 2.5" in name or "2.5 goals" in name:
            return "Over/Under 2.5 Goals"
        return None

    def _best_prices_by_side(self, prices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        best: dict[str, dict[str, Any]] = {}
        for price in prices:
            side_raw = (price.get("side") or price.get("exchange-type") or price.get("exchangeType") or "").lower()
            side = "lay" if "lay" in side_raw else "back"
            price_odds = self._price_odds(price)
            best_odds = self._price_odds(best.get(side, {}))
            if side not in best or price_odds > best_odds:
                best[side] = price
        return best

    def _price_odds(self, price: dict[str, Any]) -> float:
        return float(price.get("decimal-odds") or price.get("decimalOdds") or price.get("odds") or 0)

    def _price_liquidity(self, price: dict[str, Any]) -> float:
        return float(
            price.get("available-amount")
            or price.get("availableAmount")
            or price.get("available")
            or price.get("stake")
            or 0
        )

    def _is_redirect(self, response: requests.Response) -> bool:
        return 300 <= response.status_code < 400

    def _redirect_error(self, context: str, response: requests.Response) -> str:
        return (
            f"{context} failed: HTTP {response.status_code} redirect to "
            f"{response.headers.get('location')}; configured MATCHBOOK_API_BASE_URL may not expose the API endpoint."
        )

    def _non_json_error(self, context: str, response: requests.Response) -> str:
        body = response.text[:300].replace("\n", " ")
        return (
            f"{context} failed: non-JSON response from API endpoint; "
            f"status={response.status_code}; content-type={response.headers.get('content-type')}; body_prefix={body}"
        )

    def _format_http_error(self, exc: requests.RequestException) -> str:
        response = getattr(exc, "response", None)
        if response is None:
            return str(exc)
        body = response.text[:500].replace("\n", " ")
        return f"{exc}; response_body={body}"

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if "token" not in key.lower()}

    def _record_error(self, message: str) -> None:
        self.errors.append(message)
        LOGGER.error("Matchbook: %s", message)
