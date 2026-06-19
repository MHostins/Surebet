"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class ExchangeCommission:
    betfair: float = field(default_factory=lambda: _float_env("BETFAIR_COMMISSION", 0.05))
    matchbook: float = field(default_factory=lambda: _float_env("MATCHBOOK_COMMISSION", 0.02))
    matchbook_br: float = field(default_factory=lambda: _float_env("MATCHBOOK_BR_COMMISSION", 0.02))


@dataclass(frozen=True)
class Settings:
    betfair_username: str | None = field(default_factory=lambda: os.getenv("BETFAIR_USERNAME"))
    betfair_password: str | None = field(default_factory=lambda: os.getenv("BETFAIR_PASSWORD"))
    betfair_app_key: str | None = field(default_factory=lambda: os.getenv("BETFAIR_APP_KEY"))
    betfair_cert_path: str | None = field(default_factory=lambda: os.getenv("BETFAIR_CERT_PATH"))
    betfair_cert_file: str | None = field(
        default_factory=lambda: os.getenv("BETFAIR_CERT_FILE", r"C:\Projetos\API-Betfair\certs\client.crt")
    )
    betfair_key_file: str | None = field(
        default_factory=lambda: os.getenv("BETFAIR_KEY_FILE", r"C:\Projetos\API-Betfair\certs\client.key")
    )
    betfair_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "BETFAIR_API_BASE_URL",
            "https://api.betfair.bet.br/exchange/betting/rest/v1.0",
        )
    )
    betfair_cert_login_url: str = field(
        default_factory=lambda: os.getenv(
            "BETFAIR_CERT_LOGIN_URL",
            "https://identitysso-cert.betfair.bet.br/api/certlogin",
        )
    )

    matchbook_username: str | None = field(default_factory=lambda: os.getenv("MATCHBOOK_USERNAME"))
    matchbook_password: str | None = field(default_factory=lambda: os.getenv("MATCHBOOK_PASSWORD"))
    matchbook_api_base_url: str = field(
        default_factory=lambda: os.getenv("MATCHBOOK_API_BASE_URL", "https://api.matchbook.com")
    )
    matchbook_br_api_base_url: str = field(
        default_factory=lambda: os.getenv("MATCHBOOK_BR_API_BASE_URL", "https://mexchange-api.matchbook.bet.br")
    )
    matchbook_br_cookie: str | None = field(default_factory=lambda: os.getenv("MATCHBOOK_BR_COOKIE"))

    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "outputs")))
    stake_total: float = field(default_factory=lambda: _float_env("STAKE_TOTAL", 100.0))
    min_margin: float = field(default_factory=lambda: _float_env("MIN_ARBITRAGE_MARGIN", 0.01))
    max_start_time_delta_minutes: int = field(
        default_factory=lambda: _int_env("MAX_START_TIME_DELTA_MINUTES", 90)
    )
    min_event_match_confidence: float = field(
        default_factory=lambda: _float_env("MIN_EVENT_MATCH_CONFIDENCE", 0.85)
    )
    min_odds_difference_percent: float = field(
        default_factory=lambda: _float_env("MIN_ODDS_DIFFERENCE_PERCENT", 5.0)
    )
    min_liquidity_betfair: float = field(
        default_factory=lambda: _float_env("MIN_LIQUIDITY_BETFAIR", 50.0)
    )
    min_liquidity_matchbook_br: float = field(
        default_factory=lambda: _float_env("MIN_LIQUIDITY_MATCHBOOK_BR", 50.0)
    )
    team_aliases_path: Path = field(
        default_factory=lambda: Path(os.getenv("TEAM_ALIASES_PATH", "config/team_aliases.json"))
    )
    request_timeout: int = field(default_factory=lambda: _int_env("REQUEST_TIMEOUT", 20))
    watch_interval_seconds: int = field(default_factory=lambda: _int_env("WATCH_INTERVAL_SECONDS", 300))
    watch_max_cycles: int = field(default_factory=lambda: _int_env("WATCH_MAX_CYCLES", 0))
    watch_moneyline_interval_seconds: int = field(default_factory=lambda: _int_env("WATCH_MONEYLINE_INTERVAL_SECONDS", 300))
    watch_moneyline_max_cycles: int = field(default_factory=lambda: _int_env("WATCH_MONEYLINE_MAX_CYCLES", 0))
    watch_multi_bookmaker_interval_seconds: int = field(default_factory=lambda: _int_env("WATCH_MULTI_BOOKMAKER_INTERVAL_SECONDS", 300))
    watch_multi_bookmaker_max_cycles: int = field(default_factory=lambda: _int_env("WATCH_MULTI_BOOKMAKER_MAX_CYCLES", 0))
    the_odds_api_key: str | None = field(default_factory=lambda: os.getenv("THE_ODDS_API_KEY"))
    the_odds_api_base_url: str = field(
        default_factory=lambda: os.getenv("THE_ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4")
    )
    the_odds_api_regions: str = field(
        default_factory=lambda: os.getenv("THE_ODDS_API_REGIONS", "eu")
    )
    the_odds_api_bookmakers: str = field(
        default_factory=lambda: os.getenv("THE_ODDS_API_BOOKMAKERS", "pinnacle,betano,sportingbet,novibet,bet365")
    )
    the_odds_api_sports: str = field(
        default_factory=lambda: os.getenv(
            "THE_ODDS_API_SPORTS",
            "mma_mixed_martial_arts,baseball_mlb,basketball_wnba,soccer_brazil_serie_b,soccer_fifa_world_cup,tennis_atp_halle_open,tennis_atp_queens_club_champ,tennis_wta_german_open"
        )
    )
    odds_history_db_path: str = field(
        default_factory=lambda: os.getenv("ODDS_HISTORY_DB_PATH", "outputs/odds_history.db")
    )
    novibet_public_url: str = field(
        default_factory=lambda: os.getenv("NOVIBET_PUBLIC_URL", "https://www.novibet.bet.br/apostas-esportivas")
    )
    novibet_headless: bool = field(default_factory=lambda: _bool_env("NOVIBET_HEADLESS", True))
    novibet_navigation_timeout_ms: int = field(
        default_factory=lambda: _int_env("NOVIBET_NAVIGATION_TIMEOUT_MS", 30000)
    )
    novibet_post_load_wait_ms: int = field(
        default_factory=lambda: _int_env("NOVIBET_POST_LOAD_WAIT_MS", 3000)
    )
    commissions: ExchangeCommission = field(default_factory=ExchangeCommission)


settings = Settings()



