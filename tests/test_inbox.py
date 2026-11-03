from __future__ import annotations

import json
from pathlib import Path

import pytest

from hirelane import inbox
from hirelane.db import DB
from hirelane.inbox import Message
from hirelane.models import STATUS_INTERVIEW, STATUS_READY, STATUS_REJECTED, STATUS_SUBMITTED, Posting
from tests.fakes import FakeProvider


def msg(thread: str, sender: str, subject: str, body: str = "") -> Message:
    return Message(thread, "2026-03-10T10:00:00+00:00", sender, subject, body)


@pytest.fixture
def db(tmp_path: Path):
    with DB(tmp_path / "t.db") as d:
        for i, (company, status) in enumerate([("Fabrikam", STATUS_SUBMITTED), ("Contoso Labs", STATUS_SUBMITTED),
                                               ("Adatum", STATUS_READY)]):
            p = Posting(ats="greenhouse", slug=company.split()[0].lower(), job_id=str(i), company=company,
                        title="Data Analyst")
            d.add_posting(p, status=status)
        yield d


@pytest.mark.parametrize("subject,body,kind", [
    ("Thanks for applying to Fabrikam", "", "confirmation"),
    ("Your application", "Unfortunately we are moving forward with other candidates.", "rejection"),
    ("Next steps", "We would like to schedule a call with you this week.", "interview"),
    ("Assessment", "Please complete the online assessment on HackerRank.", "assessment"),
    ("Offer", "We are pleased to offer you the role.", "offer"),
    ("Quick job", "Buy gift cards and send the codes, we will reimburse you.", "scam"),
    ("Newsletter", "Our monthly update", "other"),
])
def test_classify(subject: str, body: str, kind: str) -> None:
    assert inbox.classify(subject, body) == kind


def test_scam_signals_beat_other_rules() -> None:
    body = "schedule a call. Also, purchase equipment with a cashier's check"
    assert inbox.classify("Interview invitation", body) == "scam"


def test_rejection_moves_the_matching_job(db: DB) -> None:
    changes = inbox.process(db, [msg("t1", "jobs@fabrikam.com", "Update on your application",
                                     "Unfortunately we will not be moving forward.")])
    assert [(c.kind, c.moved_to) for c in changes] == [("rejection", STATUS_REJECTED)]
    assert db.get_job("greenhouse:fabrikam:0").status == STATUS_REJECTED  # type: ignore[union-attr]


def test_interview_moves_forward_and_matches_the_longest_company_name(db: DB) -> None:
    changes = inbox.process(db, [msg("t2", "recruiting@contosolabs.example.com", "Let's schedule a call", "Hi Alex")])
    assert changes[0].job_key == "greenhouse:contoso:1" and changes[0].moved_to == STATUS_INTERVIEW


def test_a_job_that_was_never_sent_is_not_moved(db: DB) -> None:
    changes = inbox.process(db, [msg("t3", "hr@adatum.com", "Unfortunately", "we regret to inform you")])
    assert changes[0].job_key == "greenhouse:adatum:2" and changes[0].moved_to == ""
    assert db.get_job("greenhouse:adatum:2").status == STATUS_READY  # type: ignore[union-attr]


def test_each_thread_is_handled_once(db: DB) -> None:
    m = msg("t4", "jobs@fabrikam.com", "Update", "we regret to inform you")
    assert len(inbox.process(db, [m])) == 1
    assert inbox.process(db, [m]) == []
    assert len(db.emails()) == 1


def test_unmatched_mail_is_stored_without_a_job(db: DB) -> None:
    (c,) = inbox.process(db, [msg("t5", "news@example.org", "Weekly digest", "hello")])
    assert c.kind == "other" and c.job_key == ""


def test_the_model_only_sees_unplaced_mail_and_cannot_declare_scams(db: DB) -> None:
    reply = json.dumps({"kind": "recruiter", "summary": "A recruiter says hello."})
    p = FakeProvider(reply)
    changes = inbox.process(db, [msg("t6", "hi@fabrikam.com", "Hello", "I am a recruiter at Fabrikam")], p)
    assert changes[0].kind == "recruiter" and changes[0].summary == "A recruiter says hello."
    inbox.process(db, [msg("t7", "jobs@fabrikam.com", "Update", "we regret to inform you")], p)
    assert len(p.calls) == 1                                                  # rules handled the second one
    bad = FakeProvider(json.dumps({"kind": "scam", "summary": "x"}))
    assert inbox.process(db, [msg("t8", "a@b.example", "Hi", "text")], bad)[0].kind == "other"
    assert inbox.process(db, [msg("t9", "a@b.example", "Hi", "text")], FakeProvider("garbage"))[0].kind == "other"
