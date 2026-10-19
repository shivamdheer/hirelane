from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from hirelane import facts
from hirelane.terms import find_terms, forms, has_term
from tests.bank_fixture import NORTHWIND, write_bank


def test_load_bank(tmp_path: Path) -> None:
    bank = facts.load_bank(write_bank(tmp_path / "experience"))
    assert [e.key for e in bank.experiences] == ["campus_bikes", "lincoln_state", "northwind"]
    nw = bank.get("northwind")
    assert nw is not None and nw.dates == "Jun 2023 - Aug 2025"
    assert nw.confirmed_skills()[:2] == ["SQL", "Tableau"]
    assert nw.denied_skills() == ["Spark"]
    assert "dbt" not in nw.confirmed_skills()
    assert nw.bullet("dash").wordings()[1].startswith("Created")  # type: ignore[union-attr]


def test_confirmed_skills_are_unique_across_experiences(tmp_path: Path) -> None:
    bank = facts.load_bank(write_bank(tmp_path))
    skills = [s.lower() for s in bank.all_confirmed_skills()]
    assert len(skills) == len(set(skills))
    assert "scikit-learn" in skills and "spark" not in skills
    assert bank.denied_skills() == {"spark"}


def test_approved_numbers_cover_bullets_and_metrics(tmp_path: Path) -> None:
    bank = facts.load_bank(write_bank(tmp_path))
    nums = bank.approved_numbers()
    assert {"12", "5", "2", "4", "18", "15"} <= nums
    assert "40" not in nums


@pytest.mark.parametrize("mutate,message", [
    (lambda d: d.update(kind="hobby"), "kind"),
    (lambda d: d.update(name=""), "name"),
    (lambda d: d["bullets"].append({"id": "dash", "text": "x"}), "unique"),
    (lambda d: d["bullets"].append({"id": "z", "text": ""}), "text"),
    (lambda d: d["skills"].append({"name": "X", "status": "maybe"}), "status"),
])
def test_invalid_experience_files(mutate, message: str) -> None:
    import copy
    raw = copy.deepcopy(NORTHWIND)
    mutate(raw)
    with pytest.raises(facts.FactsError, match=re.escape(message)):
        facts.parse_experience(raw, "northwind")


def test_save_roundtrip_keeps_everything(tmp_path: Path) -> None:
    exp = facts.parse_experience(NORTHWIND, "northwind")
    path = facts.save_experience(exp, tmp_path)
    assert path.read_text().startswith("# Approved facts")
    again = facts.parse_experience(yaml.safe_load(path.read_text()), "northwind")
    assert again == exp


def test_bad_yaml_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("name: [unclosed\n")
    with pytest.raises(facts.FactsError, match=r"broken\.yaml"):
        facts.load_bank(tmp_path)


def test_missing_directory_is_an_empty_bank(tmp_path: Path) -> None:
    assert facts.load_bank(tmp_path / "nope").experiences == []


@pytest.mark.parametrize("text,term,expected", [
    ("Experience with Node.js and APIs", "node.js", True),
    ("We use K8s in production", "kubernetes", True),
    ("Time to go to market quickly", "golang", False),
    ("Write Go services", "go", True),
    ("Knowledge of C++ is a plus", "c++", True),
    ("We use JavaScript", "java", False),
    ("Tableau dashboards", "tableau", True),
])
def test_has_term(text: str, term: str, expected: bool) -> None:
    assert has_term(text, term) is expected


def test_find_terms_dedupes_aliases() -> None:
    found = find_terms("Postgres and PostgreSQL, plus SQL", ["PostgreSQL", "postgres", "SQL", "Tableau"])
    assert found == ["PostgreSQL", "SQL"]
    assert forms("k8s")[0] == "kubernetes"


def test_apply_skill_proposal_confirms_and_saves(tmp_path: Path) -> None:
    directory = write_bank(tmp_path)
    bank = facts.load_bank(directory)
    msg = facts.apply_proposal(bank, {"kind": "skill", "text": "dbt", "experience": ""}, "northwind", directory)
    assert "confirmed skill" in msg
    again = facts.load_bank(directory).get("northwind")
    assert again is not None and "dbt" in again.confirmed_skills()
    assert [s.name for s in again.skills].count("dbt") == 1          # the unsure entry was upgraded, not duplicated


def test_apply_variant_proposal_adds_a_wording_once(tmp_path: Path) -> None:
    directory = write_bank(tmp_path)
    bank = facts.load_bank(directory)
    proposal = {"kind": "variant", "text": "Delivered Tableau dashboards to 12 regional managers every week.",
                "experience": "northwind", "target": "dash"}
    facts.apply_proposal(bank, proposal, directory=directory)
    facts.apply_proposal(facts.load_bank(directory), proposal, directory=directory)
    bullet = facts.load_bank(directory).get("northwind").bullet("dash")  # type: ignore[union-attr]
    assert bullet is not None and bullet.variants.count(proposal["text"]) == 1


def test_apply_proposal_errors(tmp_path: Path) -> None:
    directory = write_bank(tmp_path)
    bank = facts.load_bank(directory)
    with pytest.raises(facts.FactsError, match="choose which experience"):
        facts.apply_proposal(bank, {"kind": "skill", "text": "dbt", "experience": ""}, "", directory)
    with pytest.raises(facts.FactsError, match="no longer exists"):
        facts.apply_proposal(bank, {"kind": "variant", "text": "x", "experience": "northwind", "target": "zzz"},
                             directory=directory)
