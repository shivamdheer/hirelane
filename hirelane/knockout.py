"""Hard requirements a posting may state that the user clearly does not meet.

A doubtful case is never a knockout. The form and the match score decide those.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .profile import Knockouts

NO_SPONSORSHIP = re.compile(
    r"(?:unable|not able|cannot|can't|do not|does not|don't|will not|won't) (?:to )?(?:provide )?(?:visa )?sponsor|"
    r"no (?:visa )?sponsorship|without (?:the need for )?(?:visa )?sponsorship|"
    r"must be (?:legally )?authori[sz]ed to work[^.]{0,40}without", re.I)
CLEARANCE = re.compile(
    r"(?:active|current)\s+(?:secret|top secret|ts/sci|security|public trust)\s+clearance|"
    r"(?:security|secret|top secret|ts/sci|public trust) clearance\s+(?:is\s+)?required|"
    r"u\.?s\.? citizen(?:ship)?\s+(?:is\s+)?(?:required|only)|must be (?:a )?(?:u\.?s\.?|united states) citizen|"
    r"us persons? only", re.I)
CITIZEN_OR_AUTH = re.compile(r"citizen\s+(?:or|and)\s+(?:a\s+)?(?:permanent|authori[sz]ed|lawful|eligible|green)", re.I)
PHD_REQUIRED = re.compile(
    r"(?:ph\.?d\.?|doctorate|doctoral degree)\b[^.\n]{0,40}\b(?:required|is a must|must have|minimum)|"
    r"(?:requires?|must (?:have|hold)|minimum qualifications?:?)[^.\n]{0,30}(?:ph\.?d\.?|doctorate|doctoral)", re.I)
PHD_OPTIONAL = re.compile(r"(?:ph\.?d\.?|doctorate)[^.\n]{0,40}\b(?:preferred|a plus|nice to have|or equivalent|bonus)|"
                          r"(?:master'?s?|bachelor'?s?)[^.\n]{0,40}\bor\b[^.\n]{0,12}(?:ph\.?d\.?|doctorate)", re.I)
DEGREE_RANK = {"": 0, "none": 0, "bachelors": 1, "masters": 2, "phd": 3}
CONTEXT = 20
CONTEXT_AFTER = 60


@dataclass(frozen=True)
class KnockoutVerdict:
    eligible: bool
    reason: str = ""


def check(title: str, desc: str, rules: Knockouts) -> KnockoutVerdict:
    text = desc or ""
    low = f"{title}\n{text}".lower()
    if rules.needs_sponsorship and (m := NO_SPONSORSHIP.search(text)):
        return KnockoutVerdict(False, f"no visa sponsorship ({m.group(0).strip()[:40]})")
    if not rules.has_clearance and (m := CLEARANCE.search(text) or CLEARANCE.search(title or "")):
        nearby = text[max(0, m.start() - CONTEXT): m.end() + CONTEXT_AFTER]
        if not CITIZEN_OR_AUTH.search(nearby):
            return KnockoutVerdict(False, f"citizenship or clearance required ({m.group(0).strip()[:40]})")
    holds_phd = DEGREE_RANK.get(rules.degree, 0) >= DEGREE_RANK["phd"]
    if not holds_phd and PHD_REQUIRED.search(text) and not PHD_OPTIONAL.search(text):
        return KnockoutVerdict(False, "the posting requires a PhD")
    for term in rules.avoid_terms:
        if term and term in low:
            return KnockoutVerdict(False, f"contains your avoid term {term!r}")
    return KnockoutVerdict(True)
