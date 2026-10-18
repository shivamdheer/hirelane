"""Matching skill terms in free text."""
from __future__ import annotations

import re
from functools import lru_cache

# A few common spellings that should count as the same skill.
ALIASES: dict[str, tuple[str, ...]] = {
    "javascript": ("js",),
    "typescript": ("ts",),
    "postgresql": ("postgres",),
    "machine learning": ("ml",),
    "power bi": ("powerbi",),
    "node.js": ("nodejs", "node"),
    "golang": ("go",),
    "kubernetes": ("k8s",),
    "amazon web services": ("aws",),
    "google cloud": ("gcp",),
    "ci/cd": ("cicd",),
}
_REVERSE = {alias: canon for canon, aliases in ALIASES.items() for alias in aliases}
# Short aliases that are also ordinary words are never matched through an alias.
AMBIGUOUS = {"go", "node", "ml", "ts", "js"}


def canonical(term: str) -> str:
    t = term.strip().lower()
    return _REVERSE.get(t, t)


@lru_cache(maxsize=2048)
def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w.#+-])" + re.escape(term) + r"(?![\w#+-])", re.I)


def forms(term: str) -> tuple[str, ...]:
    canon = canonical(term)
    out = [canon, *ALIASES.get(canon, ())]
    return tuple(dict.fromkeys(f for f in out if f))


def has_term(text: str, term: str) -> bool:
    """True when the term or an unambiguous alias of it appears as a whole word or phrase."""
    return any(_pattern(f).search(text or "") for f in forms(term) if f not in AMBIGUOUS or f == term.strip().lower())


def find_terms(text: str, vocabulary: list[str] | tuple[str, ...]) -> list[str]:
    """The vocabulary terms present in the text, in vocabulary order and without duplicates."""
    seen: set[str] = set()
    out: list[str] = []
    for term in vocabulary:
        c = canonical(term)
        if c in seen:
            continue
        if has_term(text, term):
            seen.add(c)
            out.append(term)
    return out
