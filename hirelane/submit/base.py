"""The adapter base class. An adapter knows one ATS: where its form lives and how it confirms a submission.

Everything generic (scanning, planning, filling, reading back) lives here so the three adapters stay small.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..answers import AnswerBank
from ..models import Job
from ..textutil import host_of
from . import fields as F
from .gate import url_allowed
from .optmatch import match_option
from .plan import Plan, make_plan

MAX_PASSES = 3
HTTP_ERROR_FLOOR = 400
CONFIRM_TIMEOUT_MS = 20_000
CONFIRM_POLL_MS = 500
CAPTCHA_SELECTORS = (
    'iframe[src*="recaptcha"]:visible', 'iframe[src*="hcaptcha"]:visible', 'iframe[src*="turnstile"]:visible',
    '[class*="captcha"]:visible',
)
CAPTCHA_TEXT = re.compile(r"verify (that )?you are (a )?human|are you a robot|complete the (captcha|security check)",
                          re.I)


def _already_set(f: F.FormField, value: str) -> bool:
    if F.values_match(value, f.value):
        return True
    choice_kinds = ("select", "radio", "checkboxes", "checkbox", "combobox")
    return f.kind in choice_kinds and bool(f.value.strip()) and match_option(value, [f.value]) is not None


class FormUnavailable(RuntimeError):
    """The posting is closed or the form did not load."""


@dataclass
class FillReport:
    fields: list[F.FormField] = field(default_factory=list)
    plan: Plan = field(default_factory=Plan)
    fill_problems: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    captcha: bool = False


class Adapter:
    ats = ""
    ready_selector = "form"
    submit_selector = "button[type=submit]"
    confirm_patterns: tuple[str, ...] = (r"thank you for applying", r"application (has been )?(submitted|received)")

    def form_url(self, job: Job) -> str:
        return job.apply_url

    def open(self, page: Any, job: Job) -> None:
        url = self.form_url(job)
        if not url_allowed(url, self.ats):
            raise FormUnavailable(f"refusing to open {url[:80]}")
        response = page.goto(url, wait_until="domcontentloaded")
        if response is not None and response.status >= HTTP_ERROR_FLOOR:
            raise FormUnavailable(f"the form returned HTTP {response.status}")
        if not url_allowed(page.url, self.ats):
            raise FormUnavailable(f"redirected outside the {self.ats} domains to {host_of(page.url)}")
        try:
            page.wait_for_selector(self.ready_selector, timeout=F.FIELD_TIMEOUT_MS)
        except Exception as e:
            raise FormUnavailable("the application form did not appear, the posting may be closed") from e
        page.wait_for_timeout(F.SETTLE_MS)

    def captcha_present(self, page: Any) -> bool:
        for sel in CAPTCHA_SELECTORS:
            if page.locator(sel).count():
                return True
        try:
            return bool(CAPTCHA_TEXT.search(page.inner_text("body")))
        except Exception:
            return False

    def fill(self, page: Any, resume_path: Path, answers: AnswerBank) -> FillReport:
        """Upload the resume, answer every field the answer bank covers, and read the form back."""
        report = FillReport()
        uploaded = False
        for _pass in range(MAX_PASSES):
            report.fields = F.scan(page)
            report.plan = make_plan(report.fields, answers)
            by_fid = {f.fid: f for f in report.fields}
            changed = False
            resume = by_fid.get(report.plan.resume_fid)
            if resume is not None and not uploaded and resume.value != resume_path.name:
                problem = F.attach_file(page, resume, str(resume_path))
                if problem:
                    report.fill_problems.append(f"resume upload: {problem}")
                uploaded = changed = True
            for fid, value in report.plan.values.items():
                f = by_fid[fid]
                if _already_set(f, value):
                    continue
                problem = F.fill_field(page, f, value)
                if problem:
                    report.fill_problems.append(f"{f.label[:60]}: {problem}")
                changed = True
            if not changed:
                break
        report.fields = F.scan(page)
        report.plan = make_plan(report.fields, answers)
        # Fids come from document order, so the plan made on the final scan matches the fields read back.
        report.page_errors = F.page_errors(page)
        report.captcha = self.captcha_present(page)
        return report

    def click_submit(self, page: Any) -> None:
        page.locator(self.submit_selector).first.click(timeout=F.FIELD_TIMEOUT_MS)

    def confirmed_now(self, page: Any) -> bool:
        """One look at the page for the ATS's own confirmation."""
        try:
            text = page.inner_text("body")
        except Exception:
            return False
        return any(re.search(p, text, re.I) for p in self.confirm_patterns)

    def confirmed(self, page: Any) -> bool:
        """Wait a short while for the confirmation to appear after a submit."""
        for _ in range(CONFIRM_TIMEOUT_MS // CONFIRM_POLL_MS):
            if self.confirmed_now(page):
                return True
            page.wait_for_timeout(CONFIRM_POLL_MS)
        return False
