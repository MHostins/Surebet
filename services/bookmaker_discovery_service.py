"""Read-only SureBet.com bookmaker discovery research service."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
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

RESTRICTED_BOOKMAKERS = {"betano", "bet365"}


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

    @property
    def bookmaker_pair(self) -> str:
        return " x ".join(sorted([self.bookmaker_1, self.bookmaker_2], key=str.lower))

    def contains_restricted_bookmaker(self) -> bool:
        return any(_normalize_name(name) in RESTRICTED_BOOKMAKERS for name in (self.bookmaker_1, self.bookmaker_2))

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

    def parse_html(self, html: str, source_url: str, collected_at: str) -> list[DiscoveryOpportunity]:
        parser = _SurebetFixtureParser(source_url, collected_at)
        parser.feed(html or "")
        return [item for item in parser.opportunities if not item.contains_restricted_bookmaker()]

    def parse_extracted_blocks(
        self,
        blocks: list[dict[str, Any]],
        source_url: str,
        collected_at: str,
    ) -> list[DiscoveryOpportunity]:
        opportunities: list[DiscoveryOpportunity] = []
        for block in blocks:
            html = str(block.get("html") or "")
            parsed = self.parse_html(html, source_url=source_url, collected_at=collected_at)
            if parsed:
                opportunities.extend(parsed)
                continue

            opportunity = self._parse_visible_text_block(block, source_url, collected_at)
            if opportunity and not opportunity.contains_restricted_bookmaker():
                opportunities.append(opportunity)
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
                if _normalize_name(bookmaker) in RESTRICTED_BOOKMAKERS:
                    continue
                row = rows.setdefault(
                    bookmaker,
                    {
                        "bookmaker": bookmaker,
                        "appearances": 0,
                        "avg_profit_percent": 0.0,
                        "max_profit_percent": 0.0,
                        "_profit_sum": 0.0,
                    },
                )
                row["appearances"] += int(observation.get("seen_count") or 1)
                row["_profit_sum"] += float(observation["profit_percent"])
                row["max_profit_percent"] = max(row["max_profit_percent"], float(observation["profit_percent"]))

        for row in rows.values():
            count = max(1, sum(1 for obs in observations if row["bookmaker"] in {obs["bookmaker_1"], obs["bookmaker_2"]}))
            row["avg_profit_percent"] = round(row["_profit_sum"] / count, 4)
            row.pop("_profit_sum", None)
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
                        stats = self.repository.save_opportunities(opportunities)
                        if stats["inserted"] or stats["changed"]:
                            last_report = self.generate_report_only()
                        LOGGER.info(
                            "Bookmaker discovery cycle=%s blocks=%s parsed=%s inserted=%s changed=%s updated=%s",
                            cycle,
                            len(blocks),
                            len(opportunities),
                            stats["inserted"],
                            stats["changed"],
                            stats["updated"],
                        )
                    except PlaywrightTimeoutError:
                        LOGGER.warning("SureBet DOM timed out; reloading surebets page.")
                        page.goto(self.config.surebets_url, wait_until="domcontentloaded", timeout=30000)
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

    def _login(self, page: Any) -> None:
        page.goto(self.config.surebets_url, wait_until="domcontentloaded", timeout=30000)
        if self._looks_authenticated(page):
            return

        page.goto(urljoin(self.config.base_url.rstrip("/") + "/", "users/sign_in"), wait_until="domcontentloaded", timeout=30000)
        username_selector = "input[type='email'], input[name*='email' i], input[name*='login' i], input[name*='user' i]"
        password_selector = "input[type='password']"
        page.locator(username_selector).first.fill(self.config.username)
        page.locator(password_selector).first.fill(self.config.password)
        page.locator("button[type='submit'], input[type='submit']").first.click()
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.goto(self.config.surebets_url, wait_until="domcontentloaded", timeout=30000)
        if not self._looks_authenticated(page):
            raise RuntimeError("SureBet login did not reach an authenticated surebets page.")

    def _looks_authenticated(self, page: Any) -> bool:
        try:
            text = page.locator("body").inner_text(timeout=5000).lower()
        except Exception:
            return False
        return "sign in" not in text and "entrar" not in text and ("surebet" in text or "apostas seguras" in text)

    def _extract_visible_blocks(self, page: Any) -> list[dict[str, Any]]:
        return page.evaluate(
            """
            () => {
              const selectors = [
                '[data-surebet-opportunity]',
                '[class*="surebet" i]',
                'tr',
                'article',
                'section'
              ];
              const seen = new Set();
              const blocks = [];
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
            """
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


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(ascii_text.strip().lower().replace("-", " ").split())


def _clean_space(value: str) -> str:
    return " ".join((value or "").strip().split())


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


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
