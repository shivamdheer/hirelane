from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from hirelane import sourcing
from hirelane.companies import Company
from hirelane.config import Settings
from hirelane.db import DB
from hirelane.facts import load_bank
from hirelane.profile import parse_profile
from hirelane.sources.base import HttpClient
from tests.bank_fixture import write_bank
from tests.helpers import run_async
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)
TODAY = date(2026, 3, 10)
NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def gh_job(job_id: int, title: str, location: str = "Chicago, IL", content: str = "SQL and Tableau.",
           published: str = "2026-03-09T12:00:00Z") -> dict[str, Any]:
    return {"id": job_id, "title": title, "location": {"name": location}, "first_published": published,
            "content": content, "absolute_url": f"https://example.com/{job_id}"}


BOARDS: dict[str, dict[str, Any]] = {
    "fabrikam": {"jobs": [
        gh_job(1, "Data Analyst", content="SQL, Python, Tableau, pandas and Excel for stakeholders."),
        gh_job(2, "Senior Data Analyst"),
        gh_job(3, "Data Analyst II", content="SQL"),
        gh_job(4, "Business Analyst", content="Needs 6 years of experience."),
        gh_job(5, "Pastry Chef"),
        gh_job(6, "Analytics Engineer", location="Toronto, Canada"),
        gh_job(7, "Data Analyst", published="2026-01-01T00:00:00Z"),
    ]},
    "contoso": {"jobs": [
        gh_job(11, "Operations Analyst", content="Excel, SQL, process improvement, stakeholder work.")]},
    "adatum": {"jobs": [gh_job(21, "Data Analyst", content="SQL and Tableau.")]},
}


def handler(request: httpx.Request) -> httpx.Response:
    slug = request.url.path.split("/boards/")[1].split("/")[0]
    if slug == "broken":
        return httpx.Response(500)
    return httpx.Response(200, json=BOARDS[slug])


def companies(*slugs: str) -> list[Company]:
    return [Company(s.title(), "greenhouse", s) for s in slugs]


@pytest.fixture
def db(tmp_path: Path):
    with DB(tmp_path / "t.db") as d:
        yield d


def run(db: DB, tmp_path: Path, cs: list[Company], target: int = 10) -> sourcing.SourcingReport:
    bank = load_bank(write_bank(tmp_path / "exp"))
    settings = Settings(daily_target=target)

    async def go() -> sourcing.SourcingReport:
        async with HttpClient(transport=httpx.MockTransport(handler), retry_sleep_s=0) as client:
            return await sourcing.run_sourcing(db, PROFILE, settings, bank, cs, TODAY, NOW, client)

    return run_async(go())


def test_filters_and_queues_the_good_postings(db: DB, tmp_path: Path) -> None:
    report = run(db, tmp_path, companies("fabrikam", "contoso"))
    titles = sorted(j.role for j in report.queued)
    assert titles == ["Data Analyst", "Operations Analyst"]
    assert report.boards_ok == 2
    assert report.dropped["level"] == 3          # senior, II, 6 years
    assert report.dropped["title"] == 1          # chef
    assert report.dropped["location"] == 1
    assert report.dropped["freshness"] == 1
    first = next(j for j in report.queued if j.company == "Fabrikam")
    assert first.track == "data" and first.fit in ("A", "B") and first.status == "New"


def test_one_posting_per_company_and_daily_target(db: DB, tmp_path: Path) -> None:
    report = run(db, tmp_path, companies("fabrikam", "contoso", "adatum"), target=2)
    assert len(report.queued) == 2
    assert len({j.company_norm for j in report.queued}) == 2


def test_second_run_does_not_requeue(db: DB, tmp_path: Path) -> None:
    run(db, tmp_path, companies("fabrikam"))
    again = run(db, tmp_path, companies("fabrikam"))
    assert again.queued == []


def test_failed_boards_are_reported_not_fatal(db: DB, tmp_path: Path) -> None:
    report = run(db, tmp_path, [*companies("contoso"), Company("Broken", "greenhouse", "broken")])
    assert report.boards_failed == ["greenhouse/broken"]
    assert len(report.queued) == 1


def test_already_applied_company_is_skipped(db: DB, tmp_path: Path) -> None:
    run(db, tmp_path, companies("fabrikam"))
    job = db.jobs()[0]
    db.update_job(job.key, status="Submitted")
    report = run(db, tmp_path, companies("fabrikam", "contoso"))
    assert [j.company for j in report.queued] == ["Contoso"]
