from __future__ import annotations

import json

import pytest

from hirelane import ats_gate, build
from hirelane.config import Paths
from hirelane.db import DB
from hirelane.facts import FactBank, load_bank
from hirelane.models import STATUS_BUILD_FAILED, STATUS_NEW, STATUS_READY, Posting
from hirelane.profile import parse_profile
from hirelane.resume import ResumeContent
from tests.bank_fixture import write_bank
from tests.fakes import FakeProvider
from tests.profile_fixture import ALEX_PROFILE

PROFILE = parse_profile(ALEX_PROFILE)
JD = "Data analyst. SQL, Tableau, Python and pandas dashboards. Spark is a plus."


@pytest.fixture
def env(home: Paths):
    bank: FactBank = load_bank(write_bank(home.experience))
    with DB(home.db) as db:
        posting = Posting(ats="greenhouse", slug="fabrikam", job_id="9", company="Fabrikam, Inc.",
                          title="Data Analyst", description=JD)
        job = db.add_posting(posting, status=STATUS_NEW, track="data")
        yield home, db, bank, job


def test_build_saves_pdf_record_gate_result_and_proposals(env) -> None:
    home, db, bank, job = env
    out = build.build_resume(job, db, bank, PROFILE, home)
    assert out.ok and out.path is not None
    assert out.path.name == "Alex_Rivera_Resume_Fabrikam.pdf" and out.path.exists()
    saved = db.get_resume(job.key)
    assert saved is not None and saved["ok"] and len(saved["sha256"]) == 64
    assert ResumeContent.from_json(saved["record"]).name == "Alex Rivera"
    updated = db.get_job(job.key)
    assert updated is not None and updated.status == STATUS_READY and updated.resume_file == str(out.path)
    assert json.loads(updated.gaps) == ["spark"]
    assert [p["text"] for p in db.proposals()] == ["spark"]


def test_a_failing_rewrite_falls_back_to_approved_wording(env, monkeypatch: pytest.MonkeyPatch) -> None:
    home, db, bank, job = env
    calls: list[object] = []
    real = ats_gate.check_pdf

    def flaky(path, content, bank, **kw):
        calls.append(content)
        result = real(path, content, bank, **kw)
        if len(calls) == 1:
            result.problems.append("forced failure")
        return result

    monkeypatch.setattr(ats_gate, "check_pdf", flaky)
    reply = json.dumps({"0": "Delivered weekly Tableau sales dashboards to 12 regional managers."})
    out = build.build_resume(job, db, bank, PROFILE, home, FakeProvider(reply))
    assert out.ok and len(calls) == 2
    record = ResumeContent.from_json(db.get_resume(job.key)["record"])  # type: ignore[index]
    assert all(line.provenance != "rewrite" for line in record.bullet_lines())


def test_two_failures_mark_the_job_build_failed(env, monkeypatch: pytest.MonkeyPatch) -> None:
    home, db, bank, job = env
    real = ats_gate.check_pdf

    def always_bad(path, content, bank, **kw):
        result = real(path, content, bank, **kw)
        result.problems.append("forced failure")
        return result

    monkeypatch.setattr(ats_gate, "check_pdf", always_bad)
    out = build.build_resume(job, db, bank, PROFILE, home)
    assert not out.ok and out.problems == ["forced failure"]
    updated = db.get_job(job.key)
    assert updated is not None and updated.status == STATUS_BUILD_FAILED
    assert "forced failure" in updated.needs_reason
    assert db.get_resume(job.key)["ok"] is False  # type: ignore[index]


def test_read_through_notes_are_stored_as_warnings(env) -> None:
    home, db, bank, job = env
    reply = json.dumps({"notes": ["The opening line is generic."]})

    def answer(system: str, user: str) -> str:
        return json.dumps({}) if "edit resume bullets" in system else reply

    out = build.build_resume(job, db, bank, PROFILE, home, FakeProvider(answer))
    assert out.ok and "The opening line is generic." in out.warnings
    assert "The opening line is generic." in db.get_resume(job.key)["warnings"]  # type: ignore[index]
