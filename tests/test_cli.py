from __future__ import annotations

import io

import pytest
import yaml

from hirelane import cli, secrets
from hirelane.config import Paths
from hirelane.db import DB
from hirelane.models import STATUS_NEEDS_YOU, STATUS_READY, Posting
from tests.conftest import MemoryKeyring
from tests.profile_fixture import ALEX_PROFILE


def add_job(home: Paths, status: str, job_id: str = "1") -> str:
    p = Posting(ats="greenhouse", slug="fabrikam", job_id=job_id, company="Fabrikam", title="Data Analyst")
    with DB(home.db) as db:
        return db.add_posting(p, status=status, fit="A").key


def test_status_on_an_empty_install(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "mode: review, daily cap: 10" in out and "applied so far: 0" in out


def test_status_lists_counts_and_waiting_items(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    add_job(home, STATUS_READY)
    with DB(home.db) as db:
        db.add_proposal(experience="", kind="skill", text="dbt")
    cli.main(["status"])
    out = capsys.readouterr().out
    assert "Resume ready: 1" in out and "1 proposed additions" in out


def test_jobs_filter(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    key = add_job(home, STATUS_READY)
    add_job(home, STATUS_NEEDS_YOU, "2")
    cli.main(["jobs", "--status", "Resume ready"])
    assert capsys.readouterr().out.strip().split("\t")[0] == key


def test_approve_and_errors(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    key = add_job(home, STATUS_READY)
    assert cli.main(["approve", key]) == 0
    assert "Approved Fabrikam" in capsys.readouterr().out
    assert cli.main(["approve", key]) == 1
    assert "not possible" in capsys.readouterr().err
    assert cli.main(["skip", "missing"]) == 1


def test_clear_click_records_an_attempt(home: Paths) -> None:
    key = add_job(home, STATUS_NEEDS_YOU)
    with DB(home.db) as db:
        db.add_attempt(key, "submit_clicked")
    assert cli.main(["clear-click", key]) == 0
    with DB(home.db) as db:
        assert db.attempt_phases(key)[-1] == "click_cleared"
    assert cli.main(["clear-click", "missing"]) == 1


def test_companies_add_and_list(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["companies", "add", "lever", "contoso", "Contoso"]) == 0
    assert cli.main(["companies", "add", "lever", "contoso", "Contoso"]) == 0
    assert capsys.readouterr().out.split() == ["Added.", "Already", "listed."]
    cli.main(["companies", "list"])
    assert capsys.readouterr().out.strip() == "lever\tcontoso\tContoso"
    assert cli.main(["companies", "add", "ashby", "bad slug!", "X"]) == 2


def test_set_key_reads_stdin_and_uses_the_keyring(home: Paths, monkeypatch: pytest.MonkeyPatch,
                                                  fake_keyring: MemoryKeyring,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("sk-example\n"))
    assert cli.main(["set-key", "ai-api-key", "--stdin"]) == 0
    assert secrets.get_secret(secrets.AI_KEY) == "sk-example"
    assert "sk-example" not in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    assert cli.main(["set-key", "ai-api-key", "--stdin"]) == 1


def test_set_changes_one_setting_and_validates(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["set", "daily_cap", "4"]) == 0
    assert "daily_cap: 4" in home.settings_file.read_text()
    assert cli.main(["set", "daily_cap", "999"]) == 2
    assert cli.main(["set", "submit_mode", "live"]) == 0


def test_a_missing_profile_is_a_usage_error(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "source"]) == 2
    assert "hirelane init" in capsys.readouterr().err


def test_run_source_with_a_profile_and_no_companies(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    home.profile_file.write_text(yaml.safe_dump(ALEX_PROFILE))
    assert cli.main(["run", "source"]) == 0
    assert "no companies listed" in capsys.readouterr().out


def test_help_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        cli.main(["--version"])
    assert info.value.code == 0 and "hirelane" in capsys.readouterr().out


def test_digest_writes_a_file(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["digest", "--print"]) == 0
    out = capsys.readouterr().out
    assert "Nothing new today." in out
    assert len(list((home.data / "outbox").glob("digest-*.txt"))) == 1


def test_schedule_show_and_windows_install(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["schedule", "show"]) == 0
    assert "hirelane run source build" in capsys.readouterr().out
    assert cli.main(["schedule", "install", "--platform", "windows"]) == 0
    assert "schtasks /Create" in capsys.readouterr().out


def test_init_command_with_a_resume(home: Paths, tmp_path, monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    from tests.test_resume_import import PLAIN

    resume = tmp_path / "resume.txt"
    resume.write_text(PLAIN)
    monkeypatch.setattr("builtins.input", lambda _text="": "")
    assert cli.main(["init", "--resume", str(resume)]) == 0
    out = capsys.readouterr().out
    assert "Imported 3 experiences, 4 bullets and 5 skills as a draft." in out
    assert cli.main(["init", "--resume", str(resume)]) == 2
    assert "--force" in capsys.readouterr().err
    assert cli.main(["init", "--resume", str(tmp_path / "missing.pdf"), "--force"]) == 2


def test_demo_seeds_its_own_home_and_leaves_the_real_one_alone(tmp_path, monkeypatch: pytest.MonkeyPatch,
                                                               capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("HIRELANE_HOME", "placeholder")      # registers the variable so monkeypatch restores it
    monkeypatch.delenv("HIRELANE_HOME")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert cli.main(["demo", "--no-serve"]) == 0
    assert "Seeded demo data for Alex Rivera" in capsys.readouterr().out
    assert (tmp_path / ".hirelane-demo" / "config" / "profile.yaml").exists()
    assert not (tmp_path / ".hirelane").exists()
    assert cli.main(["demo", "--no-serve"]) == 0
    assert "Using the existing demo data" in capsys.readouterr().out


def test_inbox_without_google_explains_itself(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["inbox"]) == 0
    assert "Gmail is not connected" in capsys.readouterr().out


def test_google_status_and_disconnect_toggle_the_setting(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["google", "status"]) == 0
    assert capsys.readouterr().out.strip() == "not connected"
    assert cli.main(["set", "google_enabled", "true"]) == 0
    assert cli.main(["google", "disconnect"]) == 0
    assert "google_enabled: false" in home.settings_file.read_text()
    assert cli.main(["google", "connect", "--client-file", str(home.home / "missing.json")]) == 1
    assert "could not read the client file" in capsys.readouterr().err


@pytest.mark.parametrize("command", [["sheet"], ["slots"]])
def test_sheet_and_slots_need_google(home: Paths, capsys: pytest.CaptureFixture[str], command: list[str]) -> None:
    assert cli.main(command) == 1
    assert "Google is not connected" in capsys.readouterr().err


def test_mark_submitted_records_the_job_and_rejects_unknown_keys(
        home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    key = add_job(home, STATUS_NEEDS_YOU)
    assert cli.main(["mark-submitted", key]) == 0
    with DB(home.db) as db:
        job = db.get_job(key)
        assert job is not None and job.status == "Submitted"
    capsys.readouterr()
    assert cli.main(["mark-submitted", "missing"]) == 1
    assert capsys.readouterr().err.strip()


def test_demo_ignores_a_real_home_variable(tmp_path, monkeypatch: pytest.MonkeyPatch,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    real = tmp_path / "real"
    monkeypatch.setenv("HIRELANE_HOME", str(real))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert cli.main(["demo", "--no-serve"]) == 0
    assert not (real / "config").exists()
    assert (tmp_path / ".hirelane-demo" / "config" / "profile.yaml").exists()


def test_empty_lists_say_what_to_do_next(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["companies", "list"]) == 0
    assert "No companies yet" in capsys.readouterr().out
    assert cli.main(["jobs"]) == 0
    assert "No jobs yet" in capsys.readouterr().out


def test_set_with_a_bad_value_is_a_friendly_error(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["set", "daily_cap", "abc"]) == 2
    assert "daily_cap cannot be set" in capsys.readouterr().err
