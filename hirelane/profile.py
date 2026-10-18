"""The user's profile: who they are, which roles they want, and the limits on what to apply to.

Loaded from config/profile.yaml. All of it is the user's own data, nothing here is specific to one person.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import get_paths

DEFAULT_MAX_YEARS = 2
DEFAULT_SENIOR_WORDS = ("senior", "sr", "staff", "lead", "principal", "director", "head", "vp", "manager", "architect")


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class Track:
    """One kind of role the user is looking for."""
    name: str
    label: str
    titles: tuple[str, ...]                    # a posting title must contain one of these phrases
    skills: tuple[str, ...] = ()               # terms that count toward the match score
    exclude_titles: tuple[str, ...] = ()       # phrases that rule a title out for this track


@dataclass(frozen=True)
class LevelRules:
    max_years: int = DEFAULT_MAX_YEARS         # the highest minimum experience a posting may ask for
    senior_words: tuple[str, ...] = DEFAULT_SENIOR_WORDS
    # title phrases that override senior_words, for example "associate product manager"
    allow_titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchRules:
    scope: str = "country"                     # anywhere | country | regions
    countries: tuple[str, ...] = ("US",)
    regions: tuple[str, ...] = ()              # place names matched against the posting location
    include_remote: bool = True


@dataclass(frozen=True)
class Salary:
    floor: int = 0                             # drop a posting whose posted maximum is below this, 0 disables
    expectation: str = ""                      # what to type into "salary expectation" fields


@dataclass(frozen=True)
class Knockouts:
    """Hard requirements a posting may state that the user does not meet."""
    needs_sponsorship: bool = False
    has_clearance: bool = False
    degree: str = ""                           # highest degree held: none, bachelors, masters, phd
    avoid_terms: tuple[str, ...] = ()          # any of these in a posting rules it out


@dataclass(frozen=True)
class Profile:
    name: str
    email: str
    phone: str = ""
    city: str = ""
    region: str = ""
    country: str = "US"
    postal_code: str = ""
    links: dict[str, str] = field(default_factory=dict)
    tracks: tuple[Track, ...] = ()
    level: LevelRules = field(default_factory=LevelRules)
    search: SearchRules = field(default_factory=SearchRules)
    salary: Salary = field(default_factory=Salary)
    knockouts: Knockouts = field(default_factory=Knockouts)

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name.split() else ""

    @property
    def last_name(self) -> str:
        parts = self.name.split()
        return parts[-1] if len(parts) > 1 else ""

    def track(self, name: str) -> Track | None:
        return next((t for t in self.tracks if t.name == name), None)


def _tuple(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def _track(raw: dict[str, Any]) -> Track:
    name = str(raw.get("name", "")).strip()
    titles = _tuple(raw.get("titles"))
    if not name or not titles:
        raise ProfileError("each track needs a name and at least one title phrase")
    return Track(name=name, label=str(raw.get("label") or name), titles=tuple(t.lower() for t in titles),
                 skills=tuple(s.lower() for s in _tuple(raw.get("skills"))),
                 exclude_titles=tuple(t.lower() for t in _tuple(raw.get("exclude_titles"))))


def parse_profile(raw: dict[str, Any]) -> Profile:
    name = str(raw.get("name", "")).strip()
    email = str(raw.get("email", "")).strip()
    if not name or "@" not in email:
        raise ProfileError("profile needs a name and an email address")
    tracks = tuple(_track(t) for t in raw.get("tracks") or [])
    if len({t.name for t in tracks}) != len(tracks):
        raise ProfileError("track names must be unique")
    loc = raw.get("location") or {}
    level_raw = raw.get("level") or {}
    search_raw = raw.get("search") or {}
    salary_raw = raw.get("salary") or {}
    ko_raw = raw.get("knockouts") or {}
    search = SearchRules(
        scope=str(search_raw.get("scope", "country")),
        countries=_tuple(search_raw.get("countries")) or ("US",),
        regions=tuple(r.lower() for r in _tuple(search_raw.get("regions"))),
        include_remote=bool(search_raw.get("include_remote", True)),
    )
    if search.scope not in ("anywhere", "country", "regions"):
        raise ProfileError("search.scope must be anywhere, country or regions")
    return Profile(
        name=name, email=email, phone=str(raw.get("phone", "") or ""), city=str(loc.get("city", "") or ""),
        region=str(loc.get("region", "") or ""), country=str(loc.get("country", "US") or "US"),
        postal_code=str(loc.get("postal_code", "") or ""),
        links={str(k): str(v) for k, v in (raw.get("links") or {}).items()},
        tracks=tracks,
        level=LevelRules(
            max_years=int(level_raw.get("max_years", DEFAULT_MAX_YEARS)),
            senior_words=tuple(w.lower() for w in _tuple(level_raw.get("senior_words"))) or DEFAULT_SENIOR_WORDS,
            allow_titles=tuple(t.lower() for t in _tuple(level_raw.get("allow_titles")))),
        search=search,
        salary=Salary(floor=int(salary_raw.get("floor", 0) or 0),
                      expectation=str(salary_raw.get("expectation", "") or "")),
        knockouts=Knockouts(
            needs_sponsorship=bool(ko_raw.get("needs_sponsorship", False)),
            has_clearance=bool(ko_raw.get("has_clearance", False)),
            degree=str(ko_raw.get("degree", "") or ""),
            avoid_terms=tuple(t.lower() for t in _tuple(ko_raw.get("avoid_terms")))),
    )


def load_profile(path: Path | None = None) -> Profile:
    p = path or get_paths().profile_file
    if not p.exists():
        raise ProfileError(f"{p} not found, run `hirelane init` first")
    return parse_profile(yaml.safe_load(p.read_text()) or {})
