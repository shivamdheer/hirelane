"""Finish a job by hand. The form is filled and verified in a visible window, and the person reviews and submits it.

This is the path for review mode, for a CAPTCHA, and for any form the runner could not complete on its own.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..config import today_str
from ..db import DB
from ..models import STATUS_NEEDS_YOU, STATUS_REVIEW, STATUS_SUBMITTED, Job
from . import ADAPTERS
from .base import FormUnavailable
from .runner import PHASE_CLEARED, JobResult, RunContext, fill_and_verify

WAIT_MINUTES = 15
POLL_MS = 2_000
FINISHABLE = ("Approved", STATUS_REVIEW, STATUS_NEEDS_YOU)


def finish_job(ctx: RunContext, key: str, wait_minutes: int = WAIT_MINUTES,
               human: Callable[[Any], None] | None = None) -> JobResult:
    """Open the form in a visible browser, fill it, and wait for the person to submit."""
    job: Job | None = ctx.db.get_job(key)
    if job is None:
        return JobResult(key, "skipped", "no such job")
    if job.status not in FINISHABLE:
        return JobResult(key, "skipped", f"a job in status {job.status!r} cannot be finished")
    adapter = (ctx.adapters or ADAPTERS)[job.ats]()
    ctx.db.add_attempt(job.key, PHASE_CLEARED, "finish by hand", ctx.now())
    with ctx.open_page(False) as page:
        try:
            _report, problems = fill_and_verify(ctx, page, job, adapter)
        except FormUnavailable as e:
            return JobResult(key, "needs_you", str(e))
        if problems:
            print("Check these before you submit:")
            for p in problems:
                print(f"  - {p}")
        if human is not None:
            human(page)
        waited_ms = 0
        while waited_ms < wait_minutes * 60_000:
            if adapter.confirmed_now(page):
                ctx.db.update_job(key, status=STATUS_SUBMITTED, submitted_at=ctx.now().isoformat(), needs_reason="",
                                  lock_until="")
                return JobResult(key, "submitted", today_str(ctx.settings))
            try:
                page.wait_for_timeout(POLL_MS)
            except Exception:
                break                      # the window was closed
            waited_ms += POLL_MS
    note = f"No confirmation was seen. If you did submit it, run `hirelane mark-submitted {key}`."
    ctx.db.update_job(key, status=STATUS_NEEDS_YOU, lock_until="", needs_reason=note)
    return JobResult(key, "needs_you", "no confirmation seen")


def mark_submitted(db: DB, key: str, when: str) -> bool:
    job = db.get_job(key)
    if job is None:
        return False
    db.update_job(key, status=STATUS_SUBMITTED, submitted_at=when, needs_reason="", lock_until="")
    db.add_attempt(key, "marked_submitted", "by the user")
    return True
