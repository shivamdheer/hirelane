from __future__ import annotations

from typing import Any

import httpx
import pytest

from hirelane.sources import ashby, greenhouse, lever
from hirelane.sources.base import HttpClient, pay_from_text, to_date
from tests.helpers import run_async

GREENHOUSE_BOARD: dict[str, Any] = {"jobs": [
    {"id": 4001, "title": " Associate Data Analyst ", "company_name": "Fabrikam",
     "absolute_url": "https://boards.example.com/fabrikam/jobs/4001?gh_src=abc",
     "location": {"name": "Remote - US"}, "first_published": "2026-03-01T15:00:00-05:00",
     "content": "&lt;p&gt;Work with SQL.&lt;/p&gt;&lt;p&gt;Pay: $90,000 - $110,000&lt;/p&gt;",
     "departments": [{"name": "Analytics"}]},
    {"id": 4002, "title": "Support Engineer", "location": {"name": ""},
     "offices": [{"name": "Austin", "location": "Austin, TX"}], "updated_at": "2026-02-27T10:00:00Z", "content": ""},
    {"title": "No id"},
]}

LEVER_BOARD: list[dict[str, Any]] = [
    {"id": "aa-11", "text": "Junior Analyst", "hostedUrl": "https://jobs.example.com/contoso/aa-11?lever-source=x",
     "applyUrl": "https://jobs.example.com/contoso/aa-11/apply", "createdAt": 1772400000000,
     "categories": {"location": "Chicago, IL", "team": "Data", "commitment": "Full-time"},
     "workplaceType": "remote", "country": "US", "descriptionPlain": "Analyze things.",
     "lists": [{"text": "Requirements", "content": "<li>SQL</li>"}],
     "salaryRange": {"min": 80000, "max": 95000, "interval": "per-year-salary"}},
]

ASHBY_BOARD: dict[str, Any] = {"jobs": [
    {"id": "e1", "title": "Operations Analyst", "location": "New York, NY",
     "secondaryLocations": [{"location": "Remote"}], "isRemote": False, "isListed": True,
     "publishedAt": "2026-03-02T14:00:00.000+00:00", "jobUrl": "https://jobs.example.com/adatum/e1",
     "descriptionPlain": "Run the numbers. $70K - $85K", "employmentType": "FullTime",
     "compensation": {"scrapeableCompensationSalarySummary": "$70K - $85K"}},
    {"id": "e2", "title": "Hidden", "isListed": False},
]}


def test_greenhouse_parse() -> None:
    posts = greenhouse.parse(GREENHOUSE_BOARD, "fabrikam", "Fabrikam")
    assert [p.job_id for p in posts] == ["4001", "4002"]
    first = posts[0]
    assert first.title == "Associate Data Analyst"
    assert first.url == "https://boards.example.com/fabrikam/jobs/4001"
    assert first.apply_url == "https://job-boards.greenhouse.io/fabrikam/jobs/4001"
    assert first.remote
    assert first.description == ""
    first.materialize()
    assert "Work with SQL." in first.description
    assert first.pay == "$90,000 - $110,000"
    assert posts[1].location == "Austin, TX"


def test_lever_parse() -> None:
    (p,) = lever.parse(LEVER_BOARD, "contoso", "Contoso")
    assert p.remote
    assert p.pay == "$80,000-$95,000"
    assert p.url == "https://jobs.example.com/contoso/aa-11"
    p.materialize()
    assert "Analyze things." in p.description and "- SQL" in p.description


def test_ashby_parse_skips_unlisted() -> None:
    (p,) = ashby.parse(ASHBY_BOARD, "adatum", "Adatum")
    assert p.location == "New York, NY / Remote"
    assert p.pay == "$70K - $85K"
    assert p.apply_url.endswith("/e1/application")


def test_to_date_handles_epoch_iso_and_junk() -> None:
    from zoneinfo import ZoneInfo
    utc = ZoneInfo("UTC")
    assert to_date("2026-03-01T23:30:00-05:00", utc) == "2026-03-02"
    assert to_date(1772400000000, utc) == "2026-03-01"
    assert to_date("not a date", utc) == ""
    assert to_date(None, utc) == ""


def test_pay_from_text() -> None:
    assert pay_from_text("Range: $120K to $150K a year") == "$120K to $150K"
    assert pay_from_text("no pay here") == ""


def _client(handler: Any) -> HttpClient:
    return HttpClient(transport=httpx.MockTransport(handler), retry_sleep_s=0)


def test_fetch_retries_once_on_server_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, json=GREENHOUSE_BOARD)

    async def run() -> None:
        async with _client(handler) as c:
            result, posts = await greenhouse.fetch(c, "fabrikam", "Fabrikam")
            assert result.ok and len(posts) == 2

    run_async(run())
    assert calls["n"] == 2


def test_fetch_reports_404_without_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    async def run() -> None:
        async with _client(handler) as c:
            result, posts = await lever.fetch(c, "gone", "Gone")
            assert result.status == 404 and posts == []

    run_async(run())
    assert calls["n"] == 1


@pytest.mark.parametrize("status,expected", [(200, True), (404, False), (500, None)])
def test_is_open(status: int, expected: bool | None) -> None:
    async def run() -> bool | None:
        async with _client(lambda r: httpx.Response(status, json={})) as c:
            return await greenhouse.is_open(c, "fabrikam", "4001")

    assert run_async(run()) is expected


def test_ashby_is_open_checks_the_board_listing() -> None:
    async def run(job_id: str) -> bool | None:
        async with _client(lambda r: httpx.Response(200, json=ASHBY_BOARD)) as c:
            return await ashby.is_open(c, "adatum", job_id)

    assert run_async(run("e1")) is True
    assert run_async(run("e2")) is False


def test_lever_posting_without_dates_parses_with_an_empty_posted_date() -> None:
    board = [{"id": "zz-1", "text": "Analyst", "categories": {"location": "Austin, TX"}}]
    (p,) = lever.parse(board, "contoso", "Contoso")
    assert p.posted == ""


def test_lever_falls_back_to_the_updated_date() -> None:
    board = [{"id": "zz-2", "text": "Analyst", "updatedAt": 1772400000000, "categories": {}}]
    (p,) = lever.parse(board, "contoso", "Contoso")
    assert p.posted == to_date(1772400000000)


@pytest.mark.parametrize("payload", [[], "oops", {"jobs": "nope"}, {"jobs": [1, "x", None]}, {"jobs": None}, None])
def test_board_parsers_survive_malformed_payloads(payload: Any) -> None:
    assert greenhouse.parse(payload, "fabrikam", "Fabrikam") == []
    assert ashby.parse(payload, "fabrikam", "Fabrikam") == []


def test_ashby_is_open_with_a_malformed_board_is_unknown() -> None:
    async def run() -> bool | None:
        async with _client(lambda request: httpx.Response(200, json=["not", "a", "board"])) as c:
            return await ashby.is_open(c, "fabrikam", "1")

    assert run_async(run()) is None


def test_a_non_json_body_is_reported_not_raised() -> None:
    async def run() -> None:
        async with _client(lambda request: httpx.Response(200, text="<html>maintenance</html>")) as c:
            result = await c.get_json("https://example.com/board")
            assert not result.ok and result.error == "not JSON"

    run_async(run())


def test_a_numeric_retry_after_is_honored_once_and_capped() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}) if calls["n"] == 1 else httpx.Response(200, json={})

    async def run() -> None:
        async with _client(handler) as c:
            assert (await c.get_json("https://example.com/board")).status == 200

    run_async(run())
    assert calls["n"] == 2
