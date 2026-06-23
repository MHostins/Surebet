from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.bookmaker_discovery_service import (
    BookmakerDiscoveryParser,
    BookmakerDiscoveryRepository,
    BookmakerDiscoveryReporter,
    BookmakerDiscoveryService,
    DiscoveryConfig,
    DiscoveryOpportunity,
)


class BookmakerDiscoveryParserTests(unittest.TestCase):
    def test_extracts_opportunities_from_fixture_html(self) -> None:
        html = """
        <article data-surebet-opportunity data-profit="2.45" data-sport="Futebol"
                 data-event="Team A x Team B" data-market="Resultado Final"
                 data-url="/calculator/surebet/123">
            <span data-bookmaker="Novibet" data-odds="2.10"></span>
            <span data-bookmaker="EsportivaBet" data-odds="1.95"></span>
        </article>
        """

        opportunities = BookmakerDiscoveryParser().parse_html(
            html,
            source_url="https://pt.surebet.com/surebets",
            collected_at="2026-06-23T10:00:00+00:00",
        )

        self.assertEqual(len(opportunities), 1)
        opportunity = opportunities[0]
        self.assertEqual(opportunity.profit_percent, 2.45)
        self.assertEqual(opportunity.sport, "Futebol")
        self.assertEqual(opportunity.event_name, "Team A x Team B")
        self.assertEqual(opportunity.market, "Resultado Final")
        self.assertEqual(opportunity.bookmaker_1, "Novibet")
        self.assertEqual(opportunity.bookmaker_2, "EsportivaBet")
        self.assertEqual(opportunity.odds, [2.10, 1.95])
        self.assertEqual(opportunity.opportunity_url, "https://pt.surebet.com/calculator/surebet/123")

    def test_excludes_restricted_bookmakers(self) -> None:
        html = """
        <article data-surebet-opportunity data-profit="5.00" data-sport="Futebol"
                 data-event="Team A x Team B" data-market="Resultado Final">
            <span data-bookmaker="Betano" data-odds="2.30"></span>
            <span data-bookmaker="Novibet" data-odds="1.80"></span>
        </article>
        """

        opportunities = BookmakerDiscoveryParser().parse_html(
            html,
            source_url="https://pt.surebet.com/surebets",
            collected_at="2026-06-23T10:00:00+00:00",
        )

        self.assertEqual(opportunities, [])

    def test_ignores_incomplete_opportunities(self) -> None:
        html = """
        <article data-surebet-opportunity data-profit="2.00" data-sport="Futebol"
                 data-event="Team A x Team B">
            <span data-bookmaker="Novibet" data-odds="2.10"></span>
        </article>
        """

        opportunities = BookmakerDiscoveryParser().parse_html(
            html,
            source_url="https://pt.surebet.com/surebets",
            collected_at="2026-06-23T10:00:00+00:00",
        )

        self.assertEqual(opportunities, [])


class BookmakerDiscoveryRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output_dir = Path(self.temp_dir.name)
        self.db_path = self.output_dir / "bookmaker_discovery.db"
        self.repository = BookmakerDiscoveryRepository(
            self.db_path,
            min_profit_change=0.05,
            odds_change_epsilon=0.01,
        )

    def opportunity(self, *, profit: float = 2.45, odds: list[float] | None = None) -> DiscoveryOpportunity:
        return DiscoveryOpportunity(
            collected_at="2026-06-23T10:00:00+00:00",
            profit_percent=profit,
            sport="Futebol",
            event_name="Team A x Team B",
            market="Resultado Final",
            bookmaker_1="Novibet",
            bookmaker_2="EsportivaBet",
            odds=odds or [2.10, 1.95],
            opportunity_url="https://pt.surebet.com/calculator/surebet/123",
        )

    def test_deduplicates_same_opportunity_and_updates_seen_count(self) -> None:
        first = self.repository.save_opportunities([self.opportunity()])
        second = self.repository.save_opportunities([self.opportunity()])

        self.assertEqual(first["inserted"], 1)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["updated"], 1)

        connection = sqlite3.connect(self.db_path)
        try:
            row_count = connection.execute("select count(*) from observations").fetchone()[0]
            seen_count = connection.execute("select seen_count from observations").fetchone()[0]
            events_count = connection.execute("select count(*) from observation_events").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(row_count, 1)
        self.assertEqual(seen_count, 2)
        self.assertEqual(events_count, 1)

    def test_records_relevant_profit_change(self) -> None:
        self.repository.save_opportunities([self.opportunity(profit=2.45)])
        result = self.repository.save_opportunities([self.opportunity(profit=2.60)])

        self.assertEqual(result["changed"], 1)

        connection = sqlite3.connect(self.db_path)
        try:
            events_count = connection.execute("select count(*) from observation_events").fetchone()[0]
            current_profit = connection.execute("select profit_percent from observations").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(events_count, 2)
        self.assertEqual(current_profit, 2.60)


class BookmakerDiscoveryReporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output_dir = Path(self.temp_dir.name)
        self.db_path = self.output_dir / "bookmaker_discovery.db"
        self.repository = BookmakerDiscoveryRepository(self.db_path)

    def test_generates_rankings_and_top_five(self) -> None:
        opportunities = [
            DiscoveryOpportunity("2026-06-23T10:00:00+00:00", 2.0, "Futebol", "A x B", "Resultado Final", "Novibet", "EsportivaBet", [2.1, 1.9], None),
            DiscoveryOpportunity("2026-06-23T10:00:05+00:00", 4.0, "Tênis", "C x D", "Vencedor", "Novibet", "Superbet", [2.4, 1.8], None),
            DiscoveryOpportunity("2026-06-23T10:00:10+00:00", 3.0, "Basquete", "E x F", "Money Line", "HiperBet", "Superbet", [2.2, 1.9], None),
        ]
        self.repository.save_opportunities(opportunities)

        report = BookmakerDiscoveryReporter(self.output_dir, self.db_path).generate()

        self.assertEqual(report["summary"]["total_observations"], 3)
        self.assertEqual(report["ranking_frequency"][0]["bookmaker"], "Novibet")
        self.assertEqual(report["ranking_frequency"][0]["appearances"], 2)
        self.assertEqual(len(report["recommended_top_5"]), 4)
        self.assertTrue((self.output_dir / "bookmaker_discovery_report.json").exists())
        self.assertTrue((self.output_dir / "weighted_ranking.csv").exists())

    def test_reporter_handles_missing_database(self) -> None:
        report = BookmakerDiscoveryReporter(self.output_dir, self.output_dir / "missing.db").generate()

        self.assertEqual(report["summary"]["total_observations"], 0)
        self.assertEqual(report["recommended_top_5"], [])


class BookmakerDiscoveryServiceTests(unittest.TestCase):
    def test_report_mode_regenerates_without_browser(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            db_path = output_dir / "bookmaker_discovery.db"
            BookmakerDiscoveryRepository(db_path).save_opportunities([
                DiscoveryOpportunity("2026-06-23T10:00:00+00:00", 2.0, "Futebol", "A x B", "Resultado Final", "Novibet", "EsportivaBet", [2.1, 1.9], None)
            ])
            config = DiscoveryConfig(
                username="user@example.com",
                password="secret",
                base_url="https://pt.surebet.com",
                output_dir=output_dir,
                poll_seconds=5,
                max_cycles=0,
                headless=False,
            )

            report = BookmakerDiscoveryService(config).generate_report_only()

            self.assertEqual(report["summary"]["total_observations"], 1)
            self.assertTrue((output_dir / "bookmaker_discovery_report.json").exists())


if __name__ == "__main__":
    unittest.main()
