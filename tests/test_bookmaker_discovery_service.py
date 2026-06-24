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

    def test_fallback_parses_visible_text_opportunity(self) -> None:
        visible_text = """
        16,2%
        2 h
        Betsson
        Futebol
        Mystake
        Futebol
        23/06 England - Ghana
        Jogos Internacionais
        Acima 0.5 gols
        1.78
        Abaixo 0.5 gols
        3.35
        """

        opportunities = BookmakerDiscoveryParser().parse_visible_text(
            visible_text,
            source_url="https://pt.surebet.com/surebets",
            collected_at="2026-06-23T10:00:00+00:00",
        )

        self.assertEqual(len(opportunities), 1)
        opportunity = opportunities[0]
        self.assertEqual(opportunity.profit_percent, 16.2)
        self.assertEqual(opportunity.bookmaker_1, "Betsson")
        self.assertEqual(opportunity.bookmaker_2, "Mystake")
        self.assertEqual(opportunity.sport, "Futebol")
        self.assertEqual(opportunity.event_name, "23/06 England - Ghana")
        self.assertEqual(opportunity.market, "Acima 0.5 gols / Abaixo 0.5 gols")
        self.assertEqual(opportunity.odds, [1.78, 3.35])

    def test_fallback_excludes_restricted_bookmakers(self) -> None:
        visible_text = """
        8,4%
        Betano
        Futebol
        Novibet
        Futebol
        23/06 Team A - Team B
        Resultado final
        Casa
        2.10
        Fora
        2.05
        """

        opportunities = BookmakerDiscoveryParser().parse_visible_text(
            visible_text,
            source_url="https://pt.surebet.com/surebets",
            collected_at="2026-06-23T10:00:00+00:00",
        )

        self.assertEqual(opportunities, [])

    def test_dom_parser_extracts_multiple_real_surebet_records(self) -> None:
        html = _realistic_surebet_records_fixture()

        opportunities = BookmakerDiscoveryParser().parse_html(
            html,
            source_url="https://pt.surebet.com/surebets",
            collected_at="2026-06-23T10:00:00+00:00",
        )

        self.assertEqual(len(opportunities), 2)
        first = opportunities[0]
        self.assertEqual(first.opportunity_id, "101")
        self.assertEqual(first.profit_percent, 16.24)
        self.assertEqual(first.bookmaker_1, "Betsson (ES)")
        self.assertEqual(first.bookmaker_2, "Mystake")
        self.assertEqual(first.sport, "Futebol")
        self.assertEqual(first.event_name, "23/06 England - Ghana")
        self.assertEqual(first.market, "Acima 0.5 gols / Abaixo 0.5 gols")
        self.assertEqual(first.odds, [1.78, 3.35])

        second = opportunities[1]
        self.assertEqual(second.opportunity_id, "102")
        self.assertEqual(second.profit_percent, 11.6)
        self.assertEqual(second.bookmaker_1, "AlfaBet (BR)")
        self.assertEqual(second.bookmaker_2, "Stake")
        self.assertEqual(second.odds, [1.58, 3.8])

    def test_dom_parser_rejects_masked_and_restricted_records(self) -> None:
        parser = BookmakerDiscoveryParser()

        opportunities = parser.parse_html(
            _realistic_surebet_records_fixture(),
            source_url="https://pt.surebet.com/surebets",
            collected_at="2026-06-23T10:00:00+00:00",
        )

        self.assertEqual(len(opportunities), 2)
        self.assertEqual(parser.last_dom_record_count, 4)
        self.assertEqual(parser.last_rejection_counts["masked_xxx"], 1)
        self.assertEqual(parser.last_rejection_counts["restricted_bookmaker"], 1)
        self.assertEqual(parser.last_dom_valid_count, 2)
        self.assertEqual(parser.last_dom_rejected_count, 2)


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

    def test_writes_debug_snapshot_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config = DiscoveryConfig(
                username="user@example.com",
                password="secret",
                base_url="https://pt.surebet.com",
                output_dir=output_dir,
                poll_seconds=5,
                max_cycles=0,
                headless=False,
            )
            service = BookmakerDiscoveryService(config)
            fake_page = _FakeDebugPage()

            summary = service.save_debug_snapshot(fake_page, output_dir / "debug")

            self.assertTrue((output_dir / "debug" / "page.html").exists())
            self.assertTrue((output_dir / "debug" / "page.png").exists())
            self.assertTrue((output_dir / "debug" / "dom_summary.json").exists())
            self.assertTrue((output_dir / "debug" / "visible_text.txt").exists())
            self.assertEqual(summary["parser_current_extracted_count"], 1)
            self.assertEqual(summary["surebet_record_count"], 1)
            self.assertEqual(summary["surebet_leg_count"], 2)
            self.assertEqual(summary["dom_parser_valid_count"], 1)
            self.assertEqual(summary["dom_parser_rejected_count"], 0)
            self.assertGreaterEqual(summary["elements_containing_percent_count"], 1)

    def test_empty_cycles_trigger_auto_debug_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            config = DiscoveryConfig(
                username="user@example.com",
                password="secret",
                base_url="https://pt.surebet.com",
                output_dir=output_dir,
                poll_seconds=5,
                max_cycles=0,
                headless=False,
            )
            service = BookmakerDiscoveryService(config)
            fake_page = _FakeDebugPage(visible_text="Pagina sem oportunidades", html="<html><body>vazio</body></html>")

            self.assertFalse(service._record_empty_cycle_and_maybe_snapshot(fake_page, 1))
            self.assertFalse(service._record_empty_cycle_and_maybe_snapshot(fake_page, 2))
            self.assertTrue(service._record_empty_cycle_and_maybe_snapshot(fake_page, 3))

            snapshot_dir = output_dir / "debug" / "auto_empty_snapshot"
            self.assertTrue((snapshot_dir / "dom_summary.json").exists())

    def test_page_auth_status_detects_limited_public_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = BookmakerDiscoveryService(
                DiscoveryConfig(
                    username="user@example.com",
                    password="secret",
                    base_url="https://pt.surebet.com",
                    output_dir=Path(temp_dir),
                    poll_seconds=5,
                    max_cycles=0,
                    headless=True,
                )
            )
            page = _FakeDebugPage(
                visible_text="Entrar Login Encontrado apostas seguras 1.0%",
                html=_single_realistic_surebet_record_fixture(profit="1.0"),
                login_form_count=1,
            )

            status = service.get_page_auth_status(page, [1.0])

            self.assertTrue(status["login_form_detected"])
            self.assertTrue(status["contains_entrar_or_login"])
            self.assertTrue(status["all_profits_are_1_percent"])
            self.assertEqual(status["max_profit_seen"], 1.0)

    def test_auth_guard_refuses_to_persist_limited_public_data_and_saves_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            service = BookmakerDiscoveryService(
                DiscoveryConfig(
                    username="user@example.com",
                    password="secret",
                    base_url="https://pt.surebet.com",
                    output_dir=output_dir,
                    poll_seconds=5,
                    max_cycles=0,
                    headless=True,
                    require_authenticated=True,
                    max_limited_cycles=1,
                )
            )
            page = _FakeDebugPage(
                visible_text="Entrar Login Encontrado apostas seguras 1.0%",
                html=_single_realistic_surebet_record_fixture(profit="1.0"),
                login_form_count=1,
            )
            opportunities = BookmakerDiscoveryParser().parse_html(
                _single_realistic_surebet_record_fixture(profit="1.0"),
                source_url="https://pt.surebet.com/surebets",
                collected_at="2026-06-24T10:00:00+00:00",
            )

            with self.assertRaises(RuntimeError):
                service._enforce_authenticated_collection(page, opportunities)

            self.assertTrue((output_dir / "debug" / "auth_failure_snapshot" / "dom_summary.json").exists())
            self.assertEqual(service.repository.fetch_observations(), [])

    def test_debug_headless_uses_config_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = BookmakerDiscoveryService(
                DiscoveryConfig(
                    username="user@example.com",
                    password="secret",
                    base_url="https://pt.surebet.com",
                    output_dir=Path(temp_dir),
                    poll_seconds=5,
                    max_cycles=0,
                    headless=True,
                )
            )

            self.assertTrue(service._debug_headless())


