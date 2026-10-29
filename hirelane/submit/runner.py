"""The submission runner. It decides what happens to each approved job, one at a time.

Safe by default: in review mode it fills and verifies the form, takes a screenshot, and stops. A person submits it
with ``hirelane finish``. A CAPTCHA is always handed to the person and never solved.
"""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..answers import AnswerBank
from ..config import Paths, Settings, live_submit_allowed
from ..db import DB
from ..models import (
    STATUS_APPROVED,
    STATUS_CLOSED,
    STATUS_NEEDS_YOU,
    STATUS_REVIEW,
    STATUS_SUBMITTED,
    STATUS_SUBMITTING,
    Job,
)
from . import ADAPTERS
from .base import Adapter, FillReport, FormUnavailable
from .fields import page_errors
from .gate import preflight, runs_today
from .verify import verify

log = logging.getLogger(__name__)

PHASE_FILLED = "filled"
PHASE_CLICKED = "submit_clicked"
PHASE_CAPTCHA = "captcha_blocked"
PHASE_VERIFY_FAILED = "verify_failed"
PHASE_CLEARED = "click_cleared"
FINISH_WAIT_MINUTES = 15
FINISH_POLL_MS = 2_000

OUTCOMES = ("review", "submitted", "needs_you", "captcha", "closed", "capped", "skipped")


@dataclass
class JobResult:
    key: str
    outcome: str
    detail: str = ""


@dataclass
class RunContext:
    db: DB
    settings: Settings
    paths: Paths
    answers: AnswerBank
    allowed_text: str                                   # approved fact text, for the leftover company name check
    open_page: Callable[[bool], AbstractContextManager[Any]]   # headless flag to a context manager yielding a page
    adapters: dict[str, type[Adapter]] | None = None
    now: Callable[[], datetime] = datetime.now
    sleep: Callable[[float], None] = time.sleep
    rng: random.Random | None = None


def _day(ctx: RunContext) -> str:
    return ctx.now().strftime("%Y-%m-%d")


def _adapter(ctx: RunContext, job: Job) -> Adapter:
    return (ctx.adapters or ADAPTERS)[job.ats]()


def _to_user(ctx: RunContext, job: Job, reason: str, outcome: str = "needs_you") -> JobResult:
    ctx.db.update_job(job.key, status=STATUS_NEEDS_YOU, needs_reason=reason[:500], lock_until="")
    return JobResult(job.key, outcome, reason)


def click_is_unresolved(db: DB, key: str) -> bool:
    """A submit click that is neither confirmed nor cleared. The form may have gone through, so it is never repeated."""
    phases = db.attempt_phases(key)
    for phase in reversed(phases):
        if phase == PHASE_CLEARED:
            return False
        if phase == PHASE_CLICKED:
            return True
    return False


def _screenshot(ctx: RunContext, page: Any, job: Job, suffix: str) -> Path:
    safe = job.key.replace(":", "_")
    path = ctx.paths.runs / _day(ctx) / f"{safe}_{suffix}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception as e:
        log.info("screenshot failed for %s: %s", job.key, e)
    return path


def fill_and_verify(ctx: RunContext, page: Any, job: Job, adapter: Adapter) -> tuple[FillReport, list[str]]:
    record = ctx.db.get_resume(job.key)
    resume = Path(record["path"]) if record else Path()
    adapter.open(page, job)
    report = adapter.fill(page, resume, ctx.answers)
    ctx.db.add_attempt(job.key, PHASE_FILLED, now=ctx.now())
    for q in report.plan.unanswered:
        ctx.db.add_question(job.key, q.label, q.options, ctx.now())
    others = [j.company for j in ctx.db.jobs()]
    result = verify(report.fields, report.plan, resume_file=resume.name, company=job.company, other_companies=others,
                    allowed_text=ctx.allowed_text, page_errors=page_errors(page) + report.page_errors)
    problems = [*report.fill_problems, *result.problems]
    return report, list(dict.fromkeys(problems))


