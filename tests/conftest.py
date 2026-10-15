from __future__ import annotations

from pathlib import Path

import pytest

from hirelane.config import HOME_ENV, Paths


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Paths:
    """An empty hirelane home directory, isolated per test."""
    monkeypatch.setenv(HOME_ENV, str(tmp_path / "home"))
    monkeypatch.delenv("HIRELANE_ALLOW_LIVE", raising=False)
    return Paths(tmp_path / "home").ensure()


FORMS = Path(__file__).parent / "fixtures" / "forms"


@pytest.fixture(scope="session")
def browser():
    """A local Chromium for tests marked `browser`. Skips when Playwright or its browser is not installed."""
    import os

    local = Path(__file__).resolve().parent.parent / ".build" / "browsers"
    if local.exists() and "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(local)
    sync_api = pytest.importorskip("playwright.sync_api")
    pw = sync_api.sync_playwright().start()
    try:
        b = pw.chromium.launch(headless=True)
    except Exception as e:  # the browser binary is missing
        pw.stop()
        pytest.skip(f"chromium not available: {str(e).splitlines()[0]}")
    yield b
    b.close()
    pw.stop()


@pytest.fixture
def form_page(browser):
    page = browser.new_page()
    page.goto((FORMS / "application.html").as_uri())
    yield page
    page.close()


class MemoryKeyring:
    """A keyring backend that keeps secrets in a dict, so tests never touch the real keyring."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> MemoryKeyring:
    import keyring
    from keyring.errors import PasswordDeleteError

    mem = MemoryKeyring()
    monkeypatch.setattr(keyring, "get_password", lambda s, n: mem.store.get((s, n)))
    monkeypatch.setattr(keyring, "set_password", lambda s, n, v: mem.store.__setitem__((s, n), v))

    def delete(service: str, name: str) -> None:
        if (service, name) not in mem.store:
            raise PasswordDeleteError("not found")
        del mem.store[(service, name)]

    monkeypatch.setattr(keyring, "delete_password", delete)
    return mem