class _FakeLocator:
    def __init__(self, count_value: int) -> None:
        self.count_value = count_value

    def count(self) -> int:
        return self.count_value


class _FakeDebugPage:
    url = "https://pt.surebet.com/surebets"

    def __init__(
        self,
        visible_text: str | None = None,
        html: str | None = None,
        login_form_count: int = 0,
        account_count: int = 0,
    ) -> None:
        self._visible_text = visible_text or """
        Apostas seguras Encontrado
        16,2%
        Betsson
        Futebol
        Mystake
        Futebol
        23/06 England - Ghana
        Acima 0.5 gols
        1.78
        Abaixo 0.5 gols
        3.35
        """
        self._html = html or _single_realistic_surebet_record_fixture()
        self._login_form_count = login_form_count
        self._account_count = account_count

    def content(self) -> str:
        return self._html

    def title(self) -> str:
        return "Apostas seguras encontradas"

    def screenshot(self, path: str, full_page: bool = True) -> None:
        Path(path).write_bytes(b"fake-png")

    def locator(self, selector: str) -> _FakeLocator:
        lowered = selector.lower()
        if "password" in lowered or "sign_in" in lowered or "login" in lowered:
            return _FakeLocator(self._login_form_count)
        if "account" in lowered or "logout" in lowered or "sign_out" in lowered:
            return _FakeLocator(self._account_count)
        return _FakeLocator(0)

    def evaluate(self, script: str, *args):
        if "document.body.innerText" in script:
            return self._visible_text
        return {
            "div_count": 1,
            "tr_count": 1,
            "a_count": 2,
            "surebet_record_count": 1,
            "surebet_leg_count": 2,
            "elements_containing_percent_count": 1,
            "elements_containing_known_bookmakers_count": 2,
            "candidate_blocks": [
                {
                    "text": self._visible_text,
                    "html": self._html,
                    "href": None,
                    "selector": "body",
                }
            ],
        }


