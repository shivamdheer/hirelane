"""Page routes. Data shaping lives in plain functions so it can be tested without HTTP.

This module avoids postponed annotations on purpose: FastAPI resolves the route signatures at runtime.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from .. import answers as answer_store
from .. import facts
from ..actions import ActionError, apply_action
from ..config import Paths, Settings, load_settings, now
from ..db import DB
from ..models import (
    APPLIED_STATUSES,
    STATUS_APPROVED,
    STATUS_BUILD_FAILED,
    STATUS_NEEDS_YOU,
    STATUS_READY,
    STATUS_REVIEW,
    STATUS_SUBMITTED,
    STATUSES,
    Job,
)
from ..resume import ResumeContent

NEEDS_STATUSES = (STATUS_NEEDS_YOU, STATUS_REVIEW, STATUS_BUILD_FAILED)
RECENT_RUNS = 5


@dataclass
class HomeData:
    queued: int
    ready: int
    approved: int
    needs: int
    applied: int
    submitted_today: int
    daily_cap: int
    mode: str
    open_questions: int
    pending_proposals: int
    runs: list[dict[str, Any]]


def nav_counts(db: DB) -> dict[str, int]:
    counts = db.status_counts()
    needs = sum(counts.get(s, 0) for s in NEEDS_STATUSES) + len(db.open_questions())
    return {"/needs": needs, "/studio": len(db.proposals())}


def home_data(db: DB, settings: Settings) -> HomeData:
    counts = db.status_counts()
    day = now(settings).strftime("%Y-%m-%d")
    return HomeData(
        queued=counts.get("New", 0), ready=counts.get(STATUS_READY, 0), approved=counts.get(STATUS_APPROVED, 0),
        needs=sum(counts.get(s, 0) for s in NEEDS_STATUSES),
        applied=sum(counts.get(s, 0) for s in APPLIED_STATUSES),
        submitted_today=db.submitted_today(day), daily_cap=settings.daily_cap, mode=settings.submit_mode,
        open_questions=len(db.open_questions()), pending_proposals=len(db.proposals()),
        runs=db.last_runs(RECENT_RUNS))


def register(app: FastAPI, get_db: Any) -> None:
    DbDep = Annotated[DB, Depends(get_db)]

    def paths(request: Request) -> Paths:
        p: Paths = request.app.state.paths
        return p

    def page(request: Request, db: DB, template: str, title: str, active: str, **ctx: Any) -> Response:
        render = request.app.state.render
        resp: Response = render(request, template, title, active, counts=nav_counts(db), **ctx)
        return resp

    @app.get("/")
    def home(request: Request, db: DbDep) -> Response:
        settings = load_settings(paths(request).settings_file)
        return page(request, db, "home.html", "Home", "/", data=home_data(db, settings),
                    submitted_status=STATUS_SUBMITTED)


    def back(path: str, message: str) -> RedirectResponse:
        return RedirectResponse(f"{path}?msg={quote(message)}", status_code=303)

    @app.get("/needs")
    def needs(request: Request, db: DbDep) -> Response:
        jobs = db.jobs(*NEEDS_STATUSES, order="added_at")
        return page(request, db, "needs.html", "Needs you", "/needs", jobs=jobs, questions=db.open_questions(),
                    shots={j.key: latest_screenshot(paths(request), j) for j in jobs})

    @app.post("/jobs/action")
    def job_action(request: Request, db: DbDep, key: str = Form(...), action: str = Form(...),
                   next: str = Form("/needs")) -> Response:
        target = next if next.startswith("/") and not next.startswith("//") else "/needs"
        try:
            message = apply_action(db, key, action, now(load_settings(paths(request).settings_file)))
        except ActionError as e:
            return back(target, str(e))
        return back(target, message)

    @app.post("/questions/{question_id}")
    def answer_question(request: Request, question_id: int, db: DbDep, answer: str = Form(...)) -> Response:
        text = answer.strip()
        if not text:
            return back("/needs", "An empty answer was not saved.")
        question = db.answer_question(question_id, text)
        if question is None:
            raise HTTPException(status_code=404, detail="no such question")
        profile_dir = paths(request).config
        answer_store.save_learned(question["label"], text, profile_dir)
        job = db.get_job(question["job_key"])
        if job is not None and job.status == STATUS_NEEDS_YOU:
            apply_action(db, job.key, "retry", now(load_settings(paths(request).settings_file)))
        return back("/needs", "Saved. The answer is used from now on.")

    @app.get("/shots/{day}/{name}")
    def shot(request: Request, day: str, name: str) -> Response:
        runs = paths(request).runs.resolve()
        path = (runs / day / name).resolve()
        if runs not in path.parents or path.suffix != ".png" or not path.is_file():
            raise HTTPException(status_code=404, detail="no such screenshot")
        return FileResponse(path, media_type="image/png")

    @app.get("/applications")
    def applications(request: Request, db: DbDep, status: str = "") -> Response:
        chosen = status if status in STATUSES else ""
        jobs = db.jobs(chosen) if chosen else db.jobs()
        counts = db.status_counts()
        return page(request, db, "applications.html", "Applications", "/applications", jobs=jobs, chosen=chosen,
                    statuses=[(s, counts.get(s, 0)) for s in STATUSES if counts.get(s, 0)])

    @app.get("/jobs")
    def job_detail(request: Request, db: DbDep, key: str) -> Response:
        job = db.get_job(key)
        if job is None:
            raise HTTPException(status_code=404, detail="no such job")
        record = db.get_resume(key)
        content = ResumeContent.from_json(record["record"]) if record and record["record"] else None
        return page(request, db, "job.html", f"{job.company}, {job.role}", "/applications", job=job, record=record,
                    content=content, phases=db.attempt_phases(key), shot=latest_screenshot(paths(request), job),
                    gaps=job.gap_list)

    @app.get("/resume")
    def resume_file(request: Request, db: DbDep, key: str) -> Response:
        record = db.get_resume(key)
        root = paths(request).resumes.resolve()
        if record is None:
            raise HTTPException(status_code=404, detail="no resume for this job")
        path = Path(record["path"]).resolve()
        if root not in path.parents or not path.is_file():
            raise HTTPException(status_code=404, detail="the resume file is missing")
        return FileResponse(path, media_type="application/pdf", filename=path.name)
    @app.get("/studio")
    def studio(request: Request, db: DbDep) -> Response:
        bank = facts.load_bank(paths(request).experience)
        return page(request, db, "studio.html", "Resume studio", "/studio", bank=bank, proposals=db.proposals(),
                    experiences=[(e.key, e.name) for e in bank.of_kind("work", "project")])

    @app.post("/proposals/{proposal_id}")
    def decide_proposal(request: Request, proposal_id: int, db: DbDep, decision: str = Form(...),
                        experience: str = Form("")) -> Response:
        proposal = db.get_proposal(proposal_id)
        if proposal is None or proposal["status"] != "pending":
            raise HTTPException(status_code=404, detail="no such pending proposal")
        if decision == "reject":
            db.decide_proposal(proposal_id, "rejected")
            return back("/studio", "Rejected. It will not be proposed again.")
        if decision != "approve":
            raise HTTPException(status_code=400, detail="decision must be approve or reject")
        directory = paths(request).experience
        try:
            message = facts.apply_proposal(facts.load_bank(directory), proposal, experience, directory)
        except facts.FactsError as e:
            return back("/studio", str(e))
        db.decide_proposal(proposal_id, "approved")
        return back("/studio", message)

def latest_screenshot(paths: Paths, job: Job) -> str:
    """The URL of the newest screenshot taken for a job, or an empty string."""
    safe = job.key.replace(":", "_")
    found = sorted(paths.runs.glob(f"*/{safe}_*.png"))
    if not found:
        return ""
    return f"/shots/{found[-1].parent.name}/{found[-1].name}"
