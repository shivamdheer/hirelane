"""The fictional candidate used across the tests."""
from __future__ import annotations

from typing import Any

ALEX_PROFILE: dict[str, Any] = {
    "name": "Alex Rivera",
    "email": "alex.rivera@example.com",
    "phone": "+1 555 0100",
    "location": {"city": "Springfield", "region": "IL", "country": "US", "postal_code": "62701"},
    "links": {"github": "https://github.com/alex-rivera-example"},
    "tracks": [
        {"name": "data", "label": "Data analytics",
         "titles": ["data analyst", "analytics engineer", "business intelligence"],
         "skills": ["sql", "python", "tableau", "dbt", "excel"]},
        {"name": "ops", "label": "Operations",
         "titles": ["operations analyst", "business analyst"],
         "skills": ["sql", "excel", "process improvement", "stakeholder"],
         "exclude_titles": ["sales"]},
    ],
    "level": {"max_years": 2, "allow_titles": ["associate product manager"]},
    "search": {"scope": "country", "countries": ["US"], "include_remote": True},
    "salary": {"floor": 60000, "expectation": "75000"},
    "knockouts": {"needs_sponsorship": False, "has_clearance": False, "degree": "bachelors",
                  "avoid_terms": ["commission only"]},
}
