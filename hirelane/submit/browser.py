"""Browser session. A dedicated profile directory keeps the user's own logins out of reach of the filler."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 1600
LOCALE = "en-US"
NAV_TIMEOUT_MS = 45_000


class BrowserUnavailable(RuntimeError):
    pass


@contextmanager
def open_context(profile_dir: Path, headless: bool = True) -> Iterator[Any]:
    """Yield a Playwright browser context with a persistent profile that belongs to hirelane alone."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise BrowserUnavailable("install the browser extra: pip install 'hirelane[browser]'") from e
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            context = pw.chromium.launch_persistent_context(
                str(profile_dir), headless=headless, locale=LOCALE, accept_downloads=False,
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
        except Exception as e:
            raise BrowserUnavailable(f"could not start Chromium, run `playwright install chromium`: {e}") from e
        context.set_default_navigation_timeout(NAV_TIMEOUT_MS)
        try:
            yield context
        finally:
            context.close()
