"""The list of company boards to poll, kept in config/companies.yaml."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import get_paths
from .models import SUPPORTED_ATS

HEADER = "# Boards to poll. ats is greenhouse, lever or ashby. slug is the name in the board's public URL.\n"
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")


class CompaniesError(ValueError):
    pass


@dataclass(frozen=True)
class Company:
    name: str
    ats: str
    slug: str


def validate(c: Company) -> Company:
    if c.ats not in SUPPORTED_ATS:
        raise CompaniesError(f"ats must be one of {SUPPORTED_ATS}, got {c.ats!r}")
    if not SLUG.match(c.slug):
        raise CompaniesError(f"invalid board slug {c.slug!r}")
    if not c.name.strip():
        raise CompaniesError("company name is required")
    return c


def load_companies(path: Path | None = None) -> list[Company]:
    p = path or get_paths().companies_file
    if not p.exists():
        return []
    raw = yaml.safe_load(p.read_text()) or {}
    out = [validate(Company(str(c.get("name", "")), str(c.get("ats", "")), str(c.get("slug", ""))))
           for c in raw.get("companies") or []]
    seen: set[tuple[str, str]] = set()
    unique = []
    for c in out:
        if (c.ats, c.slug) not in seen:
            seen.add((c.ats, c.slug))
            unique.append(c)
    return unique


def save_companies(companies: list[Company], path: Path | None = None) -> None:
    p = path or get_paths().companies_file
    p.parent.mkdir(parents=True, exist_ok=True)
    body = HEADER + yaml.safe_dump({"companies": [{"name": c.name, "ats": c.ats, "slug": c.slug} for c in companies]},
                                   sort_keys=False)
    tmp = p.with_suffix(".yaml.tmp")
    tmp.write_text(body)
    os.replace(tmp, p)


def add_company(company: Company, path: Path | None = None) -> bool:
    """Add one board. False when it is already listed."""
    validate(company)
    current = load_companies(path)
    if any((c.ats, c.slug) == (company.ats, company.slug) for c in current):
        return False
    save_companies([*current, company], path)
    return True
