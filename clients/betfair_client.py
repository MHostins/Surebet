"""Read-only Betfair Exchange API client."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from config.settings import Settings

LOGGER = logging.getLogger(__name__)


class BetfairClient:
    """Read-only wrapper around Betfair Exchange list endpoints."""

    SOCCER_EVENT_TYPE_ID = "1"
    MARKET_BOOK_BATCH_SIZE = 40
    MARKET_TYPES = {
        "MATCH_ODDS": "Match Odds",
        "OVER_UNDER_25": "Over/Under 2.5 Goals",
    }
    MARKET_NAMES = {
        "match odds": "MATCH_ODDS",
        "over/under 2.5 goals": "OVER_UNDER_25",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session_token: str | None = None
        self.errors: list[str] = []

    def authenticate(self) -> bool:
        """Authenticate with Betfair Brazil SSO certificate login, with 1 retry on failure."""
        if not self.settings.betfair_username or not self.settings.betfair_password or not self.settings.betfair_app_key:
            self._record_error("Authentication failed: missing Betfair username, password or app key.")
            return False

        cert = self._resolve_cert()
        if not cert:
            self._record_error("Authentication failed: missing Betfair certificate configuration.")
            return False

        headers = {
            "Accept": "application/json",
            "X-Application": self.settings.betfair_app_key.strip(),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        payload = {
            "username": self.settings.betfair_username,
            "password": self.settings.betfair_password,
        }

        attempts = 2
        for attempt in range(1, attempts + 1):
            try:
                LOGGER.info("Betfair authenticate attempt %d/%d...", attempt, attempts)
                response = self.session.post(
                    self.settings.betfair_cert_login_url,
                    data=payload,
                    headers=headers,
                    cert=cert,
                    timeout=self.settings.request_timeout,
                )
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as exc:
                self._record_error(f"Authentication attempt {attempt} failed: HTTP error: {exc}")
                if attempt < attempts:
                    continue
                return False
            except ValueError as exc:
                self._record_error(f"Authentication attempt {attempt} failed: invalid JSON response: {exc}")
                if attempt < attempts:
                    continue
                return False

            if data.get("loginStatus") != "SUCCESS":
                self._record_error(f"Authentication attempt {attempt} failed: loginStatus not SUCCESS: {data}")
                if attempt < attempts:
                    continue
                return False

            token = data.get("sessionToken")
            if not token:
                self._record_error(f"Authentication attempt {attempt} failed: missing sessionToken in response: {data}")
                if attempt < attempts:
                    continue
                return False

            self.session_token = token
            self.session.headers.update(
                {
                    "X-Application": self.settings.betfair_app_key.strip(),
                    "X-Authentication": token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
            )
            LOGGER.info("Betfair authenticated successfully.")
            return True
        return False

    def fetch_future_football_markets(self, days_ahead: int = 7) -> list[dict[str, Any]]:
        """Fetch future non-live football markets and return normalized odds rows."""
        diagnostic = self.fetch_diagnostic_data(days_ahead=days_ahead)
        return diagnostic["normalized_odds"]

    def fetch_diagnostic_data(self, days_ahead: int = 7) -> dict[str, Any]:
        """Fetch raw diagnostic data without placing or preparing any bets."""
        if not self.session_token and not self.authenticate():
            return {"catalogue": [], "books": [], "normalized_odds": []}

        now = datetime.now(timezone.utc)
        market_filter = {
            "eventTypeIds": [self.SOCCER_EVENT_TYPE_ID],
            "marketTypeCodes": list(self.MARKET_TYPES.keys()),
            "inPlayOnly": False,
            "marketStartTime": {
                "from": now.isoformat(),
                "to": (now + timedelta(days=days_ahead)).isoformat(),
            },
        }

        catalogue = self._post_betting(
            "listMarketCatalogue/",
            {
                "filter": market_filter,
                "maxResults": "200",
                "marketProjection": ["EVENT", "RUNNER_DESCRIPTION", "MARKET_START_TIME", "MARKET_DESCRIPTION"],
                "sort": "FIRST_TO_START",
            },
        )
        if not catalogue:
            return {"catalogue": [], "books": [], "normalized_odds": []}

        books = self._fetch_market_books([market["marketId"] for market in catalogue])
        books_by_id = {book["marketId"]: book for book in books}
        return {
            "catalogue": catalogue,
            "books": books,
            "normalized_odds": self._normalize_markets(catalogue, books_by_id),
        }

    def market_type_code(self, market: dict[str, Any]) -> str | None:
        description_type = market.get("description", {}).get("marketType")
        if description_type in self.MARKET_TYPES:
            return description_type
        market_name = str(market.get("marketName", "")).strip().lower()
        return self.MARKET_NAMES.get(market_name)

    def _fetch_market_books(self, market_ids: list[str]) -> list[dict[str, Any]]:
        books: list[dict[str, Any]] = []
        for index in range(0, len(market_ids), self.MARKET_BOOK_BATCH_SIZE):
            batch = market_ids[index : index + self.MARKET_BOOK_BATCH_SIZE]
            result = self._post_betting(
                "listMarketBook/",
                {
                    "marketIds": batch,
                    "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
                },
            )
            if result:
                books.extend(result)
        return books

    def _post_betting(self, endpoint: str, payload: dict[str, Any], retry_on_auth_failure: bool = True) -> Any:
        url = f"{self.settings.betfair_api_base_url.rstrip('/')}/{endpoint}"
        try:
            response = self.session.post(url, json=payload, timeout=self.settings.request_timeout)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            if retry_on_auth_failure and status_code in (400, 401, 403):
                LOGGER.warning("Betfair post returned HTTP %d. Attempting session renewal...", status_code)
                if self.authenticate():
                    return self._post_betting(endpoint, payload, retry_on_auth_failure=False)
            self._record_error(f"Betfair endpoint {endpoint} HTTP error: {exc}")
        except requests.RequestException as exc:
            self._record_error(f"Betfair endpoint {endpoint} Request error: {exc}")
        except ValueError as exc:
            self._record_error(f"Betfair endpoint {endpoint} invalid response: {exc}")
        return None

    def _normalize_markets(
        self,
        catalogue: list[dict[str, Any]],
        books_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for market in catalogue:
            market_id = market["marketId"]
            book = books_by_id.get(market_id)
            if not book:
                LOGGER.warning("Betfair market without liquidity book: %s", market_id)
                continue

            runners_by_id = {runner["selectionId"]: runner for runner in market.get("runners", [])}
            event_name = market.get("event", {}).get("name", "")
            market_type_code = self.market_type_code(market)
            market_type = self.MARKET_TYPES.get(market_type_code or "", market.get("marketName", ""))
            start_time = market.get("marketStartTime") or market.get("event", {}).get("openDate")

            for runner_book in book.get("runners", []):
                runner_meta = runners_by_id.get(runner_book.get("selectionId"), {})
                selection = runner_meta.get("runnerName", str(runner_book.get("selectionId")))
                exchange_prices = runner_book.get("ex", {})
                rows.extend(
                    self._price_rows(
                        event_name=event_name,
                        start_time=start_time,
                        market_type=market_type,
                        selection=selection,
                        side="back",
                        prices=exchange_prices.get("availableToBack", []),
                    )
                )
                rows.extend(
                    self._price_rows(
                        event_name=event_name,
                        start_time=start_time,
                        market_type=market_type,
                        selection=selection,
                        side="lay",
                        prices=exchange_prices.get("availableToLay", []),
                    )
                )
        return rows

    def _price_rows(
        self,
        event_name: str,
        start_time: str,
        market_type: str,
        selection: str,
        side: str,
        prices: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not prices:
            LOGGER.info("Betfair market without liquidity: %s | %s | %s | %s", event_name, market_type, selection, side)
            return []

        best_price = prices[0]
        return [
            {
                "bookmaker": "betfair",
                "event_name": event_name,
                "start_time": start_time,
                "market_type": market_type,
                "selection": selection,
                "side": side,
                "odds": float(best_price.get("price", 0)),
                "available_liquidity": float(best_price.get("size", 0)),
            }
        ]

    def _resolve_cert(self) -> tuple[str, str] | str | None:
        if self.settings.betfair_cert_file and self.settings.betfair_key_file:
            cert_file = self.settings.betfair_cert_file
            key_file = self.settings.betfair_key_file
            if Path(cert_file).is_file() and Path(key_file).is_file():
                return cert_file, key_file
            self._record_error(f"Certificate files not found: {cert_file}, {key_file}")
            return None

        cert_path = self.settings.betfair_cert_path
        if not cert_path:
            return None
        if "," in cert_path:
            cert_file, key_file = [part.strip() for part in cert_path.split(",", maxsplit=1)]
            if Path(cert_file).is_file() and Path(key_file).is_file():
                return cert_file, key_file
            self._record_error(f"Certificate files not found: {cert_file}, {key_file}")
            return None
        if Path(cert_path).is_file():
            return cert_path
        self._record_error(f"Certificate file not found: {cert_path}")
        return None

    def _record_error(self, message: str) -> None:
        self.errors.append(message)
        LOGGER.error("Betfair: %s", message)
