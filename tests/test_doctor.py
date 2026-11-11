from __future__ import annotations

import pytest
import yaml

from hirelane import cli, doctor, secrets
from hirelane.config import Paths
from tests.bank_fixture import write_bank
from tests.profile_fixture import ALEX_PROFILE


def levels(paths: Paths) -> dict[str, str]:
    return {f.check: f.level for f in doctor.run_checks(paths)}


def test_a_new_install_fails_on_the_profile_only(home: Paths) -> None:
    result = levels(home)
    assert result["profile"] == doctor.FAIL and result["settings"] == doctor.OK
    assert result["facts"] == doctor.WARN and result["ai"] == doctor.OK


def test_a_complete_setup_passes(home: Paths) -> None:
    home.profile_file.write_text(yaml.safe_dump(ALEX_PROFILE))
    write_bank(home.experience)
    result = levels(home)
    assert result["profile"] == doctor.OK and result["facts"] == doctor.OK and "tracks" not in result


def test_ai_without_a_key_or_model_warns(home: Paths) -> None:
    home.settings_file.write_text("ai:\n  provider: openai\n  model: <model-id>\n")
    assert levels(home)["ai"] == doctor.WARN
    secrets.set_secret(secrets.AI_KEY, "k")
    assert levels(home)["ai"] == doctor.OK
    home.settings_file.write_text("ai:\n  provider: openai\n")
    assert levels(home)["ai"] == doctor.WARN


def test_a_broken_settings_file_stops_the_checks(home: Paths) -> None:
    home.settings_file.write_text("submit_mode: sideways\n")
    found = doctor.run_checks(home)
    assert [f.check for f in found] == ["settings"] and found[0].level == doctor.FAIL


def test_a_profile_without_tracks_warns(home: Paths) -> None:
    home.profile_file.write_text(yaml.safe_dump({"name": "Sam Lee", "email": "sam@example.com"}))
    assert levels(home)["tracks"] == doctor.WARN


def test_the_command_exits_nonzero_on_a_failure(home: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["doctor"]) == 1
    assert "hirelane init" in capsys.readouterr().out
