"""Suggest team aliases from unpaired event reports without applying them."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


class AliasSuggestionService:
    """Reads unpaired event CSVs and suggests possible aliases/events."""

    def __init__(self, output_dir: Path, max_start_delta_minutes: int = 90, min_score: float = 0.75) -> None:
        self.output_dir = output_dir
        self.max_start_delta_minutes = max_start_delta_minutes
        self.min_score = min_score

    def suggest(self) -> dict[str, Any]:
        betfair_path = self.output_dir / "unpaired_events_betfair.csv"
        matchbook_path = self.output_dir / "unpaired_events_matchbook_br.csv"
        betfair_events = self._read_events(betfair_path)
        matchbook_events = self._read_events(matchbook_path)

        suggested_pairs = []
        alias_suggestions: dict[str, set[str]] = {}
        for betfair_event in betfair_events:
            betfair_time = self._parse_datetime(betfair_event.get("start_time"))
            for matchbook_event in matchbook_events:
                matchbook_time = self._parse_datetime(matchbook_event.get("start_time"))
                if betfair_time and matchbook_time:
                    delta_minutes = abs((betfair_time - matchbook_time).total_seconds()) / 60
                    if delta_minutes > self.max_start_delta_minutes:
                        continue
                else:
                    delta_minutes = None

                score, team_pairs = self._score_events(betfair_event["event_name"], matchbook_event["event_name"])
                if score < self.min_score:
                    continue

                suggested_pairs.append(
                    {
                        "score": round(score, 6),
                        "time_delta_minutes": round(delta_minutes, 2) if delta_minutes is not None else None,
                        "betfair_event_name": betfair_event["event_name"],
                        "betfair_start_time": betfair_event.get("start_time"),
                        "matchbook_br_event_name": matchbook_event["event_name"],
                        "matchbook_br_start_time": matchbook_event.get("start_time"),
                        "suggested_team_pairs": team_pairs,
                    }
                )
                for canonical, alias in team_pairs:
                    if canonical and alias and canonical != alias:
                        alias_suggestions.setdefault(canonical, set()).add(alias)

        suggested_pairs.sort(key=lambda row: row["score"], reverse=True)
        aliases_json = {key: sorted(values | {key}) for key, values in sorted(alias_suggestions.items())}
        report = {
            "source_files": {
                "betfair": str(betfair_path),
                "matchbook_br": str(matchbook_path),
            },
            "min_score": self.min_score,
            "max_start_delta_minutes": self.max_start_delta_minutes,
            "suggested_event_pairs_count": len(suggested_pairs),
            "suggested_aliases_count": len(aliases_json),
            "suggested_aliases": aliases_json,
            "suggested_event_pairs": suggested_pairs,
        }
        self._write_json(self.output_dir / "suggested_team_aliases.json", aliases_json)
        self._write_event_pairs_csv(self.output_dir / "suggested_event_pairs.csv", suggested_pairs)
        return report

    def _read_events(self, path: Path) -> list[dict[str, str]]:
        if not path.exists():
            raise FileNotFoundError(f"Arquivo nao encontrado: {path}")
        with path.open("r", newline="", encoding="utf-8-sig") as file:
            return list(csv.DictReader(file))

    def _score_events(self, betfair_name: str, matchbook_name: str) -> tuple[float, list[tuple[str, str]]]:
        betfair_teams = self._split_teams(betfair_name)
        matchbook_teams = self._split_teams(matchbook_name)
        if len(betfair_teams) >= 2 and len(matchbook_teams) >= 2:
            direct_pairs = [(betfair_teams[0], matchbook_teams[0]), (betfair_teams[1], matchbook_teams[1])]
            swapped_pairs = [(betfair_teams[0], matchbook_teams[1]), (betfair_teams[1], matchbook_teams[0])]
            direct_score = self._pair_score(direct_pairs)
            swapped_score = self._pair_score(swapped_pairs)
            if swapped_score > direct_score:
                return swapped_score, swapped_pairs
            return direct_score, direct_pairs

        score = self._text_similarity(self._normalize_name(betfair_name), self._normalize_name(matchbook_name))
        return score, [(self._normalize_name(betfair_name), self._normalize_name(matchbook_name))]

    def _pair_score(self, pairs: list[tuple[str, str]]) -> float:
        scores = []
        for left, right in pairs:
            scores.append(max(self._text_similarity(left, right), self._partial_similarity(left, right)))
        return sum(scores) / max(1, len(scores))

    def _split_teams(self, value: str) -> list[str]:
        normalized = self._basic_normalize(value)
        parts = [part.strip() for part in re.split(r"\b(?:v|vs|x)\b", normalized) if part.strip()]
        return [self._normalize_name(part) for part in parts]

    def _normalize_name(self, value: str) -> str:
        normalized = self._basic_normalize(value)
        normalized = re.sub(r"\b(fc|cf|sc|afc|club|ca|cd|fk|sv|svg|umfn)\b", "", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _basic_normalize(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value.lower())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = normalized.replace("-", " ")
        normalized = re.sub(r"\bversus\b", " v ", normalized)
        normalized = re.sub(r"\bvs\.\b|\bvs\b|\bx\b", " v ", normalized)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _text_similarity(self, left: str, right: str) -> float:
        if left == right:
            return 1.0
        return SequenceMatcher(None, left, right).ratio()

    def _partial_similarity(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        left_tokens = set(left.split())
        right_tokens = set(right.split())
        overlap = len(left_tokens & right_tokens)
        return overlap / max(1, min(len(left_tokens), len(right_tokens)))

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

    def _write_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_event_pairs_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        fieldnames = [
            "score",
            "time_delta_minutes",
            "betfair_event_name",
            "betfair_start_time",
            "matchbook_br_event_name",
            "matchbook_br_start_time",
            "suggested_team_pairs",
        ]
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                output = dict(row)
                output["suggested_team_pairs"] = json.dumps(row["suggested_team_pairs"], ensure_ascii=False)
                writer.writerow(output)
