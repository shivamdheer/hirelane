"""Greenhouse public job board API. No key needed."""
from __future__ import annotations

from collections.abc import Callable

from ..models import Posting
from ..textutil import html_to_text, strip_tracking
from .base import FetchResult, HttpClient, job_dicts, pay_from_text, to_date

ATS = "greenhouse"


def board_url(slug: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def job_url(slug: str, job_id: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"


def hosted_url(slug: str, job_id: str) -> str:
    return f"https://job-boards.greenhouse.io/{slug}/jobs/{job_id}"


def _lazy(content: str) -> Callable[[], tuple[str, str]]:
    def build() -> tuple[str, str]:
        desc = html_to_text(content)
        return desc, pay_from_text(desc)
    return build


def parse(data: object, slug: str, company: str) -> list[Posting]:
    out: list[Posting] = []
    for j in job_dicts(data):
        job_id = str(j.get("id", ""))
        if not job_id:
            continue
        offices = [o.get("location") or o.get("name") or "" for o in j.get("offices") or []]
        loc = ((j.get("location") or {}).get("name") or "").strip()
        location = loc or " / ".join(o for o in offices if o)
        out.append(Posting(
            ats=ATS, slug=slug, job_id=job_id, company=j.get("company_name") or company,
            title=(j.get("title") or "").strip(), location=location,
            url=strip_tracking(j.get("absolute_url") or hosted_url(slug, job_id)),
            apply_url=hosted_url(slug, job_id), posted=to_date(j.get("first_published") or j.get("updated_at")),
            remote="remote" in location.lower(), pending=_lazy(j.get("content") or ""),
            departments=[d.get("name", "") for d in j.get("departments") or []],
        ))
    return out


async def fetch(client: HttpClient, slug: str, company: str) -> tuple[FetchResult, list[Posting]]:
    r = await client.get_json(board_url(slug))
    return r, (parse(r.data, slug, company) if r.ok else [])


async def is_open(client: HttpClient, slug: str, job_id: str) -> bool | None:
    """True when open, False when closed (404), None when unknown."""
    r = await client.get_json(job_url(slug, job_id))
    if r.status == 200:
        return True
    if r.status == 404:
        return False
    return None
