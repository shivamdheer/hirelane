from __future__ import annotations

from pathlib import Path

import yaml

from hirelane import answers
from hirelane.profile import parse_profile
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)

USER_RULES = {"answers": [
    {"match": ["authorized to work", "legally authorized"], "answer": "Yes"},
    {"match": ["require sponsorship"], "answer": "No"},
    {"match": "re:how did you (hear|find)", "answer": "Company website"},
    {"match": ["favorite color"], "answer": ""},
    {"match": ["first name"], "answer": "Al"},
]}


def bank(tmp_path: Path) -> answers.AnswerBank:
    (tmp_path / "answers.yaml").write_text(yaml.safe_dump(USER_RULES))
    return answers.load_bank(PROFILE, tmp_path)


def test_identity_fields_come_from_the_profile(tmp_path: Path) -> None:
    b = answers.load_bank(PROFILE, tmp_path)
    assert b.resolve("Email address *").answer == "alex.rivera@example.com"  # type: ignore[union-attr]
    assert b.resolve("Last Name").answer == "Rivera"  # type: ignore[union-attr]
    assert b.resolve("Salary expectation (USD)").answer == "75000"  # type: ignore[union-attr]
    assert b.resolve("LinkedIn profile") is None            # the profile has no LinkedIn link


def test_user_rules_come_first_and_support_regex(tmp_path: Path) -> None:
    b = bank(tmp_path)
    assert b.resolve("Are you legally authorized to work in the US?").answer == "Yes"  # type: ignore[union-attr]
    assert b.resolve("How did you hear about us?").answer == "Company website"  # type: ignore[union-attr]
    assert b.resolve("How did you find this role").answer == "Company website"  # type: ignore[union-attr]
    assert b.resolve("First name").answer == "Al"  # type: ignore[union-attr]


def test_empty_answers_do_not_match(tmp_path: Path) -> None:
    assert bank(tmp_path).resolve("What is your favorite color?") is None


def test_unknown_questions_return_none(tmp_path: Path) -> None:
    assert bank(tmp_path).resolve("Describe a time you led a team") is None


def test_learned_answers_are_saved_and_used(tmp_path: Path) -> None:
    answers.save_learned("Do you have a driver's license?", "Yes", tmp_path)
    answers.save_learned("Do you have a driver's license?", "No", tmp_path)   # replaces, never duplicates
    b = answers.load_bank(PROFILE, tmp_path)
    hit = b.resolve("Do you have a driver's license? *")
    assert hit is not None and hit.answer == "No" and hit.source == "learned"
    assert len(yaml.safe_load((tmp_path / answers.LEARNED_NAME).read_text())["answers"]) == 1
