from __future__ import annotations

import copy
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from hirelane import ats_gate, pdf, tailor
from hirelane.facts import FactBank, load_bank
from hirelane.models import Job
from hirelane.profile import parse_profile
from hirelane.resume import ResumeContent
from tests.bank_fixture import write_bank
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)
JD = "Data analyst role using SQL, Tableau, Python and pandas for dashboards."
FILENAME = "Alex_Rivera_Resume_Fabrikam.pdf"


@pytest.fixture
def bank(tmp_path: Path) -> FactBank:
    return load_bank(write_bank(tmp_path / "exp"))


def built(tmp_path: Path, bank: FactBank) -> tuple[Path, ResumeContent]:
    job = Job(key="k", company="Fabrikam", role="Data Analyst", track="data", desc_text=JD)
    rendered = pdf.render(tailor.tailor(job, bank, PROFILE).content, tmp_path / FILENAME)
    return rendered.path, rendered.content


def test_a_clean_resume_passes(tmp_path: Path, bank: FactBank) -> None:
    path, content = built(tmp_path, bank)
    result = ats_gate.check_pdf(path, content, bank, expected_filename=FILENAME, jd_text=JD)
    assert result.ok, result.problems
    assert result.coverage == 100 and len(result.sha256) == 64


def test_wrong_file_name_fails(tmp_path: Path, bank: FactBank) -> None:
    path, content = built(tmp_path, bank)
    result = ats_gate.check_pdf(path, content, bank, expected_filename="Alex_Rivera_Resume_Contoso.pdf")
    assert any("file name" in p for p in result.problems)


def test_a_line_the_bank_does_not_back_fails(tmp_path: Path, bank: FactBank) -> None:
    path, content = built(tmp_path, bank)
    tampered = copy.deepcopy(content)
    tampered.blocks[0].bullets[0].text = "Led a team of 30 engineers to ship a new platform in record time."
    tampered.blocks[0].bullets[0].provenance = "rewrite"
    pdf.render(tampered, path)
    result = ats_gate.check_pdf(path, tampered, bank)
    assert any("not backed by the fact bank" in p for p in result.problems)


def test_unapproved_skill_fails(tmp_path: Path, bank: FactBank) -> None:
    path, content = built(tmp_path, bank)
    content.skills.append("Spark")
    pdf.render(content, path)
    assert any("skill not approved" in p for p in ats_gate.check_pdf(path, content, bank).problems)


def test_image_only_pdf_fails(tmp_path: Path, bank: FactBank) -> None:
    _path, content = built(tmp_path, bank)
    blank = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(blank), pagesize=LETTER)
    c.showPage()
    c.save()
    result = ats_gate.check_pdf(blank, content, bank)
    assert any("selectable text" in p for p in result.problems)


def test_two_pages_fail(tmp_path: Path, bank: FactBank) -> None:
    _path, content = built(tmp_path, bank)
    two = tmp_path / "two.pdf"
    c = canvas.Canvas(str(two), pagesize=LETTER)
    for _ in range(2):
        for i in range(60):
            c.drawString(40, 760 - i * 11, "Delivered something useful for a customer every single week " * 1)
        c.showPage()
    c.save()
    assert any("2 pages" in p for p in ats_gate.check_pdf(two, content, bank).problems)


def test_low_coverage_is_a_warning_not_a_failure(tmp_path: Path, bank: FactBank) -> None:
    path, content = built(tmp_path, bank)
    content.skills = ["Excel"]
    pdf.render(content, path)
    jd = "SQL Tableau Python pandas Excel stakeholder management process improvement scikit-learn"
    result = ats_gate.check_pdf(path, content, bank, jd_text=jd)
    assert result.coverage < ats_gate.COVERAGE_TARGET and result.warnings
    assert result.ok, result.problems
