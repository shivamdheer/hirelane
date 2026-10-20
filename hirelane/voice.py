"""House style for resume text. These checks are plain code, so they hold with or without a model."""
from __future__ import annotations

import re

EM_DASH = "\N{EM DASH}"
EN_DASH = "\N{EN DASH}"
BANNED_PHRASES = (
    "spearheaded", "synergy", "synergies", "results-driven", "passionate", "dynamic", "go-getter", "rockstar",
    "ninja", "guru", "proven track record", "fast-paced", "team player", "detail-oriented", "self-starter",
    "think outside the box", "hit the ground running",
)
MAX_BULLET_CHARS = 200
MIN_BULLET_CHARS = 25


def violations(text: str) -> list[str]:
    """Style problems in one line of resume text. Empty means the line is fine."""
    problems: list[str] = []
    if EM_DASH in text or EN_DASH in text:
        problems.append("contains a dash character")
    if ";" in text:
        problems.append("contains a semicolon")
    low = text.lower()
    problems += [f"banned phrase: {p}" for p in BANNED_PHRASES if re.search(rf"\b{re.escape(p)}\b", low)]
    if re.search(r"[^\x00-\x7f]", text.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")):
        problems.append("contains a non-ASCII character")
    return problems


def bullet_problems(text: str) -> list[str]:
    problems = violations(text)
    if len(text) > MAX_BULLET_CHARS:
        problems.append(f"longer than {MAX_BULLET_CHARS} characters")
    if len(text) < MIN_BULLET_CHARS:
        problems.append("too short")
    if not re.match(r"[A-Z]", text):
        problems.append("does not start with a capital letter")
    if re.match(r"(?:i|we|my|our)\b", text, re.I):
        problems.append("starts with a pronoun")
    return problems
