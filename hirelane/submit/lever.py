"""Lever adapter. The apply form lives at /apply under the posting URL."""
from __future__ import annotations

from typing import Any

from ..models import Job
from .base import Adapter


class LeverAdapter(Adapter):
    ats = "lever"
    ready_selector = "form#application-form, .application-form, input[name=name]"
    submit_selector = "#btn-submit, button[type=submit]:has-text('Submit')"
    confirm_patterns = (r"application (has been )?(submitted|received)", r"thank you for applying",
                        r"your application was submitted")

    def form_url(self, job: Job) -> str:
        if not (job.ats_slug and job.ats_job_id):
            raise ValueError("a Lever job needs a board slug and a posting id")
        return f"https://jobs.lever.co/{job.ats_slug}/{job.ats_job_id}/apply"

    def confirmed_now(self, page: Any) -> bool:
        return page.url.rstrip("/").endswith("/thanks") or super().confirmed_now(page)
