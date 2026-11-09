"""Scheduling. ``hirelane run`` does the whole day, and these writers make a scheduler call it for you.

launchd on macOS, systemd user timers on Linux, and printed Task Scheduler commands on Windows. Cron works too,
see the README. The render functions are pure so the files can be checked without installing anything.
"""
from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .config import HOME_ENV

LABEL_PREFIX = "com.hirelane"
UNIT_PREFIX = "hirelane"
PLATFORMS = ("macos", "linux", "windows")


@dataclass(frozen=True)
class Job:
    name: str
    args: tuple[str, ...]             # arguments after "hirelane"
    times: tuple[str, ...]            # local times, HH:MM
    note: str = ""


DEFAULT_JOBS: tuple[Job, ...] = (
    Job("morning", ("run", "source", "build"), ("07:30",), "find roles and build resumes"),
    Job("fill", ("run", "submit"), ("12:30", "18:00"), "fill the forms of approved roles"),
    Job("inbox", ("inbox",), ("09:00", "13:00", "17:00", "21:00"), "read replies when Gmail is connected"),
    Job("digest", ("digest",), ("19:00",), "write the daily digest"),
)


def current_platform() -> str:
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def program(python: str | None = None) -> list[str]:
    return [python or sys.executable, "-m", "hirelane"]


def _hm(t: str) -> tuple[int, int]:
    h, m = t.split(":")
    return int(h), int(m)


def render_launchd(job: Job, home: Path, log_dir: Path, python: str | None = None) -> bytes:
    plist = {
        "Label": f"{LABEL_PREFIX}.{job.name}",
        "ProgramArguments": [*program(python), *job.args],
        "StartCalendarInterval": [{"Hour": _hm(t)[0], "Minute": _hm(t)[1]} for t in job.times],
        "EnvironmentVariables": {HOME_ENV: str(home)},
        "StandardOutPath": str(log_dir / f"{job.name}.log"),
        "StandardErrorPath": str(log_dir / f"{job.name}.err.log"),
        "ProcessType": "Background",
    }
    return plistlib.dumps(plist)


def render_systemd(job: Job, home: Path, python: str | None = None) -> tuple[str, str]:
    """The service and timer unit texts for one job."""
    exec_line = " ".join(shlex.quote(a) for a in [*program(python), *job.args])
    service = (f"[Unit]\nDescription=hirelane {job.name}: {job.note}\n\n[Service]\nType=oneshot\n"
               f"Environment={HOME_ENV}={shlex.quote(str(home))}\nExecStart={exec_line}\n")
    calendar = "\n".join(f"OnCalendar=*-*-* {t}:00" for t in job.times)
    timer = (f"[Unit]\nDescription=hirelane {job.name} timer\n\n[Timer]\n{calendar}\nPersistent=true\n\n"
             "[Install]\nWantedBy=timers.target\n")
    return service, timer


def render_windows(job: Job, home: Path, python: str | None = None) -> list[str]:
    """schtasks commands, one per time. The user runs them in a terminal."""
    cmd = " ".join(f'"{a}"' if " " in a else a for a in [*program(python), *job.args])
    wrapped = f'cmd /c "set {HOME_ENV}={home}&& {cmd}"'
    return [f'schtasks /Create /F /TN "hirelane {job.name} {i + 1}" /SC DAILY /ST {t} /TR "{wrapped}"'
            for i, t in enumerate(job.times)]


Runner = Callable[[Sequence[str]], int]


def _run(cmd: Sequence[str]) -> int:
    return subprocess.run(cmd, check=False, capture_output=True).returncode


def install(platform: str, home: Path, jobs: Sequence[Job] = DEFAULT_JOBS, *, target: Path | None = None,
            runner: Runner = _run, python: str | None = None) -> list[str]:
    """Write the scheduler files and load them. Returns a line per thing done."""
    if platform not in PLATFORMS:
        raise ValueError(f"platform must be one of {PLATFORMS}")
    log_dir = home / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    done: list[str] = []
    if platform == "windows":
        return ["Run these commands in a terminal:", *(c for j in jobs for c in render_windows(j, home, python))]
    if platform == "macos":
        launch_dir = target or Path.home() / "Library" / "LaunchAgents"
        launch_dir.mkdir(parents=True, exist_ok=True)
        for j in jobs:
            path = launch_dir / f"{LABEL_PREFIX}.{j.name}.plist"
            path.write_bytes(render_launchd(j, home, log_dir, python))
            code = runner(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)])
            note = "" if code == 0 else f" (launchctl exited {code}, it may be loaded already)"
            done.append(f"wrote {path}{note}")
        return done
    units = target or Path.home() / ".config" / "systemd" / "user"
    units.mkdir(parents=True, exist_ok=True)
    for j in jobs:
        service, timer = render_systemd(j, home, python)
        (units / f"{UNIT_PREFIX}-{j.name}.service").write_text(service)
        (units / f"{UNIT_PREFIX}-{j.name}.timer").write_text(timer)
        code = runner(["systemctl", "--user", "enable", "--now", f"{UNIT_PREFIX}-{j.name}.timer"])
        done.append(f"wrote {UNIT_PREFIX}-{j.name}.timer" + ("" if code == 0 else f" (systemctl exited {code})"))
    runner(["systemctl", "--user", "daemon-reload"])
    return done


def uninstall(platform: str, jobs: Sequence[Job] = DEFAULT_JOBS, *, target: Path | None = None,
              runner: Runner = _run) -> list[str]:
    done: list[str] = []
    if platform == "windows":
        return ["Run these commands in a terminal:", *(f'schtasks /Delete /F /TN "hirelane {j.name} {i + 1}"'
                                                       for j in jobs for i in range(len(j.times)))]
    if platform == "macos":
        launch_dir = target or Path.home() / "Library" / "LaunchAgents"
        for j in jobs:
            path = launch_dir / f"{LABEL_PREFIX}.{j.name}.plist"
            if path.exists():
                runner(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)])
                path.unlink()
                done.append(f"removed {path.name}")
        return done
    units = target or Path.home() / ".config" / "systemd" / "user"
    for j in jobs:
        runner(["systemctl", "--user", "disable", "--now", f"{UNIT_PREFIX}-{j.name}.timer"])
        for suffix in ("service", "timer"):
            path = units / f"{UNIT_PREFIX}-{j.name}.{suffix}"
            if path.exists():
                path.unlink()
                done.append(f"removed {path.name}")
    return done


def describe(jobs: Sequence[Job] = DEFAULT_JOBS) -> list[str]:
    return [f"{j.name:8} {', '.join(j.times):28} hirelane {' '.join(j.args)}  ({j.note})" for j in jobs]

