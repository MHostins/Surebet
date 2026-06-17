"""Experimental read-only Matchbook Brazil regional API client."""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

import requests

from config.settings import Settings

LOGGER = logging.getLogger(__name__)


class MatchbookBRClient:
    """Read-only diagnostic client for the regional Matchbook Brazil events endpoint."""

    EVENTS_PATH = "/api/events"
    RAW_SAMPLE_NAME = "matchbook_br_raw_sample.json"
    NORMALIZED_SAMPLE_NAME = "matchbook_br_normalized_sample.json"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.errors: list[str] = []

    def get_normalized_odds(self) -> list[dict[str, Any]]:
        """Fetch regional events and normalize runner prices into the common odds format."""
        fetch = self._fetch_events()
        events = self._extract_events(fetch.get("payload"))
        return self._normalize_events(events)

    def fetch_events_diagnostic(self) -> dict[str, Any]:
        fetch = self._fetch_events()
        payload = fetch.get("payload")
        events = self._extract_events(payload)
        normalized_odds = self._normalize_events(events)
        markets = [market for event in events for market in self._event_markets(event)]
        markets_by_type = Counter(self._market_type(market) for market in markets)

        self._save_json_sample(self.RAW_SAMPLE_NAME, events[:5])
        self._save_json_sample(self.NORMALIZED_SAMPLE_NAME, normalized_odds[:10])

        result: dict[str, Any] = {
            "request_url": fetch["request_url"],
            "request_method": "GET",
            "cookie_sent": False,
            "status_http": fetch["status_http"],
            "content_type": fetch["content_type"],
            "events_count": len(events),
            "has_markets": bool(markets),
            "has_prices": any(self._contains_price(markets_for_event) for markets_for_event in (self._event_markets(event) for event in events)),
            "normalized_odds_count": len(normalized_odds),
            "markets_by_type": dict(markets_by_type),
            "first_10_normalized_odds": normalized_odds[:10],
            "sample_events_redacted": [self._redact_event(event) for event in events[:5]],
            "raw_sample_path": str(self.settings.output_dir / self.RAW_SAMPLE_NAME),
            "normalized_sample_path": str(self.settings.output_dir / self.NORMALIZED_SAMPLE_NAME),
            "api_errors": self.errors,
        }
        return result

    def _fetch_events(self) -> dict[str, Any]:
        url = f"{self.settings.matchbook_br_api_base_url.rstrip('/')}{self.EVENTS_PATH}"
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
            "sport-ids": 15,
            "market-types": "one_x_two,money_line,to_qualify",
            "markets-limit": 30,
        }
        result: dict[str, Any] = {
            "request_url": url,
            "status_http": None,
            "content_type": None,
            "payload": None,
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=self.settings.request_timeout)
            result["status_http"] = response.status_code
            result["content_type"] = response.headers.get("content-type")
            response.raise_for_status()
            if "json" not in (result["content_type"] or "").lower():
                self._record_error(
                    "Regional events endpoint returned non-JSON response: "
                    f"content_type={result['content_type']} body_prefix={response.text[:200]}"
                )
                return result
            result["payload"] = response.json()
        except requests.RequestException as exc:
            self._record_error(f"Regional events endpoint HTTP error: {self._format_http_error(exc)}")
        except ValueError as exc:
            self._record_error(f"Regional events endpoint invalid JSON: {exc}")
        return result

    def _normalize_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for event in events:
            event_name = event.get("name", "")
            start_time = event.get("start") or event.get("start-time") or event.get("startTime")
            for market in self._event_markets(event):
                market_type = self._market_type(market)
                for runner in self._market_runners(market):
                    selection = runner.get("name", "")
                    for price in runner.get("prices", []) or []:
                        odds = self._price_odds(price)
                        side = str(price.get("side", "")).lower()
                        if side not in {"back", "lay"} or odds <= 0:
                            continue
                        rows.append(
                            {
                                "bookmaker": "matchbook-br",
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

    def _extract_events(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("events", "data", "items", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def _event_markets(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("markets", "market-list", "marketList"):
            value = event.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _market_runners(self, market: dict[str, Any]) -> list[dict[str, Any]]:
        runners = market.get("runners")
        if isinstance(runners, list):
            return [item for item in runners if isinstance(item, dict)]
        return []

    def _market_type(self, market: dict[str, Any]) -> str:
        market_name = str(market.get("name") or market.get("name-original") or "").strip()
        market_type = str(market.get("market-type") or market.get("marketType") or "").strip()
        if market_name:
            return market_name
        aliases = {
            "one_x_two": "Match Odds",
            "money_line": "Money Line",
            "to_qualify": "To Qualify",
        }
        return aliases.get(market_type, market_type or "Unknown")

    def _contains_price(self, value: Any) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"prices", "price", "odds", "decimal-odds", "decimalOdds", "available-amount"}:
                    return True
                if self._contains_price(item):
                    return True
        elif isinstance(value, list):
            return any(self._contains_price(item) for item in value)
        return False

    def _redact_event(self, event: dict[str, Any]) -> dict[str, Any]:
        markets = self._event_markets(event)
        return {
            "id": self._redact_id(event.get("id")),
            "name": event.get("name"),
            "type": event.get("type"),
            "start": event.get("start") or event.get("start-time") or event.get("startTime"),
            "markets_count": len(markets),
            "has_prices": self._contains_price(markets),
        }

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

    def _redact_id(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        if len(text) <= 4:
            return "****"
        return f"****{text[-4:]}"

    def _save_json_sample(self, filename: str, data: Any) -> None:
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.output_dir / filename
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _format_http_error(self, exc: requests.RequestException) -> str:
        response = getattr(exc, "response", None)
        if response is None:
            return str(exc)
        body = response.text[:300].replace("\n", " ")
        return f"{exc}; body_prefix={body}"

    def _record_error(self, message: str) -> None:
        self.errors.append(message)
        LOGGER.error("Matchbook BR: %s", message)
