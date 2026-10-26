"""Greenhouse adapter. It opens the hosted embed form directly, so the company's own careers page is never involved."""
from __future__ import annotations

from typing import Any

from ..models import Job
from .base import Adapter


class GreenhouseAdapter(Adapter):
    ats = "greenhouse"
    ready_selector = "#application-form, form#application_form, input[id^=question_], #first_name"
    submit_selector = "button[type=submit]:has-text('Submit'), #submit_app"
    confirm_patterns = (r"thank you for applying", r"application (has been )?(submitted|received)",
                        r"we.?ve received your application")

    def form_url(self, job: Job) -> str:
        if not (job.ats_slug and job.ats_job_id.isdigit()):
            raise ValueError("a Greenhouse job needs a board slug and a numeric job id")
        return f"https://job-boards.greenhouse.io/embed/job_app?for={job.ats_slug}&token={job.ats_job_id}"

    def confirmed_now(self, page: Any) -> bool:
        return "/confirmation" in page.url or super().confirmed_now(page)
