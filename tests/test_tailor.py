from __future__ import annotations

import json
from pathlib import Path

import pytest

from hirelane import tailor, truth
from hirelane.facts import FactBank, load_bank
from hirelane.models import Job
from hirelane.profile import parse_profile
from tests.bank_fixture import write_bank
from tests.fakes import FakeProvider
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)

DATA_JD = ("We need a data analyst. You will write SQL, build Tableau dashboards for regional managers, and "
           "automate reports with Python and pandas. Experience with Spark or dbt is a plus.")
OPS_JD = "Operations analyst role: improve processes with finance stakeholders using Excel and SQL."


@pytest.fixture
def bank(tmp_path: Path) -> FactBank:
    return load_bank(write_bank(tmp_path))


def job(desc: str, track: str = "data", role: str = "Data Analyst") -> Job:
    return Job(key="greenhouse:fabrikam:1", company="Fabrikam", role=role, track=track, desc_text=desc)


def test_selects_bullets_by_relevance_and_respects_limits(bank: FactBank) -> None:
    result = tailor.tailor(job(DATA_JD), bank, PROFILE)
    work = next(b for b in result.content.blocks if b.key == "northwind")
    assert len(work.bullets) == 4                     # first work block gets one extra
    assert work.bullets[0].source_id == "dash"
    project = next(b for b in result.content.blocks if b.key == "campus_bikes")
    assert len(project.bullets) == 2


def test_a_different_posting_reorders_the_same_facts(bank: FactBank) -> None:
    result = tailor.tailor(job(OPS_JD, "ops", "Operations Analyst"), bank, PROFILE)
    work = next(b for b in result.content.blocks if b.key == "northwind")
    assert work.bullets[0].source_id in {"audit", "etl"}
    assert result.content.skills[0].lower() in {"sql", "excel", "process improvement", "stakeholder management"}


def test_variant_wording_is_used_when_it_matches_the_posting_better(bank: FactBank) -> None:
    exp = bank.get("northwind")
    assert exp is not None
    dash = exp.bullet("dash")
    assert dash is not None
    dash.variants = ["Created weekly Tableau and SQL sales dashboards for 12 regional managers."]
    result = tailor.tailor(job(DATA_JD), bank, PROFILE)
    work = next(b for b in result.content.blocks if b.key == "northwind")
    line = next(b for b in work.bullets if b.source_id == "dash")
    assert line.provenance == "variant" and line.text.startswith("Created")


def test_unconfirmed_skills_are_proposed_never_added(bank: FactBank) -> None:
    result = tailor.tailor(job(DATA_JD), bank, PROFILE)
    assert {g.lower() for g in result.gaps} == {"spark", "dbt"}
    assert {p.text.lower() for p in result.proposals if p.kind == "skill"} == {"spark", "dbt"}
    assert "spark" not in {s.lower() for s in result.content.skills}
    assert truth.audit_content(result.content, bank) == []


def test_education_is_always_included_last(bank: FactBank) -> None:
    result = tailor.tailor(job(DATA_JD), bank, PROFILE)
    assert result.content.blocks[-1].kind == "education"
    assert result.content.blocks[-1].bullets == []


def test_recent_experience_comes_first(bank: FactBank) -> None:
    result = tailor.tailor(job(DATA_JD), bank, PROFILE)
    kinds = [b.kind for b in result.content.blocks]
    assert kinds == ["work", "project", "education"]


def test_contact_line_uses_only_profile_fields() -> None:
    assert tailor.contact_line(PROFILE) == ["alex.rivera@example.com", "+1 555 0100", "Springfield, IL",
                                            "github.com/alex-rivera-example"]


def reword_reply(system: str, user: str) -> str:
    return json.dumps({
        "0": "Delivered weekly Tableau sales dashboards to 12 regional managers.",   # faithful
        "1": "Wrote SQL pipelines that cut reporting from 5 days to 1 day.",         # invented figure
        "2": "Created Python and pandas reports with Spark for 4 recurring reports.",  # new skill
    })


def test_rewording_accepts_only_validated_lines(bank: FactBank) -> None:
    provider = FakeProvider(reword_reply)
    result = tailor.tailor(job(DATA_JD), bank, PROFILE, provider)
    work = next(b for b in result.content.blocks if b.key == "northwind")
    lines = {b.source_id: b for b in work.bullets}
    assert lines["dash"].provenance == "rewrite" and lines["dash"].text.startswith("Delivered")
    assert lines["etl"].provenance == "original"
    assert result.rewrites == 1
    assert truth.audit_content(result.content, bank) == []
    sent = provider.calls[0][1]
    assert '<data label="posting">' in sent


def test_a_reword_that_only_adds_a_skill_becomes_a_proposal(bank: FactBank) -> None:
    reply = json.dumps({"0": "Built weekly sales dashboards in Tableau and Power BI used by 12 regional managers."})
    result = tailor.tailor(job(DATA_JD), bank, PROFILE, FakeProvider(reply))
    variants = [p for p in result.proposals if p.kind == "variant"]
    assert len(variants) == 1 and "power bi" in variants[0].reason
    assert "Power BI" not in " ".join(b.text for b in result.content.bullet_lines())


@pytest.mark.parametrize("reply", ["not json", "[1, 2]", '{"0": 5}', ""])
def test_bad_replies_fall_back_to_the_approved_text(bank: FactBank, reply: str) -> None:
    result = tailor.tailor(job(DATA_JD), bank, PROFILE, FakeProvider(reply))
    assert result.rewrites == 0
    assert all(b.provenance != "rewrite" for b in result.content.bullet_lines())
