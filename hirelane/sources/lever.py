"""Lever public postings API. No key needed."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..models import Posting
from ..textutil import html_to_text, strip_tracking
from .base import FetchResult, HttpClient, pay_from_text, to_date

ATS = "lever"


def board_url(slug: str) -> str:
    return f"https://api.lever.co/v0/postings/{slug}?mode=json"


def job_url(slug: str, job_id: str) -> str:
    return f"https://api.lever.co/v0/postings/{slug}/{job_id}"


def _salary(j: dict[str, Any]) -> str:
    sr = j.get("salaryRange") or {}
    lo, hi = sr.get("min"), sr.get("max")
    if lo and hi and str(sr.get("interval", "")).startswith("per-year"):
        return f"${int(lo):,}-${int(hi):,}"
    return ""


def _lazy(j: dict[str, Any]) -> Callable[[], tuple[str, str]]:
    def build() -> tuple[str, str]:
        parts = [j.get("descriptionPlain") or html_to_text(j.get("description") or "")]
        for lst in j.get("lists") or []:
            parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content') or '')}")
        parts.append(j.get("additionalPlain") or "")
        desc = html_to_text("\n\n".join(p for p in parts if p))
        return desc, pay_from_text(desc)
    return build


def parse(data: list[dict[str, Any]], slug: str, company: str) -> list[Posting]:
    out: list[Posting] = []
    for j in data or []:
        if not isinstance(j, dict) or not j.get("id"):
            continue
        cats = j.get("categories") or {}
        loc = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        out.append(Posting(
            ats=ATS, slug=slug, job_id=str(j["id"]), company=company, title=(j.get("text") or "").strip(),
            location=loc, url=strip_tracking(j.get("hostedUrl") or ""),
            apply_url=strip_tracking(j.get("applyUrl") or ""), posted=to_date(j.get("createdAt") or j.get("updatedAt")),
            pending=_lazy(j), remote=(j.get("workplaceType") == "remote") or "remote" in loc.lower(),
            country=j.get("country") or "", pay=_salary(j), employment_type=cats.get("commitment") or "",
            departments=[x for x in (cats.get("department"), cats.get("team")) if x],
        ))
    return out


async def fetch(client: HttpClient, slug: str, company: str) -> tuple[FetchResult, list[Posting]]:
    r = await client.get_json(board_url(slug))
    return r, (parse(r.data, slug, company) if r.ok and isinstance(r.data, list) else [])


async def is_open(client: HttpClient, slug: str, job_id: str) -> bool | None:
    r = await client.get_json(job_url(slug, job_id))
    if r.status == 200:
        return True
    if r.status == 404:
        return False
    return None
