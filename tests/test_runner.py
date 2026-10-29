from __future__ import annotations

import random
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from hirelane import answers, build
from hirelane.config import Paths, Settings
from hirelane.db import DB
from hirelane.facts import load_bank
from hirelane.models import (
    STATUS_APPROVED,
    STATUS_NEEDS_YOU,
    STATUS_REVIEW,
    STATUS_SUBMITTED,
    Posting,
)
from hirelane.profile import parse_profile
from hirelane.submit import fields, runner
from hirelane.submit.greenhouse import GreenhouseAdapter
from tests.bank_fixture import write_bank
from tests.conftest import FORMS
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)
NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


class FixtureAdapter(GreenhouseAdapter):
    """Opens the local fixture form instead of a real board. Everything else is the real adapter."""

    captcha = False

    def open(self, page: Any, job: Any) -> None:
        page.goto((FORMS / "application.html").as_uri())
        if self.captcha:
            page.evaluate("document.body.insertAdjacentHTML('beforeend', '<p>Please verify you are human</p>')")


class CaptchaAdapter(FixtureAdapter):
    captcha = True


RULES = {"answers": [
    {"match": ["authorized to work"], "answer": "Yes"}, {"match": ["visa sponsorship"], "answer": "No"},
    {"match": ["privacy policy"], "answer": "Yes"}, {"match": ["favorite color"], "answer": "Green"},
]}


@pytest.fixture
def world(home: Paths, browser, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fields, "SETTLE_MS", 10)
    bank = load_bank(write_bank(home.experience))
    (home.config / "answers.yaml").write_text(yaml.safe_dump(RULES))
    db = DB(home.db)
    jobs = []
    for i, company in enumerate(("Fabrikam", "Contoso")):
        p = Posting(ats="greenhouse", slug=company.lower(), job_id=str(100 + i), company=company, title="Data Analyst",
                    apply_url=f"https://job-boards.greenhouse.io/{company.lower()}/jobs/{100 + i}",
                    description="SQL Tableau Python dashboards")
        job = db.add_posting(p, status=STATUS_APPROVED, track="data")
        assert build.build_resume(job, db, bank, PROFILE, home).ok
        db.update_job(job.key, status=STATUS_APPROVED)
        jobs.append(job)

    @contextmanager
    def open_page(headless: bool) -> Iterator[Any]:
        page = browser.new_page()
        try:
            yield page
        finally:
            page.close()

    def make_ctx(adapter: type = FixtureAdapter, **settings: Any) -> runner.RunContext:
        delays: list[float] = []
        ctx = runner.RunContext(
            db=db, settings=Settings(delay_min_s=5, delay_max_s=9, **settings), paths=home,
            answers=answers.load_bank(PROFILE, home.config), allowed_text=bank.all_text(), open_page=open_page,
            adapters={"greenhouse": adapter}, now=lambda: NOW, sleep=delays.append, rng=random.Random(1))
        ctx.delays = delays  # type: ignore[attr-defined]
        return ctx

    yield db, jobs, make_ctx
    db.close()


@pytest.mark.browser
def test_review_mode_fills_verifies_and_stops(world) -> None:
    db, jobs, make_ctx = world
    ctx = make_ctx()
    results = runner.run_submissions(ctx, limit=1)
    assert [r.outcome for r in results] == ["review"]
    job = db.get_job(jobs[0].key)
    assert job is not None and job.status == STATUS_REVIEW and "hirelane finish" in job.needs_reason
    assert Path(results[0].detail).exists()
    assert db.attempt_phases(job.key) == ["filled"]
    assert job.lock_until == ""


@pytest.mark.browser
def test_an_unanswerable_question_goes_to_the_user(world, home: Paths) -> None:
    db, jobs, make_ctx = world
    rules = {"answers": [r for r in RULES["answers"] if r["match"] != ["favorite color"]]}
    (home.config / "answers.yaml").write_text(yaml.safe_dump(rules))
    results = runner.run_submissions(make_ctx(), limit=1)
    assert results[0].outcome == "needs_you" and "favorite color" in results[0].detail
    assert db.get_job(jobs[0].key).status == STATUS_NEEDS_YOU  # type: ignore[union-attr]
    assert [q["label"] for q in db.open_questions()] == ["What is your favorite color?"]


