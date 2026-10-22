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
