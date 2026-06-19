"""Read-only parser for Novibet visible/catalog samples."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from bookmakers.novibet.novibet_models import NovibetNormalizedOdd, NovibetParseResult


class NovibetParser:
    """Parses controlled Novibet HTML snapshots without creating betting actions."""

    def parse_html(self, html: str, source_url: str, scraped_at: str) -> NovibetParseResult:
        fixture_parser = _NovibetFixtureHTMLParser()
        fixture_parser.feed(html or "")

        result = NovibetParseResult(raw_events=fixture_parser.events)
        for event in fixture_parser.events:
            sport = str(event.get("sport") or "").strip()
            event_name = str(event.get("event_name") or "").strip()
            if not sport or not event_name:
                result.warnings.append("event_missing_required_fields")
                continue

            for market in event.get("markets", []):
                market_type = self.normalize_market_type(str(market.get("market_type") or "").strip())
                if not market_type:
                    result.warnings.append("market_missing_type")
                    continue
                for outcome in market.get("outcomes", []):
                    selection = str(outcome.get("selection") or "").strip()
                    odds = self._float_or_none(outcome.get("odds"))
                    if not selection or odds is None or odds <= 1.0:
                        result.warnings.append("outcome_missing_required_fields")
                        continue
                    result.normalized_odds.append(
                        NovibetNormalizedOdd(
                            bookmaker="novibet",
                            sport=sport,
                            league=event.get("league"),
                            event_name=event_name,
                            start_time=event.get("start_time"),
                            market_type=market_type,
                            selection=selection,
                            odds=odds,
                            source_url=source_url,
                            scraped_at=scraped_at,
                        )
                    )

        return result

    def normalize_market_type(self, value: str) -> str:
        normalized = " ".join((value or "").strip().lower().split())
        if not normalized:
            return ""
        if normalized in {"resultado final", "resultado", "vencedor", "1x2", "money line", "moneyline"}:
            return "Match Odds"
        if "mais/menos" in normalized or "over/under" in normalized or "total de gols" in normalized:
            return "Over/Under"
        if "handicap" in normalized:
            return "Handicap"
        return value.strip()

    def _float_or_none(self, value: Any) -> float | None:
        if value is None:
            return None
        text = str(value).strip().replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None


class _NovibetFixtureHTMLParser(HTMLParser):
    """Extracts deliberately marked read-only event samples from local fixtures or snapshots."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[dict[str, Any]] = []
        self._current_event: dict[str, Any] | None = None
        self._current_market: dict[str, Any] | None = None
        self._stack: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name.lower(): value for name, value in attrs}

        if "data-novibet-event" in attr or "data-event" in attr:
            event = {
                "sport": attr.get("data-sport"),
                "league": attr.get("data-league"),
                "event_name": attr.get("data-event"),
                "start_time": attr.get("data-start") or attr.get("data-start-time"),
                "markets": [],
            }
            self.events.append(event)
            self._current_event = event
            self._stack.append(("event", tag))
            return

        if self._current_event is not None and ("data-novibet-market" in attr or "data-market" in attr):
            market = {
                "market_type": attr.get("data-market"),
                "outcomes": [],
            }
            self._current_event["markets"].append(market)
            self._current_market = market
            self._stack.append(("market", tag))
            return

        if self._current_market is not None and "data-selection" in attr:
            self._current_market["outcomes"].append(
                {
                    "selection": attr.get("data-selection"),
                    "odds": attr.get("data-odds"),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        context, open_tag = self._stack[-1]
        if open_tag != tag:
            return
        self._stack.pop()
        closed = context
        if closed == "market":
            self._current_market = None
        elif closed == "event":
            self._current_event = None
            self._current_market = None
