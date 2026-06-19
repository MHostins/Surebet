"""Read-only Playwright client for public Novibet inspection."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bookmakers.novibet.novibet_parser import NovibetParser
from config.settings import Settings

LOGGER = logging.getLogger(__name__)


class NovibetClient:
    """Opens public Novibet pages and extracts visible/catalog data without betting actions."""

    BETTING_ACTION_SELECTORS = (
        "[data-testid*='betslip' i]",
        "[class*='betslip' i]",
        "[id*='betslip' i]",
        "[class*='coupon' i]",
        "[id*='coupon' i]",
        "[class*='cupom' i]",
        "[id*='cupom' i]",
        "input[name*='stake' i]",
        "button:has-text('Apostar')",
        "button:has-text('Fazer aposta')",
        "button:has-text('Place bet')",
    )

    def __init__(self, settings: Settings, parser: NovibetParser | None = None) -> None:
        self.settings = settings
        self.parser = parser or NovibetParser()
        self.errors: list[str] = []

    def inspect_public_page(self) -> dict[str, Any]:
        scraped_at = datetime.now(timezone.utc).isoformat()
        report: dict[str, Any] = {
            "timestamp": scraped_at,
            "status": "started",
            "mode": "read_only_public_inspection",
            "target_url": self.settings.novibet_public_url,
            "final_url": None,
            "page_title": None,
            "playwright_available": False,
            "browser_started": False,
            "login_used": False,
            "cookies_saved": False,
            "betting_actions_performed": False,
            "blocked_action_selectors": list(self.BETTING_ACTION_SELECTORS),
            "blocked_action_selectors_detected": 0,
            "raw_events_count": 0,
            "normalized_odds_count": 0,
            "parser_warnings": [],
            "errors": self.errors,
            "raw_sample": {},
            "normalized_odds": [],
        }

        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            self._record_error(f"Playwright is not available: {exc}")
            report["status"] = "playwright_unavailable"
            return report

        report["playwright_available"] = True

        try:
            with sync_playwright() as playwright:
                browser = None
                context = None
                try:
                    browser = playwright.chromium.launch(headless=self.settings.novibet_headless)
                    report["browser_started"] = True
                    context = browser.new_context(
                        locale="pt-BR",
                        viewport={"width": 1365, "height": 900},
                    )
                    page = context.new_page()
                    page.goto(
                        self.settings.novibet_public_url,
                        wait_until="domcontentloaded",
                        timeout=self.settings.novibet_navigation_timeout_ms,
                    )
                    page.wait_for_timeout(self.settings.novibet_post_load_wait_ms)

                    html = page.content()
                    visible_text = self._safe_body_text(page)
                    parsed = self.parser.parse_html(
                        html,
                        source_url=page.url,
                        scraped_at=scraped_at,
                    )

                    report.update(
                        {
                            "status": "success",
                            "final_url": page.url,
                            "page_title": page.title(),
                            "blocked_action_selectors_detected": self._count_betting_action_selectors(page),
                            "raw_events_count": parsed.raw_events_count,
                            "normalized_odds_count": len(parsed.normalized_odds),
                            "parser_warnings": parsed.warnings[:50],
                            "raw_sample": {
                                "visible_text_prefix": visible_text[:5000],
                                "parser_raw_events": parsed.raw_events[:10],
                            },
                            "normalized_odds": parsed.normalized_dicts(),
                        }
                    )
                finally:
                    if context is not None:
                        context.close()
                    if browser is not None:
                        browser.close()
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            self._record_error(f"Playwright navigation/inspection error: {exc}")
            report["status"] = "playwright_error"
        except Exception as exc:
            self._record_error(f"Unexpected Novibet inspection error: {exc}")
            report["status"] = "error"

        report["errors"] = self.errors
        return report

    def _safe_body_text(self, page: Any) -> str:
        try:
            return page.locator("body").inner_text(timeout=3000)
        except Exception:
            return ""

    def _count_betting_action_selectors(self, page: Any) -> int:
        detected = 0
        for selector in self.BETTING_ACTION_SELECTORS:
            try:
                detected += page.locator(selector).count()
            except Exception:
                continue
        return detected

    def _record_error(self, message: str) -> None:
        self.errors.append(message)
        LOGGER.error("Novibet: %s", message)
