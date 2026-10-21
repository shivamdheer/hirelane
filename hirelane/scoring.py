"""Deterministic match scoring. No model is involved, so it works without an API key.

The score rewards skills the user has confirmed and the posting asks for, a title that matches the track closely,
and a location that fits. It penalizes required skills the user has not confirmed. Those become gaps, and gaps are
never written onto a resume.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import terms
from .facts import FactBank
from .models import Posting
from .profile import Profile, Track
from .vocab import SKILL_VOCAB

WEIGHT_TITLE = 3.0
WEIGHT_HIT = 1.0
HIT_CAP = 8
WEIGHT_GAP = -0.75
GAP_CAP = 4
WEIGHT_LOCAL = 1.0
WEIGHT_REMOTE = 0.5
THRESHOLD_A = 7.0
THRESHOLD_B = 4.5
MAX_GAPS_FOR_A = 2
TITLE_WORDS_BONUS = 1.0


@dataclass
class Scored:
    posting: Posting
    track: str
    fit: str
    score: float
    reasons: list[str] = field(default_factory=list)
    hits: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


def vocabulary(track: Track | None, bank: FactBank) -> list[str]:
    extra = list(track.skills) if track else []
    return list(dict.fromkeys([*extra, *bank.all_confirmed_skills(), *SKILL_VOCAB]))


def skill_gaps(description: str, bank: FactBank, track: Track | None) -> list[str]:
    """Terms the posting mentions that the user has not confirmed. Denied and unsure skills count as unconfirmed."""
    have = {terms.canonical(s) for s in bank.all_confirmed_skills()}
    found = terms.find_terms(description, vocabulary(track, bank))
    return [t for t in found if terms.canonical(t) not in have]


def score(p: Posting, track: Track | None, profile: Profile, bank: FactBank) -> Scored:
    desc = p.description or ""
    s = WEIGHT_TITLE if track else 0.0
    reasons = [f"track {track.name}"] if track else []
    if track and any(phrase == p.title.lower().strip() for phrase in track.titles):
        s += TITLE_WORDS_BONUS
        reasons.append("exact title")
    wanted = list(dict.fromkeys([*(track.skills if track else ()), *bank.all_confirmed_skills()]))
    hits = terms.find_terms(f"{p.title}\n{desc}", wanted)
    s += min(len(hits), HIT_CAP) * WEIGHT_HIT
    reasons.append(f"{len(hits)} skill hits")
    gaps = skill_gaps(desc, bank, track)
    if gaps:
        s += max(len(gaps) * WEIGHT_GAP, WEIGHT_GAP * GAP_CAP)
        reasons.append(f"gaps: {', '.join(gaps[:4])}")
    loc = (p.location or "").lower()
    if any(r in loc for r in profile.search.regions):
        s += WEIGHT_LOCAL
        reasons.append("in your regions")
    elif p.remote or "remote" in loc:
        s += WEIGHT_REMOTE
        reasons.append("remote")
    if s >= THRESHOLD_A and len(gaps) <= MAX_GAPS_FOR_A:
        fit = "A"
    elif s >= THRESHOLD_B:
        fit = "B"
    else:
        fit = "C"
    return Scored(p, track.name if track else "", fit, round(s, 2), reasons, hits, gaps)
