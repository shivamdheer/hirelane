"""Ashby public job board API. No key needed."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..models import Posting
from ..textutil import html_to_text, strip_tracking
from .base import FetchResult, HttpClient, job_dicts, pay_from_text, to_date

ATS = "ashby"
MAX_PLAIN_CHARS = 40_000


def board_url(slug: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def _pay(j: dict[str, Any]) -> str:
    comp = j.get("compensation") or {}
    return comp.get("scrapeableCompensationSalarySummary") or comp.get("compensationTierSummary") or ""


def _lazy(j: dict[str, Any]) -> Callable[[], tuple[str, str]]:
    def build() -> tuple[str, str]:
        desc = j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml") or "")
        desc = html_to_text(desc) if "<" in desc[:500] else desc[:MAX_PLAIN_CHARS]
        return desc, pay_from_text(desc)
    return build


def parse(data: object, slug: str, company: str) -> list[Posting]:
    out: list[Posting] = []
    for j in job_dicts(data):
        if not j.get("id") or j.get("isListed") is False:
            continue
        addr = (j.get("address") or {}).get("postalAddress") or {}
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        location = " / ".join(loc.strip() for loc in locs if loc and loc.strip())
        out.append(Posting(
            ats=ATS, slug=slug, job_id=str(j["id"]), company=company, title=(j.get("title") or "").strip(),
            location=location, url=strip_tracking(j.get("jobUrl") or ""),
            apply_url=strip_tracking(j.get("applyUrl") or f"https://jobs.ashbyhq.com/{slug}/{j['id']}/application"),
            posted=to_date(j.get("publishedAt")), pending=_lazy(j),
            remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
            country=addr.get("addressCountry") or "", pay=_pay(j), employment_type=j.get("employmentType") or "",
            departments=[x for x in (j.get("department"), j.get("team")) if x],
        ))
    return out


async def fetch(client: HttpClient, slug: str, company: str) -> tuple[FetchResult, list[Posting]]:
    r = await client.get_json(board_url(slug))
    return r, (parse(r.data, slug, company) if r.ok else [])


async def is_open(client: HttpClient, slug: str, job_id: str) -> bool | None:
    """Ashby has no single job endpoint, so a posting is open when the board still lists it."""
    r = await client.get_json(board_url(slug))
    if r.status == 404:
        return False
    if not r.ok or not isinstance(r.data, dict):
        return None
    return any(str(j.get("id")) == job_id and j.get("isListed", True) for j in job_dicts(r.data))
