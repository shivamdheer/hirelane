from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from hirelane import demo, facts, truth
from hirelane.config import Paths
from hirelane.db import DB
from hirelane.models import STATUS_NEEDS_YOU, STATUS_READY, STATUS_REVIEW, STATUS_SUBMITTED
from hirelane.resume import ResumeContent
from hirelane.web.app import create_app

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def test_seed_builds_a_complete_demo_home(home: Paths) -> None:
    assert not demo.is_seeded(home)
    demo.seed(home, NOW)
    assert demo.is_seeded(home)
    with DB(home.db) as db:
        counts = db.status_counts()
        assert counts[STATUS_READY] == 2 and counts[STATUS_REVIEW] == 1 and counts[STATUS_NEEDS_YOU] == 1
        assert counts[STATUS_SUBMITTED] == 2 and sum(counts.values()) == len(demo.JOBS)
        assert len(db.open_questions()) == 2 and len(db.proposals()) >= 3 and len(db.emails()) == 2
        assert len(db.last_runs()) == 3


def test_every_demo_resume_passes_the_audit_against_the_demo_bank(home: Paths) -> None:
    demo.seed(home, NOW)
    bank = facts.load_bank(home.experience)
    with DB(home.db) as db:
        records = [db.get_resume(j.key) for j in db.jobs() if db.get_resume(j.key)]
        assert len(records) >= 8
        for record in records:
            assert record is not None and record["ok"]
            assert truth.audit_content(ResumeContent.from_json(record["record"]), bank) == []


def test_demo_data_is_fictional_and_example_only(home: Paths) -> None:
    demo.seed(home, NOW)
    text = "\n".join(p.read_text() for p in home.config.rglob("*.yaml"))
    assert "example.com" in text and "Alex Rivera" in text


def test_the_web_ui_renders_every_page_on_demo_data(home: Paths) -> None:
    demo.seed(home, NOW)
    client = TestClient(create_app(home))
    for path in ("/", "/needs", "/applications", "/studio"):
        r = client.get(path)
        assert r.status_code == 200, path
    assert "Litware Energy" in client.get("/needs").text
    assert "Spark (denied)" in client.get("/studio").text
