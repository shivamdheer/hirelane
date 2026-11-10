from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import yaml

from hirelane import pipeline
from hirelane.companies import Company, save_companies
from hirelane.config import Paths, Settings
from hirelane.db import DB
from hirelane.facts import load_bank
from hirelane.models import STATUS_APPROVED, STATUS_READY
from hirelane.profile import parse_profile
from hirelane.sources.base import HttpClient
from tests.bank_fixture import write_bank
from tests.profile_fixture import ALEX_PROFILE

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
BOARD: dict[str, Any] = {"jobs": [
    {"id": 7, "title": "Data Analyst", "location": {"name": "Chicago, IL"}, "first_published": "2026-03-09T12:00:00Z",
     "content": "SQL, Python, Tableau, pandas and Excel for dashboards.", "absolute_url": "https://example.com/7"},
]}


@pytest.fixture
def env(home: Paths):
    write_bank(home.experience)
    save_companies([Company("Fabrikam", "greenhouse", "fabrikam")], home.companies_file)
    (home.config / "answers.yaml").write_text(yaml.safe_dump({"answers": []}))
    db = DB(home.db)
    settings = Settings()
    e = pipeline.Env(paths=home, settings=settings, profile=parse_profile(ALEX_PROFILE), db=db,
                     bank=load_bank(home.experience), clock=lambda: NOW,
                     client_factory=lambda: HttpClient(transport=httpx.MockTransport(
                         lambda r: httpx.Response(200, json=BOARD)), retry_sleep_s=0))
    yield e
    db.close()


def test_source_then_build_leaves_a_ready_job(env: pipeline.Env) -> None:
    results = pipeline.run_day(env, ("source", "build"))
    assert [(n, ok) for n, ok, _ in results] == [("source", True), ("build", True)]
    assert "1 queued from 1 postings on 1 boards" in results[0][2]
    (job,) = env.db.jobs()
    assert job.status == STATUS_READY and job.resume_file.endswith("Alex_Rivera_Resume_Fabrikam.pdf")
    runs = env.db.last_runs()
    assert [r["task"] for r in runs] == ["build", "source"] and all(r["ok"] for r in runs)


def test_nothing_is_approved_unless_the_user_or_the_setting_says_so(env: pipeline.Env) -> None:
    pipeline.run_day(env, ("source", "build"))
    assert env.db.jobs(STATUS_APPROVED) == []
    pipeline.run_step(env, "source")
    env.settings = Settings(auto_approve="fit_a")
    job = env.db.jobs()[0]
    env.db.update_job(job.key, fit="A", gaps="[]")
    assert pipeline.auto_approve(env) == 1
    assert env.db.get_job(job.key).status == STATUS_APPROVED  # type: ignore[union-attr]


def test_auto_approve_skips_jobs_with_gaps_or_weaker_fit(env: pipeline.Env) -> None:
    pipeline.run_day(env, ("source", "build"))
    env.settings = Settings(auto_approve="fit_a")
    job = env.db.jobs()[0]
    env.db.update_job(job.key, fit="A", gaps='["spark"]')
    assert pipeline.auto_approve(env) == 0
    env.db.update_job(job.key, fit="B", gaps="[]")
    assert pipeline.auto_approve(env) == 0


def test_submit_with_nothing_approved_does_not_open_a_browser(env: pipeline.Env) -> None:
    def explode(headless: bool) -> Any:
        raise AssertionError("a browser was opened")

    env.open_page = explode
    ok, summary = pipeline.run_step(env, "submit")
    assert ok and summary == "nothing approved to fill"


def test_a_failing_step_is_recorded_and_the_next_still_runs(env: pipeline.Env,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(e: pipeline.Env) -> str:
        raise RuntimeError("network is down")

    monkeypatch.setitem(pipeline.STEP_FUNCS, "source", boom)
    results = pipeline.run_day(env, ("source", "build"))
    assert results[0][:2] == ("source", False) and "network is down" in results[0][2]
    assert results[1][:2] == ("build", True)
    assert env.db.last_runs()[1]["ok"] == 0


def test_source_without_companies_says_what_to_do(env: pipeline.Env, home: Paths) -> None:
    home.companies_file.unlink()
    assert "hirelane companies add" in pipeline.run_source(env)

