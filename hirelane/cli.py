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


def cmd_google(args: argparse.Namespace) -> int:
    from .google import auth
    try:
        if args.google_cmd == "connect":
            auth.connect(Path(args.client_file).expanduser())
            save_setting("google_enabled", True)
            print("Connected. Gmail, Sheets and Calendar features are on.")
        elif args.google_cmd == "disconnect":
            auth.disconnect()
            save_setting("google_enabled", False)
            print("Disconnected. The stored token was removed from the keyring.")
        else:
            print("connected" if auth.is_connected() else "not connected")
    except auth.GoogleError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


def cmd_sheet(args: argparse.Namespace) -> int:
    paths = get_paths().ensure()
    settings = load_settings(paths.settings_file)
    if not settings.google_enabled:
        print("Google is not connected. Run `hirelane google connect` first.", file=sys.stderr)
        return EXIT_FAIL
    from .google import auth, sheets
    try:
        svc = auth.service("sheets", "v4")
        with DB(paths.db) as db:
            sheet_id = sheets.sheet_id_for(svc, db)
            result = sheets.sync(svc, db, sheet_id, now(settings))
    except auth.GoogleError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAIL
    print(f"Pushed {(len(result.decisions) and 0) or result.pushed} rows to https://docs.google.com/spreadsheets/d/{sheet_id}")
    for line in (*result.decisions, *result.errors):
        print(f"  {line}")
    return EXIT_OK


def cmd_slots(args: argparse.Namespace) -> int:
    from datetime import timedelta

    from .config import local_tz
    from .google import auth, calendar
    settings = load_settings(get_paths().ensure().settings_file)
    if not settings.google_enabled:
        print("Google is not connected. Run `hirelane google connect` first.", file=sys.stderr)
        return EXIT_FAIL
    t = now(settings)
    try:
        busy = calendar.fetch_busy(auth.service("calendar", "v3"), t, t + timedelta(days=calendar.DEFAULT_DAYS + 2))
    except auth.GoogleError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAIL
    print("\n".join(calendar.describe(calendar.free_slots(busy, t, local_tz(settings), count=args.count))))
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    findings = doctor.run_checks(get_paths())
    for f in findings:
        print(f"{f.level:5} {f.check:9} {f.message}")
    return EXIT_FAIL if any(f.level == doctor.FAIL for f in findings) else EXIT_OK


def cmd_schedule(args: argparse.Namespace) -> int:
    platform = args.platform or schedule.current_platform()
    home = get_paths().home
    if args.schedule_cmd == "show":
        print("\n".join(schedule.describe()))
        return EXIT_OK
    lines = (schedule.install(platform, home) if args.schedule_cmd == "install" else schedule.uninstall(platform))
    print("\n".join(lines) if lines else "Nothing to do.")
    return EXIT_OK


