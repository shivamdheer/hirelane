"""The ``hirelane`` command line."""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import __version__, demo, digest, doctor, schedule, secrets
from .actions import ActionError, apply_action
from .companies import CompaniesError, Company, add_company, load_companies
from .config import DEMO_HOME_ENV, HOME_ENV, get_paths, load_settings, now, save_setting
from .db import DB
from .init import InitError, run_init
from .models import APPLIED_STATUSES, STATUSES
from .pipeline import STEPS, browser_page, load_env, run_day, run_step
from .profile import ProfileError
from .providers import get_provider

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _print_results(results: list[tuple[str, bool, str]]) -> int:
    code = EXIT_OK
    for name, ok, summary in results:
        print(f"{name}: {'ok' if ok else 'FAILED'}. {summary}")
        code = code if ok else EXIT_FAIL
    return code


def cmd_source(args: argparse.Namespace) -> int:
    return _step("source")


def cmd_build(args: argparse.Namespace) -> int:
    return _step("build")


def cmd_submit(args: argparse.Namespace) -> int:
    return _step("submit")


def _step(name: str) -> int:
    env = load_env()
    env.provider = get_provider(env.settings.ai)
    try:
        ok, summary = run_step(env, name)
    finally:
        env.db.close()
    return _print_results([(name, ok, summary)])


def cmd_run(args: argparse.Namespace) -> int:
    env = load_env()
    env.provider = get_provider(env.settings.ai)
    try:
        steps = tuple(args.steps) if args.steps else STEPS
        return _print_results(run_day(env, steps))
    finally:
        env.db.close()


def cmd_status(args: argparse.Namespace) -> int:
    paths = get_paths().ensure()
    settings = load_settings(paths.settings_file)
    with DB(paths.db) as db:
        counts = db.status_counts()
        print(f"mode: {settings.submit_mode}, daily cap: {settings.daily_cap}")
        for status in STATUSES:
            if counts.get(status):
                print(f"  {status}: {counts[status]}")
        applied = sum(counts.get(s, 0) for s in APPLIED_STATUSES)
        print(f"applied so far: {applied}")
        questions, proposals = len(db.open_questions()), len(db.proposals())
        if questions or proposals:
            print(f"waiting for you: {questions} form questions, {proposals} proposed additions")
    return EXIT_OK


def cmd_jobs(args: argparse.Namespace) -> int:
    paths = get_paths().ensure()
    with DB(paths.db) as db:
        jobs = db.jobs(args.status) if args.status else db.jobs()
        for j in jobs:
            print(f"{j.key}\t{j.status}\t{j.fit or '-'}\t{j.company}\t{j.role}")
        if not jobs:
            print("No jobs yet. Add companies, then run: hirelane run source build")
    return EXIT_OK


def _job_action(action: str) -> Callable[[argparse.Namespace], int]:
    def run(args: argparse.Namespace) -> int:
        paths = get_paths().ensure()
        settings = load_settings(paths.settings_file)
        with DB(paths.db) as db:
            try:
                print(apply_action(db, args.key, action, now(settings)))
            except ActionError as e:
                print(f"error: {e}", file=sys.stderr)
                return EXIT_FAIL
        return EXIT_OK
    return run


def cmd_clear_click(args: argparse.Namespace) -> int:
    paths = get_paths().ensure()
    with DB(paths.db) as db:
        if db.get_job(args.key) is None:
            print("error: no such job", file=sys.stderr)
            return EXIT_FAIL
        db.add_attempt(args.key, "click_cleared", "cleared by the user")
        print("Cleared. The job can be tried again.")
    return EXIT_OK


def cmd_finish(args: argparse.Namespace) -> int:
    from . import answers as answer_store
    from .submit.finish import finish_job
    from .submit.runner import RunContext

    env = load_env()
    ctx = RunContext(db=env.db, settings=env.settings, paths=env.paths,
                     answers=answer_store.load_bank(env.profile, env.paths.config),
                     allowed_text=env.bank.all_text(), now=env.clock,
                     open_page=lambda headless: browser_page(env.paths, headless))
    try:
        print("A browser window will open. Review the form, then submit it yourself.")
        result = finish_job(ctx, args.key)
    finally:
        env.db.close()
    print(f"{result.outcome}: {result.detail}")
    return EXIT_OK if result.outcome == "submitted" else EXIT_FAIL


def cmd_mark_submitted(args: argparse.Namespace) -> int:
    return _job_action("mark_submitted")(args)


def cmd_companies(args: argparse.Namespace) -> int:
    if args.companies_cmd == "list":
        companies = load_companies()
        for c in companies:
            print(f"{c.ats}\t{c.slug}\t{c.name}")
        if not companies:
            print("No companies yet. Add one with: hirelane companies add greenhouse fabrikam \"Fabrikam\"")
        return EXIT_OK
    try:
        added = add_company(Company(args.name, args.ats, args.slug))
    except CompaniesError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    print("Added." if added else "Already listed.")
    return EXIT_OK


def cmd_set_key(args: argparse.Namespace) -> int:
    name = args.name
    value = sys.stdin.readline().strip() if args.stdin else getpass.getpass(f"{name} (input is hidden): ").strip()
    try:
        secrets.set_secret(name, value)
    except secrets.SecretsError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAIL
    print(f"Stored {name} in the system keyring.")
    return EXIT_OK


def cmd_set(args: argparse.Namespace) -> int:
    try:
        raw = args.value
        value: object = int(raw) if raw.lstrip("-").isdigit() else {"true": True, "false": False}.get(raw.lower(), raw)
        save_setting(args.key, value)
    except (ValueError, TypeError) as e:
        print(f"error: {args.key} cannot be set to {args.value!r} ({e})", file=sys.stderr)
        return EXIT_USAGE
    print(f"{args.key} set to {value}")
    return EXIT_OK


def cmd_digest(args: argparse.Namespace) -> int:
    paths = get_paths().ensure()
    settings = load_settings(paths.settings_file)
    t = now(settings)
    day = t.strftime("%Y-%m-%d")
    with DB(paths.db) as db:
        d = digest.build_digest(db, day, f"http://127.0.0.1:{settings.web_port}")
    path = digest.write_digest(d, paths.data / "outbox", day, t)
    print(f"Wrote {path}")
    if settings.google_enabled and not d.empty and not args.no_email:
        from .google import auth, gmail
        from .profile import load_profile
        try:
            gmail.send_digest(auth.service("gmail", "v1"), load_profile(paths.profile_file), d.subject, d.body)
            print("Sent the digest to your own address.")
        except auth.GoogleError as e:
            print(f"note: the digest was not emailed: {e}", file=sys.stderr)
    if args.print:
        print(d.body)
    return EXIT_OK


def cmd_inbox(args: argparse.Namespace) -> int:
    """Read recent mail and update jobs. Does nothing until Gmail is connected."""
    paths = get_paths().ensure()
    settings = load_settings(paths.settings_file)
    if not settings.google_enabled:
        print("Gmail is not connected, so there is nothing to read. "
              "See docs/GOOGLE.md or run `hirelane google connect`.")
        return EXIT_OK
    from . import inbox
    from .google import auth, gmail
    try:
        messages = gmail.fetch_messages(auth.service("gmail", "v1"))
    except auth.GoogleError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAIL
    with DB(paths.db) as db:
        changes = inbox.process(db, messages, get_provider(settings.ai), now(settings))
    for c in changes:
        moved = f" -> {c.moved_to}" if c.moved_to else ""
        print(f"{c.kind}: {c.company or 'unmatched'}{moved}")
    print(f"{len(messages)} messages read, {len(changes)} new.")
    return EXIT_OK
