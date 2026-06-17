"""Diagnostic reporting for read-only exchange data quality checks."""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from clients.betfair_client import BetfairClient
from clients.matchbook_br_client import MatchbookBRClient
from clients.matchbook_client import MatchbookClient
from config.settings import Settings

LOGGER = logging.getLogger(__name__)


class DiagnosticRunner:
    """Runs read-only diagnostics for Betfair, Matchbook, or both."""

    REPORT_NAME = "diagnostic_report.json"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.output_dir = settings.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, target: str) -> dict[str, Any]:
        target = target.lower()
        if target not in {"betfair", "matchbook", "matchbook-br", "both"}:
            raise ValueError("Diagnostic target must be: betfair, matchbook, matchbook-br, or both")

        report: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "diagnostic",
            "target": target,
            "read_only": True,
            "exchanges": {},
        }

        if target in {"betfair", "both"}:
            report["exchanges"]["betfair"] = self._run_betfair()
        if target in {"matchbook", "both"}:
            report["exchanges"]["matchbook"] = self._run_matchbook()
        if target == "matchbook-br":
            report["exchanges"]["matchbook-br"] = self._run_matchbook_br()

        report_path = self.output_dir / self.REPORT_NAME
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.info("Diagnostic report saved to %s", report_path)
        return report

    def _run_betfair(self) -> dict[str, Any]:
        client = BetfairClient(self.settings)
        started = time.perf_counter()
        auth_ok = client.authenticate()
        data = client.fetch_diagnostic_data() if auth_ok else {"catalogue": [], "books": [], "normalized_odds": []}
        elapsed = time.perf_counter() - started

        catalogue = data["catalogue"]
        rows = data["normalized_odds"]
        event_ids = {market.get("event", {}).get("id") or market.get("event", {}).get("name") for market in catalogue}
        market_counts = Counter(client.market_type_code(market) for market in catalogue)

        result = {
            "authentication_status": "success" if auth_ok else "failed",
            "response_time_seconds": round(elapsed, 3),
            "future_events_found": len([event_id for event_id in event_ids if event_id]),
            "match_odds_markets": market_counts.get("MATCH_ODDS", 0),
            "over_under_25_markets": market_counts.get("OVER_UNDER_25", 0),
            "sample_events": self._sample_betfair_events(catalogue),
            "sample_odds_with_liquidity": self._sample_odds(rows),
            "api_errors": client.errors,
        }
        self._log_exchange_result("betfair", result)
        return result

    def _run_matchbook(self) -> dict[str, Any]:
        client = MatchbookClient(self.settings)
        started = time.perf_counter()
        auth_ok = client.authenticate()
        data = client.fetch_diagnostic_data() if auth_ok else {"events": [], "normalized_odds": []}
        elapsed = time.perf_counter() - started

        events = data["events"]
        rows = data["normalized_odds"]
        market_counts = self._matchbook_market_counts(events)

        result = {
            "authentication_status": "success" if auth_ok else "failed",
            "response_time_seconds": round(elapsed, 3),
            "future_events_found": len(events),
            "match_odds_markets": market_counts.get("Match Odds", 0),
            "over_under_25_markets": market_counts.get("Over/Under 2.5 Goals", 0),
            "sample_events": self._sample_matchbook_events(events),
            "sample_odds_with_liquidity": self._sample_odds(rows),
            "api_errors": client.errors,
        }
        self._log_exchange_result("matchbook", result)
        return result

    def _run_matchbook_br(self) -> dict[str, Any]:
        client = MatchbookBRClient(self.settings)
        started = time.perf_counter()
        result = client.fetch_events_diagnostic()
        result["response_time_seconds"] = round(time.perf_counter() - started, 3)
        LOGGER.info(
            "matchbook-br diagnostic: status=%s content_type=%s events=%s normalized_odds=%s has_markets=%s has_prices=%s errors=%s cookie_sent=%s",
            result["status_http"],
            result["content_type"],
            result["events_count"],
            result["normalized_odds_count"],
            result["has_markets"],
            result["has_prices"],
            len(result["api_errors"]),
            result["cookie_sent"],
        )
        return result

    def _sample_betfair_events(self, catalogue: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        events: list[dict[str, Any]] = []
        for market in catalogue:
            event = market.get("event", {})
            event_id = event.get("id") or event.get("name")
            if not event_id or event_id in seen:
                continue
            seen.add(event_id)
            events.append(
                {
                    "event_name": event.get("name"),
                    "start_time": market.get("marketStartTime") or event.get("openDate"),
                }
            )
            if len(events) == 10:
                break
        return events

    def _sample_matchbook_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sample = []
        for event in events[:10]:
            sample.append(
                {
                    "event_name": event.get("name"),
                    "start_time": event.get("start") or event.get("start-time") or event.get("startTime"),
                }
            )
        return sample

    def _sample_odds(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sample = []
        for row in rows:
            if float(row.get("available_liquidity") or 0) <= 0:
                continue
            sample.append(row)
            if len(sample) == 10:
                break
        return sample

    def _matchbook_market_counts(self, events: list[dict[str, Any]]) -> Counter[str]:
        counts: Counter[str] = Counter()
        helper = MatchbookClient(self.settings)
        for event in events:
            for market in event.get("markets", []):
                market_type = helper._market_type(market)
                if market_type:
                    counts[market_type] += 1
        return counts

    def _log_exchange_result(self, exchange: str, result: dict[str, Any]) -> None:
        LOGGER.info(
            "%s diagnostic: auth=%s response_time=%ss events=%s match_odds=%s over_under_25=%s errors=%s",
            exchange,
            result["authentication_status"],
            result["response_time_seconds"],
            result["future_events_found"],
            result["match_odds_markets"],
            result["over_under_25_markets"],
            len(result["api_errors"]),
        )