def _ask(question: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        reply = input(f"{question}{suffix}: ").strip()
    except EOFError:
        return default
    return reply or default


def cmd_init(args: argparse.Namespace) -> int:
    paths = get_paths()
    try:
        result = run_init(paths, Path(args.resume).expanduser() if args.resume else None, _ask, force=args.force)
    except (InitError, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(f"Wrote {len(result.written)} files under {paths.home}.")
    print(f"Imported {_count(result.experiences, 'experience')}, {_count(result.bullets, 'bullet')} and "
          f"{_count(result.skills, 'skill')} as a draft.")
    for w in result.warnings:
        print(f"  note: {w}")
    print("Next: read config/experience/*.yaml and fix anything the import got wrong. Only what is in those files can")
    print("appear on a resume. Then add boards with `hirelane companies add` and try `hirelane run`.")
    return EXIT_OK


def cmd_demo(args: argparse.Namespace) -> int:
    """Seed a separate demo home with a fictional candidate and open the web interface on it."""
    os.environ[HOME_ENV] = os.environ.get(DEMO_HOME_ENV) or str(Path.home() / ".hirelane-demo")
    paths = get_paths().ensure()
    if not demo.is_seeded(paths):
        demo.seed(paths, now(load_settings(paths.settings_file)))
        print(f"Seeded demo data for Alex Rivera in {paths.home}")
    else:
        print(f"Using the existing demo data in {paths.home}")
    if args.no_serve:
        return EXIT_OK
    from .web.serve import serve
    port = args.port or load_settings(paths.settings_file).web_port
    print(f"Open http://127.0.0.1:{port} (Ctrl+C to stop)")
    serve("127.0.0.1", port, paths)
    return EXIT_OK


def cmd_web(args: argparse.Namespace) -> int:
    from .web.serve import serve
    try:
        serve(args.host, args.port)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hirelane", description="Find roles, tailor your resume truthfully, and apply "
                                                              "with a human in the loop.")
    p.add_argument("--version", action="version", version=f"hirelane {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    for name, fn, help_text in (("source", cmd_source, "poll the boards and queue new roles"),
                                ("build", cmd_build, "build a tailored resume for each queued role"),
                                ("submit", cmd_submit, "fill the forms of approved roles")):
        sub.add_parser(name, help=help_text).set_defaults(func=fn)
    run = sub.add_parser("run", help="do the whole day: source, build, submit")
    run.add_argument("steps", nargs="*", choices=STEPS, help="limit the run to some steps")
    run.set_defaults(func=cmd_run)
    ini = sub.add_parser("init", help="import your resume and write the starting config")
    ini.add_argument("--resume", help="a PDF or DOCX resume to import")
    ini.add_argument("--force", action="store_true", help="replace existing config files")
    ini.set_defaults(func=cmd_init)
    sub.add_parser("status", help="counts by status and what waits for you").set_defaults(func=cmd_status)
    jobs = sub.add_parser("jobs", help="list jobs")
    jobs.add_argument("--status", choices=STATUSES)
    jobs.set_defaults(func=cmd_jobs)
    for name, action, help_text in (("approve", "approve", "approve a job with a ready resume"),
                                    ("skip", "skip", "skip a job"), ("retry", "retry", "try a job again")):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("key")
        sp.set_defaults(func=_job_action(action))
    ms = sub.add_parser("mark-submitted", help="record that you submitted a job yourself")
    ms.add_argument("key")
    ms.set_defaults(func=cmd_mark_submitted)
    cc = sub.add_parser("clear-click", help="allow a job to be tried again after you checked it was not sent")
    cc.add_argument("key")
    cc.set_defaults(func=cmd_clear_click)
    fin = sub.add_parser("finish", help="fill a form in a visible window and submit it yourself")
    fin.add_argument("key")
    fin.set_defaults(func=cmd_finish)

    comp = sub.add_parser("companies", help="the boards to poll")
    csub = comp.add_subparsers(dest="companies_cmd", required=True)
    csub.add_parser("list")
    add = csub.add_parser("add")
    add.add_argument("ats", choices=("greenhouse", "lever", "ashby"))
    add.add_argument("slug")
    add.add_argument("name")
    comp.set_defaults(func=cmd_companies)

    sk = sub.add_parser("set-key", help="store a secret in the system keyring")
    sk.add_argument("name", choices=secrets.KNOWN_NAMES)
    sk.add_argument("--stdin", action="store_true", help="read the value from standard input")
    sk.set_defaults(func=cmd_set_key)
    st = sub.add_parser("set", help="change one setting in config/settings.yaml")
    st.add_argument("key")
    st.add_argument("value")
    st.set_defaults(func=cmd_set)
    dg = sub.add_parser("digest", help="write the daily digest")
    dg.add_argument("--print", action="store_true", help="also print it")
    dg.add_argument("--no-email", action="store_true", help="do not email it even when Gmail is connected")
    dg.set_defaults(func=cmd_digest)
    sub.add_parser("doctor", help="check the setup and say what is missing").set_defaults(func=cmd_doctor)
    sub.add_parser("inbox", help="read recent replies when Gmail is connected").set_defaults(func=cmd_inbox)
    gg = sub.add_parser("google", help="connect or disconnect your Google account")
    gsub = gg.add_subparsers(dest="google_cmd", required=True)
    gc = gsub.add_parser("connect")
    gc.add_argument("--client-file", required=True, help="the desktop OAuth client JSON from Google Cloud")
    gsub.add_parser("disconnect")
    gsub.add_parser("status")
    gg.set_defaults(func=cmd_google)
    sub.add_parser("sheet", help="sync the Google Sheet and apply decisions typed in it").set_defaults(func=cmd_sheet)
    sl = sub.add_parser("slots", help="propose free calendar slots for a scheduling reply")
    sl.add_argument("--count", type=int, default=4)
    sl.set_defaults(func=cmd_slots)
    sc = sub.add_parser("schedule", help="install or remove the scheduled jobs")
    sc.add_argument("schedule_cmd", choices=("install", "uninstall", "show"))
    sc.add_argument("--platform", choices=schedule.PLATFORMS)
    sc.set_defaults(func=cmd_schedule)
    dm = sub.add_parser("demo", help="try hirelane on invented data, without touching your own")
    dm.add_argument("--port", type=int)
    dm.add_argument("--no-serve", action="store_true", help="only write the demo data")
    dm.set_defaults(func=cmd_demo)
    web = sub.add_parser("web", help="start the web interface")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int)
    web.set_defaults(func=cmd_web)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ProfileError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
