"""Sourcing: poll the boards, filter, score and queue the best postings for the day."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from . import filters, scoring
from .companies import Company
from .config import Settings
from .db import DB, job_key
from .facts import FactBank
from .models import STATUS_NEW, Job, Posting
from .profile import Profile
from .sources import MODULES
from .sources.base import HttpClient
from .textutil import norm_company

log = logging.getLogger(__name__)

FIT_ORDER = {"A": 0, "B": 1, "C": 2}


@dataclass
class SourcingReport:
    boards_ok: int = 0
    boards_failed: list[str] = field(default_factory=list)
    seen: int = 0
    candidates: int = 0
    queued: list[Job] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)


async def fetch_all(client: HttpClient, companies: list[Company]) -> list[tuple[Company, list[Posting] | None]]:
    async def one(c: Company) -> tuple[Company, list[Posting] | None]:
        module = MODULES[c.ats]
        try:
            result, postings = await module.fetch(client, c.slug, c.name)
        except (AttributeError, KeyError, TypeError, ValueError) as e:   # a board that returns an unexpected shape
            log.info("board %s/%s could not be read: %s", c.ats, c.slug, type(e).__name__)
            return c, None
        if not result.ok:
            log.info("board %s/%s failed: %s", c.ats, c.slug, result.error)
            return c, None
        return c, postings

    return list(await asyncio.gather(*(one(c) for c in companies)))


def _reason_bucket(reason: str) -> str:
    return reason.split(":", 1)[0] or "other"


def select(candidates: list[scoring.Scored], limit: int, applied: set[str], db: DB) -> list[scoring.Scored]:
    """The best postings, at most one per company and none for a company already applied to."""
    ranked = sorted(candidates, key=lambda s: (FIT_ORDER[s.fit], -s.score, s.posting.company))
    chosen: list[scoring.Scored] = []
    taken: set[str] = set()
    for s in ranked:
        company = norm_company(s.posting.company)
        if company in taken or company in applied:
            continue
        if db.find_duplicate(s.posting.company, s.posting.title):
            continue
        taken.add(company)
        chosen.append(s)
        if len(chosen) >= limit:
            break
    return chosen


def process(boards: list[tuple[Company, list[Posting] | None]], db: DB, profile: Profile, settings: Settings,
            bank: FactBank, today: date, now: datetime) -> SourcingReport:
    report = SourcingReport()
    candidates: list[scoring.Scored] = []
    for company, postings in boards:
        if postings is None:
            report.boards_failed.append(f"{company.ats}/{company.slug}")
            continue
        report.boards_ok += 1
        meta_key = f"first_fetch:{company.ats}:{company.slug}"
        first_fetch = not db.get_meta(meta_key)
        db.set_meta(meta_key, now.isoformat())
        for p in postings:
            report.seen += 1
            if db.get_job(job_key(p)):
                continue
            first_sight = db.mark_seen(p.ats, p.job_id, now)
            if not p.posted and (first_fetch or not first_sight):
                # Without a posted date, only a posting first seen on a later fetch counts as new.
                report.dropped["freshness"] += 1
                continue
            verdict = filters.check_title(p, profile)
            if not verdict.keep:
                report.dropped[_reason_bucket(verdict.reason)] += 1
                continue
            p.materialize()
            verdict = filters.check_description(p, profile, settings.posted_within_days, today)
            if not verdict.keep:
                report.dropped[_reason_bucket(verdict.reason)] += 1
                continue
            track = profile.track(verdict.track)
            candidates.append(scoring.score(p, track, profile, bank))
    report.candidates = len(candidates)
    chosen = select(candidates, settings.daily_target, db.applied_companies(), db)
    for s in chosen:
        job = db.add_posting(s.posting, status=STATUS_NEW, track=s.track, fit=s.fit, score=s.score, now=now)
        db.update_job(job.key, gaps=json.dumps(s.gaps), notes=" | ".join(s.reasons))
        report.queued.append(db.get_job(job.key) or job)
    return report


async def run_sourcing(db: DB, profile: Profile, settings: Settings, bank: FactBank, companies: list[Company],
                       today: date, now: datetime, client: HttpClient | None = None) -> SourcingReport:
    own = client is None
    http = client or HttpClient()
    try:
        boards = await fetch_all(http, companies)
    finally:
        if own:
            await http.close()
    return process(boards, db, profile, settings, bank, today, now)
