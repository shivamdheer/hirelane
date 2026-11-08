from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hirelane.config import Paths
from hirelane.db import DB
from hirelane.models import STATUS_NEEDS_YOU, STATUS_NEW, STATUS_REVIEW, STATUS_SUBMITTED, Posting
from hirelane.web.app import create_app


def add(db: DB, job_id: str, company: str, status: str, **fields: str) -> str:
    p = Posting(ats="greenhouse", slug=company.lower(), job_id=job_id, company=company, title="Data Analyst",
                location="Remote, US", apply_url=f"https://job-boards.greenhouse.io/{company.lower()}/jobs/{job_id}",
                description="SQL and Tableau")
    job = db.add_posting(p, status=status, track="data", fit="A", score=8.0)
    if fields:
        db.update_job(job.key, **fields)
    return job.key


@pytest.fixture
def seeded(home: Paths):
    with DB(home.db) as db:
        add(db, "1", "Fabrikam", STATUS_NEW)
        add(db, "2", "Contoso", STATUS_NEEDS_YOU, needs_reason="A CAPTCHA is on the form.")
        add(db, "3", "Adatum", STATUS_REVIEW, needs_reason="Filled and verified.")
        add(db, "4", "Tailspin", STATUS_SUBMITTED, submitted_at="2026-03-10T12:00:00+0000")
        db.add_question("greenhouse:contoso:2", "What is your favorite color?", [])
        db.add_proposal(experience="northwind", kind="skill", text="dbt")
        run_id = db.start_run("source")
        db.finish_run(run_id, True, "4 queued")
    return TestClient(create_app(home))


def test_home_shows_counts_and_waiting_items(seeded: TestClient) -> None:
    r = seeded.get("/")
    assert r.status_code == 200
    html = r.text
    assert "New roles to prepare" in html
    assert "2 applications" in html and "1 form question" in html and "1 proposed addition" in html
    assert "4 queued" in html
    assert "Needs you (3)" in html          # two jobs in need and one open question


def test_home_on_an_empty_install(home: Paths) -> None:
    html = TestClient(create_app(home)).get("/").text
    assert "Nothing is waiting for you." in html and "No runs yet." in html
    assert "review" in html


def test_needs_page_lists_jobs_and_questions(seeded: TestClient) -> None:
    html = seeded.get("/needs").text
    assert "What is your favorite color?" in html
    assert "Contoso, Data Analyst" in html and "A CAPTCHA is on the form." in html
    assert "hirelane finish greenhouse:adatum:3" in html
    assert "Fabrikam" not in html and "Tailspin" not in html


def test_answering_a_question_saves_it_and_retries_the_job(seeded: TestClient, home: Paths) -> None:
    with DB(home.db) as db:
        qid = db.open_questions()[0]["id"]
    r = seeded.post(f"/questions/{qid}", data={"answer": "Green"}, follow_redirects=False)
    assert r.status_code == 303 and "Saved" in r.headers["location"].replace("%20", " ")
    assert "favorite color" in (home.config / "answers_learned.yaml").read_text()
    with DB(home.db) as db:
        assert db.open_questions() == []
        job = db.get_job("greenhouse:contoso:2")
        assert job is not None and job.status == "Approved"


def test_empty_answers_are_not_saved(seeded: TestClient, home: Paths) -> None:
    with DB(home.db) as db:
        qid = db.open_questions()[0]["id"]
    seeded.post(f"/questions/{qid}", data={"answer": "   "}, follow_redirects=False)
    assert not (home.config / "answers_learned.yaml").exists()


def test_job_actions_and_safe_redirects(seeded: TestClient, home: Paths) -> None:
    form = {"key": "greenhouse:contoso:2", "action": "skip", "next": "//evil.example.com"}
    r = seeded.post("/jobs/action", data=form, follow_redirects=False)
    assert r.headers["location"].startswith("/needs?msg=")
    with DB(home.db) as db:
        assert db.get_job("greenhouse:contoso:2").status == "Skip"  # type: ignore[union-attr]
    illegal = {"key": "greenhouse:tailspin:4", "action": "approve"}
    bad = seeded.post("/jobs/action", data=illegal, follow_redirects=False)
    assert "not%20possible" in bad.headers["location"]