def _leg_html(bookmaker: str, sport: str, event: str, tournament: str, market: str, odd: str) -> str:
    return f"""
    <tr data-testid="surebet-leg">
      <td class="booker">
        {bookmaker}
        <span data-testid="surebet-leg-sport">{sport}</span>
      </td>
      <td class="time">23/06 14:00</td>
      <td class="event">
        {event}
        <span data-testid="surebet-leg-tournament">{tournament}</span>
      </td>
      <td class="coeff">{market}</td>
      <td class="value">{odd}</td>
    </tr>
    """


def _record_html(record_id: str, profit: str, legs: str) -> str:
    return f"""
    <tbody class="surebet_record" data-testid="surebet-record" data-id="{record_id}"
           data-signature="sig-{record_id}" data-profit="{profit}" data-created-at="2026-06-23T10:00:00Z"
           data-start-at="2026-06-23T14:00:00Z" data-roi="{profit}">
      <tr><td><span data-testid="surebet-profit" class="profit">{profit}%</span></td></tr>
      {legs}
    </tbody>
    """


def _realistic_surebet_records_fixture(*, include_restricted: bool = True, include_masked: bool = True) -> str:
    valid_a = _record_html(
        "101",
        "16.24",
        _leg_html("Betsson (ES)", "Futebol", "23/06 England - Ghana", "Jogos Internacionais", "Acima 0.5 gols", "1.78")
        + _leg_html("Mystake", "Futebol", "23/06 England - Ghana", "Jogos Internacionais", "Abaixo 0.5 gols", "3.35"),
    )
    valid_b = _record_html(
        "102",
        "11.6",
        _leg_html("AlfaBet (BR)", "Futebol", "23/06 Spain - France", "Euro", "Casa vence", "1.58")
        + _leg_html("Stake", "Futebol", "23/06 Spain - France", "Euro", "Fora vence", "3.80"),
    )
    masked = _record_html(
        "103",
        "9.0",
        _leg_html("XXX", "Futebol", "23/06 A - B", "Liga", "XXX", "XXX")
        + _leg_html("Novibet", "Futebol", "23/06 A - B", "Liga", "Fora", "2.10"),
    )
    restricted = _record_html(
        "104",
        "8.0",
        _leg_html("Bet365", "Futebol", "23/06 C - D", "Liga", "Casa", "2.20")
        + _leg_html("Superbet", "Futebol", "23/06 C - D", "Liga", "Fora", "1.90"),
    )
    records = valid_a + valid_b
    if include_masked:
        records += masked
    if include_restricted:
        records += restricted
    return f"<html><body><table>{records}</table></body></html>"


def _single_realistic_surebet_record_fixture(profit: str = "16.24") -> str:
    return (
        "<html><body><table>"
        + _record_html(
            "101",
            profit,
            _leg_html("Betsson (ES)", "Futebol", "23/06 England - Ghana", "Jogos Internacionais", "Acima 0.5 gols", "1.78")
            + _leg_html("Mystake", "Futebol", "23/06 England - Ghana", "Jogos Internacionais", "Abaixo 0.5 gols", "3.35"),
        )
        + "</table></body></html>"
    )


if __name__ == "__main__":
    unittest.main()
