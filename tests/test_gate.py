from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hirelane import build
from hirelane.config import Paths, Settings
from hirelane.db import DB
from hirelane.facts import load_bank
from hirelane.models import STATUS_APPROVED, Posting
from hirelane.profile import parse_profile
from hirelane.submit import gate
from tests.bank_fixture import write_bank
from tests.profile_fixture import ALEX_PROFILE

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
DAY = "2026-03-10"
PROFILE = parse_profile(ALEX_PROFILE)


@pytest.fixture
def env(home: Paths):
    bank = load_bank(write_bank(home.experience))
    with DB(home.db) as db:
        posting = Posting(ats="greenhouse", slug="fabrikam", job_id="9", company="Fabrikam", title="Data Analyst",
                          apply_url="https://job-boards.greenhouse.io/fabrikam/jobs/9",
                          description="SQL Tableau Python dashboards")
        job = db.add_posting(posting, status=STATUS_APPROVED, track="data")
        assert build.build_resume(job, db, bank, PROFILE, home).ok
        yield home, db, db.get_job(job.key)


def test_a_built_job_passes(env) -> None:
    _home, db, job = env
    assert gate.preflight(job, db, Settings(), DAY).ok


def test_unsupported_ats_and_foreign_urls_fail(env) -> None:
    _home, db, job = env
    job.ats = "workday"
    assert "not supported" in gate.preflight(job, db, Settings(), DAY).problems[0]
    job.ats = "greenhouse"
    job.apply_url = "https://evil.example.com/greenhouse.io/apply"
    assert any("outside the greenhouse domains" in p for p in gate.preflight(job, db, Settings(), DAY).problems)


def test_daily_cap_counts_fills_and_submits(env) -> None:
    _home, db, job = env
    db.add_attempt(job.key, "filled", now=NOW)
    db.add_attempt(job.key, "submit_clicked", now=NOW)
    db.add_attempt(job.key, "captcha", now=NOW)                  # not counted
    assert gate.runs_today(db, DAY) == 2
    assert gate.preflight(job, db, Settings(daily_cap=2), DAY).problems == ["daily cap of 2 reached"]
    assert gate.preflight(job, db, Settings(daily_cap=3), DAY).ok


def test_resume_must_exist_unchanged_and_belong_to_the_company(env) -> None:
    _home, db, job = env
    path = Path(job.resume_file)
    path.write_bytes(path.read_bytes() + b"\n%tampered")
    assert any("changed after" in p for p in gate.preflight(job, db, Settings(), DAY).problems)
    path.unlink()
    assert any("missing" in p for p in gate.preflight(job, db, Settings(), DAY).problems)


def test_job_without_a_passing_resume_fails(env) -> None:
    _home, db, job = env
    job.key = "greenhouse:other:1"
    assert gate.preflight(job, db, Settings(), DAY).problems[-1] == "no resume that passed the ATS gate"


@pytest.mark.parametrize("url,ats,allowed", [
    ("https://job-boards.greenhouse.io/fabrikam/jobs/9", "greenhouse", True),
    ("https://greenhouse.io/x", "greenhouse", True),
    ("https://evilgreenhouse.io/x", "greenhouse", False),
    ("https://greenhouse.io.evil.example/x", "greenhouse", False),
    ("https://jobs.lever.co/x", "greenhouse", False),
    ("https://jobs.ashbyhq.com/x", "workday", False),
])
def test_url_allowed_matches_whole_domains_only(url: str, ats: str, allowed: bool) -> None:
    assert gate.url_allowed(url, ats) is allowed
