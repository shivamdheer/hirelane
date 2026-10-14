"""Shared data shapes: a posting as a board returns it, and a job as the database tracks it."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from typing import Any

SUPPORTED_ATS = ("greenhouse", "lever", "ashby")

# Statuses in the order a job normally moves through them.
STATUS_NEW = "New"
STATUS_READY = "Resume ready"
STATUS_APPROVED = "Approved"
STATUS_SUBMITTING = "Submitting"
STATUS_REVIEW = "Ready for review"
STATUS_SUBMITTED = "Submitted"
STATUS_NEEDS_YOU = "Needs you"
STATUS_BUILD_FAILED = "Build failed"
STATUS_INTERVIEW = "Interview"
STATUS_OFFER = "Offer"
STATUS_REJECTED = "Rejected"
STATUS_SKIP = "Skip"
STATUS_CLOSED = "Closed"
STATUSES = (STATUS_NEW, STATUS_READY, STATUS_APPROVED, STATUS_SUBMITTING, STATUS_REVIEW, STATUS_SUBMITTED,
            STATUS_NEEDS_YOU, STATUS_BUILD_FAILED, STATUS_INTERVIEW, STATUS_OFFER, STATUS_REJECTED, STATUS_SKIP,
            STATUS_CLOSED)
# A job in one of these still holds its company's resume file name.
PENDING_STATUSES = (STATUS_NEW, STATUS_READY, STATUS_APPROVED, STATUS_SUBMITTING, STATUS_REVIEW, STATUS_NEEDS_YOU,
                    STATUS_BUILD_FAILED)
APPLIED_STATUSES = (STATUS_SUBMITTED, STATUS_INTERVIEW, STATUS_OFFER, STATUS_REJECTED)


@dataclass
class Posting:
    ats: str
    slug: str
    job_id: str
    company: str
    title: str
    location: str = ""
    url: str = ""
    apply_url: str = ""
    posted: str = ""             # YYYY-MM-DD, empty when the board does not say
    description: str = ""        # plain text
    remote: bool = False
    country: str = ""
    pay: str = ""
    employment_type: str = ""
    departments: list[str] = field(default_factory=list)
    # Builds (description, pay) on demand. HTML to text is most of the CPU cost of sourcing and most postings are
    # dropped on their title alone, so the text is only made for postings that pass the title checks.
    pending: Callable[[], tuple[str, str]] | None = field(default=None, repr=False, compare=False)

    def materialize(self) -> Posting:
        if self.pending is not None:
            desc, pay = self.pending()
            self.description = desc
            self.pay = self.pay or pay
            self.pending = None
        return self


@dataclass
class Job:
    key: str
    company: str
    role: str
    status: str = STATUS_NEW
    track: str = ""
    location: str = ""
    pay: str = ""
    posted: str = ""
    fit: str = ""
    score: float = 0.0
    ats: str = ""
    ats_slug: str = ""
    ats_job_id: str = ""
    apply_url: str = ""
    desc_text: str = ""
    file_key: str = ""
    resume_file: str = ""
    gaps: str = "[]"
    notes: str = ""
    needs_reason: str = ""
    added_at: str = ""
    decided_at: str = ""
    submitted_at: str = ""
    attempts: int = 0
    lock_until: str = ""
    title_norm: str = ""
    company_norm: str = ""

    @classmethod
    def from_row(cls, row: Any) -> Job:
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in dict(row).items() if k in names})

    @property
    def gap_list(self) -> list[str]:
        try:
            data = json.loads(self.gaps or "[]")
        except ValueError:
            return []
        return [str(x) for x in data] if isinstance(data, list) else []
