from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from hirelane import pdf, tailor
from hirelane.facts import FactBank, load_bank
from hirelane.models import Job
from hirelane.profile import parse_profile
from hirelane.resume import Block, BulletLine, ResumeContent
from tests.bank_fixture import write_bank
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)


@pytest.fixture
def bank(tmp_path: Path) -> FactBank:
    return load_bank(write_bank(tmp_path / "exp"))


def text_of(path: Path) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(str(path)).pages)


def content(bank: FactBank) -> ResumeContent:
    job = Job(key="k", company="Fabrikam", role="Data Analyst", track="data",
              desc_text="SQL Tableau Python dashboards pandas")
    return tailor.tailor(job, bank, PROFILE).content


def test_filename_follows_the_company_key() -> None:
    assert pdf.resume_filename("Alex", "Rivera", "Fabrikam, Inc.") == "Alex_Rivera_Resume_Fabrikam.pdf"
    assert pdf.resume_filename("", "", "AT&T") == "Resume_Resume_ATT.pdf"


def test_renders_one_page_with_real_text(tmp_path: Path, bank: FactBank) -> None:
    out = pdf.render(content(bank), tmp_path / "r.pdf")
    assert out.pages == 1
    text = text_of(out.path)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0] == "Alex Rivera"
    assert "alex.rivera@example.com" in lines[1]
    for heading in ("EXPERIENCE", "PROJECTS", "EDUCATION", "SKILLS"):
        assert heading in text
    assert "Northwind Analytics" in text and "Lincoln State University" in text
    meta = PdfReader(str(out.path)).metadata
    assert meta is not None and meta.author == "Alex Rivera"


def test_every_bullet_line_appears_in_the_pdf(tmp_path: Path, bank: FactBank) -> None:
    c = content(bank)
    out = pdf.render(c, tmp_path / "r.pdf")
    flat = " ".join(text_of(out.path).split())
    for line in out.content.bullet_lines():
        assert " ".join(line.text.split()) in flat


def test_overlong_content_is_trimmed_to_one_page(tmp_path: Path) -> None:
    bullets = [BulletLine(text=f"Delivered a reporting improvement number {i} for the finance team every month.",
                          source_id=f"b{i}") for i in range(60)]
    long = ResumeContent(name="Alex Rivera", contact=["alex.rivera@example.com"], skills=["SQL"], blocks=[
        Block(key="a", kind="work", name="Northwind Analytics", bullets=bullets[:30]),
        Block(key="b", kind="work", name="Contoso", bullets=bullets[30:])])
    out = pdf.render(long, tmp_path / "long.pdf")
    assert out.pages == 1
    assert len(out.content.bullet_lines()) < 60
    assert len(long.bullet_lines()) == 60           # the input is not modified
    assert all(len(b.bullets) >= 1 for b in out.content.blocks)
