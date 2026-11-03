from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hirelane import digest
from hirelane.db import DB
from hirelane.models import (
    STATUS_INTERVIEW,
    STATUS_NEEDS_YOU,
    STATUS_READY,
    STATUS_REVIEW,
    STATUS_SUBMITTED,
    Posting,
)

DAY = "2026-03-10"


@pytest.fixture
def db(tmp_path: Path):
    with DB(tmp_path / "t.db") as d:
        yield d


def add(db: DB, n: int, company: str, status: str, **fields: str) -> None:
    p = Posting(ats="greenhouse", slug=company.lower(), job_id=str(n), company=company, title="Data Analyst")
    job = db.add_posting(p, status=status)
    if fields:
        db.update_job(job.key, **fields)


def test_an_empty_day(db: DB) -> None:
    d = digest.build_digest(db, DAY)
    assert d.empty and d.body == "Nothing new today.\n" and d.subject == "hirelane 2026-03-10: nothing new"


def test_sections_and_counts(db: DB) -> None:
    add(db, 1, "Fabrikam", STATUS_SUBMITTED, submitted_at="2026-03-10T09:00:00+0000")
    add(db, 2, "Contoso", STATUS_SUBMITTED, submitted_at="2026-03-09T09:00:00+0000")       # yesterday
    add(db, 3, "Adatum", STATUS_NEEDS_YOU, needs_reason="A CAPTCHA is on the form.")
    add(db, 4, "Tailspin", STATUS_REVIEW)
    add(db, 5, "Northwind", STATUS_READY)
    add(db, 6, "Litware", STATUS_INTERVIEW)
    db.add_question("greenhouse:adatum:3", "Favorite color?", [])
    db.add_proposal(experience="", kind="skill", text="dbt")
    db.save_email("t1", received=DAY, from_addr="jobs@litware.com", subject="Call", kind="interview",
                  company="Litware", job_key="", summary="", now=datetime(2026, 3, 10, 8, 0, tzinfo=UTC))
    d = digest.build_digest(db, DAY, "http://127.0.0.1:8766")
    assert d.subject == "hirelane 2026-03-10: 1 applied, 2 need you"
    assert "Applied today (1)\n  Fabrikam, Data Analyst" in d.body
    assert "Contoso" not in d.body
    assert "  Adatum, Data Analyst - A CAPTCHA is on the form." in d.body
    assert "Interviews and offers (1)" in d.body and "Resumes ready for your approval (1)" in d.body
    assert "Replies (1)\n  interview: Litware" in d.body
    assert "1 form question need an answer." in d.body and "1 proposed addition to your facts" in d.body
    assert d.body.rstrip().endswith("Open hirelane: http://127.0.0.1:8766")


def test_long_lists_are_cut(db: DB) -> None:
    for i in range(11):
        add(db, i, f"Company{i}", STATUS_READY)
    assert "and 3 more" in digest.build_digest(db, DAY).body


def test_write_digest(tmp_path: Path) -> None:
    d = digest.Digest("hirelane x", "Nothing new today.\n", True)
    path = digest.write_digest(d, tmp_path / "outbox", DAY, datetime(2026, 3, 10, 19, 0, tzinfo=UTC))
    assert path.name == "digest-2026-03-10.txt"
    assert path.read_text().startswith("Subject: hirelane x\nDate: 2026-03-10T19:00:00+00:00\n\nNothing new")
