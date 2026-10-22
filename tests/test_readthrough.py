from __future__ import annotations

import json

from hirelane import readthrough
from hirelane.resume import Block, BulletLine, ResumeContent
from tests.fakes import FakeProvider


def content(*texts: str, skills: int = 6) -> ResumeContent:
    lines = [BulletLine(text=t, source_id=f"b{i}") for i, t in enumerate(texts)]
    return ResumeContent(name="Alex Rivera", contact=["alex.rivera@example.com"],
                         skills=[f"S{i}" for i in range(skills)],
                         blocks=[Block(key="a", kind="work", name="Northwind Analytics", bullets=lines)])


def test_repeated_openings_duplicates_and_short_skills() -> None:
    c = content("Built a dashboard for managers.", "Built a pipeline for reports.", "Built a model for demand.",
                "Built a dashboard for managers.", skills=2)
    notes = readthrough.deterministic_notes(c)
    assert "4 bullets start with 'built'" in notes
    assert "two bullets say the same thing" in notes
    assert "the skills line is short" in notes


def test_empty_experience_is_reported() -> None:
    c = content()
    assert readthrough.deterministic_notes(c) == ["Northwind Analytics has no bullets"]


def test_a_clean_resume_has_no_notes() -> None:
    c = content("Built a dashboard for managers.", "Wrote SQL pipelines for reporting.", "Automated data cleaning.")
    assert readthrough.read_through(c, "Data Analyst", "SQL") == []


def test_model_notes_are_validated() -> None:
    c = content("Built a dashboard for managers.", "Wrote SQL pipelines for reporting.", "Automated data cleaning.")
    reply = json.dumps({"notes": ["Opening is generic.", 5, "see https://evil.example.com", "x" * 500,
                                  "<b>bold</b>", "  Spacing   is   odd.  "]})
    notes = readthrough.read_through(c, "Data Analyst", "SQL", FakeProvider(reply))
    assert notes == ["Opening is generic.", "Spacing is odd."]


def test_provider_failures_and_bad_shapes_are_ignored() -> None:
    c = content("Built a dashboard for managers.", "Wrote SQL pipelines for reporting.", "Automated data cleaning.")
    assert readthrough.read_through(c, "Data Analyst", "SQL", FakeProvider("not json")) == []
    assert readthrough.read_through(c, "Data Analyst", "SQL", FakeProvider('{"notes": "nope"}')) == []
    assert readthrough.read_through(c, "Data Analyst", "SQL", FakeProvider([])) == []
