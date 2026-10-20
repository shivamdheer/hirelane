from __future__ import annotations

from pathlib import Path

import pytest

from hirelane import facts, truth, voice
from hirelane.resume import Block, BulletLine, ResumeContent
from tests.bank_fixture import write_bank


@pytest.fixture
def bank(tmp_path: Path) -> facts.FactBank:
    return facts.load_bank(write_bank(tmp_path))


def check(bank: facts.FactBank, bullet_id: str, candidate: str, exp_key: str = "northwind") -> truth.Check:
    exp = bank.get(exp_key)
    assert exp is not None
    bullet = exp.bullet(bullet_id)
    assert bullet is not None
    return truth.check_rewrite(bullet, candidate, exp, bank)


def test_a_faithful_reword_passes(bank: facts.FactBank) -> None:
    r = check(bank, "dash", "Delivered weekly Tableau sales dashboards to 12 regional managers.")
    assert r.ok, r.problems


def test_new_figures_are_rejected(bank: facts.FactBank) -> None:
    r = check(bank, "dash", "Built weekly sales dashboards in Tableau used by 40 regional managers.")
    assert any("figure 40" in p for p in r.problems)


def test_new_skills_are_rejected_and_reported(bank: facts.FactBank) -> None:
    r = check(bank, "dash", "Built weekly sales dashboards in Tableau and Power BI used by 12 regional managers.")
    assert not r.ok and r.new_terms == ["power bi"]


def test_skill_from_another_bullet_is_still_rejected(bank: facts.FactBank) -> None:
    # Python is approved for this employer, but not for this accomplishment.
    r = check(bank, "dash", "Built weekly sales dashboards in Tableau and Python used by 12 regional managers.")
    assert r.new_terms == ["python"]


def test_denied_skill_is_rejected(bank: facts.FactBank) -> None:
    r = check(bank, "etl", "Wrote Spark pipelines that cut monthly reporting time from 5 days to 2.")
    assert "spark" in r.new_terms


def test_new_proper_names_are_rejected(bank: facts.FactBank) -> None:
    r = check(bank, "audit", "Documented and streamlined the order audit process with Acme finance stakeholders.")
    assert any("Acme" in p for p in r.problems)


def test_too_much_change_is_rejected(bank: facts.FactBank) -> None:
    r = check(bank, "audit", "Improved company efficiency substantially through careful analysis work every quarter.")
    assert any("too much" in p for p in r.problems)


@pytest.mark.parametrize("text,problem", [
    ("Built dashboards \N{EM DASH} fast and used by 12 regional managers.", "dash"),
    ("Built dashboards; used by 12 regional managers weekly.", "semicolon"),
    ("Spearheaded dashboards used by 12 regional managers.", "banned"),
])
def test_style_rules_apply_to_rewrites(bank: facts.FactBank, text: str, problem: str) -> None:
    assert any(problem in p for p in check(bank, "dash", text).problems)


def line(text: str, source: str, prov: str = "original") -> BulletLine:
    return BulletLine(text=text, source_id=source, provenance=prov)


def test_audit_accepts_approved_lines_and_flags_invented_ones(bank: facts.FactBank) -> None:
    exp = bank.get("northwind")
    assert exp is not None
    content = ResumeContent(name="Alex Rivera", contact=[], skills=["SQL", "Tableau"], blocks=[Block(
        key="northwind", kind="work", name="Northwind Analytics", bullets=[
            line(exp.bullet("etl").text, "etl"),  # type: ignore[union-attr]
            line("Created weekly Tableau sales dashboards for 12 regional managers.", "dash", "variant"),
            line("Led a team of 30 engineers to ship a platform.", "etl", "rewrite"),
            line("Anything", "missing"),
        ])])
    bad = truth.audit_content(content, bank)
    assert len(bad) == 2
    assert all(b.startswith("Northwind Analytics") for b in bad)


def test_audit_flags_unapproved_skills(bank: facts.FactBank) -> None:
    content = ResumeContent(name="Alex", contact=[], skills=["SQL", "Spark", "dbt"], blocks=[])
    assert truth.audit_content(content, bank) == ["skill not approved: Spark", "skill not approved: dbt"]


def test_voice_bullet_problems() -> None:
    assert voice.bullet_problems("Built a dashboard that 12 managers use every week.") == []
    assert "too short" in voice.bullet_problems("Did stuff")
    assert any("pronoun" in p for p in voice.bullet_problems("We built a dashboard that 12 managers use weekly."))
