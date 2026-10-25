"""The verification gate. It re-reads the form after filling and compares it with what must be there.

Any problem means the form is not submitted and the job goes to the user with the exact reason. The checks are
independent of the code that filled the form.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..textutil import norm_company
from .fields import FormField, values_match
from .optmatch import norm_value
from .plan import Plan

MIN_COMPANY_LEN = 4
TEXT_KINDS = ("text", "textarea", "email", "tel", "url", "number", "combobox", "date")
# Company names that are also ordinary words a form value may hold.
COMMON_WORDS = {"january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
                "sunday", "present", "other", "none", "united states", "remote", "yes", "no", "future", "current",
                "never", "today"}
JUNK = re.compile(r"^(select\.*|please select|choose\.*|--+|n/?a|none|null|undefined|nan|\[object object\]|"
                  r"lorem ipsum.*|test|tbd|x{3,}|\{.*\})$", re.I)


@dataclass
class Verification:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def other_company_hits(text: str, others: list[str], allowed: str) -> list[str]:
    low = (text or "").lower()
    hits = []
    for name in others:
        n = name.strip().lower()
        if len(n) < MIN_COMPANY_LEN or n in allowed or n in COMMON_WORDS:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", low):
            hits.append(name)
    return hits


def verify(fields: list[FormField], plan: Plan, *, resume_file: str, company: str, other_companies: list[str],
           allowed_text: str, page_errors: list[str], require_resume: bool = True) -> Verification:
    """Check the scanned, filled form.

    ``allowed_text`` is everything the user has approved (the fact bank text). A company name from it may appear in a
    field. Any other tracked company name in a field means a value was carried over from another application.
    """
    v = Verification()
    me = norm_company(company)
    others = sorted({c for c in other_companies if norm_company(c) not in ("", me)}, key=len, reverse=True)
    by_fid = {f.fid: f for f in fields}
    resume_seen = False
    unanswered = {f.fid for f in plan.unanswered}
    for f in fields:
        if f.kind == "file" and f.fid == plan.resume_fid:
            resume_seen = True
            if norm_value(f.value) != norm_value(resume_file):
                v.problems.append(f"resume field shows {f.value or 'nothing'!r}, expected {resume_file}")
        if f.required and not f.value.strip() and f.kind != "file" and f.fid not in unanswered:
            v.problems.append(f"required field empty: {f.label[:80]}")
        if f.kind == "file" and f.required and not f.value.strip() and f.fid != plan.resume_fid:
            v.problems.append(f"required upload empty: {f.label[:80]}")
        if f.kind in TEXT_KINDS and f.value and JUNK.match(f.value.strip()):
            v.problems.append(f"placeholder text in {f.label[:60]}: {f.value[:30]!r}")
        if f.kind in TEXT_KINDS and f.value and f.value not in f.options:
            for hit in other_company_hits(f.value, others, allowed_text.lower()):
                v.problems.append(f"another company's name {hit!r} in field {f.label[:60]}")
    if require_resume and not resume_seen:
        v.problems.append("no resume upload field found")
    for fid, expected in plan.values.items():
        planned = by_fid.get(fid)
        if planned is None:
            continue                  # a field may disappear once an earlier answer changes the form
        if planned.kind in ("select", "radio", "checkboxes", "combobox", "checkbox"):
            if not planned.value.strip():
                v.problems.append(f"{planned.label[:60]} is empty, expected {expected!r}")
            continue
        if not values_match(expected, planned.value):
            v.problems.append(f"{planned.label[:60]} reads {planned.value[:40]!r}, expected {expected[:40]!r}")
    for fld in plan.unanswered:
        v.problems.append(f"no answer for required question: {fld.label[:80]}")
    for fld in plan.unsupported:
        v.problems.append(f"required upload this tool does not provide: {fld.label[:80]}")
    v.problems += [f"page shows: {e[:80]}" for e in page_errors]
    return v
