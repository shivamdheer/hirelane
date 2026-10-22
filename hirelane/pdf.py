"""Render a ResumeContent as a plain, ATS-friendly one-page PDF.

Single column, standard fonts, real text, no images, no tables, no header or footer. Applicant tracking systems read
this kind of file reliably, and so do people.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

from .resume import Block, ResumeContent
from .textutil import file_key

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"
BODY_SIZES = (10.0, 9.5, 9.0, 8.5)
MARGIN = 0.6 * inch
HEADINGS = {"work": "EXPERIENCE", "project": "PROJECTS", "education": "EDUCATION"}
SKILLS_HEADING = "SKILLS"
# A plain hyphen extracts as text in every PDF reader. A drawn dot glyph is often dropped from the text layer.
BULLET_GLYPH = "-"
MIN_BULLETS_PER_BLOCK = 1


@dataclass
class Rendered:
    path: Path
    pages: int
    body_size: float
    content: ResumeContent       # the content actually rendered, after any trimming


def resume_filename(first: str, last: str, company: str) -> str:
    """Alex_Rivera_Resume_Fabrikam.pdf. The company key keeps one file per employer."""
    who = "_".join(re.sub(r"[^A-Za-z0-9]", "", p) for p in (first, last) if p)
    return f"{who or 'Resume'}_Resume_{file_key(company)}.pdf"


def _styles(size: float) -> dict[str, ParagraphStyle]:
    lead = size * 1.22
    return {
        "name": ParagraphStyle("name", fontName=FONT_BOLD, fontSize=size + 6, leading=size + 9, alignment=TA_CENTER),
        "contact": ParagraphStyle("contact", fontName=FONT, fontSize=size - 0.5, leading=lead, alignment=TA_CENTER,
                                  spaceAfter=3),
        "heading": ParagraphStyle("heading", fontName=FONT_BOLD, fontSize=size + 0.5, leading=lead + 1, spaceBefore=6,
                                  spaceAfter=1),
        "entry": ParagraphStyle("entry", fontName=FONT_BOLD, fontSize=size, leading=lead, spaceBefore=3),
        "sub": ParagraphStyle("sub", fontName=FONT_ITALIC, fontSize=size, leading=lead),
        "bullet": ParagraphStyle("bullet", fontName=FONT, fontSize=size, leading=lead, leftIndent=14, bulletIndent=3,
                                 spaceBefore=0.5),
        "plain": ParagraphStyle("plain", fontName=FONT, fontSize=size, leading=lead),
    }


def _entry_line(left: str, right: str, style: ParagraphStyle) -> Paragraph:
    # One line, with the date or place after a wide gap. Real text, so extraction keeps it on one line.
    text = f"{escape(left)}" + (f"    {escape(right)}" if right else "")
    return Paragraph(text, style)


def _block(block: Block, st: dict[str, ParagraphStyle]) -> list[Paragraph]:
    head = f"{block.name}" if not block.location else f"{block.name}, {block.location}"
    flow = [_entry_line(head, block.dates, st["entry"])]
    if block.title:
        flow.append(Paragraph(escape(block.title), st["sub"]))
    if block.detail:
        flow.append(Paragraph(escape(block.detail), st["plain"]))
    flow += [Paragraph(escape(b.text), st["bullet"], bulletText=BULLET_GLYPH) for b in block.bullets]
    return flow


def _story(content: ResumeContent, size: float) -> list[object]:
    st = _styles(size)
    story: list[object] = [Paragraph(escape(content.name), st["name"]),
                           Paragraph(escape(" | ".join(content.contact)), st["contact"])]
    for kind, heading in HEADINGS.items():
        blocks = [b for b in content.blocks if b.kind == kind]
        if not blocks:
            continue
        story += [Paragraph(heading, st["heading"]), HRFlowable(width="100%", thickness=0.6, spaceAfter=1)]
        for b in blocks:
            story.append(KeepTogether(_block(b, st)))
    if content.skills:
        story += [Paragraph(SKILLS_HEADING, st["heading"]), HRFlowable(width="100%", thickness=0.6, spaceAfter=1),
                  Paragraph(escape(", ".join(content.skills)), st["plain"])]
    story.append(Spacer(1, 1))
    return story


def _write(content: ResumeContent, path: Path, size: float) -> int:
    doc = SimpleDocTemplate(str(path), pagesize=LETTER, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=MARGIN, title=f"{content.name} Resume", author=content.name,
                            creator="hirelane", subject="")
    doc.build(_story(content, size))
    from pypdf import PdfReader
    return len(PdfReader(str(path)).pages)


def _trim_one(content: ResumeContent) -> bool:
    """Drop the last bullet of the block with the most bullets. Bullets are ranked, so the last is the weakest."""
    candidates = [b for b in content.blocks if len(b.bullets) > MIN_BULLETS_PER_BLOCK]
    if not candidates:
        return False
    max(candidates, key=lambda b: len(b.bullets)).bullets.pop()
    return True


def render(content: ResumeContent, path: Path) -> Rendered:
    """Write the PDF, shrinking the type and then trimming the weakest bullets until it fits on one page."""
    path.parent.mkdir(parents=True, exist_ok=True)
    work = copy.deepcopy(content)
    while True:
        for size in BODY_SIZES:
            pages = _write(work, path, size)
            if pages == 1:
                return Rendered(path, pages, size, work)
        if not _trim_one(work):
            return Rendered(path, pages, BODY_SIZES[-1], work)
