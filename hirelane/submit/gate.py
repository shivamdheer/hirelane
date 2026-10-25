"""Pre-flight checks before a form is opened. Code only, independent of the filler.

A job that fails any check is not touched. It goes to the user with the reason.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings
from ..db import DB
from ..models import SUPPORTED_ATS, Job
from ..textutil import file_key, host_matches, host_of

ALLOWED_HOSTS = {
    "greenhouse": ("greenhouse.io",),
    "lever": ("lever.co",),
    "ashby": ("ashbyhq.com",),
}
COUNTED_PHASES = ("filled", "submit_clicked")


@dataclass
class Preflight:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def url_allowed(url: str, ats: str) -> bool:
    host = host_of(url)
    return any(host_matches(host, d) for d in ALLOWED_HOSTS.get(ats, ()))


def runs_today(db: DB, day: str) -> int:
    """Forms already opened and filled or submitted today. The daily cap counts both."""
    return db.count_attempts(day, COUNTED_PHASES)


def preflight(job: Job, db: DB, settings: Settings, day: str) -> Preflight:
    out = Preflight()
    if job.ats not in SUPPORTED_ATS:
        out.problems.append(f"{job.ats or 'this'} forms are not supported, apply by hand")
        return out
    if not url_allowed(job.apply_url, job.ats):
        out.problems.append(f"apply URL is outside the {job.ats} domains: {job.apply_url[:80]}")
    if runs_today(db, day) >= settings.daily_cap:
        out.problems.append(f"daily cap of {settings.daily_cap} reached")
    record = db.get_resume(job.key)
    if record is None or not record["ok"]:
        out.problems.append("no resume that passed the ATS gate")
        return out
    path = Path(record["path"])
    if not path.exists():
        out.problems.append(f"resume file is missing: {path.name}")
        return out
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        out.problems.append("resume file changed after it passed the ATS gate")
    if file_key(job.company) not in path.name:
        out.problems.append(f"resume file {path.name} does not belong to {job.company}")
    return out
