"""Build one tailored resume for one job: tailor, render, run the ATS gate, and keep the record.

A resume that fails the gate is rebuilt once from the approved wording only, with no model rewording. A second
failure marks the job as build failed with the exact reason, and nothing is attached to any application.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import ats_gate, pdf, tailor
from .config import Paths
from .db import DB
from .facts import FactBank
from .models import STATUS_BUILD_FAILED, STATUS_READY, Job
from .profile import Profile
from .providers.base import Provider
from .readthrough import read_through

log = logging.getLogger(__name__)


@dataclass
class BuildOutcome:
    ok: bool
    path: Path | None = None
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    proposals: int = 0
    rewrites: int = 0


def build_resume(job: Job, db: DB, bank: FactBank, profile: Profile, paths: Paths,
                 provider: Provider | None = None, now: datetime | None = None) -> BuildOutcome:
    filename = pdf.resume_filename(profile.first_name, profile.last_name, job.company)
    out_path = paths.resumes / filename
    problems: list[str] = []
    for use_provider in (provider, None):
        result = tailor.tailor(job, bank, profile, use_provider)
        rendered = pdf.render(result.content, out_path)
        gate = ats_gate.check_pdf(rendered.path, rendered.content, bank, expected_filename=filename,
                                  jd_text=job.desc_text)
        problems = gate.problems
        if gate.ok:
            notes = [*gate.warnings, *read_through(rendered.content, job.role, job.desc_text, provider)]
            gate.warnings = notes
            db.save_resume(job.key, str(rendered.path), gate.sha256, True, [], notes, gate.coverage,
                           rendered.content.to_json(), now)
            for p in result.proposals:
                db.add_proposal(experience=p.experience, kind=p.kind, target=p.target, text=p.text, reason=p.reason,
                                job_key=job.key, now=now)
            db.update_job(job.key, status=STATUS_READY, resume_file=str(rendered.path), file_key=job.file_key,
                          gaps=json.dumps(result.gaps), needs_reason="")
            return BuildOutcome(True, rendered.path, [], gate.warnings, len(result.proposals), result.rewrites)
        if use_provider is None:
            break
        log.info("gate failed for %s with rewording, rebuilding from approved wording: %s", job.key, problems)
    db.save_resume(job.key, str(out_path), "", False, problems, [], 0, "", now)
    db.update_job(job.key, status=STATUS_BUILD_FAILED, needs_reason=" | ".join(problems)[:300])
    return BuildOutcome(False, None, problems)
