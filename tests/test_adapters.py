from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hirelane import answers
from hirelane.models import Job
from hirelane.profile import parse_profile
from hirelane.submit import ADAPTERS
from hirelane.submit.base import FormUnavailable
from hirelane.submit.verify import verify
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)
RESUME_NAME = "Alex_Rivera_Resume_Fabrikam.pdf"


def job(ats: str, slug: str = "fabrikam", job_id: str = "4001", url: str = "") -> Job:
    return Job(key=f"{ats}:{slug}:{job_id}", company="Fabrikam", role="Data Analyst", ats=ats, ats_slug=slug,
               ats_job_id=job_id, apply_url=url)


@pytest.mark.parametrize("ats,expected", [
    ("greenhouse", "https://job-boards.greenhouse.io/embed/job_app?for=fabrikam&token=4001"),
    ("lever", "https://jobs.lever.co/fabrikam/4001/apply"),
    ("ashby", "https://jobs.ashbyhq.com/fabrikam/4001/application"),
])
def test_form_urls(ats: str, expected: str) -> None:
    assert ADAPTERS[ats]().form_url(job(ats)) == expected


def test_greenhouse_needs_a_numeric_job_id() -> None:
    with pytest.raises(ValueError):
        ADAPTERS["greenhouse"]().form_url(job("greenhouse", job_id="abc"))


def test_open_refuses_urls_outside_the_ats_domains() -> None:
    class Pagey:
        url = "https://example.com"

    adapter = ADAPTERS["lever"]()
    adapter.form_url = lambda j: "https://example.com/apply"  # type: ignore[method-assign]
    with pytest.raises(FormUnavailable, match="refusing"):
        adapter.open(Pagey(), job("lever"))


def make_bank(tmp_path: Path) -> answers.AnswerBank:
    rules = {"answers": [{"match": ["authorized to work"], "answer": "Yes"},
                         {"match": ["visa sponsorship"], "answer": "No"},
                         {"match": ["privacy policy"], "answer": "Yes"}]}
    (tmp_path / "answers.yaml").write_text(yaml.safe_dump(rules))
    return answers.load_bank(PROFILE, tmp_path)


@pytest.mark.browser
def test_fill_then_verify_flags_only_the_unanswerable_question(form_page, tmp_path: Path) -> None:
    resume = tmp_path / RESUME_NAME
    resume.write_bytes(b"%PDF-1.4 test")
    adapter = ADAPTERS["greenhouse"]()
    report = adapter.fill(form_page, resume, make_bank(tmp_path))
    assert report.fill_problems == []
    result = verify(report.fields, report.plan, resume_file=RESUME_NAME, company="Fabrikam", other_companies=[],
                    allowed_text="", page_errors=report.page_errors)
    assert result.problems == ["no answer for required question: What is your favorite color?"]
    values = {f.label: f.value for f in report.fields}
    assert values["Email"] == "alex.rivera@example.com"
    assert values["Resume/CV"] == RESUME_NAME
    assert values["I acknowledge the privacy policy"] == "checked"


@pytest.mark.browser
def test_confirmation_and_captcha_detection(browser) -> None:
    adapter = ADAPTERS["ashby"]()
    page = browser.new_page()
    try:
        page.set_content("<p>Hello</p>")
        assert not adapter.captcha_present(page)
        page.set_content("<p>Please verify you are human to continue</p>")
        assert adapter.captcha_present(page)
        page.set_content("<p>Thank you for applying. We received it.</p>")
        assert adapter.confirmed(page)
    finally:
        page.close()
