"""Basic mapper for matching equivalent markets across exchanges."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

LOGGER = logging.getLogger(__name__)


class MarketMapper:
    def __init__(self, max_start_delta_minutes: int = 90, min_name_similarity: float = 0.62) -> None:
        self.max_start_delta_minutes = max_start_delta_minutes
        self.min_name_similarity = min_name_similarity

    def match_markets(
        self,
        betfair_rows: list[dict[str, Any]],
        matchbook_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return pairs of rows likely representing the same event, market and selection."""
        matches: list[dict[str, Any]] = []
        matchbook_by_market = defaultdict(list)
        for row in matchbook_rows:
            matchbook_by_market[(row["market_type"], self._normalize_selection(row["selection"]))].append(row)

        unmatched_events: set[tuple[str, str]] = set()
        for betfair_row in betfair_rows:
            key = (betfair_row["market_type"], self._normalize_selection(betfair_row["selection"]))
            candidates = matchbook_by_market.get(key, [])
            best_candidate = self._find_best_candidate(betfair_row, candidates)
            if best_candidate:
                matches.append({"betfair": betfair_row, "matchbook": best_candidate})
            else:
                event_key = (betfair_row["event_name"], betfair_row["market_type"])
                if event_key not in unmatched_events:
                    LOGGER.info(
                        "Evento sem equivalente: %s | %s | %s",
                        betfair_row["event_name"],
                        betfair_row["start_time"],
                        betfair_row["market_type"],
                    )
                    unmatched_events.add(event_key)
        return matches

    def _find_best_candidate(
        self,
        source: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        source_time = self._parse_datetime(source["start_time"])
        best_candidate = None
        best_score = 0.0

        for candidate in candidates:
            candidate_time = self._parse_datetime(candidate["start_time"])
            if source_time and candidate_time:
                delta_minutes = abs((source_time - candidate_time).total_seconds()) / 60
                if delta_minutes > self.max_start_delta_minutes:
                    continue

            score = SequenceMatcher(
                None,
                self._normalize_event_name(source["event_name"]),
                self._normalize_event_name(candidate["event_name"]),
            ).ratio()
            if score > best_score:
                best_candidate = candidate
                best_score = score

        if best_score >= self.min_name_similarity:
            return best_candidate
        return None

    def _normalize_event_name(self, value: str) -> str:
        normalized = value.lower()
        normalized = re.sub(r"\b(fc|cf|sc|afc|club|football|soccer)\b", "", normalized)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return " ".join(sorted(normalized.split()))

    def _normalize_selection(self, value: str) -> str:
        normalized = value.lower().strip()
        aliases = {
            "the draw": "draw",
            "x": "draw",
            "under 2.5": "under 2.5 goals",
            "over 2.5": "over 2.5 goals",
        }
        normalized = aliases.get(normalized, normalized)
        normalized = re.sub(r"[^a-z0-9.]+", " ", normalized)
        return " ".join(normalized.split())

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
