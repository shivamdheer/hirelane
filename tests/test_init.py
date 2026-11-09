from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hirelane import facts
from hirelane.answers import load_bank
from hirelane.config import Paths, load_settings
from hirelane.init import InitError, run_init
from hirelane.profile import load_profile
from tests.test_resume_import import PLAIN


def ask_with(answers: dict[str, str]):
    def ask(question: str, default: str) -> str:
        for key, value in answers.items():
            if key in question:
                return value
        return default
    return ask


@pytest.fixture
def resume(tmp_path: Path) -> Path:
    path = tmp_path / "resume.txt"
    path.write_text(PLAIN)
    return path


def test_init_writes_config_and_facts_from_a_resume(home: Paths, resume: Path) -> None:
    result = run_init(home, resume, ask_with({"live": "Springfield, IL", "sponsorship": "n", "authorized": "y"}))
    assert result.experiences == 3 and result.bullets == 4 and result.skills == 5 and result.warnings == []
    profile = load_profile()
    assert profile.name == "Alex Rivera" and profile.email == "alex.rivera@example.com"
    assert (profile.city, profile.region) == ("Springfield", "IL")
    assert [t.name for t in profile.tracks] == ["data_analyst"]
    assert profile.tracks[0].skills[:2] == ("python", "sql")
    assert load_settings().submit_mode == "review" and load_settings().daily_cap == 10
    bank = facts.load_bank()
    assert {e.key for e in bank.experiences} >= {"northwind_analytics", "skills", "lincoln_state_university"}
    assert "Tableau" in bank.all_confirmed_skills()


def test_answers_follow_what_the_user_said(home: Paths, resume: Path) -> None:
    run_init(home, resume, ask_with({"sponsorship": "y", "authorized": "n"}))
    rules = yaml.safe_load(home.answers_file.read_text())["answers"]
    by_match = {r["match"][0]: r["answer"] for r in rules}
    assert by_match["authorized to work"] == "No" and by_match["require sponsorship"] == "Yes"
    assert load_profile().knockouts.needs_sponsorship is True
    bank = load_bank(load_profile(), home.config)
    assert bank.resolve("Do you require visa sponsorship?").answer == "Yes"  # type: ignore[union-attr]


def test_an_unanswered_authorization_question_writes_no_rule(home: Paths, resume: Path) -> None:
    run_init(home, resume, ask_with({}))
    text = home.answers_file.read_text()
    assert "authorized to work\", \"legally" not in text.split("answers:")[1]
    assert load_bank(load_profile(), home.config).resolve("Are you authorized to work in the US?") is None


def test_init_refuses_to_overwrite_and_changes_nothing(home: Paths, resume: Path) -> None:
    run_init(home, resume, ask_with({}))
    before = home.profile_file.read_text()
    home.profile_file.write_text(before + "# my edit\n")
    with pytest.raises(InitError, match="--force"):
        run_init(home, resume, ask_with({}))
    assert home.profile_file.read_text().endswith("# my edit\n")
    run_init(home, resume, ask_with({}), force=True)
    assert not home.profile_file.read_text().endswith("# my edit\n")


def test_without_a_resume_the_questions_fill_the_gaps(home: Paths) -> None:
    result = run_init(home, None, ask_with({"full name": "Sam Lee", "email": "sam@example.com"}))
    assert result.warnings == ["no resume imported"] and result.experiences == 0
    profile = load_profile()
    assert profile.name == "Sam Lee" and profile.tracks == ()


def test_missing_identity_is_an_error(home: Paths) -> None:
    with pytest.raises(InitError, match="name and an email"):
        run_init(home, None, ask_with({}))


def test_templates_keep_their_comments(home: Paths, resume: Path) -> None:
    run_init(home, resume, ask_with({}))
    assert "Read the Responsible use section" in home.settings_file.read_text()
    assert "Alex Rivera" in home.profile_file.read_text()


def test_titles_the_user_wants_become_a_track(home: Paths) -> None:
    answers = {"full name": "Sam Lee", "email": "sam@example.com",
               "job titles": "Data Analyst, Analytics Engineer"}
    run_init(home, None, ask_with(answers))
    profile = load_profile()
    assert len(profile.tracks) == 1
    assert set(profile.tracks[0].titles) == {"data analyst", "analytics engineer"}
