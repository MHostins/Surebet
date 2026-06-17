"""Service to persist odds data to a local SQLite database for historical analysis."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import Settings

LOGGER = logging.getLogger(__name__)


class OddsHistoryService:
    """Manages SQLite storage for odds, event details, and metadata."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = Path(self.settings.odds_history_db_path)
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Create database directory and table if they do not exist."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS odds_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        collected_at TEXT NOT NULL,
                        event_start_time TEXT NOT NULL,
                        event_name TEXT NOT NULL,
                        sport TEXT NOT NULL,
                        market_type TEXT NOT NULL,
                        selection TEXT NOT NULL,
                        side TEXT NOT NULL,
                        odds REAL NOT NULL,
                        available_liquidity REAL,
                        source_type TEXT NOT NULL,
                        source_provider TEXT NOT NULL,
                        bookmaker TEXT NOT NULL,
                        event_id TEXT
                    )
                    """
                )
                # Auto-migration: check if event_id column exists, if not, add it
                cursor.execute("PRAGMA table_info(odds_history)")
                columns = [col[1] for col in cursor.fetchall()]
                if "event_id" not in columns:
                    LOGGER.info("Column 'event_id' not found in odds_history table. Migrating database...")
                    cursor.execute("ALTER TABLE odds_history ADD COLUMN event_id TEXT")
                    LOGGER.info("Column 'event_id' added to odds_history table successfully.")
                conn.commit()
            LOGGER.info("Odds history database initialized at %s", self.db_path)
        except Exception as exc:
            LOGGER.error("Failed to initialize database: %s", exc)

    def log_odds(
        self,
        rows: list[dict[str, Any]],
        source_type: str,
        source_provider: str,
    ) -> int:
        """Insert a batch of normalized odds into the database in a single transaction."""
        if not rows:
            return 0

        collected_at = datetime.now(timezone.utc).isoformat()
        insert_data: list[tuple[Any, ...]] = []

        for row in rows:
            # Map columns cleanly
            event_id = row.get("event_id") or ""
            event_start_time = row.get("start_time") or row.get("event_start_time") or ""
            # Format time if string
            if isinstance(event_start_time, datetime):
                event_start_time = event_start_time.isoformat()

            event_name = row.get("event_name") or ""
            sport = row.get("sport") or ""
            market_type = row.get("market_type") or ""
            selection = row.get("selection") or ""
            side = row.get("side") or "back"
            odds = row.get("odds") or 0.0
            available_liquidity = row.get("available_liquidity")

            # Bookmaker name defaults to row's bookmaker or source_provider
            bookmaker = row.get("bookmaker") or source_provider

            insert_data.append((
                collected_at,
                event_start_time,
                event_name,
                sport,
                market_type,
                selection,
                side,
                float(odds),
                float(available_liquidity) if available_liquidity is not None else None,
                source_type,
                source_provider,
                bookmaker,
                str(event_id),
            ))

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT INTO odds_history (
                        collected_at,
                        event_start_time,
                        event_name,
                        sport,
                        market_type,
                        selection,
                        side,
                        odds,
                        available_liquidity,
                        source_type,
                        source_provider,
                        bookmaker,
                        event_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    insert_data,
                )
                conn.commit()
            LOGGER.info("Logged %d odds rows to history database", len(insert_data))
            return len(insert_data)
        except Exception as exc:
            LOGGER.error("Failed to log odds rows to database: %s", exc)
            return 0
