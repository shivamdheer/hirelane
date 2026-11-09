from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hirelane import facts, pdf, tailor
from hirelane.models import Job
from hirelane.profile import parse_profile
from hirelane.resume_import import ImportError_, import_resume, parse_text, read_text
from tests.bank_fixture import write_bank
from tests.profile_fixture import ALEX_PROFILE

PLAIN = """Alex Rivera
alex.rivera@example.com | +1 555 0100 | Springfield, IL | github.com/alex-rivera-example

EXPERIENCE
Northwind Analytics, Springfield, IL   Jun 2023 - Aug 2025
Data Analyst
- Built weekly sales dashboards in Tableau used by 12 regional managers.
- Wrote SQL pipelines that cut monthly reporting time from 5 days to 2
  and removed a manual export step.
Fabrikam Cafe, Springfield, IL   Jun 2021 - Aug 2022
Barista
- Trained 6 new hires on the register and opening checklist.

PROJECTS
Campus Bike Share Analysis   Jan 2023 - May 2023
- Modeled station demand with Python and scikit-learn on 18 months of trip data.

EDUCATION
Lincoln State University, Springfield, IL   Aug 2019 - May 2023
B.S. in Statistics
Relevant coursework: regression, databases

SKILLS
Languages: Python, SQL
Tools: Tableau, Excel, pandas
"""


def test_parse_header_and_contact_details() -> None:
    r = parse_text(PLAIN)
    assert (r.name, r.email, r.phone) == ("Alex Rivera", "alex.rivera@example.com", "+1 555 0100")
    assert r.links == {"github": "https://github.com/alex-rivera-example"}
    assert r.warnings == []


def test_parse_experiences_projects_and_education() -> None:
    r = parse_text(PLAIN)
    assert [(e.kind, e.name) for e in r.experiences] == [
        ("work", "Northwind Analytics"), ("work", "Fabrikam Cafe"), ("project", "Campus Bike Share Analysis"),
        ("education", "Lincoln State University")]
    nw = r.experiences[0]
    assert (nw.title, nw.location, nw.start, nw.end) == ("Data Analyst", "Springfield, IL", "Jun 2023", "Aug 2025")
    assert [b.id for b in nw.bullets] == ["b1", "b2"]
    assert nw.bullets[1].text.endswith("2 and removed a manual export step.")          # the wrapped line was joined
    edu = r.experiences[3]
    assert edu.title == "B.S. in Statistics" and edu.detail == "Relevant coursework: regression, databases"


def test_skills_are_split_and_attached_to_bullets() -> None:
    r = parse_text(PLAIN)
    assert r.skills == ["Python", "SQL", "Tableau", "Excel", "pandas"]
    nw = r.experiences[0]
    assert {s.name.lower() for s in nw.skills} >= {"tableau", "sql"}
    assert {s.lower() for s in nw.bullets[0].skills} >= {"tableau"}
    assert all(s.status == "confirmed" for s in nw.skills)


def test_the_users_words_are_kept_exactly() -> None:
    r = parse_text(PLAIN)
    assert r.experiences[0].bullets[0].text == "Built weekly sales dashboards in Tableau used by 12 regional managers."


def test_a_resume_the_parser_cannot_read_warns_instead_of_guessing() -> None:
    r = parse_text("Resume 2026\nnothing else here")
    assert r.experiences == [] and len(r.warnings) == 4
    with pytest.raises(ImportError_):
        parse_text("   \n  ")


def test_pdf_roundtrip_through_our_own_renderer(tmp_path: Path) -> None:
    bank = facts.load_bank(write_bank(tmp_path / "exp"))
    job = Job(key="k", company="Fabrikam", role="Data Analyst", track="data", desc_text="SQL Tableau Python")
    pdf_path = pdf.render(tailor.tailor(job, bank, parse_profile(ALEX_PROFILE)).content, tmp_path / "r.pdf").path
    r = import_resume(pdf_path)
    assert r.name == "Alex Rivera" and r.email == "alex.rivera@example.com"
    names = {e.name for e in r.experiences}
    assert {"Northwind Analytics", "Campus Bike Share Analysis", "Lincoln State University"} <= names
    imported = {b.text for e in r.experiences for b in e.bullets}
    original = {w for e in bank.experiences for b in e.bullets for w in [b.text]}
    assert len(imported & original) >= 4


def test_docx_is_read(tmp_path: Path) -> None:
    body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in PLAIN.splitlines() if line.strip())
    xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    path = tmp_path / "resume.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)
    assert read_text(path).startswith("Alex Rivera")
    assert import_resume(path).experiences[0].name == "Northwind Analytics"


def test_unsupported_types_are_refused(tmp_path: Path) -> None:
    f = tmp_path / "resume.pages"
    f.write_bytes(b"x")
    with pytest.raises(ImportError_, match="unsupported"):
        import_resume(f)


def test_a_corrupt_docx_is_an_import_error(tmp_path: Path) -> None:
    not_a_zip = tmp_path / "broken.docx"
    not_a_zip.write_bytes(b"this is not a zip file")
    with pytest.raises(ImportError_, match="could not be read"):
        read_text(not_a_zip)
    no_body = tmp_path / "empty.docx"
    with zipfile.ZipFile(no_body, "w") as z:
        z.writestr("other.xml", "<a/>")
    with pytest.raises(ImportError_, match="could not be read"):
        read_text(no_body)
    bad_xml = tmp_path / "bad.docx"
    with zipfile.ZipFile(bad_xml, "w") as z:
        z.writestr("word/document.xml", "<w:document")
    with pytest.raises(ImportError_, match="could not be read"):
        read_text(bad_xml)


def test_a_corrupt_pdf_is_an_import_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 truncated")
    with pytest.raises(ImportError_, match="could not be read"):
        read_text(broken)
