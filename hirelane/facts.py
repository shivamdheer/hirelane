"""The fact bank: everything the user has approved to appear on a resume.

One YAML file per experience lives in config/experience/. Tailoring may choose from these facts, reorder them and
reword them under validation. It may never add to them. New material becomes a proposal the user must confirm.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import get_paths

KINDS = ("work", "project", "education", "skills")
SKILL_STATUSES = ("confirmed", "denied", "unsure")
HEADER = ("# Approved facts for one experience. Tailoring may only choose, reorder and reword what is here.\n"
          "# Anything new is proposed to you first. Edit this file freely.\n")
NUMBER = re.compile(r"(?<![\w.#/])[~$]?\d[\d,.]*\+?%?[BKMk]?(?![\w#])")


class FactsError(ValueError):
    pass


@dataclass
class Skill:
    name: str
    status: str = "confirmed"
    how: str = ""                  # a short note on how the user used it, shown in the editor only


@dataclass
class Bullet:
    id: str
    text: str
    skills: list[str] = field(default_factory=list)
    tracks: list[str] = field(default_factory=list)       # tracks this bullet suits, empty means all
    variants: list[str] = field(default_factory=list)     # other approved wordings of the same fact

    def wordings(self) -> list[str]:
        return [self.text, *self.variants]


@dataclass
class Experience:
    key: str
    kind: str
    name: str
    title: str = ""
    location: str = ""
    start: str = ""
    end: str = ""
    detail: str = ""                                       # degree line or project link
    bullets: list[Bullet] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)       # approved figures, exact wording

    @property
    def dates(self) -> str:
        if self.start and self.end:
            return f"{self.start} - {self.end}"
        return self.start or self.end

    def confirmed_skills(self) -> list[str]:
        return [s.name for s in self.skills if s.status == "confirmed"]

    def denied_skills(self) -> list[str]:
        return [s.name for s in self.skills if s.status == "denied"]

    def bullet(self, bullet_id: str) -> Bullet | None:
        return next((b for b in self.bullets if b.id == bullet_id), None)


@dataclass
class FactBank:
    experiences: list[Experience] = field(default_factory=list)

    def get(self, key: str) -> Experience | None:
        return next((e for e in self.experiences if e.key == key), None)

    def of_kind(self, *kinds: str) -> list[Experience]:
        return [e for e in self.experiences if e.kind in kinds]

    def all_confirmed_skills(self) -> list[str]:
        seen: dict[str, str] = {}
        for e in self.experiences:
            for s in e.confirmed_skills():
                seen.setdefault(s.lower(), s)
        return list(seen.values())

    def denied_skills(self) -> set[str]:
        return {s.lower() for e in self.experiences for s in e.denied_skills()}

    def approved_numbers(self) -> set[str]:
        """Every figure that appears in an approved bullet, variant or metric."""
        out: set[str] = set()
        for e in self.experiences:
            texts = [*e.metrics, *(w for b in e.bullets for w in b.wordings())]
            for t in texts:
                out.update(_norm_number(n) for n in NUMBER.findall(t))
        return out

    def all_text(self) -> str:
        parts: list[str] = []
        for e in self.experiences:
            parts += [e.name, e.title, *e.metrics, *e.confirmed_skills()]
            parts += [w for b in e.bullets for w in b.wordings()]
        return "\n".join(parts)


def _norm_number(token: str) -> str:
    return token.strip().lower().replace(",", "").lstrip("~$")


def _skill(raw: Any) -> Skill:
    if isinstance(raw, str):
        return Skill(name=raw)
    status = str(raw.get("status", "confirmed"))
    if status not in SKILL_STATUSES:
        raise FactsError(f"skill status must be one of {SKILL_STATUSES}, got {status!r}")
    return Skill(name=str(raw["name"]), status=status, how=str(raw.get("how", "") or ""))


def _bullet(raw: dict[str, Any], index: int) -> Bullet:
    text = str(raw.get("text", "")).strip()
    if not text:
        raise FactsError("every bullet needs text")
    return Bullet(id=str(raw.get("id") or f"b{index + 1}"), text=text,
                  skills=[str(s) for s in raw.get("skills") or []], tracks=[str(t) for t in raw.get("tracks") or []],
                  variants=[str(v).strip() for v in raw.get("variants") or [] if str(v).strip()])
