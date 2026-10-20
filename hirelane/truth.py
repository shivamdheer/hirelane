"""The truthfulness checks. A reworded bullet is accepted only if it adds nothing the user did not approve.

A rewrite may change verbs, order and emphasis. It may not add a number, a tool or skill, a proper name or a claim of
scope. Every rule is a plain check on the text, so the result does not depend on how well a model behaved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import terms, voice
from .facts import NUMBER, Bullet, Experience, FactBank, _norm_number
from .resume import BulletLine, ResumeContent
from .vocab import SKILL_VOCAB

MIN_CONTENT_OVERLAP = 0.5
MIN_WORD_LEN = 4
MIN_NAME_LEN = 3
WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.'-]*")
STOP = {"with", "that", "this", "from", "into", "across", "while", "using", "through", "their", "than", "over",
        "under", "which", "where", "when", "also", "such", "each", "other", "team", "teams"}


@dataclass
class Check:
    problems: list[str] = field(default_factory=list)
    new_terms: list[str] = field(default_factory=list)      # skills the rewrite adds, worth proposing to the user

    @property
    def ok(self) -> bool:
        return not self.problems


def _proper_names(text: str) -> list[str]:
    """Capitalized words that are not the first word of the line. They are usually products, tools or places."""
    names = []
    for i, m in enumerate(WORD.finditer(text)):
        word = m.group(0).strip(".'-")
        if i > 0 and len(word) >= MIN_NAME_LEN and word[0].isupper():
            names.append(word)
    return names


def _content_words(text: str) -> set[str]:
    return {w.lower().strip(".'-") for w in WORD.findall(text) if len(w) >= MIN_WORD_LEN and w.lower() not in STOP}


def allowed_source(bullet: Bullet, exp: Experience) -> str:
    """All text a rewrite of this bullet may draw on: its own wordings, its skills and the experience's metrics."""
    return "\n".join([*bullet.wordings(), *bullet.skills, *exp.metrics])


def check_rewrite(bullet: Bullet, candidate: str, exp: Experience, bank: FactBank) -> Check:
    result = Check()
    text = candidate.strip()
    result.problems += voice.bullet_problems(text)
    source = allowed_source(bullet, exp)

    allowed_numbers = {_norm_number(n) for n in NUMBER.findall(source)}
    for n in NUMBER.findall(text):
        if _norm_number(n) not in allowed_numbers:
            result.problems.append(f"adds the figure {n}")

    vocab = [*SKILL_VOCAB, *bank.all_confirmed_skills(), *bank.denied_skills()]
    for term in terms.find_terms(text, vocab):
        if not terms.has_term(source, term):
            result.new_terms.append(term)
            result.problems.append(f"adds the skill {term}")

    source_words = _content_words(source)
    flagged = {terms.canonical(t) for t in result.new_terms}
    for word in _proper_names(text):
        if word.lower() not in source_words and terms.canonical(word) not in flagged:
            result.problems.append(f"adds the name {word}")

    original_words = _content_words(bullet.text)
    if original_words:
        overlap = len(original_words & _content_words(text)) / len(original_words)
        if overlap < MIN_CONTENT_OVERLAP:
            result.problems.append("changes too much of the original wording")
    return result


def line_is_approved(line: BulletLine, exp: Experience | None, bank: FactBank) -> bool:
    """Audit one resume line against the bank, independent of how it was produced."""
    if exp is None:
        return False
    bullet = exp.bullet(line.source_id)
    if bullet is None:
        return False
    if line.provenance in ("original", "variant"):
        return line.text in bullet.wordings()
    return check_rewrite(bullet, line.text, exp, bank).ok


def audit_content(content: ResumeContent, bank: FactBank) -> list[str]:
    """Every line of the resume that the bank does not back. Empty means the resume is clean."""
    bad: list[str] = []
    for block in content.blocks:
        exp = bank.get(block.key)
        for line in block.bullets:
            if not line_is_approved(line, exp, bank):
                bad.append(f"{block.name}: {line.text[:80]}")
    approved = {s.lower() for s in bank.all_confirmed_skills()}
    bad += [f"skill not approved: {s}" for s in content.skills if s.lower() not in approved]
    return bad
