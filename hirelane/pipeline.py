"""The day's work in one place: source, build, approve, submit. Each step is a function so cron, launchd,
systemd and the web interface can run any of them alone, and ``run_day`` runs them in order.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

from . import answers as answer_store
from . import build, companies, facts, sourcing
from .config import Paths, Settings, get_paths, load_settings, now
from .db import DB
from .models import STATUS_APPROVED, STATUS_NEW, STATUS_READY
from .profile import Profile, load_profile
from .providers.base import Provider
from .sources.base import HttpClient
from .submit import runner

log = logging.getLogger(__name__)

T = TypeVar("T")
STEPS = ("source", "build", "submit")


@dataclass
class Env:
    paths: Paths
    settings: Settings
    profile: Profile
    db: DB
    bank: facts.FactBank
    provider: Provider | None = None
    client_factory: Callable[[], HttpClient] | None = None
    open_page: Callable[[bool], AbstractContextManager[Any]] | None = None
    clock: Callable[[], datetime] = field(default=lambda: now())


def load_env(provider: Provider | None = None) -> Env:
    paths = get_paths().ensure()
    settings = load_settings(paths.settings_file)
    return Env(paths=paths, settings=settings, profile=load_profile(paths.profile_file), db=DB(paths.db),
               bank=facts.load_bank(paths.experience), provider=provider, clock=lambda: now(settings))


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion. When the calling thread already has a running loop, as it does under the
    Playwright sync API, the coroutine gets a thread of its own."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def run_source(env: Env) -> str:
    cs = companies.load_companies(env.paths.companies_file)
    if not cs:
        return "no companies listed, add some with `hirelane companies add`"
    t = env.clock()
    client = env.client_factory() if env.client_factory else None
    report = _run(sourcing.run_sourcing(env.db, env.profile, env.settings, env.bank, cs, t.date(), t, client))
    dropped = ", ".join(f"{k} {v}" for k, v in report.dropped.most_common(4))
    failed = f", {len(report.boards_failed)} boards failed" if report.boards_failed else ""
    return (f"{len(report.queued)} queued from {report.seen} postings on {report.boards_ok} boards{failed}. "
            f"Dropped: {dropped or 'none'}")


def run_build(env: Env) -> str:
    built = failed = 0
    for job in env.db.jobs(STATUS_NEW):
        outcome = build.build_resume(job, env.db, env.bank, env.profile, env.paths, env.provider, env.clock())
        built += outcome.ok
        failed += not outcome.ok
    approved = auto_approve(env)
    return f"{built} resumes built, {failed} failed, {approved} approved automatically"


def auto_approve(env: Env) -> int:
    """With auto_approve set to fit_a, strong matches with a clean resume are approved for the user."""
    if env.settings.auto_approve != "fit_a":
        return 0
    n = 0
    for job in env.db.jobs(STATUS_READY):
        record = env.db.get_resume(job.key)
        if job.fit == "A" and record and record["ok"] and not job.gap_list:
            env.db.update_job(job.key, status=STATUS_APPROVED, decided_at=env.clock().isoformat())
            n += 1
    return n


def run_submit(env: Env) -> str:
    approved = env.db.jobs(STATUS_APPROVED)
    if not approved:
        return "nothing approved to fill"
    if env.open_page is None:
        env.open_page = lambda headless: browser_page(env.paths, headless)
    ctx = runner.RunContext(db=env.db, settings=env.settings, paths=env.paths,
                            answers=answer_store.load_bank(env.profile, env.paths.config),
                            allowed_text=env.bank.all_text(), open_page=env.open_page, now=env.clock)
    results = runner.run_submissions(ctx)
    tally: dict[str, int] = {}
    for r in results:
        tally[r.outcome] = tally.get(r.outcome, 0) + 1
    return ", ".join(f"{n} {k}" for k, n in sorted(tally.items())) or "nothing processed"


@contextmanager
def browser_page(paths: Paths, headless: bool) -> Iterator[Any]:
    from .submit.browser import open_context

    with open_context(paths.data / "browser-profile", headless) as context:
        yield context.new_page()


STEP_FUNCS: dict[str, Callable[[Env], str]] = {"source": run_source, "build": run_build, "submit": run_submit}


def run_step(env: Env, name: str) -> tuple[bool, str]:
    """Run one step and record it in the runs table. A failure is recorded and returned, never raised."""
    run_id = env.db.start_run(name, env.clock())
    try:
        summary = STEP_FUNCS[name](env)
        ok = True
    except Exception as e:  # a failed step must not stop the next one or hide in a stack trace
        log.exception("step %s failed", name)
        summary, ok = f"{type(e).__name__}: {str(e)[:200]}", False
    env.db.finish_run(run_id, ok, summary, env.clock())
    return ok, summary


def run_day(env: Env, steps: tuple[str, ...] = STEPS) -> list[tuple[str, bool, str]]:
    out = []
    for name in steps:
        ok, summary = run_step(env, name)
        out.append((name, ok, summary))
    return out
