from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hirelane import secrets
from hirelane.config import Paths
from hirelane.web import security
from hirelane.web.app import create_app


@pytest.fixture
def client(home: Paths) -> TestClient:
    return TestClient(create_app(home), follow_redirects=False)


def test_health_is_open_and_headers_are_set(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["Cache-Control"] == "no-store"


def test_no_token_means_open_on_loopback(client: TestClient) -> None:
    assert client.get("/login").status_code == 200


def test_with_a_token_pages_redirect_until_login(home: Paths) -> None:
    secrets.set_secret(secrets.WEB_TOKEN, "correct horse")
    c = TestClient(create_app(home), follow_redirects=False)
    assert c.get("/healthz").status_code == 200
    assert c.get("/static/style.css").status_code == 200
    r = c.get("/some-page")
    assert r.status_code == 303 and r.headers["location"] == "/login"
    bad = c.post("/login", data={"token": "wrong"})
    assert bad.status_code == 401
    ok = c.post("/login", data={"token": "correct horse"})
    assert ok.status_code == 303 and security.COOKIE in ok.cookies
    assert "httponly" in ok.headers["set-cookie"].lower() and "samesite=strict" in ok.headers["set-cookie"].lower()
    assert c.get("/some-page").status_code == 404          # signed in now, the page just does not exist


def test_tampered_or_foreign_cookies_are_rejected(home: Paths) -> None:
    secrets.set_secret(secrets.WEB_TOKEN, "one")
    cookie = security.issue_cookie()
    secrets.set_secret(secrets.WEB_TOKEN, "two")
    assert not security.cookie_valid(cookie)
    assert not security.cookie_valid("garbage")
    assert not security.cookie_valid(None)


def test_cross_site_posts_are_refused(client: TestClient) -> None:
    r = client.post("/login", data={"token": "x"}, headers={"origin": "https://evil.example.com", "host": "testserver"})
    assert r.status_code == 403


@pytest.mark.parametrize("host,loopback", [("127.0.0.1", True), ("::1", True), ("localhost", True),
                                           ("0.0.0.0", False), ("192.168.1.5", False)])
def test_is_loopback(host: str, loopback: bool) -> None:
    assert security.is_loopback(host) is loopback


def test_binding_beyond_loopback_needs_a_token(home: Paths) -> None:
    security.check_bind("127.0.0.1")
    with pytest.raises(RuntimeError, match="set-key web-token"):
        security.check_bind("0.0.0.0")
    secrets.set_secret(secrets.WEB_TOKEN, "t")
    security.check_bind("0.0.0.0")


@pytest.mark.parametrize("origin,host,expected", [
    (None, "127.0.0.1:8000", True),
    ("http://127.0.0.1:8000", "127.0.0.1:8000", True),
    ("http://evil.example", "127.0.0.1:8000", False),
    ("http://127.0.0.1:8000.evil.example", "127.0.0.1:8000", False),
    ("http://127.0.0.1:8000", None, False),
])
def test_same_origin(origin: str | None, host: str | None, expected: bool) -> None:
    assert security.same_origin(origin, host) is expected
