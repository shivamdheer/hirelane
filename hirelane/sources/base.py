"""HTTP client and date helpers shared by the board sources."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Any

import httpx

from ..config import local_tz
from ..textutil import RANGE_SEP

log = logging.getLogger(__name__)

TIMEOUT_S = 15.0
CONCURRENCY = 8
RETRY_SLEEP_S = 2.0
MAX_RETRY_AFTER_S = 30.0
MAX_BYTES = 30_000_000
USER_AGENT = "hirelane/0.1 (personal job search tool)"

PAY_RE = re.compile(
    r"\$\s?\d{2,3}(?:,\d{3})+(?:\.\d+)?\s*(?:[kK])?\s*" + RANGE_SEP + r"\s*\$?\s?\d{2,3}(?:,\d{3})+(?:\.\d+)?|"
    r"\$\s?\d{2,3}(?:\.\d+)?\s?[kK]\s*" + RANGE_SEP + r"\s*\$?\s?\d{2,3}(?:\.\d+)?\s?[kK]")


@dataclass
class FetchResult:
    url: str
    status: int          # HTTP status, 0 for a network failure
    data: Any = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 and self.data is not None


def to_date(value: Any, tz: tzinfo | None = None) -> str:
    """An ISO string or epoch milliseconds to YYYY-MM-DD in the user's zone. Empty when unknown."""
    if value in (None, ""):
        return ""
    zone = tz or local_tz()
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            dt = datetime.fromtimestamp(int(value) / 1000, tz=UTC)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(zone).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return ""


def job_dicts(data: Any) -> list[dict[str, Any]]:
    """The job objects under a board payload's "jobs" key. A malformed payload or entry yields nothing."""
    jobs = data.get("jobs") if isinstance(data, dict) else None
    return [j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []


def pay_from_text(text: str) -> str:
    m = PAY_RE.search(text or "")
    return re.sub(r"\s+", " ", m.group(0)).replace("\N{EN DASH}", "-").replace("\N{EM DASH}", "-") if m else ""


class HttpClient:
    """Async JSON fetcher with a concurrency limit, one retry, and one honored Retry-After."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, concurrency: int = CONCURRENCY,
                 retry_sleep_s: float = RETRY_SLEEP_S) -> None:
        self._client = httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=True, transport=transport,
                                         headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        self._sem = asyncio.Semaphore(concurrency)
        self.retry_sleep_s = retry_sleep_s

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def get_json(self, url: str) -> FetchResult:
        async with self._sem:
            for attempt in range(2):
                try:
                    r = await self._client.get(url)
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    if attempt == 0:
                        await asyncio.sleep(self.retry_sleep_s)
                        continue
                    return FetchResult(url, 0, error=type(e).__name__)
                if r.status_code == 429 and attempt == 0:
                    retry_after = r.headers.get("Retry-After", "")
                    numeric = retry_after.replace(".", "", 1).isdigit()
                    await asyncio.sleep(min(float(retry_after), MAX_RETRY_AFTER_S) if numeric else self.retry_sleep_s)
                    continue
                if r.status_code >= 500 and attempt == 0:
                    await asyncio.sleep(self.retry_sleep_s)
                    continue
                if r.status_code != 200:
                    return FetchResult(url, r.status_code, error=f"HTTP {r.status_code}")
                if len(r.content) > MAX_BYTES:
                    return FetchResult(url, 413, error="response too large")
                try:
                    return FetchResult(url, 200, r.json())
                except ValueError:
                    return FetchResult(url, 200, None, error="not JSON")
            return FetchResult(url, 0, error="retries exhausted")
