from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hirelane.actions import ActionError, apply_action
from hirelane.db import DB
from hirelane.models import (
    STATUS_APPROVED,
    STATUS_BUILD_FAILED,
    STATUS_NEEDS_YOU,
    STATUS_NEW,
    STATUS_READY,
    STATUS_SKIP,
    STATUS_SUBMITTED,
    Posting,
)

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path: Path):
    with DB(tmp_path / "t.db") as d:
        yield d


def job(db: DB, status: str) -> str:
    p = Posting(ats="greenhouse", slug="fabrikam", job_id="1", company="Fabrikam", title="Data Analyst")
    return db.add_posting(p, status=status).key


def status(db: DB, key: str) -> str:
    j = db.get_job(key)
    assert j is not None
    return j.status


def test_approve_only_from_ready(db: DB) -> None:
    key = job(db, STATUS_READY)
    apply_action(db, key, "approve", NOW)
    assert status(db, key) == STATUS_APPROVED
    with pytest.raises(ActionError, match="not possible"):
        apply_action(db, key, "approve", NOW)


def test_skip_and_unskip(db: DB) -> None:
    key = job(db, STATUS_NEEDS_YOU)
    apply_action(db, key, "skip", NOW)
    assert status(db, key) == STATUS_SKIP
    apply_action(db, key, "unskip", NOW)
    assert status(db, key) == STATUS_NEW


def test_retry_sends_build_failures_back_to_be_rebuilt(db: DB) -> None:
    key = job(db, STATUS_BUILD_FAILED)
    apply_action(db, key, "retry", NOW)
    assert status(db, key) == STATUS_NEW
    db.update_job(key, status=STATUS_NEEDS_YOU, needs_reason="x", lock_until="later")
    apply_action(db, key, "retry", NOW)
    j = db.get_job(key)
    assert j is not None and j.status == STATUS_APPROVED and j.needs_reason == "" and j.lock_until == ""


def test_mark_submitted_records_the_time_and_an_attempt(db: DB) -> None:
    key = job(db, STATUS_NEEDS_YOU)
    apply_action(db, key, "mark_submitted", NOW)
    j = db.get_job(key)
    assert j is not None and j.status == STATUS_SUBMITTED and j.submitted_at.startswith("2026-03-10")
    assert db.attempt_phases(key) == ["marked_submitted"]


def test_unknown_job_and_action(db: DB) -> None:
    with pytest.raises(ActionError, match="no such job"):
        apply_action(db, "missing", "skip", NOW)
    key = job(db, STATUS_READY)
    with pytest.raises(ActionError, match="unknown action"):
        apply_action(db, key, "explode", NOW)
