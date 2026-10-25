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
