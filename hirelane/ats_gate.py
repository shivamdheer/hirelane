"""The ATS and format gate. Every resume passes it before it can be attached to an application.

The gate reads the finished PDF the way an applicant tracking system does. It also audits every line against the fact
bank, so a resume that says something the user never approved cannot pass, whatever produced it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from . import pdf, terms, truth, voice
from .facts import FactBank
from .resume import ResumeContent

LETTER = (612.0, 792.0)
LETTER_TOLERANCE = 1.0
MIN_TEXT_CHARS = 600
COVERAGE_TARGET = 80
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
DATE_MONTH_YEAR = re.compile(rf"\b{MONTH} \d{{4}}\b")
DATE_OTHER = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}(?:-\d{2})?\b")
ALLOWED_NON_ASCII = {"\N{RIGHT SINGLE QUOTATION MARK}"}
MIN_HEADER_LINES = 2          # the name line and the contact line
LAST_ASCII_CODE = 127
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f�]")


@dataclass
class GateResult:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: int = 100
    sha256: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems


def _has_images(reader: PdfReader) -> bool:
    for page in reader.pages:
        xobjects = (page.get("/Resources") or {}).get("/XObject") or {}
        for ref in xobjects.values():
            if (ref.get_object().get("/Subtype") or "") == "/Image":
                return True
    return False


def _norm(text: str) -> str:
    return " ".join(text.split())


def check_pdf(path: Path, content: ResumeContent, bank: FactBank, *, expected_filename: str = "",
              jd_text: str = "") -> GateResult:
    result = GateResult()
    data = path.read_bytes()
    result.sha256 = hashlib.sha256(data).hexdigest()
    reader = PdfReader(str(path))
    if expected_filename and path.name != expected_filename:
        result.problems.append(f"file name is {path.name}, expected {expected_filename}")
    if len(reader.pages) != 1:
        result.problems.append(f"{len(reader.pages)} pages, expected 1")
    box = reader.pages[0].mediabox
    if abs(float(box.width) - LETTER[0]) > LETTER_TOLERANCE or abs(float(box.height) - LETTER[1]) > LETTER_TOLERANCE:
        result.problems.append("page is not US Letter")
    if _has_images(reader):
        result.problems.append("contains an image")

    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(text) < MIN_TEXT_CHARS:
        result.problems.append("too little selectable text, the file may be an image")
        return result

    if not lines or lines[0] != content.name:
        result.problems.append("the first line is not the name")
    if len(lines) < MIN_HEADER_LINES or "@" not in lines[1]:
        result.problems.append("the second line is not the contact line")
    positions = [text.find(h) for h in (*pdf.HEADINGS.values(), pdf.SKILLS_HEADING) if h in text]
    if positions != sorted(positions):
        result.problems.append("section headings are out of the expected order")
    for heading in pdf.HEADINGS.values():
        kind = next(k for k, v in pdf.HEADINGS.items() if v == heading)
        if any(b.kind == kind for b in content.blocks) and heading not in text:
            result.problems.append(f"missing heading {heading}")

    if DATE_OTHER.search(text):
        result.problems.append("a date is not in Mon YYYY form")
    if CONTROL.search(text):
        result.problems.append("contains control or replacement characters")
    odd = {c for c in text if ord(c) > LAST_ASCII_CODE and c not in ALLOWED_NON_ASCII}
    if odd:
        result.problems.append(f"contains unusual characters: {''.join(sorted(odd))[:10]}")
    for line in lines:
        for v in voice.violations(line.removeprefix(pdf.BULLET_GLYPH)):
            if "non-ASCII" not in v:
                result.problems.append(f"style: {v} in {line[:50]!r}")

    flat = _norm(text)
    bullet_lines = content.bullet_lines()
    for b in bullet_lines:
        if _norm(b.text) not in flat:
            result.problems.append(f"bullet missing from the PDF: {b.text[:50]!r}")
    if sum(1 for ln in lines if ln.startswith(pdf.BULLET_GLYPH + " ")) != len(bullet_lines):
        result.problems.append("the PDF has a different number of bullets than the record")
    result.problems += [f"not backed by the fact bank: {x}" for x in truth.audit_content(content, bank)]

    meta = reader.metadata
    if meta is None or (meta.author or "") != content.name:
        result.problems.append("document author is not the candidate's name")

    result.coverage = _coverage(flat, jd_text, bank)
    if result.coverage < COVERAGE_TARGET:
        result.warnings.append(f"covers {result.coverage} percent of the posting's terms you can claim")
    return result


def _coverage(resume_text: str, jd_text: str, bank: FactBank) -> int:
    """Share of the posting's terms that the user has confirmed and the resume mentions."""
    if not jd_text:
        return 100
    from .vocab import SKILL_VOCAB
    confirmed = bank.all_confirmed_skills()
    wanted = [t for t in terms.find_terms(jd_text, [*SKILL_VOCAB, *confirmed])
              if any(terms.canonical(t) == terms.canonical(c) for c in confirmed)]
    if not wanted:
        return 100
    hit = sum(1 for t in wanted if terms.has_term(resume_text, t))
    return round(100 * hit / len(wanted))
