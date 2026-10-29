"""Ashby adapter. The application form lives at /application under the posting URL."""
from __future__ import annotations

from ..models import Job
from .base import Adapter


class AshbyAdapter(Adapter):
    ats = "ashby"
    ready_selector = "form, [class*=ashby-application-form]"
    submit_selector = "button[type=submit]:has-text('Submit')"
    confirm_patterns = (r"application (was )?(successfully )?submitted", r"thank you for applying",
                        r"we.?ve received your application")

    def form_url(self, job: Job) -> str:
        if not (job.ats_slug and job.ats_job_id):
            raise ValueError("an Ashby job needs a board slug and a posting id")
        return f"https://jobs.ashbyhq.com/{job.ats_slug}/{job.ats_job_id}/application"
