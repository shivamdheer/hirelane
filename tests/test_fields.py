from __future__ import annotations

from pathlib import Path

import pytest

from hirelane.submit import fields
from hirelane.submit.fields import values_match

AUTH = "Are you legally authorized to work in the United States?"
SPONSOR = "Will you now or in the future require visa sponsorship?"


@pytest.mark.parametrize("a,b,ok", [
    ("Alex", " alex ", True),
    ("+1 555 0100", "(1) 555-0100", True),
    ("Alex", "Alexander", False),
    ("12", "", False),
])
def test_values_match(a: str, b: str, ok: bool) -> None:
    assert values_match(a, b) is ok


@pytest.mark.browser
def test_scan_reads_labels_kinds_and_required(form_page) -> None:
    found = {f.label: f for f in fields.scan(form_page)}
    assert found["First Name"].required and found["First Name"].kind == "text"
    assert found["Phone"].required is False and found["Phone"].kind == "tel"
    assert found["Resume/CV"].kind == "file"
    auth = found[AUTH]
    assert auth.kind == "select" and auth.options == ["Yes", "No"]
    sponsor = found[SPONSOR]
    assert sponsor.kind == "radio" and sponsor.options == ["Yes", "No"] and sponsor.required
    assert found["I acknowledge the privacy policy"].kind == "checkbox"


@pytest.mark.browser
def test_fill_each_kind_and_read_back(form_page, tmp_path: Path) -> None:
    pdf = tmp_path / "Alex_Rivera_Resume_Fabrikam.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    by_label = {f.label: f for f in fields.scan(form_page)}
    assert fields.fill_field(form_page, by_label["First Name"], "Alex") is None
    assert fields.fill_field(form_page, by_label[AUTH], "Yes") is None
    assert fields.fill_field(form_page, by_label[SPONSOR], "No") is None
    assert fields.fill_field(form_page, by_label["I acknowledge the privacy policy"], "Yes") is None
    assert fields.attach_file(form_page, by_label["Resume/CV"], str(pdf)) is None
    after = {f.label: f for f in fields.scan(form_page)}
    assert after["First Name"].value == "Alex"
    assert after[AUTH].value == "Yes"
    assert after[SPONSOR].value == "No"
    assert after["I acknowledge the privacy policy"].value == "checked"
    assert after["Resume/CV"].value == pdf.name


@pytest.mark.browser
def test_fill_reports_a_missing_option(form_page) -> None:
    by_label = {f.label: f for f in fields.scan(form_page)}
    problem = fields.fill_field(form_page, by_label[AUTH], "Perhaps")
    assert problem is not None and "no option" in problem
