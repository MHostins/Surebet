from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.bookmaker_intelligence_service import BookmakerIntelligenceService, classify_market_family


class BookmakerIntelligenceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.discovery_db = self.root / "bookmaker_discovery" / "bookmaker_discovery.db"
        self.output_dir = self.root / "bookmaker_intelligence"

    def create_db(self) -> None:
        self.discovery_db.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.discovery_db)
        try:
            connection.execute(
                """
                create table observations (
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
            rows = [
                ("k1", "2026-06-24T10:00:00+00:00", "2026-06-24T12:00:00+00:00", 10.0, "Futebol", "A x B", "Acima 2.5 gols / Abaixo 2.5 gols", "Betsson (ES)", "Mystake", "Betsson (ES) x Mystake", 3),
                ("k2", "2026-06-24T11:00:00+00:00", "2026-06-24T11:30:00+00:00", 6.0, "Futebol", "C x D", "Handicap -1.5 / Handicap +1.5", "Betsson (ES)", "Stake", "Betsson (ES) x Stake", 2),
                ("k3", "2026-06-24T13:00:00+00:00", "2026-06-24T15:00:00+00:00", 14.0, "Tenis", "E x F", "Vencedor da partida / Vencedor da partida", "Stake", "Mystake", "Mystake x Stake", 5),
            ]
            for stable_key, first_seen, last_seen, profit, sport, event_name, market, bookmaker_1, bookmaker_2, pair, seen_count in rows:
                connection.execute(
                    """
                    insert into observations (
                        stable_key, dedupe_key, first_seen_at, last_seen_at, profit_percent,
                        sport, event_name, market, bookmaker_1, bookmaker_2, bookmaker_pair,
                        odds_json, opportunity_url, opportunity_id, seen_count
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, null, ?, ?)
                    """,
                    (
                        stable_key,
                        stable_key,
                        first_seen,
                        last_seen,
                        profit,
                        sport,
                        event_name,
                        market,
                        bookmaker_1,
                        bookmaker_2,
                        pair,
                        "[2.0, 2.1]",
                        stable_key,
                        seen_count,
                    ),
                )
            connection.commit()
        finally:
            connection.close()

    def test_classifies_market_family(self) -> None:
        self.assertEqual(classify_market_family("Acima 2.5 gols / Abaixo 2.5 gols"), "over_under")
        self.assertEqual(classify_market_family("Handicap Asiatico -1.5"), "handicap")
        self.assertEqual(classify_market_family("Empate anula aposta"), "dnb")
        self.assertEqual(classify_market_family("Vencedor da partida"), "match_winner")
        self.assertEqual(classify_market_family("Jogador marca gol"), "player_props")
        self.assertEqual(classify_market_family("Total de games"), "sets_games")
        self.assertEqual(classify_market_family("Cartoes"), "corners_throwins_cards")
        self.assertEqual(classify_market_family("Mercado Especial"), "other")

    def test_generates_intelligence_reports(self) -> None:
        self.create_db()

        report = BookmakerIntelligenceService(self.discovery_db, self.output_dir).generate()

        self.assertEqual(report["summary"]["total_observations"], 3)
        self.assertEqual(report["summary"]["total_bookmakers"], 3)
        self.assertTrue(report["bookmaker_by_sport"])
        self.assertTrue(report["bookmaker_by_market"])
        self.assertTrue(report["bookmaker_by_hour"])
        self.assertTrue(report["bookmaker_pair_strength"])
        self.assertTrue(report["bookmaker_consistency"])
        self.assertIn("Copa do Mundo", report["context_notes"]["sports_context"])
        self.assertTrue((self.output_dir / "bookmaker_intelligence_report.json").exists())
        self.assertTrue((self.output_dir / "bookmaker_by_sport.csv").exists())
        self.assertTrue((self.output_dir / "bookmaker_context_notes.json").exists())

    def test_pair_strength_uses_seen_count_for_persistence_score(self) -> None:
        self.create_db()

        report = BookmakerIntelligenceService(self.discovery_db, self.output_dir).generate()

        pair = next(row for row in report["bookmaker_pair_strength"] if row["bookmaker_pair"] == "Mystake x Stake")
        self.assertEqual(pair["appearances"], 5)
        self.assertEqual(pair["unique_opportunities"], 1)
        self.assertGreater(pair["persistence_score"], 1.0)

    def test_empty_database_generates_empty_reports(self) -> None:
        report = BookmakerIntelligenceService(self.discovery_db, self.output_dir).generate()

        self.assertEqual(report["summary"]["total_observations"], 0)
        self.assertEqual(report["bookmaker_by_sport"], [])
        self.assertEqual(report["bookmaker_consistency"], [])
        self.assertTrue((self.output_dir / "bookmaker_intelligence_report.json").exists())


if __name__ == "__main__":
    unittest.main()
