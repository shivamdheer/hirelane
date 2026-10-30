"""The decisions a person can make about a job. Shared by the web interface and the command line."""
from __future__ import annotations

from datetime import datetime

from .db import DB, iso
from .models import (
    STATUS_APPROVED,
    STATUS_BUILD_FAILED,
    STATUS_NEEDS_YOU,
    STATUS_NEW,
    STATUS_READY,
    STATUS_REVIEW,
    STATUS_SKIP,
    STATUS_SUBMITTED,
    Job,
)

ACTIONS = ("approve", "skip", "retry", "unskip", "mark_submitted")
ALLOWED_FROM = {
    "approve": (STATUS_READY,),
    "skip": (STATUS_NEW, STATUS_READY, STATUS_APPROVED, STATUS_NEEDS_YOU, STATUS_REVIEW, STATUS_BUILD_FAILED),
    "retry": (STATUS_NEEDS_YOU, STATUS_REVIEW, STATUS_BUILD_FAILED),
    "unskip": (STATUS_SKIP,),
    "mark_submitted": (STATUS_NEEDS_YOU, STATUS_REVIEW, STATUS_APPROVED),
}


class ActionError(ValueError):
    pass


def apply_action(db: DB, key: str, action: str, now: datetime) -> str:
    """Change a job's status. Returns a short message for the page. Raises ActionError for an illegal move."""
    job: Job | None = db.get_job(key)
    if job is None:
        raise ActionError("no such job")
    if action not in ACTIONS:
        raise ActionError(f"unknown action {action!r}")
    if job.status not in ALLOWED_FROM[action]:
        raise ActionError(f"{action} is not possible for a job in status {job.status!r}")
    stamp = iso(now)
    if action == "approve":
        db.update_job(key, status=STATUS_APPROVED, decided_at=stamp)
        return f"Approved {job.company}. It is filled on the next run."
    if action == "skip":
        db.update_job(key, status=STATUS_SKIP, decided_at=stamp, lock_until="")
        return f"Skipped {job.company}."
    if action == "unskip":
        db.update_job(key, status=STATUS_READY if job.resume_file else STATUS_NEW, decided_at="")
        return f"{job.company} is back in the queue."
    if action == "retry":
        target = STATUS_NEW if job.status == STATUS_BUILD_FAILED else STATUS_APPROVED
        db.update_job(key, status=target, needs_reason="", lock_until="")
        return f"{job.company} will be tried again."
    db.update_job(key, status=STATUS_SUBMITTED, submitted_at=stamp, needs_reason="", lock_until="")
    db.add_attempt(key, "marked_submitted", "by the user", now)
    return f"Marked {job.company} as submitted."
