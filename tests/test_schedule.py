from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from hirelane import schedule
from hirelane.schedule import DEFAULT_JOBS, Job

HOME = Path("/tmp/af-home")
PY = "/usr/bin/python3"
JOB = Job("fill", ("run", "submit"), ("12:30", "18:00"), "fill forms")


def test_launchd_plist_has_calendar_entries_and_home() -> None:
    data = plistlib.loads(schedule.render_launchd(JOB, HOME, HOME / "logs", PY))
    assert data["Label"] == "com.hirelane.fill"
    assert data["ProgramArguments"] == [PY, "-m", "hirelane", "run", "submit"]
    assert data["StartCalendarInterval"] == [{"Hour": 12, "Minute": 30}, {"Hour": 18, "Minute": 0}]
    assert data["EnvironmentVariables"] == {"HIRELANE_HOME": str(HOME)}
    assert data["StandardOutPath"].endswith("fill.log")


def test_systemd_units() -> None:
    service, timer = schedule.render_systemd(JOB, Path("/home/a b/hirelane"), PY)
    assert "ExecStart=/usr/bin/python3 -m hirelane run submit" in service
    assert "Environment=HIRELANE_HOME='/home/a b/hirelane'" in service
    assert "Type=oneshot" in service
    assert timer.count("OnCalendar=") == 2 and "OnCalendar=*-*-* 12:30:00" in timer
    assert "Persistent=true" in timer and "WantedBy=timers.target" in timer


def test_windows_commands() -> None:
    cmds = schedule.render_windows(JOB, Path("C:/Users/alex/hirelane"), "C:/Python 311/python.exe")
    assert len(cmds) == 2
    assert cmds[0].startswith('schtasks /Create /F /TN "hirelane fill 1" /SC DAILY /ST 12:30')
    assert '"C:/Python 311/python.exe"' in cmds[0] and "HIRELANE_HOME=C:/Users/alex/hirelane" in cmds[0]


def test_install_macos_writes_plists_and_calls_launchctl(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    lines = schedule.install("macos", tmp_path / "home", target=tmp_path / "launch",
                             runner=lambda c: calls.append(list(c)) or 0, python=PY)
    assert len(lines) == len(DEFAULT_JOBS)
    assert sorted(p.name for p in (tmp_path / "launch").iterdir()) == sorted(
        f"com.hirelane.{j.name}.plist" for j in DEFAULT_JOBS)
    assert all(c[:2] == ["launchctl", "bootstrap"] for c in calls)
    assert (tmp_path / "home" / "data" / "logs").is_dir()


def test_install_linux_writes_units_and_enables_timers(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    schedule.install("linux", tmp_path / "home", target=tmp_path / "units",
                     runner=lambda c: calls.append(list(c)) or 0, python=PY)
    names = sorted(p.name for p in (tmp_path / "units").iterdir())
    assert "hirelane-morning.service" in names and "hirelane-digest.timer" in names
    assert ["systemctl", "--user", "enable", "--now", "hirelane-morning.timer"] in calls
    assert calls[-1] == ["systemctl", "--user", "daemon-reload"]


def test_a_failing_scheduler_command_is_reported_not_raised(tmp_path: Path) -> None:
    lines = schedule.install("macos", tmp_path / "h", target=tmp_path / "a", runner=lambda c: 5, python=PY)
    assert all("launchctl exited 5" in line for line in lines)


def test_uninstall_removes_only_what_it_wrote(tmp_path: Path) -> None:
    schedule.install("linux", tmp_path / "home", target=tmp_path / "units", runner=lambda c: 0, python=PY)
    (tmp_path / "units" / "someone-else.service").write_text("[Unit]\n")
    removed = schedule.uninstall("linux", target=tmp_path / "units", runner=lambda c: 0)
    assert len(removed) == 2 * len(DEFAULT_JOBS)
    assert [p.name for p in (tmp_path / "units").iterdir()] == ["someone-else.service"]


def test_windows_install_only_prints(tmp_path: Path) -> None:
    lines = schedule.install("windows", tmp_path, python="python")
    assert lines[0].startswith("Run these commands") and any("schtasks /Create" in x for x in lines)
    assert not (tmp_path / "data").exists() or not any((tmp_path / "data").glob("*.plist"))


def test_unknown_platform_and_describe() -> None:
    with pytest.raises(ValueError):
        schedule.install("plan9", HOME)
    assert any("hirelane run source build" in line for line in schedule.describe())
