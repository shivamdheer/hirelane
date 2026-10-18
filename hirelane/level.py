"""Seniority filter. Code only, no model.

A posting is dropped when its title signals a level above the user's, or when the description asks for more years
of experience than ``level.max_years``. A description that states no requirement is kept, because the form and the
match score are better judges than a guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .profile import LevelRules
from .textutil import RANGE_SEP

MAX_PLAUSIBLE_YEARS = 20
ROMAN_ABOVE_ONE = re.compile(r"\b(?:II|III|IV)\b")
YEARS_ASKED = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:" + RANGE_SEP + r"\s*(\d{1,2})\s*(?:\+|plus)?\s*)?(?:years?|yrs?)"
    r"(?:'|\N{RIGHT SINGLE QUOTATION MARK})?s?\s*(?:of\s+)?(?:\w+\s+){0,4}?"
    r"(?:experience|exp\b|background|working)", re.I)
YEARS_BARE = re.compile(r"(?:minimum|at least|requires?|required)[^.]{0,30}?(\d{1,2})\s*\+?\s*years?\b"
                        r"(?!\s*(?:of age|old))", re.I)
OPTIONAL_NEARBY = re.compile(r"preferred|a plus|nice to have|bonus|ideally|desired|helpful|is an advantage|welcome|"
                             r"not required|not necessary", re.I)
CONTEXT_BEFORE = 40
CONTEXT_AFTER = 60
ROMAN_LEVEL_YEARS_CEILING = 3          # a numeral level above I only matters for a limit below this


@dataclass(frozen=True)
class LevelVerdict:
    keep: bool
    reason: str = ""
    years: int | None = None


def years_asked(desc: str) -> tuple[int | None, int | None]:
    """The lowest and highest number of years a posting asks for. A range counts at both ends."""
    text = desc or ""
    lows: list[int] = []
    highs: list[int] = []
    for rx in (YEARS_ASKED, YEARS_BARE):
        for m in rx.finditer(text):
            if OPTIONAL_NEARBY.search(text[max(0, m.start() - CONTEXT_BEFORE): m.end() + CONTEXT_AFTER]):
                continue
            a = int(m.group(1))
            b = int(m.group(2)) if rx is YEARS_ASKED and m.group(2) else a
            if 0 <= a <= MAX_PLAUSIBLE_YEARS and 0 <= b <= MAX_PLAUSIBLE_YEARS:
                lows.append(a)
                highs.append(max(a, b))
    return (min(lows), max(highs)) if lows else (None, None)


def senior_word_in_title(title: str, rules: LevelRules) -> str:
    low = (title or "").lower()
    probe = low
    for phrase in rules.allow_titles:
        probe = probe.replace(phrase, " ")
    for word in rules.senior_words:
        if re.search(rf"\b{re.escape(word)}\b\.?", probe):
            return word
    if rules.max_years < ROMAN_LEVEL_YEARS_CEILING and ROMAN_ABOVE_ONE.search(title or ""):
        return ROMAN_ABOVE_ONE.search(title or "").group(0)  # type: ignore[union-attr]
    return ""


def assess(title: str, desc: str, rules: LevelRules) -> LevelVerdict:
    lo, _hi = years_asked(desc)
    word = senior_word_in_title(title, rules)
    if word:
        return LevelVerdict(False, f"level: the title says {word}", lo)
    if lo is not None and lo > rules.max_years:
        return LevelVerdict(False, f"level: the posting asks for {lo}+ years, your limit is {rules.max_years}", lo)
    return LevelVerdict(True, years=lo)
