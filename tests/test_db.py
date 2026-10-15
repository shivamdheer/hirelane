from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hirelane.db import DB
from hirelane.models import STATUS_APPROVED, STATUS_NEW, STATUS_SUBMITTED, Posting

NOW = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)


def posting(job_id: str = "101", company: str = "Fabrikam Inc.", title: str = "Data Analyst") -> Posting:
    return Posting(ats="greenhouse", slug="fabrikam", job_id=job_id, company=company, title=title,
                   location="Remote, US", apply_url="https://example.com/apply", description="SQL and Python")


@pytest.fixture
def db(tmp_path):
    with DB(tmp_path / "t.db") as d:
        yield d


def test_add_posting_is_idempotent(db: DB) -> None:
    first = db.add_posting(posting(), status=STATUS_NEW, track="data", now=NOW)
    again = db.add_posting(posting(), status=STATUS_APPROVED)
    assert first.key == "greenhouse:fabrikam:101"
    assert again.status == STATUS_NEW
    assert len(db.jobs()) == 1
    assert first.file_key == "Fabrikam"


def test_update_rejects_unknown_columns(db: DB) -> None:
    job = db.add_posting(posting(), status=STATUS_NEW)
    with pytest.raises(KeyError):
        db.update_job(job.key, nonsense=1)


def test_duplicate_lookup_ignores_suffixes_and_case(db: DB) -> None:
    db.add_posting(posting(), status=STATUS_NEW)
    assert db.find_duplicate("FABRIKAM", "data analyst") is not None
    assert db.find_duplicate("Fabrikam", "Data Engineer") is None


def test_claim_is_exclusive_until_released_or_expired(db: DB) -> None:
    job = db.add_posting(posting(), status=STATUS_APPROVED)
    assert db.claim(job.key, NOW, (STATUS_APPROVED,))
    assert not db.claim(job.key, NOW + timedelta(minutes=5), (STATUS_APPROVED,))
    assert db.claim(job.key, NOW + timedelta(hours=2), (STATUS_APPROVED,))
    db.release(job.key)
    assert db.claim(job.key, NOW + timedelta(hours=2, minutes=1), (STATUS_APPROVED,))


def test_claim_requires_matching_status(db: DB) -> None:
    job = db.add_posting(posting(), status=STATUS_NEW)
    assert not db.claim(job.key, NOW, (STATUS_APPROVED,))


def test_seen_reports_new_once(db: DB) -> None:
    assert db.mark_seen("lever", "abc")
    assert not db.mark_seen("lever", "abc")


def test_submitted_today_counts_by_date_prefix(db: DB) -> None:
    job = db.add_posting(posting(), status=STATUS_NEW)
    db.update_job(job.key, status=STATUS_SUBMITTED, submitted_at="2026-03-02T09:00:00+0000")
    assert db.submitted_today("2026-03-02") == 1
    assert db.submitted_today("2026-03-03") == 0
    assert db.applied_companies() == {"fabrikam"}


def test_meta_roundtrip(db: DB) -> None:
    db.set_meta_json("x", {"a": [1, 2]})
    assert db.get_meta_json("x") == {"a": [1, 2]}
    assert db.get_meta_json("missing", 5) == 5


def test_proposals_are_unique_and_can_be_decided(db: DB) -> None:
    assert db.add_proposal(experience="northwind", kind="skill", text="dbt", reason="posting asks for it")
    assert not db.add_proposal(experience="northwind", kind="skill", text="dbt")
    (pending,) = db.proposals()
    assert pending["status"] == "pending"
    db.decide_proposal(pending["id"], "rejected")
    assert db.proposals() == []
    assert db.proposals("rejected")[0]["text"] == "dbt"
    assert not db.add_proposal(experience="northwind", kind="skill", text="dbt")
    with pytest.raises(ValueError):
        db.decide_proposal(pending["id"], "maybe")
