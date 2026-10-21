from __future__ import annotations

from pathlib import Path

from hirelane import facts, scoring
from hirelane.models import Posting
from hirelane.profile import parse_profile
from tests.bank_fixture import write_bank
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)
DATA = PROFILE.track("data")


def posting(desc: str, title: str = "Data Analyst", location: str = "Chicago, IL", remote: bool = False) -> Posting:
    return Posting(ats="greenhouse", slug="s", job_id="1", company="Fabrikam", title=title, location=location,
                   remote=remote, description=desc)


def bank(tmp_path: Path) -> facts.FactBank:
    return facts.load_bank(write_bank(tmp_path))


def test_strong_match_is_fit_a(tmp_path: Path) -> None:
    desc = "You will use SQL, Python, Tableau, pandas and Excel to build dashboards for stakeholders."
    r = scoring.score(posting(desc, remote=True), DATA, PROFILE, bank(tmp_path))
    assert r.fit == "A"
    assert {"sql", "python", "tableau"} <= {h.lower() for h in r.hits}
    assert r.gaps == []


def test_unconfirmed_required_skills_become_gaps_and_lower_the_fit(tmp_path: Path) -> None:
    desc = "SQL, Python, Tableau plus Spark, Kafka, Airflow, Snowflake and Databricks."
    r = scoring.score(posting(desc), DATA, PROFILE, bank(tmp_path))
    assert {"spark", "kafka", "airflow", "snowflake", "databricks"} <= {g.lower() for g in r.gaps}
    assert r.fit != "A"


def test_denied_and_unsure_skills_are_gaps(tmp_path: Path) -> None:
    gaps = scoring.skill_gaps("We use Spark and dbt daily.", bank(tmp_path), DATA)
    assert {g.lower() for g in gaps} == {"spark", "dbt"}


def test_no_description_is_fit_c(tmp_path: Path) -> None:
    assert scoring.score(posting(""), DATA, PROFILE, bank(tmp_path)).fit == "C"


def test_region_and_remote_bonuses() -> None:
    regional = parse_profile({**ALEX_PROFILE, "search": {"scope": "regions", "regions": ["chicago"]}})
    empty = facts.FactBank()
    near = scoring.score(posting("", location="Chicago, IL"), DATA, regional, empty)
    far = scoring.score(posting("", location="Denver, CO"), DATA, regional, empty)
    remote = scoring.score(posting("", location="Denver, CO", remote=True), DATA, regional, empty)
    assert near.score > remote.score > far.score
