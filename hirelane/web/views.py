"""Page routes. Data shaping lives in plain functions so it can be tested without HTTP.

This module avoids postponed annotations on purpose: FastAPI resolves the route signatures at runtime.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from .. import answers as answer_store
from .. import facts
from ..actions import ActionError, apply_action
from ..config import Paths, Settings, load_settings, now
from ..db import DB
from ..models import (
    APPLIED_STATUSES,
    STATUS_APPROVED,
    STATUS_BUILD_FAILED,
    STATUS_NEEDS_YOU,
    STATUS_READY,
    STATUS_REVIEW,
    STATUS_SUBMITTED,
    STATUSES,
    Job,
)
from ..resume import ResumeContent

NEEDS_STATUSES = (STATUS_NEEDS_YOU, STATUS_REVIEW, STATUS_BUILD_FAILED)
RECENT_RUNS = 5


@dataclass
class HomeData:
    queued: int
    ready: int
    approved: int
    needs: int
    applied: int
    submitted_today: int
    daily_cap: int
    mode: str
    open_questions: int
    pending_proposals: int
    runs: list[dict[str, Any]]


def nav_counts(db: DB) -> dict[str, int]:
    counts = db.status_counts()
    needs = sum(counts.get(s, 0) for s in NEEDS_STATUSES) + len(db.open_questions())
    return {"/needs": needs, "/studio": len(db.proposals())}


def home_data(db: DB, settings: Settings) -> HomeData:
    counts = db.status_counts()
    day = now(settings).strftime("%Y-%m-%d")
    return HomeData(
        queued=counts.get("New", 0), ready=counts.get(STATUS_READY, 0), approved=counts.get(STATUS_APPROVED, 0),
        needs=sum(counts.get(s, 0) for s in NEEDS_STATUSES),
        applied=sum(counts.get(s, 0) for s in APPLIED_STATUSES),
        submitted_today=db.submitted_today(day), daily_cap=settings.daily_cap, mode=settings.submit_mode,
        open_questions=len(db.open_questions()), pending_proposals=len(db.proposals()),
        runs=db.last_runs(RECENT_RUNS))
