"""Posting filters: track match, location and freshness. Each returns a reason when it drops a posting."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from . import knockout, level, salary
from .models import Posting
from .profile import Profile, SearchRules, Track

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}
COUNTRY_NAMES = {"US": ("united states", "usa", "u.s."), "CA": ("canada",), "GB": ("united kingdom", "uk", "england"),
                 "IN": ("india",), "DE": ("germany",), "AU": ("australia",)}
OTHER_COUNTRY_HINTS = ("canada", "united kingdom", "india", "germany", "australia", "ireland", "france", "brazil",
                       "mexico", "singapore", "netherlands", "poland", "spain", "japan", "israel", "emea", "apac",
                       "latam")


@dataclass(frozen=True)
class Verdict:
    keep: bool
    reason: str = ""
    track: str = ""


def match_track(title: str, profile: Profile) -> Track | None:
    """The track whose longest title phrase appears in the title, ignoring tracks that exclude it."""
    low = (title or "").lower()
    best: tuple[int, Track] | None = None
    for track in profile.tracks:
        if any(x in low for x in track.exclude_titles):
            continue
        for phrase in track.titles:
            if phrase in low and (best is None or len(phrase) > best[0]):
                best = (len(phrase), track)
    return best[1] if best else None


def _state_codes(location: str) -> set[str]:
    return set(re.findall(r"\b([A-Z]{2})\b", location or "")) & US_STATE_CODES


def location_ok(p: Posting, rules: SearchRules) -> tuple[bool, str]:
    loc = (p.location or "").lower()
    if rules.scope == "anywhere":
        return True, ""
    remote = p.remote or "remote" in loc
    if rules.scope == "regions":
        if any(r in loc for r in rules.regions):
            return True, ""
        if remote and rules.include_remote and _in_countries(p, rules):
            return True, ""
        return False, "location: outside your regions"
    if not _in_countries(p, rules):
        return False, "location: outside your countries"
    if remote and not rules.include_remote:
        return False, "location: remote roles excluded"
    return True, ""


def _in_countries(p: Posting, rules: SearchRules) -> bool:
    loc = (p.location or "").lower()
    wanted = {c.upper() for c in rules.countries}
    names = tuple(n for c in wanted for n in COUNTRY_NAMES.get(c, (c.lower(),)))
    if any(re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", loc) for n in names):
        return True
    if "US" in wanted and _state_codes(p.location):
        return True
    if p.country and p.country.upper() in wanted:
        return True
    if any(h in loc for h in OTHER_COUNTRY_HINTS):
        return False
    # A bare "Remote" gives no country, so it is kept and the description gets the last word.
    return (p.remote or "remote" in loc) and not p.country


def fresh(p: Posting, within_days: int, today: date) -> bool:
    if not p.posted:
        return True
    try:
        posted = date.fromisoformat(p.posted)
    except ValueError:
        return True
    return posted >= today - timedelta(days=within_days)


def check_title(p: Posting, profile: Profile) -> Verdict:
    """The cheap checks that run before a description is converted."""
    track = match_track(p.title, profile)
    if track is None:
        return Verdict(False, "title: matches none of your tracks")
    ok, why = location_ok(p, profile.search)
    if not ok:
        return Verdict(False, why, track.name)
    return Verdict(True, track=track.name)


def check_description(p: Posting, profile: Profile, within_days: int, today: date) -> Verdict:
    """The checks that read the description. Call after materialize()."""
    track = match_track(p.title, profile)
    name = track.name if track else ""
    if not fresh(p, within_days, today):
        return Verdict(False, f"freshness: posted {p.posted}", name)
    verdict = level.assess(p.title, p.description, profile.level)
    if not verdict.keep:
        return Verdict(False, verdict.reason, name)
    if salary.below_floor(p.pay, profile.salary.floor):
        return Verdict(False, f"pay: posted {p.pay}, below your floor of {profile.salary.floor:,}", name)
    ko = knockout.check(p.title, p.description, profile.knockouts)
    if not ko.eligible:
        return Verdict(False, f"not eligible: {ko.reason}", name)
    return Verdict(True, track=name)
