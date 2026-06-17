"""Initial read-only odds comparison reports."""

from __future__ import annotations

import csv
import json
import logging
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


class ComparisonService:
    """Compares normalized odds from two sources without calculating surebets."""

    def __init__(
        self,
        output_dir: Path,
        max_start_delta_minutes: int = 90,
        min_event_match_confidence: float = 0.85,
        aliases_path: Path | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.max_start_delta_minutes = max_start_delta_minutes
        self.min_event_match_confidence = min_event_match_confidence
        self.aliases_path = aliases_path or Path("config/team_aliases.json")
        self.alias_lookup = self._load_aliases(self.aliases_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def compare_betfair_matchbook_br(
        self,
        betfair_rows: list[dict[str, Any]],
        matchbook_br_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        betfair_match_odds = self._match_odds_rows(betfair_rows)
        matchbook_match_odds = self._match_odds_rows(matchbook_br_rows)
        betfair_events = self._group_by_event(betfair_match_odds)
        matchbook_events = self._group_by_event(matchbook_match_odds)

        paired_events = []
        unmatched_betfair = []
        used_matchbook_keys: set[tuple[str, str | None]] = set()
        comparison_rows: list[dict[str, Any]] = []

        for betfair_key, betfair_event_rows in betfair_events.items():
            matchbook_key, confidence = self._find_matching_event(betfair_key, matchbook_events, used_matchbook_keys)
            if not matchbook_key:
                unmatched_betfair.append(self._event_summary(betfair_key, betfair_event_rows))
                continue

            used_matchbook_keys.add(matchbook_key)
            matchbook_event_rows = matchbook_events[matchbook_key]
            selection_matches = self._compare_event_selections(betfair_event_rows, matchbook_event_rows, confidence)
            comparison_rows.extend(selection_matches)
            paired_events.append(
                {
                    "betfair_event_name": betfair_key[0],
                    "betfair_start_time": betfair_key[1],
                    "matchbook_br_event_name": matchbook_key[0],
                    "matchbook_br_start_time": matchbook_key[1],
                    "match_confidence": round(confidence, 4),
                    "paired_selections": len(selection_matches),
                }
            )

        unmatched_matchbook = [
            self._event_summary(key, rows)
            for key, rows in matchbook_events.items()
            if key not in used_matchbook_keys
        ]
        biggest_difference = max(comparison_rows, key=lambda row: row["absolute_odds_difference"], default=None)
        paired_events_sorted = sorted(paired_events, key=lambda row: row["match_confidence"], reverse=True)
        paired_selection_denominator = max(1, min(len(betfair_match_odds), len(matchbook_match_odds)))
        report = {
            "comparison": "betfair-matchbook-br",
            "market_filter": "Match Odds",
            "min_event_match_confidence": self.min_event_match_confidence,
            "total_events_betfair": len(betfair_events),
            "total_events_matchbook_br": len(matchbook_events),
            "paired_events_count": len(paired_events),
            "unpaired_events_count": len(unmatched_betfair) + len(unmatched_matchbook),
            "paired_selections_count": len(comparison_rows),
            "event_pairing_rate": round(len(paired_events) / max(1, len(betfair_events)), 6),
            "selection_pairing_rate": round(len(comparison_rows) / paired_selection_denominator, 6),
            "best_20_pairs_by_confidence": paired_events_sorted[:20],
            "worst_20_accepted_pairs": sorted(paired_events, key=lambda row: row["match_confidence"])[:20],
            "biggest_odds_difference": biggest_difference,
            "paired_events": paired_events,
            "unpaired_events": {
                "betfair": unmatched_betfair,
                "matchbook_br": unmatched_matchbook,
            },
            "selection_comparisons": comparison_rows,
        }
        self._save_report(report, comparison_rows, unmatched_betfair, unmatched_matchbook)
        LOGGER.info(
            "comparison betfair-matchbook-br: betfair_events=%s matchbook_br_events=%s paired_events=%s paired_selections=%s event_rate=%.2f%% selection_rate=%.2f%%",
            report["total_events_betfair"],
            report["total_events_matchbook_br"],
            report["paired_events_count"],
            report["paired_selections_count"],
            report["event_pairing_rate"] * 100,
            report["selection_pairing_rate"] * 100,
        )
        return report

    def _match_odds_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if str(row.get("market_type", "")).lower() == "match odds"]

    def _group_by_event(self, rows: list[dict[str, Any]]) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
        grouped: dict[tuple[str, str | None], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(row.get("event_name", ""), row.get("start_time"))].append(row)
        return dict(grouped)

    def _find_matching_event(
        self,
        source_key: tuple[str, str | None],
        candidates: dict[tuple[str, str | None], list[dict[str, Any]]],
        used_keys: set[tuple[str, str | None]],
    ) -> tuple[tuple[str, str | None] | None, float]:
        best_key = None
        best_confidence = 0.0
        source_time = self._parse_datetime(source_key[1])
        for candidate_key in candidates:
            if candidate_key in used_keys:
                continue
            candidate_time = self._parse_datetime(candidate_key[1])
            if source_time and candidate_time:
                delta_minutes = abs((source_time - candidate_time).total_seconds()) / 60
                if delta_minutes > self.max_start_delta_minutes:
                    continue
            confidence = self._event_confidence(source_key[0], candidate_key[0])
            if confidence > best_confidence:
                best_key = candidate_key
                best_confidence = confidence
        if best_key and best_confidence >= self.min_event_match_confidence:
            return best_key, best_confidence
        return None, best_confidence

    def _event_confidence(self, source_name: str, candidate_name: str) -> float:
        source_teams = self._event_team_tokens(source_name)
        candidate_teams = self._event_team_tokens(candidate_name)
        if len(source_teams) >= 2 and len(candidate_teams) >= 2:
            direct = (self._token_similarity(source_teams[0], candidate_teams[0]) + self._token_similarity(source_teams[1], candidate_teams[1])) / 2
            swapped = (self._token_similarity(source_teams[0], candidate_teams[1]) + self._token_similarity(source_teams[1], candidate_teams[0])) / 2
            return max(direct, swapped)
        return self._token_similarity(self._normalize_event_name(source_name), self._normalize_event_name(candidate_name))

    def _compare_event_selections(
        self,
        betfair_rows: list[dict[str, Any]],
        matchbook_rows: list[dict[str, Any]],
        match_confidence: float,
    ) -> list[dict[str, Any]]:
        comparisons: list[dict[str, Any]] = []
        matchbook_index = defaultdict(list)
        for row in matchbook_rows:
            matchbook_index[(self._normalize_selection(row.get("selection", "")), row.get("side"))].append(row)

        for betfair_row in betfair_rows:
            key = (self._normalize_selection(betfair_row.get("selection", "")), betfair_row.get("side"))
            candidates = matchbook_index.get(key, [])
            if not candidates:
                continue
            matchbook_row = max(candidates, key=lambda row: float(row.get("available_liquidity") or 0))
            betfair_odds = float(betfair_row.get("odds") or 0)
            matchbook_odds = float(matchbook_row.get("odds") or 0)
            comparisons.append(
                {
                    "event_name_betfair": betfair_row.get("event_name"),
                    "event_name_matchbook_br": matchbook_row.get("event_name"),
                    "start_time_betfair": betfair_row.get("start_time"),
                    "start_time_matchbook_br": matchbook_row.get("start_time"),
                    "match_confidence": round(match_confidence, 4),
                    "selection_betfair": betfair_row.get("selection"),
                    "selection_matchbook_br": matchbook_row.get("selection"),
                    "side": betfair_row.get("side"),
                    "betfair_odds": betfair_odds,
                    "matchbook_br_odds": matchbook_odds,
                    "absolute_odds_difference": round(abs(betfair_odds - matchbook_odds), 6),
                    "betfair_liquidity": betfair_row.get("available_liquidity"),
                    "matchbook_br_liquidity": matchbook_row.get("available_liquidity"),
                }
            )
        return comparisons

    def _event_summary(self, key: tuple[str, str | None], rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "event_name": key[0],
            "normalized_event_name": self._normalize_event_name(key[0]),
            "start_time": key[1],
            "rows": len(rows),
            "selections": sorted({str(row.get("selection")) for row in rows}),
        }

    def _event_team_tokens(self, value: str) -> list[str]:
        normalized = self._basic_normalize(value)
        parts = [part.strip() for part in re.split(r"\b(?:v|vs|x)\b", normalized) if part.strip()]
        return [self._canonical_name(part) for part in parts]

    def _normalize_event_name(self, value: str) -> str:
        tokens = self._event_team_tokens(value)
        if tokens:
            return " ".join(sorted(tokens))
        return self._canonical_name(value)

    def _normalize_selection(self, value: str) -> str:
        normalized = self._canonical_name(value)
        aliases = {
            "the draw": "draw",
            "empate": "draw",
            "x": "draw",
        }
        return aliases.get(normalized, normalized)

    def _canonical_name(self, value: str) -> str:
        normalized = self._basic_normalize(value)
        normalized = re.sub(r"\b(fc|cf|sc|afc|club|football|soccer)\b", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return self.alias_lookup.get(normalized, normalized)

    def _basic_normalize(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value.lower())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = normalized.replace("-", " ")
        normalized = re.sub(r"\bversus\b", " v ", normalized)
        normalized = re.sub(r"\bvs\.\b|\bvs\b|\bx\b", " v ", normalized)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _token_similarity(self, left: str, right: str) -> float:
        if left == right:
            return 1.0
        return SequenceMatcher(None, left, right).ratio()

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

    def _load_aliases(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        lookup: dict[str, str] = {}
        for canonical, aliases in data.items():
            canonical_norm = self._basic_normalize(canonical)
            lookup[canonical_norm] = canonical_norm
            if isinstance(aliases, list):
                for alias in aliases:
                    lookup[self._basic_normalize(str(alias))] = canonical_norm
        return lookup

    def _save_report(
        self,
        report: dict[str, Any],
        rows: list[dict[str, Any]],
        unmatched_betfair: list[dict[str, Any]],
        unmatched_matchbook: list[dict[str, Any]],
    ) -> None:
        json_path = self.output_dir / "comparison_report.json"
        csv_path = self.output_dir / "comparison_report.csv"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_csv(csv_path, rows)
        self._write_csv(self.output_dir / "unpaired_events_betfair.csv", unmatched_betfair)
        self._write_csv(self.output_dir / "unpaired_events_matchbook_br.csv", unmatched_matchbook)

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        normalized_rows = [self._flatten_for_csv(row) for row in rows]
        fieldnames = sorted({key for row in normalized_rows for key in row.keys()})
        if not fieldnames:
            fieldnames = ["message"]
            normalized_rows = [{"message": "Nenhum registro encontrado"}]
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(normalized_rows)

    def _flatten_for_csv(self, row: dict[str, Any]) -> dict[str, Any]:
        flattened = {}
        for key, value in row.items():
            if isinstance(value, (list, dict)):
                flattened[key] = json.dumps(value, ensure_ascii=False)
            else:
                flattened[key] = value
        return flattened

