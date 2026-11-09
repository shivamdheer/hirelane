"""First-run setup: import a resume into a fact bank and write the config files from commented templates."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import facts
from .config import Paths
from .resume_import import ParsedResume, import_resume

TEMPLATES = Path(__file__).parent / "templates"
SKILLS_KEY = "skills"
Ask = Callable[[str, str], str]           # question and default, returns the answer


class InitError(RuntimeError):
    pass


@dataclass
class InitResult:
    written: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    experiences: int = 0
    bullets: int = 0
    skills: int = 0


def _fill(template: str, values: dict[str, str]) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)


def _yaml_str(value: str) -> str:
    return yaml.safe_dump(value, default_flow_style=True, width=1000).split("\n")[0].removesuffix("...").strip()


def starter_track(parsed: ParsedResume, wanted: tuple[str, ...] = ()) -> str:
    """A first track from the titles the user wants, or the most recent job title, so sourcing has something to find."""
    titles = list(wanted) or [e.title for e in parsed.experiences if e.kind == "work" and e.title]
    if not titles:
        return ("  # Add at least one track, for example:\n"
                "  # - {name: data, label: Data analytics, titles: [data analyst], skills: [sql, python]}")
    title = titles[0].strip()
    all_titles = ", ".join(_yaml_str(t.strip().lower()) for t in titles)
    name = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "main"
    skills = ", ".join(s.lower() for s in parsed.skills[:6])
    return (f"  - name: {name}\n    label: {_yaml_str(title)}\n    titles: [{all_titles}]\n"
            f"    skills: [{skills}]")


def _split_place(text: str) -> tuple[str, str]:
    parts = [p.strip() for p in text.split(",")]
    return (parts[0], parts[1]) if len(parts) > 1 else (parts[0], "")


def write_config(paths: Paths, parsed: ParsedResume, *, name: str, email: str, location: str, needs_sponsorship: bool,
                 authorized: bool | None, force: bool, wanted: tuple[str, ...] = ()) -> list[Path]:
    city, region = _split_place(location)
    links = "\n".join(f"  {k}: {_yaml_str(v)}" for k, v in parsed.links.items()) or "  {}"
    rules = ""
    if authorized is not None:
        rules += (f'  - match: ["authorized to work", "legally authorized", "eligible to work"]\n'
                  f'    answer: "{"Yes" if authorized else "No"}"\n')
    rules += (f'  - match: ["require sponsorship", "visa sponsorship", "require a visa"]\n'
              f'    answer: "{"Yes" if needs_sponsorship else "No"}"\n')
    values = {
        "name": _yaml_str(name), "email": _yaml_str(email), "phone": parsed.phone, "city": city, "region": region,
        "country": "US", "postal_code": "", "links": links, "tracks": starter_track(parsed, wanted),
        "needs_sponsorship": "true" if needs_sponsorship else "false", "degree": "bachelors", "rules": rules.rstrip(),
    }
    out: list[Path] = []
    for name_, target in (("settings.yaml", paths.settings_file), ("profile.yaml", paths.profile_file),
                          ("answers.yaml", paths.answers_file), ("companies.yaml", paths.companies_file)):
        if target.exists() and not force:
            raise InitError(f"{target} already exists, use --force to replace it. Nothing was changed.")
        text = _fill((TEMPLATES / name_).read_text(), values)
        yaml.safe_load(text)                    # a template that does not parse is a bug, so fail loudly here
        out.append(target)
        target.write_text(text)
    return out


def write_facts(paths: Paths, parsed: ParsedResume) -> list[Path]:
    out = [facts.save_experience(e, paths.experience) for e in parsed.experiences]
    if parsed.skills:
        skills = facts.Experience(key=SKILLS_KEY, kind="skills", name="Skills",
                                  skills=[facts.Skill(name=s, how="listed on your resume") for s in parsed.skills])
        out.append(facts.save_experience(skills, paths.experience))
    return out


def run_init(paths: Paths, resume: Path | None, ask: Ask, *, force: bool = False) -> InitResult:
    """Import the resume if there is one, ask for what it did not contain, and write everything."""
    paths.ensure()
    if not force and any(f.exists() for f in (paths.profile_file, paths.settings_file)):
        raise InitError(f"{paths.config} already has a profile or settings, use --force to replace them.")
    existing = list(paths.experience.glob("*.yaml"))
    if existing and not force:
        raise InitError(f"{paths.experience} already holds facts, use --force to replace them.")
    parsed = import_resume(resume) if resume else ParsedResume(warnings=["no resume imported"])
    name = parsed.name or ask("Your full name", "")
    email = parsed.email or ask("Your email address", "")
    if not name or "@" not in email:
        raise InitError("a name and an email address are needed")
    location = ask("Where do you live? City, state or region", "")
    needs = ask("Will you need visa sponsorship? (y/n)", "n").lower().startswith("y")
    auth_raw = ask("Are you authorized to work in your country? (y/n, empty to skip)", "").lower()
    authorized = None if not auth_raw else auth_raw.startswith("y")
    has_title = any(e.kind == "work" and e.title for e in parsed.experiences)
    wanted_raw = "" if has_title else ask("What job titles are you looking for? Separate several with commas", "")
    wanted = tuple(t.strip() for t in wanted_raw.split(",") if t.strip())
    result = InitResult(warnings=list(parsed.warnings))
    result.written += write_config(paths, parsed, name=name, email=email, location=location, needs_sponsorship=needs,
                                   authorized=authorized, force=force, wanted=wanted)
    result.written += write_facts(paths, parsed)
    result.experiences = len([e for e in parsed.experiences if e.kind in ("work", "project")])
    result.bullets = sum(len(e.bullets) for e in parsed.experiences)
    result.skills = len(parsed.skills)
    return result