def test_screenshots_are_served_only_from_the_runs_folder(seeded: TestClient, home: Paths) -> None:
    day = home.runs / "2026-03-10"
    day.mkdir(parents=True)
    (day / "greenhouse_adatum_3_filled.png").write_bytes(b"\x89PNG\r\n")
    assert seeded.get("/shots/2026-03-10/greenhouse_adatum_3_filled.png").status_code == 200
    assert "/shots/2026-03-10/greenhouse_adatum_3_filled.png" in seeded.get("/needs").text
    assert seeded.get("/shots/2026-03-10/..%2F..%2Fsecret.png").status_code == 404
    assert seeded.get("/shots/2026-03-10/missing.png").status_code == 404


def test_applications_filter_by_status(seeded: TestClient) -> None:
    everything = seeded.get("/applications").text
    assert all(name in everything for name in ("Fabrikam", "Contoso", "Adatum", "Tailspin"))
    only = seeded.get("/applications?status=Submitted").text
    assert "Tailspin" in only and "Fabrikam" not in only
    assert "Fabrikam" in seeded.get("/applications?status=nonsense").text      # an unknown filter shows everything


def test_job_detail_and_missing_job(seeded: TestClient) -> None:
    html = seeded.get("/jobs", params={"key": "greenhouse:contoso:2"}).text
    assert "A CAPTCHA is on the form." in html and "No resume has been built" in html
    assert seeded.get("/jobs", params={"key": "nope"}).status_code == 404


def test_resume_download_requires_a_file_inside_the_resumes_folder(seeded: TestClient, home: Paths) -> None:
    pdf = home.resumes / "Alex_Rivera_Resume_Contoso.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    outside = home.home / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4 fake")
    with DB(home.db) as db:
        db.save_resume("greenhouse:contoso:2", str(pdf), "x", True, [], [], 100, "")
        db.save_resume("greenhouse:adatum:3", str(outside), "x", True, [], [], 100, "")
    ok = seeded.get("/resume", params={"key": "greenhouse:contoso:2"})
    assert ok.status_code == 200 and ok.headers["content-type"] == "application/pdf"
    assert seeded.get("/resume", params={"key": "greenhouse:adatum:3"}).status_code == 404
    assert seeded.get("/resume", params={"key": "greenhouse:fabrikam:1"}).status_code == 404


def studio_client(home: Paths) -> TestClient:
    from tests.bank_fixture import write_bank
    write_bank(home.experience)
    with DB(home.db) as db:
        db.add_proposal(experience="", kind="skill", text="kafka", reason="Contoso asks for it.")
    return TestClient(create_app(home))


def test_studio_lists_facts_and_pending_proposals(seeded: TestClient, home: Paths) -> None:
    c = studio_client(home)
    html = c.get("/studio").text
    assert "Northwind Analytics" in html and "Skill: dbt" in html
    assert "Spark (denied)" in html and "Where did you use it?" in html


def test_approving_a_skill_proposal_writes_the_fact_bank(seeded: TestClient, home: Paths) -> None:
    c = studio_client(home)
    with DB(home.db) as db:
        pid = next(p["id"] for p in db.proposals() if p["text"] == "kafka")
    missing = c.post(f"/proposals/{pid}", data={"decision": "approve"}, follow_redirects=False)
    assert "choose%20which%20experience" in missing.headers["location"]
    done = c.post(f"/proposals/{pid}", data={"decision": "approve", "experience": "northwind"}, follow_redirects=False)
    assert done.status_code == 303
    assert "kafka" in (home.experience / "northwind.yaml").read_text()
    with DB(home.db) as db:
        assert [p["text"] for p in db.proposals()] == ["dbt"] and db.proposals("approved")[0]["id"] == pid
    assert c.post(f"/proposals/{pid}", data={"decision": "approve"}).status_code == 404     # already decided


def test_rejecting_a_proposal_leaves_the_facts_alone(seeded: TestClient, home: Paths) -> None:
    c = studio_client(home)
    before = (home.experience / "northwind.yaml").read_text()
    with DB(home.db) as db:
        pid = db.proposals()[0]["id"]
    c.post(f"/proposals/{pid}", data={"decision": "reject"})
    assert (home.experience / "northwind.yaml").read_text() == before
    with DB(home.db) as db:
        assert db.proposals("rejected")
    assert c.post(f"/proposals/{pid}", data={"decision": "maybe"}).status_code == 404
