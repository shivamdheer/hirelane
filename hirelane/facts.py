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


def parse_experience(raw: dict[str, Any], key: str) -> Experience:
    kind = str(raw.get("kind", "work"))
    if kind not in KINDS:
        raise FactsError(f"{key}: kind must be one of {KINDS}")
    name = str(raw.get("name", "")).strip()
    if not name:
        raise FactsError(f"{key}: name is required")
    dates = raw.get("dates") or {}
    bullets = [_bullet(b, i) for i, b in enumerate(raw.get("bullets") or [])]
    if len({b.id for b in bullets}) != len(bullets):
        raise FactsError(f"{key}: bullet ids must be unique")
    return Experience(
        key=key, kind=kind, name=name, title=str(raw.get("title", "") or ""),
        location=str(raw.get("location", "") or ""),
        start=str(dates.get("start", "") or ""), end=str(dates.get("end", "") or ""),
        detail=str(raw.get("detail", "") or ""), bullets=bullets,
        skills=[_skill(s) for s in raw.get("skills") or []], metrics=[str(m) for m in raw.get("metrics") or []])


def load_bank(directory: Path | None = None) -> FactBank:
    d = directory or get_paths().experience
    bank = FactBank()
    if not d.exists():
        return bank
    for f in sorted(d.glob("*.yaml")):
        try:
            raw = yaml.safe_load(f.read_text()) or {}
            bank.experiences.append(parse_experience(raw, f.stem))
        except (yaml.YAMLError, KeyError, TypeError) as e:
            raise FactsError(f"{f.name}: {e}") from e
    return bank


def to_dict(e: Experience) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": e.kind, "name": e.name}
    for attr in ("title", "location", "detail"):
        if getattr(e, attr):
            out[attr] = getattr(e, attr)
    if e.start or e.end:
        out["dates"] = {"start": e.start, "end": e.end}
    if e.bullets:
        out["bullets"] = [
            {k: v for k, v in (("id", b.id), ("text", b.text), ("skills", b.skills), ("tracks", b.tracks),
                               ("variants", b.variants)) if v}
            for b in e.bullets]
    if e.skills:
        out["skills"] = [{"name": s.name, "status": s.status, **({"how": s.how} if s.how else {})} for s in e.skills]
    if e.metrics:
        out["metrics"] = list(e.metrics)
    return out


def save_experience(e: Experience, directory: Path | None = None) -> Path:
    d = directory or get_paths().experience
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{e.key}.yaml"
    body = HEADER + yaml.safe_dump(to_dict(e), sort_keys=False, allow_unicode=True, width=100)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(body)
    os.replace(tmp, path)
    return path


def apply_proposal(bank: FactBank, proposal: dict[str, Any], experience_key: str = "",
                   directory: Path | None = None) -> str:
    """Write an approved proposal into the fact bank. Returns a short description of what changed.

    A skill proposal needs an experience to attach to. The user picks one when the proposal has none.
    """
    key = experience_key or str(proposal.get("experience") or "")
    exp = bank.get(key)
    if exp is None:
        raise FactsError("choose which experience this belongs to")
    text = str(proposal["text"]).strip()
    kind = proposal["kind"]
    if kind == "skill":
        existing = next((s for s in exp.skills if s.name.lower() == text.lower()), None)
        if existing is not None:
            existing.status = "confirmed"
        else:
            exp.skills.append(Skill(name=text, status="confirmed", how="added from a proposal"))
        message = f"{text} is now a confirmed skill for {exp.name}."
    elif kind == "variant":
        bullet = exp.bullet(str(proposal.get("target") or ""))
        if bullet is None:
            raise FactsError("the bullet this reword was for no longer exists")
        if text not in bullet.wordings():
            bullet.variants.append(text)
        message = f"Added an approved wording to a bullet at {exp.name}."
    else:
        raise FactsError(f"unknown proposal kind {kind!r}")
    save_experience(exp, directory)
    return message