@pytest.mark.browser
def test_a_captcha_is_always_handed_over(world, monkeypatch: pytest.MonkeyPatch) -> None:
    db, jobs, make_ctx = world
    monkeypatch.setenv("HIRELANE_ALLOW_LIVE", "1")
    results = runner.run_submissions(make_ctx(CaptchaAdapter, submit_mode="live"), limit=1)
    assert results[0].outcome == "captcha"
    assert "captcha_blocked" in db.attempt_phases(jobs[0].key)
    assert "submit_clicked" not in db.attempt_phases(jobs[0].key)


@pytest.mark.browser
def test_live_mode_needs_both_switches(world, monkeypatch: pytest.MonkeyPatch) -> None:
    db, jobs, make_ctx = world
    results = runner.run_submissions(make_ctx(submit_mode="live"), limit=1)      # no environment variable
    assert results[0].outcome == "review"
    monkeypatch.setenv("HIRELANE_ALLOW_LIVE", "1")
    db.update_job(jobs[0].key, status=STATUS_APPROVED)
    results = runner.run_submissions(make_ctx(submit_mode="live"), limit=1)
    assert results[0].outcome == "submitted"
    job = db.get_job(jobs[0].key)
    assert job is not None and job.status == STATUS_SUBMITTED and job.submitted_at
    assert db.attempt_phases(job.key)[-1] == "submit_clicked"


@pytest.mark.browser
def test_an_unresolved_click_is_never_repeated(world, monkeypatch: pytest.MonkeyPatch) -> None:
    db, jobs, make_ctx = world
    db.add_attempt(jobs[0].key, "submit_clicked", now=NOW)
    results = runner.run_submissions(make_ctx(), limit=1)
    assert results[0].outcome == "needs_you" and "never confirmed" in results[0].detail
    db.update_job(jobs[0].key, status=STATUS_APPROVED)
    db.add_attempt(jobs[0].key, "click_cleared", now=NOW)
    assert runner.run_submissions(make_ctx(), limit=1)[0].outcome == "review"


@pytest.mark.browser
def test_daily_cap_stops_the_run_and_delays_are_polite(world) -> None:
    db, jobs, make_ctx = world
    ctx = make_ctx(daily_cap=1)
    results = runner.run_submissions(ctx)
    assert [r.outcome for r in results] == ["review", "capped"]
    ctx2 = make_ctx(daily_cap=10)
    db.update_job(jobs[0].key, status=STATUS_APPROVED)
    runner.run_submissions(ctx2)
    assert len(ctx2.delays) == 1 and 5 <= ctx2.delays[0] <= 9       # type: ignore[attr-defined]


def test_click_is_unresolved_logic(tmp_path: Path) -> None:
    with DB(tmp_path / "t.db") as db:
        assert not runner.click_is_unresolved(db, "k")
        db.add_attempt("k", "filled")
        db.add_attempt("k", "submit_clicked")
        assert runner.click_is_unresolved(db, "k")
        db.add_attempt("k", "click_cleared")
        assert not runner.click_is_unresolved(db, "k")


@pytest.mark.browser
def test_finish_waits_for_the_person_and_records_the_submit(world) -> None:
    from hirelane.submit.finish import finish_job

    db, jobs, make_ctx = world
    db.update_job(jobs[0].key, status=STATUS_REVIEW)

    def person_submits(page: Any) -> None:
        page.click("button[type=submit]")

    result = finish_job(make_ctx(), jobs[0].key, wait_minutes=1, human=person_submits)
    assert result.outcome == "submitted"
    job = db.get_job(jobs[0].key)
    assert job is not None and job.status == STATUS_SUBMITTED
    assert "click_cleared" in db.attempt_phases(job.key)


@pytest.mark.browser
def test_finish_without_a_confirmation_asks_the_person_to_mark_it(world) -> None:
    from hirelane.submit.finish import finish_job, mark_submitted

    db, jobs, make_ctx = world
    result = finish_job(make_ctx(), jobs[1].key, wait_minutes=0)
    assert result.outcome == "needs_you"
    assert "mark-submitted" in db.get_job(jobs[1].key).needs_reason  # type: ignore[union-attr]
    assert mark_submitted(db, jobs[1].key, "2026-03-10T12:30:00+00:00")
    assert db.get_job(jobs[1].key).status == STATUS_SUBMITTED  # type: ignore[union-attr]
    assert not mark_submitted(db, "nope", "x")


def test_finish_rejects_jobs_that_are_not_finishable(world) -> None:
    from hirelane.submit.finish import finish_job

    db, jobs, make_ctx = world
    db.update_job(jobs[0].key, status=STATUS_SUBMITTED)
    assert finish_job(make_ctx(), jobs[0].key).outcome == "skipped"
    assert finish_job(make_ctx(), "missing").outcome == "skipped"
