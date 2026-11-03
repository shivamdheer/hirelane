"""The daily digest: a short summary of what happened and what waits for the user.

It is written to the data folder and, when Gmail is connected, sent to the user's own address from the profile.
There is no setting for another recipient.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .db import DB
from .models import (
    STATUS_BUILD_FAILED,
    STATUS_INTERVIEW,
    STATUS_NEEDS_YOU,
    STATUS_OFFER,
    STATUS_READY,
    STATUS_REVIEW,
    STATUS_SUBMITTED,
    Job,
)

MAX_LISTED = 8


@dataclass
class Digest:
    subject: str
    body: str
    empty: bool


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _lines(title: str, jobs: list[Job], extra: str = "") -> list[str]:
    if not jobs:
        return []
    out = [f"{title} ({len(jobs)})"]
    for j in jobs[:MAX_LISTED]:
        note = f" - {j.needs_reason}" if j.needs_reason and extra == "reason" else ""
        out.append(f"  {j.company}, {j.role}{note}")
    if len(jobs) > MAX_LISTED:
        out.append(f"  and {len(jobs) - MAX_LISTED} more")
    return [*out, ""]


def build_digest(db: DB, day: str, web_url: str = "") -> Digest:
    ready = db.jobs(STATUS_READY)
    review = db.jobs(STATUS_REVIEW)
    needs = db.jobs(STATUS_NEEDS_YOU, STATUS_BUILD_FAILED)
    submitted = [j for j in db.jobs(STATUS_SUBMITTED) if j.submitted_at.startswith(day)]
    moving = db.jobs(STATUS_INTERVIEW, STATUS_OFFER)
    questions = db.open_questions()
    proposals = db.proposals()
    quiet = ("other", "confirmation")
    replies = [e for e in db.emails(20) if e["handled_at"].startswith(day) and e["kind"] not in quiet]

    body: list[str] = []
    body += _lines("Applied today", submitted)
    body += _lines("Interviews and offers", moving)
    body += _lines("Filled and waiting for your review", review)
    body += _lines("Resumes ready for your approval", ready)
    body += _lines("Need you", needs, "reason")
    if replies:
        body.append(f"Replies ({len(replies)})")
        body += [f"  {e['kind']}: {e['company'] or e['from_addr']}" for e in replies[:MAX_LISTED]]
        body.append("")
    if questions:
        body += [f"{_count(len(questions), 'form question')} need an answer.", ""]
    if proposals:
        body += [f"{_count(len(proposals), 'proposed addition')} to your facts need a yes or no.", ""]
    empty = not body
    if empty:
        body = ["Nothing new today."]
    if web_url:
        body += ["", f"Open hirelane: {web_url}"]
    subject = f"hirelane {day}: " + (f"{len(submitted)} applied, {len(needs) + len(review)} need you" if not empty
                                      else "nothing new")
    return Digest(subject=subject, body="\n".join(body).strip() + "\n", empty=empty)


def write_digest(digest: Digest, outbox: Path, day: str, now: datetime) -> Path:
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / f"digest-{day}.txt"
    path.write_text(f"Subject: {digest.subject}\nDate: {now.isoformat()}\n\n{digest.body}")
    return path
