"""Decide what to type into each field. Pure logic, no browser, so it is easy to test."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..answers import AnswerBank
from .fields import FormField

RESUME_LABEL = re.compile(r"\b(resume|cv|curriculum)\b", re.I)
COVER_LABEL = re.compile(r"cover letter", re.I)
OPTIONAL_SKIP = re.compile(r"cover letter|additional (file|document|attachment)|other (file|document)", re.I)
MIN_TEXT_REPLY = 2


@dataclass
class Plan:
    values: dict[str, str] = field(default_factory=dict)      # fid to the text to enter
    sources: dict[str, str] = field(default_factory=dict)     # fid to where the answer came from
    resume_fid: str = ""
    unanswered: list[FormField] = field(default_factory=list)  # required, and no rule matched
    skipped: list[FormField] = field(default_factory=list)     # optional, and no rule matched
    unsupported: list[FormField] = field(default_factory=list)  # required file uploads other than the resume


def make_plan(fields: list[FormField], bank: AnswerBank) -> Plan:
    plan = Plan()
    for f in fields:
        if f.kind == "file":
            if RESUME_LABEL.search(f.label) and not COVER_LABEL.search(f.label) and not plan.resume_fid:
                plan.resume_fid = f.fid
            elif f.required and not OPTIONAL_SKIP.search(f.label):
                plan.unsupported.append(f)
            continue
        hit = bank.resolve(f.label)
        if hit is not None and len(hit.answer) >= 1:
            if f.maxlength and len(hit.answer) > f.maxlength:
                plan.unanswered.append(f)         # an answer that does not fit is never silently cut
                continue
            plan.values[f.fid] = hit.answer
            plan.sources[f.fid] = hit.source
        elif f.required:
            plan.unanswered.append(f)
        else:
            plan.skipped.append(f)
    return plan
