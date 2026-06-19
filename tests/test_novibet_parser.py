from __future__ import annotations

import unittest

from bookmakers.novibet.novibet_parser import NovibetParser


class NovibetParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = NovibetParser()

    def test_extracts_simple_event_and_odds_from_fixture_html(self) -> None:
        html = """
        <section data-novibet-event data-sport="Futebol" data-league="Brasil Serie B"
                 data-event="Team A x Team B" data-start="2026-06-20T19:00:00Z">
          <div data-novibet-market data-market="Resultado Final">
            <button data-selection="Team A" data-odds="2.10">Team A 2.10</button>
            <button data-selection="Empate" data-odds="3.20">Empate 3.20</button>
            <button data-selection="Team B" data-odds="3.60">Team B 3.60</button>
          </div>
        </section>
        """

        result = self.parser.parse_html(html, source_url="https://www.novibet.bet.br/sports", scraped_at="2026-06-19T12:00:00Z")

        self.assertEqual(result.raw_events_count, 1)
        self.assertEqual(len(result.normalized_odds), 3)
        first = result.normalized_odds[0]
        self.assertEqual(first.bookmaker, "novibet")
        self.assertEqual(first.sport, "Futebol")
        self.assertEqual(first.league, "Brasil Serie B")
        self.assertEqual(first.event_name, "Team A x Team B")
        self.assertEqual(first.start_time, "2026-06-20T19:00:00Z")
        self.assertEqual(first.market_type, "Match Odds")
        self.assertEqual(first.selection, "Team A")
        self.assertEqual(first.odds, 2.10)
        self.assertEqual(first.source_url, "https://www.novibet.bet.br/sports")

    def test_ignores_incomplete_odds(self) -> None:
        html = """
        <section data-novibet-event data-sport="Futebol" data-league="Liga"
                 data-event="Team A x Team B">
          <div data-novibet-market data-market="Resultado Final">
            <button data-selection="Team A"></button>
            <button data-odds="2.10"></button>
            <button data-selection="Team B" data-odds="bad"></button>
          </div>
        </section>
        """

        result = self.parser.parse_html(html, source_url="https://example.test", scraped_at="2026-06-19T12:00:00Z")

        self.assertEqual(result.raw_events_count, 1)
        self.assertEqual(result.normalized_odds, [])

    def test_does_not_generate_betting_actions(self) -> None:
        html = """
        <section data-novibet-event data-sport="Futebol" data-league="Liga"
                 data-event="Team A x Team B">
          <div data-novibet-market data-market="Resultado Final">
            <button data-selection="Team A" data-odds="2.10">Adicionar ao cupom</button>
          </div>
        </section>
        """

        result = self.parser.parse_html(html, source_url="https://example.test", scraped_at="2026-06-19T12:00:00Z")

        self.assertEqual(len(result.normalized_odds), 1)
        self.assertFalse(any("click" in item for item in result.actions))
        self.assertFalse(any("stake" in item for item in result.actions))
        self.assertFalse(any("order" in item for item in result.actions))

    def test_normalizes_common_market_types(self) -> None:
        self.assertEqual(self.parser.normalize_market_type("Resultado Final"), "Match Odds")
        self.assertEqual(self.parser.normalize_market_type("Total de Gols Mais/Menos 2.5"), "Over/Under")
        self.assertEqual(self.parser.normalize_market_type("Handicap Asiatico"), "Handicap")
        self.assertEqual(self.parser.normalize_market_type("Mercado Especial"), "Mercado Especial")


if __name__ == "__main__":
    unittest.main()
