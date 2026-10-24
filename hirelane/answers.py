"""The answer bank: what to type into form questions.

Rules come from config/answers.yaml (written by the user) and config/answers_learned.yaml (answers the user gave
for questions the filler could not answer). Identity fields fall back to the profile. A required question with no
matching rule is never guessed. It goes to the user.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import get_paths
from .profile import Profile

LEARNED_NAME = "answers_learned.yaml"
REGEX_PREFIX = "re:"
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class Rule:
    patterns: tuple[str, ...]
    answer: str
    source: str = "answers.yaml"

    def matches(self, label: str) -> bool:
        low = label.lower()
        for p in self.patterns:
            if p.startswith(REGEX_PREFIX):
                if re.search(p[len(REGEX_PREFIX):], low, re.I):
                    return True
            elif p.lower() in low:
                return True
        return False


@dataclass(frozen=True)
class Resolution:
    answer: str
    source: str


def profile_values(profile: Profile) -> dict[str, str]:
    links = profile.links
    return {
        "first_name": profile.first_name, "last_name": profile.last_name, "full_name": profile.name,
        "email": profile.email, "phone": profile.phone, "city": profile.city, "region": profile.region,
        "country": profile.country, "postal_code": profile.postal_code,
        "salary_expectation": profile.salary.expectation,
        "linkedin": links.get("linkedin", ""), "github": links.get("github", ""), "website": links.get("website", ""),
    }


def _identity_rules() -> list[Rule]:
    return [
        Rule(("first name", "given name"), "{first_name}", "profile"),
        Rule(("last name", "family name", "surname"), "{last_name}", "profile"),
        Rule(("full name", "legal name", "your name"), "{full_name}", "profile"),
        Rule(("email",), "{email}", "profile"),
        Rule(("phone", "mobile"), "{phone}", "profile"),
        Rule(("linkedin",), "{linkedin}", "profile"),
        Rule(("github",), "{github}", "profile"),
        Rule(("website", "portfolio"), "{website}", "profile"),
        Rule(("city",), "{city}", "profile"),
        Rule(("zip", "postal code"), "{postal_code}", "profile"),
        Rule(("salary expectation", "desired salary", "desired compensation", "expected compensation"),
             "{salary_expectation}", "profile"),
    ]


class AnswerBank:
    def __init__(self, rules: list[Rule], profile: Profile) -> None:
        self.rules = rules
        self.profile = profile
        self._values = profile_values(profile)

    def _fill(self, template: str) -> str:
        return PLACEHOLDER.sub(lambda m: self._values.get(m.group(1), ""), template).strip()

    def resolve(self, label: str) -> Resolution | None:
        """The first rule that matches and yields a non-empty answer. User rules win over identity defaults."""
        for rule in self.rules:
            if rule.matches(label):
                answer = self._fill(rule.answer)
                if answer:
                    return Resolution(answer, rule.source)
        return None


def _parse_rules(raw: dict[str, Any] | None, source: str) -> list[Rule]:
    out = []
    for entry in (raw or {}).get("answers") or []:
        patterns = entry.get("match") or []
        patterns = [patterns] if isinstance(patterns, str) else patterns
        answer = entry.get("answer")
        if not patterns or answer is None:
            continue
        out.append(Rule(tuple(str(p) for p in patterns), str(answer), source))
    return out


def load_bank(profile: Profile, directory: Path | None = None) -> AnswerBank:
    d = directory or get_paths().config
    rules: list[Rule] = []
    for name, source in (("answers.yaml", "answers.yaml"), (LEARNED_NAME, "learned")):
        f = d / name
        if f.exists():
            rules += _parse_rules(yaml.safe_load(f.read_text()), source)
    return AnswerBank([*rules, *_identity_rules()], profile)


def save_learned(label: str, answer: str, directory: Path | None = None) -> None:
    """Remember an answer the user gave, matching the exact question text next time."""
    d = directory or get_paths().config
    path = d / LEARNED_NAME
    raw = yaml.safe_load(path.read_text()) if path.exists() else None
    entries = (raw or {}).get("answers") or []
    entries = [e for e in entries if e.get("match") != [label.strip().lower()]]
    entries.append({"match": [label.strip().lower()], "answer": answer})
    d.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text("# Answers you gave to questions the filler could not answer.\n"
                   + yaml.safe_dump({"answers": entries}, sort_keys=False))
    os.replace(tmp, path)
