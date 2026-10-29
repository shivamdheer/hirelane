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
