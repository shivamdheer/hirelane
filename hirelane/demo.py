"""Demo data for a fictional candidate, Alex Rivera. Everything here is invented, nothing touches the network.

``hirelane demo`` seeds an empty home directory with this data and starts the web interface so every page has
something to show.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import yaml

from . import build, facts
from .config import Paths
from .db import DB
from .models import (
    STATUS_APPROVED,
    STATUS_BUILD_FAILED,
    STATUS_INTERVIEW,
    STATUS_NEEDS_YOU,
    STATUS_NEW,
    STATUS_READY,
    STATUS_REJECTED,
    STATUS_REVIEW,
    STATUS_SUBMITTED,
    Posting,
)
from .profile import load_profile

PROFILE: dict[str, Any] = {
    "name": "Alex Rivera", "email": "alex.rivera@example.com", "phone": "+1 555 0100",
    "location": {"city": "Springfield", "region": "IL", "country": "US", "postal_code": "62701"},
    "links": {"github": "https://github.com/alex-rivera-example"},
    "tracks": [
        {"name": "data", "label": "Data analytics", "titles": ["data analyst", "analytics engineer"],
         "skills": ["sql", "python", "tableau", "dbt", "excel"]},
        {"name": "ops", "label": "Operations", "titles": ["operations analyst", "business analyst"],
         "skills": ["sql", "excel", "process improvement", "stakeholder management"]},
    ],
    "level": {"max_years": 2},
    "search": {"scope": "country", "countries": ["US"], "include_remote": True},
    "salary": {"floor": 60000, "expectation": "75000"},
    "knockouts": {"needs_sponsorship": False, "has_clearance": False, "degree": "bachelors"},
}

EXPERIENCE: dict[str, dict[str, Any]] = {
    "northwind_analytics": {
        "kind": "work", "name": "Northwind Analytics", "title": "Data Analyst", "location": "Springfield, IL",
        "dates": {"start": "Jun 2023", "end": "Aug 2025"},
        "bullets": [
            {"id": "dash", "text": "Built weekly sales dashboards in Tableau used by 12 regional managers.",
             "skills": ["tableau", "sql"], "tracks": ["data"],
             "variants": ["Created weekly Tableau sales dashboards for 12 regional managers."]},
            {"id": "etl", "text": "Wrote SQL pipelines that cut monthly reporting time from 5 days to 2.",
             "skills": ["sql"], "tracks": ["data", "ops"]},
            {"id": "audit", "text": "Documented and streamlined the order audit process with finance stakeholders.",
             "skills": ["process improvement", "stakeholder management"], "tracks": ["ops"]},
            {"id": "py", "text": "Automated data cleaning with Python and pandas for 4 recurring reports.",
             "skills": ["python", "pandas"]},
        ],
        "skills": [{"name": "SQL"}, {"name": "Tableau"}, {"name": "Python"}, {"name": "pandas"}, {"name": "Excel"},
                   {"name": "Process improvement"}, {"name": "Stakeholder management"},
                   {"name": "Spark", "status": "denied"}],
    },
    "fabrikam_cafe": {
        "kind": "work", "name": "Fabrikam Cafe", "title": "Shift Lead", "location": "Springfield, IL",
        "dates": {"start": "Jun 2021", "end": "Aug 2022"},
        "bullets": [
            {"id": "train", "text": "Trained 6 new hires on the register and the opening checklist.",
             "skills": ["stakeholder management"]},
            {"id": "count", "text": "Reconciled daily cash counts in Excel and flagged variances to the owner.",
             "skills": ["excel"], "tracks": ["ops"]},
        ],
        "skills": [{"name": "Excel"}],
    },
    "campus_bikes": {
        "kind": "project", "name": "Campus Bike Share Analysis", "title": "Course project",
        "location": "Springfield, IL",
        "dates": {"start": "Jan 2023", "end": "May 2023"},
        "bullets": [
            {"id": "model", "text": "Modeled station demand with Python and scikit-learn on 18 months of trip data.",
             "skills": ["python", "scikit-learn"], "tracks": ["data"]},
            {"id": "brief", "text": "Presented findings to the city transit office in a 15 minute briefing.",
             "skills": ["stakeholder management"]},
        ],
        "skills": [{"name": "scikit-learn"}],
    },
    "lincoln_state": {
        "kind": "education", "name": "Lincoln State University", "title": "B.S. in Statistics",
        "location": "Springfield, IL", "dates": {"start": "Aug 2019", "end": "May 2023"},
        "detail": "Relevant coursework: regression, databases, experimental design",
    },
}

DESCRIPTION = ("You will answer business questions with data. We use SQL, Python and Tableau every day, build "
               "dashboards for managers, and work with stakeholders across the company. {extra}")

# company, slug, id, title, location, status, fit, extra text, final state notes
JOBS: list[tuple[str, str, str, str, str, str, str, str]] = [
    ("Fabrikam Analytics", "fabrikam", "1001", "Data Analyst", "Remote, US", STATUS_NEW, "A", "Excel is a plus."),
    ("Contoso Health", "contoso", "1002", "Junior Data Analyst", "Chicago, IL", STATUS_READY, "A", "pandas helps."),
    ("Adatum Logistics", "adatum", "1003", "Operations Analyst", "Indianapolis, IN", STATUS_READY, "B",
     "Process improvement matters. dbt and Airflow are used on the team."),
    ("Tailspin Toys", "tailspin", "1004", "Business Analyst", "Remote, US", STATUS_APPROVED, "B",
     "Stakeholder management is key."),
    ("Litware Energy", "litware", "1005", "Data Analyst", "St. Louis, MO", STATUS_REVIEW, "A", "Tableau is required."),
    ("Wide World Importers", "wideworld", "1006", "Analytics Engineer", "Remote, US", STATUS_NEEDS_YOU, "B",
     "Spark and dbt are used."),
    ("Proseware", "proseware", "1007", "Data Analyst", "Madison, WI", STATUS_SUBMITTED, "A", "SQL and Python."),
    ("Humongous Insurance", "humongous", "1008", "Operations Analyst", "Remote, US", STATUS_SUBMITTED, "B",
     "Excel and SQL."),
    ("Alpine Ski House", "alpine", "1009", "Business Analyst", "Denver, CO", STATUS_INTERVIEW, "A", "SQL and Excel."),
    ("Lucerne Publishing", "lucerne", "1010", "Data Analyst", "Remote, US", STATUS_REJECTED, "C", "Tableau."),
    ("Coho Winery", "coho", "1011", "Data Analyst", "Remote, US", STATUS_BUILD_FAILED, "B", "SQL."),
]


def is_seeded(paths: Paths) -> bool:
    return paths.db.exists() and paths.profile_file.exists()


def seed(paths: Paths, now: datetime) -> None:
    """Fill an empty home with the demo candidate, jobs, resumes, questions and replies."""
    paths.ensure()
    paths.profile_file.write_text(yaml.safe_dump(PROFILE, sort_keys=False))
    if not paths.settings_file.exists():
        paths.settings_file.write_text("submit_mode: review\ndaily_cap: 10\nweb_port: 8766\n")
    for key, raw in EXPERIENCE.items():
        facts.save_experience(facts.parse_experience(raw, key), paths.experience)
    profile, bank = load_profile(paths.profile_file), facts.load_bank(paths.experience)
    with DB(paths.db) as db:
        for i, (company, slug, jid, title, loc, status, fit, extra) in enumerate(JOBS):
            posting = Posting(
                ats="greenhouse", slug=slug, job_id=jid, company=company, title=title, location=loc,
                posted=(now - timedelta(days=i % 5)).strftime("%Y-%m-%d"), remote="Remote" in loc,
                apply_url=f"https://job-boards.greenhouse.io/{slug}/jobs/{jid}", pay="$70,000-$85,000",
                description=DESCRIPTION.format(extra=extra))
            track = "ops" if "Operations" in title or "Business" in title else "data"
            job = db.add_posting(posting, status=STATUS_NEW, track=track, fit=fit, score=9.0 - i * 0.4, now=now)
            if status == STATUS_NEW:
                continue
            out = build.build_resume(db.get_job(job.key) or job, db, bank, profile, paths, now=now)
            if status == STATUS_BUILD_FAILED:
                db.update_job(job.key, status=status, needs_reason="keyword coverage check failed twice")
                continue
            if not out.ok:
                continue
            fields: dict[str, Any] = {"status": status}
            if status == STATUS_REVIEW:
                fields["needs_reason"] = f"Filled and verified. Review it, then run: hirelane finish {job.key}."
            if status == STATUS_NEEDS_YOU:
                fields["needs_reason"] = "A CAPTCHA is on the form. Finish it yourself with: hirelane finish."
            if status in (STATUS_SUBMITTED, STATUS_INTERVIEW, STATUS_REJECTED):
                fields["submitted_at"] = (now - timedelta(days=1 + i % 3)).isoformat()
            db.update_job(job.key, **fields)
        db.add_question("greenhouse:wideworld:1006", "What is your preferred pronoun?", [], now)
        db.add_question("greenhouse:tailspin:1004", "Are you willing to travel up to 10 percent?", ["Yes", "No"], now)
        db.add_proposal(experience="", kind="skill", text="dbt", reason="Adatum Logistics asks for it.", now=now)
        db.add_proposal(experience="", kind="skill", text="airflow", reason="Adatum Logistics asks for it.", now=now)
        db.add_proposal(experience="northwind_analytics", kind="variant", target="etl",
                        text="Wrote SQL pipelines that reduced monthly reporting from 5 days to 2.",
                        reason="A reword the checks accepted as new wording. Confirm it is accurate.", now=now)
        for task, summary in (("source", "6 queued from 212 postings on 8 boards. Dropped: title 140, level 31"),
                              ("build", "5 resumes built, 1 failed, 0 approved automatically"),
                              ("submit", "1 review, 1 needs_you")):
            run_id = db.start_run(task, now - timedelta(hours=3))
            db.finish_run(run_id, True, summary, now - timedelta(hours=3))
        replies = (
            ("demo-1", 5, "talent@alpineskihouse.example.com", "Let's schedule a call", "interview",
             "Alpine Ski House", "greenhouse:alpine:1009", "Recruiter asks for a 30 minute call."),
            ("demo-2", 9, "jobs@lucernepublishing.example.com", "Your application", "rejection",
             "Lucerne Publishing", "greenhouse:lucerne:1010", ""),
        )
        for thread, hours, sender, subject, kind, company, key, summary in replies:
            db.save_email(thread, received=(now - timedelta(hours=hours)).isoformat(), from_addr=sender,
                          subject=subject, kind=kind, company=company, job_key=key, summary=summary, now=now)
