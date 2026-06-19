"""Models for read-only Novibet inspection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class NovibetNormalizedOdd:
    bookmaker: str
    sport: str
    league: str | None
    event_name: str
    start_time: str | None
    market_type: str
    selection: str
    odds: float
    source_url: str
    scraped_at: str
    side: str = "back"
    available_liquidity: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NovibetParseResult:
    raw_events: list[dict[str, Any]] = field(default_factory=list)
    normalized_odds: list[NovibetNormalizedOdd] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)

    @property
    def raw_events_count(self) -> int:
        return len(self.raw_events)

    def normalized_dicts(self) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self.normalized_odds]