def process_job(ctx: RunContext, job: Job, page: Any) -> JobResult:
    day = _day(ctx)
    pre = preflight(job, ctx.db, ctx.settings, day)
    if pre.problems and any("daily cap" in p for p in pre.problems):
        return JobResult(job.key, "capped", pre.problems[0])
    if pre.problems:
        return _to_user(ctx, job, " | ".join(pre.problems))
    if click_is_unresolved(ctx.db, job.key):
        return _to_user(ctx, job, "A submit was clicked earlier and never confirmed. Check your inbox, then run "
                                  f"`hirelane clear-click {job.key}` if it did not go through.")
    adapter = _adapter(ctx, job)
    try:
        report, problems = fill_and_verify(ctx, page, job, adapter)
    except FormUnavailable as e:
        closed = "closed" in str(e) or "HTTP 404" in str(e)
        ctx.db.update_job(job.key, status=STATUS_CLOSED if closed else STATUS_NEEDS_YOU, needs_reason=str(e)[:300],
                          lock_until="")
        return JobResult(job.key, "closed" if closed else "needs_you", str(e))
    shot = _screenshot(ctx, page, job, "filled")
    if report.captcha:
        ctx.db.add_attempt(job.key, PHASE_CAPTCHA, now=ctx.now())
        return _to_user(ctx, job, f"A CAPTCHA is on the form. Finish it yourself with: hirelane finish {job.key}.",
                        "captcha")
    if problems:
        ctx.db.add_attempt(job.key, PHASE_VERIFY_FAILED, " | ".join(problems), ctx.now())
        return _to_user(ctx, job, " | ".join(problems))
    if not live_submit_allowed(ctx.settings):
        note = f"Filled and verified. Review {shot.name}, then run `hirelane finish {job.key}`."
        ctx.db.update_job(job.key, status=STATUS_REVIEW, lock_until="", needs_reason=note)
        return JobResult(job.key, "review", str(shot))
    return _submit(ctx, job, page, adapter)


def _submit(ctx: RunContext, job: Job, page: Any, adapter: Adapter) -> JobResult:
    ctx.db.update_job(job.key, status=STATUS_SUBMITTING)
    ctx.db.add_attempt(job.key, PHASE_CLICKED, now=ctx.now())          # recorded first, so a crash cannot double submit
    try:
        adapter.click_submit(page)
    except Exception as e:
        return _to_user(ctx, job, f"The submit click failed ({type(e).__name__}). Check the form before retrying.")
    if adapter.confirmed(page):
        ctx.db.update_job(job.key, status=STATUS_SUBMITTED, submitted_at=ctx.now().isoformat(), needs_reason="",
                          lock_until="")
        _screenshot(ctx, page, job, "confirmed")
        return JobResult(job.key, "submitted")
    if adapter.captcha_present(page):
        ctx.db.add_attempt(job.key, PHASE_CLEARED, "captcha stopped the submit", ctx.now())
        ctx.db.add_attempt(job.key, PHASE_CAPTCHA, now=ctx.now())
        return _to_user(ctx, job, f"A CAPTCHA stopped the submit. Finish it with `hirelane finish {job.key}`.",
                        "captcha")
    return _to_user(ctx, job, "No confirmation page appeared. It may or may not have been sent, so check your inbox. "
                              f"Then run `hirelane clear-click {job.key}` if it did not go through.")


def run_submissions(ctx: RunContext, limit: int | None = None) -> list[JobResult]:
    """Process approved jobs one at a time with polite random pauses between them."""
    rng = ctx.rng or random.Random()
    results: list[JobResult] = []
    jobs = ctx.db.jobs(STATUS_APPROVED)
    if limit is not None:
        jobs = jobs[:limit]
    with ctx.open_page(ctx.settings.headless) as page:
        for i, job in enumerate(jobs):
            if runs_today(ctx.db, _day(ctx)) >= ctx.settings.daily_cap:
                results.append(JobResult(job.key, "capped", f"daily cap of {ctx.settings.daily_cap} reached"))
                break
            if not ctx.db.claim(job.key, ctx.now(), (STATUS_APPROVED,)):
                results.append(JobResult(job.key, "skipped", "another run holds this job"))
                continue
            try:
                results.append(process_job(ctx, job, page))
            except Exception as e:  # one broken form must not stop the rest of the day
                log.exception("job %s failed", job.key)
                results.append(_to_user(ctx, job, f"Unexpected error: {type(e).__name__}: {str(e)[:200]}"))
            if i < len(jobs) - 1:
                ctx.sleep(rng.uniform(ctx.settings.delay_min_s, ctx.settings.delay_max_s))
    return results
