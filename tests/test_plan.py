from __future__ import annotations

from pathlib import Path

import yaml

from hirelane import answers
from hirelane.profile import parse_profile
from hirelane.submit.fields import FormField
from hirelane.submit.plan import make_plan
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)


def bank(tmp_path: Path) -> answers.AnswerBank:
    rules = {"answers": [{"match": ["authorized to work"], "answer": "Yes"},
                         {"match": ["privacy policy"], "answer": "Yes"}]}
    (tmp_path / "answers.yaml").write_text(yaml.safe_dump(rules))
    return answers.load_bank(PROFILE, tmp_path)


def f(fid: str, label: str, kind: str = "text", required: bool = True, maxlength: int = 0) -> FormField:
    return FormField(fid, label, kind, required, maxlength=maxlength)


def test_plan_fills_known_fields_and_separates_the_rest(tmp_path: Path) -> None:
    form = [
        f("f0", "First Name"), f("f1", "Email"), f("f2", "Resume/CV", "file"),
        f("f3", "Cover Letter", "file", required=False),
        f("f4", "Are you legally authorized to work in the US?", "select"),
        f("f5", "What is your favorite color?"),
        f("f6", "Pronouns", required=False),
        f("f7", "Writing sample", "file"),
    ]
    plan = make_plan(form, bank(tmp_path))
    assert plan.values == {"f0": "Alex", "f1": "alex.rivera@example.com", "f4": "Yes"}
    assert plan.resume_fid == "f2"
    assert [x.label for x in plan.unanswered] == ["What is your favorite color?"]
    assert [x.label for x in plan.skipped] == ["Pronouns"]
    assert [x.label for x in plan.unsupported] == ["Writing sample"]
    assert plan.sources["f0"] == "profile"


def test_an_answer_longer_than_the_field_allows_is_not_truncated(tmp_path: Path) -> None:
    plan = make_plan([f("f0", "Email", maxlength=5)], bank(tmp_path))
    assert plan.values == {} and [x.fid for x in plan.unanswered] == ["f0"]
