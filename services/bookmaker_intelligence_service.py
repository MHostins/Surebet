"""Read-only intelligence reports from Bookmaker Discovery SQLite data."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


WORLD_CUP_CONTEXT_NOTE = (
    "Os dados coletados durante a Copa do Mundo devem ser interpretados com cautela, "
    "pois as principais ligas de futebol estão paralisadas, alterando a distribuição "
    "normal de esportes, mercados e oportunidades."
)


def classify_market_family(market: str) -> str:
    text = _normalize_text(market)
    if any(token in text for token in ("acima", "abaixo", "over", "under", "mais de", "menos de", "total de gols")):
        return "over_under"
    if "handicap" in text:
        return "handicap"
    if any(token in text for token in ("dnb", "empate anula", "draw no bet")):
        return "dnb"
    if any(token in text for token in ("vencedor", "resultado final", "match winner", "money line", "moneyline")):
        return "match_winner"
    if any(token in text for token in ("jogador", "player", "marca gol", "pontos do jogador")):
        return "player_props"
    if any(token in text for token in ("set", "sets", "game", "games")):
        return "sets_games"
    if any(token in text for token in ("escanteio", "corner", "lateral", "throw", "cartao", "cartoes", "card")):
        return "corners_throwins_cards"
    return "other"


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return ascii_text.lower()


class BookmakerIntelligenceService:
    """Generates operational bookmaker intelligence without mutating discovery data."""

    def __init__(self, discovery_db_path: Path, output_dir: Path) -> None:
        self.discovery_db_path = discovery_db_path
        self.output_dir = output_dir

    def generate(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        rows = self._load_observations()
        expanded = self._expand_bookmaker_rows(rows)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_database": str(self.discovery_db_path),
            "summary": {
                "total_observations": len(rows),
                "total_expanded_bookmaker_rows": len(expanded),
                "total_bookmakers": len({row["bookmaker"] for row in expanded}),
                "total_pairs": len({row["bookmaker_pair"] for row in rows}),
            },
            "bookmaker_by_sport": self._bookmaker_by_sport(expanded),
            "bookmaker_by_market": self._bookmaker_by_market(expanded),
            "bookmaker_by_hour": self._bookmaker_by_hour(expanded),
            "bookmaker_pair_strength": self._bookmaker_pair_strength(rows),
            "bookmaker_consistency": self._bookmaker_consistency(expanded),
            "context_notes": {
                "sports_context": WORLD_CUP_CONTEXT_NOTE,
            },
        }
        self._write_outputs(report)
        return report

    def _load_observations(self) -> list[dict[str, Any]]:
        if not self.discovery_db_path.exists():
            return []
        connection = sqlite3.connect(self.discovery_db_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                select stable_key, first_seen_at, last_seen_at, profit_percent, sport, event_name,
                       market, bookmaker_1, bookmaker_2, bookmaker_pair, seen_count
                  from observations
                """
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def _expand_bookmaker_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        expanded: list[dict[str, Any]] = []
        for row in rows:
            for bookmaker in (row.get("bookmaker_1"), row.get("bookmaker_2")):
                if not bookmaker:
                    continue
                expanded.append(
                    {
                        **row,
                        "bookmaker": str(bookmaker),
                        "market_family": classify_market_family(str(row.get("market") or "")),
                        "hour_bucket": self._hour_bucket(row.get("first_seen_at")),
                        "seen_count": self._int_value(row.get("seen_count"), 1),
                        "profit_percent": self._float_value(row.get("profit_percent")),
                    }
                )
        return expanded

    def _bookmaker_by_sport(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._group_bookmaker_context(rows, ("bookmaker", "sport"), ("bookmaker", "sport"))

    def _bookmaker_by_market(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._group_bookmaker_context(rows, ("bookmaker", "market_family"), ("bookmaker", "market_family"))

    def _bookmaker_by_hour(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped = self._group_bookmaker_context(rows, ("hour_bucket", "bookmaker"), ("hour_bucket", "bookmaker"))
        return sorted(grouped, key=lambda row: (row["hour_bucket"], -row["appearances"], row["bookmaker"].lower()))

    def _group_bookmaker_context(
        self,
        rows: list[dict[str, Any]],
        key_fields: tuple[str, str],
        output_fields: tuple[str, str],
    ) -> list[dict[str, Any]]:
        groups: dict[tuple[Any, Any], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[(row.get(key_fields[0]), row.get(key_fields[1]))].append(row)

        result = []
        for key, group_rows in groups.items():
            profits = [row["profit_percent"] for row in group_rows]
            result.append(
                {
                    output_fields[0]: key[0],
                    output_fields[1]: key[1],
                    "appearances": sum(row["seen_count"] for row in group_rows),
                    "unique_opportunities": len({row["stable_key"] for row in group_rows}),
                    "avg_profit_percent": self._round(sum(profits) / len(profits)),
                    "max_profit_percent": self._round(max(profits)),
                }
            )
        return sorted(result, key=lambda row: (-row["appearances"], -row["max_profit_percent"], str(row[output_fields[0]])))

    def _bookmaker_pair_strength(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row.get("bookmaker_pair") or "unknown")].append(row)

        result = []
        for pair, group_rows in groups.items():
            profits = [self._float_value(row.get("profit_percent")) for row in group_rows]
            appearances = sum(self._int_value(row.get("seen_count"), 1) for row in group_rows)
            unique = len({row["stable_key"] for row in group_rows})
            result.append(
                {
                    "bookmaker_pair": pair,
                    "appearances": appearances,
                    "unique_opportunities": unique,
                    "avg_profit_percent": self._round(sum(profits) / len(profits)),
                    "max_profit_percent": self._round(max(profits)),
                    "persistence_score": self._round(appearances / max(unique, 1)),
                }
            )
        return sorted(result, key=lambda row: (-row["persistence_score"], -row["appearances"], row["bookmaker_pair"].lower()))

    def _bookmaker_consistency(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[row["bookmaker"]].append(row)

        result = []
        for bookmaker, group_rows in groups.items():
            profits = sorted(row["profit_percent"] for row in group_rows)
            appearances = sum(row["seen_count"] for row in group_rows)
            unique = len({row["stable_key"] for row in group_rows})
            active_span_hours = self._active_span_hours(group_rows)
            avg_profit = sum(profits) / len(profits)
            p95_profit = self._percentile(profits, 95)
            result.append(
                {
                    "bookmaker": bookmaker,
                    "appearances": appearances,
                    "unique_opportunities": unique,
                    "avg_profit_percent": self._round(avg_profit),
                    "median_profit_percent": self._round(float(median(profits))),
                    "p95_profit_percent": self._round(p95_profit),
                    "max_profit_percent": self._round(max(profits)),
                    "active_span_hours": self._round(active_span_hours),
                    "consistency_score": self._round((math.log1p(appearances) * avg_profit) + active_span_hours),
                }
            )
        return sorted(result, key=lambda row: (-row["consistency_score"], -row["appearances"], row["bookmaker"].lower()))

    def _write_outputs(self, report: dict[str, Any]) -> None:
        (self.output_dir / "bookmaker_intelligence_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.output_dir / "bookmaker_context_notes.json").write_text(
            json.dumps(report["context_notes"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_csv("bookmaker_by_sport.csv", report["bookmaker_by_sport"])
        self._write_csv("bookmaker_by_market.csv", report["bookmaker_by_market"])
        self._write_csv("bookmaker_by_hour.csv", report["bookmaker_by_hour"])
        self._write_csv("bookmaker_pair_strength.csv", report["bookmaker_pair_strength"])
        self._write_csv("bookmaker_consistency.csv", report["bookmaker_consistency"])

    def _write_csv(self, filename: str, rows: list[dict[str, Any]]) -> None:
        path = self.output_dir / filename
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def _hour_bucket(self, value: Any) -> str:
        parsed = self._parse_datetime(value)
        if parsed is None:
            return "unknown"
        return f"{parsed.hour:02d}:00"

    def _active_span_hours(self, rows: list[dict[str, Any]]) -> float:
        timestamps = []
        for row in rows:
            for field in ("first_seen_at", "last_seen_at"):
                parsed = self._parse_datetime(row.get(field))
                if parsed is not None:
                    timestamps.append(parsed)
        if len(timestamps) < 2:
            return 0.0
        return (max(timestamps) - min(timestamps)).total_seconds() / 3600.0

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            text = str(value).replace("Z", "+00:00")
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _percentile(self, values: list[float], percentile: int) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return values[0]
        index = (len(values) - 1) * percentile / 100.0
        lower = math.floor(index)
        upper = math.ceil(index)
        if lower == upper:
            return values[int(index)]
        return values[lower] + (values[upper] - values[lower]) * (index - lower)

    def _float_value(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _int_value(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _round(self, value: float) -> float:
        return round(float(value), 4)
