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
