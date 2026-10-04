"""Bounded Chromium fallback for pages whose content is JavaScript rendered."""

import logging
import re
import time

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.config import settings
from app.services.network import _rate_key, wait_for_rate_slot

logger = logging.getLogger(__name__)


def needs_browser(html: str, extracted_text: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    app_root = soup.find(id=re.compile(r"^(root|app)$", re.IGNORECASE))
    return len(extracted_text) < 1000 and len(soup.find_all("script")) >= 2 and (
        app_root is not None or len(extracted_text) < 200
    )


def render_page(url: str, user_agent: str) -> tuple[str, str]:
    wait_for_rate_slot(_rate_key(url), settings.website_min_interval_seconds)
    started = time.monotonic()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=user_agent)
            response = page.goto(
                url, wait_until="domcontentloaded", timeout=settings.browser_timeout_ms,
            )
            if response is not None and response.status >= 400:
                raise RuntimeError(f"Browser request failed with HTTP {response.status}")
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except PlaywrightTimeoutError:
                pass
            result = page.url, page.content()
        finally:
            browser.close()
    logger.info("Browser fallback completed", extra={
        "event": "browser_fetch", "url": result[0],
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
    })
    return result
