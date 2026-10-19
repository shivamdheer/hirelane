"""Fact bank for the fictional candidate Alex Rivera. Employers and figures are invented."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

NORTHWIND: dict[str, Any] = {
    "kind": "work", "name": "Northwind Analytics", "title": "Data Analyst", "location": "Springfield, IL",
    "dates": {"start": "Jun 2023", "end": "Aug 2025"},
    "bullets": [
        {"id": "dash", "text": "Built weekly sales dashboards in Tableau used by 12 regional managers.",
         "skills": ["tableau", "sql"], "tracks": ["data"],
         "variants": ["Created weekly Tableau sales dashboards for 12 regional managers."]},
        {"id": "etl", "text": "Wrote SQL pipelines that cut monthly reporting time from 5 days to 2.",
         "skills": ["sql"], "tracks": ["data", "ops"]},
        {"id": "audit", "text": "Documented and streamlined the order audit process with finance stakeholders.",
         "skills": ["process improvement", "stakeholder"], "tracks": ["ops"]},
        {"id": "py", "text": "Automated data cleaning with Python and pandas for 4 recurring reports.",
         "skills": ["python", "pandas"]},
    ],
    "skills": [
        {"name": "SQL", "how": "daily reporting queries"}, {"name": "Tableau"}, {"name": "Python"},
        {"name": "pandas"}, {"name": "Excel"}, {"name": "Process improvement"}, {"name": "Stakeholder management"},
        {"name": "Spark", "status": "denied"}, {"name": "dbt", "status": "unsure"},
    ],
    "metrics": ["12 regional managers", "5 days to 2", "4 recurring reports"],
}

CAMPUS_PROJECT: dict[str, Any] = {
    "kind": "project", "name": "Campus Bike Share Analysis", "title": "Course project", "location": "Springfield, IL",
    "dates": {"start": "Jan 2023", "end": "May 2023"},
    "bullets": [
        {"id": "model", "text": "Modeled station demand with Python and scikit-learn on 18 months of trip data.",
         "skills": ["python", "scikit-learn"], "tracks": ["data"]},
        {"id": "dash", "text": "Presented findings to the city transit office in a 15 minute briefing.",
         "skills": ["stakeholder"]},
    ],
    "skills": [{"name": "scikit-learn"}],
    "metrics": ["18 months", "15 minute"],
}

EDUCATION: dict[str, Any] = {
    "kind": "education", "name": "Lincoln State University", "title": "B.S. in Statistics",
    "location": "Springfield, IL",
    "dates": {"start": "Aug 2019", "end": "May 2023"},
    "detail": "Relevant coursework: regression, databases, experimental design",
}

EXPERIENCE_FILES = {"northwind": NORTHWIND, "campus_bikes": CAMPUS_PROJECT, "lincoln_state": EDUCATION}


def write_bank(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for key, raw in EXPERIENCE_FILES.items():
        (directory / f"{key}.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    return directory
