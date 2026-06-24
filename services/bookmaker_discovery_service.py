"""Read-only SureBet.com bookmaker discovery research service."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

LOGGER = logging.getLogger(__name__)

AUTH_FAILURE_MESSAGE = "SureBet authenticated session not confirmed; refusing to collect limited public data."
RESTRICTED_BOOKMAKERS = {"betano", "bet365"}
PARSER_SELECTORS = [
    'tbody[data-testid="surebet-record"]',
    "[data-surebet-opportunity]",
    '[class*="surebet" i]',
    "tr",
    "article",
    "section",
    "div",
]
KNOWN_BOOKMAKERS = {
    "apostaganha",
    "bet7k",
    "betano",
    "bet365",
    "betfair",
    "betnacional",
    "betsson",
    "betwarrior",
    "bolsadeaposta",
    "br4bet",
    "esportivabet",
    "estrela bet",
    "f12bet",
    "hiperbet",
    "kto",
    "luck.bet",
    "matchbook",
    "mystake",
    "novibet",
    "pinnacle",
    "rivalo",
    "sportingbet",
    "superbet",
    "vaidebet",
}
KNOWN_SPORTS = {
    "basquete",
    "beisebol",
    "boxe",
    "futebol",
    "futebol americano",
    "hockey",
    "mma",
    "tenis",
    "tênis",
    "volei",
    "vôlei",
}


@dataclass(frozen=True)
class DiscoveryConfig:
    username: str | None
    password: str | None
    base_url: str
    output_dir: Path
    poll_seconds: int
    max_cycles: int
    headless: bool
    min_profit_change: float = 0.05
    odds_change_epsilon: float = 0.01
    require_authenticated: bool = True
    max_limited_cycles: int = 2

    @property
    def db_path(self) -> Path:
        return self.output_dir / "bookmaker_discovery.db"

    @property
    def surebets_url(self) -> str:
        return urljoin(self.base_url.rstrip("/") + "/", "surebets")


@dataclass(frozen=True)
class DiscoveryOpportunity:
    collected_at: str
    profit_percent: float
    sport: str
    event_name: str
    market: str
    bookmaker_1: str
    bookmaker_2: str
    odds: list[float]
    opportunity_url: str | None = None
    opportunity_id: str | None = None
    signature: str | None = None
    created_at: str | None = None
    start_at: str | None = None
    roi: float | None = None
    tournament: str | None = None

    @property
    def bookmaker_pair(self) -> str:
        return " x ".join(sorted([self.bookmaker_1, self.bookmaker_2], key=str.lower))

    def contains_restricted_bookmaker(self) -> bool:
        return any(_normalize_bookmaker_for_ranking(name) in RESTRICTED_BOOKMAKERS for name in (self.bookmaker_1, self.bookmaker_2))

    def dedupe_key(self) -> str:
        normalized_parts = [
            _normalize_name(self.event_name),
            _normalize_name(self.market),
            _normalize_name(self.bookmaker_1),
            _normalize_name(self.bookmaker_2),
            ",".join(f"{odd:.2f}" for odd in self.odds),
            f"{self.profit_percent:.2f}",
        ]
        payload = "|".join(normalized_parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def stable_key_without_prices(self) -> str:
        payload = "|".join(
            [
                _normalize_name(self.event_name),
                _normalize_name(self.market),
                " x ".join(sorted([_normalize_name(self.bookmaker_1), _normalize_name(self.bookmaker_2)])),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BookmakerDiscoveryParser:
    """Parses controlled SureBet.com DOM snapshots into discovery opportunities."""

    def __init__(self) -> None:
        self.last_restricted_count = 0
        self.last_fallback_used = False
        self.last_dom_record_count = 0
        self.last_dom_valid_count = 0
        self.last_dom_rejected_count = 0
        self.last_rejection_counts = self._empty_rejection_counts()

    def parse_html(self, html: str, source_url: str, collected_at: str) -> list[DiscoveryOpportunity]:
        self._reset_dom_stats()
        dom_parser = _SurebetRecordHTMLParser(source_url, collected_at)
        dom_parser.feed(html or "")
        opportunities = self._build_dom_opportunities(dom_parser.records)
        if opportunities or dom_parser.records:
            return opportunities

        parser = _SurebetFixtureParser(source_url, collected_at)
        parser.feed(html or "")
        return self._filter_restricted(parser.opportunities)

    def parse_visible_text(
        self,
        visible_text: str,
        source_url: str,
        collected_at: str,
    ) -> list[DiscoveryOpportunity]:
        self.last_fallback_used = True
        lines = [_clean_space(line) for line in (visible_text or "").splitlines() if _clean_space(line)]
        opportunities: list[DiscoveryOpportunity] = []
        profit_indexes = [index for index, line in enumerate(lines) if _parse_percent_line(line) is not None]
        for position, start in enumerate(profit_indexes):
            end = profit_indexes[position + 1] if position + 1 < len(profit_indexes) else min(len(lines), start + 40)
            opportunity = self._parse_visible_lines_block(lines[start:end], source_url, collected_at)
            if opportunity is not None:
                opportunities.append(opportunity)
        return self._filter_restricted(opportunities)

    def parse_extracted_blocks(
        self,
        blocks: list[dict[str, Any]],
        source_url: str,
        collected_at: str,
    ) -> list[DiscoveryOpportunity]:
        self.last_fallback_used = False
        self.last_restricted_count = 0
        self._reset_dom_stats()
        opportunities: list[DiscoveryOpportunity] = []
        for block in blocks:
            html = str(block.get("html") or "")
            dom_parser = _SurebetRecordHTMLParser(source_url, collected_at)
            dom_parser.feed(html or "")
            parsed = self._build_dom_opportunities(dom_parser.records, accumulate=True)
            if not parsed and not dom_parser.records:
                parser = _SurebetFixtureParser(source_url, collected_at)
                parser.feed(html or "")
                parsed = parser.opportunities
            if parsed:
                valid = [item for item in parsed if not item.contains_restricted_bookmaker()]
                self.last_restricted_count += len(parsed) - len(valid)
                opportunities.extend(valid)
                continue

            opportunity = self._parse_visible_text_block(block, source_url, collected_at)
            if opportunity and not opportunity.contains_restricted_bookmaker():
                opportunities.append(opportunity)
            elif opportunity and opportunity.contains_restricted_bookmaker():
                self.last_restricted_count += 1
        return opportunities

    def _parse_visible_text_block(
        self,
        block: dict[str, Any],
        source_url: str,
        collected_at: str,
    ) -> DiscoveryOpportunity | None:
        text = _clean_space(str(block.get("text") or ""))
        if not text:
            return None

        profit_match = re.search(r"(\d+(?:[,.]\d+)?)\s*%", text)
        if not profit_match:
            return None
        profit = _float_or_none(profit_match.group(1))
        if profit is None:
            return None

        # This fallback is deliberately conservative. Unknown layouts remain unparsed
        # instead of guessing unsafe or misleading bookmaker pairs.
        names = _extract_known_name_like_lines(text)
        odds = _extract_decimal_odds(text)
        if len(names) < 5 or len(odds) < 2:
            return None

        bookmaker_1 = names[-2]
        bookmaker_2 = names[-1]
        event_name = names[1] if len(names) > 1 else ""
        market = names[2] if len(names) > 2 else ""
        sport = names[0]

        if not event_name or not market or not bookmaker_1 or not bookmaker_2:
            return None

        return DiscoveryOpportunity(
            collected_at=collected_at,
            profit_percent=profit,
            sport=sport,
            event_name=event_name,
            market=market,
            bookmaker_1=bookmaker_1,
            bookmaker_2=bookmaker_2,
            odds=odds[:2],
            opportunity_url=_absolute_url(source_url, block.get("href")),
            opportunity_id=_extract_opportunity_id(str(block.get("href") or "")),
        )

    def _build_dom_opportunities(
        self,
        records: list[dict[str, Any]],
        *,
        accumulate: bool = False,
    ) -> list[DiscoveryOpportunity]:
        if not accumulate:
            self._reset_dom_stats()
        self.last_dom_record_count += len(records)
        opportunities: list[DiscoveryOpportunity] = []
        for record in records:
            opportunity, reason = self._build_dom_opportunity(record)
            if opportunity is None:
                self.last_dom_rejected_count += 1
                self.last_rejection_counts[reason] = self.last_rejection_counts.get(reason, 0) + 1
                if reason == "restricted_bookmaker":
                    self.last_restricted_count += 1
                continue
            opportunities.append(opportunity)
        self.last_dom_valid_count += len(opportunities)
        return opportunities

    def _build_dom_opportunity(self, record: dict[str, Any]) -> tuple[DiscoveryOpportunity | None, str]:
        profit = _float_or_none(record.get("profit_percent") or record.get("profit_text"))
        if profit is None:
            return None, "missing_profit"

        raw_legs = record.get("legs") or []
        valid_legs: list[dict[str, Any]] = []
        for leg in raw_legs:
            if self._leg_is_masked(leg):
                return None, "masked_xxx"
            bookmaker = _clean_bookmaker_name(str(leg.get("bookmaker") or ""), str(leg.get("sport") or ""))
            if not bookmaker:
                return None, "missing_bookmaker"
            odd = _float_or_none(leg.get("odd"))
            if odd is None or odd <= 1.0:
                return None, "missing_odd"
            valid_legs.append({**leg, "bookmaker": bookmaker, "odd": odd})

        if len(valid_legs) < 2:
            return None, "incomplete_legs"
        if len({leg["bookmaker"] for leg in valid_legs}) < 2:
            return None, "missing_bookmaker"
        if any(_normalize_bookmaker_for_ranking(leg["bookmaker"]) in RESTRICTED_BOOKMAKERS for leg in valid_legs):
            return None, "restricted_bookmaker"

        first_leg = valid_legs[0]
        tournament = str(first_leg.get("tournament") or "").strip()
        event_name = _remove_nested_text(str(first_leg.get("event") or "").strip(), tournament)
        market_parts = [str(leg.get("market") or "").strip() for leg in valid_legs[:2] if str(leg.get("market") or "").strip()]
        if not event_name or not market_parts:
            return None, "incomplete_legs"

        return (
            DiscoveryOpportunity(
                collected_at=str(record.get("collected_at") or ""),
                profit_percent=profit,
                sport=str(first_leg.get("sport") or "unknown").strip() or "unknown",
                event_name=event_name,
                market=" / ".join(market_parts),
                bookmaker_1=valid_legs[0]["bookmaker"],
                bookmaker_2=valid_legs[1]["bookmaker"],
                odds=[float(valid_legs[0]["odd"]), float(valid_legs[1]["odd"])],
                opportunity_url=None,
                opportunity_id=str(record.get("opportunity_id") or "") or None,
                signature=record.get("signature"),
                created_at=record.get("created_at"),
                start_at=record.get("start_at"),
                roi=_float_or_none(record.get("roi")),
                tournament=tournament or None,
            ),
            "",
        )

    def _leg_is_masked(self, leg: dict[str, Any]) -> bool:
        fields = [leg.get("bookmaker"), leg.get("market"), leg.get("odd"), leg.get("event")]
        return any(str(value or "").strip().upper() == "XXX" for value in fields)

    def _parse_visible_lines_block(
        self,
        lines: list[str],
        source_url: str,
        collected_at: str,
    ) -> DiscoveryOpportunity | None:
        if not lines:
            return None
        profit = _parse_percent_line(lines[0])
        if profit is None:
            return None

        bookmaker_positions = [
            (index, _canonical_bookmaker(line))
            for index, line in enumerate(lines)
            if _canonical_bookmaker(line)
        ]
        bookmaker_positions = [(index, name) for index, name in bookmaker_positions if name]
        if len(bookmaker_positions) < 2:
            return None

        odds_positions = [
            (index, _float_or_none(line))
            for index, line in enumerate(lines)
            if _is_plain_decimal_odd(line)
        ]
        odds_positions = [(index, odd) for index, odd in odds_positions if odd is not None and odd > 1.0]
        if len(odds_positions) < 2:
            return None

        event_name = self._find_event_line(lines)
        if not event_name:
            return None

        sport = self._find_sport(lines) or "unknown"
        market_parts = self._find_market_parts(lines, [index for index, _ in odds_positions[:2]])
        market = " / ".join(market_parts) if market_parts else "unknown"

        return DiscoveryOpportunity(
            collected_at=collected_at,
            profit_percent=profit,
            sport=sport,
            event_name=event_name,
            market=market,
            bookmaker_1=bookmaker_positions[0][1],
            bookmaker_2=bookmaker_positions[1][1],
            odds=[float(odds_positions[0][1]), float(odds_positions[1][1])],
            opportunity_url=source_url,
            opportunity_id=None,
        )

    def _find_sport(self, lines: list[str]) -> str | None:
        for line in lines:
            if _normalize_name(line) in {_normalize_name(sport) for sport in KNOWN_SPORTS}:
                return line
        return None

    def _find_event_line(self, lines: list[str]) -> str | None:
        for line in lines:
            normalized = _normalize_name(line)
            if _canonical_bookmaker(line) or normalized in {_normalize_name(sport) for sport in KNOWN_SPORTS}:
                continue
            if re.search(r"\b\d{1,2}/\d{1,2}\b", line) and re.search(r"\s[-–x]\s", line):
                return line
            if re.search(r"\s[-–]\s", line) and not _is_plain_decimal_odd(line) and "%" not in line:
                return line
        return None

    def _find_market_parts(self, lines: list[str], odds_indexes: list[int]) -> list[str]:
        parts: list[str] = []
        for odd_index in odds_indexes:
            for candidate_index in range(odd_index - 1, -1, -1):
                candidate = lines[candidate_index]
                if self._line_is_metadata(candidate):
                    continue
                parts.append(candidate)
                break
        return parts

    def _line_is_metadata(self, line: str) -> bool:
        normalized = _normalize_name(line)
        return (
            _parse_percent_line(line) is not None
            or _is_plain_decimal_odd(line)
            or _canonical_bookmaker(line) is not None
            or normalized in {_normalize_name(sport) for sport in KNOWN_SPORTS}
            or re.fullmatch(r"\d+\s*(h|min|m|s)", normalized or "")
        )

    def _filter_restricted(self, opportunities: list[DiscoveryOpportunity]) -> list[DiscoveryOpportunity]:
        self.last_restricted_count = sum(1 for item in opportunities if item.contains_restricted_bookmaker())
        return [item for item in opportunities if not item.contains_restricted_bookmaker()]

    def _reset_dom_stats(self) -> None:
        self.last_dom_record_count = 0
        self.last_dom_valid_count = 0
        self.last_dom_rejected_count = 0
        self.last_rejection_counts = self._empty_rejection_counts()

    def _empty_rejection_counts(self) -> dict[str, int]:
        return {
            "masked_xxx": 0,
            "missing_bookmaker": 0,
            "missing_odd": 0,
            "restricted_bookmaker": 0,
            "incomplete_legs": 0,
            "missing_profit": 0,
        }


class BookmakerDiscoveryRepository:
    """SQLite persistence for discovery observations and relevant changes."""

    def __init__(
        self,
        db_path: Path,
        min_profit_change: float = 0.05,
        odds_change_epsilon: float = 0.01,
    ) -> None:
        self.db_path = db_path
        self.min_profit_change = min_profit_change
        self.odds_change_epsilon = odds_change_epsilon
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def save_opportunities(self, opportunities: list[DiscoveryOpportunity]) -> dict[str, int]:
        stats = {"seen": len(opportunities), "inserted": 0, "updated": 0, "changed": 0, "skipped": 0}
        connection = sqlite3.connect(self.db_path)
        try:
            connection.row_factory = sqlite3.Row
            for opportunity in opportunities:
                if opportunity.contains_restricted_bookmaker():
                    stats["skipped"] += 1
                    continue
                stable_key = opportunity.stable_key_without_prices()
                existing = connection.execute(
                    "select * from observations where stable_key = ?",
                    (stable_key,),
                ).fetchone()
                if existing is None:
                    self._insert_observation(connection, opportunity)
                    self._insert_event(connection, opportunity, "inserted")
                    stats["inserted"] += 1
                    continue

                if self._has_relevant_change(existing, opportunity):
                    self._update_observation(connection, opportunity, existing["seen_count"] + 1)
                    self._insert_event(connection, opportunity, "changed")
                    stats["changed"] += 1
                else:
                    connection.execute(
                        """
                        update observations
                           set last_seen_at = ?,
                               seen_count = seen_count + 1
                         where stable_key = ?
                        """,
                        (opportunity.collected_at, stable_key),
                    )
                    stats["updated"] += 1
            connection.commit()
        finally:
            connection.close()
        return stats

    def fetch_observations(self) -> list[dict[str, Any]]:
        if not self.db_path.exists():
            return []
        connection = sqlite3.connect(self.db_path)
        try:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "select * from observations order by profit_percent desc, seen_count desc"
            ).fetchall()
        finally:
            connection.close()
        return [self._row_to_dict(row) for row in rows]

    def _ensure_schema(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                """
                create table if not exists observations (
                    id integer primary key autoincrement,
                    stable_key text not null unique,
                    dedupe_key text not null,
                    first_seen_at text not null,
                    last_seen_at text not null,
                    profit_percent real not null,
                    sport text not null,
                    event_name text not null,
                    market text not null,
                    bookmaker_1 text not null,
                    bookmaker_2 text not null,
                    bookmaker_pair text not null,
                    odds_json text not null,
                    opportunity_url text,
                    opportunity_id text,
                    seen_count integer not null default 1
                )
                """
            )
            connection.execute(
                """
                create table if not exists observation_events (
                    id integer primary key autoincrement,
                    observed_at text not null,
                    stable_key text not null,
                    dedupe_key text not null,
                    change_type text not null,
                    profit_percent real not null,
                    odds_json text not null,
                    payload_json text not null
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _insert_observation(self, connection: sqlite3.Connection, opportunity: DiscoveryOpportunity) -> None:
        connection.execute(
            """
            insert into observations (
                stable_key, dedupe_key, first_seen_at, last_seen_at, profit_percent,
                sport, event_name, market, bookmaker_1, bookmaker_2, bookmaker_pair,
                odds_json, opportunity_url, opportunity_id, seen_count
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            self._observation_values(opportunity),
        )

    def _update_observation(
        self,
        connection: sqlite3.Connection,
        opportunity: DiscoveryOpportunity,
        seen_count: int,
    ) -> None:
        connection.execute(
            """
            update observations
               set dedupe_key = ?,
                   last_seen_at = ?,
                   profit_percent = ?,
                   sport = ?,
                   event_name = ?,
                   market = ?,
                   bookmaker_1 = ?,
                   bookmaker_2 = ?,
                   bookmaker_pair = ?,
                   odds_json = ?,
                   opportunity_url = ?,
                   opportunity_id = ?,
                   seen_count = ?
             where stable_key = ?
            """,
            (
                opportunity.dedupe_key(),
                opportunity.collected_at,
                opportunity.profit_percent,
                opportunity.sport,
                opportunity.event_name,
                opportunity.market,
                opportunity.bookmaker_1,
                opportunity.bookmaker_2,
                opportunity.bookmaker_pair,
                json.dumps(opportunity.odds),
                opportunity.opportunity_url,
                opportunity.opportunity_id,
                seen_count,
                opportunity.stable_key_without_prices(),
            ),
        )

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        opportunity: DiscoveryOpportunity,
        change_type: str,
    ) -> None:
        connection.execute(
            """
            insert into observation_events (
                observed_at, stable_key, dedupe_key, change_type, profit_percent, odds_json, payload_json
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity.collected_at,
                opportunity.stable_key_without_prices(),
                opportunity.dedupe_key(),
                change_type,
                opportunity.profit_percent,
                json.dumps(opportunity.odds),
                json.dumps(asdict(opportunity), ensure_ascii=False),
            ),
        )

    def _observation_values(self, opportunity: DiscoveryOpportunity) -> tuple[Any, ...]:
        return (
            opportunity.stable_key_without_prices(),
            opportunity.dedupe_key(),
            opportunity.collected_at,
            opportunity.collected_at,
            opportunity.profit_percent,
            opportunity.sport,
            opportunity.event_name,
            opportunity.market,
            opportunity.bookmaker_1,
            opportunity.bookmaker_2,
            opportunity.bookmaker_pair,
            json.dumps(opportunity.odds),
            opportunity.opportunity_url,
            opportunity.opportunity_id,
        )

    def _has_relevant_change(self, row: sqlite3.Row, opportunity: DiscoveryOpportunity) -> bool:
        if abs(float(row["profit_percent"]) - opportunity.profit_percent) >= self.min_profit_change:
            return True
        old_odds = json.loads(row["odds_json"] or "[]")
        if len(old_odds) != len(opportunity.odds):
            return True
        return any(abs(float(old) - float(new)) >= self.odds_change_epsilon for old, new in zip(old_odds, opportunity.odds))

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["odds"] = json.loads(data.pop("odds_json") or "[]")
        return data


class BookmakerDiscoveryReporter:
    """Builds CSV and JSON reports from the discovery SQLite database."""

    def __init__(self, output_dir: Path, db_path: Path) -> None:
        self.output_dir = output_dir
        self.db_path = db_path
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self) -> dict[str, Any]:
        observations = BookmakerDiscoveryRepository(self.db_path).fetch_observations() if self.db_path.exists() else []
        bookmaker_rows = self._bookmaker_rows(observations)
        frequency = sorted(bookmaker_rows.values(), key=lambda row: (-row["appearances"], row["bookmaker"].lower()))
        avg_profit = sorted(bookmaker_rows.values(), key=lambda row: (-row["avg_profit_percent"], row["bookmaker"].lower()))
        max_profit = sorted(bookmaker_rows.values(), key=lambda row: (-row["max_profit_percent"], row["bookmaker"].lower()))
        pairs = self._pair_rows(observations)
        top_opportunities = sorted(observations, key=lambda row: (-row["profit_percent"], -row["seen_count"]))[:20]
        weighted = self._weighted_rows(bookmaker_rows)

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_observations": len(observations),
                "total_bookmakers": len(bookmaker_rows),
                "total_pairs": len(pairs),
                "restricted_bookmakers_excluded": sorted(RESTRICTED_BOOKMAKERS),
            },
            "ranking_frequency": frequency,
            "ranking_avg_profit": avg_profit,
            "ranking_max_profit": max_profit,
            "ranking_pairs": pairs,
            "top_opportunities": top_opportunities,
            "weighted_ranking": weighted,
            "recommended_top_5": weighted[:5],
        }
        self._write_report_files(report)
        return report

    def _bookmaker_rows(self, observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for observation in observations:
            for bookmaker in (observation["bookmaker_1"], observation["bookmaker_2"]):
                bookmaker_key = _normalize_bookmaker_for_ranking(bookmaker)
                if bookmaker_key in RESTRICTED_BOOKMAKERS:
                    continue
                row = rows.setdefault(
                    bookmaker_key,
                    {
                        "bookmaker": bookmaker,
                        "bookmaker_normalized": bookmaker_key,
                        "appearances": 0,
                        "avg_profit_percent": 0.0,
                        "max_profit_percent": 0.0,
                        "_profit_sum": 0.0,
                        "_observation_count": 0,
                    },
                )
                row["appearances"] += int(observation.get("seen_count") or 1)
                row["_profit_sum"] += float(observation["profit_percent"])
                row["_observation_count"] += 1
                row["max_profit_percent"] = max(row["max_profit_percent"], float(observation["profit_percent"]))

        for row in rows.values():
            count = max(1, int(row["_observation_count"]))
            row["avg_profit_percent"] = round(row["_profit_sum"] / count, 4)
            row.pop("_profit_sum", None)
            row.pop("_observation_count", None)
        return rows

    def _pair_rows(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pairs: dict[str, dict[str, Any]] = {}
        for observation in observations:
            pair = observation["bookmaker_pair"]
            row = pairs.setdefault(pair, {"bookmaker_pair": pair, "appearances": 0, "max_profit_percent": 0.0})
            row["appearances"] += int(observation.get("seen_count") or 1)
            row["max_profit_percent"] = max(row["max_profit_percent"], float(observation["profit_percent"]))
        return sorted(pairs.values(), key=lambda row: (-row["appearances"], -row["max_profit_percent"], row["bookmaker_pair"].lower()))

    def _weighted_rows(self, bookmaker_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        if not bookmaker_rows:
            return []
        max_frequency = max(float(row["appearances"]) for row in bookmaker_rows.values()) or 1.0
        max_avg = max(float(row["avg_profit_percent"]) for row in bookmaker_rows.values()) or 1.0
        max_profit = max(float(row["max_profit_percent"]) for row in bookmaker_rows.values()) or 1.0
        weighted = []
        for row in bookmaker_rows.values():
            frequency_norm = float(row["appearances"]) / max_frequency
            avg_norm = float(row["avg_profit_percent"]) / max_avg
            max_norm = float(row["max_profit_percent"]) / max_profit
            weighted.append(
                {
                    **row,
                    "frequency_norm": round(frequency_norm, 4),
                    "avg_profit_norm": round(avg_norm, 4),
                    "max_profit_norm": round(max_norm, 4),
                    "score": round(0.5 * frequency_norm + 0.3 * avg_norm + 0.2 * max_norm, 4),
                }
            )
        return sorted(weighted, key=lambda row: (-row["score"], -row["appearances"], row["bookmaker"].lower()))

    def _write_report_files(self, report: dict[str, Any]) -> None:
        (self.output_dir / "bookmaker_discovery_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_csv("ranking_frequency.csv", report["ranking_frequency"])
        self._write_csv("ranking_avg_profit.csv", report["ranking_avg_profit"])
        self._write_csv("ranking_max_profit.csv", report["ranking_max_profit"])
        self._write_csv("ranking_pairs.csv", report["ranking_pairs"])
        self._write_csv("top_opportunities.csv", report["top_opportunities"])
        self._write_csv("weighted_ranking.csv", report["weighted_ranking"])

    def _write_csv(self, filename: str, rows: list[dict[str, Any]]) -> None:
        path = self.output_dir / filename
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


class BookmakerDiscoveryService:
    """Coordinates the long-running read-only SureBet.com discovery scan."""

    def __init__(self, config: DiscoveryConfig, parser: BookmakerDiscoveryParser | None = None) -> None:
        self.config = config
        self.parser = parser or BookmakerDiscoveryParser()
        self.empty_cycles = 0
        self.limited_cycles = 0
        self.repository = BookmakerDiscoveryRepository(
            config.db_path,
            min_profit_change=config.min_profit_change,
            odds_change_epsilon=config.odds_change_epsilon,
        )

    def generate_report_only(self) -> dict[str, Any]:
        return BookmakerDiscoveryReporter(self.config.output_dir, self.config.db_path).generate()

    def run(self) -> dict[str, Any]:
        if not self.config.username or not self.config.password:
            raise ValueError("SUREBET_USERNAME and SUREBET_PASSWORD must be configured in .env")

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError(f"Playwright is not available: {exc}") from exc

        cycle = 0
        last_report: dict[str, Any] = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.config.headless)
            context = browser.new_context(locale="pt-BR", viewport={"width": 1365, "height": 900})
            page = context.new_page()
            page.on("popup", lambda popup: popup.close())
            try:
                self._login(page)
                while True:
                    cycle += 1
                    collected_at = datetime.now(timezone.utc).isoformat()
                    try:
                        blocks = self._extract_visible_blocks(page)
                        opportunities = self.parser.parse_extracted_blocks(blocks, page.url, collected_at)
                        if not opportunities:
                            visible_text = self._visible_text(page)
                            opportunities = self.parser.parse_visible_text(visible_text, page.url, collected_at)
                            if opportunities:
                                LOGGER.warning("SureBet discovery used visible-text fallback parser.")
                        self._enforce_authenticated_collection(page, opportunities)
                        stats = self.repository.save_opportunities(opportunities)
                        max_profit = max((row.profit_percent for row in opportunities), default=None)
                        if stats["inserted"] or stats["changed"]:
                            last_report = self.generate_report_only()
                        if opportunities:
                            self.empty_cycles = 0
                        else:
                            self._record_empty_cycle_and_maybe_snapshot(page, cycle)
                        LOGGER.info(
                            "Bookmaker discovery cycle=%s dom_records=%s parsed=%s inserted=%s changed=%s updated=%s masked=%s restricted=%s max_profit=%s",
                            cycle,
                            self.parser.last_dom_record_count or len(blocks),
                            len(opportunities),
                            stats["inserted"],
                            stats["changed"],
                            stats["updated"],
                            self.parser.last_rejection_counts.get("masked_xxx", 0),
                            self.parser.last_restricted_count,
                            max_profit,
                        )
                        print(
                            f"[Bookmaker Discovery ciclo {cycle}] dom_records={self.parser.last_dom_record_count or len(blocks)} "
                            f"validas={len(opportunities)} "
                            f"rejeitadas_xxx={self.parser.last_rejection_counts.get('masked_xxx', 0)} "
                            f"rejeitadas_restritas={self.parser.last_restricted_count} "
                            f"gravadas={stats['inserted'] + stats['changed']} "
                            f"duplicadas={stats['updated']} "
                            f"maior_lucro={max_profit if max_profit is not None else 'N/A'}"
                        )
                    except PlaywrightTimeoutError:
                        LOGGER.warning("SureBet DOM timed out; reloading surebets page.")
                        page.goto(self.config.surebets_url, wait_until="domcontentloaded", timeout=30000)
                    except RuntimeError as exc:
                        if AUTH_FAILURE_MESSAGE in str(exc):
                            LOGGER.error(str(exc))
                            raise
                        raise
                    except Exception:
                        LOGGER.exception("SureBet discovery cycle failed; attempting lightweight page recovery.")
                        page.goto(self.config.surebets_url, wait_until="domcontentloaded", timeout=30000)

                    if self.config.max_cycles > 0 and cycle >= self.config.max_cycles:
                        break
                    time.sleep(max(1, self.config.poll_seconds))
            except KeyboardInterrupt:
                LOGGER.info("Bookmaker discovery interrupted by user.")
            finally:
                last_report = self.generate_report_only()
                context.close()
                browser.close()
        return last_report

    def run_debug(self) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError(f"Playwright is not available: {exc}") from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self._debug_headless())
            context = browser.new_context(locale="pt-BR", viewport={"width": 1365, "height": 900})
            page = context.new_page()
            page.on("popup", lambda popup: popup.close())
            try:
                self._login_or_wait_manual(page)
                self._wait_for_visible_opportunities(page)
                return self.save_debug_snapshot(page, self.config.output_dir / "debug")
            finally:
                context.close()
                browser.close()

    def save_debug_snapshot(self, page: Any, debug_dir: Path) -> dict[str, Any]:
        debug_dir.mkdir(parents=True, exist_ok=True)
        html = page.content()
        visible_text = self._visible_text(page)
        (debug_dir / "page.html").write_text(html, encoding="utf-8")
        (debug_dir / "visible_text.txt").write_text(visible_text, encoding="utf-8")
        try:
            page.screenshot(path=str(debug_dir / "page.png"), full_page=True)
        except Exception as exc:
            LOGGER.warning("Failed to save full-page screenshot: %s", exc)
            (debug_dir / "page.png").write_bytes(b"")

        dom_counts = self._dom_diagnostic_counts(page)
        collected_at = datetime.now(timezone.utc).isoformat()
        blocks = dom_counts.get("candidate_blocks", [])
        parsed_blocks = self.parser.parse_extracted_blocks(blocks, page.url, collected_at)
        parsed_fallback = self.parser.parse_visible_text(visible_text, page.url, collected_at)
        profit_values = [row.profit_percent for row in (parsed_blocks or parsed_fallback)]
        auth_status = self.get_page_auth_status(page, profit_values, visible_text=visible_text)
        summary = {
            "url": page.url,
            "current_url": page.url,
            "title": page.title(),
            "page_title": page.title(),
            "timestamp": collected_at,
            "looks_authenticated": self._looks_authenticated(page),
            **auth_status,
            "contains_encontrado": "encontrado" in visible_text.lower(),
            "contains_apostas_seguras": "apostas seguras" in visible_text.lower(),
            "div_count": dom_counts.get("div_count", 0),
            "tr_count": dom_counts.get("tr_count", 0),
            "a_count": dom_counts.get("a_count", 0),
            "surebet_record_count": dom_counts.get("surebet_record_count", 0),
            "surebet_leg_count": dom_counts.get("surebet_leg_count", 0),
            "elements_containing_percent_count": dom_counts.get("elements_containing_percent_count", 0),
            "elements_containing_known_bookmakers_count": dom_counts.get("elements_containing_known_bookmakers_count", 0),
            "parser_selectors_tested": PARSER_SELECTORS,
            "parser_current_extracted_count": len(parsed_blocks) or len(parsed_fallback),
            "parser_dom_extracted_count": len(parsed_blocks),
            "parser_visible_text_extracted_count": len(parsed_fallback),
            "dom_parser_valid_count": self.parser.last_dom_valid_count,
            "dom_parser_rejected_count": self.parser.last_dom_rejected_count,
            "dom_parser_rejection_reasons": self.parser.last_rejection_counts,
            "first_20_candidate_blocks": blocks[:20],
        }
        (debug_dir / "dom_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary

    def get_page_auth_status(
        self,
        page: Any,
        profit_values: list[float],
        *,
        visible_text: str | None = None,
    ) -> dict[str, Any]:
        text = visible_text if visible_text is not None else self._visible_text(page)
        lower = text.lower()
        login_form_detected = self._login_form_detected(page)
        logout_account_menu_detected = self._logout_account_menu_detected(page, lower)
        max_profit_seen = max(profit_values, default=None)
        all_profits_are_1_percent = bool(profit_values) and all(abs(float(value) - 1.0) < 1e-9 for value in profit_values)
        surebet_count_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:apostas seguras|surebets|encontrado)", lower)
        return {
            "current_url": getattr(page, "url", None),
            "page_title": self._safe_title(page),
            "login_form_detected": login_form_detected,
            "logout_account_menu_detected": logout_account_menu_detected,
            "contains_entrar_or_login": "entrar" in lower or "login" in lower or "sign in" in lower,
            "contains_encontrado": "encontrado" in lower,
            "contains_apostas_seguras": "apostas seguras" in lower,
            "surebet_count_text": surebet_count_match.group(0) if surebet_count_match else None,
            "max_profit_seen": max_profit_seen,
            "all_profits_are_1_percent": all_profits_are_1_percent,
        }

    def _enforce_authenticated_collection(self, page: Any, opportunities: list[DiscoveryOpportunity]) -> None:
        if not self.config.require_authenticated:
            return
        profit_values = [row.profit_percent for row in opportunities]
        auth_status = self.get_page_auth_status(page, profit_values)
        limited_now = (
            bool(auth_status["login_form_detected"])
            or bool(auth_status["all_profits_are_1_percent"])
            or (
                auth_status["max_profit_seen"] is not None
                and float(auth_status["max_profit_seen"]) <= 1.0
            )
        )
        if limited_now:
            self.limited_cycles += 1
            LOGGER.warning(
                "SureBet authenticated session is not confirmed: login_form=%s all_profits_1=%s max_profit=%s limited_cycles=%s/%s url=%s title=%s",
                auth_status["login_form_detected"],
                auth_status["all_profits_are_1_percent"],
                auth_status["max_profit_seen"],
                self.limited_cycles,
                self.config.max_limited_cycles,
                auth_status["current_url"],
                auth_status["page_title"],
            )
        else:
            self.limited_cycles = 0

        if bool(auth_status["login_form_detected"]) or bool(auth_status["all_profits_are_1_percent"]) or self.limited_cycles >= self.config.max_limited_cycles:
            self.save_debug_snapshot(page, self.config.output_dir / "debug" / "auth_failure_snapshot")
            raise RuntimeError(AUTH_FAILURE_MESSAGE)

    def _debug_headless(self) -> bool:
        override = os.getenv("SUREBET_DISCOVERY_DEBUG_HEADLESS")
        if override is None or override == "":
            return self.config.headless
        return override.strip().lower() in {"1", "true", "yes", "y", "on"}

    def _record_empty_cycle_and_maybe_snapshot(self, page: Any, cycle: int) -> bool:
        self.empty_cycles += 1
        if self.empty_cycles == 3:
            self.save_debug_snapshot(page, self.config.output_dir / "debug" / "auto_empty_snapshot")
            LOGGER.info("Saved automatic empty-cycle debug snapshot at cycle %s", cycle)
            return True
        return False

    def _login(self, page: Any) -> None:
        page.goto(self.config.surebets_url, wait_until="domcontentloaded", timeout=30000)
        if self._looks_authenticated(page):
            return

        page.goto(urljoin(self.config.base_url.rstrip("/") + "/", "users/sign_in"), wait_until="domcontentloaded", timeout=30000)
        username_selector = "input[type='email'], input[name='email' i], input[name='user' i], input[name='username' i], input[name*='email' i], input[name*='login' i], input[name*='user' i]"
        password_selector = "input[type='password']"
        page.locator(username_selector).first.fill(self.config.username)
        page.locator(password_selector).first.fill(self.config.password)
        page.locator("button[type='submit'], input[type='submit'], button:has-text('Entrar'), button:has-text('Login'), button:has-text('Sign in')").first.click()
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.goto(self.config.surebets_url, wait_until="domcontentloaded", timeout=30000)
        if not self._looks_authenticated(page):
            raise RuntimeError("SureBet login did not reach an authenticated surebets page.")

    def _login_or_wait_manual(self, page: Any) -> None:
        page.goto(self.config.surebets_url, wait_until="domcontentloaded", timeout=30000)
        if self._looks_authenticated(page):
            return
        if self.config.username and self.config.password:
            try:
                self._login(page)
                return
            except Exception as exc:
                LOGGER.warning("Automatic SureBet login failed in debug mode: %s", exc)
        print("Faça login manualmente na janela aberta. O diagnóstico continuará quando a página autenticada carregar.")
        deadline = time.time() + 300
        while time.time() < deadline:
            if self._looks_authenticated(page):
                return
            time.sleep(2)
        raise RuntimeError("SureBet debug mode timed out waiting for authenticated page.")

    def _looks_authenticated(self, page: Any) -> bool:
        try:
            text = page.locator("body").inner_text(timeout=5000).lower()
        except Exception:
            return False
        return "sign in" not in text and "entrar" not in text and ("surebet" in text or "apostas seguras" in text)

    def _login_form_detected(self, page: Any) -> bool:
        try:
            return bool(
                page.locator(
                    "input[type='password'], input[name='password' i], form[action*='sign_in'], form[action*='login']"
                ).count()
            )
        except Exception:
            return False

    def _logout_account_menu_detected(self, page: Any, visible_text_lower: str) -> bool:
        if any(token in visible_text_lower for token in ("sair", "logout", "minha conta", "perfil", "account")):
            return True
        try:
            return bool(page.locator("a[href*='sign_out'], a[href*='logout'], [data-testid*='account' i], [class*='account' i]").count())
        except Exception:
            return False

    def _safe_title(self, page: Any) -> str | None:
        try:
            return page.title()
        except Exception:
            return None

    def _wait_for_visible_opportunities(self, page: Any) -> None:
        deadline = time.time() + 120
        while time.time() < deadline:
            visible_text = self._visible_text(page)
            if _parse_percent_line(visible_text) is not None or "encontrado" in visible_text.lower():
                return
            time.sleep(2)

    def _visible_text(self, page: Any) -> str:
        try:
            return str(page.evaluate("() => document.body ? document.body.innerText : ''") or "")
        except Exception:
            try:
                return page.locator("body").inner_text(timeout=3000)
            except Exception:
                return ""

    def _extract_visible_blocks(self, page: Any) -> list[dict[str, Any]]:
        return page.evaluate(
            """
            (selectors) => {
              const seen = new Set();
              const blocks = [];
              const primaryRecords = Array.from(document.querySelectorAll('tbody[data-testid="surebet-record"]'));
              for (const element of primaryRecords) {
                const text = (element.innerText || '').trim();
                const hrefElement = element.querySelector('a[href*="surebet"], a[href*="calculator"], a[href]');
                blocks.push({
                  text,
                  html: element.outerHTML || '',
                  href: hrefElement ? hrefElement.href : null,
                  selector: 'tbody[data-testid="surebet-record"]'
                });
              }
              if (blocks.length > 0) return blocks;
              for (const selector of selectors) {
                for (const element of Array.from(document.querySelectorAll(selector))) {
                  if (seen.has(element)) continue;
                  seen.add(element);
                  const text = (element.innerText || '').trim();
                  if (!text || !/%/.test(text)) continue;
                  const hrefElement = element.querySelector('a[href*="surebet"], a[href*="calculator"], a[href]');
                  blocks.push({
                    text,
                    html: element.outerHTML || '',
                    href: hrefElement ? hrefElement.href : null
                  });
                  if (blocks.length >= 300) return blocks;
                }
              }
              return blocks;
            }
            """,
            PARSER_SELECTORS,
        )

    def _dom_diagnostic_counts(self, page: Any) -> dict[str, Any]:
        known_bookmakers = sorted(KNOWN_BOOKMAKERS)
        selectors = PARSER_SELECTORS
        return page.evaluate(
            """
            ({ knownBookmakers, selectors }) => {
              const lowerKnown = knownBookmakers.map((name) => name.toLowerCase());
              const all = Array.from(document.querySelectorAll('*'));
              const textOf = (element) => (element.innerText || element.textContent || '').trim();
              const containsKnown = (text) => {
                const lower = text.toLowerCase();
                return lowerKnown.some((name) => lower.includes(name));
              };
              const seen = new Set();
              const candidateBlocks = [];
              for (const selector of selectors) {
                for (const element of Array.from(document.querySelectorAll(selector))) {
                  if (seen.has(element)) continue;
                  seen.add(element);
                  const text = textOf(element);
                  if (!text || !/%/.test(text)) continue;
                  const decimalMatches = text.match(/(^|\\s)([1-9]\\d?[\\.,]\\d{1,3})(?=\\s|$)/g) || [];
                  const bookmakerHits = lowerKnown.filter((name) => text.toLowerCase().includes(name));
                  if (decimalMatches.length >= 2 || bookmakerHits.length >= 1 || candidateBlocks.length < 20) {
                    const hrefElement = element.querySelector('a[href]');
                    candidateBlocks.push({
                      selector,
                      text: text.slice(0, 2500),
                      html: (element.outerHTML || '').slice(0, 5000),
                      href: hrefElement ? hrefElement.href : null,
                      decimal_odds_count: decimalMatches.length,
                      bookmaker_hits: bookmakerHits.slice(0, 10)
                    });
                  }
                  if (candidateBlocks.length >= 100) break;
                }
                if (candidateBlocks.length >= 100) break;
              }
              return {
                div_count: document.querySelectorAll('div').length,
                tr_count: document.querySelectorAll('tr').length,
                a_count: document.querySelectorAll('a').length,
                surebet_record_count: document.querySelectorAll('tbody[data-testid="surebet-record"]').length,
                surebet_leg_count: document.querySelectorAll('tr[data-testid="surebet-leg"]').length,
                elements_containing_percent_count: all.filter((element) => textOf(element).includes('%')).length,
                elements_containing_known_bookmakers_count: all.filter((element) => containsKnown(textOf(element))).length,
                candidate_blocks: candidateBlocks
              };
            }
            """,
            {"knownBookmakers": known_bookmakers, "selectors": selectors},
        )


class _SurebetFixtureParser(HTMLParser):
    def __init__(self, source_url: str, collected_at: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.collected_at = collected_at
        self.opportunities: list[DiscoveryOpportunity] = []
        self._current: dict[str, Any] | None = None
        self._stack: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name.lower(): value for name, value in attrs}
        if "data-surebet-opportunity" in attr:
            self._current = {
                "profit_percent": _float_or_none(attr.get("data-profit")),
                "sport": attr.get("data-sport") or "",
                "event_name": attr.get("data-event") or "",
                "market": attr.get("data-market") or "",
                "opportunity_url": _absolute_url(self.source_url, attr.get("data-url") or attr.get("href")),
                "opportunity_id": _extract_opportunity_id(attr.get("data-url") or attr.get("href") or ""),
                "bookmakers": [],
                "odds": [],
            }
            self._stack.append(("opportunity", tag))
            return

        if self._current is not None and "data-bookmaker" in attr:
            bookmaker = _clean_space(attr.get("data-bookmaker") or "")
            odd = _float_or_none(attr.get("data-odds"))
            if bookmaker and odd is not None:
                self._current["bookmakers"].append(bookmaker)
                self._current["odds"].append(odd)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        context, open_tag = self._stack[-1]
        if open_tag != tag:
            return
        self._stack.pop()
        if context == "opportunity" and self._current is not None:
            opportunity = self._build_opportunity(self._current)
            if opportunity is not None:
                self.opportunities.append(opportunity)
            self._current = None

    def _build_opportunity(self, raw: dict[str, Any]) -> DiscoveryOpportunity | None:
        bookmakers = raw.get("bookmakers") or []
        odds = raw.get("odds") or []
        if (
            raw.get("profit_percent") is None
            or not raw.get("sport")
            or not raw.get("event_name")
            or not raw.get("market")
            or len(bookmakers) < 2
            or len(odds) < 2
        ):
            return None
        return DiscoveryOpportunity(
            collected_at=self.collected_at,
            profit_percent=float(raw["profit_percent"]),
            sport=str(raw["sport"]),
            event_name=str(raw["event_name"]),
            market=str(raw["market"]),
            bookmaker_1=str(bookmakers[0]),
            bookmaker_2=str(bookmakers[1]),
            odds=[float(odds[0]), float(odds[1])],
            opportunity_url=raw.get("opportunity_url"),
            opportunity_id=raw.get("opportunity_id"),
        )


class _SurebetRecordHTMLParser(HTMLParser):
    """Extracts real SureBet.com surebet records from table bodies."""

    def __init__(self, source_url: str, collected_at: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.collected_at = collected_at
        self.records: list[dict[str, Any]] = []
        self._record: dict[str, Any] | None = None
        self._leg: dict[str, Any] | None = None
        self._field_name: str | None = None
        self._field_tag: str | None = None
        self._field_buffer: list[str] = []
        self._subfield_name: str | None = None
        self._subfield_tag: str | None = None
        self._subfield_buffer: list[str] = []
        self._record_tag: str | None = None
        self._leg_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name.lower(): value or "" for name, value in attrs}
        data_testid = attr.get("data-testid", "")
        classes = set((attr.get("class", "") or "").split())

        if tag == "tbody" and data_testid == "surebet-record":
            self._record = {
                "collected_at": self.collected_at,
                "opportunity_id": attr.get("data-id"),
                "signature": attr.get("data-signature"),
                "profit_percent": attr.get("data-profit"),
                "created_at": attr.get("data-created-at"),
                "start_at": attr.get("data-start-at"),
                "roi": attr.get("data-roi"),
                "profit_text": "",
                "legs": [],
            }
            self._record_tag = tag
            return

        if self._record is not None and tag == "tr" and data_testid == "surebet-leg":
            self._leg = {
                "bookmaker": "",
                "sport": "",
                "event": "",
                "tournament": "",
                "market": "",
                "odd": "",
                "time": "",
            }
            self._leg_tag = tag
            return

        if self._record is not None and tag == "span" and data_testid == "surebet-profit":
            self._subfield_name = "profit_text"
            self._subfield_tag = tag
            self._subfield_buffer = []
            return

        if self._leg is not None and tag == "span" and data_testid == "surebet-leg-sport":
            self._subfield_name = "sport"
            self._subfield_tag = tag
            self._subfield_buffer = []
            return

        if self._leg is not None and tag == "span" and data_testid == "surebet-leg-tournament":
            self._subfield_name = "tournament"
            self._subfield_tag = tag
            self._subfield_buffer = []
            return

        if self._leg is not None and tag == "td":
            field = None
            if "booker" in classes:
                field = "bookmaker"
            elif "time" in classes:
                field = "time"
            elif "event" in classes:
                field = "event"
            elif "coeff" in classes:
                field = "market"
            elif "value" in classes:
                field = "odd"
            if field:
                self._field_name = field
                self._field_tag = tag
                self._field_buffer = []

    def handle_data(self, data: str) -> None:
        if self._subfield_name is not None:
            self._subfield_buffer.append(data)
        if self._field_name is not None:
            self._field_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._subfield_name is not None and self._subfield_tag == tag:
            value = _clean_space(" ".join(self._subfield_buffer))
            if self._subfield_name == "profit_text" and self._record is not None:
                self._record["profit_text"] = value
            elif self._leg is not None:
                self._leg[self._subfield_name] = value
            self._subfield_name = None
            self._subfield_tag = None
            self._subfield_buffer = []
            return

        if self._field_name is not None and self._field_tag == tag:
            value = _clean_space(" ".join(self._field_buffer))
            if self._leg is not None:
                self._leg[self._field_name] = value
            self._field_name = None
            self._field_tag = None
            self._field_buffer = []
            return

        if self._leg is not None and self._leg_tag == tag:
            if self._record is not None:
                self._record["legs"].append(self._leg)
            self._leg = None
            self._leg_tag = None
            return

        if self._record is not None and self._record_tag == tag:
            self.records.append(self._record)
            self._record = None
            self._record_tag = None


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(ascii_text.strip().lower().replace("-", " ").split())


def _normalize_bookmaker_for_ranking(value: str) -> str:
    without_region = re.sub(r"\s*\([A-Z]{2,3}\)\s*$", "", value or "", flags=re.IGNORECASE)
    normalized = _normalize_name(without_region)
    compact_restricted = normalized.replace(" ", "")
    if compact_restricted in RESTRICTED_BOOKMAKERS:
        return compact_restricted
    return normalized


def _clean_bookmaker_name(value: str, sport: str = "") -> str:
    text = _clean_space(value)
    sport_text = _clean_space(sport)
    if sport_text:
        text = _remove_nested_text(text, sport_text)
    return _clean_space(text)


def _remove_nested_text(value: str, nested: str) -> str:
    text = _clean_space(value)
    nested_text = _clean_space(nested)
    if not nested_text:
        return text
    return _clean_space(re.sub(re.escape(nested_text), "", text, flags=re.IGNORECASE))


def _clean_space(value: str) -> str:
    return " ".join((value or "").strip().split())


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def _parse_percent_line(value: str) -> float | None:
    match = re.search(r"(\d+(?:[,.]\d+)?)\s*%", value or "")
    if not match:
        return None
    return _float_or_none(match.group(1))


def _canonical_bookmaker(value: str) -> str | None:
    normalized = _normalize_name(value)
    compact = normalized.replace(" ", "")
    for bookmaker in KNOWN_BOOKMAKERS:
        normalized_bookmaker = _normalize_name(bookmaker)
        if normalized == normalized_bookmaker or compact == normalized_bookmaker.replace(" ", ""):
            return bookmaker.title() if bookmaker.islower() else bookmaker
    return None


def _is_plain_decimal_odd(value: str) -> bool:
    text = (value or "").strip()
    return bool(re.fullmatch(r"[1-9]\d?[,.]\d{1,3}", text))


def _absolute_url(base_url: str, href: Any) -> str | None:
    if not href:
        return None
    return urljoin(base_url, str(href))


def _extract_opportunity_id(value: str) -> str | None:
    match = re.search(r"(\d+)(?:\D*)$", value or "")
    return match.group(1) if match else None


def _extract_decimal_odds(text: str) -> list[float]:
    odds = []
    for match in re.finditer(r"(?<!\d)([1-9]\d?[,.]\d{1,3})(?!\d)", text):
        value = _float_or_none(match.group(1))
        if value is not None and value > 1.0:
            odds.append(value)
    return odds


def _extract_known_name_like_lines(text: str) -> list[str]:
    lines = [_clean_space(line) for line in re.split(r"[\r\n]+", text) if _clean_space(line)]
    ignored = {"calc", "calculator", "aposta", "apostar", "roi"}
    result = []
    for line in lines:
        normalized = _normalize_name(line)
        if "%" in line or re.fullmatch(r"\d+(?:[,.]\d+)?", line):
            continue
        if normalized in ignored:
            continue
        if len(line) > 80:
            continue
        result.append(line)
    return result
