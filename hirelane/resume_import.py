"""Import an existing resume (PDF or DOCX) into an editable fact bank.

Parsing a resume is a heuristic, so the result is a draft. ``hirelane init`` says so and points at the files. The
user's own words are kept exactly as written. Nothing is rewritten or added at this stage.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from . import terms
from .facts import Bullet, Experience, Skill
from .vocab import SKILL_VOCAB

DOCX_BODY = "word/document.xml"
MAX_DOCX_XML_BYTES = 20_000_000
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BULLET_MARKS = ("-", "*", "\N{BULLET}", "\N{MIDDLE DOT}", "\N{BLACK CIRCLE}", "\N{WHITE BULLET}", "\N{EN DASH}")
SECTIONS = {
    "experience": ("experience", "work experience", "professional experience", "employment", "employment history",
                   "work history"),
    "project": ("projects", "personal projects", "selected projects", "academic projects"),
    "education": ("education", "academic background"),
    "skills": ("skills", "technical skills", "core skills", "skills and tools"),
}
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
DATE = rf"(?:{MONTH}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
DATE_RANGE = re.compile(rf"({DATE})\s*(?:-|to|\N{{EN DASH}}|\N{{EM DASH}})\s*({DATE}|Present|Current|Now)", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
URL = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in/|github\.com/)[\w./-]+|https?://[\w./-]+", re.I)
MIN_NAME_WORDS = 2
MAX_NAME_WORDS = 4
MIN_BULLET_CHARS = 3          # a mark and at least two characters of text


class ImportError_(ValueError):
    pass


@dataclass
class ParsedResume:
    name: str = ""
    email: str = ""
    phone: str = ""
    links: dict[str, str] = field(default_factory=dict)
    experiences: list[Experience] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            reader = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except PdfReadError as e:
            raise ImportError_("the PDF could not be read") from e
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as z:
                if z.getinfo(DOCX_BODY).file_size > MAX_DOCX_XML_BYTES:
                    raise ImportError_("the document body is too large to import")
                root = ElementTree.fromstring(z.read(DOCX_BODY))
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as e:
            raise ImportError_("the DOCX file could not be read") from e
        paras = ["".join(t.text or "" for t in p.iter(f"{W_NS}t")) for p in root.iter(f"{W_NS}p")]
        return "\n".join(paras)
    if suffix in (".txt", ".md"):
        return path.read_text()
    raise ImportError_(f"unsupported file type {suffix!r}, use PDF or DOCX")


def _section_of(line: str) -> str | None:
    key = re.sub(r"[^a-z ]", "", line.lower()).strip()
    for name, words in SECTIONS.items():
        if key in words:
            return name
    return None


def _is_bullet(line: str) -> bool:
    return line.lstrip().startswith(BULLET_MARKS) and len(line.strip()) >= MIN_BULLET_CHARS


def _strip_bullet(line: str) -> str:
    return line.strip().lstrip("".join(BULLET_MARKS)).strip()


def _slug(text: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "entry"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    taken.add(key)
    return key


def _split_header(line: str) -> tuple[str, str, str, str]:
    """Name, location, start and end from a header line like 'Acme Corp, Austin, TX  Jun 2023 - Aug 2025'."""
    m = DATE_RANGE.search(line)
    start, end = (m.group(1), m.group(2)) if m else ("", "")
    head = (line[:m.start()] + line[m.end():]).strip(" ,|-\N{EN DASH}\N{EM DASH}\t") if m else line.strip()
    parts = [p.strip() for p in re.split(r",|\|", head, maxsplit=1)]
    return parts[0], (parts[1] if len(parts) > 1 else ""), start, end


def _vocab_hits(text: str, extra: list[str]) -> list[str]:
    return terms.find_terms(text, [*extra, *SKILL_VOCAB])


def parse_text(text: str) -> ParsedResume:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    out = ParsedResume()
    if not lines:
        raise ImportError_("the file has no readable text")
    first = lines[0].strip()
    if MIN_NAME_WORDS <= len(first.split()) <= MAX_NAME_WORDS and re.fullmatch(r"[A-Za-z.'\- ]+", first):
        out.name = first
    head = "\n".join(lines[:6])
    if m := EMAIL.search(head):
        out.email = m.group(0)
    if m := PHONE.search(head):
        out.phone = m.group(0).strip()
    for m in URL.finditer(head):
        url = m.group(0)
        out.links["linkedin" if "linkedin" in url else "github" if "github" in url else "website"] = (
            url if url.startswith("http") else "https://" + url)

    section = ""
    current: Experience | None = None
    taken: set[str] = set()
    for line in lines:
        name = _section_of(line.strip())
        if name:
            section, current = name, None
            continue
        if section in ("experience", "project", "education"):
            if _is_bullet(line):
                if current is not None:
                    current.bullets.append(Bullet(id=f"b{len(current.bullets) + 1}", text=_strip_bullet(line)))
                continue
            has_dates = bool(DATE_RANGE.search(line))
            if current is not None and current.bullets and not has_dates and line.strip()[:1].islower():
                current.bullets[-1].text += " " + line.strip()                  # a wrapped bullet
                continue
            if current is not None and not current.bullets and not has_dates:
                if not current.title:
                    current.title = line.strip()
                else:
                    current.detail = (current.detail + " " + line.strip()).strip()
                continue
            name_, loc, start, end = _split_header(line)
            current = Experience(key=_slug(name_, taken), kind="work" if section == "experience" else section,
                                 name=name_, location=loc, start=start, end=end)
            out.experiences.append(current)
        elif section == "skills":
            body = re.sub(r"^[A-Za-z /&]+:\s*", "", _strip_bullet(line) if _is_bullet(line) else line.strip())
            out.skills += [s.strip() for s in re.split(r"[,|]", body) if s.strip()]

    for exp in out.experiences:
        exp.skills = [Skill(name=t, status="confirmed", how="mentioned in your resume bullets")
                      for t in dict.fromkeys(_vocab_hits(" ".join(b.text for b in exp.bullets), out.skills))]
        for b in exp.bullets:
            b.skills = _vocab_hits(b.text, out.skills)
    out.skills = list(dict.fromkeys(out.skills))
    if not out.name:
        out.warnings.append("could not find your name on the first line")
    if not out.email:
        out.warnings.append("could not find an email address")
    if not any(e.kind == "work" for e in out.experiences):
        out.warnings.append("no work experience section was recognised")
    if not out.skills:
        out.warnings.append("no skills section was recognised")
    return out


def import_resume(path: Path) -> ParsedResume:
    return parse_text(read_text(path))
